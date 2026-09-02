# CONTRACTS — sonar record schemas

`schema_rev: 1.1.2`. Source of truth: `docs/research/2026-09-02-task-graph-and-design.md`,
Appendix §Contracts, §Pipeline rules, §Statistics, §Error matrix, as amended
by `docs/DECISIONS.md` D012 (review
`docs/research/reviews/2026-09-02-contracts-review.md`), D013 (review
`docs/research/reviews/2026-09-02-contracts-review-2.md`) and D014 (relevance
by context, first live smoke run). This file is frozen
at the Wave 1 gate (`docs-frozen` tag). Any later change goes through a
`docs/DECISIONS.md` entry by the wave lead, bumps `schema_rev`, and is listed
in §Changelog.

`src/sonar/models.py` (W2.1) implements every record below as a pydantic v2
frozen model with `extra="forbid"`. Field names here are the wire names: JSON
artifacts under `results/`, `runs.jsonl`, `answers.jsonl` and the receipt card
all use them unchanged.

## Notation

| Written | Meaning |
|---|---|
| `str`, `int`, `float`, `bool` | JSON string, integer, number, boolean |
| `datetime` | ISO 8601 string, UTC, second precision, `Z` suffix |
| `date` | ISO 8601 calendar date string, UTC |
| `T \| None` | field always present; JSON `null` allowed |
| `list[T]` | JSON array; empty array allowed unless a length is stated |
| `dict[K, V]` | JSON object with keys of type K |
| `CI95` | two-element array `[lo, hi]` of `float`, percentile 95 % bootstrap |
| `Literal[a, b]` | closed enum; any other value is a validation error |
| `= x` | default when the field is omitted on input |

Money is `float` USD with the precision the upstream returns; never rounded
before the Markdown layer. Hashes are lowercase hex.

## Enumerations

### Source enum

`Source = Literal["reddit", "youtube", "youtube_comment", "tiktok", "instagram", "google_maps", "facebook", "trustpilot", "g2", "news"]`

Exactly ten values. `x` is not a member: X/Twitter has no Monid endpoint
(verified 2026-09-02), is registered `available=False` in
`providers/x.py`, and appears only in `Digest.coverage_gaps`. The ElevenLabs
text-to-speech run is a Monid run, not a source; its `RunRecord.source` is
`null`.

Review sources (carry a `rating`): `google_maps`, `facebook`, `trustpilot`,
`g2`. Comment sources (cluster bootstrap expected to show design effect,
H2): `reddit`, `youtube_comment`, `tiktok`, `instagram`. H2 is scored on the
two thread-clustered comment sources, `reddit` and `youtube_comment`, from
`BySourceEntry.design_effect` on each entry that meets the H2 minimums
(`n_clusters ≥ 5` and `n ≥ 20` on the `BySourceEntry` over the full window,
D013 N3); the author-clustered sources `tiktok` and `instagram` are
reported, not scored (D012 F3).

### Other closed enums

| Name | Values | Used by |
|---|---|---|
| `Profile` | `smoke`, `lite`, `full` | Query |
| `Lang` | `pt`, `en`, `other`, `unknown` | Mention |
| `MatchKind` | `text`, `inherited`, `entity` | Mention |
| `SentimentLabel` | `positive`, `negative`, `neutral`, `irrelevant` | Label |
| `Polarity` | `positive`, `negative`, `neutral` | Label.signals.deterministic |
| `Corroboration` | `confirmed`, `model_only`, `contested`, `irrelevant` | Label |
| `DecidedBy` | `classifier`, `tiebreak` | Label |
| `LabelStatus` | `ok`, `refused`, `unparseable`, `error`, `cached` | Label, Label.signals.* |
| `SignalKind` | `rating`, `lexicon`, `none` | Label.signals.deterministic |
| `CostSource` | `/v1/runs`, `unreconciled`, `local` | RunRecord |
| `Verdict` | `RECONCILED`, `PARTIAL`, `REPLAY` | Receipt |
| `WowVerdict` | `SIGNIFICANT`, `SUGGESTIVE`, `NO_CHANGE_DETECTED`, `ABSTAIN` | Digest |
| `AnswerStatus` | `ok`, `unverified`, `refused` | Answer |
| `LlmKind` | `classify`, `tiebreak`, `embed`, `name_topic`, `narrate`, `ask` | Receipt.totals.llm_calls |
| `AbstainReason` | see below | Receipt, Digest |
| `AbstainScope` | `source`, `brand`, `topics`, `voice`, `session` | Receipt, Digest |

`AbstainReason` values (PRE-REGISTRATION v1.1.1 §Abstain reasons, identical
list): `empty`, `provider_failed`, `rate_limited`, `deadline`, `unavailable`,
`schema_drift`, `below_minimum` (brand-level, `n_clusters < 5` or `n < 20` in
either period; see §Digest for which `n`), `halted` (Monid 402 breaker),
`embedding_failed` (topics only; chat falls back to lexical retrieval and
says so), `signals_conflict` (verdict only; full-set and confirmed-only CIs
exclude 0 with opposite signs), `degenerate` (minimums met but one estimate
is undefined: `design_effect` when the iid CI width is 0, or
`ci95_confirmed_only` when `n_confirmed = 0`; D013 N4). `no_timestamps` is
**not** an abstention (D012 F2): a source every one of whose items lacks
`published_at` keeps counting for share and is flagged `wow_scope=false` on
its `BySourceEntry`, excluded from `wow` and `events`, and listed under
`what_could_not_be_checked`; in a source with mixed timestamps the items
lacking one are dropped from `wow` and `events` one by one and the source
keeps `wow_scope=true` (D013 A1).

