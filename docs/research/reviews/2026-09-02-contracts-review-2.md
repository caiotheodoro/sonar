# Review 2 — CONTRACTS 1.1.0 and PRE-REGISTRATION v1.1.0 against D012

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result, no memory of the first review beyond its text
**Documents compared**

| Key | File |
|---|---|
| D012 | `docs/DECISIONS.md` L374–493, entry "Resolutions to the CONTRACTS / PRE-REGISTRATION review (F1–F26)" |
| C | `CONTRACTS.md`, `schema_rev` 1.1.0 (commit `b615b51`) |
| P | `docs/PRE-REGISTRATION.md` v1.1.0 (same commit) |
| R1 | `docs/research/reviews/2026-09-02-contracts-review.md` (findings F1–F26) |

State at review time: `docs-frozen` tag is on `b615b51` (HEAD), moved from
`c5c3d69` as D012 says. RED-TEAM 17 (commit `9d77954`) exists and matches
D012 F16.

Question asked per finding: do C and P now state D012's resolution
**exactly** — same rule, same fields, same values — and did the new text
create a contradiction that 1.0.0 did not have.

Severity as in R1: **S1** blocks a hypothesis or makes a record
unrepresentable; **S2** two statements disagree or a rule has an
unassigned case; **S3** wording an implementer could read two ways.

---

## Verdict: **FAIL**

Twenty-three of twenty-six findings are implemented exactly. Two are not
(F5, F10). Six new S2 contradictions were introduced by the amendments,
each fixable with one sentence; four S3 ambiguities are listed but not
required. Minimum list at the end.

---

## Per-finding check

### F1 + F7 + F8 — verdict rule
**Implemented.**
- P L55–58: family brands × {net WoW, share WoW}; two-sided bootstrap p; adjusted p governs. P L60–65: the four rows match D012 L383–392 word for word (SIGNIFICANT `p_holm < 0.05` and, for net, confirmed-only CI same sign as the full-set point estimate; share by `p_holm` alone; SUGGESTIVE `p_raw < 0.05` and not SIGNIFICANT; NO_CHANGE `p_raw ≥ 0.05` minimums met; ABSTAIN minimums not met or opposite-sign CIs, `signals_conflict`). P L67–69: CIs are display; share WoW confirmed, eight tests.
- C L301–302: `WowNet` / `WowShare` shapes; `WowShare` has no `ci95_confirmed_only`. C L304–319: the same four rules. C L445: OQ-7 resolved. P L176: threshold index names `p_holm` / `p_raw`.

**New contradiction N1 (S2).** The SUGGESTIVE row and the `signals_conflict`
ABSTAIN row overlap and no evaluation order is stated. If the full-set
and confirmed-only CIs exclude 0 with opposite signs, the full-set CI
excludes 0, so `p_raw < 0.05` (percentile CI excluding 0 is equivalent to
two-sided bootstrap `p < 0.05` on the same resamples); the test is not
SIGNIFICANT (wrong sign); therefore SUGGESTIVE by P L63 / C L314 **and**
ABSTAIN by P L65 / C L317–319. D012 L383–392 has the same overlap; both
documents reproduce it verbatim. This is the exact class F7 asked to
close. One sentence fixes it: ABSTAIN is evaluated first.

**New contradiction N2 (S2).** Holm family size when a test abstains.
`p_raw` / `p_holm` are `null` on `below_minimum` (C L321). With the
adjusted p now governing the verdict word, `m` in the Holm step-down
must be either the eight nominal tests or the count of non-null `p_raw`;
the two give different `p_holm` and can give different words. Neither
D012 nor P L55 nor C L306–307 says which. Latent in 1.0.0 (Holm was
display then); governing now.

