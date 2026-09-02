# PRE-REGISTRATION — sonar statistics plan

**Version**: 1.1.0
**Frozen**: 2026-09-02 (design reference: `docs/research/2026-09-02-task-graph-and-design.md`)
**Amended**: 2026-09-02, A1 and A2 (see §Amendments; `docs/DECISIONS.md` D012)

> **FROZEN TEXT.** Any change to the thresholds, rules, or hypotheses below
> after this freeze date is a **DECISIONS.md entry** (not an edit to this file).
> The entry must state the prior value, the new value, rationale, and reversal
> clause. This banner and the version line above are never modified by edits.

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
   for share but are excluded from WoW and from events; their source is
   flagged `wow_scope = false` (per source, in `by_source`) and listed under
   `what_could_not_be_checked`. This is a scope flag, not an abstention: the
   source stays in `basis_sources`.

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
reported; the adjusted one governs the verdict word.

| Verdict | Condition |
|---|---|
| **SIGNIFICANT** | `p_holm < 0.05` on the full set **and**, for net, the confirmed-only 95 % CI excludes 0 with the same sign as the full-set point estimate. For share (no confirmed-only interval): `p_holm < 0.05` |
| **SUGGESTIVE** | `p_raw < 0.05` and not SIGNIFICANT |
| **NO_CHANGE_DETECTED** | `p_raw ≥ 0.05` (minimums met) |
| **ABSTAIN** | Minimums not met (reason `below_minimum`), **or** the full-set and confirmed-only 95 % CIs exclude 0 with opposite signs (reason `signals_conflict`) |

The 95 % CIs are published alongside every verdict as display; they are not
the rule. Share WoW is part of the design: the Holm family is brands × {net
WoW, share WoW}, eight tests for a brand with three competitors.

---

## Abstention thresholds

A brand's share and net estimates are set to **ABSTAIN** (reason
`below_minimum`) when **either**:

- `n_clusters < 5` in either the current or previous period, **or**
- `n < 20` in either the current or previous period.

`n` is the estimand's own count: for share, `SovEntry.n` (mention–brand
pairs over `basis_sources`); for net, `SentimentEntry.n` (relevant
mentions). Each is evaluated per period.

Abstained sources leave `basis_sources` for **every** brand (not just the
abstaining brand). Every abstained (null) estimate is paired with an
`Abstention` row naming the brand, the source (or null) and the reason.

**Abstain reasons** (per source, brand, topics, or verdict):

| Reason | Trigger |
|---|---|
| `empty` | zero fetched mentions from provider |
| `provider_failed` | Monid status BLOCKED/FAILED/STOPPED or provider 4xx–5xx |
| `rate_limited` | Monid 429 (retry exhausted) |
| `deadline` | TIMED_OUT / exceeded deadline |
| `unavailable` | endpoint absent (e.g. X/Twitter) |
| `schema_drift` | AdapterSchemaError (raw saved) |
| `below_minimum` | brand-level minimums above not met in either period |
| `halted` | Monid 402 breaker stopped the session |
| `embedding_failed` | embedding call failed; topics abstain, chat falls back to lexical retrieval |
| `signals_conflict` | verdict only: full-set and confirmed-only CIs exclude 0 with opposite signs |

`no_timestamps` is not an abstention. Items lacking a timestamp (all
`youtube_comment` items; some Instagram hashtag items) keep their source in
`basis_sources`; the source carries `wow_scope = false` and is excluded from
WoW and events only.

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
| Relevance | `about_brand` (model) **and** `matched_terms ≠ ∅` (regex); both required |
| Deterministic signal | rating bucket for review sources: ≤ 2 negative, 3 neutral, ≥ 4 positive; lexicon sign otherwise |
| Tiebreak trigger | classifier disagrees with the deterministic signal, **or** no deterministic signal and classifier `confidence < 0.6` |
| Tiebreak cap | at most **40 %** of a brand's rows; beyond the cap, mentions keep the classifier label as `model_only` with `overflow = true`, are excluded from the confirmed-only subset, and the overflow count is published in `receipt.audit.tiebreak_overflow` |
| Audit sample | a fixed **10 %** of rows (seed 777) always sent to the tiebreak model, for H3 |
| Denominators | for the 10 % sample and the 40 % cap: relevant mention–brand rows after dedup, per brand, per session; a mention kept for two brands is two rows and may be sampled in each |
| `contested` | a tiebreak triggered by disagreement or low confidence disagrees with the classifier; tiebreak label wins; excluded from the confirmed-only subset |

