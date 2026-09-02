"""Drive the sonar skill's scripts the way an agent would: as child processes, JSON in,
JSON out, on the offline fixtures path, with the keys stripped from the environment.

The gate semantics are the point: nothing runs past ``plan`` until ``decisions.json``
approves the exact plan, and a stale, rejected, under-capped or absent decision refuses.
``sonar ask`` is stubbed through ``SONAR_CLI`` because the chat wave lands separately.

Type-check together with the scripts::

    uv run mypy --strict skill/sonar/scripts/*.py tests/test_skill_driver.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / "skill" / "sonar"
SCRIPTS = SKILL_DIR / "scripts"
SKILL_MD = SKILL_DIR / "SKILL.md"
FIXTURES = ROOT / "tests" / "fixtures"

STEP_IDS = ("doctor", "plan", "spend-approval", "run", "verify", "ask")
KEY_VARS = ("MONID_API_KEY", "OPENAI_API_KEY")


def clean_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """The process env without any key and with ``SONAR_ENV`` pointing at nothing."""
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARS and k != "SONAR_CLI"}
    env["SONAR_ENV"] = str(tmp_path / "no-such-env")
    env.update(extra)
    return env


def call(script: str, *args: str, env: dict[str, str]) -> tuple[int, dict[str, Any], str]:
    """Run one skill script; stdout must be exactly one JSON object."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic only
        raise AssertionError(
            f"{script} did not print one JSON object\nstdout: {completed.stdout!r}\n"
            f"stderr: {completed.stderr!r}"
        ) from exc
    assert isinstance(payload, dict)
    assert payload["exit_code"] == completed.returncode
    return completed.returncode, payload, completed.stderr


def write_request(workspace: Path, **fields: Any) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    request = {"brand": "Nubank", "profile": "smoke", **fields}
    (workspace / "request.json").write_text(json.dumps(request), encoding="utf-8")


def plan_digest(workspace: Path) -> str:
    plan = json.loads((workspace / "plan.json").read_text(encoding="utf-8"))
    digest = plan["plan_digest"]
    assert isinstance(digest, str)
    return digest


