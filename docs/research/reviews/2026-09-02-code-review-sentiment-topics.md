# Review — `src/sonar/sentiment/`, `src/sonar/topics/`

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result
**Checked against**

| Key | Source |
|---|---|
| PRE-REG | `docs/PRE-REGISTRATION.md` v1.1.2 — §Two-signal labelling policy table and precedence 1-4, relevance row as amended by A4/D014, §Threshold index |
| CONTRACTS | `CONTRACTS.md` schema_rev 1.1.2 — §Mention (`match_kind`), §Label, `Signals`, §Two-signal policy, §Topic |
| DECISIONS | `docs/DECISIONS.md` D012 F9/F10/F17 (precedence + denominators), D013 N5 (`model_only`) and A2 (rule 4), D014 (relevance by context; Reddit split) |
| CONFIG | `src/sonar/config.py` — `TIEBREAK_CONFIDENCE_THRESHOLD`, `TIEBREAK_CAP_FRACTION`, `AUDIT_SAMPLE_FRACTION`, `RATING_NEGATIVE_MAX`/`RATING_POSITIVE_MIN`, `RATIONALE_MAX_WORDS`, `PROMPT_REV`, `SEED`, `TOPIC_MIN_SIZE`/`TOPIC_MIN_BREADTH`/`TOPIC_LINKAGE`/`TOPIC_DISTANCE_THRESHOLD`/`TOPIC_EXEMPLARS`/`TOPIC_NAME_MAX_WORDS` |
| LLM SEAM | `src/sonar/llm/base.py`, `src/sonar/llm/fake.py` |

Severity: **S1** wrong published number; **S2** contract violation; **S3**
style, clarity, or documentation drift with no behavior change.

Verification method: read every file in `src/sonar/sentiment/`,
`src/sonar/topics/` and `src/sonar/llm/base.py`/`fake.py` line by line against
the cited sections; ran the existing suite
(`uv run python -m pytest tests/test_rules.py tests/test_labeler.py
tests/test_topics.py -q`, 392 passed); ran `ruff check` and `mypy` over the
three packages (clean). Wrote eight throwaway probe scripts under
`/private/tmp/claude-501/.../scratchpad/` (`uv run python`, no network, the
fake LLM only) that execute the code directly rather than trust its
docstrings:

- `probe_cap.py` / `probe_cap2.py`: `rules.plan_tiebreaks` over brand sizes
  0..1000, both with no triggers (audit-only) and with every row triggered
  (worst case for the cap); checked the audit sample size equals
  `floor(0.10·n)` exactly, the call set never exceeds `floor(0.40·n)`, and
  both are reproducible under the same seed and order-independent under a
  reshuffle of the row list.
- `probe_precedence.py`: precedence rule 1 (`rules.corroborate` with a
  disagreeing audit-only tiebreak on a classifier/deterministic agreement —
  decision stays `confirmed`), overflow end-to-end through `Labeler.run`
  (`signals.overflow=True` rows are `model_only`, keep the classifier label,
  and `run.audit.tiebreak_overflow` matches the count), and the label cache
  end-to-end (second run over the same mention returns `status="cached"`,
  `usage={0, 0.0}`, and zero backend calls).
- `probe_rule4_and_failed.py`: precedence rule 4 (audit-only trigger on a
  null deterministic signal at confidence ≥ 0.6 is never adopted even when
  it disagrees), a failed tiebreak call, and a tiebreak that returns a
  non-adoptable answer (`label="irrelevant"` or `about_brand=False`) — all
  three land on `model_only`/`decided_by=classifier` per D013 N5.
- `probe_topics_determinism.py` / `probe_topics_determinism3.py`: regenerated
  `tests/golden/topics.json` with `SONAR_UPDATE_GOLDEN=1` five times in a row
  (identical sha256 each time) and diffed a reshuffled-row-order rebuild
  against the canonical one.
- `probe_topics_order.py`: isolated the one real order-dependence found (see
  Confirmed correct, not a finding) by building two brands with one topic
  each and swapping which brand's rows come first.
- A one-off `lex.score(...)` check of six PT/EN sentences (positive,
  negative, with and without an explicit negation phrase) against
  `sonar.sentiment.lexicon.load_lexicon()`.

No repo file was edited except this one.

---

## Verdict: **PASS**

No S1 or S2 finding. The two-signal policy (`rules.py`), its wiring into the
batched labeler and cache (`labeler.py`, `cache.py`), the PT/EN lexicons, and
the topics builder (`build.py`, `cluster.py`, `estimate.py`, `name.py`) match
PRE-REGISTRATION v1.1.2 and CONTRACTS 1.1.2 on every point the task asked to
probe, confirmed by direct execution, not just by reading. Two S3 items
(documentation drift and one hardcoded constant) are listed below as an
independent, disjoint fix list; neither moves a published number or changes
behavior.

---

## S3 — style, clarity, documentation drift

