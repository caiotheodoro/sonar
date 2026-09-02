# Code review — config, incumbent, providers (2026-09-02)

**Scope**: `src/sonar/config.py`, `src/sonar/report/incumbent.py`,
`tests/test_config.py`, `src/sonar/providers/base.py`,
`src/sonar/providers/registry.py`, `src/sonar/providers/x.py`,
`tests/fixtures/README.md`.

**Checked against**: `docs/PRE-REGISTRATION.md` v1.1.0 threshold index,
`docs/research/2026-09-02-task-graph-and-design.md` Endpoint reference table
and Pipeline rules, `docs/DECISIONS.md` D001/D003/D011/D012 (F14, F16),
`CONTRACTS.md` 1.1.0 (Mention, Provider usage).

**Command run**: `uv run pytest tests/test_config.py -q` →
**2 failed, 28 passed** (both failures detailed below).

**Verdict: FAIL** — one contract-breaking bug in `base.py`, one dropped
threshold in the published-claims gate (D012 F16), and the gate's own test
file is currently red against the doc it is supposed to enforce.

---

## Findings

### S1 — `src/sonar/providers/base.py:49-51` — Provider protocol contradicts the frozen `Mention` contract and every real adapter

```python
def parse(
    self, raw: dict[str, Any], run_id: str, brand: str
) -> list[Any]:
```

Two separate defects:

1. `run_id: str` is non-nullable. `CONTRACTS.md:117` and the already-shipped
   `src/sonar/models.py:312` both type `Mention.run_id` as `str | None`
   ("`null` when the run returned no id (`$0` sync endpoints, OQ-2)"). Every
   live adapter except `google_maps.py:158` and `facebook.py:185` already
   types its own `run_id` parameter as `str | None` (`reddit.py:216`,
   `youtube.py:198`, `youtube_comments.py:109`, `tiktok.py:208`,
   `instagram.py:227`, `news.py:186`) — the Protocol is narrower than every
   implementation, so code written against the `Provider` type can never
   pass `None` for a sync ($0) source such as `news`, even though the
   contract requires it.
2. The Protocol has no `local_seq` parameter at all. `Mention.raw_ref`
   (`CONTRACTS.md:128`) is `"{local_seq}#{index}"`, and every live adapter
   (`reddit.py:219`, `youtube.py:201`, `youtube_comments.py:112`,
   `tiktok.py:211`, `instagram.py:230`, `google_maps.py:161`,
   `facebook.py:188`, `news.py:186-189`) declares a keyword-only `local_seq`
   parameter to build it — `news.py:213-214` even raises `ValueError` if it
   is omitted. A caller typed against `Provider.parse(raw, run_id, brand)`
   has no way to supply it, so `raw_ref` cannot be constructed through the
   sanctioned interface.

The Protocol, as written, is not implementable by the adapters that exist
today — it is not a stub-ahead-of-`models.py` situation (the docstring at
`base.py:3-4` says W2.1 "will define" `Mention`, but `models.py` already
exists with the frozen shape).

### S1 — `src/sonar/config.py:444-465` — `THRESHOLD_INDEX` drops the D012 F16 topic thresholds

`docs/DECISIONS.md:443` (D012 F16): *"Topic cut: average-linkage cosine
distance 0.35, `min_size 3`, `min_breadth 2`, all in `config` **and in the
threshold index**."* `docs/PRE-REGISTRATION.md:182` lists the same triple
under `## Threshold index`. `config.py` defines the constants
(`TOPIC_DISTANCE_THRESHOLD` at line 125, `TOPIC_MIN_SIZE` at line 122,
`TOPIC_MIN_BREADTH` at line 123) but `THRESHOLD_INDEX` (lines 444-465) never
references them. `tests/test_config.py`'s
`test_threshold_index_matches_constant` parametrize list (lines 33-57) has
no case for the topic-cut line either, so the published-claims gate this
whole module exists to serve never actually checks these three numbers
against the doc — the one explicit requirement D012 F16 imposed.

### S1 — `tests/test_config.py` is red against the doc it enforces (confirmed by `uv run pytest tests/test_config.py -q`)

Two of the 30 tests fail right now:

