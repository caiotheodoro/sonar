# PRE-REGISTRATION — sonar statistics plan

**Version**: 1.1.3
**Frozen**: 2026-09-02 (design reference: `docs/research/2026-09-02-task-graph-and-design.md`)
**Amended**: 2026-09-02, A1–A4 (D012, D013, D014); 2026-09-03, A5 (`docs/DECISIONS.md` D018)

> **FROZEN TEXT.** Any change to the thresholds, rules, or hypotheses below
> after the freeze date goes through a **DECISIONS.md entry** stating the
> prior value, the new value, rationale, and reversal clause; only then is
> it applied to the sections below in place, together with an §Amendments
> entry quoting the prior value and a bump of the version line above. No
> other edit touches this file after the freeze; the `docs-frozen` tag marks
> the commit that applied the latest amendment.

---

## Estimands

1. **Share of voice (share)**: `n_brand / Σn` over `basis_sources`, the set
   of sources that returned (did not abstain) for **every** compared brand.
   A source that abstained for any one brand is excluded from the share of
   all brands, so a competitor missing a source cannot inflate the brand.
   `n` counts mention–brand pairs; a mention matching two brands counts once
   for each.
2. **Net sentiment (net)**: `(pos − neg) / (pos + neg + neu)` over relevant
   mentions (`about_brand ∧ matched_terms`), reported for the full set and
   for the `confirmed`-only subset.
3. **Week-over-week (WoW) delta**: the window is fixed at 14 days
   (`window_days == 14`); periods are `current = [now − 7 d, now)` and
   `previous = [now − 14 d, now − 7 d)` by `published_at`; delta in share
   and net, `current − previous`. Mentions with `published_at = null` count
   for share but are excluded from WoW and from events, one by one. A source
   every one of whose items lacks a timestamp is flagged `wow_scope = false`
   (per source, in `by_source`) and listed under `what_could_not_be_checked`;
   a source with mixed timestamps keeps `wow_scope = true` and only its null
   items are dropped. This is a scope flag, not an abstention: the source
   stays in `basis_sources`.

---

## Cluster bootstrap

| Parameter | Value |
|---|---|
| Bootstrap unit | `cluster_key` (per source: reddit → post id; youtube_comment → video id; tiktok/instagram → author_hash; reviews/news/youtube video → mention_id) |
| Resampling | one global index over the units `(brand, cluster_key)` present in the session, drawn once per iteration and shared by every estimand, period and brand, so WoW deltas and cross-brand shares are paired; a cluster spanning both periods is resampled as one unit carrying both periods' mentions |
| Percentile | 95 % |
| Resamples (live) | **B = 2000** |
| Resamples (frozen demo) | **B = 10000** |
| Seed | **777** |
| Design effect | `(cluster CI width / iid CI width)²` reported alongside the cluster CI |

The iid CI (ignoring cluster structure) is computed in parallel as a
comparison; the design effect quantifies how much clustering matters.

---

## Verdict rule

Holm-adjusted α = **0.05** over the family brands × {net WoW, share WoW}.
The per-test two-sided p-value is the bootstrap `p = 2 · min(P(Δ ≤ 0),
P(Δ ≥ 0))` over the B shared resamples. Raw and Holm-adjusted p are both
reported; the adjusted one governs the verdict word. Holm is applied over
the tests with non-null `p_raw`, so `m` is the number of non-abstained tests
in the family.

Rows are evaluated in the order ABSTAIN, SIGNIFICANT, SUGGESTIVE,
NO_CHANGE_DETECTED; SUGGESTIVE and NO_CHANGE_DETECTED both require not
ABSTAIN.

| Verdict | Condition |
|---|---|
| **ABSTAIN** | Minimums not met (reason `below_minimum`), **or** the full-set and confirmed-only 95 % CIs exclude 0 with opposite signs (reason `signals_conflict`); evaluated first |
| **SIGNIFICANT** | Not ABSTAIN and `p_holm < 0.05` on the full set **and**, for net, the confirmed-only 95 % CI excludes 0 with the same sign as the full-set point estimate (a null confirmed-only CI, `n_confirmed = 0`, never satisfies this). For share (no confirmed-only interval): `p_holm < 0.05` |
| **SUGGESTIVE** | Not ABSTAIN, `p_raw < 0.05` and not SIGNIFICANT |
| **NO_CHANGE_DETECTED** | Not ABSTAIN and `p_raw ≥ 0.05` (minimums met) |

