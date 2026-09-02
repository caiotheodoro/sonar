# Review — CONTRACTS.md and PRE-REGISTRATION.md against the design appendix

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result
**Documents compared**

| Key | File |
|---|---|
| D | `docs/research/2026-09-02-task-graph-and-design.md`, Appendix §Contracts (L207–216), §Pipeline rules (L218–226), §Statistics (L228–235); §Error matrix (L237–253) and §Endpoint reference (L255–272) consulted where the other two cite them |
| C | `CONTRACTS.md` (schema_rev 1.0.0) |
| P | `docs/PRE-REGISTRATION.md` (v1.0.0, frozen 2026-09-02) |

State at review time: `docs-frozen` tag is already on HEAD (`c5c3d69`), so every
fix below is a `docs/DECISIONS.md` entry plus a `schema_rev` / version bump, not
an edit to C or P.

Severity: **S1** blocks a stated hypothesis or makes a record unrepresentable;
**S2** two documents disagree or a rule has an unassigned case; **S3** wording
gap that an implementer could reasonably read two ways.

---

## Verdict: **FAIL**

Six S1 findings (F1–F6). Field-for-field, C reproduces every record of D
§Contracts and P reproduces every threshold of D §Statistics (checked line by
line, no field of D is absent from C). The failures are in rules that the three
documents state differently, or that no document states, and each one changes a
number that will be published.

---

## S1 — blocks a hypothesis or makes a record unrepresentable

### F1. Holm p versus CI: which governs the verdict word
- P L50–53: "Raw and Holm-adjusted p are both reported; **the adjusted one governs the verdict word**."
- P L55–60: the verdict table is written entirely in terms of 95 % CIs excluding or including 0, with no reference to p.
- C L269–277: verdict defined by CIs; `p_holm` "Holm-adjusted at α = 0.05", reported alongside, not used in the rule.
- D L232: "SIGNIFICANT iff full-set and confirmed-only CIs both exclude 0 same sign … Holm α=0.05 over brands × {net, share}." Both mechanisms named, relation unstated.

A 95 % percentile CI excluding 0 is equivalent to raw p < 0.05, not to Holm-adjusted p < 0.05. With 8 tests (brand + 3 × {net, share}) the two rules will disagree on real data. P contradicts itself; C and D pick the CI rule silently. Resolve in DECISIONS: either (a) verdict from `p_holm` with CIs as display, or (b) verdict from CIs and Holm demoted to a reported number. The threshold index (P L138) and `tests/test_published_claims.py` must assert whichever one wins.

### F2. `no_timestamps` is both a source-level abstention and a partial exclusion
- P L84: `no_timestamps` is an abstain reason, "no timestamp field in response (Instagram)".
- P L71–72 and D L233: "abstained sources leave `basis_sources` for **every** brand".
- P L24–27 and C L377 (OQ-4): mentions with `published_at = null` "count for share but are excluded from WoW and from events".
- C L114: `published_at` is `null` for "YouTube comments; Instagram hashtag items without one"; D L261 confirms youtube_comment has no timestamp.

Read literally, a source with no timestamps abstains with `no_timestamps`, therefore leaves `basis_sources`, therefore does **not** count for share. That contradicts P L25. It also removes `youtube_comment` from every bootstrap, which is the one source H2 (P L125) is scored on. Needs a single rule: either `no_timestamps` is a WoW/events-scope flag (not an `Abstention` that removes a source from `basis_sources`), or the OQ-4 text is wrong. Also fix the Instagram wording: P L84 says Instagram has no timestamp field; C L114 says only some items lack one.

### F3. H2 is not computable from any contract field
- D L235: "H2 design effect ≥ 1.5 on **comment sources**" (C L43–44 defines comment sources as reddit, youtube_comment, tiktok, instagram).
- P L125: "pass if `design_effect ≥ 1.5` **for youtube_comment**" — narrowed to one source without a DECISIONS entry.
- C L256: `design_effect` exists only on `SentimentEntry`, one per brand over all sources.
- C L257: `BySourceEntry` has `n, n_clusters, pos, neg, neu, net` — no `ci95`, no `ci95_iid`, no `design_effect`.

