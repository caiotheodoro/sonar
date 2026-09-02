"""Step ``verify``: ``sonar verify`` on the session's receipt, as JSON.

    python skill/sonar/scripts/verify.py --workspace DIR [--receipt PATH]

Exit ``0`` only on ``RECONCILED``; ``1`` on ``PARTIAL`` or ``REPLAY`` (an offline replay
never verifies, by contract); ``2`` on an unreadable card. Writes ``verify.json`` and,
whatever the verdict, ``RUN_COMPLETE.json`` so a driver knows the run is over; the
``next`` field names the reconcile command when the verdict is ``PARTIAL``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    EXIT_USAGE,
    RECEIPT_JSON,
    RUN_COMPLETE_JSON,
    SESSION_DIR,
    VERIFY_JSON,
    call_sonar,
    emit,
    utcnow_iso,
    workspace_parser,
    write_json,
)


def parse_verify_output(lines: list[str]) -> tuple[str | None, str | None, str | None, list[str]]:
    """``verdict <stored> (re-derived <derived>); status <status>`` and the problem bullets."""
    stored = derived = status = None
    problems: list[str] = []
    for line in lines:
        if line.startswith("verdict "):
            head, _, tail = line.partition("; status ")
            status = tail.strip() or None
            words = head.split()
            if len(words) >= 2:
                stored = words[1]
            if "(re-derived " in head:
                derived = head.split("(re-derived ", 1)[1].rstrip(")").strip()
        elif line.startswith("- "):
            problems.append(line[2:])
    return stored, derived, status, problems


def main(argv: list[str] | None = None) -> int:
    parser = workspace_parser("sonar verify as JSON")
    parser.add_argument(
        "--receipt", type=Path, default=None, help="default <workspace>/session/receipt.json"
    )
    args = parser.parse_args(argv)
    workspace: Path = args.workspace
    session_dir = workspace / SESSION_DIR
    receipt: Path = args.receipt if args.receipt is not None else session_dir / RECEIPT_JSON
    if not receipt.is_file():
        return emit(
            {"step": "verify", "status": "missing", "error": f"no receipt at {receipt}"}, EXIT_USAGE
        )
    result = call_sonar(["verify", str(receipt)])
    stored, derived, status, problems = parse_verify_output(result.lines)
    report: dict[str, Any] = {
        "step": "verify",
        "verified_at": utcnow_iso(),
        "receipt": str(receipt),
        "verdict": stored,
        "derived_verdict": derived,
        "status": status,
        "problems": problems,
        "reconciled": result.exit_code == 0,
        "exit_code": result.exit_code,
        "lines": result.lines,
    }
    if stored == "PARTIAL" and result.exit_code != EXIT_USAGE:
        report["next"] = f"sonar reconcile --session {receipt.parent}"
    write_json(workspace / VERIFY_JSON, report)
    write_json(
        workspace / RUN_COMPLETE_JSON,
        {
            "completed_at": report["verified_at"],
            "session_dir": str(receipt.parent),
            "verdict": stored,
            "reconciled": report["reconciled"],
            "exit_code": result.exit_code,
        },
    )
    return emit(report, result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