def decide(
    workspace: Path,
    *,
    decision_type: str = "approve_spend",
    approved: bool = True,
    max_spend_usd: float | None = 1.0,
    digest: str | None = None,
) -> None:
    """Append one spend-approval decision, the way the driver or a human does."""
    path = workspace / "decisions.json"
    decisions: list[dict[str, Any]] = (
        json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    )
    decisions.append(
        {
            "decision_type": decision_type,
            "scope_key": "spend-approval",
            "new_value": {
                "approved": approved,
                "max_spend_usd": max_spend_usd,
                "plan_digest": digest if digest is not None else plan_digest(workspace),
            },
            "decided_by": "test-driver",
            "decided_at": "2026-09-02T12:00:00+00:00",
            "source_step": "spend-approval",
        }
    )
    path.write_text(json.dumps(decisions, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    write_request(ws)
    return ws


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return clean_env(tmp_path)


@pytest.fixture
def planned(workspace: Path, env: dict[str, str]) -> Path:
    code, payload, _ = call("plan.py", "--workspace", str(workspace), env=env)
    assert code == 0, payload
    return workspace


# --------------------------------------------------------------------------- doctor


class TestDoctor:
    def test_no_keys_reports_missing_and_exits_2(
        self, workspace: Path, env: dict[str, str]
    ) -> None:
        workspace.mkdir(exist_ok=True)
        code, payload, _ = call(
            "doctor.py", "--workspace", str(workspace), "--root", str(workspace / "none"), env=env
        )
        assert code == 2 and payload["ok"] is False
        assert payload["monid_key"].startswith("MISSING")
        assert payload["openai_key"].startswith("MISSING")
        assert payload["monid_api"] is None and payload["openai_api"] is None
        assert "budget cap $10.00" in payload["wallet"]
        stored = json.loads((workspace / "doctor.json").read_text(encoding="utf-8"))
        assert stored["exit_code"] == 2 and stored["lines"] == payload["lines"]


# --------------------------------------------------------------------------- plan


class TestPlan:
    def test_prints_the_estimate_and_writes_plan_json(
        self, workspace: Path, env: dict[str, str]
    ) -> None:
        code, payload, _ = call("plan.py", "--workspace", str(workspace), env=env)
        assert code == 0 and payload["ok"] is True
        assert payload["query"]["brand"] == "Nubank"
        assert payload["query"]["sources"] == ["reddit", "google_maps"]
        assert payload["estimate_usd"] == pytest.approx(0.2818)
        assert payload["brands"] == 1 and payload["exceeds_max_spend"] is False
        assert any(line.startswith("estimate total $0.2818") for line in payload["lines"])
        assert re.fullmatch(r"[0-9a-f]{16}", payload["plan_digest"])
        stored = json.loads((workspace / "plan.json").read_text(encoding="utf-8"))
        assert stored["plan_digest"] == payload["plan_digest"]

    def test_request_from_stdin_and_a_named_file(self, tmp_path: Path, env: dict[str, str]) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        request = {
            "brand": "Nubank",
            "profile": "lite",
            "competitors": ["Inter"],
            "aliases": ["nu"],
        }
        named = tmp_path / "req.json"
        named.write_text(json.dumps(request), encoding="utf-8")
        code, payload, _ = call("plan.py", "--workspace", str(ws), "--in", str(named), env=env)
        assert code == 0 and payload["query"]["competitors"] == ["Inter"]
        assert payload["query"]["brand_aliases"] == ["nu"] and payload["brands"] == 2
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "plan.py"), "--workspace", str(ws), "--in", "-"],
            cwd=ROOT,
            env=env,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert json.loads(completed.stdout)["plan_digest"] == payload["plan_digest"]

    @pytest.mark.parametrize(
        "fields",
        [
            {"brand": "X"},
            {"brand": "Nubank", "profile": "lite", "competitors": ["Inter", "C6"]},
            {"brand": "Nubank", "profile": "full", "competitors": ["A1", "B1", "C1", "D1"]},
            {"brand": "Nubank", "competitors": ["Nubank"]},
            {"brand": "Nubank", "aliases": ["nubank"]},
        ],
    )
    def test_the_cli_validators_refuse_with_exit_2(
        self, tmp_path: Path, env: dict[str, str], fields: dict[str, Any]
    ) -> None:
        ws = tmp_path / "ws"
        write_request(ws, **fields)
        code, payload, _ = call("plan.py", "--workspace", str(ws), env=env)
        assert code == 2 and payload["ok"] is False and "invalid query" in payload["error"]
        assert not (ws / "plan.json").exists()

    @pytest.mark.parametrize(
        "raw",
        ["[]", '{"profile": "smoke"}', '{"brand": "Nubank", "profile": "huge"}', "not json"],
    )
    def test_a_malformed_request_exits_2_before_the_cli(
        self, tmp_path: Path, env: dict[str, str], raw: str
    ) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "request.json").write_text(raw, encoding="utf-8")
        code, payload, _ = call("plan.py", "--workspace", str(ws), env=env)
        assert code == 2 and payload["ok"] is False and payload["error"]

    def test_max_spend_below_the_estimate_is_flagged(
        self, tmp_path: Path, env: dict[str, str]
    ) -> None:
        ws = tmp_path / "ws"
        write_request(ws, max_spend_usd=0.1)
        code, payload, _ = call("plan.py", "--workspace", str(ws), env=env)
        assert code == 0 and payload["exceeds_max_spend"] is True
        assert not any(line.startswith("WARNING") for line in payload["lines"])


# --------------------------------------------------------------------------- the gate


