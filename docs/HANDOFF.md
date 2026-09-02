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
| 2026-09-02 | W3.7 smoke | 01M1GPJXYTAMZNGWQNT7Y7KWG0, 01M1GPP9HXJKQQYJ0V2FFCE0QV | 0.25 | 0.00 | smoke Nubank via scripts/record_fixtures.py: reddit 40 results $0.2480, google_maps 4 results $0.0027 (estimate $0.0338); reconciled, no unmatched; wallet $1.00 → $0.75 |
| 2026-09-02 | W5.5 solo (key 2, adapters fixed) | session 20260902T210914Z-nubank-43ee7e, `out/w5.5-solo/` — 01M1HZ8RA6J5TRJP7TWM3JGPJT +10 more | 0.2415 | 0.0375 | `sonar run --profile lite Nubank --no-voice`, backgrounded, key 2. **verdict RECONCILED, `sonar verify` ok.** 74 mentions, all 74 labelled, 14 not_about_brand (19%). **Adapter fixes confirmed live** — reddit "1 item skipped, deleted or empty content" note, no spurious schema_drift; abstentions are honest (youtube_comment HTTP 400, trustpilot/g2 `empty`). Real topic ("Nubank Stock Analysis", n=3), **2 events detected** (09-01 n=9, 09-02 n=21, baseline_median 2). Sentiment counts computed (pos 19 / neg 14 / neu 27, n_confirmed 28) but **net + WoW ABSTAIN** — pre-reg rule: `n < 20` in the previous 7-day period (14-day window → 7+7 split, previous half too thin). This is OQ-HO-3. Key 2 wallet ≈ $0.29. |
| 2026-09-02 | W5.5 real (key 2) | session 20260902T194057Z-nubank-57d7a9, `out/w5.5-real/` (21 run ids in its runs.jsonl) | 0.4733 | 0.0454 | `sonar run --profile lite Nubank --vs Inter --no-voice`, backgrounded, on **key 2**. **verdict RECONCILED, `sonar verify` passes.** 133 mentions, **all 133 labelled, 0 errors** — the classifier fix holds on real data. But: (a) 56/133 `not_about_brand` — "Inter" collides with Inter Milan (football topic "Lautaro Chooses to Stay at Inter" clustered); (b) sentiment + SoV **abstained** for both brands (too few relevant after the homonym filter); (c) 3 adapters hit `schema_drift` on Apify "no-results" error-items — youtube/facebook return `{error,…}` items the adapter reads as a missing `id`/`text`; reddit skipped on one deleted comment with no `body`; Inter reddit hit the RUNNING deadline. Real digest/receipt in `out/w5.5-real/`. Key 2 wallet ≈ $0.53. |
| 2026-09-02 | W5.5 attempt 3 (killed) | session `out/w5.5-attempt3` — orphan reddit 01M1HT1AR6C3NSMXWKSGEYKY28 (billed, not in local ledger by id), youtube 01M1HT1ARNJJQ7J8WAYVNB5HE5, instagram 01M1HT1AR53RTERJ2Z61EKGXNS, tiktok 01M1HT1ARVFD0KQYJSRV4SC38D, gmaps 01M1HT1ARQXVQE3S5P9RSEEG71, facebook 01M1HT1ARS3X87HSX3R4NRVYM7, trustpilot 01M1HT1FMDDB38CR8N01RD5GCQ, g2 01M1HT1R5ARG6DW2KT9E31FAE0, news 01M1HT1V9TMZ5EK9VF5J7R931V + 01M1HT1XW5NZRMFCNKB56MQ0GG, yt-comments 01M1HT3E0JVSKKKKD8SJ85J6P6 (BLOCKED) | ~0.2408 | 0.00 | `sonar run --profile lite Nubank --no-voice` on the **old** key. Killed by a 120 s foreground timeout while polling — must background live runs. Monid ran every fetch anyway: reddit $0.134, youtube $0.0225, instagram $0.00345, tiktok $0.009, gmaps $0.01485/22, facebook $0.007, trustpilot $0.03 (0), g2 $0.02 (0), news $0, yt-comments BLOCKED $0. No receipt, no mentions saved. Old key wallet ≈ $0.05 — effectively spent, per operator instruction switch to the second key here. |
| 2026-09-02 | W5.5 attempt 2 | session 20260902T192411Z-nubank-f69c73 — 01M1HS8D4W77SMAG0BAJT21H5E, 01M1HS8D5H28HVJ3WWTW1P683F, 01M1HS8P8HW8AXWVCQCMP077Q4, 01M1HS8YQ030M5CRQ8RF125AJH, 01M1HS90D9ESQ39XTH5N95GAMS, 01M1HS8YS69JD24SF84NJ1J8PV, 01M1HS8D3AMMT0SW77T9MB09KM, 01M1HS8D41WS3KTJJDFV1EPGCC, 01M1HS9J5ZR8S5NV324MFDN9NH, 01M1HS8D3FCWAMA7RS8FQ7VJW4, 01M1HS8D6MM6EXC4HQS8WMAANW | 0.2320 | ~0.0000 | `sonar run --profile lite Nubank --no-voice` after the pipeline fix. **verdict RECONCILED**, 11 runs, 0 failed, no unmatched. 67 mentions fetched (reddit 15, tiktok 19, instagram 15, gmaps 9, youtube 5, facebook 2, news 2). trustpilot/g2 lookups found no entity (abstained, reviews skipped); yt-comments HTTP 400. **All 67 labelled `error`** — second bug: `gpt-5.6-luna` rejects `temperature=0.0` (400), so every classify batch failed, `llm_usd $0`, empty topics. Fixed `ec789de` (drop the param; verified live). Real mentions saved; not re-analysed (no offline re-label path, single brand). Wallet ~$0.52 → ~$0.29. |
| 2026-09-02 | W5.5 attempt 1 (crashed) | session 20260902T190653Z-nubank-cb9cae — reddit 01M1HR8PMMP6SESZMP3SYG24WC, youtube 01M1HR8PN33AQCS8DNS2AW8H2F, yt-comments 01M1HRAFHKNH5FJC2SCZNN2TTP, tiktok 01M1HR8PMSP89RE2QZ1G847C4V, instagram 01M1HR8PN48VHQ87S2DZRK6QJS, gmaps 01M1HR8PMZZVV4H0WWQMY9AN4W, facebook 01M1HR8PN2GR27M85MNPCA0DEK, trustpilot 01M1HR97KK9CBJYSCEJNZYD616, g2 01M1HR98976QYRZ6ZFSW2MTFJF, news 01M1HR9GD0Y816J620RJYWVNTM | 0.2266 | 0.00 | `sonar run --profile lite Nubank --no-voice`, est $0.4293; session dir left uncommitted under out/. All 10 source runs COMPLETED; pipeline then crashed parsing the news result (pre-existing bug, fixed `fc5b2c9`). No receipt written. Costs from `GET /v1/runs` (authoritative): reddit $0.134/20, youtube $0.0225/5, yt-comments $0 (HTTP 400, no charge), tiktok $0.009/20, instagram $0.00345, gmaps $0.000675/**1 review**, facebook $0.007/2, trustpilot $0.03 (0 companies), g2 $0.02 (0 products), news $0. No unmatched, nothing pending — reconciliation obligation met by direct listing. Data too thin to salvage (1 maps review, 0 trustpilot/g2/yt-comments). Wallet $0.75 → ~$0.52. |
| 2026-09-02 | W0.1 closed | none | 0.00 | 0.00 | Hackathon registration submitted; X handle @uiuizap; Monid workspace budget/run cap left unset by decision (sonar's own guard is the stop) |
| 2026-09-02 | W0.1 + W0.3 | none | 0.00 | 0.00 | keys stored in ~/.sonar/.env; monid whoami OK, balance $1.00; OpenAI models list OK (gpt-5.6-luna/terra present); 7 inspects saved to docs/monid/inspect/ (all free) |
| 2026-09-02 | W0.1 setup wizard (`scripts/setup-wizard.sh`) | none | 0.00 | 0.00 | Wizard writes `~/.sonar/.env` (mode 600) with Monid key, budget, run cap, OpenAI key, X handle. Verification calls are unbilled (`monid whoami`, `monid discover`, OpenAI `models.list`). No Monid spend has occurred yet. |

Running totals — **key 1** (`monid_live_VI12…`): $0.9494 of $1, exhausted. **Key 2** (`monid_live_DJVq…`, in `~/.sonar/.env`, old value at `~/.sonar/.env.bak-*`): $0.4733 (Inter run) + $0.2415 (solo run, adapters fixed) = **$0.7148**, ≈ $0.29 left. Two 2-brand attempts were REFUSED pre-flight (`--max-spend` vs the $0.8587 estimate) — key 2 can't cover a 2-brand lite. OpenAI ≈ $0.083 total. **A real top-up is required for the 2-brand W5.5 and for W6.1 (full, 4 brands, $2.8).**

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
| W3.7 smoke fixtures | `uv run python scripts/record_fixtures.py --brand Nubank --profile smoke` | 0.40 | done 2026-09-02, billed 0.25 | fixtures committed; see ledger |
| W5.5 lite run + Avenza empty + TTS probe | `sonar run --profile lite Nubank --vs Inter`; `sonar run --profile lite Avenza` | 1.30 | 2 attempts (Nubank solo, no-voice) billed $0.4586 total, each surfaced a bug (`fc5b2c9` pipeline, `ec789de` classifier); no usable digest yet. Real caps seen: gmaps 1–9 reviews, trustpilot/g2 0 hits, yt-comments HTTP 400 | blocked: wallet ≈ $0.29, need top-up for the full Nubank+Inter+Avenza run |
| W6.1 full demo + empty | `sonar run --profile full Nubank --vs Inter C6 Itaú --resamples 10000` | 2.80 | `sonar plan` 2026-09-02: **$2.8168** over 4 brands | waiting on W5.5 + top-up |
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

### 2026-09-02 — Waves 3 and 4

- Wave 3 adapters: two reviews (`…code-review-adapters-a.md`, `…-b.md`) FAIL → 13 fixes → verification review PASS (`…code-review-adapters-verify.md`). Wave 3 gate passed.
- W3.7 live smoke on Nubank recorded (see ledger). Findings: Google Maps accepts a search URL; reviews and thread comments rarely contain the brand string, hence D014 (match_kind: text, inherited, entity) applied across contracts, models, adapters and config with `tests/test_fixtures_live.py` on the real payloads.
- Wave 4 layers (sentiment, topics, stats, report, voice) committed; three separate-context reviews in progress. Claims gate (`make check-claims`) live with demo checks deferred to W6.1.
- Contracts at schema_rev 1.1.2, PRE-REGISTRATION v1.1.2, DECISIONS through D015, `docs-frozen` at `144ccd9`.
- Wallet: $0.75 of the $1 free credit remains; a top-up is required before W5.5 (lite run ≈ $0.75 plus TTS probe) and W6.1 (full demo ≈ $2.8).

## Theoretical (non-billed) spend — direct ElevenLabs voice path (D016)

When `SONAR_TTS_DIRECT=1` and `ELEVENLABS_API_KEY` are set, the voice run
goes straight to ElevenLabs (operator's ~8 000 prepaid credits) and costs
the Monid wallet nothing. The ledger row is `cost_source="local"`,
`cost_usd=0.0`; its `estimate_usd` holds the Monid-equivalent price
(`chars / 1000 × $0.05`, `eleven_flash_v2_5`). These figures are
estimates, never ledger numbers, and are not added to the running totals.

| Task | Chars | Monid-equivalent (theoretical) | Billed to Monid |
|---|---|---|---|
| W5.5 TTS unit probe | 20 | $0.00100 | $0.00 |
| W7.2 narration | ≤ 900 (cap) | ≤ $0.04500 (≈ $0.041 at ~820) | $0.00 |
| Project total, voice | | ≤ $0.046 | $0.00 |

`/voices` is $0.00 on Monid regardless; a direct run skips it and uses the
configured `voice_id` (default Rachel `21m00Tcm4TlvDq8ikWAM`).

When a direct run's receipt row is committed, its HANDOFF ledger row notes
`voice: direct (D016), Monid-equiv $X.XXXXX, not billed`.

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
- Do not quote a direct-TTS run's `estimate_usd` as a billed Monid cost
  (D016). It is the Monid-equivalent price, not a `/v1/runs` number.
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

### 2026-09-02 — Wave 5 close-out and the credit wall

- Hackathon gives **no participant credits** (`hacks.monid.ai`: "charges per
  call. One key, no plan"). Credits are prizes only. The $1 Monid free
  credit is standard signup dust; $0.25 spent at W3.7, $0.75 left.
- Demo brand fixed: **Nubank vs Inter, C6, Itaú** (Brazilian fintech,
  PT+EN). W5.5 uses Nubank + Inter; W6.1 adds C6 + Itaú.
- `sonar doctor` green: Monid + OpenAI reachable, `GET /v1/runs` returns.
- Offline full pipeline re-run on the W3.7 smoke fixtures after D016: all
  artifacts written, `brief.mp3` included, verdict REPLAY, no regression.
- Direct-TTS live probe (D016): ElevenLabs key is a **free** plan, 402
  `paid_plan_required` on a library voice. Adapter handled it cleanly.
  Voicing the brief needs Monid credit or an ElevenLabs upgrade.
- **Blocked on top-up.** ~$4.90 of Monid spend left (W5.5 $1.29 + W6.1
  $2.82 + W8.2 $0.80; W7.2 ≈ $0), plus the $1.50 judging reserve → top up
  ~$8 at app.monid.ai and W5.5 runs first try.

### 2026-09-02 — W5.5 real run: pipeline works, demo config and 3 adapters do not

The Nubank vs Inter lite run reached RECONCILED and `sonar verify` passes;
133/133 mentions labelled with no errors. Blockers found for W6.1:

- **"Inter" is unusable as a competitor.** Inter Milan (football) drowns
  Banco Inter — 42 % of mentions `not_about_brand`, the only Inter topic
  was about a footballer's contract. Need a clean competitor (PicPay,
  Itaú, C6) or `--brand-hint "Banco Inter"` + aliases, then re-measure.
- ~~3 adapters mis-handle Apify "no-results" items.~~ **Fixed.**
  `AdapterEmpty` + `is_error_item()` in `base.py`; youtube / youtube_comments
  / facebook / reddit skip `{error}` rows and raise `AdapterEmpty`
  (→ `empty` abstention) when every row is an error. reddit skips a
  bodyless comment / titleless-and-bodyless post and counts it
  (`skipped_no_text`). Structural drift still raises. 1371 tests green.
- **reddit is slow** — Inter's reddit run hit the per-run deadline while
  RUNNING. Consider a longer reddit deadline or a smaller cap.
- Sentiment + SoV abstained: after the homonym filter, too few relevant
  mentions per brand to clear the pre-registered thresholds.

### 2026-09-02 — W5.5 solo run: pipeline validated end-to-end, OQ-HO-3 now actionable

The adapter-fixed solo Nubank run is clean: RECONCILED, `sonar verify` ok,
74/74 labelled, honest abstentions, real topics + events. Two decisions
the operator must make before W6.1:

- **OQ-HO-3 / window length.** `net` and WoW abstain because the 14-day
  fetch window splits 7 + 7 and the previous 7 days hold `< 20` relevant
  mentions (pre-reg `## Abstention thresholds`). To get a non-abstaining
  `net`, fetch a **28-day** window (2× the Monid cost) so each period has
  ≥ 20, **or** accept that a first brief reports current-period pos/neg/neu
  counts + topics + events and abstains on net/WoW, and document that in
  COVERAGE. Needs a DECISIONS entry either way.
- **Top-up.** Key 2 is down to ~$0.29. A 2-brand lite is $0.86 est; W6.1
  full is $2.8. No more real runs until the wallet is funded.

### 2026-09-02 — W5.5 attempt 1: real run, real bug

- `sonar run --profile lite Nubank --no-voice` fired live. All 10 source
  runs COMPLETED ($0.2266 billed, from `GET /v1/runs`), then the pipeline
  crashed: `_run_source` read `report.cluster_key_fallbacks` on the news
  adapter's report, which only reddit's carries. Pre-existing W5.1 bug;
  smoke (reddit+maps) never hit it. Fixed in `fc5b2c9` with
  `_report_notes()` + regression tests; suite 1365 green.
- No receipt was written, so `sonar reconcile` (needs one) can't run.
  Billing is settled anyway: every run terminal, no unmatched, verified
  against the listing directly. Session dir kept under `out/`.
- Live data was thin pre-crash: 1 Google Maps review, 0 Trustpilot, 0 G2,
  youtube-comments HTTP 400. Not worth salvaging — a funded rerun starts
  clean.
- Wallet ≈ $0.52. **OQ-HO-3 still open** (needs a real lite run with two
  weeks of populated data).

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
- **OQ-HO-3** The event rule fired on the first offline replay with
  `baseline_median = 0` and `baseline_mad = 0`: a window whose earlier days
  carry no fetched mentions makes every day with five mentions an event.
  Resolves at W5.5 on the first live lite run with two weeks of data: the
  lead decides whether a minimum count of non-empty baseline days is
  needed (a DECISIONS amendment to the frozen rule) or the behaviour is
  honest for a first brief and is documented in COVERAGE.
