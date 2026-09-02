# sonar — task graph to submission (Monid "We Kill" hackathon)

## Context

Caio is entering Monid's "We Kill" hackathon (Sep 1–10 2026, 23:59 ET;
today Sep 2) with **`sonar`**: a zero-infra Python CLI plus Claude Code
skill that kills Brand24 Team ($349/mo, published) with pay-per-call brand
and competitor listening across Monid providers, shipping the receipt as
the product (every run id with billed cost including empty returns,
bootstrap intervals, significance verdicts, abstentions). Settled through
four grilling rounds; the design reference is in the Appendix.

This plan is **not** the development plan. It is the complete task graph:
every task from now to submission, each with owned files, dependencies,
deliverable, and an executable done-check, arranged in waves so that each
wave fans out to parallel workers with disjoint file ownership. Development
runs on top of it, one `agentgraph dispatch` per task.

## How to run this graph

- **Ownership is by directory or file.** No task edits a path it does not
  own (reconforge's rule). Shared files (`config.py`, `models.py`,
  `CONTRACTS.md`) are frozen at the end of the wave that owns them; later
  changes go through a `DECISIONS.md` entry by the wave lead (Caio's session).
- **Worker briefs are prose, one deliverable each**, never a file list,
  so the worker's own `agentgraph task start` classifies `single` (see
  memory: workers self-classify fanout and block on their first Edit).
- **Done-checks are commands.** A task is done when its command exits 0
  from a fresh shell, not when the worker says so. The lead reads
  `agentgraph node log <id>` before marking a node done.
- **Spread tools across caps**: dispatch `--tool claude|codex|cursor|
  opencode` round-robin; each has its own quota; keep a reroute fallback.
- **Money**: only tasks marked `$` spend Monid or OpenAI credit; they are
  serialized through the lead and logged in `docs/HANDOFF.md`. Cap $10
  Monid total, wallet reserve $1.5 for judging.
- Task ids: `W<wave>.<n>`. `→` = depends on.

## Wave 0 — accounts and repo (Sep 2, serial, Caio + one worker)

| Id | Task | Owns | → | Deliverable | Done when |
|---|---|---|---|---|---|
| W0.1 | Human wizard: Monid signup, API key, workspace budget $10 + run cap $3.5 at app.monid.ai; OpenAI key; hackathon Google Form registration; X account ready | `~/.sonar/.env` (gitignored) | — | keys in env | `monid whoami` and a $0 `monid discover -q reddit` succeed; OpenAI `models.list` returns |
| W0.2 | Repo init: `personal-ml/sonar`, MIT, `.gitignore` (`.sonar/`, `out/`, `.env`, `video/out`, `node_modules`), `uv init`, empty `src/sonar/__init__.py` NOT yet (docs first), GitHub repo private for now | repo root, `pyproject.toml`, `Makefile` skeleton | — | first commit is docs-only scaffolding | `git log --oneline \| wc -l` = 1 and `git ls-files \| grep -c '^src/'` = 0 |
| W0.3 | Install `@monid-ai/cli`, run `monid inspect` for `trustpilot /get_company_reviews`, `/get_company_review_summary`, `/search_companies`, `g2 /get_product_reviews`, `/search_software`, `elevenlabs /text-to-speech`, `/voices`; save raw JSON to `docs/monid/inspect/*.json` | `docs/monid/` | W0.1 | schemas the public catalog hides | 7 JSON files present; each has `input` schema keys |
| W0.4 | Brand24 price snapshot: screenshot + `web.archive.org` save of brand24.com/prices, dated | `results/incumbent/` | — | evidence for `$349` | `results/incumbent/brand24-2026-09-02.png` and `archive-url.txt` exist |

## Wave 1 — documentation spine (Sep 2, fan-out 7, all `→ W0.2`)

All docs written from the Appendix design. No TBD/TODO; unknowns are named
open questions with the trigger that resolves them. Each task owns exactly
its files.