Precedence:

1. Classifier agrees with a non-null deterministic signal → `confirmed`. No
   tiebreak result overrides it; an audit-sample tiebreak on such a mention is
   recorded and counted in H3 only.
2. A tiebreak triggered by disagreement or low confidence wins when it
   disagrees with the classifier (`contested`) and confirms when it agrees
   (`confirmed`).
3. A mention that would have triggered a tiebreak but hit the 40 % cap keeps
   the classifier label (`model_only`, `overflow = true`).

---

## Hypotheses

| Id | Hypothesis | Threshold | Stopping rule |
|---|---|---|---|
| **H1** | Brand + 3 competitors, all-in cost < $5 | `< $5` total, where `total_usd = monid_usd + llm_usd` and `elevenlabs_usd` is a breakout of `monid_usd`, not additive | Measured from frozen demo receipt; pass if `receipt.totals.total_usd < 5` |
| **H2** | Design effect ≥ 1.5 on thread-clustered comment sources | `≥ 1.5` | Measured at bootstrap from `by_source.design_effect`; pass if `design_effect ≥ 1.5` on each of `reddit` and `youtube_comment` that meets minimums; `tiktok` and `instagram` (author-clustered) are reported, not scored |
| **H3** | Classifier–tiebreak agreement on audit sample ≥ 0.85 | `≥ 0.85` | 10 % fixed audit (seed 777); pass if `receipt.audit.agreement ≥ 0.85` |
| **H4** | Zero-mention brand still costs > $0 | `> $0` | Avenza run yields a receipt; pass if `receipt.totals.total_usd > 0` even when `mentions.fetched = 0` |
| **H5** | 50-label blind hand check agreement ≥ 0.85 | `≥ 0.85` | 50 relevant mention–brand rows from the frozen demo, all brands pooled, seed 777, stratified by source in proportion; the rater sees text only (no rationale, deterministic signal, source, or brand label); agreement is raw agreement with the final `label`; pass if `agreement ≥ 0.85`; published either way |

---

## Threshold index

The published-claims test asserts each of these equals the constant in
`src/sonar/config.py`:

- 95 %, B=2000 live, B=10000 frozen demo, seed 777
- α=0.05 (Holm); `p_holm` governs SIGNIFICANT, `p_raw` governs SUGGESTIVE
- window_days = 14; periods `[now − 7 d, now)` and `[now − 14 d, now − 7 d)`
- abstain at n_clusters < 5 or n < 20 in either period
- events: n_day ≥ max(5, median + 3·MAD), n_clusters_day ≥ 3, 14-day baseline
  excluding the tested day, UTC days
- tiebreak: confidence < 0.6, cap 40 %, audit 10 %
- topics: average-linkage cosine distance cut 0.35, min_size 3, min_breadth 2
- H1: < $5; H2: ≥ 1.5 on reddit and youtube_comment; H3: ≥ 0.85;
  H4: > $0; H5: ≥ 0.85 on 50 labels, seed 777

---

## Amendments

Each amendment is a `docs/DECISIONS.md` entry plus a version bump, as the
banner requires. Prior values are quoted; the sections above show the new
values.

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
- [F2, F11] Abstain reasons: `no_timestamps` removed and replaced by the
  per-source `wow_scope` flag; `below_minimum`, `halted`, `embedding_failed`,
  `signals_conflict` added; Instagram wording is "items lacking a timestamp".
- [F3] H2: prior "for youtube_comment"; new scored on `reddit` and
  `youtube_comment` from `by_source.design_effect`.
- [F4] H3 reads `receipt.audit.agreement`; overflow count is
  `receipt.audit.tiebreak_overflow`.
- [F5] Null estimates are paired with an `Abstention` row.
- [F6] Window fixed at 14 days; periods stated; minimums per period.
- [F9, F10, F17] Two-signal precedence 1–3, overflow case, denominators.
- [F15] Resampling frame: one global index over `(brand, cluster_key)`.
- [F16] Topic cut 0.35, `min_size 3`, `min_breadth 2` added to the threshold
  index.
- [F18] Share minimums use `SovEntry.n`; net minimums use `SentimentEntry.n`.
- [F19] Event baseline excludes the tested day; UTC days; `baseline_mad` and
  `threshold` published.
- [F24] H1: prior "total (Monid + LLM + ElevenLabs)"; new
  `total_usd = monid_usd + llm_usd`, ElevenLabs a breakout.
- [F25] H5 sampling frame, seed, stratification and blinding defined.
- [F26] A1 recorded above.
