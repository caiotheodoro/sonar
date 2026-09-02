# DECISIONS.md — sonar design decisions

Frozen: 2026-09-02. Each entry records one settled choice, the rationale,
supporting evidence, alternatives rejected, and the condition that would
force revisiting it. No entry may be edited after the `docs-frozen` gate;
later changes append a new entry that supersedes the old one.

---

## D001 — Kill target: Brand24 Team

**Decision.** Sonar targets Brand24 Team at $349/mo as the incumbent to
displace. Every run prints a side-by-side receipt: what sonar billed versus
what Brand24 charges monthly.

**Rationale.** Brand24 Team is the most-cited mid-market brand-monitoring
plan, priced high enough that a pay-per-call alternative has a clear cost
story but not so dominant that judges will dismiss the comparison as
unrealistic. The $349 figure is publicly listed and archiveable.

**Evidence.** Brand24 pricing page captured 2026-09-02
(`results/incumbent/brand24-2026-09-02.png`); web.archive.org snapshot
receipt in `results/incumbent/archive-url.txt`.

**Alternatives rejected.** Mention ($49/mo, too cheap to make a dramatic
cost story); Sprout Social ($249/mo, enterprise-locked, no public API);
Meltwater (custom pricing, no published number to put on screen).

**Reverses when.** Brand24 removes or changes the $349/mo tier before
submission, or judges explicitly disqualify the comparison. Reversal:
pick the next published-price incumbent and update the receipt constant in
`report/incumbent.py`, README, and DECISIONS.

---

## D002 — Zero-infra architecture

**Decision.** Sonar is a local Python CLI plus a Claude Code skill. No
server, no container, no database, no cron. Every run is a fresh process
that exits when done. State is files on disk: `results/`, `out/`,
`tests/fixtures/`.

**Rationale.** The hackathon scores "would adopt" on a 72-hour horizon.
Zero infrastructure means zero ops burden for a judge evaluating the
project. It also eliminates the largest class of deployment bugs that
could derail a live demo. Pay-per-call economics work because Monid
handles the upstream infrastructure; sonar just orchestrates HTTP calls.

**Evidence.** The full pipeline (fetch → label → stats → receipt → voice)
runs as a single `sonar run` invocation that exits 0 or 2. The task graph
(`2026-09-02-task-graph-and-design.md`) defines 8 waves with no
infrastructure provisioning step. Every dependency (`httpx`, `pydantic`,
`openai`, `numpy`) is a pip-installable library with no native bindings.

**Alternatives rejected.** FastAPI + Postgres (deploy burden, cold start
kills the demo); Redis queue (adds a service to manage); Docker Compose
(judges must install Docker); serverless functions (cold start, vendor
lock-in, hard to show a live trace).

**Reverses when.** A judge or collaborator requests a hosted version for
continuous monitoring. Reversal: add a thin server wrapper, but the CLI
remains the primary interface.

---

## D003 — OpenAI models, IDs, and prices

**Decision.** Sonar uses two OpenAI models dated 2026-09-02:

| Role | Model ID | Input $/MTok | Output $/MTok |
|---|---|---|---|
| Bulk classifier | `gpt-5.6-luna` | 0.20 | 1.20 |
| Tiebreak judge | `gpt-5.6-terra` | 2.00 | 12.00 |

Embedding model is a third OpenAI endpoint (model id in `config.py`,
price negligible per call). All model IDs and prices are recorded in
`docs/DECISIONS.md` and `src/sonar/config.py` with the date they were
verified.

**Rationale.** Luna is the cheapest reasoning model that produces
structured JSON reliably enough for bulk classification at ~1000
mentions per brand. Terra is a stronger model reserved for the ~10 % of
mentions where the deterministic signal and the classifier disagree —
high-stakes calls where a wrong label distorts the net sentiment. Using
two models keeps total LLM cost under $2 for a full brief.

**Evidence.** Pricing verified 2026-09-02 from the OpenAI pricing page.
Luna structured-output latency and token usage measured during W5.5 live
runs (logged in `docs/HANDOFF.md`). Tiebreak invocation rate on the
audit sample will be measured in W4.1.

**Alternatives rejected.** Single-model (Luna only): cheaper but tiebreak
quality drops; two weaker models: Terra's instruction-following is
measurably better on contested cases; local models: judges can't verify
cost, and the project commits to OpenAI transparency; GPT-4o: more
expensive and slower for bulk work that doesn't need the full context
window.