| Id | Task | Owns | Done when |
|---|---|---|---|
| W1.1 | `CONTRACTS.md`: Query, Mention, Label, RunRecord, Topic, Receipt, Digest, Answer records verbatim from Appendix §Contracts, plus cluster_key rules, dedup precedence, source enum, receipt `verdict` rule | `CONTRACTS.md` | every record in Appendix §Contracts appears with all fields; `grep -c TBD` = 0 |
| W1.2 | `docs/PRE-REGISTRATION.md` v1.0.0: estimands, bootstrap unit and method, verdict rule, abstention thresholds, event rule, H1–H5 with thresholds and stopping rules; frozen-text notice | `docs/PRE-REGISTRATION.md` | thresholds listed match Appendix §Statistics; frozen banner present |
| W1.3 | `README.md` (the kill, the receipt, scope claimed and not claimed, quickstart, price side-by-side placeholder wired to `results/demo`), `AGENTS.md`, `llms.txt` | `README.md`, `AGENTS.md`, `llms.txt` | `$349` appears exactly as in `report/incumbent.py` spec; "Not claimed" section lists X, influencer scoring, email alerts |
| W1.4 | `docs/DECISIONS.md` D001–D010: kill choice, zero-infra, OpenAI models (ids + prices dated), Luna bulk / Terra tiebreak, English voice, no SMS, X only, compact spine, cluster bootstrap unit, receipt as card; each with reversal clause | `docs/DECISIONS.md` | 10 entries, each has Decision/Rationale/Evidence/Reverses-when |
| W1.5 | `docs/RED-TEAM.md`: ≥ 12 numbered attacks on sonar's own claims (scraped sample ≠ Brand24's, sentiment model bias PT vs EN, cluster key wrong, cost hidden in OpenAI, X gap, homonyms, cherry-picked demo brand, replay passed as live, price drift, empty-source inflation of SoV, tiebreak volume, hand-check by author) with pre-committed scoring | `docs/RED-TEAM.md` | ≥ 12 attacks, each with "how we would know" |
| W1.6 | `docs/COVERAGE.md` in Brand24's vocabulary (every Brand24 source and AI feature: covered / partial / not covered / why), `docs/HANDOFF.md` skeleton (spend ledger table, jobs, what not to do), `docs/REPRODUCTION.md` (commands from a fresh clone) | `docs/COVERAGE.md`, `docs/HANDOFF.md`, `docs/REPRODUCTION.md` | COVERAGE has one row per Brand24 source from the price page list |
| W1.7 | `Makefile` (targets as table of contents: `sync validate test typecheck privacy-gate check-placeholders check-claims demo video`), `pyproject.toml` deps (`httpx`, `pydantic>=2`, `openai`, `numpy`, `pytest`, `hypothesis`, `ruff`, `mypy`), `scripts/privacy_gate.py`, `scripts/check_placeholders.py` | `Makefile`, `pyproject.toml`, `scripts/` | `make validate` exits 0 on a docs-only tree |

**Wave 1 gate**: lead reviews W1.1 and W1.2 together, tags `docs-frozen`,
commits. `git log` must show this commit before any `src/` commit.

## Wave 2 — core seams (Sep 3, fan-out 6, all `→ docs-frozen`)

| Id | Task | Owns | → | Done when |
|---|---|---|---|---|
| W2.1 | `models.py`: pydantic v2 frozen records for every CONTRACTS entry, `extra="forbid"`, validators; `tests/test_models.py` round-trips | `src/sonar/models.py`, `tests/test_models.py` | W1.1 | `pytest tests/test_models.py` green; every CONTRACTS record name has a class |
| W2.2 | `config.py`: `SOURCE_PLAN`, `PROFILES`, `LLM` ids (`gpt-5.6-luna` bulk, `gpt-5.6-terra` tiebreak, embedding model), `LLM_RATES` dated, `PROMPT_REV`, `SEED`, `B`, thresholds equal to PRE-REGISTRATION; `report/incumbent.py` constant | `src/sonar/config.py`, `src/sonar/report/incumbent.py` | W1.2 | `python -c "import sonar.config"`; thresholds test placeholder passes |
| W2.3 | Monid client + ledger: `run()` with 202 polling and sync passthrough, 429 backoff, 402 breaker, `list_runs()`, open-before-POST ledger, `reconcile()`; `tests/test_errors.py` with stub httpx transport (429→429→200, 402 halts, deadline, reconcile 500) | `src/sonar/monid/`, `tests/test_errors.py` | W2.1 | `pytest tests/test_errors.py` green; no network in tests |
| W2.4 | LLM seam: `llm/base.py` Protocol (`classify`, `complete_json`, `embed`), `llm/openai_backend.py` (only file importing `openai`, structured parse, usage → cost), `llm/fake.py` replaying fixtures; `tests/test_llm_seam.py` | `src/sonar/llm/`, `tests/test_llm_seam.py` | W2.1, W2.2 | fake passes the same contract tests as the backend's stubbed transport |
| W2.5 | Text layer: `normalize`, `lang` (PT/EN stopword ratio), `match` (word-boundary aliases), `dedup` (native id → url → text key); table-driven tests PT and EN incl. homonym negatives | `src/sonar/text/`, `tests/test_text.py` | W2.1 | `pytest tests/test_text.py` green |
| W2.6 | Provider protocol + registry + `AdapterSchemaError` + `x.py` `available=False` dated; fixture policy doc `tests/fixtures/README.md`; `sonar record` command spec | `src/sonar/providers/base.py`, `providers/registry.py`, `providers/x.py`, `tests/fixtures/README.md` | W2.1 | `python -c "from sonar.providers.registry import PROVIDERS"`; X registered unavailable |

