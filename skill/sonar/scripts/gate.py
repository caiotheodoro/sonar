"""Step ``spend-approval``: the human gate between the plan and any live call.

    python skill/sonar/scripts/gate.py request --workspace DIR
    python skill/sonar/scripts/gate.py check   --workspace DIR

``request`` writes ``<workspace>/escalation.json`` from ``plan.json`` (one item,
``item_id`` ``spend-approval``, carrying the estimate, the query and the
``plan_digest``) and exits ``3``: the agent stops here and waits. A human, or the
driver acting for one, appends to ``<workspace>/decisions.json``::

    {"decision_type": "approve_spend", "scope_key": "spend-approval",
     "new_value": {"approved": true, "max_spend_usd": 0.30, "plan_digest": "<from plan.json>"},
     "decided_by": "<who>", "decided_at": "<iso8601>", "source_step": "spend-approval"}

``check`` reads the decisions and exits ``0`` only when the newest ``spend-approval``
decision approves this exact plan with a cap at or above the estimate; ``3`` otherwise
(rejected, stale digest, cap below the estimate, or no decision). ``run.py`` performs
the same check before it submits anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    ESCALATION_JSON,
    EXIT_REFUSED,
    GATE_ITEM_ID,
    GATE_STEP,
    emit,
    evaluate_gate,
    load_decisions,
    load_plan,
    utcnow_iso,
    write_json,
)


def escalation_for(plan: dict[str, Any]) -> dict[str, Any]:
    estimate = float(plan.get("estimate_usd", 0.0))
    query = plan.get("query", {})
    return {
        "step": GATE_STEP,
        "raised_at": utcnow_iso(),
        "items": [
            {
                "item_id": GATE_ITEM_ID,
                "kind": "spend_approval",
                "estimate_usd": estimate,
                "plan_digest": plan.get("plan_digest"),
                "query": query,
                "requested_max_spend_usd": plan.get("max_spend_usd"),
                "lines": plan.get("lines", []),
                "question": (
                    f"Approve spending up to ${estimate:.4f} on Monid and OpenAI for this brief? "
                    "Answer by appending an approve_spend or reject_spend decision to decisions.json."
                ),
                "resolution_shape": {
                    "decision_type": "approve_spend | reject_spend",
                    "scope_key": GATE_ITEM_ID,
                    "new_value": {
                        "approved": True,
                        "max_spend_usd": estimate,
                        "plan_digest": plan.get("plan_digest"),
                    },
                    "decided_by": "<who>",
                    "decided_at": "<iso8601>",
                    "source_step": GATE_STEP,
                },
            }
        ],
    }


def cmd_request(workspace: Path) -> int:
    plan = load_plan(workspace)
    if plan is None:
        return emit(
            {"step": GATE_STEP, "status": "no_plan", "error": "run plan.py first"}, EXIT_REFUSED
        )
    escalation = escalation_for(plan)
    write_json(workspace / ESCALATION_JSON, escalation)
    return emit(
        {
            "step": GATE_STEP,
            "status": "awaiting_approval",
            "escalation": str(workspace / ESCALATION_JSON),
            "estimate_usd": escalation["items"][0]["estimate_usd"],
            "plan_digest": plan.get("plan_digest"),
        },
        EXIT_REFUSED,
    )


def cmd_check(workspace: Path) -> int:
    plan = load_plan(workspace)
    verdict = evaluate_gate(plan, load_decisions(workspace))
    payload: dict[str, Any] = {
        "step": GATE_STEP,
        "status": "approved" if verdict.approved else "refused",
        **verdict.as_dict(),
        "plan_digest": None if plan is None else plan.get("plan_digest"),
        "estimate_usd": None if plan is None else plan.get("estimate_usd"),
    }
    return emit(payload, 0 if verdict.approved else EXIT_REFUSED)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the spend-approval human gate")
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("request", "check"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", type=Path, required=True, metavar="DIR")
    args = parser.parse_args(argv)
    workspace: Path = args.workspace
    if args.action == "request":
        return cmd_request(workspace)
    return cmd_check(workspace)


if __name__ == "__main__":
    raise SystemExit(main())