**Reverses when.** OpenAI deprecates either model ID, or measured LLM
cost exceeds $4 for a full brief. Reversal: update `config.py`
`LLM` dict and `LLM_RATES`, log the change in a new DECISIONS entry.

---

## D004 — Luna as bulk classifier

**Decision.** Every mention passes through `gpt-5.6-luna` for label
classification (positive / negative / neutral / irrelevant) plus a
≤ 20-word rationale. The prompt is frozen at `PROMPT_REV` in
`config.py`. Results are cached; repeated calls for the same
mention_id return the cached label.

**Rationale.** Bulk classification is the highest-volume LLM call
(~1000 per brand). Luna at $0.20/$1.20 per MTok keeps the per-mention
cost under $0.002. Structured JSON output with `extra="forbid"` on the
pydantic model guarantees parseable responses. The 10 % audit sample
(seed 777) is always tiebroken regardless of agreement, giving a
measurement of classifier–tiebreak agreement for H3.

**Evidence.** Monid provider costs for the fetch layer are dominated by
Apify compute units, not OpenAI tokens. The two-signal policy
(Appendix §Pipeline rules) is designed around a cheap bulk model plus
an expensive judge, not a single expensive pass.

**Alternatives rejected.** Terra for bulk: 10× the price, same accuracy
on easy cases; regex / lexicon only: misses context-dependent sentiment;
local model: no cost transparency for judges; human review: doesn't
scale to 1000 mentions.

**Reverses when.** Luna accuracy on the audit sample drops below 0.80
against tiebreak, or OpenAI raises Luna pricing by > 50 %. Reversal:
promote Terra to bulk for the affected language, or switch to a
comparable model and log the change.

---

## D005 — Terra as tiebreak

**Decision.** When the deterministic signal (rating bucket or lexicon)
disagrees with the Luna classifier, or when there is no deterministic
signal and Luna confidence is below 0.6, the mention is sent to
`gpt-5.6-terra` for a final label. The tiebreak label wins; the mention
is marked `contested` with `decided_by=tiebreak`. Tiebreak calls are
capped at 40 % of mentions per brand.

**Rationale.** Tiebreak is the quality safety net. Terra is a stronger
model that makes fewer errors on ambiguous text, but costs 10× more.
Capping at 40 % bounds cost; the 10 % mandatory audit always tiebreaks,
giving a clean H3 measurement.

**Evidence.** The two-signal policy is defined in Appendix §Pipeline
rules. The cap is enforced in `config.py` as `TIEBREAK_CAP = 0.40`.
The audit sample (seed 777, 10 % of mentions) is always tiebroken
regardless of agreement.

**Alternatives rejected.** No tiebreak: net sentiment would drift on
ambiguous mentions; always tiebreak: 10× LLM cost; human tiebreak:
breaks the zero-infra promise; consensus of multiple models: slower,
more complex, no measurable quality gain over a single stronger judge.

**Reverses when.** Tiebreak call rate exceeds 25 % of mentions (signs of
a bad bulk classifier), or Terra cost drives total LLM spend above $4
for a full brief. Reversal: tune the confidence threshold, retrain the
prompt, or switch to a different tiebreak model.

---

## D006 — English-only voice brief

**Decision.** The voice narration (`sonar voice`) is produced in English
only, regardless of the brand's home market or the language distribution
of mentions. The script is ≤ 900 characters, generated from the Digest
JSON via `complete_json`, and passed through a numbers gate that rejects
any number not present in the digest. Output is MP3 via ElevenLabs
`eleven_flash_v2_5`.

**Rationale.** The hackathon judging is in English. A bilingual TTS pipeline
would double the prompt surface, the number-gate logic, and the test
matrix for no scoring benefit. English narration is also the language
of the video (≤ 90 s, captioned). Keeping voice English-only eliminates
a class of localization bugs.

**Evidence.** The video script and captions are English (W7.1 shot list).
The voice adapter (W3.6) uses a single voice_id selected from
ElevenLabs `/voices`. The numbers gate in `voice/` rejects planted
foreign numbers in tests.

