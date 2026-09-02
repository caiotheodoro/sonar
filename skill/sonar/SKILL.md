---
name: sonar
description: Drive the sonar brand-listening CLI end to end. Checks keys and reachability, validates the query and prints the spend estimate, stops at a human spend-approval gate, runs the brief, verifies the receipt, and answers questions over the session with cited mentions. Every dollar is approved before it is spent.
keywords:
  - brand listening
  - share of voice
  - sentiment
  - competitor
  - receipt
  - Monid
process:
  title: Sonar brief with spend approval
  phrase_hints:
    - run a sonar brief
    - listen for a brand
    - compare a brand against competitors
    - what is the receipt for this brief
  steps:
    - id: doctor
      title: Check keys, reachability and the wallet line
      assignee_role: agent
    - id: plan
      title: Validate the query and print the estimate
      assignee_role: agent
    - id: spend-approval
      title: Budget owner approves the estimate before any live call
      assignee_role: human
      gate:
        type: approval
        role: budget_owner
    - id: run
      title: Fetch, label, bootstrap, write the artifacts and the receipt
      assignee_role: agent
    - id: verify
      title: Re-derive the receipt verdict; reconcile when PARTIAL
      assignee_role: agent
    - id: ask
      title: Answer questions over the session with cited mentions
      assignee_role: agent
  artifacts:
    - slot: request
      title: Request (brand, competitors, aliases, brand_hint, profile, max_spend_usd)
      accepts: [application/json]
    - slot: plan
      title: Plan with estimate and plan_digest
      accepts: [application/json]
    - slot: decisions
      title: decisions.json carrying the spend-approval decision
      accepts: [application/json]
    - slot: receipt
      title: Session receipt (RECONCILED, PARTIAL or REPLAY)
      accepts: [application/json]
    - slot: digest
      title: Session digest, Markdown
      accepts: [text/markdown]
---

# Sonar brief with spend approval

Scripts own every call to the CLI; the agent never hand-computes an estimate, a total or
a verdict, and never reads, prints or passes an API key. The CLI loads `MONID_API_KEY`
and `OPENAI_API_KEY` itself from the environment or `~/.sonar/.env`. `$WORKSPACE` is a
directory the caller names; `request.json` goes in, every artifact comes out.

Scripts (JSON in, JSON out, one object on stdout, exit codes follow the CLI's error
matrix: 0 ok, 1 unreachable, 2 bad input, 3 refused, 4 PARTIAL):

- `scripts/doctor.py --workspace $WORKSPACE` writes `doctor.json`: key presence,
  reachability of Monid and OpenAI, the wallet line. Exit 2 means a key is missing.
- `scripts/plan.py --workspace $WORKSPACE [--in request.json | -]` runs the query
  validators and writes `plan.json` with `estimate_usd`, the plan lines and a
  `plan_digest`. Exit 2 is an invalid query (bad brand, more than three competitors,
  duplicates, two competitors under `lite`).
- `scripts/gate.py request --workspace $WORKSPACE` writes `escalation.json` and exits 3.
  `scripts/gate.py check --workspace $WORKSPACE` exits 0 only when `decisions.json`
  approves the current plan.
- `scripts/run.py --workspace $WORKSPACE [--fixtures [DIR]] [--no-voice]` refuses with
  exit 3 unless the gate check passes, then runs `sonar run --out $WORKSPACE/session`
  with `--max-spend` set to the approved cap and writes `run.json`.
- `scripts/verify.py --workspace $WORKSPACE` writes `verify.json` and
  `RUN_COMPLETE.json`. Exit 0 only on `RECONCILED`; a `REPLAY` receipt never verifies.
- `scripts/ask.py --workspace $WORKSPACE --question "..."` appends to `answers.jsonl`.

## Process

1. **doctor.** Run `doctor.py`. On exit 2 stop and tell the user which key is missing
   (`~/.sonar/.env` or the environment); do not write a key anywhere. On exit 1 report
   the unreachable service and stop.
2. **plan.** Write `request.json` from the user's ask (`brand` required; `competitors`
   up to three, one under `lite`; `profile` smoke, lite or full; `max_spend_usd`
   optional). Run `plan.py`. Show the user the plan lines and the estimate verbatim
   from `plan.json`. On exit 2 fix the request with the user and re-plan.
3. **spend-approval (human gate).** Run `gate.py request`. It writes
   `$WORKSPACE/escalation.json` and exits 3. Stop here. Say that the estimate is in
   `escalation.json` and that the run continues once `decisions.json` carries an
   `approve_spend` decision for `scope_key` `spend-approval` naming the current
   `plan_digest` with `max_spend_usd` at or above the estimate. Do not write
   `decisions.json` yourself, do not resume without it, and do not call `run.py` to
   test whether the gate opens. When resumed, run `gate.py check`; exit 3 means still
   refused (rejected, stale digest after a re-plan, or a cap below the estimate): stop
   again and say why. Re-planning invalidates an earlier approval by design.
4. **run.** Run `run.py`. Exit 3 with `submitted: false` is the gate refusing; go back
   to step 3. Exit 3 with `submitted: true` is the Monid 402 breaker: the receipt lists
   what was fetched; report it. Exit 4 is a `PARTIAL` receipt: run
   `sonar reconcile --session $WORKSPACE/session` once billing settles (the `next`
   field carries the command). Exit 0 is a complete run; read the verdict and totals
   from `run.json` and point the user at `session/digest.md` and `session/receipt.json`.
   `--fixtures` replays the recorded fixtures offline with no key and no spend; the
   gate still applies and the receipt is `REPLAY`.
5. **verify.** Run `verify.py`. Report the stored and re-derived verdicts from
   `verify.json`. `RECONCILED` is the only passing verdict; `PARTIAL` names the
   reconcile command in `next`; `REPLAY` is expected on the fixtures path and is not a
   failure of the run.
6. **ask.** For each question, run `ask.py --question`. Report the answer with its
   citations and `status` (`ok`, `unverified`, `refused`). `status: unavailable` with
   exit 2 means this build has no `ask` command; say so and stop asking.

## Escalation protocol

The only escalation is `spend-approval`. `escalation.json` has `step`, `raised_at` and
one item with `item_id` `spend-approval`, `estimate_usd`, `plan_digest`, `query`,
`lines` and a `resolution_shape`. A resolution is one entry appended to
`decisions.json` (a JSON list):

```json
{
  "decision_type": "approve_spend",
  "scope_key": "spend-approval",
  "new_value": {"approved": true, "max_spend_usd": 0.30, "plan_digest": "<plan.json plan_digest>"},
  "decided_by": "budget_owner",
  "decided_at": "2026-09-02T12:00:00+00:00",
  "source_step": "spend-approval"
}
```

`reject_spend` with the same `scope_key` refuses. The newest `spend-approval` decision
wins. A driver deletes `escalation.json` after it writes the decision and resumes the
session with `resolved: spend-approval: approve_spend`; the skill then runs
`gate.py check` and continues at step 4.

## What the skill never does

- Read, echo, or store `MONID_API_KEY`, `OPENAI_API_KEY` or `~/.sonar/.env`.
- Run `run.py`, `sonar run` or `sonar record` before `gate.py check` exits 0.
- Raise the approved cap, edit `decisions.json`, or re-plan to a cheaper profile and
  reuse an older approval.
- Quote a number that is not in `plan.json`, `run.json`, `verify.json` or an answer.