### F2 + F11 — abstain reasons and `wow_scope`
**Implemented.**
- P L91–102: ten reasons; `no_timestamps` absent; `below_minimum`, `halted`, `embedding_failed`, `signals_conflict` present with D012's triggers. P L104–107: "Items lacking a timestamp (all `youtube_comment` items; some Instagram hashtag items)", source stays in `basis_sources`, `wow_scope = false`. P L28–32 same in the estimand text.
- C L72–81: identical list, same triggers, `no_timestamps` explicitly not an abstention. C L123: `published_at` null for "YouTube comments; Instagram hashtag items without one". C L263: example sentence reworded. C L292: `wow_scope: bool` on `BySourceEntry`. C L442: OQ-4 resolved.

**Ambiguity A1 (S3).** For a mixed source (Instagram, some items with
timestamps) the two documents point different ways. C L292 sets
`wow_scope=false` "iff the source's items carry no `published_at`"
(reads: all items), so Instagram would be `wow_scope=true` with null
items dropped one by one per P L28–29. P L30 and L104–107 say the null
items' "source is flagged `wow_scope = false`" (reads: any null item flags
the whole source), which drops timestamped Instagram items from WoW too.
D012 L393–399 does not decide it. Changes the brand's net WoW `n`.

### F3 — H2 fields and scope
**Implemented.**
- C L292: `BySourceEntry` gains `ci95`, `ci95_iid`, `design_effect`, all `| None`; "H2 reads `design_effect` on `reddit` and `youtube_comment`". C L46–50: comment-source paragraph restates scoring and the reported-not-scored pair.
- P L163: H2 measured from `by_source.design_effect`, pass iff `≥ 1.5` on each of `reddit` and `youtube_comment` "that meets minimums"; `tiktok`, `instagram` reported, not scored. P L183 threshold index agrees.

**New contradiction N3 (S2).** "Meets minimums" is undefined for a
`BySourceEntry`. The only minimums in either document are brand-level
and **per period** (P L75–83, C L74–75, L289), and C L292 nulls
per-source estimates only "under the same rule as `SentimentEntry`"
(brand abstains or `pos + neg + neu = 0`). Read literally, a
`youtube_comment` entry can never be assigned to a period because its
items have no `published_at` (P L104–105, F2), so the per-period minimum
cannot be evaluated on the one source H2 was rewritten to keep. Created
by F2 + F3 + F6 together. One sentence: H2 minimums are `n_clusters ≥ 5`
and `n ≥ 20` on the `BySourceEntry` over the whole window.

### F4 — audit fields
**Implemented.** C L261: `audit {n_sample, n_agree, agreement, tiebreak_calls, tiebreak_overflow}` with each term defined; "H3 reads `audit.agreement`". P L140: overflow published in `receipt.audit.tiebreak_overflow`. P L164: H3 pass iff `receipt.audit.agreement ≥ 0.85`.

### F5 — nullability
**Partly implemented.**
- Types: C L290 (`SovEntry.share`, `ci95`), L291 (`SentimentEntry.net`, `ci95`, `ci95_iid`, `design_effect`), L292 (`BySourceEntry` same), L231–233 (`Topic.share`, `net`, `ci95`), L301–302 (`WowNet` / `WowShare` `delta`, `ci95`, `ci95_confirmed_only`, `p_raw`, `p_holm`) are all `T | None`. Matches D012 L408–412.
- Pairing: C L296 "every `null` estimate in this Digest is paired with exactly one `Abstention` row naming the brand, the source (or `null`) and the reason"; C L237–238 for Topic; P L86–87.

**New contradiction N4 (S2).** Two nulls the documents themselves
introduce have no `AbstainReason`. (i) C L291–292:
`design_effect` is `null` "when the iid width is 0" — reachable with
minimums met (twenty relevant mentions all `positive` gives a
zero-width CI in every resample); the brand has not abstained, so
`below_minimum` is false and no other reason in C L72–78 / P L91–102
applies. (ii) C L301: `ci95_confirmed_only` is `null` when
`n_confirmed = 0` while the full set meets minimums; same gap. C L296
requires a row for each, so the pairing invariant D012 F5 states cannot
be satisfied by the enum D012 F2/F11 fixes. Either exempt these two
fields from pairing or add a reason.