- **`tests/test_config.py:42`** — `r"n < (\d+) in either week"` no longer
  matches. `docs/PRE-REGISTRATION.md:178` reads *"...or n < 20 in either
  **period**"* (wording changed by amendment A1, `docs/PRE-REGISTRATION.md:200-206`,
  and echoed at `CONTRACTS.md:75`, `"n < 20 in either period"`). The
  constant value (20) is right; only the stale regex fails.
- **`tests/test_config.py:91`** — `assert "**Version**: 1.0.0" in text`.
  `docs/PRE-REGISTRATION.md:3` is now `**Version**: 1.1.0` (bumped by
  amendment A2 / D012). Test was never updated after the freeze-day
  amendments landed.

Both are the test file drifting behind a doc it is meant to gate, not a
config-constant error — but as shipped, the gate the task says to run does
not pass.

### S3 — `src/sonar/config.py:4-5` — module docstring cites the wrong PRE-REGISTRATION version

`"the threshold index of docs/PRE-REGISTRATION.md (v1.0.0, frozen
2026-09-02)"` — the frozen doc is v1.1.0 (A1 + A2 amendments, same freeze
date). Cosmetic, but it's the exact kind of drift this module's own
docstring warns against.

### S3 — `src/sonar/providers/registry.py:10` — docstring example references a class that doesn't exist

```python
PROVIDERS["x"] = XProvider()
```

The real class in `src/sonar/providers/x.py:17` is `_XProvider` (leading
underscore, private). The example won't run as written.

### S2 — `tests/fixtures/README.md:12,29-31` — documents `labels.jsonl`, repo has `labels.json`

The README's layout block (line 12) and Rules section (lines 29-31)
describe `labels.jsonl` as JSON Lines, "one `Label` per line." The file that
actually exists, `tests/fixtures/labels.json`, is a single pretty-printed
JSON object (`{"labels": {<mention_id>: {...}, ...}}`), not JSON Lines. Name
and shape both diverge from the doc — pick one and make the other match.

### S3 — `tests/fixtures/README.md` doesn't mention `tests/fixtures/samples/`

The Layout section (lines 8-15) and Rule 1 ("no fixture is hand-written...
A fixture that was typed or fabricated is invalid," lines 46-48) describe
the directory as if every file under `tests/fixtures/` is a recorded Monid
payload. `tests/fixtures/samples/` holds `SAMPLE-hand-built-*.json` files
that are explicitly and legitimately exempt (its own
`tests/fixtures/samples/README.md` states the exemption clearly), but the
top-level README gives no pointer to that directory or its exemption, so
read alone it overstates the "never hand-written" rule.

### S3 — `tests/fixtures/samples/README.md` table is stale

The table (lines 10-13) lists 2 files (`reddit_reddit-scraper-lite_sample.json`,
`tinyfish_search_sample.json`); the directory now holds 14, including four
`SAMPLE-hand-built-*` files the table's own naming convention note doesn't
cover.

---

## Things checked and found correct

- `config.SOURCE_PLAN` provider ids, endpoint paths, and per-result/per-call/
  lookup prices match the Endpoint reference table exactly for all ten
  sources (reddit, youtube, youtube_comment, tiktok, instagram, google_maps,
  facebook, trustpilot, g2, news); `"x"` correctly absent from `SOURCE_PLAN`
  and from `SourceName`.
- Full-profile caps match Pipeline rules exactly (reddit 40+$0.02, youtube
  10, youtube_comment 60, tiktok 40, instagram 30, google_maps 50, facebook
  30, trustpilot/g2 1 call, news 3 pages/$0); `lite` halves every cap except
  `news` (3 → 2, not an exact half — functionally reasonable, not flagged as
  a defect); smoke = reddit + google_maps only, 1 brand.
  `full.estimate_usd_per_brand()` computes to ≈$0.7042/brand, matching the
  design doc's "≈ $0.7/brand → ≈ $2.8 for brand + 3" and the ≈$0.3 smoke
  estimate, by hand recomputation.
- `cluster_rule`, `has_rating`/`REVIEW_SOURCES`, `has_timestamps`/
  `COMMENT_SOURCES` all match the CONTRACTS/PRE-REGISTRATION tables.
- D001: `report/incumbent.py`'s `BRAND24_TEAM` ($349/mo, checked 2026-09-02,
  10,000 mentions quota) matches DECISIONS D001 and is echoed verbatim in
  `README.md:11-12`.
