# Review — `src/sonar/report/`, `src/sonar/voice/`

**Date**: 2026-09-02
**Reviewer stance**: skeptical, no stake in the result
**Checked against**

| Key | Source |
|---|---|
| CONTRACTS | `CONTRACTS.md` `schema_rev` 1.1.2 — §RunRecord (totals paragraph), §Receipt (verdict, `totals`, `audit`, `comparison`, `mentions.excluded_with_reason`, `abstentions`, `what_could_not_be_checked`, `content_digest`), §Digest (`top_mentions`, `cost`, `narration`), §StatsFile, §Receipt verdict rule |
| D011 | `docs/DECISIONS.md` — ElevenLabs endpoint, 900-char cap, `out/<session>/brief.mp3` |
| D012 | F4 audit fields, F13 `run_id=null` rows reconcile by construction, F20 `verified_numbers`, F21 `stats.json`/`topics.json` written with `digest.json`, F22 exclusion keys, F23 `top_mentions` sort, F24 H1 on `total_usd` |
| D013 N6 | `local` rows: failed iff `LOCAL_*`; succeeded `run_id=null` sync run not failed; `LOCAL_DEADLINE` keeps its id and stays `unreconciled` |
| D006 | English narration ≤ 900 chars through `complete_json`, numbers gate |
| DESIGN | `docs/research/2026-09-02-task-graph-and-design.md` §Error matrix (ElevenLabs fails → no mp3, rest complete, exit 0; `GET /v1/runs` fails → PARTIAL, exit 4), W4.5 row |
| PRICE | `src/sonar/report/incumbent.py` `BRAND24_TEAM` as the only price source |

Severity: **S1** wrong published number or money; **S2** contract violation
or a defect that makes a documented feature fail on real data; **S3** style,
clarity, test gap.

Verification method: read `receipt.py`, `digest.py`, `markdown.py`,
`incumbent.py`, `voice/script.py`, `voice/tts.py`, `voice/__init__.py`,
`tests/test_receipt.py`, `tests/test_voice.py`, `tests/golden/receipt.json`
line by line against the sections above; ran
`.venv/bin/python -m pytest tests/test_receipt.py tests/test_voice.py -q`
(72 passed); ran five throwaway scripts under
`/private/tmp/claude-501/.../scratchpad/` (no network, not committed):

1. hand-summed `tests/golden/receipt.json` with plain `json` and no sonar
   import: `monid_usd` 0.31405 = 0.248 + 0.03375 + 0.02 + 0.0 + 0.0123 over
   the five `/v1/runs` rows; the two `local` rows (seq 4 succeeded sync,
   seq 5 `LOCAL_REJECTED_402`) carry 0.0; seq 8 `unreconciled` adds nothing
   and is the only entry of `unreconciled_local_seqs`; `monid_runs` 8,
   `billed` 4, `zero_results` 3, `failed` 2 (seq 5 and seq 6 `FAILED`, per
   N6); `elevenlabs_usd` 0.0123 equals the seq 7 row; `total_usd` =
   `monid_usd + llm_usd`; `sonar_usd_month_equiv` = `total_usd × 4`;
   `ratio` = 349 / equiv = 273.1598…; seq 3 has `n_results=0` and
   `cost_usd=0.02`; the eight exclusion keys are exactly the contract's;
   `by_source` and `by_brand` both sum to `deduped` 110. All match.
2. rendered the golden receipt and an empty-runs receipt to Markdown;
   verdict transitions PARTIAL → RECONCILED → REPLAY with `verify` exit
   1 / 0 / 1; a `LOCAL_DEADLINE` row with a `run_id` stays `unreconciled`,
   forces PARTIAL and counts as failed; the zero-runs table renders header
   only and `ratio` prints `—`.
3. numbers gate against `make_digest()` from `tests/test_voice.py` with
   planted negative nets, real-precision floats, window-day integers and
   formatted variants (results in F1, F2, F7, F10).
