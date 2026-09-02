# Review — `src/sonar/llm/`, `src/sonar/text/`

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result
**Checked against**

| Key | Source |
|---|---|
| CONTRACTS | `CONTRACTS.md` `schema_rev` 1.1.0 — §Enumerations (`Label`, `Lang`, `LabelStatus`), §Mention, §Label, §Two-signal policy, §Dedup precedence, §mention_id rule |
| PRE-REG | `docs/PRE-REGISTRATION.md` v1.1.0 — §Two-signal labelling policy (ids round-trip or `unparseable`) |
| D003–D005 | `docs/DECISIONS.md` — Luna bulk / Terra tiebreak model ids and dated rates; usage → cost |
| DESIGN | `docs/research/2026-09-02-task-graph-and-design.md` Appendix §Module layout (L195: "only backend imports `openai`; fake for tests"), §Pipeline rules (L221: dedup precedence, "kept once per brand") |

Severity: **S1** wrong number or lost/misrepresented money; **S2** contract
violation that doesn't move a published number (or a real, currently-latent
risk of one); **S3** style or clarity.

Verification method: read all six files line by line against the cited
sections; ran `uv run pytest tests/test_llm_seam.py tests/test_text.py -q`
(85 passed, no failures); read the installed `openai==3.7.0` SDK's
`_parsing/_completions.py` and `types/completion_usage.py` to confirm which
exceptions `chat.completions.parse()` actually raises and what fields
`CompletionUsage` carries; ran a throwaway repro under
`/private/tmp/claude-501/.../scratchpad/lang_repro.py` (not committed, no
network) confirming `detect_lang`'s tie-break behavior against its own
docstring. No repo file was edited except this one.

---

## Verdict: **FAIL**

One S1 (a real gap in how OpenAI usage is priced, which feeds the receipt's
headline cost numbers) and four S2s, including one file where the function's
own docstring contradicts its own code. The probed contract points that
*are* correctly implemented: dedup precedence order and its `raw_ref`
tie-break, substring rejection in `match_terms` for PT and EN aliases, the
`Lang` closed enum (only ever returns one of the four members), missing-id →
`unparseable`-only, whole-batch refusal → `status=refused`, and the
`openai`-import boundary (enforced by an AST-based test). See §Confirmed
correct at the end.

---

## S1 — wrong number or lost/misrepresented money

### F1. Usage pricing ignores OpenAI's cached-input-token discount entirely

- `src/sonar/llm/openai_backend.py:156` (`_usage_of`): reads only
  `usage.prompt_tokens` and `usage.completion_tokens` and prices every
  prompt token at the full input rate via `self._usage(...)` →
  `Usage.price` (`src/sonar/llm/base.py:163-180`).
- The type annotation at `openai_backend.py:153`
  (`usage: openai.types.CompletionUsage | None`) is the real SDK type; its
  actual definition
  (`.venv/lib/python3.12/site-packages/openai/types/completion_usage.py:67-71`)
  carries `prompt_tokens_details.cached_tokens` — the count of prompt
  tokens served from OpenAI's prompt cache, which the real API bills at a
  reduced rate versus `prompt_tokens`. Nothing in `_usage_of`, `_usage`, or
  `Usage.price` reads or prices this field; `Usage.price`'s signature
  (`base.py:163-166`) only accepts one `input_tokens` count, so there is no
  plumbing to price a cached and an uncached portion differently even if the
  caller wanted to.
- This is not hypothetical: every `classify` call resends the same frozen
  system prompt (`ClassifyBatch.system`, D004: "prompt is frozen at
  `PROMPT_REV`"), and D003/D004 target ~1000 mentions/brand — exactly the
  repeated-prefix pattern OpenAI's prompt cache exists for. Whatever this
  code prices as `Label.usage.cost_usd` for real accounts sums, unmodified,
  into `Receipt.totals.llm_usd` and `total_usd`
  (`CONTRACTS.md:275,279`) — the number the whole project's pitch (D001,
  D002) puts on the card next to Brand24's $349/mo, and the number H1 gates
  at `< $5` (`docs/PRE-REGISTRATION.md:162`). A systematically inflated
  `llm_usd` is a wrong number on the one artifact this project is built to
  make trustworthy.