No record carries a per-source design effect, so the H2 stopping rule cannot be evaluated from `digest.json` or `receipt.json`. (`docs/RED-TEAM.md` L115 says it is scored from `results/demo/stats.json`, a file no contract defines.) Either add `ci95`, `ci95_iid`, `design_effect` to `BySourceEntry`, or define a `stats.json` record in C, and make D and P agree on "comment sources" versus "youtube_comment".

### F4. H3 agreement and the tiebreak overflow count have no field
- P L114: "the **overflow count is published in the receipt**" (mentions past the 40 % tiebreak cap).
- P L126: H3 "pass if `agreement ≥ 0.85`" on the 10 % audit sample.
- C L231–244 (`Totals`), C L212–229 (`Receipt`), C L250–264 (`Digest`): no field for tiebreak overflow, audit-sample size, or classifier–tiebreak agreement.

H3 is unreproducible from the artifacts and P's own promise about the receipt is unmet by C. Add e.g. `Receipt.audit {n_sample, n_agree, agreement, tiebreak_overflow}` or an equivalent.

### F5. Zero-mention brand cannot be serialised
- D L242 (Error matrix): zero mentions (Avenza) → "all abstain", exit 0; H4 (P L127) requires this receipt to exist.
- C L255: `SovEntry.share: float`, `ci95: CI95` (two floats).
- C L256: `SentimentEntry.net: float`, `ci95: CI95`, `ci95_iid: CI95`, `design_effect: float` — none nullable. With `pos + neg + neu = 0`, `net` is 0/0; with zero-width iid CI, `design_effect` is division by zero. JSON has no NaN.
- C L257 makes `BySourceEntry.net` `float | None`, so the authors saw the case once and missed it twice.

Every estimate on `SovEntry` and `SentimentEntry` (and `Topic.net`/`ci95`, C L201–202, when a cluster has only `irrelevant` labels) must be `T | None`, with the null case tied to a brand-level `Abstention`. Same for `WowNet.delta`/`ci95` on `ABSTAIN` (C L266–267: only `p_raw`/`p_holm` are nullable).

### F6. 14-day baseline hard-coded while `window_days` is 1–31
- C L87: `window_days: int = 14`, rule "1–31".
- C L254: `previous = [now − window_days, now − 7 d)` — empty or inverted for `window_days ≤ 7`; unequal weeks for any value other than 14.
- P L98–99: median and MAD "over the daily counts of the **full 14-day window**"; P L140 threshold index: "14-day baseline".
- P L68–69 and C L273: minimums are stated per "week", assuming two equal weeks.
- D L209: `window_days=14` only as a default; D L231: "WoW split at now − 7 d".

Either freeze `window_days = 14` for any run that produces `wow` or `events` (and say so in C L87), or restate P in terms of `window_days` (baseline over the full window, previous period `[now − window_days, now − 7 d)`, minimums per period) and admit unequal periods. Today P's threshold index will fail against a config that honours C.

---

## S2 — contradictions and unassigned cases

### F7. Verdict rule has no branch for opposite-sign CIs
- P L57–60, C L270–273, D L232: SIGNIFICANT needs same sign; SUGGESTIVE needs confirmed-only to include 0; NO_CHANGE_DETECTED needs full-set to include 0. When the full-set CI and the confirmed-only CI both exclude 0 with **opposite** signs, none applies and the only remaining word is ABSTAIN, whose stated trigger (minimums not met) is false. Assign it explicitly (SUGGESTIVE or a fifth word).

### F8. Share of voice can never be SIGNIFICANT, but only C says so
- C L273–275: no confirmed-only interval for share, so "`SIGNIFICANT` and `SUGGESTIVE` coincide and the entry reports `SUGGESTIVE`".
- P L55–60: verdict table applied to "share and net" (P L66) with a confirmed-only column that is undefined for share.
- D L232: Holm family is brands × {net, share}, implying share is tested on equal footing.
- D L215: the design's `share_of_voice` entry has **no** `wow` at all; C L255/L267 add `WowShare` and record it as OQ-7 (C L380). D §Contracts and D §Statistics disagree with each other here; C's resolution needs the lead's sign-off to become the design.