4. `narrate()` end to end with the **real** `ElevenLabsProvider` behind
   `httpx.MockTransport` (harness from `tests/test_adapter_elevenlabs.py`):
   the `/text-to-speech` row lands in `runs.jsonl` as `local_seq` 1,
   provider `elevenlabs`, `brand`/`source` null, `n_results` 1,
   `cost_source=unreconciled`, `cost_usd` null; `brief.mp3` bytes match;
   `narration.local_seq` points at the row; the POST body text equals the
   gated narration.
5. `rank_top_mentions` with four rows at equal `engagement_score`: newest
   first, the two equal-timestamp rows in ascending `mention_id`, the
   `published_at=null` row last; brand groups follow `[brand, *competitors]`
   even when a competitor row has the highest score.

No repo file was edited except this one.

---

## Verdict: **FAIL**

One S1 (the digest's cost quote and the narrated cost cannot both agree with
the receipt as the three modules are wired), three S2 (the numbers gate
rejects every negative number and every real-precision float, so the
narration is unvoiced on real data; the Markdown card's money rows do not
sum to the printed Monid total), and nine S3. Everything the task asked to
probe by execution and that is *not* listed below behaves as the contract
says: totals hand-sum including `local` rows per N6, the zero-result billed
run is in the table with its cost, the unreconciled run contributes zero
and is listed, PARTIAL/RECONCILED/REPLAY transitions and `verify` exit
codes, `$349` printed from the receipt's incumbent block which is built from
`BRAND24_TEAM`, ratio arithmetic, the F23 sort, zero-row and zero-result
rendering, the 900-char cap, and the TTS run reaching the ledger through the
adapter.

---

## Findings

### F1 — S1 — `Digest.cost` quotes a receipt that cannot yet contain the narration and voice spend

`src/sonar/report/digest.py:140-162`, `src/sonar/voice/script.py:209-242`,
`src/sonar/voice/tts.py:68-111`, `tests/golden/receipt.json:203-212,156-174`

`build_digest` takes a `Receipt` and copies `receipt.verdict` and
`receipt.totals` into `cost` (digest.py:162). `write_script` narrates *that*
digest and gates its numbers against *that* digest. `synthesize_narration`
then opens a new ledger row. The golden receipt shows the receipt is meant to
be final *after* voice: `llm_calls.narrate` is 1 and seq 7 is the
`elevenlabs` row with `cost_usd` 0.0123. So whichever order the pipeline
picks, a published number is wrong:

- receipt built before voice, digest quotes it, receipt written as is:
  `receipt.totals` omits the narrate call and the ElevenLabs run;
  `elevenlabs_usd` is 0.0 while a `/text-to-speech` row sits in `runs`;
  H1/H4 read a `total_usd` that is short by the voice spend.
- receipt rebuilt after voice (correct receipt), digest not re-quoted:
  `digest.json` / `digest.md` print `total $0.3194` while `receipt.json`
  prints a larger `total_usd`; two published money figures for one session.
