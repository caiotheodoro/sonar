"""Step ``plan``: validate the request and print the estimate, as JSON.

    python skill/sonar/scripts/plan.py --workspace DIR [--in request.json | -]

Reads the request (``brand``, ``competitors``, ``aliases``, ``brand_hint``, ``profile``,
``max_spend_usd``), runs ``sonar plan`` and writes ``<workspace>/plan.json`` carrying
the validated query, the estimate in USD, the plan lines and a ``plan_digest`` that the
spend-approval decision has to name. Exit ``2`` on an invalid request (the CLI's own
``Query`` validators, or a malformed ``request.json``); ``0`` otherwise, with
``exceeds_max_spend`` set when ``sonar run`` would refuse at the request's cap.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    EXIT_USAGE,
    PLAN_JSON,
    RequestError,
    call_sonar,
    digest_of,
    emit,
    load_request,
    utcnow_iso,
    workspace_parser,
    write_json,
)

ESTIMATE_LINE = re.compile(r"^estimate total \$(?P<usd>[0-9]+(?:\.[0-9]+)?) over (?P<n>\d+) brand")


def parse_plan_output(lines: list[str]) -> tuple[dict[str, Any] | None, float | None, int | None]:
    """The query JSON (first line), the estimate and the brand count from ``sonar plan``."""
    query: dict[str, Any] | None = None
    if lines and lines[0].startswith("{"):
        try:
            parsed = json.loads(lines[0])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            query = parsed
    estimate: float | None = None
    brands: int | None = None
    for line in lines:
        match = ESTIMATE_LINE.match(line)
        if match:
            estimate = float(match.group("usd"))
            brands = int(match.group("n"))
    return query, estimate, brands


def main(argv: list[str] | None = None) -> int:
    parser = workspace_parser("sonar plan as JSON")
    parser.add_argument(
        "--in", dest="source", default=None, help="request JSON file, or - for stdin"
    )
    args = parser.parse_args(argv)
    workspace: Path = args.workspace
    try:
        request = load_request(workspace, args.source)
    except RequestError as exc:
        return emit({"step": "plan", "ok": False, "error": str(exc)}, EXIT_USAGE)
    result = call_sonar(["plan", *request.query_args()])
    lines = result.lines
    if result.exit_code != 0:
        return emit(
            {
                "step": "plan",
                "ok": False,
                "error": "\n".join(lines) or result.stderr.strip(),
                "request": request.as_dict(),
            },
            result.exit_code,
        )
    query, estimate, brands = parse_plan_output(lines)
    if query is None or estimate is None:
        return emit(
            {
                "step": "plan",
                "ok": False,
                "error": "could not parse the plan output",
                "lines": lines,
            },
            EXIT_USAGE,
        )
    exceeds = any(line.startswith("WARNING: estimate") for line in lines)
    plan_lines = [line for line in lines[1:] if not line.startswith("WARNING:")]
    plan: dict[str, Any] = {
        "step": "plan",
        "ok": True,
        "planned_at": utcnow_iso(),
        "request": request.as_dict(),
        "query": query,
        "estimate_usd": estimate,
        "brands": brands,
        "max_spend_usd": request.max_spend_usd,
        "exceeds_max_spend": exceeds,
        "lines": plan_lines,
        "plan_digest": digest_of({"query": query, "estimate_usd": estimate}),
    }
    write_json(workspace / PLAN_JSON, plan)
    return emit(plan, 0)


if __name__ == "__main__":
    raise SystemExit(main())