- D003: `LLM_RATES` for `gpt-5.6-luna` (0.20/1.20) and `gpt-5.6-terra`
  (2.00/12.00) match DECISIONS D003 exactly, dated 2026-09-02.
  D011: `ELEVENLABS_MODEL_ID="eleven_flash_v2_5"`,
  `ELEVENLABS_USD_PER_1K_CHARS=0.05`, endpoint `/text-to-speech` all match.
- `x.py`: registered unavailable, `available=False`,
  `unavailable_reason="Monid catalog has no X/Twitter endpoint (verified
  2026-09-02)"` — matches `CONTRACTS.md:38-41` word for word on the dated
  reason.
- Every non-topic threshold in `THRESHOLD_INDEX` (CI 95%, B 2000/10000,
  seed 777, α 0.05, minimums 5/20, event rule 5/3·MAD/3/14, tiebreak 0.6/
  40%/10%, H1-H5) matches the PRE-REGISTRATION text and passes its
  parametrized test.

---

## Fix list (independently applicable)

1. `tests/test_config.py:42` — change the regex from
   `r"n < (\d+) in either week"` to `r"n < (\d+) in either period"`.
2. `tests/test_config.py:91` — change `"**Version**: 1.0.0"` to
   `"**Version**: 1.1.0"`. After 1 and 2, re-run
   `uv run pytest tests/test_config.py -q` and confirm 30/30 pass.
3. `src/sonar/config.py:4-5` — change `"(v1.0.0, frozen 2026-09-02)"` to
   `"(v1.1.0, frozen 2026-09-02, amended same day by D012 A1/A2)"`.
4. `src/sonar/config.py:444-465` — add three entries to `THRESHOLD_INDEX`:
   `"topic_distance_threshold": TOPIC_DISTANCE_THRESHOLD`,
   `"topic_min_size": TOPIC_MIN_SIZE`, `"topic_min_breadth": TOPIC_MIN_BREADTH`.
5. `tests/test_config.py:62-86` — add the same three keys/values to the
   `expected` dict in `test_threshold_index_mapping_covers_every_constant`,
   and add three parametrize cases to `test_threshold_index_matches_constant`
   (lines 33-57) matching `docs/PRE-REGISTRATION.md:182`, e.g.
   `(r"distance cut ([\d.]+)", config.TOPIC_DISTANCE_THRESHOLD)`,
   `(r"min_size (\d+)", config.TOPIC_MIN_SIZE)`,
   `(r"min_breadth (\d+)", config.TOPIC_MIN_BREADTH)`.
6. `src/sonar/providers/base.py:49-51` — change the `Provider.parse`
   signature to
   `def parse(self, raw: dict[str, Any], run_id: str | None, brand: str, *, local_seq: int | None = None) -> list[Any]:`
   and update the docstring to state `run_id` may be `None` for `$0` sync
   endpoints and that `local_seq` is required to build `Mention.raw_ref`.
7. `src/sonar/providers/google_maps.py:158` and
   `src/sonar/providers/facebook.py:185` — once (6) lands, change
   `run_id: str` to `run_id: str | None` so both match the fixed Protocol
   and the other five adapters. (Outside this review's file list; flag for
   the provider-owning worker, don't apply blind.)
8. `src/sonar/providers/registry.py:10` — change
   `PROVIDERS["x"] = XProvider()` to `PROVIDERS["x"] = _XProvider()`.
9. `tests/fixtures/README.md` — either rename `labels.jsonl` (lines 12, 29)
   to `labels.json` and describe it as "a single JSON object keyed by
   `mention_id`" (matching the file that exists), or, if JSON Lines is the
   intended long-term shape, note that `labels.json` is a placeholder ahead
   of the real format. Pick one; state which in the same edit.
10. `tests/fixtures/README.md` — add a line under Layout (after line 15)
    pointing to `tests/fixtures/samples/README.md` and its documented
    exemption from Rule 1, so the "never hand-written" rule doesn't read as
    silently contradicted by the `samples/` directory.
11. `tests/fixtures/samples/README.md:10-13` — update the table to list all
    current sample files (14, not 2), or replace the table with "see
    directory listing" if it will keep drifting.