- receipt rebuilt and digest re-quoted: the narration said the pre-voice
  cost; that number no longer occurs in the final digest, so
  `narration.numbers_verified=true` is false against the digest that ships,
  contradicting CONTRACTS §Digest `narration` ("iff every number in `text`
  occurs in this Digest"), and the mp3 already cost money.

No function in either layer exposes a way to re-quote `cost` or to re-gate a
narration, and neither docstring mentions the ordering. The sibling
`pipeline.py` (not yet in the tree) will copy whatever order the docstrings
imply, which is the first bullet.

### F2 — S2 — Numbers gate rejects every negative number

`src/sonar/voice/script.py:64-72` (regex has no sign), `:99-116`
(`extract_numbers`), `:119-127` (`_leaf_numbers` keeps the sign)

Probe: digest with `sentiment[*].net = -0.27`; `digest_numbers` contains
`Decimal("-0.27")` and not `0.27`. `numbers_gate("net sentiment -0.27")`,
`"minus 0.27"`, `"net −0.27"` and `"-27%"` all return `foreign=("0.27",)`
(or `"27%"`). Net sentiment and WoW `delta` are negative for any brand with
more negatives than positives, which is the common case for a bank on
Reddit; the re-ask tells the model its own correct number is "not in the
digest", the second draft fails the same way, `numbers_verified=false`, no
audio. `tests/test_voice.py:159-307` builds a digest whose negative leaves
(`-0.3`, `-0.05`, `-0.03`) are never narrated, so the suite does not see it.

### F3 — S2 — Numbers gate only accepts exact float equality, so real-precision digests cannot be narrated

`src/sonar/voice/script.py:28-35` (prompt: "exactly as written there; do not
… round"), `:91-96` (`_normalise`), `:163-177` (`numbers_gate`)

Every published float is a bootstrap or a division at machine precision:
golden `total_usd` is `0.31940999999999997`, `share` is `37/110 =
0.33636363636363636`. Probe against a digest quoting the golden totals:
`"$0.3194"`, `"$0.32"`, `"$0.31941"`, `"$0.3140"` are all foreign; only
`"$0.31405"` (a value that happens to be exact) and the full 17-digit string
pass. Share `0.3363…`: `"34%"`, `"33.6%"`, `"0.336"` foreign. The system
prompt requires the model to cover "share of voice, sentiment … and the
cost", so on any live session the first draft carries a rounded figure, the
re-ask carries another, and the narration ships unvoiced. `tests/test_voice.py`
only ever uses exact short floats (`0.42`, `0.6`, `0.5`, `1.44`), which is why
72 tests pass. The receipt Markdown itself prints `$0.3194`
(`markdown.py:29,55`), so the card and the narration can never agree on the
cost under the current rule. "Formatted variants" in the task brief must
include the value rounded to the precision the narration states, otherwise
the feature is dead on arrival.

### F4 — S2 — Receipt card money rows do not sum to the printed Monid total

`src/sonar/report/markdown.py:51-55` (`usd`), `:145-159` (`totals_table`),
`:111-142` (`runs_table`)

`f"{value:.4f}"` rounds the binary double, not the decimal the ledger
carries. Golden card: `Monid billed | $0.3140` (from `0.31405`, whose double
is `0.31404999…`) while the printed `billed` cells are `$0.2480 + $0.0338 +
$0.0200 + $0.0000 + $0.0000 + $0.0000 + $0.0123 = $0.3141` (`0.03375` rounds
*up* because its double is `0.033750000000000002`). A reader hand-summing the
card, which is the card's stated purpose (module docstring, H4), gets a
different number from the total line. The JSON is right; the published
Markdown is inconsistent with itself.

### F5 — S3 — `349`, `10000`, `"Brand24 Team"` and `4` are re-typed as `Literal`s in `models.py`

`src/sonar/models.py:680-686` (`Incumbent`), `:688-689` (`Comparison`),
`src/sonar/report/incumbent.py:1-13` (docstring: "single source"),
`tests/test_receipt.py:406,414,546,1022`

Probe: `Incumbent.model_validate({**BRAND24_TEAM.to_record(),
"price_usd_month": 299})` fails on the `Literal[349]`. So the price lives in
two files; D001's reversal clause ("updates this constant, the README and
DECISIONS together") would also have to touch `models.py`, which nothing
documents. `markdown.py:167,172` correctly prints from the receipt block, and
`receipt.py:141-142,363` correctly builds it from the constant, so the card
is fine today. The tests compute the expected ratio with a literal `349`
(`test_receipt.py:414,546`) instead of `BRAND24_TEAM.price_usd_month`, which
is the re-typing the published-claims gate exists to prevent.

### F6 — S3 — `mp3_path` is an absolute machine path

`src/sonar/voice/tts.py:107-110`

`str(out_dir / "brief.mp3")` is written into `Narration.mp3_path`, hence into
`digest.json` and `digest.md` (`markdown.py:459`). Probe: the path stored was
`/private/tmp/…/sess/brief.mp3`. `results/demo/digest.json` is a committed,
published artifact (README, W5.4 gate); it will carry the lead's home
directory, and `sonar render --from results/demo` on another machine points
at a file that does not exist. D011 names the location as
`out/<session>/brief.mp3`; the session-relative name is the stable value.

### F7 — S3 — Window date components vouch for arbitrary integers

`src/sonar/voice/script.py:126-127`

`_leaf_numbers` adds `year`, `month` and `day` of every date leaf. Probe:
`"26 mentions"` passes against `make_digest()` solely because
`window.current.start` is 2026-08-26; `"2 topics"` and `"9 mentions"` pass
because of the month and day of the end date. Any narration integer in 1–31
or equal to 9 (month) or 2026 is accepted regardless of what it claims to
count. The gate's promise (D006: "rejects any number not present in the
digest") holds only in the letter.

### F8 — S3 — An over-budget first draft aborts the narration with no re-ask

`src/sonar/voice/script.py:45-57` (`NarrationSchema`, `max_length`),
`:224-234` (loop only re-asks on the numbers gate), `src/sonar/voice/__init__.py:61-72`

A draft of 901+ characters raises `LlmUnparseable` out of `complete_json`
(`tests/test_voice.py:459-464` pins this), which `narrate` converts to
`NO_NARRATION` plus a `provider_failed` abstention. Models overshoot a
character budget routinely; the design's own error-matrix idiom for an
LLM output that misses a check is "re-ask once". `MAX_ATTEMPTS` is spent
only on foreign numbers. Also, `max_length` runs before the `strip()`
validator, so a 900-character body padded with whitespace is rejected.

### F9 — S3 — `NO_NARRATION` is defined twice

`src/sonar/report/digest.py:48-51`, `src/sonar/voice/__init__.py:30`

Two equal constants, two docstrings, two `__all__` entries. One of them will
drift.

### F10 — S3 — `per cent` is not recognised as a percentage

`src/sonar/voice/script.py:69`

`percent\b` matches `60 percent` but not `60 per cent` or `60 pct`; those
degrade to the bare integer, which then fails unless the digest happens to
contain `60` as an integer. British spelling is common in model output.

### F11 — S3 — Rows with no `Label` are invisible in `MentionCounts`

`src/sonar/report/receipt.py:267-275`

A kept row with no entry in `labels` (labeler halted by the 402 breaker,
OpenAI outage after retries, or a batch never sent) is counted in `deduped`
but in neither `labelled` nor any `excluded_with_reason` bucket, so the
card's Mentions block does not reconcile and nothing says why. The contract
fixes the eight keys, so the count cannot be added there; it belongs in
`what_could_not_be_checked` (which `build_receipt` accepts) or in a `session`
abstention, and `count_mentions` should at least return the number.

### F12 — S3 — No test drives the TTS run through the ledger

`tests/test_voice.py:120-144` (`StubAdapter`), `:482-637`

Every voice test replaces the adapter with a stub that never touches
`client` or `ledger`; the `ledger` fixture is created and never read. The
W4.5 acceptance line is "TTS through the ElevenLabs adapter as a ledger
run", and `tests/test_receipt.py` never builds a receipt from a ledger that
`narrate` wrote to. Probe 4 above shows the wiring works today; nothing
pins it.

### F13 — S3 — Narration model is the classifier model with no decision recording it

`src/sonar/voice/script.py:217`

`model or config.LLM.classifier_model` picks Luna for narration. D003
assigns models by role (classifier, tiebreak, embedding) and W5.4's
published-claims gate requires "model ids dated in DECISIONS"; no entry
names the narration model, and `config.LLM` has no narration role, so the
choice is invisible to the gate and to the receipt's `llm_calls.narrate`
reader.

---

## Confirmed correct (probed, not just read)

- `build_totals` (receipt.py:203-217): `monid_usd` sums only `/v1/runs`
  rows; `local` rows contribute 0.0 and count as failed iff `LOCAL_*`
  (`is_failed`, ledger.py:62-67); `unreconciled` contributes 0.0 and is
  listed by `_reconciliation` from the rows themselves, not from the caller's
  list (receipt.py:129-138); `elevenlabs_usd` is a breakout and
  `total_usd = monid_usd + llm_usd`. `Receipt._ledger_consistency`
  (models.py:807-856) re-checks all of it on load, so `verify` catches a
  tampered total.
- Verdict rule and `verify`: PARTIAL with seq 8 unreconciled, RECONCILED
  once priced, REPLAY on `replay=True`, PARTIAL on a stray remote id and on
  `fetched_at=None`; `LOCAL_DEADLINE` with a `run_id` stays unreconciled;
  exit codes 0/1/2 as documented; a forged verdict or digest exits 2.
- Incumbent block built from `BRAND24_TEAM` only (receipt.py:141-142, 352,
  363); Markdown prints `$349 per month` from the receipt (markdown.py:167).
- `comparison`: equiv = `total_usd × 4`, ratio = 349 / equiv, `None` when
  nothing was spent (and the model rejects any other combination).
- `count_mentions` carries exactly the eight F22 keys, rejects any other
  `dedup_*` key, and `by_source`/`by_brand` sum to `deduped`.
- `build_audit` follows F4: `n_sample` = sampled rows whose tiebreak is
  `ok`, `n_agree` compares tiebreak to classifier label, overflow counted
  from `signals.overflow`.
- `what_could_not_be_checked` leads with the X sentence and deduplicates.
- `rank_top_mentions`: F23 order, `null` `published_at` last, ≤ 10 per
  brand, brand groups in query order, `irrelevant`/`not_about_brand`/
  unlabelled rows excluded, quote cut at 240.
- `write_digest_files` writes the three files together (F21) and
  `StatsFile` is field-identical to the digest.
- `runs_table` prints every row including `run_id=null`, `n_results=0`,
  `$0.0000` and `unreconciled` cells; empty `runs` renders a header-only
  table.
- Gate accepts `30.0`, `0.60`, `$0.420`, `1,234` and `60%` for `0.6`; a
  planted `$999.99` and `31` are rejected and listed once in order; the
  re-ask message names them; two rejections keep the text with
  `numbers_verified=false` and spend nothing; `NarrationSchema` caps at 900.
- `synthesize_narration` skips unverified text without opening a run,
  writes `brief.mp3`, sets `local_seq` from the adapter's row, and maps
  `MonidHalted`/`AlreadySubmitted`/`AdapterSchemaError`/failed statuses to
  `voice`-scoped abstentions without raising (error matrix: "no mp3, rest
  complete").

---

## Fix list (each item touches a disjoint file set; apply independently)

1. **F1 — `src/sonar/report/digest.py` only.** Add
   `requote_cost(digest: Digest, receipt: Receipt) -> Digest` returning
   `digest.model_copy(update={"cost": CostQuote(verdict=receipt.verdict,
   totals=receipt.totals)})`, export it, and state in the `build_digest`
   docstring the required order: build the digest from a pre-voice receipt,
   narrate, voice, reconcile, build the final receipt, `requote_cost`, then
   re-gate (item 2) before writing. Add a test that `requote_cost` changes
   only `cost`.
2. **F1 (voice half), F2, F3, F7, F10 — `src/sonar/voice/script.py` and
   `tests/test_voice.py` only.**
   - Regex: add `(?P<sign>[-−–])?` before `dollar` and negate `value` when
     present; treat a preceding word `minus` the same way (F2).
   - Matching: a token passes when any candidate equals a digest value
     **or**, for a token with `k ≥ 1` decimals (or any percent token), when
     some digest value quantized to `k` places with `ROUND_HALF_UP` equals
     it (`34%` ↔ `0.336…` via `k+2`; `$0.3194` ↔ `0.31940999…`). Bare
     integers keep exact matching so `30` never vouches for `29.6` (F3).
     Change the system prompt from "exactly as written" to "at most two
     decimals, rounded, never converted between units".
   - Drop the `datetime | date` branch from `_leaf_numbers` (F7).
   - `percent\b` → `(?:percent|per\s?cent|pct)\b` (F10).
   - Add `regate(narration: Narration, digest: Digest) -> Narration` that
     re-runs `numbers_gate` on the final digest and returns the narration
     with `numbers_verified` updated (F1); the pipeline calls it after
     item 1.
   - Tests: negative net narrated as `-0.27`, `minus 0.27` and `-27%`;
     golden-precision total narrated as `$0.3194` and share `0.336…` as
     `34%` pass; `$0.3195` and `35%` fail; `26 mentions` fails against
     `make_digest()`; `60 per cent` passes; `regate` flips a stale cost.
3. **F4 — `src/sonar/report/markdown.py` and the money assertions in
   `tests/test_receipt.py:995-1061` only.** `usd()` formats
   `Decimal(repr(value)).quantize(Decimal("0.0001"), ROUND_HALF_UP)`; add a
   test that the printed `billed` cells of the golden card sum to the
   printed `Monid billed` line (`$0.3141`) and update the two `$0.3194`
   assertions if they move (they do not: `0.31941` → `$0.3194` either way).
4. **F5 — `src/sonar/models.py` (`Incumbent`, `Comparison`) and
   `tests/test_receipt.py:403-416,540-562` only.** Replace the four
   `Literal`s with plain typed fields (`price_usd_month: int = Field(gt=0)`
   etc.); keep the ratio cross-check in `Receipt._ledger_consistency`. In
   the tests, derive expected values from `BRAND24_TEAM.price_usd_month`
   and `config.BRIEFS_PER_MONTH_ASSUMED` instead of literals. The
   published-claims gate already asserts `BRAND24_TEAM == README ==
   results/demo/receipt.json`, which is the one place the literal belongs.
5. **F6 — `src/sonar/voice/tts.py` and its tests in
   `tests/test_voice.py:482-500,580-598` only.** Store
   `mp3_path=BRIEF_MP3_FILENAME` (session-relative, per D011) and document
   that it resolves against the session directory; update the two
   `mp3_path == str(tmp_path / …)` assertions.
6. **F8 — `src/sonar/voice/script.py` loop (coordinate with item 2; same
   file, different lines, `:224-234`).** Catch `LlmUnparseable` inside the
   attempt loop, append a "your draft exceeded 900 characters; shorten it"
   sentence to the re-ask, and let the second failure propagate as today.
   Move `strip()` into a `mode="before"` validator so padding does not
   count against the cap.
7. **F9 — `src/sonar/voice/__init__.py` only.** Delete the local
   `NO_NARRATION` and import it from `sonar.report.digest` (re-export
   unchanged).
8. **F11 — `src/sonar/report/receipt.py` `count_mentions` and
   `tests/test_receipt.py:685-737` only.** Count kept rows with no label,
   return it (e.g. a `MentionCounts`-adjacent `unlabelled: int` on a small
   result dataclass, or a second return value), and have the docstring
   direct the pipeline to add
   `"labelling: N deduped rows never labelled (<reason>)"` to
   `what_could_not_be_checked` when non-zero.
9. **F12 — `tests/test_voice.py` only (append; no source change).** One
   test that runs `narrate()` with the real `ELEVENLABS` provider behind
   the `Script`/`make_client` harness from `tests/test_adapter_elevenlabs.py`
   and asserts the `/text-to-speech` row in `runs.jsonl` (provider,
   endpoint, null brand/source, `n_results=1`, `cost_source=unreconciled`)
   and that `narration.local_seq` equals its `local_seq`.
10. **F13 — `docs/DECISIONS.md` and `src/sonar/config.py` only.** Add a
    `narration_model` role (default = classifier model) and a dated
    DECISIONS line naming it, so the W5.4 gate can see it; `script.py:217`
    then reads `config.LLM.narration_model` (one-line change, do together
    with item 2 or 6 since it is the same file).

Items 2 and 6 share `script.py`; apply 2 first. Everything else is
file-disjoint.
