# sonar — red team

Attacks on sonar's own claims, written before any code, data, or demo
exists. Each attack has a fixed severity and a fixed "landed if" test, so the
outcome cannot be renegotiated after the numbers come in. The response to a
landed attack is also fixed here. Results are appended under **Outcome** by
the lead only, at the trigger named for each attack; the attack text above
the Outcome line does not change after the `docs-frozen` tag.

**Severity scale (pre-committed)**

| Severity | Meaning | Required response |
|---|---|---|
| S1 Fatal | A headline claim (the kill, the price, "live data") is false | Fix before submission or withdraw the claim from README, video, and form |
| S2 Major | A published number or scope statement must change | Correct README, `docs/PRE-REGISTRATION.md` results block, and `docs/DECISIONS.md`; republish the receipt |
| S3 Minor | Disclosure only | Footnote in README and `what_could_not_be_checked` in the receipt |

**Scoring rule.** An attack is scored exactly once, at its trigger, by
running its "How we would know" check. It lands if the "Landed if" condition
holds. A landed attack is published in README under "Red team results" with
its severity, whether or not that is flattering. An attack that cannot be
scored by Sep 10 is published as "unscored", with the reason.

**Sources of truth referenced below**: `CONTRACTS.md` (records),
`docs/PRE-REGISTRATION.md` (thresholds, H1–H5), `docs/COVERAGE.md`
(Brand24 source map), `docs/HANDOFF.md` (spend ledger),
`results/demo/receipt.json` (frozen demo receipt), `results/incumbent/`
(price evidence), `results/handcheck/` (H5 sheet).

## 1. The scraped sample is not Brand24's sample

**Attack.** sonar's mentions are whatever ten Apify actors and TinyFish
return for a keyword search sorted by newest, capped at 40 per source.
Brand24 sells a crawler with a 10,000-mention quota and its own ranking.
Share of voice and net sentiment are therefore measured on a different
population, and any sentence that reads "sonar gives you Brand24's numbers
for cents" is false even if every number in sonar is right.

**If it lands.** Two `full` runs on the same brand a day apart produce
share-of-voice intervals that do not overlap, or a source Brand24 lists as
high-volume for the demo brand contributes fewer than 5 mentions in sonar.
A judge who knows Brand24 reads the receipt as a toy.

**How we would know.** (a) `docs/COVERAGE.md` has one row per Brand24
source stating covered, partial, or not, with the cap; (b) README "Scope
not claimed" says the population differs and sonar reports a brief with
intervals, not Brand24's dashboard; (c) at W8.2, the rehearsal run on the
demo brand is compared to the frozen demo: share-of-voice `ci95` per brand
must overlap; (d) `make check-claims` greps README, `video/src/data/
narration.json`, and the X post text for "same numbers", "Brand24's
numbers", "identical", "all social media".

**Landed if.** Any artifact equates sonar counts with Brand24 counts, or
the W8.2 share-of-voice intervals are disjoint from the demo intervals for
any brand.