The 95 % CIs are published alongside every verdict as display; they are not
the rule. A confirmed-only CI with `n_confirmed = 0` is null and paired with
an `Abstention` row of reason `degenerate`; the verdict is still decided by
the rows above. Share WoW is part of the design: the Holm family is brands × {net
WoW, share WoW}, eight tests for a brand with three competitors.

---

## Abstention thresholds

The minimums are `n_clusters ≥ 5` and `n ≥ 20`. They gate two estimands
separately (A5):

- A brand's **level** estimates — `share` and `net` with their `ci95` —
  are set to **ABSTAIN** (reason `below_minimum`) when a minimum is missed
  in the **current** period.
- A brand's **week-over-week** delta — `delta`, its `ci95`, `p_raw`,
  `p_holm` and the WoW `verdict` — is set to **ABSTAIN** (reason
  `below_minimum`) when a minimum is missed in **either** the current or
  the previous period.

So a brand with a well-populated current period but a thin previous
period reports its level `share` and `net` and abstains only on the trend.

`n` is the estimand's own count: for share, `SovEntry.n` (mention–brand
pairs over `basis_sources`); for net, `SentimentEntry.n` (relevant
mentions). Each is evaluated per period.

Abstained sources leave `basis_sources` for **every** brand (not just the
abstaining brand). Every null `share`, `net`, `ci95`, `delta`, `p_raw` and
`p_holm` is paired with an `Abstention` row naming the brand, the source (or
null) and the reason. A `design_effect` with zero iid CI width and a
confirmed-only CI with `n_confirmed = 0` are null with minimums met; each is
paired with a row of reason `degenerate`.

**Abstain reasons** (per source, brand, topics, or verdict):

| Reason | Trigger |
|---|---|
| `empty` | zero fetched mentions from provider |
| `provider_failed` | Monid status BLOCKED/FAILED/STOPPED or provider 4xx–5xx |
| `rate_limited` | Monid 429 (retry exhausted) |
| `deadline` | TIMED_OUT / exceeded deadline |
| `unavailable` | endpoint absent (e.g. X/Twitter) |
| `schema_drift` | AdapterSchemaError (raw saved) |
| `below_minimum` | level: minimum missed in the current period; WoW: minimum missed in either period (A5) |
| `halted` | Monid 402 breaker stopped the session |
| `embedding_failed` | embedding call failed; topics abstain, chat falls back to lexical retrieval |
| `signals_conflict` | verdict only: full-set and confirmed-only CIs exclude 0 with opposite signs |
| `degenerate` | minimums met but the estimate is undefined: `design_effect` with zero iid CI width, or confirmed-only CI with `n_confirmed = 0` |

`no_timestamps` is not an abstention. Items lacking a timestamp (all
`youtube_comment` items; some Instagram hashtag items) keep their source in
`basis_sources` and are excluded from WoW and events only, item by item. A
source carries `wow_scope = false` only when every one of its items lacks a
timestamp (`youtube_comment`); a mixed source such as Instagram keeps
`wow_scope = true`.

---

## Event rule

A date is flagged as an **event** when:

```
n_day ≥ max(5, median + 3·MAD)
    AND
n_clusters_day ≥ 3
```

where `median` and `MAD` are taken over the daily counts of the 14-day
window per brand **excluding the tested day**, days are UTC calendar days,
and `n_clusters_day` is the number of distinct `cluster_key` values on that
day. Each emitted event carries `baseline_median`, `baseline_mad` and
`threshold = max(5, median + 3·MAD)` so the rule can be re-derived from the
digest. Both signals are required: volume alone (one viral thread) is not an
event.

---

## Two-signal labelling policy

The model supplies observations; code decides. Thresholds frozen here:

| Parameter | Value |
|---|---|
| Relevance | `about_brand` (model) **and** `matched_terms ≠ ∅`; both required. `matched_terms` comes from the item's own text (`match_kind = text`), from the parent post for a comment whose text matched nothing when that post is in the same payload and matched (`inherited`), or from the resolved entity for a review source, Google Maps place, Facebook page, Trustpilot domain or G2 slug (`entity`); `about_brand` is required in every kind (A4, D014) |
| Deterministic signal | rating bucket for review sources: ≤ 2 negative, 3 neutral, ≥ 4 positive; lexicon sign otherwise |
| Tiebreak trigger | classifier disagrees with the deterministic signal, **or** no deterministic signal and classifier `confidence < 0.6` |
| Tiebreak cap | at most **40 %** of a brand's rows; beyond the cap, mentions keep the classifier label as `model_only` with `overflow = true`, are excluded from the confirmed-only subset, and the overflow count is published in `receipt.audit.tiebreak_overflow` |
| Audit sample | a fixed **10 %** of rows (seed 777) always sent to the tiebreak model, for H3 |
| Denominators | for the 10 % sample and the 40 % cap: relevant mention–brand rows after dedup, per brand, per session; a mention kept for two brands is two rows and may be sampled in each |
| `contested` | a tiebreak triggered by disagreement or low confidence disagrees with the classifier; tiebreak label wins; excluded from the confirmed-only subset |
| `model_only` | no tiebreak adopted and not `confirmed`: a null deterministic signal with classifier confidence ≥ 0.6, a failed tiebreak call, or `overflow = true` |

