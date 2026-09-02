"""Step ``ask``: one question to ``sonar ask`` over the session, as JSON.

    python skill/sonar/scripts/ask.py --workspace DIR --question "..." [--brand B]

Calls ``sonar ask <brand> "<question>" --session <workspace>/session``; the brand
defaults to the plan's. The CLI's stdout is parsed as JSON when it is JSON (the
``Answer`` record: ``answer``, ``citations``, ``verified_numbers``, ``status`` ok |
unverified | refused), otherwise kept as ``text``. When the CLI has no ``ask`` command
yet the script reports ``status: unavailable`` with exit ``2`` and asks nothing. Every
answer is appended to ``<workspace>/answers.jsonl``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    ANSWERS_JSONL,
    EXIT_USAGE,
    SESSION_DIR,
    call_sonar,
    emit,
    load_plan,
    utcnow_iso,
    workspace_parser,
)


def parse_answer(stdout: str) -> dict[str, Any] | None:
    """The last JSON object on stdout, when the CLI printed one."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def main(argv: list[str] | None = None) -> int:
    parser = workspace_parser("sonar ask as JSON")
    parser.add_argument("--question", required=True)
    parser.add_argument("--brand", default=None, help="default: the plan's brand")
    args = parser.parse_args(argv)
    workspace: Path = args.workspace
    brand: str | None = args.brand
    if brand is None:
        plan = load_plan(workspace)
        query = plan.get("query", {}) if plan is not None else {}
        candidate = query.get("brand") if isinstance(query, dict) else None
        brand = candidate if isinstance(candidate, str) else None
    if brand is None:
        return emit(
            {"step": "ask", "status": "unavailable", "error": "no brand: pass --brand or run plan"},
            EXIT_USAGE,
        )
    session_dir = workspace / SESSION_DIR
    result = call_sonar(["ask", brand, args.question, "--session", str(session_dir)])
    if result.exit_code == 2 and "invalid choice: 'ask'" in result.stderr:
        return emit(
            {
                "step": "ask",
                "status": "unavailable",
                "brand": brand,
                "question": args.question,
                "error": "this sonar build has no ask command",
            },
            EXIT_USAGE,
        )
    answer = parse_answer(result.stdout)
    record: dict[str, Any] = {
        "step": "ask",
        "asked_at": utcnow_iso(),
        "brand": brand,
        "question": args.question,
        "session_dir": str(session_dir),
        "status": (answer or {}).get("status", "ok" if result.exit_code == 0 else "error"),
        "answer": answer,
        "text": result.stdout.strip() if answer is None else None,
        "stderr": result.stderr.strip()[-2000:],
        "exit_code": result.exit_code,
    }
    with open(workspace / ANSWERS_JSONL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return emit(record, result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
