# HANDOFF.md — operator log

This is the running log for anyone operating sonar with real credit:
Caio, a worker session, or a judge reproducing the demo. Every task that
spends Monid or OpenAI credit (`$` tasks in
`docs/research/2026-09-02-task-graph-and-design.md`) is serialized through
the lead and gets one row in the spend ledger before its receipt is
committed.

## Rules of the wallet

- Monid workspace budget $10.00, per-run cap $3.50, both set by the W0.1
  wizard (`MONID_WORKSPACE_BUDGET_USD`, `MONID_RUN_CAP_USD` in
  `~/.sonar/.env`).
- Wallet reserve $1.50 must remain for judging; the ledger total stays
  ≤ $8.50 through W8.2.
- One `$` task at a time. A second live run never starts before the
  previous session's `sonar reconcile` has written `RECONCILED`.
- Cost figures in this file come from `GET /v1/runs` via the session
  receipt, never from estimates. `estimate_usd` is not a ledger number.

## Spend ledger

| Date | Task | Run ids | Monid USD | OpenAI USD | Notes |
|---|---|---|---|---|---|
| 2026-09-02 | W0.1 closed | none | 0.00 | 0.00 | Hackathon registration submitted; X handle @uiuizap; Monid workspace budget/run cap left unset by decision (sonar's own guard is the stop) |
| 2026-09-02 | W0.1 setup wizard (`scripts/setup-wizard.sh`) | none | 0.00 | 0.00 | Wizard writes `~/.sonar/.env` (mode 600) with Monid key, budget, run cap, OpenAI key, X handle. Verification calls are unbilled (`monid whoami`, `monid discover`, OpenAI `models.list`). No Monid spend has occurred yet. |

Running totals: Monid 0.00 of 10.00 spent, OpenAI 0.00, reserve 1.50 intact.

Row format: one row per session id. `Run ids` lists every Monid run id
the receipt contains, including `run_id=null` rows written as
`local_seq=<n>`, so a judge can match this table against
`results/*/receipt.json`. When a row would exceed the column, put the
session id here and the full list in the receipt.

## Jobs

Planned `$` jobs, in critical-path order. Estimates come from the task
graph budget ledger; the measured column is filled from the receipt when
the job runs.

| Job | Command | Est. Monid | Measured | Status |
|---|---|---|---|---|
| W3.7 smoke fixtures | `sonar record --profile smoke <brand>` | 0.40 | not run | waiting on W3.1 and W3.4 |
| W5.5 lite run + Avenza empty + TTS probe | `sonar run --profile lite <brand> --vs <competitor>`; `sonar run --profile lite Avenza` | 1.30 | not run | waiting on W5.1–W5.4 |
| W6.1 full demo + empty | `sonar run --profile full <brand> --vs <c1> <c2> <c3> --resamples 10000` | 2.80 | not run | waiting on W5.5 |
| W7.2 narration TTS | one ElevenLabs run through `voice/tts` | 0.10 | not run | waiting on W7.1 |
| W8.2 rehearsal | `sonar run --profile lite <never-used brand>` | 0.80 | not run | waiting on W8.1 |

Recurring operator jobs, all free:

- `sonar doctor` before any live run: keys present, Monid reachable,
  OpenAI `models.list` returns, wallet balance printed.
- `sonar spend` after any live run: prints the session totals and the
  running ledger total so this table can be updated from output, not
  memory.
- `sonar reconcile --session <id>` at least 10 minutes after the last
  run of a session finished, then `sonar verify <receipt>`; both must
  print `RECONCILED` before the row is written here.
- `make validate` before every commit that touches docs or results.

### 2026-09-02 — Wave 2 review and fix cycle

- Three separate-context reviews of Wave 2 code (`docs/research/reviews/2026-09-02-code-review-{monid,llm-text,config-providers}.md`) all returned FAIL; every numbered item was applied by a fix worker on disjoint files (commits `450a7d7`, `de53299`, `cd0da1e`, `26afa56`, `6fc7b2f`).
- Contracts went through two reviews (`…contracts-review.md`, `…contracts-review-2.md`) and two decisions (D012, D013); CONTRACTS is at schema_rev 1.1.1, PRE-REGISTRATION at v1.1.1, `docs-frozen` tag at `a852f5c`.
- An account rate limit killed five workers mid-edit; each was re-dispatched with orders to audit its own leftover diff first. Nothing was lost; nothing partial was committed.
- Suite: 570 tests green; 6 mypy errors remain in adapter files against the corrected Provider protocol, queued for the Wave 3 fix wave.

## What not to do

- Do not start a live run while another session is unreconciled.
- Do not resubmit a run that returned `TIMED_OUT` or hit the deadline;
  the abstention is the result and the cost is already billed.
- Do not reconcile immediately after the last run completes; billing
  settles late (`docs/RED-TEAM.md` §15). Wait, then reconcile once.
- Do not hand-edit anything under `results/demo/` or `results/demo-empty/`.
  Re-run W6.1 and re-freeze through a `docs/DECISIONS.md` entry instead.
- Do not pass a replay as live. Replays carry `verdict=REPLAY` and stay
  that way in every artifact.
- Do not call `apify/instagram-search-scraper`; it is entity search, not
  keyword search, and bills for the wrong thing.
- Do not submit a YouTube or Google Maps run without `maxResults` or
  `maxReviews`; the per-run cap is the only backstop and it is $3.50.
- Do not store raw author handles. Only `author_hash` leaves the adapter.
- Do not commit `.env`, `~/.sonar/.env`, or anything under `out/`.
- Do not edit `CONTRACTS.md`, `docs/PRE-REGISTRATION.md` or `config.py`
  after the `docs-frozen` gate without a new DECISIONS entry.
- Do not run `agentgraph viz` from a worker; it opens windows on the
  operator's screen.
- Do not quote a Monid cost that has not come back from `GET /v1/runs`.

## Open questions

- **OQ-HO-1** The Monid dashboard menu names for workspace budget and run
  cap were not verified before the wizard was written. Resolves when W0.1
  is run by a human; the wizard prompts for where the setting was found
  and the answer is recorded in the W0.1 ledger row notes.
- **OQ-HO-2** Whether OpenAI cost per session is read from the SDK usage
  fields or from the OpenAI dashboard. Resolves at W3.7: the first
  receipt with `totals.llm_usd` is compared against the dashboard for
  the same hour, and the method that matches is written into the rules
  above.

| 2026-09-02 | W0.1 + W0.3 | none | 0.00 | 0.00 | keys stored in ~/.sonar/.env; monid whoami OK, balance $1.00; OpenAI models list OK (gpt-5.6-luna/terra present); 7 inspects saved to docs/monid/inspect/ (all free) |
