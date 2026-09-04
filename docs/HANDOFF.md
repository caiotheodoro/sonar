# HANDOFF.md — operator log

This is the running log for anyone operating sonar with real credit:
Caio, a worker session, or a judge reproducing the demo. Every task that
spends Monid or OpenAI credit (`$` tasks in
`docs/research/2026-09-02-task-graph-and-design.md`) is serialized through
the lead and gets one row in the spend ledger before its receipt is
committed.

## Rules of the wallet

- **Three Monid keys exist.** Only ONE carries funds at a time. As of
  2026-09-04: key 1 (`…VI12…`) ≈ small; key 2 (`…DJVq…`) ≈ $0; key 3
  (`…lAzr…`, in `~/.sonar/.env` now) ≈ $18. Monid `BLOCKED` with an empty
  `providerResponse` = wallet-block; check the raw `/v1/run` `reason` field.
- Per-run cap `MONID_RUN_CAP_USD=3.5`. `MONID_WORKSPACE_BUDGET_USD` in
  `~/.sonar/.env` is a stale display hint, not enforced.
- Reserve $1.50 stays for judging.
- **`BLOCKED` today was a $3/day workspace budget cap** (control
  `01M1GB8M12ZEDM99NS357K29NQ`, resets 00:00 UTC), NOT Apify flakiness and
  NOT the wallet. All 3 keys share it. Raise it at app.monid.ai/rules.
- One `$` task at a time. A second live run never starts before the
  previous session's `sonar reconcile` has written `RECONCILED`.
- Cost figures in this file come from `GET /v1/runs` via the session
  receipt, never from estimates. `estimate_usd` is not a ledger number.

## Spend ledger