## Query

Input record. Validated in `cli.py` before any client exists; a validation
error exits 2.

| Field | Type | Rule |
|---|---|---|
| `brand` | `str` | 2–64 chars after whitespace trim; not punctuation-only |
| `brand_aliases` | `list[str] = []` | each 2–64 chars, not punctuation-only, distinct from `brand` and each other (case-insensitive after `text.normalize`) |
| `brand_hint` | `str \| None = null` | free text for the classifier prompt to resolve homonyms (e.g. "Brazilian digital bank"); ≤ 120 chars |
| `competitors` | `list[str] = []` | length 0–3 (`profile=lite`: 0–1); each 2–64 chars, not punctuation-only, distinct from `brand`, aliases, and each other |
| `window_days` | `int = 14` | fixed at 14 in v1 (validator: `== 14`); the fetch window ends at run start and is split into two 7-day periods (§Digest `window`) |
| `profile` | `Profile = "full"` | selects caps from `config.SOURCE_PLAN` and `config.PROFILES` |
| `sources` | `list[Source]` | default = the profile's source list from `config.SOURCE_PLAN`; explicit values must be members of `Source`; distinct; `smoke` allows only `reddit` and `google_maps` |

Validators run in this order: length and punctuation per term, then
distinctness across `brand`, `brand_aliases`, `competitors`, then
`competitors` count (profile-aware: `lite` allows at most one competitor,
exit 2), then `window_days == 14`, then `sources` membership. The first
failure is reported;
`sonar plan` prints the validated Query and the estimate without spending.

## Mention