### F6 — window
**Implemented.** C L94 (`window_days` "fixed at 14 in v1 (validator: `== 14`)"), L101 (validator order), L289 (periods `[now − 7 d, now)` and `[now − 14 d, now − 7 d)`, minimums per period), L294 (14-day baseline excluding the tested day). P L25–27, L78–79, L121–122, L177.

### F7 — opposite-sign case
**Implemented** as ABSTAIN `signals_conflict` (P L65, L102; C L317–319, L321–323: intervals and p kept, only the word abstains). See N1: the assignment is made but is not exclusive.

### F8 — share WoW
**Implemented.** P L68–69; C L302 (no confirmed-only interval), L313, L445 (OQ-7 "Resolved: D012 F1/F8").

### F9 + F10 + F17 — two-signal policy
**F9 implemented, F17 implemented, F10 not exactly.**
- Precedence: C L171–183 rules 1–3 with `decided_by` and `label` stated per rule; P L145–154 the same three rules. Rule 1's "audit tiebreak recorded and counted in H3 only" is at C L174–176 / P L147–149. Matches D012 L417–426.
- `Signals.overflow`: C L158.
- Denominators: C L166–169 and P L142 reproduce D012 L426–429 verbatim.
- `contested`: C L145, P L143.

**New contradiction N5 (S2) — F10 not exactly implemented.** C L145
defines `model_only` as "**no deterministic signal** and no tiebreak
adopted (classifier confidence ≥ 0.6, tiebreak failed, or
`signals.overflow=true`)". The overflow case D012 F10 adds (L423–426) is a
mention that met trigger (a): classifier **disagrees with a non-null
deterministic label** and the cap is hit. That mention has a deterministic
signal, so it fails the first clause of C L145 while C L158, C L180–183,
P L140 and P L153–154 all assign it `model_only`. The same clause
excludes the "trigger (a) fired, tiebreak call failed" case. The
`Corroboration` enum has no other value for it, so the record is
unrepresentable under L145 and representable under L180 — precisely the
F10 defect, now stated on one line of the same document instead of two
documents. Fix: drop "no deterministic signal and" from L145 and let the
three bracketed cases stand.