**Wave 2 gate**: `make validate` green; `config.py` and `models.py` frozen.

## Wave 3 — adapters and first live data (Sep 3, fan-out 6, all `→ W2.6, W2.3`)

Each adapter task: `build_input` from the endpoint schema (Appendix
§Endpoints or `docs/monid/inspect/`), `parse` → `Mention`, `cluster_key`,
unit cost, and a test on a recorded fixture plus a mutated-fixture drift test.

| Id | Task | Owns | Done when |
|---|---|---|---|
| W3.1 | Reddit (`trudax/reddit-scraper-lite`, `includeMediaLinks=true`) + News (`tinyfish /search` news, $0; `context.dev` fallback) | `providers/reddit.py`, `providers/news.py`, `tests/test_adapters_reddit_news.py` | tests green on fixtures |
| W3.2 | YouTube videos (`maxResults` always set) + YouTube comments (`startUrls` from videos, `maxComments`) | `providers/youtube.py`, `providers/youtube_comments.py`, `tests/test_adapters_youtube.py` | tests green |
| W3.3 | TikTok (`apidojo/tiktok-scraper`) + Instagram (`apify/instagram-hashtag-scraper`; abstain `no_timestamps` if absent) | `providers/tiktok.py`, `providers/instagram.py`, `tests/test_adapters_short_video.py` | tests green |
| W3.4 | Google Maps reviews (`maxReviews` always set, `reviewsStartDate`) + Facebook reviews | `providers/google_maps.py`, `providers/facebook.py`, `tests/test_adapters_reviews.py` | tests green |
| W3.5 | Trustpilot + G2 from `docs/monid/inspect/` schemas (search → company/product id → reviews) | `providers/trustpilot.py`, `providers/g2.py`, `tests/test_adapters_b2b.py` | tests green |
| W3.6 | ElevenLabs adapter (`/text-to-speech`, `eleven_flash_v2_5`, base64 → mp3 bytes; `voice_id` location per inspect) + `/voices` pick | `providers/elevenlabs.py`, `tests/test_adapter_elevenlabs.py` | test green on fixture |
| W3.7 `$` | Lead, serial after W3.1/W3.4: `sonar record --profile smoke Nubank` live → `tests/fixtures/` (raw payloads, `runs.jsonl`, `v1_runs_page.json`); log spend in HANDOFF | `tests/fixtures/`, `docs/HANDOFF.md` | fixtures committed; reconcile shows every run id; spend ≤ $0.4 |

## Wave 4 — analysis (Sep 4, fan-out 5, all `→ W2.4, W2.5, W3.7`)

| Id | Task | Owns | Done when |
|---|---|---|---|
| W4.1 | Sentiment: frozen prompt + `PROMPT_REV`, batched labeler with cache, lexicons PT/EN, `rules.corroborate` + tiebreak policy (Appendix §Two-signal), 10 % audit sample; exhaustive policy-matrix test; fake counts tiebreak calls | `src/sonar/sentiment/`, `tests/test_rules.py`, `tests/test_labeler.py` | matrix test green; tiebreak invoked exactly when policy says |
| W4.2 | Topics: embed cache, agglomerative cosine clustering (`min_size=3`, `min_breadth=2`), medoids, model naming; golden `topics.json` | `src/sonar/topics/`, `tests/test_topics.py`, `tests/golden/topics.json` | deterministic on fixture embeddings |
| W4.3 | Stats: cluster bootstrap with shared resamples (pattern `assay/scripts/intervals.py`), SoV, sentiment + WoW, events (median+3·MAD ∧ breadth), verdict + Holm, abstention; hypothesis property tests; golden `stats.json` seed 777 | `src/sonar/stats/`, `tests/test_stats.py`, `tests/golden/stats.json` | properties + golden green |
| W4.4 | Report: `build_receipt` (verdict RECONCILED/PARTIAL/REPLAY, totals, comparison vs `$349`), `build_digest`, Markdown render with the receipt table printing zero rows; golden receipt; `sonar verify` semantics | `src/sonar/report/receipt.py`, `digest.py`, `markdown.py`, `tests/test_receipt.py`, `tests/golden/receipt.json` | golden totals hand-summed; unreconciled run listed and contributes 0 |
| W4.5 | Voice: narration via `complete_json` ≤ 900 chars, `numbers_gate` (every number must exist in digest), TTS through the ElevenLabs adapter as a ledger run | `src/sonar/voice/`, `tests/test_voice.py` | gate rejects a planted foreign number |