### F9. Corroboration is double-assigned in the audit-sample case
- C L136: `confirmed` = "classifier agrees with deterministic signal, **or** tiebreak agrees with classifier"; `contested` = "tiebreak disagreed with classifier and won".
- C L150–153 (c) and P L115: audit-sample mentions are always tiebroken, including those where classifier already agrees with the deterministic signal.
- D L223: "disagrees → tiebreak wins, `contested`".

Audit mention, classifier = deterministic = positive, tiebreak = negative: `confirmed` by the first clause and `contested` by the second, and the tiebreak overrides a 2-to-1 majority. State the precedence and decide whether tiebreak wins against a corroborated classifier.

### F10. Corroboration undefined for cap overflow
- P L114: beyond the 40 % cap "mentions stay `model_only`".
- C L136: `model_only` requires "no deterministic signal … or tiebreak failed". A mention whose classifier **disagrees** with a non-null deterministic label but is not tiebroken because the cap is hit satisfies none of `confirmed`, `model_only`, `contested`, `irrelevant`.
- D L223: silent on overflow.

Add the overflow case to C L136 (and decide whether the deterministic label or the classifier label is `label` in that case).

### F11. Three abstain reasons exist only in C
- D L233 and P L76–84: seven reasons.
- C L66–74: adds `below_minimum`, `halted`, `embedding_failed`, and C L69–70 defines `below_minimum` as the P L66–69 brand-level rule, which P names but gives no reason code.
- P's frozen banner (L6–9) says any new value is a DECISIONS entry. There is none. Either P gains the three codes via DECISIONS or C drops them and the Error matrix rows for 402 (D L244), embedding failure (D L250) and brand minimums have no representation.

### F12. `Mention.run_id` is non-nullable but `RunRecord.run_id` is not
- C L108: `Mention.run_id: str`.
- C L166: `RunRecord.run_id: str | None`.
- C L375 (OQ-2): $0 sync endpoints (`tinyfish /search`, `/fetch`) may return no `runId`; D L268–269 and L272 say Apify is async with a run id and say nothing about sync endpoints.

A news mention from a run with no run id cannot be emitted. Make `Mention.run_id` nullable or reference `local_seq` instead (`raw_ref` at C L119 already does).

### F13. `run_id = null` rows cannot be reconciled by the stated mechanism
- C L359–361: a `run_id = null` row reaches `cost_source = "/v1/runs"` "when the listing confirms no run was created for its `input_digest` window".
- D L272: `GET /v1/runs` items carry `runId, status, providerResponse.httpStatus, price, cost, billedUnits` — no input digest, no request echo.

The listing cannot confirm absence by `input_digest`. Consequence: any locally rejected POST makes RECONCILED unreachable (C L352–354, D L214), so H1's demo receipt fails `sonar verify` if a single 429 exhausts. Define the actual rule (time-window count match, or treat `LOCAL_*` rows as reconciled by construction).

### F14. `lite` profile competitor limit is not a Query validator
- D L220: "`lite` … ≤ 1 competitor".
- C L86: `competitors` length 0–3 with no profile dependence; C L91–93 validator order does not mention profile.
- Either C adds a profile-aware validator (exit 2 per D L241) or D's `lite` cap is a soft estimate note. Unstated today.

### F15. Bootstrap resampling frame is described three ways
- D L230: "shared resample indices (paired deltas)" — pairing across the two weeks.
- P L36: "shared resample indices (paired deltas **across brands**)".
- C L269: "`delta` = current − previous, paired on shared resample indices".

Is the resampling frame the set of `cluster_key`s per brand, per (brand, period), or one global index over all clusters so that both WoW and cross-brand share are paired? A `cluster_key` (reddit post) can span both weeks and be attributed to two brands. The choice changes every CI. State it in P.

---

## S3 — ambiguities

### F16. Topic clustering threshold has no value anywhere
- D L191 "thresholds" in config; D L224 no number; C L204 "`threshold` is the cosine-distance cut from `config`"; P: topics not covered, and P L134–142 threshold index omits `min_size 3`, `min_breadth 2`, and the cut. Topics feed events (`label`, C L259). Publish the value or state that it is tuned on the demo and say so in RED-TEAM.

### F17. Denominators for "10 %" and "40 %" are unstated
- D L223, P L114–115, C L152–153: "10 % of mentions", "40 % of mentions per brand". Of Mention rows, of relevant rows, per brand or per session, before or after dedup? A mention kept twice (two brands, one `mention_id`, C L98–101) may be sampled once or twice. H3's denominator depends on this.