- Fix: extend `Rate` with an optional cached-input rate (or a documented
  policy of "price cached tokens at the full input rate, on purpose"),
  thread `prompt_tokens_details.cached_tokens` through `_usage_of` →
  `Usage.price`, and add a stub-harness test
  (`tests/test_llm_seam.py`) where the mock transport's `usage` block
  includes a non-zero `prompt_tokens_details.cached_tokens` and assert the
  resulting `cost_usd` reflects it. If the deliberate choice is "don't
  discount," say so in a `docs/DECISIONS.md` entry, because right now the
  omission looks unnoticed, not decided.

---

## S2 — contract violation that doesn't move a published number (yet)

### F2. `detect_lang`'s code contradicts its own docstring for mixed-language text

- `src/sonar/text/lang.py:45-50` (docstring): *"Above 0.10 → that language;
  both above 0.10 → `'other'`; fewer than 5 words → `'unknown'`."*
- `src/sonar/text/lang.py:58-60` (code):
  ```python
  if pt_ratio > 0.10 and en_ratio > 0.10:
      # Both above threshold — pick the dominant one
      return "pt" if pt_ratio >= en_ratio else "en"
  ```
  This branch never returns `"other"`; it returns whichever ratio is
  larger. Repro: `detect_lang("the a an o a os is é são i ii iii iv v vi")`
  → `"pt"` (verified by running it), even though both `pt_ratio` and
  `en_ratio` are above 0.10 and the docstring says that case is `"other"`.
- `tests/test_text.py:90-93` (`test_ambiguous_picks_dominant`) asserts the
  code's behavior (`result in ("pt", "en")`), not the docstring's — so the
  test suite is green while the module's own stated contract is false. The
  comment on `lang.py:59` ("pick the dominant one") reads like a deliberate
  design choice that was never reconciled with the docstring above it.
- `Lang` stays a valid closed-enum value either way (this is why the probe
  "does `lang` return only pt/en/other/unknown" passes), but the *policy*
  for a genuinely-mixed mention is undocumented-vs-implemented, and
  `Mention.lang` is a published stratum field (CONTRACTS.md:122) — a reader
  of the docstring, or of CONTRACTS' "detected in code by PT/EN stop-word
  ratio," has no way to know which behavior is real without reading the
  `if` branch.
- Fix: pick one behavior and make code, docstring, and test agree. Given
  the docstring is the more conservative, more clearly-specified rule (a
  genuine 50/50 mix reported as `pt` or `en` misrepresents the mention),
  the straightforward fix is to delete the "pick the dominant one" branch
  and let both-above-threshold fall through to `"other"`; update
  `test_ambiguous_picks_dominant` to assert `"other"` and add a
  clearly-one-sided case (e.g. mostly-PT with a couple of EN stopwords) to
  keep dominant-language behavior covered if it's still wanted for
  near-threshold cases below 0.10/0.10.

### F3. `dedup()`'s drop reasons are free text, not the coded reasons CONTRACTS names

- `CONTRACTS.md:260`: `Receipt.mentions.excluded_with_reason` keys are
  *exactly* `{..., dedup_native_id, dedup_url, dedup_text}` (F22, a closed
  set). `CONTRACTS.md:399-404` names the three dedup rules by number, not
  by a machine-readable tag.
- `src/sonar/text/dedup.py:76,87,97`: the three rules each append
  `(item, f"duplicate native_id of {...}")`, `f"duplicate url of {...}"`,
  `f"duplicate text_key of {...}"` — free-form prose strings, not the
  `dedup_native_id`/`dedup_url`/`dedup_text` tokens the Receipt needs.
  `DedupResult.dropped` (`dedup.py:23-28`) types this as
  `list[tuple[DedupItem, str]]` — there is no separate, stable field
  identifying *which* rule fired; a caller can only get that by parsing the
  prose.
- `tests/test_text.py:174` only checks
  `"duplicate native_id" in result.dropped[0][1]` — a substring check on
  rule 1's prose; there is no test pinning rule 2's or rule 3's wording, so
  nothing stops that prose from drifting.
- Whoever writes the not-yet-built mapping from `dedup()`'s output to
  `Receipt.mentions.excluded_with_reason` will have to string-parse
  `dropped[i][1]` to recover the rule — a landmine for the day someone
  rewords "duplicate url of" for a nicer log line and silently breaks the
  bucket counts on the card.
- Fix: give `DedupResult.dropped` a typed reason field, e.g.
  `list[tuple[DedupItem, Literal["dedup_native_id", "dedup_url", "dedup_text"], str]]`
  (coded reason plus the existing prose as detail), and add three tests —
  one per rule — asserting the exact coded value.