**Ambiguity A2 (S3).** Trigger (c) alone — audit-sample mention with a
null deterministic signal and classifier confidence ≥ 0.6 — whose
tiebreak disagrees with the classifier is covered by none of rules 1–3
(rule 1 needs a non-null signal; rules 2–3 need trigger (a) or (b)).
The `contested` definition ("a tiebreak triggered by disagreement or low
confidence") implies the audit tiebreak is never adopted, so
`model_only` follows by elimination, but no sentence says so.

### F12 + F13 — run ids and reconciliation
**Implemented.**
- C L117: `Mention.run_id: str | None`, `raw_ref` via `local_seq`. C L64: `CostSource` gains `local`. C L196, L204, L210: `RunRecord` rules. C L214–218: totals. C L416–426: verdict rule, `RECONCILED` iff every row with a `run_id` has `cost_source="/v1/runs"` and `unmatched_remote_run_ids` is empty; `run_id=null` rows reconciled by construction. C L440: OQ-2 provisional value updated.

**New contradiction N6 (S2).** D012 L430–435 equates `run_id = null`
with `LOCAL_*` statuses. C L440 (OQ-2) creates a third kind of row: a
**successful** `$0` sync run with `run_id=null`, `cost_source="local"`.
C L215 says "a `local` row … is counted in `monid_runs_failed`"; C L274
counts `monid_runs_failed` by status ("Monid failure states and every
`LOCAL_*`"), which a succeeded sync run is not. The receipt card prints
`monid_runs_failed`. Also C L210's parenthetical "(every `LOCAL_*`
status)" is false for `LOCAL_DEADLINE`, which C L204 says keeps its
`run_id`. One sentence: `local` rows are counted failed iff their
`status` is `LOCAL_*`; `LOCAL_DEADLINE` rows are `unreconciled` until
listed.

### F14 — `lite` competitor cap
**Implemented.** C L93 (`profile=lite`: 0–1), L98–101 (profile-aware validator, exit 2, position in the order stated).

### F15 — resampling frame
**Implemented.** C L325–331 (§Resampling frame) and L304; P L41. Text matches D012 L437–441: one global index over `(brand, cluster_key)`, drawn once per iteration, shared by estimand, period and brand; a cluster spanning both periods is one unit.

### F16 — topic cut
**Implemented.** C L235: `linkage: "average"`, `threshold: 0.35`, `min_size: 3`, `min_breadth: 2`, fixed in `config`, "chosen before any demo data". P L182 in the threshold index. RED-TEAM 17 (L501–526) states the same and gives the `git log -S TOPIC_DISTANCE_CUT` check.

### F18 — which `n`
**Implemented.** P L81–83; C L74–75, L290 (`SovEntry.n` gates share), L291 (`SentimentEntry.n` gates net); both per period.

### F19 — event record
**Implemented.** C L294: `baseline_median`, `baseline_mad`, `threshold`, tested day excluded, UTC days, `n_clusters ≥ 3`. P L121–126, L179–180.

### F20 — `numbers_verified`
**Implemented.** C L354 `Answer.verified_numbers: list[str]` with the rename noted; C L299 `Narration.numbers_verified: bool` unchanged.

### F21 — `stats.json`, `topics.json`
**Implemented.** C L333–341: `StatsFile` = `{share_of_voice, sentiment, by_source, events, window}` byte-identical to the Digest; `topics.json` = `Digest.topics`; same write step. RED-TEAM's `results/demo/stats.json` is `results/<session>/stats.json` for the demo session.

### F22 — `excluded_with_reason`
**Implemented.** C L260: exactly the eight keys of D012 L458–460, every key present.

### F23 — `top_mentions` order
**Implemented.** C L295: `engagement_score` = sum of numeric `engagement` values (`0` for `{}`), ties `published_at` descending (`null` last) then `mention_id` ascending; `engagement_score` added to `TopMention`. The `null`-last and ascending refinements are additions D012 did not state; they do not conflict with it.

### F24 — H1 total
**Implemented.** P L162: `total_usd = monid_usd + llm_usd`, ElevenLabs a breakout; C L278–279 unchanged and agreeing.

### F25 — H5 sample
**Implemented.** P L166 reproduces D012 L466–470: 50 relevant mention–brand rows, all brands pooled, seed 777, stratified by source in proportion, text only, raw agreement with final `label`.

**Ambiguity A3 (S3).** "In proportion" over up to ten sources into 50
slots needs a rounding rule (largest remainder, floor-then-fill, …).
Seed 777 does not fix the sample if the strata sizes differ by one.

### F26 — freeze discipline
**Implemented.** P L3 v1.1.0, L5 amended line, L194–215 A1 quotes the `56240f2` corrections with prior and new values, L217–245 A2 lists the D012 changes.

**Ambiguity A4 (S3).** The banner P L7–10 still says a post-freeze
change is "a DECISIONS.md entry (**not an edit to this file**)" and that
"the version line above [is] never modified by edits". v1.1.0 edited the
rule sections in place and changed the version line. D012 L471–473 says
"as the banner says"; the banner says the opposite. P L191 promises
"prior values are quoted" in §Amendments, but A2 quotes them for only
F1, F3, F24 (the rest give new values only); the v1.0.0 text is
recoverable solely through the `56240f2` hash in A1 because the
`docs-frozen` tag moved. Not a number, but it is the sentence a reader
uses to decide whether the pre-registration is one.

---

## Confirmed consistent (no action)

- `AbstainReason` list identical in C L72–78 and P L91–102 (ten values).
- `WowVerdict` enum C L66 has the four words the rule uses.
- `Query` validator order C L98–101 covers every rule in the table above it.
- `Receipt.audit` first-in-cap rule (C L165 "audit sample first") makes the 10 % sample immune to overflow.
- Every field D012 names exists in C under that name; every threshold D012 names appears in P's threshold index L175–184.
- CONTRACTS' own banner (L6–9) describes the in-place change mechanism it actually follows; only P's banner does not (A4).

---

## New contradictions introduced by the amendments

| Id | Severity | Where | One-line statement |
|---|---|---|---|
| N1 | S2 | P L63/L65, C L314/L317 | SUGGESTIVE and `signals_conflict` ABSTAIN both hold in the opposite-sign case; no precedence. |
| N2 | S2 | P L55, C L306–307, L321 | Holm `m` with null `p_raw` (abstained tests) unstated; `p_holm` now governs. |
| N3 | S2 | P L163 vs P L75–83, C L292 | H2 "meets minimums" undefined per source; per-period minimums unevaluable on `youtube_comment`. |
| N4 | S2 | C L291, L301 vs L296, L72–78 | `design_effect` (iid width 0) and `ci95_confirmed_only` (`n_confirmed = 0`) go null with no `AbstainReason`. |
| N5 | S2 | C L145 vs L158, L180–183, P L140, L153 | `model_only` requires "no deterministic signal"; overflow and failed-tiebreak rows have one. F10 not exactly implemented. |
| N6 | S2 | C L215 vs L274, L440; L210 vs L204 | Successful `run_id=null` sync rows counted failed by one rule and not the other; `LOCAL_DEADLINE` contradicts "every `LOCAL_*`". |
| A1 | S3 | C L292 vs P L30, L104–107 | Mixed-timestamp source: `wow_scope` false on any null item, or only when all items are null. |
| A2 | S3 | C L171–183, P L145–154 | Audit-only tiebreak on a null-signal, high-confidence mention not explicitly assigned. |
| A3 | S3 | P L166 | H5 stratification rounding rule unstated. |
| A4 | S3 | P L7–10 vs L3, L5, L191 | Banner forbids the in-place edit and version change v1.1.0 made; A2 does not quote most prior values. |

---

## Minimum to flip to PASS

One DECISIONS entry (D013) with `schema_rev` 1.1.1 and P v1.1.1, each item one sentence:

1. **N1** — P §Verdict rule and C L311–319: ABSTAIN rows are evaluated before SUGGESTIVE and NO_CHANGE_DETECTED (or append "and not ABSTAIN" to SUGGESTIVE).
2. **N2** — P L55 and C L306: Holm is applied over the tests with non-null `p_raw` (or over all `2 × brands` tests with abstained tests entered as `p = 1`); pick one.
3. **N3** — P L163 and C L292: H2's "meets minimums" is `n_clusters ≥ 5` and `n ≥ 20` on the `BySourceEntry` over the full window.
4. **N4** — C L296 (and P L86): the pairing rule applies to `share`, `net`, `ci95`, `delta`, `p_raw`, `p_holm`; `design_effect` with zero iid width and `ci95_confirmed_only` with `n_confirmed = 0` are `null` without an `Abstention` row (or add a reason such as `degenerate`).
5. **N5** — C L145: `model_only` = "no tiebreak adopted and not `confirmed`: null deterministic signal with classifier confidence ≥ 0.6, tiebreak call failed, or `signals.overflow=true`".
6. **N6** — C L210/L215/L274: a `local` row is counted in `monid_runs_failed` iff its `status` is `LOCAL_*`; a succeeded `run_id=null` sync run is `local`, `cost_usd=0.0`, not failed; `LOCAL_DEADLINE` keeps its `run_id` and is `unreconciled` until listed.

A1–A4 are recommended in the same entry (one sentence each) but not required for PASS.