## Wave 5 — integration (Sep 4–5, fan-out 4 after W5.1)

| Id | Task | Owns | → | Done when |
|---|---|---|---|---|
| W5.1 | `pipeline.py` + `cli.py` (`doctor plan run reconcile spend record render verify`), 6-way fetch, deadlines, abstention wiring, `--trace`, `--no-voice`, `render --from results/demo` with REPLAY banner; `tests/test_cli.py` | `src/sonar/pipeline.py`, `src/sonar/cli.py`, `tests/test_cli.py` | W4.* | offline `sonar run --profile smoke --fixtures` produces all artifacts; bad input exits 2 |
| W5.2 | Chat: `chat/store.py`, `chat/ask.py`, citation + number gates, REPL, `answers.jsonl`; tests pin a fabricated id → `unverified`, empty store → no LLM call | `src/sonar/chat/`, `tests/test_chat.py` | W5.1 | tests green; `sonar ask` works on the fixture session |
| W5.3 | Claude Code skill: `skill/sonar/SKILL.md` (`process.steps` with `spend-approval` human gate, frontmatter per `general/skills-packages/ap-three-way-match`), `scripts/*.py` JSON in/out; `tests/test_skill_driver.py` | `skill/`, `tests/test_skill_driver.py` | W5.1 | driver test green; skill loads in Claude Code |
| W5.4 | Published-claims gate ported from `assay/tests/test_published_claims.py`: cited paths resolve and are in `git ls-files`; `$349` identical across `report/incumbent.py`, README, `results/demo/receipt.json`; suite size = collected; no TBD; narration numbers ⊂ demo results; PRE-REG thresholds = config; model ids dated in DECISIONS; `make check-claims` | `tests/test_published_claims.py`, `Makefile` (check-claims target) | W5.1 | gate green (skips demo checks until W6) |
| W5.5 `$` | Lead: `sonar run --profile lite Nubank --vs Inter` live; first real digest with intervals; Avenza empty run; one 20-char ElevenLabs call to measure the unit (DECISIONS entry with run id); spend logged | `docs/HANDOFF.md`, `docs/DECISIONS.md` | W5.1, W4.5 | both receipts `RECONCILED`; cumulative Monid spend ≤ $2 |

## Wave 6 — freeze the demo (Sep 6 AM, serial, lead, `$`)

| Id | Task | Owns | → | Done when |
|---|---|---|---|---|
| W6.1 `$` | `sonar run --profile full <brand> --vs <3 competitors> --resamples 10000` → `results/demo/` (receipt, digest, stats, topics, mentions with author hashes only, mp3); Avenza empty receipt → `results/demo-empty/` | `results/demo/`, `results/demo-empty/` | W5.* | `sonar verify results/demo/receipt.json` exits 0 with `RECONCILED`; `make check-claims` green incl. demo checks |
| W6.2 | README results section, COVERAGE and HANDOFF updated from the frozen numbers; DECISIONS entry freezing demo | `README.md`, `docs/COVERAGE.md`, `docs/HANDOFF.md`, `docs/DECISIONS.md` | W6.1 | `make validate` green |
| W6.3 | Start 50-label blind hand check (Caio, rationale hidden), sheet under `results/handcheck/` | `results/handcheck/` | W6.1 | 50 rows drawn, seed logged |

## Wave 7 — video and post (Sep 6 PM – Sep 8, fan-out 5 after W7.1)