### F18. `n` in the minimums is two different counts
- P L68–69 / D L233 / C L273: `n < 20`. `SovEntry.n` (C L255) counts mention–brand pairs over `basis_sources`; `SentimentEntry.n` (C L256) counts relevant mentions. Which `n` gates ABSTAIN for share, and which for net?

### F19. Event record omits MAD
- C L259: `Event` carries `baseline_median` but not the MAD or the threshold; the rule at P L93 cannot be re-derived from the digest. Also unstated: whether the tested day is included in the baseline, and whether "day" is UTC (C L19 implies yes; P silent).

### F20. Two fields named `numbers_verified` with different types
- C L264 `Narration.numbers_verified: bool`; C L290 `Answer.numbers_verified: list[str]`; D L215/L216 give both without types. Rename one.

### F21. `stats.json` and `topics.json` referenced but undefined
- C L290 and `docs/RED-TEAM.md` L115 reference `stats.json`; C L290 references `topics.json`; C L248 defines only `digest.json` and C L208 `receipt.json`. Either these are files with records in C, or the Answer rule should cite Digest fields.

### F22. `excluded_with_reason` keys do not match the pipeline
- C L226 keys ⊂ {`not_about_brand`, `no_matched_terms`, `refused`, `unparseable`, `error`}. `no_matched_terms` can never occur (C L118: a Mention with no match is never emitted). `label = irrelevant` with `about_brand = true` (C L136) has no key, and dedup removals are only implied by `fetched − deduped`.

### F23. "by engagement" ordering undefined
- C L260 `top_mentions` "≤ 10 per brand by engagement"; `engagement` (C L115) is a dict with heterogeneous keys (views vs upvotes vs likes). D L215 silent. Define the sort key.

### F24. H1 total written as a triple sum
- P L124: "total (Monid + LLM + ElevenLabs)"; C L243–244: `elevenlabs_usd` is a breakout of `monid_usd`, `total_usd = monid_usd + llm_usd`. Same number, but P's wording invites double-counting. Reword P.

### F25. H5 sampling unspecified
- P L128 / D L235: "50 labels rated blind". Population (per brand? all brands? relevant only?), seed, and whether the rater sees the deterministic signal are not stated. C L133 only says `rationale` is hidden.

### F26. Frozen file edited after freeze without a version bump
- P L3–9: v1.0.0, frozen 2026-09-02, "never modified by edits". Commit `56240f2` ("gate corrections …") changed thresholds text after `f51c0a8` created the file; version unchanged, no DECISIONS entry. Same calendar day, so arguably inside the freeze, but the "gate corrections" are exactly the class of change the banner routes to DECISIONS. Record them there or bump to 1.0.1.

---

## Confirmed consistent (no action)

- Source enum: D L210, C L34, P L35 (via cluster_key list) — same ten values.
- `mention_id` construction: D L210, C L300–305.
- `cluster_key` table: D L210, C L312–323, P L35.
- Dedup precedence: D L221, C L335–346.
- Rating buckets ≤2 / 3 / ≥4: D L223, C L148, P L112.
- Tiebreak trigger `confidence < 0.6`, cap 40 %, audit 10 %, seed 777: D L223, C L150–153, P L113–115, P L141.
- Bootstrap B=2000 live / 10000 frozen, seed 777, 95 %, design effect formula: D L230, C L23, P L33–41.
- Event rule `max(5, median + 3·MAD)` and `n_clusters_day ≥ 3`: D L234, C L259, P L93–95.
- Receipt verdict `RECONCILED` condition: D L214, C L352–358.
- `basis_sources` semantics: D L233, C L255/L261, P L15–18/L71–72.
- H1, H3, H4, H5 thresholds: D L235, P L124–128.
- Every record and field of D §Contracts appears in C with the same name.

---

## Minimum to flip to PASS

DECISIONS entries (with `schema_rev` bump for C, version bump for P) resolving F1–F6. F7–F15 should land in the same entries where they touch the same rule (F1+F7+F8 verdict rule; F2+F11 abstain reasons; F3+F4 hypothesis fields; F9+F10+F17 two-signal policy; F12+F13 run ids). S3 items can be closed by a one-line clarification each.