### F4. `dedup()` never scopes by brand; `DedupItem.brand` is unread dead code

- CONTRACTS.md:394-410 (§Dedup precedence): "Applied **per brand** after
  all runs complete... A mention matching the brand and a competitor is
  kept once per brand (two rows, one `mention_id`)." Design doc L221
  repeats: "Mention matching brand and competitor kept once per brand."
- `src/sonar/text/dedup.py:12-21` (`DedupItem`) carries a `brand: str`
  field, but `grep -n "brand" src/sonar/text/dedup.py` matches only that
  one declaration line — `dedup()` (`dedup.py:37`) and `_dedup_group`
  (`dedup.py:61`) group solely `by_source` (`dedup.py:50-52`); `brand` is
  never read.
- `grep -rn "dedup(" src/sonar/` finds exactly one hit: the function's own
  definition. Nothing in `src/` calls `dedup()` yet, so the "applied per
  brand" contract is entirely a documentation-only convention the future
  caller must honor by pre-partitioning its input by brand before calling
  in — `dedup()` itself does nothing to enforce or even assert that. If a
  future caller ever passes items for two brands into one call (easy
  mistake: nothing in the signature or docstring stops it), a mention
  matching the brand and a competitor with the same `native_id`/`url` would
  be wrongly collapsed into one row instead of the two the contract
  requires, corrupting `Receipt.mentions.deduped` and every mention–brand
  pair count downstream (SoV, net sentiment).
- `tests/test_text.py` has zero test cases with two different `brand`
  values (`_item()`'s `brand` default is unconditionally `"Nubank"` — see
  `tests/test_text.py:149-164`); the "kept once per brand" behavior is
  completely unexercised.
- Fix: either (a) have `dedup()` partition internally by `(source, brand)`
  the same way it now partitions by `source` alone — the safe,
  self-enforcing option — or (b) keep the "caller pre-partitions by brand"
  contract but make `dedup()` assert `len({i.brand for i in items}) <= 1`
  so a misuse fails loudly instead of silently dropping a row. Either way,
  add a test with two `DedupItem`s sharing a `native_id` but different
  `brand`, asserting the current behavior (single-brand call → 1 kept) and
  that mixing brands is either handled correctly or rejected, not silently
  wrong.

### F5. The ≤20-word rationale rule is not enforced anywhere the model's output is validated

