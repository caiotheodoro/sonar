# AGENTS.md

Short path through this repository for an agent. The README is written for a
human judge; this file says what to read, in what order, and what to run.

## What sonar is

A local Python CLI plus a Claude Code skill. One run fetches mentions of a
brand and up to three competitors through Monid, labels sentiment with
OpenAI, computes share of voice and week-over-week change with cluster
bootstrap intervals, and writes a receipt: every Monid run id with its billed
cost, compared against Brand24 Team at $349 per month.

The receipt is the deliverable. Everything else exists to make it true.

## Read in this order

1. `README.md`: the kill, the scope, the Not claimed list, quickstart.
2. `CONTRACTS.md`: every record sonar emits. Field names here are the only
   field names; adapters, stats, and report code all conform to it.
3. `docs/PRE-REGISTRATION.md`: thresholds, verdict rule, hypotheses H1 to
   H5. Frozen text; changes after the freeze are new `docs/DECISIONS.md`
   entries, never edits.
4. `docs/DECISIONS.md`: why each settled choice was made and what reverses
   it. Append, never edit.
5. `docs/RED-TEAM.md`: the attacks on sonar's claims. Check any new claim
   against this list before publishing it.
6. `docs/research/2026-09-02-task-graph-and-design.md`: the task graph and
   the design appendix. Wave, ownership, and done-check for every task.

## Rules that bind edits

- **Ownership is by path.** A task edits only the paths it owns. Shared
  files (`CONTRACTS.md`, `src/sonar/config.py`, `src/sonar/models.py`) are
  frozen after the wave that owns them; later changes go through a
  `docs/DECISIONS.md` entry.
- **Unknowns are open questions.** Each one is named and carries the trigger
  that resolves it. `make check-placeholders` fails otherwise.
- **Numbers come from artifacts.** Any number in prose must exist in
  `results/demo/` or a receipt. `make check-claims` enforces this for the
  README, the narration, and `report/incumbent.py`.
- **The price lives in one place.** `src/sonar/report/incumbent.py` holds
  `$349`; README and `results/demo/receipt.json` must agree with it.
- **Cost is real or absent.** `cost_usd` is read from `GET /v1/runs` only.
  A run not yet reconciled carries `cost_source="unreconciled"` and
  contributes zero to totals; the receipt verdict becomes `PARTIAL`.
- **Tests run offline.** Adapters test against recorded fixtures under
  `tests/fixtures/`; the OpenAI seam has a fake. No test touches the
  network.
- **Live runs spend money.** Only the lead session runs `sonar run` against
  Monid, and every live run is logged in `docs/HANDOFF.md`. Cap $10 Monid
  total, $1.5 reserved for judging.
- **Commits are plain.** No attribution footers. Commit only the paths you
  own.

## Commands

```bash
make validate          # mypy, pytest, privacy gate, placeholders, published-claims gate
make video             # lint, gates, render; copies the cut into results/video/
uv run sonar doctor    # keys, endpoints, wallet
uv run sonar plan --profile lite <brand> --vs <competitor>   # estimate, no spend
uv run sonar render --from results/demo                       # replay, no key
uv run sonar verify results/demo/receipt.json                 # exits 0 only on RECONCILED
```

## Not in scope

X coverage (Monid has no endpoint), influencer scoring, email alerts. Do
not add them; the README's Not claimed section is a published commitment.
