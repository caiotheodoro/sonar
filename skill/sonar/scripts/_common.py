"""Shared plumbing for the sonar skill scripts: JSON in, JSON out, the CLI as a subprocess.

Every script reads its input from a JSON file (``--in``, ``-`` for stdin) or from the
workspace, calls the ``sonar`` command line as a child process and prints exactly one
JSON object on stdout. No script reads, stores or forwards an API key: the CLI loads
``MONID_API_KEY`` and ``OPENAI_API_KEY`` itself from the process environment or from
``$SONAR_ENV`` / ``~/.sonar/.env`` (see ``sonar.monid.client``). The child inherits
the environment untouched.

Exit codes mirror the CLI's error matrix: ``0`` ok, ``1`` a service did not answer,
``2`` bad input, ``3`` refused (spend not approved, estimate over the cap or the Monid
402 breaker), ``4`` the receipt is not ``RECONCILED``.

``SONAR_CLI`` (a whitespace-split command prefix) replaces the default
``python -m sonar.cli`` invocation; tests use it to stand in a stub for commands that
do not exist yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

EXIT_OK: Final[int] = 0
EXIT_UNREACHABLE: Final[int] = 1
EXIT_USAGE: Final[int] = 2
EXIT_REFUSED: Final[int] = 3
EXIT_PARTIAL: Final[int] = 4

SONAR_CLI_VAR: Final[str] = "SONAR_CLI"

REQUEST_JSON: Final[str] = "request.json"
DOCTOR_JSON: Final[str] = "doctor.json"
PLAN_JSON: Final[str] = "plan.json"
ESCALATION_JSON: Final[str] = "escalation.json"
DECISIONS_JSON: Final[str] = "decisions.json"
RUN_JSON: Final[str] = "run.json"
VERIFY_JSON: Final[str] = "verify.json"
ANSWERS_JSONL: Final[str] = "answers.jsonl"
RUN_COMPLETE_JSON: Final[str] = "RUN_COMPLETE.json"
SESSION_DIR: Final[str] = "session"
RECEIPT_JSON: Final[str] = "receipt.json"

GATE_STEP: Final[str] = "spend-approval"
GATE_ITEM_ID: Final[str] = "spend-approval"
APPROVE_DECISION: Final[str] = "approve_spend"
REJECT_DECISION: Final[str] = "reject_spend"

PROFILES: Final[tuple[str, ...]] = ("smoke", "lite", "full")


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def emit(payload: dict[str, Any], code: int) -> int:
    """Print one JSON object and return the exit code (the only stdout a script writes)."""
    payload.setdefault("exit_code", code)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return code


def read_json(path: Path | str) -> Any:
    if str(path) == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest_of(payload: Any) -> str:
    """Stable sha256 (first 16 hex) of a JSON value; keys sorted, floats as written."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def workspace_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        metavar="DIR",
        help="the skill's working directory: request.json in, every artifact out",
    )
    return parser


def sonar_argv() -> list[str]:
    """The command prefix for the CLI: ``$SONAR_CLI`` split, else ``python -m sonar.cli``."""
    override = os.environ.get(SONAR_CLI_VAR, "").strip()
    if override:
        return shlex.split(override)
    return [sys.executable, "-m", "sonar.cli"]


@dataclass(frozen=True)
class CliResult:
    argv: list[str]
    exit_code: int
    stdout: str
    stderr: str

    @property
    def lines(self) -> list[str]:
        return [line for line in self.stdout.splitlines() if line.strip()]


def call_sonar(args: Sequence[str], *, cwd: Path | None = None) -> CliResult:
    """Run ``sonar <args>`` as a child process; the environment is inherited as is."""
    argv = [*sonar_argv(), *args]
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)
    return CliResult(argv, completed.returncode, completed.stdout, completed.stderr)


# --------------------------------------------------------------------------- request


@dataclass(frozen=True)
class Request:
    """The query the skill drives, as ``request.json`` states it."""

    brand: str
    competitors: tuple[str, ...]
    aliases: tuple[str, ...]
    brand_hint: str | None
    profile: str
    max_spend_usd: float | None

    def query_args(self, *, include_max_spend: bool = True) -> list[str]:
        """The CLI's positional brand and query flags; ``run.py`` passes the approved cap instead."""
        args = [self.brand, "--profile", self.profile]
        if self.competitors:
            args.extend(["--vs", *self.competitors])
        for alias in self.aliases:
            args.extend(["--alias", alias])
        if self.brand_hint is not None:
            args.extend(["--brand-hint", self.brand_hint])
        if include_max_spend and self.max_spend_usd is not None:
            args.extend(["--max-spend", repr(float(self.max_spend_usd))])
        return args

    def as_dict(self) -> dict[str, Any]:
        return {
            "brand": self.brand,
            "competitors": list(self.competitors),
            "aliases": list(self.aliases),
            "brand_hint": self.brand_hint,
            "profile": self.profile,
            "max_spend_usd": self.max_spend_usd,
        }