| Id | Task | Owns | → | Done when |
|---|---|---|---|---|
| W7.1 | Copy `assay/video/` scaffold file-by-file (new commits), point `manifest.ts` at `../results/demo/*.json`, `video/README.md` shot list: 0–5 s "$349 a month. Replaced for $0.xx. Here is the receipt.", price vs receipt side by side, live `POST /v1/run` trace, `ask` with citations, Avenza empty run, `#monid` outro | `video/` (scaffold, README, manifest) | W6.1 | `pnpm lint` in `video/` green; storyboard has 6 beats with timings ≤ 90 s |
| W7.2 | `video/src/data/narration.json` ≤ 200 words, every number from `results/demo`; ElevenLabs narration mp3 via sonar's own TTS path (one more ledger run, in the receipt) | `video/src/data/narration.json`, `video/public/narration.mp3` | W7.1 | claims gate narration check green |
| W7.3 | Record casts with `video/capture/`: `sonar doctor`, `sonar run --profile lite --trace` on the demo brand, receipt scroll, `sonar ask`, Avenza empty | `video/capture/`, `video/public/casts/` | W7.1, W5.5 | five cast files present, each ≤ 40 s at 1.5–2× |
| W7.4 | Scenes: price-vs-receipt, live-trace, ask, edge-cases, outro (one worker per two scenes, disjoint files under `video/src/scenes/`) | `video/src/scenes/` | W7.1, W7.2, W7.3 | `remotion render` produces a 1080p file |
| W7.5 | Cut to ≤ 90 s, captions burned in (auto-caption then hand-fix), phone review, export 1080p; receipt card PNG via satori (pattern `cv-related/cv`); X post text (one-line hook, `#monid` in tweet body, native upload) | `video/out/`, `results/social/` | W7.4 | `ffprobe` duration ≤ 90 s, 1920×1080; captions visible muted |
| W7.6 | Finish hand check; publish H5 in README and PRE-REG results block; DECISIONS entry | `results/handcheck/`, `README.md`, `docs/PRE-REGISTRATION.md` (results section only) | W6.3 | agreement number in README with n=50 |

## Wave 8 — ship (Sep 9–10, serial, lead)

| Id | Task | → | Done when |
|---|---|---|---|
| W8.1 | Fresh-clone reproduction per `docs/REPRODUCTION.md` in a temp dir; `make validate`; `git ls-files` check for every path the docs cite | W7.5 | `make validate` green from the clone |
| W8.2 `$` | Rehearsal: `sonar run --profile lite <never-used brand>` live as a judge would; fix only what breaks; confirm wallet reserve ≥ $1.5 | W8.1 | receipt `RECONCILED`; spend ledger total ≤ $8.5 |
| W8.3 | Repo public on `github.com/caiotheodoro/sonar`; README links; video hosted (HF dataset or GitHub release asset, as assay did) | W8.1 | URLs resolve unauthenticated |
| W8.4 | Post on X: native video, hook line, `#monid` in the tweet text; register the URL on the hackathon form within 24 h | W8.3, W7.5 | post live; registration confirmation |
| W8.5 | Submission form: one sentence (product, price, workflow replaced), endpoints in order with unique capabilities, real measured cost incl. failed runs (from `results/demo/receipt.json`), repo + post URLs; submit before Sep 10 23:59 ET; no code changes after | W8.4 | form submitted; `git log` last commit is docs |

## Critical path and parallelism

```
W0.2 → W1.{1..7} ─gate─→ W2.{1..6} ─gate─→ W3.{1..6} → W3.7$ → W4.{1..5} → W5.1 → W5.{2,3,4} → W5.5$ → W6.1$ → W7.1 → W7.{2,3} → W7.4 → W7.5 → W8.1 → W8.2$ → W8.3 → W8.4 → W8.5
W0.1, W0.3, W0.4 run beside Wave 1.  W6.3 → W7.6 runs beside Wave 7.
```

Widest fan-outs: Wave 1 (7), Wave 2 (6), Wave 3 (6), Wave 4 (5), Wave 7
(5). Serial chokepoints are all `$` tasks or gates, by design.

## Budget ledger (planned)

| Item | Est. |
|---|---|
| W3.7 smoke fixtures | $0.4 |
| W5.5 lite + Avenza + TTS probe | $1.3 |
| W6.1 full demo + empty | $2.8 |
| W7.2 narration TTS | $0.1 |
| W8.2 rehearsal lite | $0.8 |
| Reserve for judging | $1.5 |
| **Monid total** | **≈ $6.9 of $10** |
| OpenAI (Luna bulk, Terra tiebreak ≤ 40 %, embeddings) | ≈ $1–2, separate receipt line |

## Verification of the whole

- `make validate` green at every merge from Wave 1 on.
- `sonar verify results/demo/receipt.json` exits 0 with `RECONCILED`.
- Fresh clone reproduces `results/demo/stats.json` at seed 777 offline.
- Video ≤ 90 s, 1080p, captions, `#monid`, receipt beside `$349` on screen.
- Every `$` task has a HANDOFF ledger row with run ids.

## Open items flagged for Caio

- Confirm Luna bulk / Terra tiebreak (pricing reverses the phrasing used).
- Pick the demo brand and three competitors before W3.7.
- W0.1 is a human wizard; nothing live runs before it.

---

# Appendix — design reference

## Module layout (`src/sonar/`, pydantic v2, argparse, httpx, openai, numpy)