### F1. Three files still cite PRE-REGISTRATION v1.1.0/v1.1.1, not the current v1.1.2

- `src/sonar/config.py:4` — module docstring: `` docs/PRE-REGISTRATION.md`` (v1.1.0, frozen 2026-09-02, amended same day by D012 A1/A2; ...)``. The file is current (2026-09-02) is now v1.1.2 with D012, D013 and D014 all applied; the docstring names only D012 A1/A2 and the wrong version.
- `src/sonar/sentiment/rules.py:1` — module docstring: `"""The two-signal labelling policy, exactly as PRE-REGISTRATION v1.1.1 and CONTRACTS §Label state it.`. The relevance row it implements (`is_relevant`, line 73-75) is already correct for v1.1.2/D014 (it only checks `matched_terms` non-empty, agnostic to `match_kind`, which is exactly what D014 requires), so this is a citation lag, not a behavior gap.
- `src/sonar/sentiment/lexicon_pt.txt:1` and `src/sonar/sentiment/lexicon_en.txt:1` — header comments cite "PRE-REGISTRATION v1.1.1".
- Not a behavior bug (verified: every numeric policy constant matches v1.1.2's Threshold index exactly, and `is_relevant` needs no change for D014). But this repo's own discipline (`docs/DECISIONS.md`, the PRE-REGISTRATION banner) is built on exact doc/code traceability, and a reviewer chasing "why does this say v1.1.1" in these four files wastes time confirming what this review already confirmed.

### F2. `RATIONALE_MAX_CHARS = 200` is a hardcoded number, not a `config.py` constant

- `src/sonar/llm/base.py:54` — `RATIONALE_MAX_CHARS = 200`, used at `base.py:300` (`LabelObservation.rationale` `max_length`) and `base.py:336` (`LabelAnswer.rationale` `max_length`), and again in `clip_rationale` (`base.py:243-248`).
- Contrast with the line directly below it, `base.py:55`: `RATIONALE_MAX_WORDS: int = config.RATIONALE_MAX_WORDS`, which correctly sources the frozen 20-word cap from `config.py`. `RATIONALE_MAX_CHARS` has no counterpart in `config.py` and no `docs/DECISIONS.md` entry (D004 only fixes "≤ 20-word rationale", no character cap).
- Low risk in practice — 200 chars comfortably fits 20 English or Portuguese words (verified: no test or fixture rationale is anywhere near the limit) — but it is exactly the kind of literal the task asked to check for, and it sits one line below a correctly-sourced sibling constant, which makes the inconsistency easy to miss on a future edit.

---

## Confirmed correct (probed by execution, not just read)

- **Tiebreak invoked exactly when policy says**: `rules.tiebreak_trigger` and
  `rules.plan_tiebreaks` — audit sample always called
  (`plan_tiebreaks`, `rules.py:188-208`), triggered-not-audited rows called
  in `published_at` order up to the cap, the rest `overflow`. Verified for
  brand sizes 0..1000 both with zero triggers and with every row triggered.
- **Never more than 40 % of a brand's rows get a tiebreak call**: `cap =
  floor(0.40·n)` is enforced by `TiebreakPlan.__post_init__`
  (`rules.py:179-185`, raises if the call set ever exceeds the cap); probed
  up to `n=1000` with every row triggered, `len(call)/n` never exceeded
  0.40.
- **Audit sample is exactly 10 %, seed 777, reproducible**:
  `rules.audit_sample_size`/`rules.audit_sample` (`rules.py:117-133`) use
  `math.floor(0.10·n)` over `sorted(set(mention_ids))` with
  `np.random.default_rng(config.SEED)`; identical result across repeated
  calls and across a reshuffled input row order (the sort inside
  `audit_sample` canonicalizes it).
- **Precedence rule 1** (classifier agreeing with a non-null deterministic
  signal cannot be overridden by a tiebreak, audit-sample or otherwise):
  `rules.corroborate` (`rules.py:256-258`) checks this before looking at
  `triggered` at all; probed directly with a disagreeing audit tiebreak on a
  confirmed row — decision stays `confirmed`, `decided_by=classifier`.
- **Precedence rule 4** (an audit-only tiebreak on a null deterministic
  signal, classifier confidence ≥ 0.6, is never adopted): `corroborate`'s
  final branch (`rules.py:281-283`); probed with a disagreeing tiebreak —
  decision stays the classifier's label, `model_only`.
- **Overflow rows are `model_only` with `overflow=true`**:
  `corroborate` rule 3 (`rules.py:260-263`) and end-to-end through
  `Labeler.run`; `run.audit.tiebreak_overflow` matched the observed overflow
  count exactly in every probe.
- **Cache keyed by `(mention_id, prompt_rev, model)`, hits return
  `status="cached"`**: `LabelCache.get`/`.put` (`cache.py:83-113`) key
  exactly on that tuple and refuse to store anything but an `ok`
  observation; `rules.build_label`'s `cached = classifier_cached and
  tiebreak is None` (`rules.py:369`) correctly downgrades to
  `status="ok"` (not `"cached"`) whenever a tiebreak call actually ran, so a
  `Label` is never marked `cached` while carrying nonzero `usage` — this
  matches CONTRACTS' `usage: {0, 0.0} when cached` rule exactly. Probed
  end-to-end with a persisted on-disk cache across two `Labeler` instances:
  second run makes zero backend calls.
- **Rationale capped at 20 words**: sourced from `config.RATIONALE_MAX_WORDS`
  (`llm/base.py:55`), enforced by `clip_rationale` and by pydantic
  validators on both `LabelObservation.rationale` and
  `LabelAnswer.rationale` (`llm/base.py:251-256, 302-305, 340-345`).
- **Lexicon sign, PT and EN**: `Lexicon.score`/`.sign`
  (`lexicon.py:85-90`) merge both language tables and match longest-first at
  word boundaries so a negated phrase (`não recomendo`, `do not recommend`)
  wins over its positive sub-word; probed six PT/EN sentences, all signed
  correctly, including the negation cases.
- **Topics clustering deterministic**: `tests/golden/topics.json`
  regenerated identically (same sha256) across five separate
  `SONAR_UPDATE_GOLDEN=1` runs.
- **`min_size 3` / `min_breadth 2` enforced, threshold from config**:
  `build_topics` (`build.py:172-182`) raises if `TopicMethod`'s defaults
  ever drift from `config.TOPIC_LINKAGE`/`TOPIC_MIN_SIZE`/`TOPIC_MIN_BREADTH`;
  a cluster becomes a topic only if `c.n >= method.min_size and
  c.n_clusters >= method.min_breadth` (`build.py:217-219`); the golden file's
  `method` block on every topic reads `{"threshold": 0.35, "min_size": 3,
  "min_breadth": 2}`, matching `config.py` exactly.
- **Medoid exemplars**: `medoid_indices` always returns exactly
  `config.TOPIC_EXEMPLARS` (3) members nearest the cluster centroid, ties by
  row index (`cluster.py:75-91`); every topic in the golden file carries
  exactly 3 `exemplar_mention_ids`.
- **Names at most six words**: `name.py`'s `cap_words(name, max_words=
  config.TOPIC_NAME_MAX_WORDS)` (`name.py:58-61`); the golden fixture's
  7-word canned model answer (`CANNED_NAME`, `test_topics.py:75-76`) comes
  back capped to exactly 6 words in every topic.
- **Null `share`/`net` below minimums**: `build_topics` computes
  `counts.total`/`polar_breadth` from `_polar_units` separately from cluster
  membership and nulls both `share` and `net` (with a `below_minimum`
  abstention naming the topic) whenever either falls short of
  `TOPIC_MIN_SIZE`/`TOPIC_MIN_BREADTH` (`build.py:242-264`); this is a
  deliberate two-tier design (cluster membership vs. the labelled-polarity
  gate for the statistic), explicitly documented in the module docstring
  and locked in by `tests/test_topics.py::TestBuild::
  test_null_estimates_are_paired_with_below_minimum` and
  `test_polar_breadth_below_minimum_is_null_even_with_enough_labels` — not a
  bug, despite `Topic.n` counting a cluster member whose final label
  happens to be `irrelevant`.
- **Golden regenerates identically**: confirmed above (five-run sha256
  match); note that `TopicsResult.topics`/`.abstentions` order is a function
  of the *caller's* row order (`_brand_order`, `build.py:128-132`, "first
  appearance"), which is intentional and explicitly locked in by
  `test_topics.py::TestBuild::
  test_brands_are_independent_and_ordered_by_first_appearance` — not a
  determinism bug, since the golden fixture (and, presumably, the pipeline)
  always assembles rows in one canonical order.

---

## Fix list (numbered, independently applicable, disjoint files)

1. **F1 (S3)** — `src/sonar/config.py:4-6`,
   `src/sonar/sentiment/rules.py:1`, `src/sonar/sentiment/lexicon_pt.txt:1`,
   `src/sonar/sentiment/lexicon_en.txt:1`: update the cited
   PRE-REGISTRATION version from v1.1.0/v1.1.1 to v1.1.2 (and, in
   `config.py`, name D013/D014 alongside D012 A1/A2). Comment-only change,
   four files, no behavior change, no test to update.
2. **F2 (S3)** — `src/sonar/llm/base.py:54`: move `RATIONALE_MAX_CHARS`
   into `src/sonar/config.py` as a named constant (or add a one-line
   comment explaining why it is deliberately not a frozen PRE-REGISTRATION
   number and stays local), mirroring how `RATIONALE_MAX_WORDS` is already
   sourced on the very next line. Single file if kept local-with-comment;
   two files (`config.py` + `llm/base.py`) if moved.