**Severity.** S1 if the wording lands (the kill claim is overstated); S2 if
only the interval check lands (the brief is unstable and README must say
so, with both runs' intervals side by side).

**Outcome.** Open until W8.2 completes. Wording check runs at every
`make check-claims` from W5.4 on.

## 2. The sentiment model is biased between Portuguese and English

**Attack.** The demo brand is Brazilian. `gpt-5.6-luna` labels English
sarcasm and Portuguese sarcasm with different accuracy, the Portuguese
lexicon is thinner than the English one, and the deterministic rating
signal only exists on review sources. H3 (classifier versus tiebreak
agreement) and H5 (hand check) are pooled across languages, so a bad
Portuguese stratum hides under a good English one, and net sentiment for
the Brazilian brand is biased in a direction we cannot see.

**If it lands.** Agreement in the `pt` stratum is more than 0.10 below the
`en` stratum, or either stratum is below 0.80 while the pooled number
clears 0.85. Net sentiment per brand shifts by more than its `ci95` when
recomputed on confirmed-only labels within one language.

**How we would know.** The H5 hand-check sheet under `results/handcheck/`
is drawn stratified by `lang` with at least 15 rows per language present
in the demo (proportional above that), and agreement is computed per
stratum before pooling. The 10 % audit sample for H3 reports agreement per
`lang` in `results/demo/stats.json`. `sonar render` prints the confirmed-only
net sentiment per language stratum next to the pooled one.

**Landed if.** Per-language agreement gap exceeds 0.10 on H3 or H5, or
either language stratum is below 0.80 on H5.

**Severity.** S2. README publishes per-language agreement, never a pooled
number alone, and the Brazilian brand's net sentiment is reported with
the `pt` stratum caveat.

**Outcome.** Open until W7.6 (hand check finished) for H5 and W6.1 for H3.

## 3. The cluster key is wrong, so intervals are too narrow

**Attack.** The cluster bootstrap only protects the intervals if
`cluster_key` groups mentions that are genuinely correlated: comments
under one Reddit post, comments under one YouTube video, posts by one
TikTok author. If an actor returns comments without their parent id, or
the adapter falls back to `mention_id` as the key, every comment becomes
its own cluster, `design_effect` collapses to 1.0, and a verdict of
SIGNIFICANT is reached on intervals that are too narrow.

**If it lands.** `design_effect` on comment sources is below 1.5 (H2
fails), `n_clusters` equals `n` on a comment source, or the fraction of
comment-source mentions whose `cluster_key` equals their `mention_id`
exceeds 20 %.

**How we would know.** `tests/test_stats.py` property: `n_clusters ≤ n` and
`design_effect ≥ 1` for every source. Adapter tests on the recorded
fixtures assert that every `youtube_comment` carries a `videoId` and every
Reddit comment carries a post id; a missing parent id on more than 20 % of
a source's rows raises `AdapterSchemaError` and the source abstains with
`schema_drift`. `results/demo/stats.json` records `design_effect` per
source; H2 is scored there.

**Landed if.** H2 fails on the frozen demo, or the 20 % fallback threshold
is crossed on any comment source in the demo.

**Severity.** S1 for verdicts: every SIGNIFICANT verdict in the demo is
downgraded to SUGGESTIVE in README and the digest, and the receipt lists
`cluster_key_fallback` under `what_could_not_be_checked`. The price claim
is unaffected.

**Outcome.** Open until W6.1.

## 4. The real cost is hidden in OpenAI spend

**Attack.** The headline "$349 versus cents" quotes `monid_usd`. The
labeling, tiebreak, embeddings, topic naming, chat answers, and narration
all run on OpenAI, whose receipt is a separate dashboard. Terra tiebreak at
$2/$12 per million tokens on up to 40 % of mentions can cost more than
every Monid run combined. The receipt also cannot see OpenAI retries that
were billed but returned nothing.

**If it lands.** `total_usd` on the receipt is less than the sum of
`monid_usd`, `llm_usd`, and `elevenlabs_usd`; or the OpenAI usage export for
the demo window exceeds the receipt's `llm_usd` by more than 10 %; or any
headline number in README, the video, or the X post is `monid_usd` rather
than `total_usd`.

**How we would know.** `tests/test_receipt.py` asserts `total_usd` is the
exact sum. `make check-claims` asserts the README price line and
`narration.json` quote `total_usd` from `results/demo/receipt.json`. At
W6.2 the lead exports the OpenAI usage for the demo session's time window,
files it as `results/demo/openai-usage.csv`, and records the difference in
`docs/HANDOFF.md`. The comparison line on the receipt states
`briefs_per_month_assumed = 4` so the monthly equivalent is a stated
multiplication, not a guess.

**Landed if.** Any headline number is not `total_usd`, or the OpenAI export
differs from `llm_usd` by more than 10 %.

**Severity.** S1. The headline is replaced by `total_usd`; if the export
disagrees, both numbers are published and the larger one is used in the
video and form.

**Outcome.** Open until W6.2. The wording check runs at every
`make check-claims` from W5.4 on.

## 5. The X gap

**Attack.** Monid has no X endpoint. Brand24 covers X. For a Brazilian
fintech, a large share of complaints happens on X, so sonar's share of
voice omits the source where the argument is loudest, and any claim of
"social listening" or "kills Brand24" is a partial kill at best.

**If it lands.** A judge asks "where is Twitter?" and finds no answer in
the receipt or README, or any artifact uses "all social media", "every
platform", or "everything Brand24 monitors".

**How we would know.** `providers/x.py` is registered `available=False`
with a date, so every run lists X under `coverage_gaps` and the receipt's
`what_could_not_be_checked`. `docs/COVERAGE.md` has an X row marked "not
covered, no Monid endpoint as of 2026-09-02". README "Scope not claimed"
names X first. `make check-claims` greps for the three phrases above.

**Landed if.** Any of the three phrases appears in a published artifact,
or the X gap is missing from `coverage_gaps` in the demo digest.

**Severity.** S2 if the phrases land (scope statement corrected); S3
otherwise (already disclosed). Pre-committed reversal: if Monid ships an X
endpoint before Sep 10, the D-entry in `docs/DECISIONS.md` for "X only"
records whether it was added, and the receipt keeps the gap line until the
demo is re-frozen.

**Outcome.** Scored at every `make check-claims` from W5.4 on; final at W8.1.

## 6. Homonym brands poison the sample

**Attack.** "Inter" matches Inter Milan, Internacional, and every "inter-"
prefix; "Avenza" matches Avenza Maps; a short brand name matches its own
common-noun meaning. Keyword actors return them all. If the relevance gate
(`about_brand ∧ matched_terms`) leaks, share of voice and topics for the
competitor are about football, and if it over-filters, the competitor is
under-counted and the demo brand's share is inflated.

**If it lands.** For any brand, `irrelevant` exceeds 40 % of matched
mentions, a topic medoid for a bank is a football match, or the H5 hand
check finds `about_brand` wrong on more than 3 of 50 rows.

**How we would know.** `tests/test_text.py` has table-driven homonym
negatives for every demo brand and competitor alias, in Portuguese and
English. `brand_hint` is passed to the classifier prompt and frozen under
`PROMPT_REV`. The receipt reports `mentions.excluded_with_reason` per brand
with `irrelevant` as a named reason. The hand-check sheet has an
`about_brand` column scored separately from sentiment.

**Landed if.** `irrelevant` above 40 % for any brand in the demo, or more
than 3 of 50 `about_brand` disagreements on H5.

**Severity.** S2. The affected brand is reported with its irrelevant rate
beside its share, and its topics are dropped from README.

**Open question (OQ-1).** Whether a brand-level abstention at
`irrelevant > 40 %` belongs in the pre-registration. Resolved by the lead at
the Wave 1 gate when W1.2 is reviewed; if adopted, the threshold enters
`config.py` and this attack's "Landed if" becomes the abstention.

**Outcome.** Open until W7.6.

## 7. The demo brand was cherry-picked

**Attack.** The author picks a brand with rich, polite data, runs `full`
several times, and freezes the prettiest session. The receipt looks great
because it was selected, not because the tool works.

**If it lands.** `docs/HANDOFF.md` shows more than one `full` session for
the demo brand and README does not say so, or the brand was chosen after
the first live data came back.

**How we would know.** The demo brand and its three competitors are named
in a `docs/DECISIONS.md` entry dated before W3.7 (the first live run).
Every live session id is appended to the HANDOFF ledger at submission
time, including discarded ones, because the ledger is opened before POST.
The W8.2 rehearsal runs on a brand never used before, as a judge would, and
its receipt is committed under `results/rehearsal/` unedited. The
Avenza empty run is published beside the demo as `results/demo-empty/`.

**Landed if.** The brand decision postdates the first live run, or any
`full` session on the demo brand is missing from HANDOFF, or the
rehearsal receipt is not committed.

**Severity.** S2. README states how many `full` sessions were run, why the
frozen one was chosen, and links every session's receipt.

**Outcome.** Open until W8.2.

## 8. A replay is passed off as live

**Attack.** The video shows `sonar render --from results/demo` while the
narration says "live". The hackathon mandates live data and a visible
Monid call. If a judge cannot tell replay from live, the submission is
either disqualified or looks dishonest.

**If it lands.** A frame in the video shows numbers from the frozen demo
without the REPLAY banner while the narration or caption says "live", or
a run id shown on screen does not resolve in `GET /v1/runs`.

**How we would know.** The Receipt carries `replay: true` and
`verdict: REPLAY` whenever it was rendered from disk, and `sonar render`
prints a REPLAY banner on the first line. The "live POST /v1/run trace"
beat in `video/README.md` is captured from a real `sonar run --profile
lite --trace` at W7.3, and the run ids visible in that cast are listed in
HANDOFF with their `GET /v1/runs` status. `sonar verify` exits nonzero on
a REPLAY receipt, so the demo receipt shown beside $349 is the RECONCILED
one.

**Landed if.** Any video frame pairs a replay screen with the word "live",
or any on-screen run id is absent from the HANDOFF ledger.

**Severity.** S1. The scene is re-recorded from a live run before W7.5
completes; if that is impossible, the caption says "replay of the
2026-09-06 session" on that frame.

**Outcome.** Open until W7.5 (phone review of the cut).

## 9. The incumbent price drifts or is the wrong tier

**Attack.** Brand24 changes prices, renames the tier, or the $349 figure is
monthly billing while a judge sees the annual figure on the same page. The
comparison against Brand24 Team then cites a price that no longer exists,
or compares against a tier that does not offer the mention quota sonar's
receipt assumes.

**If it lands.** brand24.com/prices on Sep 9 shows a different number for
the tier with a 10,000-mention quota, or shows $349 only under one billing
cadence while README does not name the cadence.

**How we would know.** `results/incumbent/brand24-2026-09-02.png` and
`archive-url.txt` are the evidence; `report/incumbent.py` holds
`price_usd_month = 349`, `checked_at`, `billing = monthly`, and
`mentions_quota = 10000`. `make check-claims` asserts the number is
identical across `report/incumbent.py`, README, and the demo receipt. W8.1
re-checks the page and files a second dated screenshot.

**Landed if.** The Sep 9 screenshot differs from the Sep 2 screenshot in
tier name, price, or quota, or README omits the billing cadence.

**Severity.** S2. All three copies are updated through `check-claims` in
one commit, `docs/DECISIONS.md` gets an entry with both screenshots, and
the video is re-rendered only if the number itself changed.

**Outcome.** Open until W8.1.

## 10. Empty sources inflate share of voice

**Attack.** A source fails or is rate-limited for one competitor but not
for the demo brand. The competitor gets zero from that source, the demo
brand keeps its 40, and share of voice moves in the demo brand's favour
because of an outage, not the market. A subtler version: a legitimately
empty source (Avenza has no Google Maps reviews) is treated as a failure
and removed from `basis_sources` for everyone, shrinking the denominator.

**If it lands.** Share of voice for the demo brand moves by more than its
`ci95` when a single source is removed, or `basis_sources` in the digest
differs between brands, or a zero-result run is recorded as `abstain`
rather than `n_results = 0`.

**How we would know.** Pre-registration rule: an abstained source leaves
`basis_sources` for every brand. `tests/test_stats.py` asserts that
failing a source for one brand removes it for all brands and that
`n_results = 0` with `status = SUCCEEDED` stays in the basis as a zero.
`RunRecord` distinguishes the two by `status` and `n_results`. The digest
prints `basis_sources` on the share-of-voice row. A leave-one-source-out
sensitivity table is written to `results/demo/stats.json`.

**Landed if.** `basis_sources` differs across brands in the demo, or the
leave-one-source-out table moves any brand's share outside its `ci95`.

**Severity.** S2. README reports share of voice with `basis_sources` named
and the sensitivity table linked; if fewer than 5 of 10 sources are in the
basis, the share-of-voice claim is withdrawn from the video.

**Outcome.** Open until W6.1.

## 11. Tiebreak volume swallows the cost claim

**Attack.** The two-signal policy sends every disagreement and every
low-confidence label to `gpt-5.6-terra`, ten times Luna's price. If most
mentions are contested, tiebreak dominates `llm_usd`, H1 (brief under $5)
fails, and the "cheap" claim rested on Luna doing work that Terra actually
did. If the 40 % cap is hit, the remaining contested labels are kept as
`model_only` without saying so, biasing net sentiment toward the
classifier.

**If it lands.** `llm_calls.tiebreak / mentions.labelled` reaches 0.40 for
any brand, or `llm_usd` exceeds `monid_usd`, or labels beyond the cap are
not counted separately.

**How we would know.** The receipt reports `llm_calls` by kind and the
labeler emits `tiebreak_cap_hit` with the number of contested labels left
as `model_only`. `tests/test_labeler.py` asserts the fake backend counts
tiebreak calls exactly as the policy matrix predicts, and that hitting the
cap marks the remainder. H1 is scored on `total_usd` including tiebreak.
`results/demo/stats.json` reports the tiebreak rate and the confirmed-only
net sentiment beside the full-set one, which is what the SIGNIFICANT
verdict already requires.

**Landed if.** Tiebreak rate at the cap for any brand in the demo, or
`llm_usd > monid_usd`, or H1 fails.

**Severity.** S2 for the cost claim (README shows the split and the brief
cost is published as measured); S1 if H1 fails, since "under $5" leaves
README and the form.

**Outcome.** Open until W6.1.

## 12. The hand check was done by the author

**Attack.** H5's 50-label check is scored by the person who wrote the
prompt and knows what the model tends to say. Agreement is inflated by
shared priors even when the model's label is hidden, and "0.85 agreement"
reads as independent validation when it is not.

**If it lands.** H5 clears 0.85 while a second rater, or the same rater on
a second blind draw, lands below 0.80; or the sheet was labelled with the
model column visible.

**How we would know.** The sheet under `results/handcheck/` is drawn with
a logged seed, the model label and rationale are in a separate file not
opened until the author's column is committed, and the commit order proves
it. Both raw agreement and Cohen's kappa are published. README calls it
"author, blind to the model label", never "independent". The published
sheet includes both columns so anyone can re-score.

**Landed if.** The author's labels are committed after the model column
was unhidden (commit order), or kappa is below 0.60 while raw agreement is
above 0.85 (agreement driven by class imbalance).

**Severity.** S2. H5 is published with kappa and the single-rater caveat;
if the commit order is wrong, H5 is published as "not blind" and excluded
from the video.

**Open question (OQ-2).** Whether a second rater is available before W7.6.
Resolved by the lead by Sep 6 evening; if yes, inter-rater kappa replaces
the single-rater caveat, and if no, the caveat stands.

**Outcome.** Open until W7.6.

## 13. Comparison mentions are counted twice

**Attack.** A post that names the demo brand and a competitor is kept once
per brand, so share of voice counts mention–brand pairs. A thread of
"Nubank versus Inter" comparisons inflates both brands, and the denominator
is pairs rather than mentions, which a reader will not expect.

**If it lands.** `mentions.by_brand` sums to more than 1.3 times
`mentions.deduped` in the demo, and README says "mentions" where it means
pairs.

**How we would know.** The receipt reports `fetched`, `deduped`, and
`by_brand`; the digest's share-of-voice header says "mention–brand pairs".
`make check-claims` requires the word "pairs" on the README share-of-voice
line. `results/demo/stats.json` reports share computed on pairs and on
unique mentions assigned to the first matched brand, side by side.

**Landed if.** The pair ratio exceeds 1.3 without the README disclosure,
or the two share computations disagree in brand ranking.

**Severity.** S3 if disclosed; S2 if the ranking flips.

**Outcome.** Open until W6.2.

## 14. The frozen numbers do not reproduce

**Attack.** "Fresh clone reproduces `stats.json` at seed 777 offline"
fails because the bootstrap's random stream depends on the numpy version,
the order of mentions on disk, or B=10000 in the demo versus B=2000 in the
default config. Then the reproduction claim is false and the intervals in
README are unverifiable.

**If it lands.** `make validate` in a temp clone regenerates a
`stats.json` whose `ci95` values differ from the committed file at any
decimal that is printed.

**How we would know.** W8.1 performs the fresh-clone reproduction per
`docs/REPRODUCTION.md` and diffs the regenerated `stats.json` against the
committed one. `pyproject.toml` pins numpy, the resampler uses
`numpy.random.default_rng(777)` with shared indices, mention order is
sorted by `mention_id` before resampling, and the receipt records `B` so
the reproduction uses the same value.

**Landed if.** Any printed interval differs on the fresh clone.

**Severity.** S2. The reproduction claim is removed from README until the
diff is empty; the intervals stay, marked "as computed on 2026-09-06".

**Outcome.** Open until W8.1.

## 15. Reconciliation ran before billing settled

**Attack.** `GET /v1/runs` may list a run with `cost` not yet final. If
`reconcile` runs seconds after the last poll, the receipt says RECONCILED
with a cost lower than what the wallet is charged, and the measured cost
the hackathon asks for is understated.

**If it lands.** The wallet balance delta across the demo session differs
from the receipt's `monid_usd` by more than $0.05, or a re-reconcile 24
hours later changes any run's `cost_usd`.

**How we would know.** HANDOFF logs the wallet balance before and after
every `$` task. The demo receipt is re-reconciled at least 24 hours after
W6.1 and the diff is recorded in HANDOFF; if any `cost_usd` changed, the
receipt is re-frozen and `make check-claims` re-run.

**Landed if.** Wallet delta differs from `monid_usd` by more than $0.05, or
the 24-hour re-reconcile changes any cost.

**Severity.** S1 if the difference changes the headline at the printed
precision; S3 otherwise.

**Outcome.** Open until Sep 7 (24 hours after W6.1).

## 16. Sources without timestamps leak into week-over-week

**Attack.** YouTube comments carry no timestamp; Instagram may not. If
these are assigned the video's date, or the fetch date, the week-over-week
split at now − 7 days puts every comment into the current week, and the
delta is an artefact of the assignment rule, not of the market.

**If it lands.** `youtube_comment` or `instagram` appears in any
week-over-week row of the digest, or the current-week count for those
sources equals their total.

**How we would know.** The abstain reason `no_timestamps` is
pre-registered; adapters set `published_at = null` when the payload has no
timestamp, and `tests/test_stats.py` asserts that null-dated mentions are
excluded from week-over-week and counted in share of voice only. The
digest's `wow` block lists the sources it is based on.

**Landed if.** A no-timestamp source appears in the week-over-week basis
of the demo digest.

**Severity.** S2. The week-over-week verdict is recomputed without those
sources and README states the basis.

**Outcome.** Open until W6.1.

---

**Open questions**

| Id | Question | Resolved by |
|---|---|---|
| OQ-1 | Does `irrelevant > 40 %` trigger a brand-level abstention? | Lead at the Wave 1 gate, reviewing W1.2 |
| OQ-2 | Is a second rater available for H5? | Lead by Sep 6 evening, before W7.6 |
| OQ-3 | Does Monid's `GET /v1/runs` cost field settle synchronously with run completion? | Lead at W3.7, by comparing the first smoke receipt against the wallet balance |