Precedence:

1. Classifier agrees with a non-null deterministic signal → `confirmed`. No
   tiebreak result overrides it; an audit-sample tiebreak on such a mention is
   recorded and counted in H3 only.
2. A tiebreak triggered by disagreement or low confidence wins when it
   disagrees with the classifier (`contested`) and confirms when it agrees
   (`confirmed`).
3. A mention that would have triggered a tiebreak but hit the 40 % cap keeps
   the classifier label (`model_only`, `overflow = true`).
4. An audit-sample tiebreak on a mention with a null deterministic signal and
   classifier confidence ≥ 0.6 is never adopted, whether or not it agrees:
   `model_only`, `decided_by = classifier`, recorded and counted in H3 only.

---

## Hypotheses

| Id | Hypothesis | Threshold | Stopping rule |
|---|---|---|---|
| **H1** | Brand + 3 competitors, all-in cost < $5 | `< $5` total, where `total_usd = monid_usd + llm_usd` and `elevenlabs_usd` is a breakout of `monid_usd`, not additive | Measured from frozen demo receipt; pass if `receipt.totals.total_usd < 5` |
| **H2** | Design effect ≥ 1.5 on thread-clustered comment sources | `≥ 1.5` | Measured at bootstrap from `by_source.design_effect`; pass if `design_effect ≥ 1.5` on each of `reddit` and `youtube_comment` that meets minimums, where meets minimums is `n_clusters ≥ 5` and `n ≥ 20` on the `BySourceEntry` over the full window (not per period); `tiktok` and `instagram` (author-clustered) are reported, not scored |
| **H3** | Classifier–tiebreak agreement on audit sample ≥ 0.85 | `≥ 0.85` | 10 % fixed audit (seed 777); pass if `receipt.audit.agreement ≥ 0.85` |
| **H4** | Zero-mention brand still costs > $0 | `> $0` | Avenza run yields a receipt; pass if `receipt.totals.total_usd > 0` even when `mentions.fetched = 0` |
| **H5** | 50-label blind hand check agreement ≥ 0.85 | `≥ 0.85` | 50 relevant mention–brand rows from the frozen demo, all brands pooled, seed 777, stratified by source in proportion (largest-remainder allocation of the 50 slots: floor of `50 · n_source / N` per source, remaining slots to the largest fractional remainders, ties by `Source` enum order; a source's allocation is capped at its row count and the surplus is reassigned by the same rule); the rater sees text only (no rationale, deterministic signal, source, or brand label); agreement is raw agreement with the final `label`; pass if `agreement ≥ 0.85`; published either way |

---

## Threshold index

The published-claims test asserts each of these equals the constant in
`src/sonar/config.py`:

- 95 %, B=2000 live, B=10000 frozen demo, seed 777
- α=0.05 (Holm) over the tests with non-null `p_raw`; `p_holm` governs
  SIGNIFICANT, `p_raw` governs SUGGESTIVE; ABSTAIN evaluated first
- window_days = 14; periods `[now − 7 d, now)` and `[now − 14 d, now − 7 d)`
- abstain the level (share, net) at n_clusters < 5 or n < 20 in the current period; abstain the WoW delta at n_clusters < 5 or n < 20 in either period (A5)
- events: n_day ≥ max(5, median + 3·MAD), n_clusters_day ≥ 3, 14-day baseline
  excluding the tested day, UTC days
- tiebreak: confidence < 0.6, cap 40 %, audit 10 %
- topics: average-linkage cosine distance cut 0.35, min_size 3, min_breadth 2
- H1: < $5; H2: ≥ 1.5 on reddit and youtube_comment with n_clusters ≥ 5 and
  n ≥ 20 per source over the full window; H3: ≥ 0.85; H4: > $0;
  H5: ≥ 0.85 on 50 labels, seed 777, largest-remainder stratification

---

## Amendments

Each amendment is a `docs/DECISIONS.md` entry, applied in place, plus a
version bump, as the banner requires. Prior values are quoted; the sections
above show the new values.

### A1 — same-day gate corrections (v1.0.0, commit `56240f2`)

Applied on the freeze day, 2026-09-02, between the initial commit
(`f51c0a8`) and the `docs-frozen` tag, without a version bump or a
DECISIONS entry. Recorded here retroactively under D012 F26:

- `basis_sources`: prior "sources that contributed ≥ 1 mention to any brand";
  new "sources that returned for every compared brand", `n` counts
  mention–brand pairs.
- Net sentiment: prior formula only; new "over relevant mentions, full set
  and confirmed-only".
- WoW: prior "split at now − 7 d"; new "by `published_at`, null timestamps
  count for share, excluded from WoW and events".
- Holm: prior "α = 0.05 over brands × {net, share}"; new family named as
  {net WoW, share WoW}, per-test p defined, adjusted p governs the verdict
  word.
- Event baseline: prior "7-day rolling window"; new "median and MAD over the
  full 14-day window", `n_clusters_day` defined.
- Two-signal labelling policy section added (relevance, deterministic
  buckets, tiebreak trigger `confidence < 0.6`, cap 40 %, audit 10 %,
  `contested`).
- Done-check renamed Threshold index and tied to `src/sonar/config.py`.

### A2 — D012, review resolutions (v1.1.0, 2026-09-02)

Applies `docs/DECISIONS.md` D012, resolving
`docs/research/reviews/2026-09-02-contracts-review.md` (findings in
brackets):

- [F1, F7, F8] Verdict rule: prior CI-based table; new `p_holm` governs
  SIGNIFICANT, `p_raw` governs SUGGESTIVE and NO_CHANGE_DETECTED,
  opposite-sign CIs → ABSTAIN `signals_conflict`; share WoW confirmed.
- [F2, F11] Abstain reasons: prior seven reasons ending in `no_timestamps`
  ("no timestamp field in response (Instagram)"); new `no_timestamps` removed
  and replaced by the per-source `wow_scope` flag; `below_minimum`, `halted`,
  `embedding_failed`, `signals_conflict` added; Instagram wording is "items
  lacking a timestamp".
- [F3] H2: prior "for youtube_comment"; new scored on `reddit` and
  `youtube_comment` from `by_source.design_effect`.
- [F4] H3: prior "pass if `agreement ≥ 0.85`" with the overflow count
  "published in the receipt"; new reads `receipt.audit.agreement`; overflow
  count is `receipt.audit.tiebreak_overflow`.
- [F5] Prior: no pairing rule; new every null estimate is paired with an
  `Abstention` row.
- [F6] Window: prior "split at `now − 7 d`", minimums "in either week"; new
  fixed at 14 days, periods `[now − 7 d, now)` and `[now − 14 d, now − 7 d)`,
  minimums per period.
- [F9, F10, F17] Two-signal policy: prior cap row "at most 40 % of a brand's
  mentions; beyond the cap, mentions stay `model_only`", `contested` row
  "tiebreak disagrees with classifier", no precedence list, no denominators;
  new precedence 1–3, overflow case (`overflow = true`, excluded from the
  confirmed-only subset), denominators as rows per brand per session.
- [F15] Resampling: prior "shared resample indices (paired deltas across
  brands)"; new one global index over `(brand, cluster_key)`, a cluster
  spanning both periods resampled as one unit.
