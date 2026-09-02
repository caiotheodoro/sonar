# PRE-REGISTRATION — sonar statistics plan

**Version**: 1.0.0
**Frozen**: 2026-09-02 (design reference: `docs/research/2026-09-02-task-graph-and-design.md`)

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
3. **Week-over-week (WoW) delta**: split at `now − 7 d` by `published_at`;
   delta in share and net. Mentions with `published_at = null` count for
   share but are excluded from WoW and from events, and their source is
   listed under `what_could_not_be_checked`.

---

## Cluster bootstrap

| Parameter | Value |
|---|---|
| Bootstrap unit | `cluster_key` (per source: reddit → post id; youtube_comment → video id; tiktok/instagram → author_hash; reviews/news/youtube video → mention_id) |
| Resampling | shared resample indices (paired deltas across brands) |
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
| **SIGNIFICANT** | Full-set 95 % CI **and** confirmed-only 95 % CI both exclude 0, same sign |
| **SUGGESTIVE** | Full-set 95 % CI excludes 0, confirmed-only includes 0 |
| **NO_CHANGE_DETECTED** | Full-set 95 % CI includes 0 (minimums met) |
| **ABSTAIN** | Minimums not met (see abstention thresholds below) |

---

## Abstention thresholds

A brand's share and net estimates are set to **ABSTAIN** when **either**:

- `n_clusters < 5` in either the current or previous week, **or**
- `n < 20` mentions in either the current or previous week.

Abstained sources leave `basis_sources` for **every** brand (not just the
abstaining brand).

**Abstain reasons** (per source or brand):

| Reason | Trigger |
|---|---|
| `empty` | zero fetched mentions from provider |
| `provider_failed` | Monid status BLOCKED/FAILED/STOPPED or provider 4xx–5xx |
| `rate_limited` | Monid 429 (retry exhausted) |
| `deadline` | TIMED_OUT / exceeded deadline |
| `unavailable` | endpoint absent (e.g. X/Twitter) |
| `schema_drift` | AdapterSchemaError (raw saved) |
| `no_timestamps` | no timestamp field in response (Instagram) |

---

## Event rule

A date is flagged as an **event** when:

```
n_day ≥ max(5, median + 3·MAD)
    AND
n_clusters_day ≥ 3
```

where `median` and `MAD` are taken over the daily counts of the full
14-day window per brand, and `n_clusters_day` is the number of distinct
`cluster_key` values on that day. Both signals are required: volume alone
(one viral thread) is not an event.

---

## Two-signal labelling policy

The model supplies observations; code decides. Thresholds frozen here:

| Parameter | Value |
|---|---|
| Relevance | `about_brand` (model) **and** `matched_terms ≠ ∅` (regex); both required |
| Deterministic signal | rating bucket for review sources: ≤ 2 negative, 3 neutral, ≥ 4 positive; lexicon sign otherwise |
| Tiebreak trigger | classifier disagrees with the deterministic signal, **or** no deterministic signal and classifier `confidence < 0.6` |
| Tiebreak cap | at most **40 %** of a brand's mentions; beyond the cap, mentions stay `model_only` and the overflow count is published in the receipt |
| Audit sample | a fixed **10 %** of mentions (seed 777) always sent to the tiebreak model, for H3 |
| `contested` | tiebreak disagrees with classifier; tiebreak label wins; excluded from the confirmed-only subset |

---

## Hypotheses

| Id | Hypothesis | Threshold | Stopping rule |
|---|---|---|---|
| **H1** | Brand + 3 competitors, all-in cost < $5 | `< $5` total (Monid + LLM + ElevenLabs) | Measured from frozen demo receipt; pass if `receipt.totals.total_usd < 5` |
| **H2** | Design effect ≥ 1.5 on comment sources | `≥ 1.5` | Measured at bootstrap; pass if `design_effect ≥ 1.5` for youtube_comment |
| **H3** | Classifier–tiebreak agreement on audit sample ≥ 0.85 | `≥ 0.85` | 10 % fixed audit (seed 777); pass if `agreement ≥ 0.85` |
| **H4** | Zero-mention brand still costs > $0 | `> $0` | Avenza run yields a receipt; pass if `receipt.totals.total_usd > 0` even when `mentions.fetched = 0` |
| **H5** | 50-label blind hand check agreement ≥ 0.85 | `≥ 0.85` | 50 labels rated blind (rationale hidden); pass if `agreement ≥ 0.85`; published either way |

---

## Threshold index

The published-claims test asserts each of these equals the constant in
`src/sonar/config.py`:

- 95 %, B=2000 live, B=10000 frozen demo, seed 777
- α=0.05 (Holm)
- abstain at n_clusters < 5 or n < 20 in either week
- events: n_day ≥ max(5, median + 3·MAD), n_clusters_day ≥ 3, 14-day baseline
- tiebreak: confidence < 0.6, cap 40 %, audit 10 %
- H1: < $5; H2: ≥ 1.5; H3: ≥ 0.85; H4: > $0; H5: ≥ 0.85 on 50 labels