One fetched item attributed to one brand. Primary key of a row is
`(mention_id, brand)`: a text that matches both the brand and a competitor
is stored once per brand with the same `mention_id` (Pipeline rule: "kept
once per brand; SoV counts mention–brand pairs and says so").

| Field | Type | Rule |
|---|---|---|
| `mention_id` | `str` | 24 hex chars; see §mention_id rule |
| `brand` | `str` | the Query `brand` or one `competitors` entry this row is attributed to (canonical spelling from the Query, not the alias) |
| `source` | `Source` | |
| `run_id` | `str \| None` | Monid `runId` of the run that returned this item; `null` when the run returned no id (`$0` sync endpoints, OQ-2). `raw_ref` is the durable back-reference, via `local_seq` |
| `native_id` | `str \| None` | provider's own id (reddit post/comment id, YouTube video id, Maps `reviewId`, …); `null` when the payload has none |
| `url` | `str \| None` | canonical URL after `text.normalize_url` (scheme lowercased, tracking params stripped, trailing slash removed); `null` when absent |
| `author_hash` | `str \| None` | first 16 hex of sha256 over `"{source}\n{author handle as returned}"`; the raw handle is never stored; `null` when the payload has no author |
| `text` | `str` | verbatim, original language; for post-shaped items title and body joined by `"\n\n"`; ≥ 1 char after trim |
| `lang` | `Lang` | detected in code by PT/EN stop-word ratio; reported as a stratum, never used to filter |
| `published_at` | `datetime \| None` | from the payload; `null` when the endpoint carries no timestamp (YouTube comments; Instagram hashtag items without one) |
| `engagement` | `dict[str, int]` | keys ⊂ {`upvotes`, `likes`, `comments`, `shares`, `views`, `replies`, `votes`}; absent keys omitted, never `null` values; `{}` allowed |
| `rating` | `int \| None` | 1–5, review sources only; `null` for every other source |
| `cluster_key` | `str` | see §cluster_key rules |
| `matched_terms` | `list[str]` | normalized brand or alias terms the item is attributed by; ≥ 1 entry (a Mention with no match is never emitted). How they were found is `match_kind` (D014) |
| `match_kind` | `MatchKind` | `text`: terms found by word-boundary match in `text`; `inherited`: a comment whose text matched nothing carries its parent post's `matched_terms`, the post being in the same payload and itself a `text` match, and the post's `native_id` is the comment's `cluster_key`; `entity`: a review fetched from an entity the adapter resolved to the brand (Google Maps place, Facebook page, Trustpilot domain, G2 slug) carries `[normalized brand]` whether or not the text names it. Default `text`. `about_brand` stays required for relevance in every kind (D014) |
| `raw_ref` | `str` | `"{local_seq}#{index}"`: the ledger row that saved the raw payload and the zero-based item index inside it |

## Label

One sentiment decision per Mention row, produced by the two-signal policy
(Pipeline rules §Two-signal). Primary key `(mention_id, brand)` matches
Mention; `brand` is carried in the joined output, not in the Label record.

| Field | Type | Rule |
|---|---|---|
| `mention_id` | `str` | foreign key to Mention |
| `label` | `SentimentLabel` | final label after policy |
| `about_brand` | `bool` | classifier's relevance judgement; relevance for stats = `about_brand ∧ matched_terms non-empty` |
| `confidence` | `float` | 0.0–1.0; confidence of the signal named in `decided_by` |
| `rationale` | `str` | ≤ 20 words, English, from the deciding model call; hidden during the H5 blind hand check |
| `topic_id` | `str \| None` | assigned by `topics/`; `null` before clustering or when the mention is in no cluster of `min_size` |
| `signals` | `Signals` | see below |
| `corroboration` | `Corroboration` | assigned by the precedence in §Two-signal policy below: `confirmed`: classifier agrees with a non-null deterministic signal (a tiebreak never overrides this), or a tiebreak triggered by disagreement or low confidence agrees with the classifier; `contested`: such a tiebreak disagreed with the classifier and won; `model_only`: no tiebreak adopted and not `confirmed`: a null deterministic signal with classifier confidence ≥ 0.6, a failed tiebreak call, or `signals.overflow=true` (D013 N5); `irrelevant`: `about_brand=false` or `label=irrelevant` |
| `decided_by` | `DecidedBy` | `tiebreak` iff the tiebreak call ran and its label was adopted |
| `prompt_rev` | `str` | `config.PROMPT_REV` used for the classifier call |
| `status` | `LabelStatus` | `cached` when served from the label cache keyed by `(mention_id, prompt_rev, classifier model)`; `refused`, `unparseable`, `error` after 4 SDK retries exclude the mention with that reason |
| `usage` | `Usage` | `{tokens: int, cost_usd: float}`; sum over the classifier and tiebreak calls for this mention; `{0, 0.0}` when `cached` |

`Signals`:

| Field | Type | Rule |
|---|---|---|
| `classifier` | `ModelSignal` | `{model: str, label: SentimentLabel, confidence: float, status: LabelStatus}` |
| `tiebreak` | `ModelSignal \| None` | same shape; `null` when the policy did not call the tiebreak model |
| `deterministic` | `DeterministicSignal` | `{kind: SignalKind, label: Polarity \| None}`; `kind=rating` for review sources (≤ 2 → negative, 3 → neutral, ≥ 4 → positive), `kind=lexicon` otherwise (sign of PT/EN lexicon score; `label=null` when the score is 0), `kind=none` with `label=null` when no rating and no lexicon hit |
| `overflow` | `bool` | `true` iff the mention met tiebreak trigger (a) or (b) but the 40 % cap was already reached; the classifier label stands, `corroboration=model_only`, and the row is excluded from the confirmed-only subset |

### Two-signal policy

Tiebreak is invoked iff (a) classifier disagrees with a non-null
deterministic label, or (b) deterministic label is `null` and classifier
confidence < 0.6, or (c) the mention is in the fixed 10 % audit sample
(seed 777), subject to the cap of 40 % of mentions per brand (audit sample
first, then cases in `published_at` order). Denominator for the 10 % sample
and the 40 % cap: relevant mention–brand rows after §Dedup precedence, per
brand, per session; a mention kept for two brands is two rows and may be
sampled in each (D012 F17).

Precedence (D012 F9, F10):

1. Classifier agrees with a non-null deterministic signal → `confirmed`,
   `decided_by=classifier`. No tiebreak result overrides it; an audit-sample
   tiebreak on such a mention is recorded in `signals.tiebreak` and counted in
   `Receipt.audit` (H3) only.
2. A tiebreak triggered by (a) or (b) wins when it disagrees with the
   classifier (`contested`, `decided_by=tiebreak`, `label` = tiebreak label)
   and confirms when it agrees (`confirmed`, `decided_by=classifier`).
3. A mention that met (a) or (b) but hit the 40 % cap keeps the classifier
   label: `model_only`, `signals.overflow=true`, `decided_by=classifier`,
   excluded from the confirmed-only subset and counted in
   `Receipt.audit.tiebreak_overflow`.
4. A tiebreak triggered by (c) alone (audit sample; null deterministic
   signal; classifier confidence ≥ 0.6) is never adopted, whether or not it
   agrees: `model_only`, `decided_by=classifier`, recorded in
   `signals.tiebreak` and counted in `Receipt.audit` (H3) only (D013 A2).

`tests/test_rules.py` enumerates this matrix exhaustively.

## RunRecord

One row of the ledger (`runs.jsonl`), written **before** `POST /v1/run`
and updated in place by `local_seq`. Every Monid call, including the
ElevenLabs voice run and calls that never received a run id, has a row.

| Field | Type | Rule |
|---|---|---|
| `local_seq` | `int` | 1-based, monotonic within a session, assigned before the POST |
| `run_id` | `str \| None` | Monid `runId`; `null` when the POST was rejected locally or by HTTP before a run id existed |
| `provider` | `str` | Monid provider id (`apify`, `tinyfish`, `trustpilot`, `g2`, `elevenlabs`) |
| `endpoint` | `str` | Monid endpoint path exactly as sent (e.g. `/trudax/reddit-scraper-lite`, `/text-to-speech`) |
| `brand` | `str \| None` | brand the run was fetched for; `null` for the voice run |
| `source` | `Source \| None` | `null` for the voice run |
| `input_digest` | `str` | first 24 hex of sha256 over canonical JSON of the request `input` (sorted keys, `,`/`:` separators, UTF-8) |
| `submitted_at` | `datetime` | just before the POST |
| `completed_at` | `datetime \| None` | when a terminal status was observed; `null` while pending or after a deadline |
| `status` | `str` | Monid status string verbatim (observed in the design: `TIMED_OUT`, `FAILED`, `BLOCKED`, `STOPPED`, plus the running and succeeded states), or one of the local statuses `LOCAL_REJECTED_<http>` (e.g. `LOCAL_REJECTED_402`), `LOCAL_BACKOFF_EXHAUSTED`, `LOCAL_DEADLINE`. Local statuses always have `run_id=null` except `LOCAL_DEADLINE`, which keeps the id and is never resubmitted |
| `provider_http_status` | `int \| None` | `providerResponse.httpStatus` from Monid; `null` when unknown |
| `n_results` | `int \| None` | number of parsed items; `0` is a value and is billed; `null` only while the run is not terminal |
| `estimate_usd` | `float` | computed at submit time from the endpoint price table in `config` and the requested caps |
| `cost_usd` | `float \| None` | billed cost from `GET /v1/runs` `cost.value` only; `null` until reconciled; never copied from the estimate |
| `billed_units` | `int \| None` | `billedUnits` from `GET /v1/runs`; `null` until reconciled |
| `cost_source` | `CostSource` | `/v1/runs` once `cost_usd` was filled from the listing; `local` for `run_id=null` rows (every `LOCAL_*` status except `LOCAL_DEADLINE`, and a succeeded `$0` sync run that returned no id, OQ-2), reconciled by construction with `cost_usd=0.0` at write time; `LOCAL_DEADLINE` keeps its `run_id` and is `unreconciled` until the listing shows it; `unreconciled` for rows with a `run_id` not yet matched in the listing |
| `attempts` | `int` | POST attempts incl. 429 retries; ≥ 1 |
| `error` | `str \| None` | last error text (HTTP body excerpt ≤ 500 chars, or local reason); `null` on success |

Totals in the Receipt sum `cost_usd` over rows with `cost_source="/v1/runs"`
only; a `local` row carries `cost_usd=0.0` and is counted in
`monid_runs_failed` iff its `status` starts with `LOCAL_` (a succeeded
`run_id=null` sync run is `local` and not failed; D013 N6); an `unreconciled` row contributes `0.0` and is listed in
`Receipt.reconciliation.unreconciled_local_seqs`. Provider errors cost 0
upstream and reconcile to `cost_usd=0.0` with `cost_source="/v1/runs"`.

## Topic

One embedding cluster of relevant mentions for one brand.

| Field | Type | Rule |
|---|---|---|
| `topic_id` | `str` | `"{brand slug}-{index:02d}"`, index by descending `n` |
| `brand` | `str` | |
| `name` | `str` | ≤ 6 words, English, produced by the naming model from the medoids |
| `n` | `int` | mentions in the cluster; ≥ `method.min_size` |
| `n_clusters` | `int` | distinct `cluster_key` values in the cluster; ≥ `method.min_breadth` |
| `share` | `float \| None` | `n` / relevant labelled mentions of `brand`; `null` when the divisor is 0 |
| `net` | `float \| None` | `(pos − neg) / (pos + neg + neu)` over the cluster's labels; `null` when `pos + neg + neu = 0` (cluster holds only `irrelevant` labels) |
| `ci95` | `CI95 \| None` | cluster bootstrap on `net`; `null` iff `net` is `null` |
| `exemplar_mention_ids` | `list[str]` | exactly 3 medoid `mention_id`s, closest to the centroid first |
| `method` | `TopicMethod` | `{embedding_model: str, linkage: "average", threshold: 0.35, min_size: 3, min_breadth: 2}`; `threshold` is the average-linkage cosine-distance cut, fixed in `config` at 0.35 and chosen before any demo data (D012 F16) |

A `null` on any Topic estimate is paired with an `Abstention` row
(`scope=topics`, the brand, `source=null`, reason `below_minimum`).

## Receipt

The card. Written to `results/<session>/receipt.json`; `sonar verify <path>`
recomputes `content_digest`, re-derives `verdict`, and exits nonzero unless
the verdict is `RECONCILED`.

| Field | Type | Rule |
|---|---|---|
| `schema_rev` | `str` | this file's `schema_rev` |
| `sonar_rev` | `str` | package version plus short git sha, e.g. `0.1.0+82d0ab5` |
| `session_id` | `str` | `"{YYYYMMDDTHHMMSSZ}-{brand slug}-{6 hex}"` |
| `timestamps` | `Timestamps` | `{started_at: datetime, finished_at: datetime, reconciled_at: datetime \| None}` |
| `replay` | `bool` | `true` when rendered with `sonar render --from` instead of a live run |
| `verdict` | `Verdict` | see §Receipt verdict rule |
| `query` | `Query` | the validated Query |
| `runs` | `list[RunRecord]` | every ledger row of the session, including `run_id=null` and `n_results=0`; ordered by `local_seq`; the Markdown table prints zero-result rows |
| `totals` | `Totals` | see below |
| `reconciliation` | `Reconciliation` | `{fetched_at: datetime \| None, n_listed_in_window: int, unmatched_remote_run_ids: list[str], unreconciled_local_seqs: list[int]}`; `unmatched_remote_run_ids` are runs `GET /v1/runs` listed inside `[started_at, reconciled_at]` with no ledger row |
| `incumbent` | `Incumbent` | `{name: "Brand24 Team", price_usd_month: 349, url: str, checked_at: date, mentions_quota: 10000}`; values come from `report/incumbent.py` and the published-claims gate requires them identical to README |
| `comparison` | `Comparison` | `{briefs_per_month_assumed: 4, sonar_usd_month_equiv: float, ratio: float \| None, mentions_this_brief: int}`; `sonar_usd_month_equiv = totals.total_usd × briefs_per_month_assumed`; `ratio = incumbent.price_usd_month / sonar_usd_month_equiv`, `null` when the divisor is 0 |
| `mentions` | `MentionCounts` | `{fetched: int, deduped: int, labelled: int, excluded_with_reason: dict[str, int], by_source: dict[Source, int], by_brand: dict[str, int]}`; `excluded_with_reason` keys are exactly {`not_about_brand`, `irrelevant_label`, `refused`, `unparseable`, `error`, `dedup_native_id`, `dedup_url`, `dedup_text`}, every key present, `0` allowed; `deduped` counts rows after §Dedup precedence |
| `audit` | `Audit` | `{n_sample: int, n_agree: int, agreement: float \| None, tiebreak_calls: int, tiebreak_overflow: int}`; `n_sample` = rows in the fixed 10 % audit sample whose tiebreak call returned `ok`; `n_agree` = those whose tiebreak label equals the classifier label; `agreement = n_agree / n_sample`, `null` when `n_sample = 0`; `tiebreak_calls` = all tiebreak calls made; `tiebreak_overflow` = rows with `signals.overflow=true`. H3 reads `audit.agreement` |
| `abstentions` | `list[Abstention]` | `{scope: AbstainScope, brand: str \| None, source: Source \| None, reason: AbstainReason, detail: str}` |
| `what_could_not_be_checked` | `list[str]` | plain sentences, e.g. "X/Twitter: no Monid endpoint", "youtube_comment: items lacking a timestamp, excluded from WoW and events" |
| `content_digest` | `str` | sha256 hex over canonical JSON of the receipt with `content_digest` set to `""` |

`Totals`:

| Field | Type | Rule |
|---|---|---|
| `monid_usd` | `float` | Σ `cost_usd` over runs with `cost_source="/v1/runs"`; includes the ElevenLabs run |
| `monid_runs` | `int` | count of `runs`, including `run_id=null` |
| `monid_runs_billed` | `int` | runs with `cost_usd > 0` |
| `monid_runs_zero_results` | `int` | runs with `n_results = 0` (billed or not) |
| `monid_runs_failed` | `int` | runs whose `status` is a Monid failure state or starts with `LOCAL_`; a succeeded `run_id=null` sync run is not failed (D013 N6) |
| `llm_usd` | `float` | Σ OpenAI cost from `Label.usage`, topic naming, narration, and `Answer.usage` appended by `reconcile` |
| `llm_calls` | `dict[LlmKind, int]` | call counts by kind; cached labels are not calls |
| `llm_tokens` | `int` | Σ tokens over the same calls |
| `elevenlabs_usd` | `float` | the voice run's `cost_usd`; a breakout of `monid_usd`, not additive |
| `total_usd` | `float` | `monid_usd + llm_usd` |

## Digest

The analysis output (`digest.json`), rendered to Markdown and narrated.

| Field | Type | Rule |
|---|---|---|
| `brand` | `str` | |
| `competitors` | `list[str]` | as validated in Query |
| `window` | `Window` | `{current: {start: datetime, end: datetime}, previous: {start: datetime, end: datetime}}`; `current` = `[now − 7 d, now)`, `previous` = `[now − 14 d, now − 7 d)`; `window_days` is fixed at 14 so the two periods are equal; minimums apply per period |
| `share_of_voice` | `list[SovEntry]` | one per brand incl. competitors; `{brand: str, n: int, n_clusters: int, share: float \| None, ci95: CI95 \| None, basis_sources: list[Source], wow: WowShare}`; `share = n_b / Σ n` over `basis_sources`; `n` counts mention–brand pairs and is the `n` gating share minimums (`n < 20` per period → `below_minimum`); `share` and `ci95` are `null` iff the brand abstains or `Σ n = 0` |
| `sentiment` | `list[SentimentEntry]` | one per brand; `{brand: str, n: int, n_confirmed: int, pos: int, neg: int, neu: int, net: float \| None, ci95: CI95 \| None, ci95_iid: CI95 \| None, design_effect: float \| None, wow: WowNet}`; `n` counts relevant mentions and is the `n` gating net minimums; `design_effect = (cluster width / iid width)²`, `null` when the iid width is 0 (paired with an `Abstention` row of reason `degenerate`, D013 N4); every estimate is `null` when `pos + neg + neu = 0` or the brand abstains |
| `by_source` | `list[BySourceEntry]` | one per `(brand, source)` in `basis_sources`; `{brand: str, source: Source, n: int, n_clusters: int, pos: int, neg: int, neu: int, net: float \| None, ci95: CI95 \| None, ci95_iid: CI95 \| None, design_effect: float \| None, wow_scope: bool}`; estimates `null` under the same rule as `SentimentEntry`; `wow_scope=false` iff every item of the source for that brand has `published_at=null` (the source counts for share, is excluded from `wow` and `events`, and is listed in `what_could_not_be_checked`); with mixed timestamps `wow_scope=true` and the null items are dropped from `wow` and `events` one by one (D013 A1); H2 reads `design_effect` on `reddit` and `youtube_comment` where the entry meets the H2 minimums `n_clusters ≥ 5` and `n ≥ 20` over the full window, not per period (D013 N3) |
| `topics` | `list[Topic]` | ordered by brand then `topic_id` |
| `events` | `list[Event]` | `{brand: str, date: date, n: int, n_clusters: int, baseline_median: float, baseline_mad: float, threshold: float, label: str, exhibit_url: str \| None}`; days are UTC; `baseline_median` and `baseline_mad` are over the daily counts of the 14-day window excluding the tested day; `threshold = max(5, baseline_median + 3·baseline_mad)`; emitted iff `n ≥ threshold` and `n_clusters ≥ 3` over the day's mentions; `label` ≤ 6 words is the name of the day's largest topic, else the highest-`engagement_score` mention's matched term; `exhibit_url` is that mention's `url` |
| `top_mentions` | `list[TopMention]` | ≤ 10 per brand sorted by `engagement_score` descending, where `engagement_score` = sum of the numeric values of `Mention.engagement` (`0` for `{}`), ties broken by `published_at` descending (`null` last) then `mention_id` ascending; `{mention_id: str, brand: str, source: Source, url: str \| None, quote: str, lang: Lang, label: SentimentLabel, published_at: datetime \| None, engagement_score: int}`; `quote` ≤ 240 chars, verbatim, original language |
| `abstentions` | `list[Abstention]` | same shape as Receipt; an abstained source leaves `basis_sources` for every brand; every `null` in `share`, `net`, `ci95`, `delta`, `p_raw` and `p_holm` is paired with exactly one `Abstention` row naming the brand, the source (or `null` for brand-level) and the reason (`ci95_iid` is `null` iff `ci95` is and shares its row); a `null` `design_effect` from a zero iid width and a `null` `ci95_confirmed_only` from `n_confirmed = 0` are each paired with one row of reason `degenerate` (D013 N4) |
| `coverage_gaps` | `list[CoverageGap]` | `{source: str, reason: AbstainReason, note: str}`; always contains `{source: "x", reason: "unavailable", …}` |
| `cost` | `CostQuote` | `{verdict: Verdict, totals: Totals}` copied from the Receipt, never recomputed |
| `narration` | `Narration` | `{text: str \| None, chars: int, numbers_verified: bool, mp3_path: str \| None, local_seq: int \| None}`; `text` ≤ 900 chars English; `numbers_verified=true` iff every number in `text` occurs in this Digest; `local_seq` points at the ElevenLabs RunRecord |

`WowNet` (sentiment): `{delta: float \| None, ci95: CI95 \| None, ci95_confirmed_only: CI95 \| None, verdict: WowVerdict, p_raw: float \| None, p_holm: float \| None}`.
`WowShare` (share of voice): `{delta: float \| None, ci95: CI95 \| None, verdict: WowVerdict, p_raw: float \| None, p_holm: float \| None}`.
`ci95_confirmed_only` is `null` when `n_confirmed = 0`, paired with an
`Abstention` row of reason `degenerate` (D013 N4).

`delta` = current − previous, paired on the shared resample index
(§Resampling frame). `p_raw` is the two-sided bootstrap p-value
`2 · min(P(Δ ≤ 0), P(Δ ≥ 0))`; `p_holm` is Holm-adjusted at α = 0.05 over
the family brands × {net WoW, share WoW}, applied over the tests with
non-null `p_raw`, so `m` is the number of non-abstained tests in the family
(D013 N2). Verdict per PRE-REGISTRATION v1.1.1 §Verdict rule (D012 F1, F7,
F8; D013 N1); the Holm-adjusted p governs, CIs are published as display.
Rules are evaluated in the order `ABSTAIN`, `SIGNIFICANT`, `SUGGESTIVE`,
`NO_CHANGE_DETECTED`, and `SUGGESTIVE` and `NO_CHANGE_DETECTED` both require
not `ABSTAIN`:

- `ABSTAIN` iff minimums are not met (reason `below_minimum`) **or** `ci95`
  and `ci95_confirmed_only` exclude 0 with opposite signs (reason
  `signals_conflict`); evaluated first.
- `SIGNIFICANT` iff not `ABSTAIN` and `p_holm < 0.05` on the full set
  **and**, for net, `ci95_confirmed_only` excludes 0 with the same sign as
  the full-set `delta` (a `null` `ci95_confirmed_only` never satisfies this
  clause); for share (no confirmed-only interval) iff `p_holm < 0.05`.
- `SUGGESTIVE` iff not `ABSTAIN`, `p_raw < 0.05` and not `SIGNIFICANT`.
- `NO_CHANGE_DETECTED` iff not `ABSTAIN` and `p_raw ≥ 0.05` (minimums met:
  `n_clusters ≥ 5` and `n ≥ 20` in both periods).

On `ABSTAIN` for `below_minimum` every field but `verdict` is `null`; on
`signals_conflict` the intervals and p-values are kept and only the verdict
word abstains; on `degenerate` (`n_confirmed = 0`) only
`ci95_confirmed_only` is `null` and the verdict is decided by the rules
above.

### Resampling frame

One global index over the units `(brand, cluster_key)` present in the
session, drawn once per bootstrap iteration and shared by every estimand,
period and brand, so WoW deltas and cross-brand shares are paired. A cluster
spanning both periods is resampled as one unit carrying both periods'
mentions (D012 F15).

## StatsFile

`results/<session>/stats.json`: the numbers the video and `sonar ask` import
without narration or quotes. `{share_of_voice: list[SovEntry], sentiment:
list[SentimentEntry], by_source: list[BySourceEntry], events: list[Event],
window: Window}`, each field byte-identical to the same field of the
session's Digest. `results/<session>/topics.json` is `Digest.topics`
(`list[Topic]`) written alone. Both are written by the same step as
`digest.json` (D012 F21).

## Answer

One line of `answers.jsonl` per `sonar ask`.

| Field | Type | Rule |
|---|---|---|
| `session_id` | `str` | the session whose store was queried |
| `brand` | `str` | |
| `question` | `str` | verbatim user text |
| `answer` | `str` | model text after citation stripping; empty string when `refused` |
| `citations` | `list[str]` | `mention_id`s that exist in the session store; a cited id not in the store is stripped, the model is re-asked once, and a second miss sets `status=unverified` |
| `verified_numbers` | `list[str]` | every numeric token in `answer`, each of which occurs in `stats.json` (`StatsFile`), `topics.json` (`Digest.topics`), or a retrieved mention; an unverifiable number follows the same strip, re-ask once, `unverified` path. Renamed from `numbers_verified` (D012 F20); `Narration.numbers_verified: bool` keeps its name |
| `retrieved` | `list[str]` | `mention_id`s of the top-20 by cosine (or lexical fallback when embeddings failed) that were placed in context |
| `model` | `str` | OpenAI model id used |
| `usage` | `Usage` | `{tokens: int, cost_usd: float}`; `reconcile --session` appends it to the Receipt totals under `llm_calls.ask` |
| `status` | `AnswerStatus` | `refused` on model refusal; an empty store makes no LLM call and returns `refused` with `retrieved=[]` |

## Rules

### mention_id rule

`mention_id = sha256(f"{source}\n{key}".encode("utf-8")).hexdigest()[:24]`
where `key` is the first non-null of, in order: `native_id`, normalized
`url`, `text_key`. `text_key` = `text.normalize(text)` (NFKC, casefold,
whitespace collapsed, URLs and `@handles` removed) truncated to 200 chars.
The same item fetched by two runs, or for two brands, yields the same
`mention_id`.

### cluster_key rules

`cluster_key` is the bootstrap resampling unit (PRE-REGISTRATION §Cluster
bootstrap) and the breadth unit for topics and events.

| Source | `cluster_key` |
|---|---|
| `reddit` | the post id: a post's own `native_id`; a comment's parent post id |
| `youtube_comment` | the `videoId` the comment belongs to |
| `tiktok` | `author_hash` |
| `instagram` | `author_hash` |
| `youtube` (videos) | `mention_id` |
| `google_maps` | `mention_id` |
| `facebook` | `mention_id` |
| `trustpilot` | `mention_id` |
| `g2` | `mention_id` |
| `news` | `mention_id` |

When the key input is missing (`author_hash=null` on tiktok/instagram, no
parent id on a reddit comment), the adapter falls back to `mention_id` and
records it under `Receipt.what_could_not_be_checked` as "cluster key
fallback: <source> <count>", because a fallback inflates `n_clusters`.

### Dedup precedence

Applied per brand after all runs complete, before labelling
(`text.dedup`):

1. `(source, native_id)`: two items with the same source and non-null
   `native_id` are one mention; the first by `raw_ref` order wins.
2. normalized `url`: among survivors with `native_id=null`, equal normalized
   URLs are one mention.
3. `text_key`: among survivors with both `native_id` and `url` null, equal
   `text_key` is one mention.

Dedup never merges across sources. A mention matching the brand and a
competitor is kept once per brand (two rows, one `mention_id`);
`Receipt.mentions.deduped` counts rows, and the Digest states that SoV
counts mention–brand pairs. Precedence for the `raw_ref` tie-break: lower
`local_seq`, then lower item index.

### Receipt verdict rule

```
if receipt.replay:                                   verdict = REPLAY
elif all(r.cost_source == "/v1/runs" for r in runs if r.run_id is not None)
     and reconciliation.unmatched_remote_run_ids == []:  verdict = RECONCILED
else:                                                verdict = PARTIAL
```

`RECONCILED` iff every row with a `run_id` has `cost_source="/v1/runs"` and
no remote run in the window is unmatched. Rows with `run_id=null` (`LOCAL_*`
statuses other than `LOCAL_DEADLINE`, and succeeded `$0` sync runs that
returned no id) are reconciled by construction: `cost_usd=0.0`,
`cost_source="local"`, never in `unreconciled_local_seqs` (D012 F13), and
counted in `monid_runs_failed` iff `status` starts with `LOCAL_` (D013 N6).
A row with a `run_id` that the listing does not return, including
`LOCAL_DEADLINE`, stays `unreconciled` and the verdict is `PARTIAL`.
`GET /v1/runs` failure leaves `reconciliation.fetched_at=null`, verdict
`PARTIAL`, exit 4; `sonar reconcile --session <id>` reruns and may upgrade
to `RECONCILED`. `sonar verify` exits 0 only on `RECONCILED`; a `REPLAY`
receipt renders with the REPLAY banner and never passes `verify`.

## Open questions

Each is resolved by the named trigger; the resolution lands as a
`docs/DECISIONS.md` entry and, if it changes a field, a `schema_rev` bump.

| Id | Question | Provisional value in this contract | Resolved by |
|---|---|---|---|
| OQ-1 | Exact Monid status vocabulary for running and succeeded states | `status` is `str`, not an enum; the four failure states above are the ones the Error matrix names | W3.7 recorded `tests/fixtures/v1_runs_page.json` |
| OQ-2 | Whether `$0` sync endpoints (`tinyfish /search`, `/fetch`) return a `runId` and appear in `GET /v1/runs` | `Mention.run_id` is `str \| None` (D012 F12); a sync run without an id has `RunRecord.run_id=null`, `cost_usd=0.0`, `cost_source="local"` and, when succeeded, is not counted in `monid_runs_failed` (D013 N6) | W3.1 news fixture from the first live `sonar record` |
| OQ-3 | Facebook reviews carry `isRecommended`, not stars | `rating` = 5 when recommended, 1 when not, so the deterministic bucket still applies | W3.4 adapter test on a recorded fixture |
| OQ-4 | Treatment of `published_at=null` mentions (YouTube comments, some Instagram) in WoW and events | in-window for SoV (the fetch was window-bounded), excluded from `wow` and `events`, source flagged `BySourceEntry.wow_scope=false` and listed in `what_could_not_be_checked` | Resolved: D012 F2 |
| OQ-5 | Trustpilot and G2 native id, rating, timestamp and author field names | Mention fields typed as above; adapter fills `native_id` from whatever unique review id the schema exposes | W0.3 `docs/monid/inspect/*.json` |
| OQ-6 | ElevenLabs `billedUnits` semantics (characters vs calls) and `voice_id` placement | `RunRecord.billed_units` is `int \| None`; `estimate_usd` uses $0.05 per 1k chars | W5.5 20-char probe with run id in DECISIONS |
| OQ-7 | `wow` on share-of-voice entries and the `p_raw`/`p_holm` fields are additions to Appendix §Contracts so the Holm family "brands × {net, share}" is representable | included as specified | Resolved: D012 F1/F8, share WoW confirmed as part of the design |

## Changelog

### 1.1.2 — 2026-09-02, D014

- Mention gains `match_kind` (`MatchKind` enum `text | inherited | entity`); `matched_terms` may come from the parent post (reddit comments) or the resolved entity (review sources) instead of the item's own text; relevance still requires `about_brand`.

### 1.1.1 — 2026-09-02, D013

Applies `docs/DECISIONS.md` D013, resolving
`docs/research/reviews/2026-09-02-contracts-review-2.md`. Item ids in
brackets.

- [N1] §Digest verdict rule: rows evaluated in the order `ABSTAIN`,
  `SIGNIFICANT`, `SUGGESTIVE`, `NO_CHANGE_DETECTED`; `SUGGESTIVE` and
  `NO_CHANGE_DETECTED` both require not `ABSTAIN`.
- [N2] Holm is applied over the tests with non-null `p_raw`; `m` is the
  number of non-abstained tests in the family.
- [N3] H2 minimums defined on the `BySourceEntry` over the full window:
  `n_clusters ≥ 5` and `n ≥ 20` (comment-source paragraph and `by_source`).
- [N4] `AbstainReason` gains `degenerate`; the pairing rule names `share`,
  `net`, `ci95`, `delta`, `p_raw`, `p_holm`; `design_effect` with zero iid
  width and `ci95_confirmed_only` with `n_confirmed = 0` are `null` and
  paired with a `degenerate` row; `WowNet.ci95_confirmed_only` null rule
  stated.
- [N5] `Label.corroboration`: `model_only` = no tiebreak adopted and not
  `confirmed` (null deterministic signal with confidence ≥ 0.6, failed
  tiebreak call, or `signals.overflow=true`).
- [N6] `RunRecord.cost_source`, Totals, `monid_runs_failed`, §Receipt
  verdict rule and OQ-2: a `local` row is failed iff `status` starts with
  `LOCAL_`; a succeeded `run_id=null` sync run is `local`, `cost_usd=0.0`,
  not failed; `LOCAL_DEADLINE` keeps its `run_id` and is `unreconciled`
  until listed.
- [A1] `BySourceEntry.wow_scope=false` iff every item of the source lacks
  `published_at`; mixed sources keep `wow_scope=true` and drop null items
  one by one.
- [A2] §Two-signal policy rule 4: an audit-only tiebreak on a null-signal,
  confidence ≥ 0.6 mention is never adopted (`model_only`,
  `decided_by=classifier`, H3 only).
- Header cites D013; `AbstainReason` and verdict text cite PRE-REGISTRATION
  v1.1.1.

### 1.1.0 — 2026-09-02, D012

Applies `docs/DECISIONS.md` D012, resolving
`docs/research/reviews/2026-09-02-contracts-review.md`. Finding ids in
brackets.

- [F1, F7, F8] `WowNet`/`WowShare` verdict rule rewritten: `p_holm` governs,
  CIs are display; opposite-sign CIs → `ABSTAIN` with `signals_conflict`;
  share WoW confirmed, OQ-7 resolved.
- [F2, F11] `AbstainReason`: `no_timestamps` removed; `below_minimum`,
  `halted`, `embedding_failed`, `signals_conflict` added. `BySourceEntry`
  gains `wow_scope: bool`. OQ-4 resolved. `what_could_not_be_checked` example
  reworded to "items lacking a timestamp".
- [F3] `BySourceEntry` gains `ci95`, `ci95_iid`, `design_effect` (nullable);
  H2 scored on `reddit` and `youtube_comment`.
- [F4] `Receipt` gains `audit {n_sample, n_agree, agreement, tiebreak_calls,
  tiebreak_overflow}`.
- [F5] `SovEntry.share/ci95`, `SentimentEntry.net/ci95/ci95_iid/
  design_effect`, `Topic.share/net/ci95`, `WowNet.delta/ci95/
  ci95_confirmed_only`, `WowShare.delta/ci95` are `T | None`, each null
  paired with an `Abstention` row.
- [F6] `Query.window_days` fixed at 14 (validator `== 14`); `Digest.window`
  periods stated as `[now − 7 d, now)` and `[now − 14 d, now − 7 d)`;
  minimums per period.
- [F9, F10, F17] §Two-signal policy: precedence rules 1–3; `Signals` gains
  `overflow: bool`; `corroboration` rule restated; denominators for the 10 %
  sample and 40 % cap defined.
- [F12, F13] `Mention.run_id` is `str | None`; `CostSource` gains `local`;
  `RunRecord.cost_source` and §Receipt verdict rule restated so `run_id=null`
  rows reconcile by construction; OQ-2 provisional value updated.
- [F14] `Query.competitors` limited to 1 under `profile=lite`; validator order
  updated (exit 2).
- [F15] §Resampling frame added: one global index over `(brand, cluster_key)`.
- [F16] `TopicMethod.threshold` fixed at 0.35 with `min_size 3`,
  `min_breadth 2`.
- [F18] `SovEntry.n` gates share minimums; `SentimentEntry.n` gates net
  minimums, both per period.
- [F19] `Event` gains `baseline_mad`, `threshold`; baseline excludes the
  tested day; days are UTC.
- [F20] `Answer.numbers_verified` renamed `verified_numbers`.
- [F21] `StatsFile` (`stats.json`) defined; `topics.json` = `Digest.topics`.
- [F22] `MentionCounts.excluded_with_reason` keys fixed to the eight listed.
- [F23] `TopMention` gains `engagement_score`; sort key and tie-break defined.
- Header cites D012 and this Changelog; comment-source paragraph notes H2
  scoring [F3].

### 1.0.0 — 2026-09-02

Initial frozen contract (`docs-frozen` tag).