- [F16] Prior: topic cut absent from the threshold index; new 0.35,
  `min_size 3`, `min_breadth 2` added.
- [F18] Prior: "`n < 20` mentions" with no field named; new share minimums
  use `SovEntry.n`, net minimums use `SentimentEntry.n`.
- [F19] Event baseline: prior "the full 14-day window", no day convention,
  no published baseline fields; new excludes the tested day, UTC days,
  `baseline_mad` and `threshold` published.
- [F24] H1: prior "total (Monid + LLM + ElevenLabs)"; new
  `total_usd = monid_usd + llm_usd`, ElevenLabs a breakout.
- [F25] H5: prior "50 labels rated blind (rationale hidden)"; new sampling
  frame (50 relevant mention–brand rows, all brands pooled), seed 777,
  stratification by source, blinding (text only) and raw agreement with the
  final `label` defined.
- [F26] A1 recorded above.

### A3 — D013, second review resolutions (v1.1.1, 2026-09-02)

Applies `docs/DECISIONS.md` D013, resolving
`docs/research/reviews/2026-09-02-contracts-review-2.md` (item ids in
brackets):

- [N1] Verdict rule: prior SUGGESTIVE and `signals_conflict` ABSTAIN could
  both hold; new ABSTAIN is evaluated first and SUGGESTIVE and
  NO_CHANGE_DETECTED both require not ABSTAIN.