| Path | Responsibility |
|---|---|
| `cli.py` | `sonar doctor\|plan\|run\|ask\|reconcile\|spend\|record\|render\|verify`; `Query` validation exits 2 before any client exists |
| `models.py` | every CONTRACTS record |
| `config.py` | `SOURCE_PLAN`, `PROFILES`, `LLM = {classifier_model, tiebreak_model, embedding_model}` (env-overridable), `LLM_RATES` dated, `PROMPT_REV`, `SEED=777`, `B=2000`, thresholds |
| `monid/client.py`, `monid/ledger.py` | run/poll/list; open-before-POST ledger; reconcile |
| `providers/*` | one adapter per endpoint; the only place a schema appears |
| `text/*` | normalize, lang, match, dedup |
| `llm/base.py`, `llm/openai_backend.py`, `llm/fake.py` | the seam; only backend imports `openai`; fake for tests |
| `sentiment/*` | prompt, labeler + cache, rules + tiebreak policy, lexicons |
| `topics/*` | embed, cluster (code), name (model) |
| `stats/*` | bootstrap, sov, sentiment, events, verdict |
| `chat/*` | store, ask, gates, REPL |
| `report/*` | incumbent constant, receipt, digest, markdown |
| `voice/*` | script + number gate, tts |
| `pipeline.py` | orchestration |
| `skill/sonar/` | Claude Code skill |
| `video/` | Remotion from assay |
| `results/demo/`, `results/incumbent/` | frozen artifacts, price evidence |

## Contracts

- **Query**: brand, brand_aliases, brand_hint, competitors (0–3), window_days=14, profile smoke|lite|full, sources. Validators: 2–64 chars, not punctuation-only, distinct.
- **Mention**: `mention_id` sha256(source, native_id | url | text_key)[:24]; brand; source ∈ {reddit, youtube, youtube_comment, tiktok, instagram, google_maps, facebook, trustpilot, g2, news}; run_id; native_id; url; author_hash; text; lang ∈ {pt,en,other,unknown}; published_at; engagement; rating (1–5 review sources); cluster_key (reddit: post id; youtube_comment: video id; tiktok/instagram: author_hash; reviews/news/youtube video: mention_id); matched_terms; raw_ref.
- **Label**: mention_id; label ∈ {positive, negative, neutral, irrelevant}; about_brand; confidence; rationale ≤ 20 words; topic_id; signals {classifier{model, label, confidence, status}, tiebreak{…}|null, deterministic{kind rating|lexicon|none, label}}; corroboration ∈ {confirmed, model_only, contested, irrelevant}; decided_by ∈ {classifier, tiebreak}; prompt_rev; status ∈ {ok, refused, unparseable, error, cached}; usage {tokens, cost_usd}.
- **RunRecord**: local_seq; run_id|null; provider; endpoint; brand; source; input_digest; submitted_at; completed_at; status (Monid status or `LOCAL_REJECTED_<http>` / `LOCAL_BACKOFF_EXHAUSTED` / `LOCAL_DEADLINE`); provider_http_status; n_results (0 is a value); estimate_usd; cost_usd (only from `/v1/runs`); billed_units; cost_source ∈ {"/v1/runs", "unreconciled"}; attempts; error.
- **Topic**: topic_id, brand, name ≤ 6 words, n, n_clusters, share, net, ci95, exemplar_mention_ids (3 medoids), method {embedding_model, linkage, threshold, min_size 3, min_breadth 2}.
- **Receipt** (the card): schema_rev, sonar_rev, session_id, timestamps, replay; **verdict RECONCILED | PARTIAL | REPLAY** (RECONCILED iff every run has cost_source="/v1/runs" and unmatched_remote empty); query; runs (all, incl. run_id=null and n_results=0); totals {monid_usd, monid_runs, monid_runs_billed, monid_runs_zero_results, monid_runs_failed, llm_usd, llm_calls by kind, llm_tokens, elevenlabs_usd, total_usd}; reconciliation {fetched_at, n_listed_in_window, unmatched_remote_run_ids, unreconciled_local_seqs}; incumbent {name, price_usd_month 349, url, checked_at, mentions_quota 10000}; comparison {briefs_per_month_assumed 4, sonar_usd_month_equiv, ratio, mentions_this_brief}; mentions {fetched, deduped, labelled, excluded_with_reason, by_source, by_brand}; abstentions; what_could_not_be_checked; content_digest. `sonar verify` exits nonzero unless RECONCILED.
- **Digest**: brand, competitors, window {current, previous}, share_of_voice [{brand, n, n_clusters, share, ci95, basis_sources}], sentiment [{brand, n, n_confirmed, pos, neg, neu, net, ci95, ci95_iid, design_effect, wow {delta, ci95, ci95_confirmed_only, verdict}}], by_source, topics, events [{brand, date, n, n_clusters, baseline_median, label, exhibit_url}], top_mentions (quotes ≤ 240 chars, original language), abstentions, coverage_gaps, cost (quoted from Receipt), narration.
- **Answer**: session_id, brand, question, answer, citations (all verified mention ids), numbers_verified, retrieved, model, usage, status ∈ {ok, unverified, refused}.

