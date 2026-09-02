"""``sonar`` CLI: exit codes per the error matrix, offline replay, render, verify, spend.

Every test drives ``sonar.cli.main`` with injected factories; a factory that
raises proves that bad input exits ``2`` before any client exists. Live paths
use the scripted transport from ``test_pipeline``.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from sonar import cli, pipeline
from sonar.llm.base import LlmBackend
from sonar.models import Receipt
from sonar.monid import MonidClient
from sonar.pipeline import ARTIFACTS, BRIEF_MP3, FixtureLlm
from tests.test_pipeline import Script, client_for, smoke_script

ENV = {"MONID_API_KEY": "monid_test_KEY0123456789abcdef", "OPENAI_API_KEY": "sk-test-0123456789"}
NO_KEYS = {"SONAR_ENV": "/nonexistent/.env"}


def refuse_client(_key: str) -> MonidClient:
    raise AssertionError("a client was constructed before validation finished")


def refuse_llm(_key: str) -> LlmBackend:
    raise AssertionError("a seam backend was constructed before validation finished")


def fake_llm(_key: str) -> LlmBackend:
    return FixtureLlm()


def invoke(argv: Sequence[str], **kwargs: Any) -> tuple[int, str]:
    out = io.StringIO()
    err = io.StringIO()
    kwargs.setdefault("client_factory", refuse_client)
    kwargs.setdefault("llm_factory", refuse_llm)
    kwargs.setdefault("probe", lambda _key: "probe must not run")
    kwargs.setdefault("env", NO_KEYS)
    code = cli.main(list(argv), out=out, err=err, **kwargs)
    return code, out.getvalue()


def session_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir())


# --------------------------------------------------------------------------- validation


class TestValidationExits2BeforeAnyClient:
    @pytest.mark.parametrize(
        "argv",
        [
            ["run", "--profile", "smoke", "X"],
            ["run", "--profile", "lite", "Nubank", "--vs", "Inter", "C6"],
            ["run", "--profile", "full", "Nubank", "--vs", "A1", "B1", "C1", "D1"],
            ["run", "Nubank", "--vs", "Nubank"],
            ["run", "Nubank", "--alias", "nubank"],
            ["run", "--profile", "smoke", "Nubank", "--vs", "Inter"],
            ["run", "...", "--out", "/tmp/never"],
            ["plan", "--profile", "lite", "Nubank", "--vs", "Inter", "--vs", "C6"],
        ],
    )
    def test_bad_query_exits_2(self, argv: list[str], tmp_path: Path) -> None:
        code, text = invoke([*argv, "--out", str(tmp_path)] if argv[0] == "run" else argv, env=ENV)
        assert code == 2
        assert "invalid query" in text
        assert not list(tmp_path.iterdir())

    def test_missing_monid_key_exits_2_without_a_client(self, tmp_path: Path) -> None:
        code, text = invoke(["run", "--profile", "smoke", "Nubank", "--out", str(tmp_path)])
        assert code == 2 and "no Monid key" in text

    def test_missing_openai_key_exits_2_without_a_client(self, tmp_path: Path) -> None:
        env = {"MONID_API_KEY": ENV["MONID_API_KEY"], **NO_KEYS}
        code, text = invoke(
            ["run", "--profile", "smoke", "Nubank", "--out", str(tmp_path)], env=env
        )
        assert code == 2 and "no OpenAI key" in text

    def test_max_spend_refuses_with_exit_3_before_any_client(self, tmp_path: Path) -> None:
        code, text = invoke(
            [
                "run",
                "--profile",
                "full",
                "Nubank",
                "--vs",
                "Inter",
                "--max-spend",
                "0.10",
                "--out",
                str(tmp_path),
            ],
            env=ENV,
        )
        assert code == 3 and "REFUSED" in text
        assert not list(tmp_path.iterdir())

    def test_reconcile_unknown_session_exits_2(self, tmp_path: Path) -> None:
        code, text = invoke(["reconcile", "--session", "nope", "--out", str(tmp_path)], env=ENV)
        assert code == 2 and "no receipt" in text

    def test_verify_missing_file_exits_2(self, tmp_path: Path) -> None:
        code, text = invoke(["verify", str(tmp_path / "receipt.json")])
        assert code == 2 and "unreadable" in text

    def test_render_missing_dir_exits_2(self, tmp_path: Path) -> None:
        code, text = invoke(["render", "--from", str(tmp_path)])
        assert code == 2 and "missing" in text


# --------------------------------------------------------------------------- plan


class TestPlan:
    def test_plan_prints_query_and_estimate_without_a_client(self) -> None:
        code, text = invoke(
            ["plan", "--profile", "lite", "Nubank", "--vs", "Inter", "--alias", "Nu"]
        )
        assert code == 0
        assert '"brand": "Nubank"' in text and '"competitors": ["Inter"]' in text
        assert "Inter" in text and "estimate total $" in text
        assert "youtube_comment" in text and "(after youtube)" in text

    def test_plan_warns_when_estimate_exceeds_max_spend(self) -> None:
        code, text = invoke(["plan", "Nubank", "--vs", "Inter", "--max-spend", "0.01"])
        assert code == 0 and "WARNING" in text


# --------------------------------------------------------------------------- offline replay


class TestOfflineRun:
    def test_fixtures_run_writes_artifacts_then_verify_prints_replay(self, tmp_path: Path) -> None:
        code, text = invoke(
            ["run", "--fixtures", "--profile", "smoke", "Nubank", "--out", str(tmp_path), "--trace"]
        )
        assert code == 0, text
        (session_dir,) = session_dirs(tmp_path)
        names = {p.name for p in session_dir.iterdir()}
        assert set(ARTIFACTS) <= names and BRIEF_MP3 in names
        assert "verdict REPLAY" in text and "(offline replay)" in text
        receipt = Receipt.model_validate_json((session_dir / "receipt.json").read_text())
        assert receipt.replay and receipt.verdict == "REPLAY"
        assert receipt.mentions.fetched == 44 and receipt.totals.monid_usd == pytest.approx(0.2507)

        code, text = invoke(["verify", str(session_dir / "receipt.json")])
        assert code == 1
        assert "verdict REPLAY" in text and "replay receipt" in text

    def test_fixtures_run_with_explicit_dir_and_no_voice(self, tmp_path: Path) -> None:
        code, text = invoke(
            [
                "run",
                "--fixtures",
                str(pipeline.FIXTURES_DIR),
                "--profile",
                "smoke",
                "Nubank",
                "--no-voice",
                "--out",
                str(tmp_path),
                "--session",
                "20260902T120000Z-nubank-c0ffee",
            ]
        )
        assert code == 0, text
        session_dir = tmp_path / "20260902T120000Z-nubank-c0ffee"
        assert (session_dir / "receipt.json").is_file()
        assert not (session_dir / BRIEF_MP3).exists()

    def test_fixtures_dir_missing_exits_2(self, tmp_path: Path) -> None:
        code, text = invoke(
            [
                "run",
                "--fixtures",
                str(tmp_path / "nope"),
                "--profile",
                "smoke",
                "Nubank",
                "--out",
                str(tmp_path),
            ]
        )
        assert code == 2 and "fixtures directory not found" in text


# --------------------------------------------------------------------------- render


class TestRender:
    def test_render_from_prints_replay_banner_and_verdict(self, tmp_path: Path) -> None:
        invoke(["run", "--fixtures", "--profile", "smoke", "Nubank", "--out", str(tmp_path)])
        (session_dir,) = session_dirs(tmp_path)
        target = tmp_path / "rendered.md"
        code, text = invoke(["render", "--from", str(session_dir), "--out", str(target)])
        assert code == 0
        lines = text.splitlines()
        assert lines[0].startswith("> **REPLAY**")
        assert lines[1] == "verdict REPLAY"
        assert "# sonar digest — Nubank" in text and "# sonar receipt — Nubank" in text
        assert target.read_text().startswith("> **REPLAY**")

    def test_render_marks_a_live_receipt_as_replay(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        script = smoke_script()
        code, _ = invoke(
            ["run", "--profile", "smoke", "Nubank", "--out", str(tmp_path / "out")],
            env=ENV,
            client_factory=lambda key: client_for(script),
            llm_factory=fake_llm,
        )
        assert code == 0
        (session_dir,) = session_dirs(tmp_path / "out")
        stored = Receipt.model_validate_json((session_dir / "receipt.json").read_text())
        assert stored.verdict == "RECONCILED"
        code, text = invoke(["render", "--from", str(session_dir)])
        assert code == 0 and "verdict REPLAY" in text
        assert (
            Receipt.model_validate_json((session_dir / "receipt.json").read_text()).verdict
            == "RECONCILED"
        )


# --------------------------------------------------------------------------- live exit codes


class TestLiveExitCodes:
    def test_reconciled_live_run_exits_0_and_verify_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        script = smoke_script()
        code, text = invoke(
            [
                "run",
                "--profile",
                "smoke",
                "Nubank",
                "--alias",
                "Nu",
                "--out",
                str(tmp_path / "out"),
            ],
            env=ENV,
            client_factory=lambda key: client_for(script),
            llm_factory=fake_llm,
        )
        assert code == 0, text
        assert "verdict RECONCILED" in text
        (session_dir,) = session_dirs(tmp_path / "out")
        code, text = invoke(["verify", str(session_dir / "receipt.json")])
        assert code == 0 and "verdict RECONCILED" in text
        assert (tmp_path / ".sonar" / "cache" / "labels.jsonl").is_file()

    def test_stubbed_402_halts_with_exit_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        script = smoke_script(reject_402=True)
        code, text = invoke(
            ["run", "--profile", "smoke", "Nubank", "--out", str(tmp_path / "out")],
            env=ENV,
            client_factory=lambda key: client_for(script),
            llm_factory=fake_llm,
        )
        assert code == 3
        assert "HALTED" in text
        (session_dir,) = session_dirs(tmp_path / "out")
        receipt = Receipt.model_validate_json((session_dir / "receipt.json").read_text())
        assert any(a.reason == "halted" and a.scope == "session" for a in receipt.abstentions)

    def test_listing_failure_exits_4_and_reconcile_recovers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        script = smoke_script(fail_listing=True)
        out_root = tmp_path / "out"
        code, text = invoke(
            ["run", "--profile", "smoke", "Nubank", "--out", str(out_root)],
            env=ENV,
            client_factory=lambda key: client_for(script),
            llm_factory=fake_llm,
        )
        assert code == 4 and "PARTIAL" in text
        (session_dir,) = session_dirs(out_root)
        session_id = session_dir.name

        code, text = invoke(
            ["reconcile", "--session", session_id, "--out", str(out_root)],
            env=ENV,
            client_factory=lambda key: client_for(script),
        )
        assert code == 4 and "verdict PARTIAL" in text

        script.fail_listing = False
        code, text = invoke(
            ["reconcile", "--session", session_id, "--out", str(out_root)],
            env=ENV,
            client_factory=lambda key: client_for(script),
        )
        assert code == 0 and "verdict RECONCILED" in text
        code, text = invoke(["verify", str(session_dir / "receipt.json")])
        assert code == 0

        code, text = invoke(["spend", "--out", str(out_root)])
        assert code == 0 and session_id in text and "running total" in text
        code, text = invoke(["spend", "--out", str(out_root), "--session", "missing"])
        assert code == 2


# --------------------------------------------------------------------------- doctor and record


class TestDoctor:
    def test_missing_keys_exit_2_without_a_client(self, tmp_path: Path) -> None:
        code, text = invoke(["doctor", "--out", str(tmp_path)])
        assert code == 2
        assert "monid key: MISSING" in text and "openai key: MISSING" in text

    def test_reachable_services_exit_0(self, tmp_path: Path) -> None:
        script: Script = smoke_script()
        code, text = invoke(
            ["doctor", "--out", str(tmp_path)],
            env=ENV,
            client_factory=lambda key: client_for(script),
            probe=lambda key: None,
        )
        assert code == 0, text
        assert "monid api: reachable" in text and "openai api: reachable" in text
        assert "doctor: ok" in text

    def test_unreachable_openai_exits_1(self, tmp_path: Path) -> None:
        script: Script = smoke_script()
        code, text = invoke(
            ["doctor", "--out", str(tmp_path)],
            env=ENV,
            client_factory=lambda key: client_for(script),
            probe=lambda key: "HTTP 401: bad key",
        )
        assert code == 1 and "openai api: UNREACHABLE" in text


class TestRecord:
    def test_dry_run_delegates_to_the_recorder_script(self, tmp_path: Path) -> None:
        code, text = invoke(
            ["record", "--profile", "smoke", "Nubank", "--dry-run", "--fixtures-dir", str(tmp_path)]
        )
        assert code == 0
        assert "dry run: no run submitted" in text