- [N2] Holm: prior `m` unstated when a test abstains; new Holm is applied
  over the tests with non-null `p_raw`, `m` = number of non-abstained tests.
- [N3] H2: prior "that meets minimums" undefined per source; new
  `n_clusters ≥ 5` and `n ≥ 20` on the `BySourceEntry` over the full window.
- [N4] Pairing: prior "every abstained (null) estimate"; new named fields
  `share`, `net`, `ci95`, `delta`, `p_raw`, `p_holm`; `design_effect` with
  zero iid width and confirmed-only CI with `n_confirmed = 0` are null and
  paired with the new reason `degenerate` (eleventh abstain reason).
- [N5] `model_only` row added to the two-signal table: no tiebreak adopted
  and not `confirmed`.
- [A1] Mixed-timestamp sources: prior "their source is flagged
  `wow_scope = false`"; new only a source with no timestamped item is
  flagged; null items are dropped one by one.
- [A2] Precedence rule 4: audit-only tiebreak on a null-signal, confidence
  ≥ 0.6 mention is never adopted.
- [A3] H5 stratification: prior "in proportion"; new largest-remainder
  allocation with ties by `Source` enum order.
- [A4] Banner reworded to the mechanism actually used (DECISIONS entry,
  in-place edit, amendment, version bump); A2 above now quotes prior values
  for every finding.
- N6 changes CONTRACTS only (ledger and receipt rules); no statistics text
  here is affected.

### A4 — D014, relevance by context (v1.1.2, 2026-09-02)

Applies `docs/DECISIONS.md` D014 after the first live smoke run (W3.7, runs
`01M1GPJXYTAMZNGWQNT7Y7KWG0` and `01M1GPP9HXJKQQYJ0V2FFCE0QV`): 40 Reddit
items of which 11 name the brand in their own text, 4 Google Maps reviews of
which 0 do.

- Relevance row: prior "`about_brand` (model) **and** `matched_terms ≠ ∅`
  (regex); both required", where `matched_terms` was a word-boundary match
  in the item's own text only; new `matched_terms` may also be inherited
  from the matched parent post (reddit comments) or set to the brand for a
  review of the resolved entity, recorded as `match_kind` on the Mention
  (CONTRACTS 1.1.2). `about_brand` stays required, so the gate is not
  loosened on the model side. Reversal clause per D014: inherited and
  entity matches showing a false-positive rate above 10 % after the
  `about_brand` gate in the H5 hand check or the RED-TEAM homonym attack.
- Reddit sampling: prior single cap of 40 items (`maxItems`, `maxPostCount`,
  `maxComments` all 40); new `maxPostCount 15` and `maxComments 2` per post
  with `maxItems` at the profile cap and the unit cost unchanged. The
  denominators and thresholds in this file are not affected.

### A5 — D018, split the below-minimum rule by estimand (v1.1.3, 2026-09-03)

Applies `docs/DECISIONS.md` D018 after the first live full run (W6.1 dry,
session `20260904T023500Z-nubank-441cf0`): 4 brands, 27–72 relevant
mentions in the current 7-day period, 7–13 in the previous — every brand
abstained on both `share` and `net` under the old rule.

- §Abstention thresholds: prior "A brand's share and net estimates are set
  to ABSTAIN when either: `n_clusters < 5` in either the current or
  previous period, or `n < 20` in either the current or previous period.
  … Each is evaluated per period." New: the **level** estimates (`share`,
  `net`, `ci95`) gate on the **current** period only; the **week-over-week
  delta** (`delta`, its `ci95`, `p_raw`, `p_holm`, WoW `verdict`) gates on
  **either** period. A brand with a populated current period and a thin
  previous period reports its level and abstains only on the trend.
- §Threshold index: the "abstain at n_clusters < 5 or n < 20 in either
  period" line is split accordingly.
- Thresholds, window, estimands and hypotheses are otherwise unchanged;
  `MIN_MENTIONS_PER_WEEK = 20` and `MIN_CLUSTERS_PER_WEEK = 5` keep their
  values. No wire-format change (a level estimate could already be null
  independently of its WoW).
- Reversal clause per D018: the H5 hand check or a RED-TEAM attack shows a
  current-period-only level estimate is unreliable without the prior week.