## Pipeline rules

- Caps per brand (`full`): reddit 40 (+$0.02), youtube 10 + 60 comments, tiktok 40, instagram 30, google_maps 50, facebook 30, trustpilot/g2 1 call each, news via TinyFish $0 up to 3 pages. ≈ $0.7/brand → ≈ $2.8 for brand + 3. `lite` halves caps, ≤ 1 competitor (≈ $0.75); `smoke` = reddit + maps, 1 brand (≈ $0.3). Always set `maxResults` (YouTube) and `maxReviews` (Maps).
- Dedup: (source, native_id) → normalized url → text_key. Mention matching brand and competitor kept once per brand; SoV counts mention–brand pairs and says so.
- Language detected in code, reported as stratum, never filtered; outputs English, quotes verbatim.
- **Two-signal policy** (code decides): relevance = `about_brand ∧ matched_terms`. Deterministic signal = rating bucket (≤2 neg / 3 neu / ≥4 pos) for review sources, lexicon sign otherwise. Classifier agrees → `confirmed`; disagrees, or no deterministic signal with confidence < 0.6 → tiebreak call; tiebreak agrees with classifier → `confirmed`; disagrees → tiebreak wins, `contested`, `decided_by=tiebreak`; no deterministic signal and confidence ≥ 0.6 → `model_only`. Fixed 10 % audit sample (seed 777) always tiebroken for H3. Tiebreak capped at 40 % of mentions per brand.
- Topics: embeddings cached; average-linkage agglomerative on cosine, `min_size=3`, `min_breadth=2` distinct cluster keys; medoids named by model.
- Chat: `sonar ask <brand> "q" [--session]`; top-20 by cosine + stats summary + topic table; citations must exist (strip, re-ask once, then `unverified`); numbers must occur in stats/topics/retrieved; refusal → `refused`; usage appended to session receipt via `reconcile`.
- Voice: ≤ 900 chars English from Digest JSON; number gate; one ElevenLabs Monid run in the ledger.

## Statistics (PRE-REGISTRATION)

- Cluster bootstrap over `cluster_key`, percentile 95 %, B=2000 (10000 frozen demo), seed 777, shared resample indices (paired deltas). iid CI beside, `design_effect = (cluster width / iid width)²`.
- share = n_b / Σn over `basis_sources`; net = (pos − neg)/(pos + neg + neu); WoW split at now − 7 d.
- Verdicts: SIGNIFICANT iff full-set and confirmed-only CIs both exclude 0 same sign; SUGGESTIVE iff only full-set; NO_CHANGE_DETECTED iff CI includes 0 with minimums; else ABSTAIN. Holm α=0.05 over brands × {net, share}.
- Abstain reasons: empty, provider_failed, rate_limited, deadline, unavailable, schema_drift, no_timestamps; brand-level at n_clusters < 5 or n < 20 in either week; abstained source leaves basis_sources for every brand.
- Events: n_day ≥ max(5, median + 3·MAD) ∧ n_clusters_day ≥ 3.
- H1 brand+3 brief < $5 all-in; H2 design effect ≥ 1.5 on comment sources; H3 classifier–tiebreak agreement on audit sample ≥ 0.85; H4 zero-mention brand still costs > $0; H5 50-label blind hand check ≥ 0.85, published either way.

## Error matrix

| Condition | Behaviour | Exit |
|---|---|---|
| Bad brand / >3 competitors / duplicates | validator, no client | 2 |
| Zero mentions (Avenza) | all abstain, narration "no signal; cost $x", receipt lists runs | 0 |
| Monid 429 | Retry-After else 2/4/8/16 ×4, then `rate_limited` | 0 |
| Monid 402 | breaker, stats on what exists, `halted` | 3 |
| TIMED_OUT / deadline | abstain, never resubmit | 0 |
| FAILED/BLOCKED/STOPPED / provider 4xx-5xx | abstain `provider_failed`, cost as reconciled | 0 |
| Endpoint absent (X) | `unavailable`, coverage_gaps | 0 |
| Payload drift | `AdapterSchemaError`, raw saved, `schema_drift` | 0 |
| OpenAI limit / refusal / unparseable | SDK retries ×4, then excluded with reason; tiebreak failure keeps classifier label as `model_only` | 0 |
| Embedding failure | topics abstain; chat lexical fallback, stated | 0 |
| Chat unknown id / unverifiable number | strip, re-ask once, `unverified` | 0 |
| ElevenLabs fails | no mp3, rest complete | 0 |
| `GET /v1/runs` fails | receipt PARTIAL, `reconcile --session` reruns | 4 |