- `CONTRACTS.md:142`: `Label.rationale` — *"`str` | `≤ 20 words, English,
  from the deciding model call`"*. `src/sonar/config.py` separately defines
  `RATIONALE_MAX_WORDS: Final[int] = 20` (part of the published-claims
  Threshold index machinery) — but it is never imported by `llm/base.py`.
- `src/sonar/llm/base.py:41` defines an unrelated
  `RATIONALE_MAX_CHARS = 200` (a *character* cap, not derived from
  `RATIONALE_MAX_WORDS`), used at `base.py:224`
  (`LabelObservation.rationale`) and `base.py:254`
  (`LabelAnswer.rationale` — the structured-output wire schema the model's
  JSON is validated against, i.e. exactly the enforcement point for what
  the model may emit).
- A 200-character rationale can trivially contain far more than 20 words
  (e.g. many short words), so nothing in the seam's schema — the only place
  that validates the model's raw output before it becomes a `Label` — stops
  a >20-word rationale from passing through as `status="ok"`. No test in
  `tests/test_llm_seam.py` exercises word count.
- Fix: add a `field_validator` on `rationale` in both `LabelAnswer` and
  `LabelObservation` that splits on whitespace and enforces
  `len(words) <= RATIONALE_MAX_WORDS`, importing the constant from
  `sonar.config` (mirroring how `llm/base.py` already lazily imports
  `sonar.config` for rates via `load_rates()`, so there's precedent for the
  dependency direction) or duplicating the frozen constant with a comment
  cross-referencing `config.RATIONALE_MAX_WORDS`. Add a test with a
  21-word, <200-char rationale and assert it is rejected (schema
  validation failure → `unparseable`, matching how `ValidationError` is
  already handled in `openai_backend.classify`).

---

## S3 — style or clarity

### F6. `llm/base.py`'s module docstring overclaims that `LabelStatus` "mirrors" CONTRACTS

- `src/sonar/llm/base.py:16-18`: *"Label and status vocabularies below
  mirror CONTRACTS §Enumerations."*
- `src/sonar/llm/base.py:35`:
  `LabelStatus = Literal["ok", "refused", "unparseable", "error"]` —
  CONTRACTS' `LabelStatus` (`CONTRACTS.md:62`) has five members, adding
  `cached`.
- This is architecturally correct, not a bug: CONTRACTS.md:148 says
  `cached` fires "when served from the label cache keyed by `(mention_id,
  prompt_rev, classifier model)`" with usage `{0, 0.0}` — i.e. the seam is
  never called at all on a cache hit, so it's the right layering for
  `sentiment/`'s label cache (D004: "Results are cached; repeated calls...
  return the cached label") to own that status, not `llm/base.py`. But the
  docstring's "mirror" language reads as a completeness claim; a reader
  skimming this file could reasonably assume `LabelStatus` here is the
  whole CONTRACTS enum.
- Fix: reword to something like "Label and status vocabularies mirror the
  CONTRACTS §Enumerations values a model call can itself produce;
  `cached` is assigned by the label cache in `sentiment/` before the seam
  is ever invoked and does not appear here."

### F7. `FALLBACK_RATES` (llm/base.py:74-78) and `config.LLM_RATES` (config.py) duplicate the same three numbers

- Both hard-code `0.20/1.20`, `2.00/12.00`, `0.02/0.0` for the same three
  model ids. `load_rates()` (`base.py:134-143`) only falls back to
  `FALLBACK_RATES` when `sonar.config` can't be imported ("Wave 2 build
  order" per the docstring at `base.py:45`), so in the shipped system this
  is dead weight that can silently drift from `config.LLM_RATES` on a
  future D003 price change (the "Reverses when" clause of D003 says
  "update `config.py` `LLM` dict and `LLM_RATES`" — it does not mention
  `llm/base.py`). Not urgent since both currently agree and the fallback
  path is Wave-2-bootstrap-only, but worth a one-line comment or a shared
  source of truth.

---

## Confirmed correct (the probes that passed)

- **Dedup precedence and reasons, minus the coding issue in F3**:
  `src/sonar/text/dedup.py:37-100` honours `(source, native_id)` → url →
  `text_key` in that exact order, never merges across sources
  (`by_source` grouping at `dedup.py:50-52`, matching CONTRACTS' "Dedup
  never merges across sources"), and the `raw_ref` tie-break
  (`_sort_key`, `dedup.py:31-34`) is lower `local_seq` then lower item
  index, exactly as CONTRACTS.md:409-410 specifies —
  `tests/test_text.py:194-199` (`test_lower_raw_ref_wins`) confirms.
- **Substring rejection for PT and EN aliases**: `match_terms`
  (`src/sonar/text/match.py:18-36`) correctly rejects `"inter"` inside
  `"internet"`, `"it"` inside `"bit"/"fit"/"unit"`, `"a"` inside
  `"apple"`, and the Portuguese case explicitly named in the task —
  `"ban"` inside `"banco"` — while still matching each term standalone;
  `tests/test_text.py:117-139` (`test_homonym_negatives`) exercises all of
  these and passes.
- **`Lang` closed enum**: `detect_lang` only ever returns one of
  `"pt"/"en"/"other"/"unknown"` (never anything else) — see F2 above for
  the internal inconsistency in *when* `"other"` is reached, which does not
  break the closed-set guarantee itself.
- **Missing id → `unparseable`, only that id**: `align_observations`
  (`src/sonar/llm/base.py:265-290`) marks exactly the missing id
  `unparseable` while leaving every other id in the batch `ok`, in batch
  order — `tests/test_llm_seam.py:243-251`
  (`test_missing_ids_become_unparseable`) confirms for both the fake and
  the stubbed OpenAI backend, including that the still-billed tokens leave
  `usage.cost_usd > 0.0`.
- **Refusal → `status=refused`**: a whole-completion `message.refusal`
  marks every id in the batch `refused`
  (`openai_backend.py:98-106`) — `tests/test_llm_seam.py:288-295`
  confirms, including that the refusal is still billed
  (`usage.tokens == 160`).
- **Structured JSON via the SDK's pydantic parse**: both `classify` and
  `complete_json` call `self._client.chat.completions.parse(...,
  response_format=<pydantic schema>)` (`openai_backend.py:83-84,
  127-128`); `tests/test_llm_seam.py:317-330`
  (`test_backend_sends_structured_output_with_pydantic_schema`) confirms
  the wire request carries `response_format.type == "json_schema"` with
  `strict: true`. Confirmed against the installed `openai==3.7.0` SDK that
  `pydantic.ValidationError` (not `json.JSONDecodeError`) is what
  `maybe_parse_content` raises on malformed model JSON (pydantic v2's
  `model_validate_json` raises `ValidationError` for both malformed JSON
  and schema mismatches), so the `except ValidationError` branch at
  `openai_backend.py:92-98` genuinely catches the garbage-JSON case
  exercised by `test_garbage_json_marks_every_id_unparseable`.
- **Fake counts calls per model**: `FakeBackend.calls` and
  `.calls_by_kind` (`fake.py:100,119-121`) count every `classify`,
  `complete_json`, and `embed` call, keyed by model and by `(kind,
  model)` — `tests/test_llm_seam.py:475-497` confirms tiebreak-volume
  counting works as the design appendix expects ("fake counts calls per
  model").
- **`embed` returns numpy**: both backends return
  `EmbedResult.vectors: npt.NDArray[np.float64]` of shape
  `(len(texts), dim)` — `tests/test_llm_seam.py:443-452` and `:464-469`
  confirm dtype, shape, determinism, and unit-length for the fake.
- **Only `openai_backend.py` imports `openai`**:
  `tests/test_llm_seam.py:533-547`
  (`test_only_openai_backend_imports_openai`) does an AST-based import
  check over `__init__.py`, `base.py`, `fake.py`, and passes; independently
  confirmed by reading the files.

---

## Fix list (numbered, independently applicable)

1. **F1 (S1)** — `src/sonar/llm/openai_backend.py` `_usage_of` /
   `src/sonar/llm/base.py` `Usage.price`: read
   `usage.prompt_tokens_details.cached_tokens` and either price it at a
   documented discounted rate (extend `Rate`) or explicitly decide and
   record in `docs/DECISIONS.md` that cached tokens are priced at the full
   input rate. Add a stub-transport test with non-zero
   `prompt_tokens_details.cached_tokens` in the mocked `usage` block and
   assert the resulting `cost_usd`.
2. **F2 (S2)** — `src/sonar/text/lang.py:58-60`: make the
   both-ratios-above-0.10 branch return `"other"` to match its own
   docstring (or rewrite the docstring to state the "pick dominant"
   policy explicitly, if that's the one actually wanted); update
   `tests/test_text.py:90-93` (`test_ambiguous_picks_dominant`) to assert
   whichever behavior is chosen, by name, not just "one of pt or en."
3. **F3 (S2)** — `src/sonar/text/dedup.py`: change `DedupResult.dropped`
   to carry a typed/coded reason (`Literal["dedup_native_id", "dedup_url",
   "dedup_text"]`) alongside the existing prose message; update the three
   `dropped.append(...)` call sites (`dedup.py:76,87,97`); add one test per
   rule asserting the exact coded value in `tests/test_text.py`.
4. **F4 (S2)** — `src/sonar/text/dedup.py`: scope `dedup()` by
   `(source, brand)` instead of `source` alone (or add an explicit
   single-brand assertion if the "caller pre-partitions" contract is kept
   intentionally); add a `tests/test_text.py` case with two `DedupItem`s
   sharing a `native_id`/`url`/`text_key` but different `brand` values and
   assert both are kept.
5. **F5 (S2)** — `src/sonar/llm/base.py`: add a word-count validator to
   `LabelAnswer.rationale` (`base.py:254`) and
   `LabelObservation.rationale` (`base.py:224`) enforcing
   `config.RATIONALE_MAX_WORDS` (20), not just the 200-character cap; add a
   test with a >20-word, <200-char rationale asserting rejection.
6. **F6 (S3)** — `src/sonar/llm/base.py:16-18`: reword the module
   docstring so it states `LabelStatus` here excludes `cached` by design
   (assigned upstream by `sentiment/`'s label cache), rather than claiming
   to "mirror CONTRACTS §Enumerations" wholesale.
7. **F7 (S3)** — `src/sonar/llm/base.py:74-78` /
   `src/sonar/config.py` `LLM_RATES`: add a comment on `FALLBACK_RATES`
   cross-referencing `config.LLM_RATES` as the source of truth, so a future
   D003 price change doesn't leave the fallback table stale (or generate
   one from the other in a small script/test that fails if they diverge).