| Date | Task | Run ids | Monid USD | OpenAI USD | Notes |
|---|---|---|---|---|---|
| 2026-09-02 | W3.7 smoke | 01M1GPJXYTAMZNGWQNT7Y7KWG0, 01M1GPP9HXJKQQYJ0V2FFCE0QV | 0.25 | 0.00 | smoke Nubank via scripts/record_fixtures.py: reddit 40 results $0.2480, google_maps 4 results $0.0027 (estimate $0.0338); reconciled, no unmatched; wallet $1.00 → $0.75 |
| 2026-09-04 | W7.2 narration TTS | 01M1PATWZXC7CCCN4ZAT22M685 (`video/public/narration.runs.jsonl`) | 0.04475 | 0.00 | Direct ElevenLabs (D016) was tried first and rejected: free-plan accounts get 402 `paid_plan_required` on library voices via the API regardless of credit balance — an ElevenLabs plan gate, not a Monid issue. Routed through Monid instead. 895 chars, voice `21m00Tcm4TlvDq8ikWAM` (Rachel), `eleven_flash_v2_5`. Reconciled, `cost_source /v1/runs`. `video/public/narration.mp3` (1.2 MB, 76.7 s — Rachel runs slower than the 130 wpm assumed; retimed the storyboard to 82.2 s, still under the 90 s cap). |
| 2026-09-04 | W7.3 `run_trace` cast — **duplicate-run mishap** | session `20260904T135320Z-nubank-187772` (archived under video/public/captures/_stale, then deleted) | ~0.58 (partial estimate, 66-row ledger with 22 dup-local_seq collisions) | ~0.07 | Operator error, not the user's: declared the first background recording dead from a `ps aux` grep that doesn't match `uv run`'s actual process name, and launched a second concurrent attempt against the same `--out` dir before the first had finished. Both processes fetched the same 22 Monid tasks independently (no cross-process ledger lock), and the second process's `AlreadySubmitted`-starved run overwrote `run_trace.cast` with a degenerate zero-mention/zero-cost recording that did not match the (good) `receipt.json` the first process wrote. Real Monid spend happened for both; not recoverable. Session archived, then removed once logged here rather than kept in the repo. |
| 2026-09-04 | **W7.3 `run_trace` cast (kept)** | session `20260904T140346Z-nubank-31a81e` → `video/public/captures/run_trace/` (22 run ids in its runs.jsonl) | 0.6088 | 0.0705 | `sonar run --trace --profile lite --no-voice Nubank --vs Itaú`, single attempt after archiving the mishap above and confirming no other process running. **verdict RECONCILED**, 155 fetched / 145 deduped / 145 labelled, 22 runs / 18 billed / 4 zero-result / 0 failed. `video/public/casts/run_trace.cast` (99 events, 236 s). Not a numeric source for the video — `RESULTS` still binds to `results/demo/`; this cast is terminal flavor only. |
| 2026-09-04 | W7.3 `ask` cast | none (OpenAI only) | 0.00 | 0.0027 | `sonar ask Nubank "What do people complain about most?" --session results/demo` — reads the frozen demo session, writes `results/demo/answers.jsonl` (kept, CONTRACTS §Answer) and results/demo/embeddings.npy (retrieval cache, gitignored, not evidence). 6 citations, real mention URLs. `video/public/casts/ask.cast` (5 events, 9.4 s). |
| 2026-09-04 | W7.3 `empty_run` cast | session `20260904T140844Z-zephyrium-bank-2e23b9` → `video/public/captures/empty_run/` (9 run ids) | 0.2219 | 0.0003 | `sonar run --trace --profile lite --no-voice "Zephyrium Bank"` (brand read from `results/demo-empty/receipt.json`). **verdict RECONCILED**, 2 fetched (both `not_about_brand`, excluded), 9 runs / 8 billed / 3 zero-result / 0 failed. `video/public/casts/empty_run.cast` (37 events, 271 s). Numeric source for the beat is still `results/demo-empty/` (`RESULTS_EMPTY`), not this cast's own receipt. |
| 2026-09-04 | W8.2 rehearsal (`results/rehearsal/`) | session `20260904T174114Z-banco-pan-dc43db`: 01M1PR5AEDTR3ZR0M5966YPRCD, 01M1PR5ACC0AFBTN93YFR6XXYN, 01M1PR5AE8QT6BTTGW0VXAV7ND, 01M1PR5ADNN013NH2W51N02TK7, 01M1PR5ACXYRA0HVKDBZC49942, 01M1PR5AC5JFZG053NW91YNYKX, 01M1PR5V3ZQTJC2MY922SXC06K, 01M1PR5V6EWMAH091H47Q2NVX5, 01M1PR63C7C9TT6B1VGJHKJX5P, 01M1PR69RFTQ7WJJAYQYHTNX4D, 01M1PR6S8RKGFV1D3H3B3JGY62, 01M1PR9QE3CY5Y3F2NH64TPTDA | 0.3153 | 0.0199 | `sonar run --trace --profile lite "Banco Pan" --out results/rehearsal --max-spend 1.50`, key 3, one attempt, as a judge would (never-used brand, voice on). Verdict `RECONCILED`, `sonar verify` exit 0; 12 runs, 10 billed, 2 zero-result, 0 failed; 22 fetched / 21 deduped / 21 labelled (youtube 5, youtube_comment 3, tiktok 4, instagram 5, google_maps 3, news 1; reddit and the rest empty); share of voice and sentiment **abstain** (`below_minimum`: 6 relevant in the current week and 4 in the previous, both under the 20-per-week floor; 19 relevant across the 14-day window); 3 topics, largest 5 of 19 relevant (26 %, `share` 0.263); ElevenLabs voice $0.0276 inside the Monid figure; total $0.3352. Committed unedited. Cumulative Monid ≈ **$9.4**: the task graph's "ledger ≤ $8.5" done-check was already exceeded before this run (≈ $9.1 after the W7.3 mishap) and is reported here, not amended (D022). |
| 2026-09-04 | W7.9 pacing | none | 0.00 | 0.00 | The cut was airless: speech filled 78.6 % of the runtime, all ten gaps were ~1 s, `KILLED` had 0.52 s to itself and the ratio line landed after its card had cut away. Two lines the pictures already say were dropped (the source list, now the endpoint fan; the topics/summary line, now the cards), Eva re-generated in the web UI (906 chars, free plan, $0), and `video/capture/space-narration.mjs` added: it cuts the take at its even breaks and lays the lines back down against `spacing.gapsMs`, so re-timing costs one command and no new generation. Speech now 69.3 %, holds 1.0–4.0 s covering the kill, the ledger and typed call, the topic cards and the outro; the ratio card was moved to meet its line. Music 0.30→0.38 with deeper ducking (0.55→0.45) so the holds swell. |
| 2026-09-04 | W7.8 drawn acts | none | 0.00 | 0.00 | Review pass: the Brand24 and Monid acts no longer show screenshots. Both are drawn from data — the source count, the mention field, its split into sentiment lanes, the share-of-voice columns and the seat price for the incumbent; the one-key fan, the endpoints the brief called, their real billed costs and the typed `POST /v1/run` for Monid (every row from `results/demo/receipt.json` `runs[]`). Shapes carry across the cuts through `video/src/motion/geometry.ts`, and `KILLED` wipes out of the price column. The captures stay tracked as evidence for the quoted third-party figures. Cut length unchanged (74.4 s). |
| 2026-09-04 | W7.7 sound design + micro-motion | none | 0.00 | 0.00 | Ten effects synthesised by `video/capture/sfx.py` (numpy, seeded; no recordings, no licences) into `video/public/sfx/`; attached per visual event by the drawing components, plus a cut tick and act whoosh from the timeline. Act A reopened as a six-crop photo burst with shutters; the cast shot punches in. Review pass: the Monid act showed the tools catalogue twice (generic then social-filtered), so the generic shot was dropped and the social one cropped to the platform cards; the pricing and Reddit zooms were re-framed to crop first and push 6 % rather than scale a whole page 30 %. Cut length unchanged (74.4 s). |
| 2026-09-04 | W7.6 video v2 (hard-cut rebuild) | none | 0.00 | 0.00 | No Monid or OpenAI spend. Screenshots of brand24.com and monid.ai captured with `video/capture/shoot.mjs` (Playwright, public pages; `app.monid.ai` was not logged in on this machine, so the runs page is not in the cut). Music replaced: `video/public/music.mp3` is now "Cosmic Countdown" (user-supplied file from `~/Downloads`; licence/provenance not recorded in the repo — record before publishing), trimmed from 19.187 s, loudnorm −20 LUFS; the Pixabay track is gone. Narration: ElevenLabs "Eva" (`weA4Q36twV5kwSaTEL0Q`, Eleven Multilingual v2) generated in the ElevenLabs web UI on the free plan (1,082 characters of the 10k monthly quota; library voices are 402 through the API, see W7.2), downloaded, loudnorm −16 LUFS, 69.6 s; cues measured by `video/capture/measure-cues.mjs` (15 silence segments merged into 11 cues by character share). The voice sets the length: the cut is 74.4 s, over the 60 s target and under the 90 s cap. The W7.2 Rachel take stays as ledger evidence in `narration.runs.jsonl`. |
| 2026-09-04 | **W6.1 demo (frozen)** | session 20260904T033800Z-nubank-53455a → `results/demo/` (42 run ids in its runs.jsonl) | 2.0088 | 0.1944 | `sonar run --profile full Nubank --vs Itaú "C6 Bank" PicPay --resamples 10000`, key 3, budget cap raised. **verdict RECONCILED, `sonar verify` ok, 0 failed runs.** 348 fetched / 341 deduped / 341 labelled. Nubank SoV 0.291 net +0.092; Itaú SoV 0.269 net +0.159; C6 Bank SoV 0.158 net −0.079; PicPay abstains (12 current). 21 topics, 11 events, WoW abstains all. total $2.2032 → $8.81/mo → 39.6× vs $349. elevenlabs voice run $0.0265. H1 pass, H3 0.84 (not cleared), H2 partial. **A `sonar reconcile` foot-gun:** ran demo-empty probes/runs before reconciling this → its window polluted → restored with a 5s-slack bounded `reconcile_session`. |
| 2026-09-04 | demo-empty candidate A: Avenza | session 20260904T035121Z-avenza-ff217c, `out/demo-empty/` | 0.3127 | 0.0178 | `sonar run --profile full Avenza --no-voice`. RECONCILED. **Not empty** — 59 fetched, SoV 1.0 (only brand), net 0.66. Discarded as demo-empty; kept for reference that Avenza has real coverage. |
| 2026-09-04 | **demo-empty (frozen): Zephyrium Bank** | session 20260904T035438Z-zephyrium-bank-3a3600 → `results/demo-empty/` (9 run ids) | 0.2282 | 0.0000 | `sonar run --profile full "Zephyrium Bank" --no-voice`. **verdict RECONCILED, `mentions.fetched = 0`, 0 failed runs, no unmatched.** Every source abstained `empty`; receipt lists all 9 runs with cost. **H4 pass** ($0.2282 > 0 on a zero-mention brand). |
| 2026-09-03 | voice probe (key 2) | session 20260903T214315Z-nubank-36f909, `out/voiceprobe/` — 12 run ids incl. elevenlabs 01M1MKNZZBRT6SQ217YCR68T47 | 0.0817 | 0.0218 | `sonar run --profile lite Nubank` **with voice**. verdict RECONCILED, `sonar verify` ok, no unmatched. **Voice path validated end-to-end:** narration LLM → Monid `elevenlabs /text-to-speech` → real `brief.mp3` (699 KB, MPEG L3 128 kbps 44.1 kHz). **ElevenLabs unit measured: $0.0235 / 470 chars = $0.05/1000 chars** (confirms `ELEVENLABS_USD_PER_1K_CHARS`). Notes: (a) Monid was BLOCKING — reddit / trustpilot / g2 / yt-comments all `BLOCKED`, news failed both pages (transient load; reddit worked 30 min earlier). BLOCKED is a pre-registered terminal abstention (error matrix), not retried. (b) auto-narration `numbers_verified=false` — it quotes total cost from the pre-voice digest and the voice run then adds $0.0235; the shipped `digest.json` narration is ~2¢ stale on the cost line. Not gated by `make check-claims` (that checks `video/src/data/narration.json`, W7.2). Known limitation, candidate DECISIONS entry. |
| 2026-09-02 | W5.5 solo (key 2, adapters fixed) | session 20260902T210914Z-nubank-43ee7e, `out/w5.5-solo/` — 01M1HZ8RA6J5TRJP7TWM3JGPJT +10 more | 0.2415 | 0.0375 | `sonar run --profile lite Nubank --no-voice`, backgrounded, key 2. **verdict RECONCILED, `sonar verify` ok.** 74 mentions, all 74 labelled, 14 not_about_brand (19%). **Adapter fixes confirmed live** — reddit "1 item skipped, deleted or empty content" note, no spurious schema_drift; abstentions are honest (youtube_comment HTTP 400, trustpilot/g2 `empty`). Real topic ("Nubank Stock Analysis", n=3), **2 events detected** (09-01 n=9, 09-02 n=21, baseline_median 2). Sentiment counts computed (pos 19 / neg 14 / neu 27, n_confirmed 28) but **net + WoW ABSTAIN** — pre-reg rule: `n < 20` in the previous 7-day period (14-day window → 7+7 split, previous half too thin). This is OQ-HO-3. Key 2 wallet ≈ $0.29. |
| 2026-09-02 | W5.5 real (key 2) | session 20260902T194057Z-nubank-57d7a9, `out/w5.5-real/` (21 run ids in its runs.jsonl) | 0.4733 | 0.0454 | `sonar run --profile lite Nubank --vs Inter --no-voice`, backgrounded, on **key 2**. **verdict RECONCILED, `sonar verify` passes.** 133 mentions, **all 133 labelled, 0 errors** — the classifier fix holds on real data. But: (a) 56/133 `not_about_brand` — "Inter" collides with Inter Milan (football topic "Lautaro Chooses to Stay at Inter" clustered); (b) sentiment + SoV **abstained** for both brands (too few relevant after the homonym filter); (c) 3 adapters hit `schema_drift` on Apify "no-results" error-items — youtube/facebook return `{error,…}` items the adapter reads as a missing `id`/`text`; reddit skipped on one deleted comment with no `body`; Inter reddit hit the RUNNING deadline. Real digest/receipt in `out/w5.5-real/`. Key 2 wallet ≈ $0.53. |
| 2026-09-02 | W5.5 attempt 3 (killed) | session `out/w5.5-attempt3` — orphan reddit 01M1HT1AR6C3NSMXWKSGEYKY28 (billed, not in local ledger by id), youtube 01M1HT1ARNJJQ7J8WAYVNB5HE5, instagram 01M1HT1AR53RTERJ2Z61EKGXNS, tiktok 01M1HT1ARVFD0KQYJSRV4SC38D, gmaps 01M1HT1ARQXVQE3S5P9RSEEG71, facebook 01M1HT1ARS3X87HSX3R4NRVYM7, trustpilot 01M1HT1FMDDB38CR8N01RD5GCQ, g2 01M1HT1R5ARG6DW2KT9E31FAE0, news 01M1HT1V9TMZ5EK9VF5J7R931V + 01M1HT1XW5NZRMFCNKB56MQ0GG, yt-comments 01M1HT3E0JVSKKKKD8SJ85J6P6 (BLOCKED) | ~0.2408 | 0.00 | `sonar run --profile lite Nubank --no-voice` on the **old** key. Killed by a 120 s foreground timeout while polling — must background live runs. Monid ran every fetch anyway: reddit $0.134, youtube $0.0225, instagram $0.00345, tiktok $0.009, gmaps $0.01485/22, facebook $0.007, trustpilot $0.03 (0), g2 $0.02 (0), news $0, yt-comments BLOCKED $0. No receipt, no mentions saved. Old key wallet ≈ $0.05 — effectively spent, per operator instruction switch to the second key here. |
| 2026-09-02 | W5.5 attempt 2 | session 20260902T192411Z-nubank-f69c73 — 01M1HS8D4W77SMAG0BAJT21H5E, 01M1HS8D5H28HVJ3WWTW1P683F, 01M1HS8P8HW8AXWVCQCMP077Q4, 01M1HS8YQ030M5CRQ8RF125AJH, 01M1HS90D9ESQ39XTH5N95GAMS, 01M1HS8YS69JD24SF84NJ1J8PV, 01M1HS8D3AMMT0SW77T9MB09KM, 01M1HS8D41WS3KTJJDFV1EPGCC, 01M1HS9J5ZR8S5NV324MFDN9NH, 01M1HS8D3FCWAMA7RS8FQ7VJW4, 01M1HS8D6MM6EXC4HQS8WMAANW | 0.2320 | ~0.0000 | `sonar run --profile lite Nubank --no-voice` after the pipeline fix. **verdict RECONCILED**, 11 runs, 0 failed, no unmatched. 67 mentions fetched (reddit 15, tiktok 19, instagram 15, gmaps 9, youtube 5, facebook 2, news 2). trustpilot/g2 lookups found no entity (abstained, reviews skipped); yt-comments HTTP 400. **All 67 labelled `error`** — second bug: `gpt-5.6-luna` rejects `temperature=0.0` (400), so every classify batch failed, `llm_usd $0`, empty topics. Fixed `ec789de` (drop the param; verified live). Real mentions saved; not re-analysed (no offline re-label path, single brand). Wallet ~$0.52 → ~$0.29. |
| 2026-09-02 | W5.5 attempt 1 (crashed) | session 20260902T190653Z-nubank-cb9cae — reddit 01M1HR8PMMP6SESZMP3SYG24WC, youtube 01M1HR8PN33AQCS8DNS2AW8H2F, yt-comments 01M1HRAFHKNH5FJC2SCZNN2TTP, tiktok 01M1HR8PMSP89RE2QZ1G847C4V, instagram 01M1HR8PN48VHQ87S2DZRK6QJS, gmaps 01M1HR8PMZZVV4H0WWQMY9AN4W, facebook 01M1HR8PN2GR27M85MNPCA0DEK, trustpilot 01M1HR97KK9CBJYSCEJNZYD616, g2 01M1HR98976QYRZ6ZFSW2MTFJF, news 01M1HR9GD0Y816J620RJYWVNTM | 0.2266 | 0.00 | `sonar run --profile lite Nubank --no-voice`, est $0.4293; session dir left uncommitted under out/. All 10 source runs COMPLETED; pipeline then crashed parsing the news result (pre-existing bug, fixed `fc5b2c9`). No receipt written. Costs from `GET /v1/runs` (authoritative): reddit $0.134/20, youtube $0.0225/5, yt-comments $0 (HTTP 400, no charge), tiktok $0.009/20, instagram $0.00345, gmaps $0.000675/**1 review**, facebook $0.007/2, trustpilot $0.03 (0 companies), g2 $0.02 (0 products), news $0. No unmatched, nothing pending — reconciliation obligation met by direct listing. Data too thin to salvage (1 maps review, 0 trustpilot/g2/yt-comments). Wallet $0.75 → ~$0.52. |
| 2026-09-02 | W0.1 closed | none | 0.00 | 0.00 | Hackathon registration submitted; X handle @uiuizap; Monid workspace budget/run cap left unset by decision (sonar's own guard is the stop) |
| 2026-09-02 | W0.1 + W0.3 | none | 0.00 | 0.00 | keys stored in ~/.sonar/.env; monid whoami OK, balance $1.00; OpenAI models list OK (gpt-5.6-luna/terra present); 7 inspects saved to docs/monid/inspect/ (all free) |
| 2026-09-02 | W0.1 setup wizard (`scripts/setup-wizard.sh`) | none | 0.00 | 0.00 | Wizard writes `~/.sonar/.env` (mode 600) with Monid key, budget, run cap, OpenAI key, X handle. Verification calls are unbilled (`monid whoami`, `monid discover`, OpenAI `models.list`). No Monid spend has occurred yet. |

Running totals (one shared workspace across all 3 keys). Real Monid spend
that landed on a kept artifact: W3.7 smoke $0.25 + voice probe $0.0817 +
W5.5 runs (exploratory, key 2, $1.41 across five sessions) + **W6.1 demo $2.0088** +
**demo-empty (Zephyrium) $0.2282** + Avenza (discarded) $0.3127 +
W6.1-clean/dry/v3 (superseded) ~$2.8 + probes/canaries ~$0.5 +
**W7.2 narration $0.0448** + **W7.3 casts $0.6088 + $0.2219** (kept) +
**W7.3 duplicate-run mishap ~$0.58** (discarded, operator error) +
**W8.2 rehearsal $0.3153** ≈ **$9.4 Monid** to date (the listed terms sum to $9.36). OpenAI ≈ **$0.65**
total. The $3/day workspace budget cap (control `01M1GB8M12…`) was the
evening's blocker; the operator raised it, then topped up to $20. No `$`
work remains; the $1.50 judging reserve is intact.

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
| W5.5 shakeout (folded into W6.1) | `sonar run --profile lite Nubank …` | 1.30 | ~$1.0 across several attempts; surfaced 4 bug classes (`fc5b2c9`, `ec789de`, `73bd320`, `e0814c7`), D016, D017 | done — no separate W5.5 artifact; W6.1 is the first frozen digest |
| W6.1 full demo + empty | `sonar run --profile full Nubank --vs "Itaú" "C6 Bank" PicPay --resamples 10000`; `sonar run --profile full "Zephyrium Bank"` | 2.80 | **demo $2.0088 + empty $0.2282 = $2.24 billed** | **done 2026-09-04, RECONCILED, frozen to `results/demo/` + `results/demo-empty/`** (D019) |
| W7.2 narration TTS | one ElevenLabs run through Monid `voice/tts` | 0.10 | done 2026-09-04, billed 0.0448 | `video/public/narration.mp3`; direct ElevenLabs (D016) blocked on the operator's free plan, routed through Monid |
| W7.3 casts (`run_trace`, `ask`, `empty_run`) | `sonar run --trace --profile lite …`, `sonar ask …` | 0.70 | done 2026-09-04, billed 0.6088 + 0.00 + 0.2219 = 0.8307 (+ ~0.58 lost to a duplicate-run operator error, archived) | `video/public/casts/*.cast` recorded; see spend ledger rows above |
| W7.5 music + render | `pnpm render` | 0.00 | done 2026-09-04, $0.00 | Superseded by W7.6: the Pixabay track was replaced by "Cosmic Countdown" and the cut re-rendered at 74.4 s; the shipped files are `results/video/sonar.mp4`, `results/video/sonar.srt`, `results/video/cuts.png`, `results/social/{receipt-card.png,x-post.txt}` |
| W8.2 rehearsal | `sonar run --trace --profile lite "Banco Pan" --out results/rehearsal --max-spend 1.50` | 0.80 | done 2026-09-04, $0.3153 Monid + $0.0199 OpenAI | `RECONCILED`, 21 mentions, SoV/sentiment abstain (6 and 4 per week, under 20), 3 topics; see the ledger row |

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

### 2026-09-03 — `sonar ask` validated (W5.2 / video beat 4)

Ran `sonar ask` twice against `out/w5.5-solo/` ($0.0036 + $0.0019 OpenAI,
no Monid). Cosine retrieval over 60 relevant mentions, top 20; citations
resolve to real Google Maps / TikTok / Instagram URLs. One run came back
`status unverified` — the model invented one citation id and the gate
caught it (`unknown citations [...]`, the W5.2 fabricated-id path). The
other was `status ok`, 7 verified citations. It is stochastic: for the
W7.3 `ask` cast, retry until `status ok`, or constrain the prompt further.

### 2026-09-03 — REPRODUCTION.md offline path is broken (OQ-REP-1, for W8.1)

**Resolved 2026-09-04 (W8.1):** the offline block now runs `verify`,
`render --from`, and `run --fixtures --profile smoke` (the recorded-fixture
replay, verdict `REPLAY`); the seed-777 claim points at `tests/test_stats.py`;
`make validate` runs mypy and pytest as the docs said it did.

`docs/REPRODUCTION.md` line 22 runs
`sonar render results/demo --resamples 10000 --seed 777 --out out/repro`
and claims render "re-runs the statistics from the frozen mentions and
labels". The shipped `sonar render` takes `--from DIR`, has **no**
`--resamples` / `--seed`, and only re-renders Markdown from the stored
`receipt.json` + `digest.json` (`cli.cmd_render` → `replay_artifacts`).
W6.1 runs don't save raw payloads, so `--fixtures` replay of `results/demo/`
isn't possible either. Resolve in the W8.1 cycle: either add
`sonar render --recompute` (re-run `sonar.stats` from `mentions.jsonl` +
`labels.jsonl`, the real determinism proof) or rewrite the offline path to
`make validate` (golden stats seed 777) + `sonar verify`. Not a W6.1
blocker.

### 2026-09-04 evening — W6.1-clean is the demo candidate; Monid degrading

- **`out/w6.1-clean/`** (key 3, session `20260904T030429Z-nubank-d554d5`):
  **verdict RECONCILED, `sonar verify` ok.** 277 mentions, 272 labelled.
  D018 confirmed live — **Nubank SoV 0.288 [0.20,0.38], net +0.013 [-0.16,
  0.18]; Itaú SoV 0.336 [0.25,0.43], net +0.023 [-0.14,0.19]**; C6 (14) and
  PicPay (38) abstain (thin — partly the BLOCKED rate). 13 topics, 6 events,
  WoW abstains for all. **ratio 82× vs Brand24** ($4.24/mo equiv). Monid
  $0.9151 + OpenAI $0.1462. brief.mp3 written. 36/77 source runs BLOCKED.
- **A `sonar reconcile` foot-gun (my error, and a sonar bug):** running
  another Monid job between a session finishing and reconciling it pollutes
  the first session's window (`reconciled_at = now`, not `finish + slack`).
  I ran W6.1-v3 before reconciling W6.1-clean → its receipt went PARTIAL
  with ~40 "unmatched" that were v3's runs. Restored with a bounded
  `reconcile_session(now=finish+5s)`. *sonar fix:* bound the reconcile
  window to the session's own `finished_at`, not wall-clock now.
- **W6.1-v3** was worse (92/116 BLOCKED, C6+PicPay got 0 mentions) —
  discarded.
- **ROOT CAUSE of every BLOCKED today: a $3/day workspace budget cap.**
  Raw `/v1/run` `reason`: *"Workspace day budget exceeded: available
  $-0.03 of the $3 limit"*. Control `01M1GB8M12ZEDM99NS357K29NQ`
  (`WORKSPACE_BUDGET`, `period: DAY`, `limitAmount: 3`, `windowStart`
  00:00 UTC). **All 3 API keys share this one workspace budget** — key
  switching never helped. Today's $3.03 went to W6.1 dry ($1.57, PARTIAL,
  discarded) + W6.1-clean ($0.92, kept) + v3 + probes. The "36 BLOCKED
  mid-run" in W6.1-clean was the budget running out partway.
  **Operator action:** raise the cap at https://app.monid.ai/rules
  (control `01M1GB8M12…`) to ~$20, or wait for the 00:00 UTC reset
  (2026-09-05) — but $3/day barely covers W6.1 ($2.8) alone.
- **Not frozen yet.** Waiting for Monid to stabilise enough for either a
  cleaner 3-4 brand W6.1 or at least the Avenza demo-empty run (freezing
  `results/demo/` without `results/demo-empty/` breaks `make check-claims`).
  Fallback: freeze W6.1-clean as-is (2/4 brands report — honest, functional).

### 2026-09-04 — the "outage" was a wallet mix-up; W6.1 dry run; D018

- The 4.5h of `BLOCKED` was **not** a Monid outage. Raw `/v1/run` returns a
  `reason`: *"Insufficient wallet balance: available $0.023375"*. Monid uses
  `BLOCKED` for a wallet-block, and sonar does not surface the `reason` — so
  an empty wallet looked identical to an outage. The $20 top-up had landed
  on **key 1** (`monid_live_VI12…`), not key 2 (`…DJVq…`, drained to $0.02).
  **`~/.sonar/.env` now on key 3** (`monid_live_lAzr…` (its full value is in `~/.sonar/.env`, not here),
  ~$18 per the operator); key backups under `~/.sonar/.env.bak-*`.
  *Follow-up:* sonar should distinguish a wallet-block `BLOCKED` (trip the
  402 breaker) from a provider one.
- **W6.1 dry run** (key 1, `out/w6.1/`): verdict PARTIAL (my error — I fired
  balance-check probes mid-run, 2 unmatched at $0.09), $1.5715 Monid +
  $0.1869 OpenAI. **287 mentions, 4 brands, 7 events, ratio 49.6× vs
  Brand24 ($7.03/mo equiv).** But: SoV + net abstained for all 4 brands
  (previous 7-day period had 7-13 mentions) → **D018 / PRE-REG A5**: level
  gates on the current period only, WoW on both. Predicted clean outcome:
  Nubank/Itaú/C6 report level SoV+sentiment, PicPay abstains (13<20 current),
  WoW abstains for all.
- **Bug 6 fixed:** `youtube_comments` sent `sortCommentsBy="newest"` → HTTP
  400 on every run (allowed: `TOP_COMMENTS`/`NEWEST_FIRST`). Blocked H2.
- **Clean W6.1 re-run** on key 3 in progress → `out/w6.1-clean/`, then
  `results/demo/`.

### 2026-09-03 ~18:00–18:15 local — Monid "outage" (was: key 2 wallet empty)

Sustained (≥ 45 min and counting): **every Apify actor** (`trudax/reddit-`,
`compass/google-maps-`, `streamers/youtube-`, trustpilot/g2 search) returns
`BLOCKED` with an empty `providerResponse` — no reason given, so it is
Monid's actor-invocation layer, not a per-request block. **TinyFish
`/search`** returns `httpStatus 503 "Search service unavailable"`. Only
**ElevenLabs `/text-to-speech`** completes. Apify actors last worked on
key 2 in the 2026-09-02 21:09 UTC solo run — this is not a blip.

`BLOCKED` is a pre-registered terminal abstention (error matrix), not
retried. **W6.1 needs 6 Apify sources + TinyFish — it cannot run until
Monid recovers.** A persistent health monitor (`sonar run --profile smoke
Nubank`, $0 while BLOCKED, ~$0.28 when it works) re-checks every 20 min
and prints `APIFY HEALTHY -- fire W6.1` on recovery. Deadline is Sept 10;
there is slack. Nothing to do but wait for Monid.

Update: the outage was still ongoing at **21:00 UTC 2026-09-03 (~3h20m)**.
One brief flicker to gateway `502` around 22:53 UTC, otherwise clean
`BLOCKED` throughout. If Monid is still down on the next operator session,
just re-run the two staged commands (W6.1 + Avenza) once the smoke canary
passes — everything else (5 bug fixes, D017, voice/ask validation) is
already committed and green.

### 2026-09-03 — wallet topped to $20; funded push to submission

- Wallet is $20 (key 2). `MONID_WORKSPACE_BUDGET_USD=10` in `~/.sonar/.env`
  is a stale local hint only — the real caps are `MONID_RUN_CAP_USD=3.5`
  and `--max-spend`.
- **Bug 4 fixed (`e0814c7`):** Avenza run went `verdict PARTIAL` because
  Monid returned 503 for two `tinyfish /search` POSTs whose bodies still
  carried the runId Monid had created. The client dropped the id; the runs
  completed server-side as `unmatched_remote_run_ids` (PARTIAL, no
  reconcile can clear it). Now a 5xx-with-runId is polled, and a
  5xx-without-runId is retried up to MAX_ATTEMPTS. 1374 tests green.
- **Empty-run brand:** Avenza is not empty (31 fetched, 13 relevant, every
  digest section abstains, 0 topics). Treated as the *sparse-coverage*
  brand for `results/demo-empty/` — the receipt still lists all 11 runs
  and their cost, the digest draws no conclusions, which is the point.
  Video beat 5 wording changes from "zero mentions" to "barely any
  coverage".
- Funded run order: (1) voice probe `lite Nubank` w/ voice → validate the
  Monid ElevenLabs path; (2) W6.1 `full Nubank --vs Itaú "C6 Bank" PicPay`
  voice on, 10k resamples → `results/demo/`; (3) Avenza → `results/demo-empty/`;
  (4) W6.2 freeze; (5) W7.2 narration, W7.3 casts; (6) W8.1 repro.

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

- **OQ-HO-1 — RESOLVED (2026-09-04).** The control is a *rule*, not a
  workspace setting: `https://app.monid.ai/rules`, type `WORKSPACE_BUDGET`,
  `period: DAY`, `limitAmount` (ships at $3), `windowStart` 00:00 UTC,
  control id `01M1GB8M12ZEDM99NS357K29NQ`, shared by every API key in the
  workspace (see the 2026-09-04 root-cause entry below). There is no Monid
  per-run cap; `MONID_RUN_CAP_USD` is enforced by sonar itself
  (`src/sonar/config.py`). `scripts/setup-wizard.sh` now says so.
- **OQ-HO-2 — RESOLVED (D022).** SDK usage fields. `totals.llm_usd` is
  `usage.prompt_tokens` / `completion_tokens` (cached prompt tokens at the
  cached rate) priced at the list rates in `src/sonar/config.py`
  (`LlmRate`, D003), summed in `src/sonar/report/receipt.py`. No OpenAI
  dashboard export was obtained (the org scope `api.usage.read` was never
  granted; results/demo/openai-usage.csv was never filed), so the
  comparison RED-TEAM §4 asked for did not happen and the figure is
  published as modelled, not billed. SDK retries that were billed but
  returned nothing are invisible to it.
- **OQ-HO-3 — RESOLVED (D017).** The first live solo run showed the real
  cause was not the event rule but a starved previous period: Reddit's
  `time=week` capped the fetch at 7 days while the analysis window is 14,
  so `net`/WoW abstained (`net: n=9 < 20 in previous`). Fixed by
  `time=month` (D017); `postDateLimit` now populates both halves. The
  event rule itself worked correctly on real data (baseline_median 2,
  events detected). Confirm on the frozen demo; if the previous period is
  still under n=20, revisit the `maxItems` cap.