## Endpoint reference (Monid ids and prices verified 2026-09-02; field schemas upstream)

| Source | Endpoint | Price | Input | Output |
|---|---|---|---|---|
| Reddit | `apify /trudax/reddit-scraper-lite` | 0.0057/result + 0.02 | `searches[]`, `sort=new`, `time=week`, `maxItems`, `maxPostCount`, `maxComments`, `postDateLimit`, `includeMediaLinks=true` | `dataType`, `body`, `title`, `createdAt`, `upVotes`, `communityName`, `url` |
| YouTube | `apify /streamers/youtube-scraper` | 0.0045/result | `searchQueries[]`, `maxResults`, `dateFilter`, `sortingOrder` | `id,title,url,viewCount,date,likes,channelName,commentsCount,text` |
| YouTube comments | `apify /streamers/youtube-comments-scraper` | 0.00225/result | `startUrls[]`, `maxComments`, `sortCommentsBy` | `comment,author,videoId,voteCount,replyCount` (no timestamp) |
| TikTok | `apify /apidojo/tiktok-scraper` | 0.00045/result | `keywords[]`, `maxItems`, `dateRange`, `sortType` | `title,views,likes,comments,shares,hashtags,uploadedAtFormatted,channel` |
| Instagram | `apify /apify/instagram-hashtag-scraper` 0.00345/call or `/apify/instagram-api-scraper` 0.003/result + 0.001 | | (search-scraper is entity search; do not use) | |
| Google Maps | `apify /compass/google-maps-reviews-scraper` | 0.000675/result | `startUrls[]`/`placeIds[]`, `maxReviews`, `reviewsSort=newest`, `reviewsStartDate`, `language` | `text,publishedAtDate,stars,likesCount,reviewId,name,responseFromOwnerText,placeId,title,totalScore` |
| Facebook | `apify /apify/facebook-reviews-scraper` | 0.003/result + 0.001 | `startUrls[]`, `resultsLimit`, `onlyReviewsNewerThan` | `text,date,isRecommended,likesCount,pageName` |
| Trustpilot | `/get_company_reviews` 0.03, `/get_company_review_summary` 0.05, `/search_companies` 0.03 | per call | via `monid inspect` (W0.3) | |
| G2 | `/get_product_reviews` 0.05, `/search_software` 0.02 | per call | via `monid inspect` (W0.3) | |
| News | `tinyfish /search` $0 sync | | `input.queryParams{query, domain_type=news, recency_minutes|after_date, language, page≤10}` | `results[{title,snippet,url,date,site_name}]` |
| Page text | `tinyfish /fetch` $0 sync | | `input{urls[]≤10, format=markdown}` | `results[{url,title,text,published_date}]` |
| Voice | `elevenlabs /text-to-speech` | `eleven_flash_v2_5` $0.05/1k chars | `text`, `model_id`, `voice_settings`; `voice_id` location per inspect | MP3 (base64 likely) |

Monid API: `POST https://api.monid.ai/v1/run` Bearer `monid_live_…`, body `{provider, endpoint, input}`; Apify async (202 + runId, poll `GET /v1/runs/:id`); `GET /v1/runs` items carry `runId, status, providerResponse.httpStatus, price, cost{value,currency}, billedUnits`, limit ≤100, cursor; provider errors cost 0. No SDK; CLI `@monid-ai/cli` v0.1.7. No X/Twitter endpoint today.

## Hackathon rules that bind tasks

Sep 1–10 23:59 ET; commits inside window; score 850 = judges 400 (real kill / past tutorial / video / would adopt) + reach 250 (+50 per platform; X only chosen) + viral 200; mandatory live data, edge cases, measured cost incl. failed runs, video 60–90 s captioned 1080p with incumbent price vs measured cost side by side, Monid call visible, `#monid` in tweet body, URL registered within 24 h. Brand24 Team $349/mo (brand24.com/prices, 2026-09-02). OpenAI ids: `gpt-5.6-luna` $0.20/$1.20, `gpt-5.6-terra` $2/$12 per MTok.

## Reused from Caio's repos

`assay/video/` Remotion pipeline + `capture/` + `VOICE-SCRIPT.md`; `assay/scripts/intervals.py`; `assay/tests/test_published_claims.py`; vernier spine, `models.py`, card emitter; avenza `vertical-skills` escalation gate and `skills-packages` SKILL.md frontmatter; `cv-related/cv` satori receipt card.