class RequestError(ValueError):
    """``request.json`` is not a usable request; the CLI's own validators run after this."""


def _string_list(raw: Any, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise RequestError(f"{field} must be a list of strings")
    return tuple(raw)


def parse_request(raw: Any) -> Request:
    if not isinstance(raw, dict):
        raise RequestError("request must be a JSON object")
    brand = raw.get("brand")
    if not isinstance(brand, str) or not brand.strip():
        raise RequestError("brand must be a non-empty string")
    profile = raw.get("profile", "full")
    if profile not in PROFILES:
        raise RequestError(f"profile must be one of {', '.join(PROFILES)}")
    hint = raw.get("brand_hint")
    if hint is not None and not isinstance(hint, str):
        raise RequestError("brand_hint must be a string or null")
    max_spend = raw.get("max_spend_usd")
    if max_spend is not None and (
        isinstance(max_spend, bool) or not isinstance(max_spend, int | float)
    ):
        raise RequestError("max_spend_usd must be a number or null")
    return Request(
        brand=brand,
        competitors=_string_list(raw.get("competitors"), "competitors"),
        aliases=_string_list(raw.get("aliases"), "aliases"),
        brand_hint=hint,
        profile=profile,
        max_spend_usd=None if max_spend is None else float(max_spend),
    )


def load_request(workspace: Path, source: str | None) -> Request:
    """``--in`` when given (``-`` is stdin), else ``<workspace>/request.json``."""
    path: Path | str = source if source is not None else workspace / REQUEST_JSON
    if str(path) != "-" and not Path(path).is_file():
        raise RequestError(f"request file not found: {path}")
    try:
        raw = read_json(path)
    except json.JSONDecodeError as exc:
        raise RequestError(f"request is not valid JSON: {exc}") from exc
    return parse_request(raw)


# --------------------------------------------------------------------------- the gate


def load_decisions(workspace: Path) -> list[dict[str, Any]]:
    """``decisions.json`` as a list; a missing file is no decision at all."""
    path = workspace / DECISIONS_JSON
    if not path.is_file():
        return []
    try:
        raw = read_json(path)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return [d for d in raw if isinstance(d, dict)]


@dataclass(frozen=True)
class GateVerdict:
    approved: bool
    reason: str
    approved_max_spend_usd: float | None = None
    decided_by: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "approved_max_spend_usd": self.approved_max_spend_usd,
            "decided_by": self.decided_by,
        }


def evaluate_gate(plan: dict[str, Any] | None, decisions: Sequence[dict[str, Any]]) -> GateVerdict:
    """Approved iff the newest ``spend-approval`` decision approves this exact plan.

    The decision must be ``approve_spend`` with ``new_value.approved`` true, name the
    ``plan_digest`` of the current ``plan.json`` (re-planning invalidates an earlier
    approval) and carry ``new_value.max_spend_usd`` at or above the plan's estimate.
    A ``reject_spend`` decision, a stale digest, a lower cap or no decision refuses.
    """
    if plan is None:
        return GateVerdict(False, "no plan.json in the workspace; run plan first")
    digest = plan.get("plan_digest")
    estimate = float(plan.get("estimate_usd", 0.0))
    relevant = [d for d in decisions if d.get("scope_key") == GATE_ITEM_ID]
    if not relevant:
        return GateVerdict(False, "no spend-approval decision in decisions.json")
    latest = relevant[-1]
    kind = latest.get("decision_type")
    value = latest.get("new_value")
    value = value if isinstance(value, dict) else {}
    decided_by = latest.get("decided_by")
    who = decided_by if isinstance(decided_by, str) else None
    if kind == REJECT_DECISION:
        return GateVerdict(False, "spend rejected", decided_by=who)
    if kind != APPROVE_DECISION:
        return GateVerdict(False, f"unknown decision_type {kind!r}", decided_by=who)
    if value.get("approved") is not True:
        return GateVerdict(False, "approve_spend without approved=true", decided_by=who)
    if value.get("plan_digest") != digest:
        return GateVerdict(
            False,
            f"approval names plan_digest {value.get('plan_digest')!r}, current plan is {digest!r}",
            decided_by=who,
        )
    cap = value.get("max_spend_usd")
    if isinstance(cap, bool) or not isinstance(cap, int | float):
        return GateVerdict(False, "approve_spend without a numeric max_spend_usd", decided_by=who)
    if float(cap) < estimate:
        return GateVerdict(
            False,
            f"approved max_spend_usd {float(cap):.4f} is below the estimate {estimate:.4f}",
            approved_max_spend_usd=float(cap),
            decided_by=who,
        )
    return GateVerdict(True, "approved", approved_max_spend_usd=float(cap), decided_by=who)


def load_plan(workspace: Path) -> dict[str, Any] | None:
    path = workspace / PLAN_JSON
    if not path.is_file():
        return None
    try:
        raw = read_json(path)
    except json.JSONDecodeError:
        return None
    return raw if isinstance(raw, dict) else None