class TestGate:
    def test_request_writes_escalation_and_exits_3(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        code, payload, _ = call("gate.py", "request", "--workspace", str(planned), env=env)
        assert code == 3 and payload["status"] == "awaiting_approval"
        escalation = json.loads((planned / "escalation.json").read_text(encoding="utf-8"))
        assert escalation["step"] == "spend-approval"
        (item,) = escalation["items"]
        assert item["item_id"] == "spend-approval"
        assert item["estimate_usd"] == pytest.approx(0.2818)
        assert item["plan_digest"] == plan_digest(planned)
        assert item["query"]["brand"] == "Nubank"
        shape = item["resolution_shape"]
        assert shape["scope_key"] == "spend-approval" and shape["source_step"] == "spend-approval"
        assert shape["new_value"]["plan_digest"] == plan_digest(planned)

    def test_request_without_a_plan_exits_3(self, tmp_path: Path, env: dict[str, str]) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        code, payload, _ = call("gate.py", "request", "--workspace", str(ws), env=env)
        assert code == 3 and payload["status"] == "no_plan"
        assert not (ws / "escalation.json").exists()

    def test_check_without_decisions_refuses(self, planned: Path, env: dict[str, str]) -> None:
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3 and payload["approved"] is False
        assert "no spend-approval decision" in payload["reason"]

    def test_check_approves_the_exact_plan(self, planned: Path, env: dict[str, str]) -> None:
        decide(planned, max_spend_usd=0.3)
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 0 and payload["approved"] is True
        assert payload["approved_max_spend_usd"] == pytest.approx(0.3)
        assert payload["decided_by"] == "test-driver"

    def test_rejection_refuses(self, planned: Path, env: dict[str, str]) -> None:
        decide(planned, decision_type="reject_spend", approved=False)
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3 and payload["reason"] == "spend rejected"

    def test_a_cap_below_the_estimate_refuses(self, planned: Path, env: dict[str, str]) -> None:
        decide(planned, max_spend_usd=0.2)
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3 and "below the estimate" in payload["reason"]

    def test_a_stale_digest_refuses_after_a_replan(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned)
        write_request(planned, profile="lite")
        code, _, _ = call("plan.py", "--workspace", str(planned), env=env)
        assert code == 0
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3 and "current plan is" in payload["reason"]

    def test_the_newest_decision_wins(self, planned: Path, env: dict[str, str]) -> None:
        decide(planned)
        decide(planned, decision_type="reject_spend", approved=False)
        code, _, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3
        decide(planned)
        code, _, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 0

    @pytest.mark.parametrize(
        "new_value",
        [
            {"approved": False, "max_spend_usd": 1.0},
            {"approved": True},
            {"approved": True, "max_spend_usd": "1.0"},
            {"approved": True, "max_spend_usd": True},
        ],
    )
    def test_malformed_approvals_refuse(
        self, planned: Path, env: dict[str, str], new_value: dict[str, Any]
    ) -> None:
        entry = {
            "decision_type": "approve_spend",
            "scope_key": "spend-approval",
            "new_value": {**new_value, "plan_digest": plan_digest(planned)},
            "decided_by": "test-driver",
        }
        (planned / "decisions.json").write_text(json.dumps([entry]), encoding="utf-8")
        code, payload, _ = call("gate.py", "check", "--workspace", str(planned), env=env)
        assert code == 3 and payload["approved"] is False


# --------------------------------------------------------------------------- run


class TestRun:
    def test_refuses_without_approval_and_creates_no_session(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        code, payload, _ = call("run.py", "--workspace", str(planned), "--fixtures", env=env)
        assert code == 3 and payload["status"] == "refused" and payload["submitted"] is False
        assert not (planned / "session").exists() and not (planned / "run.json").exists()

    def test_refuses_without_a_plan_at_all(self, tmp_path: Path, env: dict[str, str]) -> None:
        ws = tmp_path / "ws"
        write_request(ws)
        decide(ws, digest="0000000000000000")
        code, payload, _ = call("run.py", "--workspace", str(ws), "--fixtures", env=env)
        assert code == 3 and "no plan.json" in payload["reason"]
        assert not (ws / "session").exists()

    def test_refuses_a_stale_approval_after_a_replan(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned)
        write_request(planned, profile="lite")
        call("plan.py", "--workspace", str(planned), env=env)
        code, payload, _ = call("run.py", "--workspace", str(planned), "--fixtures", env=env)
        assert code == 3 and payload["submitted"] is False
        assert not (planned / "session").exists()

    def test_approved_offline_run_writes_the_session_and_run_json(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned, max_spend_usd=0.5)
        code, payload, _ = call("run.py", "--workspace", str(planned), "--fixtures", env=env)
        assert code == 0, payload
        assert payload["status"] == "ok" and payload["submitted"] is True
        assert payload["offline"] is True and payload["approved_max_spend_usd"] == 0.5
        session = planned / "session"
        assert (session / "receipt.json").is_file() and (session / "digest.md").is_file()
        receipt = payload["receipt"]
        assert receipt["verdict"] == "REPLAY" and receipt["replay"] is True
        assert receipt["mentions"]["fetched"] == 44
        assert receipt["totals"]["monid_usd"] == pytest.approx(0.2507)
        assert any(line.startswith("verdict REPLAY") for line in payload["lines"])
        stored = json.loads((planned / "run.json").read_text(encoding="utf-8"))
        assert stored["receipt"]["session_id"] == receipt["session_id"]

    def test_the_approved_cap_is_the_max_spend_the_cli_sees(
        self, tmp_path: Path, env: dict[str, str]
    ) -> None:
        """The request asked for a cap below the estimate; the approval's cap governs."""
        ws = tmp_path / "ws"
        write_request(ws, max_spend_usd=0.1)
        code, _, _ = call("plan.py", "--workspace", str(ws), env=env)
        assert code == 0
        decide(ws, max_spend_usd=0.4)
        code, payload, _ = call(
            "run.py", "--workspace", str(ws), "--fixtures", "--no-voice", env=env
        )
        assert code == 0, payload
        assert payload["receipt"]["verdict"] == "REPLAY"
        assert not (ws / "session" / "brief.mp3").exists()

    def test_a_missing_fixtures_dir_exits_2(self, planned: Path, env: dict[str, str]) -> None:
        decide(planned)
        code, payload, _ = call(
            "run.py", "--workspace", str(planned), "--fixtures", str(planned / "nope"), env=env
        )
        assert code == 2 and payload["submitted"] is True and payload["receipt"] is None
        assert any("fixtures directory not found" in line for line in payload["lines"])

    def test_live_path_without_keys_exits_2_without_spending(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned)
        code, payload, _ = call("run.py", "--workspace", str(planned), env=env)
        assert code == 2 and payload["offline"] is False
        assert any(line.startswith("no Monid key") for line in payload["lines"])
        assert not (planned / "session" / "receipt.json").exists()


# --------------------------------------------------------------------------- verify


class TestVerify:
    def test_replay_receipt_exits_1_and_marks_the_run_complete(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned)
        assert call("run.py", "--workspace", str(planned), "--fixtures", env=env)[0] == 0
        code, payload, _ = call("verify.py", "--workspace", str(planned), env=env)
        assert code == 1 and payload["verdict"] == "REPLAY"
        assert payload["derived_verdict"] == "REPLAY" and payload["reconciled"] is False
        assert payload["status"] == "not_reconciled"
        assert any("replay receipt" in p for p in payload["problems"])
        assert "next" not in payload
        complete = json.loads((planned / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
        assert complete["verdict"] == "REPLAY" and complete["exit_code"] == 1
        assert (planned / "verify.json").is_file()

    def test_missing_receipt_exits_2_and_does_not_complete(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        code, payload, _ = call("verify.py", "--workspace", str(planned), env=env)
        assert code == 2 and payload["status"] == "missing"
        assert not (planned / "RUN_COMPLETE.json").exists()

    def test_partial_receipt_names_the_reconcile_command(
        self, planned: Path, tmp_path: Path
    ) -> None:
        """A tampered card fails the content digest (exit 2), so PARTIAL comes from a stub CLI."""
        stub = tmp_path / "stub_verify.py"
        stub.write_text(STUB_VERIFY_PARTIAL, encoding="utf-8")
        session = planned / "session"
        session.mkdir()
        (session / "receipt.json").write_text("{}", encoding="utf-8")
        env = clean_env(tmp_path, SONAR_CLI=f"{sys.executable} {stub}")
        code, payload, _ = call("verify.py", "--workspace", str(planned), env=env)
        assert code == 1 and payload["verdict"] == "PARTIAL"
        assert payload["derived_verdict"] == "PARTIAL" and payload["status"] == "not_reconciled"
        assert payload["problems"] == ["unreconciled local_seq: 1"]
        assert payload["next"] == f"sonar reconcile --session {session}"
        complete = json.loads((planned / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
        assert complete["verdict"] == "PARTIAL" and complete["reconciled"] is False

    def test_a_tampered_card_is_invalid_with_exit_2(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        decide(planned)
        assert call("run.py", "--workspace", str(planned), "--fixtures", env=env)[0] == 0
        receipt_path = planned / "session" / "receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["replay"] = False
        receipt["verdict"] = "PARTIAL"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        code, payload, _ = call("verify.py", "--workspace", str(planned), env=env)
        assert code == 2 and payload["status"] == "invalid"
        assert payload["verdict"] == "PARTIAL" and "next" not in payload
        assert any("content_digest" in p for p in payload["problems"])


STUB_VERIFY_PARTIAL = """
import sys
if sys.argv[1:2] != ["verify"]:
    sys.exit(2)
print("verdict PARTIAL (re-derived PARTIAL); status not_reconciled")
print("- unreconciled local_seq: 1")
sys.exit(1)
"""


# --------------------------------------------------------------------------- ask


STUB_CLI_WITHOUT_ASK = """
import sys
sys.stderr.write("usage: sonar [-h] {doctor,plan,run,reconcile,spend,record,render,verify} ...\\n")
sys.stderr.write("sonar: error: argument command: invalid choice: 'ask' (choose from doctor, plan)\\n")
sys.exit(2)
"""

STUB_CLI = """
import json, sys
args = sys.argv[1:]
if args[:1] != ["ask"]:
    sys.exit(2)
brand, question = args[1], args[2]
session = args[args.index("--session") + 1]
print("retrieved 3 mentions")
print(json.dumps({"brand": brand, "question": question, "answer": "Net went up.",
                  "citations": ["abc"], "verified_numbers": [], "status": "ok",
                  "session_dir": session}))
"""


class TestAsk:
    def test_unavailable_when_the_cli_has_no_ask_command(
        self, planned: Path, tmp_path: Path
    ) -> None:
        """A build without ``ask`` rejects the subcommand in argparse; the script says so."""
        stub = tmp_path / "stub_no_ask.py"
        stub.write_text(STUB_CLI_WITHOUT_ASK, encoding="utf-8")
        env = clean_env(tmp_path, SONAR_CLI=f"{sys.executable} {stub}")
        code, payload, _ = call("ask.py", "--workspace", str(planned), "--question", "q?", env=env)
        assert code == 2 and payload["status"] == "unavailable"
        assert payload["brand"] == "Nubank"
        assert not (planned / "answers.jsonl").exists()

    def test_the_real_cli_without_keys_is_an_error_not_an_answer(
        self, planned: Path, env: dict[str, str]
    ) -> None:
        code, payload, _ = call("ask.py", "--workspace", str(planned), "--question", "q?", env=env)
        assert code != 0 and payload["status"] in {"unavailable", "error"}
        assert (
            payload["answer"] is None if payload["status"] == "error" else "answer" not in payload
        )

    def test_no_brand_and_no_plan_exits_2(self, tmp_path: Path, env: dict[str, str]) -> None:
        ws = tmp_path / "ws"
        ws.mkdir()
        code, payload, _ = call("ask.py", "--workspace", str(ws), "--question", "q?", env=env)
        assert code == 2 and "no brand" in payload["error"]

    def test_answer_is_parsed_and_appended(self, planned: Path, tmp_path: Path) -> None:
        stub = tmp_path / "stub_cli.py"
        stub.write_text(STUB_CLI, encoding="utf-8")
        env = clean_env(tmp_path, SONAR_CLI=f"{sys.executable} {stub}")
        code, payload, _ = call(
            "ask.py", "--workspace", str(planned), "--question", "What changed?", env=env
        )
        assert code == 0 and payload["status"] == "ok"
        assert payload["answer"]["answer"] == "Net went up."
        assert payload["answer"]["citations"] == ["abc"]
        assert payload["answer"]["session_dir"] == str(planned / "session")
        assert payload["text"] is None
        rows = (planned / "answers.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(rows) == 1 and json.loads(rows[0])["question"] == "What changed?"
        call(
            "ask.py",
            "--workspace",
            str(planned),
            "--question",
            "Again?",
            "--brand",
            "Inter",
            env=env,
        )
        rows = (planned / "answers.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(rows) == 2 and json.loads(rows[1])["brand"] == "Inter"


# --------------------------------------------------------------------------- the skill file


def frontmatter() -> str:
    text = SKILL_MD.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    head, _, _ = text[4:].partition("\n---\n")
    return head


class TestSkillFile:
    def test_frontmatter_names_the_skill_and_the_six_steps_in_order(self) -> None:
        head = frontmatter()
        assert re.search(r"^name: sonar$", head, flags=re.MULTILINE)
        assert re.search(r"^description: .+", head, flags=re.MULTILINE)
        assert re.search(r"^process:$", head, flags=re.MULTILINE)
        ids = re.findall(r"^\s+- id: ([a-z-]+)$", head, flags=re.MULTILINE)
        assert tuple(ids) == STEP_IDS

    def test_spend_approval_is_a_human_approval_gate(self) -> None:
        head = frontmatter()
        block = head.split("- id: spend-approval", 1)[1].split("- id: run", 1)[0]
        assert "assignee_role: human" in block
        assert re.search(r"gate:\s*\n\s*type: approval\s*\n\s*role: budget_owner", block)
        for step in ("doctor", "plan", "run", "verify", "ask"):
            step_block = head.split(f"- id: {step}\n", 1)[1].split("- id:", 1)[0]
            assert "assignee_role: agent" in step_block

    def test_the_body_states_the_gate_and_the_escalation_files(self) -> None:
        body = SKILL_MD.read_text(encoding="utf-8").split("\n---\n", 1)[1]
        for needle in (
            "escalation.json",
            "decisions.json",
            "approve_spend",
            "reject_spend",
            "plan_digest",
            "gate.py check",
            "RUN_COMPLETE.json",
        ):
            assert needle in body, needle
        for script in ("doctor.py", "plan.py", "gate.py", "run.py", "verify.py", "ask.py"):
            assert f"scripts/{script}" in body and (SCRIPTS / script).is_file()

    def test_no_placeholders_in_the_skill(self) -> None:
        markers = ("TB" + "D", "TO" + "DO")  # spelled apart so this file passes the same gate
        for path in (SKILL_MD, *sorted(SCRIPTS.glob("*.py"))):
            text = path.read_text(encoding="utf-8")
            assert not any(marker in text for marker in markers), path


# --------------------------------------------------------------------------- keys


class TestNoKeyEverTouched:
    def test_scripts_never_name_a_key_variable_or_embed_a_key(self) -> None:
        for path in sorted(SCRIPTS.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            code = "\n".join(
                line
                for line in text.splitlines()
                if not line.lstrip().startswith(("#", '"""', "``"))
            )
            body = code.split('"""', 2)[-1] if code.count('"""') >= 2 else code
            for var in KEY_VARS:
                assert var not in body, f"{path.name} names {var}"
            assert not re.search(r"monid_live_[A-Za-z0-9]", text), path
            assert not re.search(r"\bsk-[A-Za-z0-9]{8,}", text), path
            assert ".sonar" not in body, f"{path.name} reaches for ~/.sonar"

    def test_the_offline_path_needs_no_key(self, planned: Path, tmp_path: Path) -> None:
        env = clean_env(tmp_path)
        for var in KEY_VARS:
            assert var not in env
        decide(planned)
        code, payload, _ = call("run.py", "--workspace", str(planned), "--fixtures", env=env)
        assert code == 0 and payload["receipt"]["verdict"] == "REPLAY"

    def test_a_key_in_the_environment_is_never_echoed(self, planned: Path, tmp_path: Path) -> None:
        """A key present in the env reaches the CLI untouched and never appears in any JSON."""
        secret = "monid_live_SECRET0123456789"
        env = clean_env(tmp_path, MONID_API_KEY=secret, OPENAI_API_KEY="sk-SECRET0123456789")
        outputs: list[str] = []
        steps: list[tuple[str, list[str]]] = [
            ("plan.py", ["--workspace", str(planned)]),
            ("gate.py", ["request", "--workspace", str(planned)]),
            ("gate.py", ["check", "--workspace", str(planned)]),
            ("run.py", ["--workspace", str(planned), "--fixtures"]),
            ("verify.py", ["--workspace", str(planned)]),
        ]
        for script, argv in steps:
            completed = subprocess.run(
                [sys.executable, str(SCRIPTS / script), *argv],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            outputs.append(completed.stdout + completed.stderr)
            if argv[0] == "request":
                decide(planned)
        for path in planned.rglob("*.json"):
            outputs.append(path.read_text(encoding="utf-8"))
        joined = "\n".join(outputs)
        assert "SECRET" not in joined