**Alternatives rejected.** PT voice for Brazilian brands: doubles
prompt/tts paths, judges may not understand; bilingual toggle: adds
config complexity for no scoring gain; silent receipt: loses the
"narration" hook that makes the demo memorable.

**Reverses when.** Judges or collaborators request multilingual voice for
a specific brand. Reversal: add a `lang` parameter to `sonar voice`,
extend the numbers gate, and log the new ElevenLabs voice_id.

---

## D007 — No SMS channel

**Decision.** Sonar does not send SMS alerts. The only notification
channels are the CLI stdout/stderr output, the receipt file, and the
voice narration. No phone number is collected or stored.

**Rationale.** SMS requires a telephony provider (Twilio, etc.), adds a
per-message cost that is not measurable in the receipt, and is out of
scope for a brand-listening tool whose output is a document (receipt +
digest), not a real-time alert. Judges score "would adopt" on the
workflow the tool replaces, not on alerting.

**Evidence.** No SMS provider appears in the Monid endpoint catalog
(`docs/monid/inspect/`). The error matrix and pipeline rules contain no
SMS references. The hackathon scoring rubric rewards live data and cost
transparency, not notification channels.

**Alternatives rejected.** Twilio SMS: per-message cost leaks outside the
receipt; email alerts: requires SMTP config, adds a deployment dependency;
Slack webhook: adds a config surface for zero scoring benefit.

**Reverses when.** A collaborator or judge requests alerting as a core
feature. Reversal: add a `notify` module with explicit opt-in and
per-channel cost in the receipt.

---

## D008 — X as the only social platform

**Decision.** Sonar does not fetch, analyze, or post to X (Twitter).
X is the submission channel: the video and hook line are posted natively
on X with `#monid` in the tweet body. But sonar's data pipeline does not
include an X adapter. X appears in `coverage_gaps` on the receipt.

**Rationale.** The Monid API catalog does not include an X/Twitter
endpoint (`docs/monid/inspect/` shows no X adapter). Building a custom
scraping path for X violates the "live data from Monid providers"
constraint. X is chosen as the submission platform because the hackathon
scores reach (+50 per platform, X is the easiest to post to natively)
and the video format (≤ 90 s, captioned) maps well to X video.

**Evidence.** The endpoint reference in the task graph appendix states:
"No X/Twitter endpoint today." The provider registry (W2.6) registers X
as `available=False` with a dated note. The coverage gap is disclosed in
the receipt and COVERAGE.md.

**Alternatives rejected.** Custom X scraping: brittle, violates the
Monid-provider constraint, risk of account suspension; Bluesky / Mastodon:
lower reach, no hackathon scoring benefit; Instagram posting: requires
a business account, adds deployment friction.

**Reverses when.** Monid ships an X/Twitter endpoint. Reversal: implement
`providers/x.py`, remove the `available=False` flag, and add X data to
the receipt.

---

## D009 — Compact documentation spine

**Decision.** Sonar's documentation is seven files, written before any
code, frozen at the `docs-frozen` gate. No file is optional; no file is
generated. The spine is:

1. `CONTRACTS.md` — every pydantic record, verbatim from the Appendix
2. `docs/PRE-REGISTRATION.md` — estimands, thresholds, stopping rules,
   frozen-text notice
3. `README.md` — the kill, the receipt, scope, quickstart
4. `docs/DECISIONS.md` — this file
5. `docs/RED-TEAM.md` — ≥ 12 attacks on sonar's own claims
6. `docs/COVERAGE.md` — Brand24 source vocabulary, row by row
7. `docs/HANDOFF.md` — spend ledger, run ids, what not to do

Plus `docs/REPRODUCTION.md` (fresh-clone commands), `AGENTS.md`, and
`llms.txt`.

**Rationale.** Documentation-first forces every design choice to be
settled before implementation begins, eliminating the "we'll fix it in
post" class of bugs. The compact size (7 core files) means a judge can
read the entire spec in under 15 minutes. The `docs-frozen` gate
ensures that the code implements the spec, not the other way around.

**Evidence.** The task graph (Wave 1) allocates 7 parallel workers to
documentation, each owning disjoint files, before any `src/` commit. The
`docs-frozen` gate is enforced: `git log` must show the docs commit
before any code commit. The `check-claims` test (W5.4) verifies that
every path cited in docs exists in `git ls-files`.

