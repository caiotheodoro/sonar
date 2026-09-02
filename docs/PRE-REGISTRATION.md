# PRE-REGISTRATION — sonar statistics plan

**Version**: 1.0.0
**Frozen**: 2026-09-02 (design reference: `docs/research/2026-09-02-task-graph-and-design.md`)

> **FROZEN TEXT.** Any change to the thresholds, rules, or hypotheses below
> after this freeze date is a **DECISIONS.md entry** (not an edit to this file).
> The entry must state the prior value, the new value, rationale, and reversal
> clause. This banner and the version line above are never modified by edits.

---

## Estimands

1. **Share of voice (share)**: `n_brand / Σn` over `basis_sources` (sources that
   contributed ≥ 1 mention to any brand in the brief).
2. **Net sentiment (net)**: `(pos − neg) / (pos + neg + neu)`.
3. **Week-over-week (WoW) delta**: split at `now − 7 d`; delta in share and net.

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

Holm-adjusted α = **0.05** over brands × {net, share}.

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

where `n_day` and `n_clusters_day` are computed over the 7-day rolling window
per brand.

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

## Done-check

Every numeric threshold in this file:

- 95 %, B=2000, B=10000, seed 777
- α=0.05
- n_clusters < 5, n < 20
- n_day ≥ max(5, median + 3·MAD), n_clusters_day ≥ 3
- H1: < $5; H2: ≥ 1.5; H3: ≥ 0.85; H4: > $0; H5: ≥ 0.85, 50 labels
