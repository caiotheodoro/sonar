"""Step ``run``: ``sonar run`` on the approved plan, as JSON.

    python skill/sonar/scripts/run.py --workspace DIR [--fixtures [DIR]] [--no-voice]
                                      [--resamples N] [--run-deadline S]

Refuses with exit ``3`` and touches nothing unless ``decisions.json`` approves the
current ``plan.json`` (the same check as ``gate.py check``), on the live path and on
the offline ``--fixtures`` replay alike. The session lands in ``<workspace>/session/``
(``sonar run --out``), ``--max-spend`` is the approved cap, and ``run.json`` records the
CLI exit code, the receipt verdict and the totals. Exit codes are the CLI's: ``0``,
``3`` halted, ``4`` PARTIAL (then ``sonar reconcile --session <workspace>/session``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    EXIT_REFUSED,
    EXIT_USAGE,
    RECEIPT_JSON,
    RUN_JSON,
    SESSION_DIR,
    RequestError,
    call_sonar,
    emit,
    evaluate_gate,
    load_decisions,
    load_plan,
    load_request,
    utcnow_iso,
    workspace_parser,
    write_json,
)


def receipt_summary(session_dir: Path) -> dict[str, Any] | None:
    path = session_dir / RECEIPT_JSON
    if not path.is_file():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, dict):
        return None
    totals = receipt.get("totals", {})
    mentions = receipt.get("mentions", {})
    return {
        "session_id": receipt.get("session_id"),
        "verdict": receipt.get("verdict"),
        "replay": receipt.get("replay"),
        "totals": totals if isinstance(totals, dict) else {},
        "mentions": mentions if isinstance(mentions, dict) else {},
        "abstentions": len(receipt.get("abstentions", []) or []),
    }


def main(argv: list[str] | None = None) -> int:
    parser = workspace_parser("sonar run behind the spend-approval gate")
    parser.add_argument(
        "--in", dest="source", default=None, help="request JSON file, or - for stdin"
    )
    parser.add_argument(
        "--fixtures",
        nargs="?",
        const="",
        default=None,
        metavar="DIR",
        help="offline replay of the recorded fixtures (default tests/fixtures)",
    )
    parser.add_argument("--no-voice", action="store_true")
    parser.add_argument("--resamples", type=int, default=None)
    parser.add_argument("--run-deadline", type=float, default=None)
    parser.add_argument("--session", default=None, help="session id instead of a fresh one")
    args = parser.parse_args(argv)
    workspace: Path = args.workspace

    plan = load_plan(workspace)
    verdict = evaluate_gate(plan, load_decisions(workspace))
    if not verdict.approved:
        return emit(
            {
                "step": "run",
                "status": "refused",
                "reason": verdict.reason,
                "plan_digest": None if plan is None else plan.get("plan_digest"),
                "submitted": False,
            },
            EXIT_REFUSED,
        )
    try:
        request = load_request(workspace, args.source)
    except RequestError as exc:
        return emit({"step": "run", "status": "refused", "reason": str(exc)}, EXIT_USAGE)
    assert plan is not None  # evaluate_gate approves only with a plan
    cap = verdict.approved_max_spend_usd
    assert cap is not None

    session_dir = workspace / SESSION_DIR
    cli_args = [
        "run",
        *request.query_args(include_max_spend=False),
        "--max-spend",
        repr(cap),
        "--out",
        str(session_dir),
    ]
    if args.fixtures is not None:
        cli_args.append("--fixtures")
        if args.fixtures:
            cli_args.append(args.fixtures)
    if args.no_voice:
        cli_args.append("--no-voice")
    if args.resamples is not None:
        cli_args.extend(["--resamples", str(args.resamples)])
    if args.run_deadline is not None:
        cli_args.extend(["--run-deadline", str(args.run_deadline)])
    if args.session is not None:
        cli_args.extend(["--session", args.session])

    result = call_sonar(cli_args)
    summary = receipt_summary(session_dir)
    report: dict[str, Any] = {
        "step": "run",
        "status": "ok" if result.exit_code == 0 else "problem",
        "ran_at": utcnow_iso(),
        "submitted": True,
        "offline": args.fixtures is not None,
        "approved_max_spend_usd": cap,
        "plan_digest": plan.get("plan_digest"),
        "session_dir": str(session_dir),
        "receipt": summary,
        "exit_code": result.exit_code,
        "lines": result.lines,
        "stderr": result.stderr.strip()[-2000:],
    }
    if result.exit_code == 4:
        report["next"] = f"sonar reconcile --session {session_dir}"
    write_json(workspace / RUN_JSON, report)
    return emit(report, result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