**Alternatives rejected.** Inline docstrings only: no spec to review,
judges can't audit design; generated docs (mkdocs, sphinx): adds a build
step, docs drift from code; single monolithic README: too long, no
ownership boundaries; wiki: requires hosting, not version-controlled.

**Reverses when.** The project outgrows 7 files (e.g., multi-brand
parallelism, plugin system). Reversal: add entries to the spine, update
W1 tasks, and re-freeze.

---

## D010 — Cluster bootstrap as the statistical unit

**Decision.** All confidence intervals and significance tests in sonar
are computed by clustering mentions on `cluster_key` and bootstrapping
over clusters, not over individual mentions. Parameters: B=2000
resamples (10000 for the frozen demo), percentile 95 %, seed 777,
shared resample indices for paired deltas. Design effect is reported as
(cluster CI width / iid CI width)².

**Rationale.** Mentions from the same source cluster (e.g., a Reddit
thread, a YouTube video's comment set) are not independent. Bootstrapping
over clusters instead of mentions produces honest CIs that account for
intra-cluster correlation. This is the standard approach in survey
statistics and is the method used in Caio's `assay` project
(`scripts/intervals.py`), from which the bootstrap logic is ported.

**Evidence.** The PRE-REGISTRATION (W1.2) freezes B=2000, seed 777, and
the design-effect formula. The statistics module (W4.3) implements the
cluster bootstrap with shared resample indices. The test suite
(`tests/test_stats.py`) includes property tests that verify CI width
decreases with more clusters and that the design effect is ≥ 1 for
correlated data.

**Alternatives rejected.** IID bootstrap (ignores clustering, CIs too
narrow, false positives); delta method (requires distributional
assumptions that don't hold for skewed mention counts); Bayesian credible
intervals (harder to explain to judges, no standard stopping rule);
jackknife (same O(n²) cost as bootstrap but less flexible for paired
deltas).

**Reverses when.** Cluster sizes become so small (< 5 clusters per
brand) that bootstrap CIs are unreliable, or a reviewer demonstrates
that the cluster key is wrong for a major source. Reversal: switch to
IID bootstrap with a wider CI, or redefine the cluster key, and log
the change.

---

## D011 — ElevenLabs endpoint shape, resolving CONTRACTS OQ-6

**Decision.** The voice brief uses `elevenlabs /text-to-speech` with
`model_id="eleven_flash_v2_5"`, `voice_id` and `text` all in `input.body`,
text capped at 900 characters (the endpoint caps at 5,000). The run output
carries an `audio` object with a signed `download_link` (valid about one
hour, file retained seven days); the adapter downloads the MP3 at run time
and stores it under `out/<session>/brief.mp3`. `audio_base64` is only
present when Monid's save failed and is treated as a fallback, not the
primary path. `RunRecord.billed_units` for this run is characters.

**Rationale.** The public catalog does not expose schemas; the
authenticated inspect (`docs/monid/inspect/elevenlabs_text-to-speech.json`,
captured 2026-09-02 via `POST /v1/inspect`) does. Flash v2.5 is half the
price of multilingual v2 ($0.05 vs $0.10 per 1,000 characters) and the
brief is English only (D006), so the multilingual model buys nothing.

**Evidence.** Inspect response fields `text`, `model_id`, `voice_id`,
`voice_settings`; price matrix keyed on `model_id`; notes state per-run
retention, the signed link, and that an unknown voice or exhausted quota
returns a COMPLETED run with the provider error as data at no charge.
`elevenlabs /voices` is $0 and lists voice ids. The Monid CLI's `inspect`
rejects the leading-slash path (`Endpoint '/text-to-speech' not found`)
while the raw API accepts it; adapters use the raw API.

**Alternatives rejected.** `eleven_multilingual_v2` (double price, no
benefit for English); `eleven_v3` (same price as multilingual, expressive
voice not needed for a receipt readout); MiniMax `t2a_v2` (per-million
pricing, not a Monid-verified English voice path).

**Reverses when.** The ElevenLabs quota behind Monid is exhausted during
judging (the run completes with a provider error, no charge): the brief is
skipped with a warning and the digest and receipt still ship, per the
error matrix. If the flash model's audio is judged unacceptable on the
first live call (W5.5), switch to `eleven_multilingual_v2` and log the
cost delta.

---

*End of decisions. Next entry would be D012.*
