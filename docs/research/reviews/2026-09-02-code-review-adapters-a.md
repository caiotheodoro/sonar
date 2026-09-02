# Code review — reddit/news/youtube/youtube_comments adapters (2026-09-02)

**Scope**: `src/sonar/providers/reddit.py`, `src/sonar/providers/news.py`,
`src/sonar/providers/youtube.py`, `src/sonar/providers/youtube_comments.py`,
`tests/test_adapters_reddit_news.py`, `tests/test_adapters_youtube.py`,
`tests/fixtures/samples/*`.

**Checked against**: `docs/research/2026-09-02-task-graph-and-design.md`
Endpoint reference table and Pipeline rules, `CONTRACTS.md` (Mention,
`mention_id` rule, `cluster_key` rules, `author_hash`, `raw_ref`, `run_id`
nullability), `src/sonar/config.py` `SOURCE_PLAN`, `src/sonar/providers/base.py`
`Provider` Protocol, `src/sonar/text/match.py`.

**Command run**: `uv run pytest tests/test_adapters_reddit_news.py
tests/test_adapters_youtube.py -q` → **101 passed**. All findings below are
real behavior confirmed by direct execution (throwaway scripts under
`/private/tmp/.../scratchpad/probe1.py`, no network), not covered by the
existing green suite.

**Verdict: FAIL** — one silent-wrong-data bug (S1) and one confirmed
Protocol-conformance break (S2) that will hard-fail two of the four adapters
the moment Wave 5's generic `pipeline.py` calls `Provider.parse()` the way
`base.py` itself declares it.

---

## Findings

### S1 — `src/sonar/providers/youtube.py:188`, `src/sonar/providers/youtube_comments.py:112` — `local_seq` silently defaults instead of being validated, corrupting `raw_ref`

`base.py:56` types `Provider.parse`'s `local_seq` as `int | None = None` and
its docstring (`base.py:63-64`) says *"local_seq is required to build
Mention.raw_ref."* `reddit.py:219,233` and `news.py:189,203` both honor this:
they accept `int | None = None` and guard it explicitly
(`reddit.py:244-245`, `news.py:214-215`):

```python
if local_seq is None or local_seq < 1:
    raise ValueError("local_seq (ledger row of the raw payload) is required, >= 1")
```

`youtube.py:188` and `youtube_comments.py:112` instead declare
`local_seq: int = 1` — a different type *and* a silent default — with no
validation at all. Confirmed by direct execution:

- Omitting `local_seq` does not raise; it silently stamps every mention's
  `raw_ref` as `"1#<index>"` regardless of which ledger row actually saved
  the payload. `raw_ref` is CONTRACTS' durable back-reference to the raw
  payload (`CONTRACTS.md` §Mention); a wrong `local_seq` here is wrong data
  written straight into the receipt's audit trail, and nothing signals the
  mistake — the row validates fine (`"1#0"` matches the `raw_ref` pattern).
- Passing `local_seq=None` or `local_seq=0` — both valid under the
  Protocol's own type — is *not* rejected before parsing either; it falls
  through to `Mention.model_validate` and blows up with an opaque
  `pydantic.ValidationError` (`raw_ref` `'None#0'`/`'0#0'` fails pattern
  `^[1-9][0-9]*#(0|[1-9][0-9]*)$`) instead of the clean `ValueError`/
  `AdapterSchemaError` that reddit/news give for the same mistake.

Neither failure mode is exercised by `tests/test_adapters_youtube.py` — every
call there either passes a valid `local_seq` or relies on the `= 1` default
in a way that happens to be correct for `local_seq=1` fixtures, so the gap is
invisible in the current suite.

### S2 — `src/sonar/providers/reddit.py:220,234`, `src/sonar/providers/news.py:190,204` — `parse`/`parse_with_report` use keyword `aliases`, not the Protocol's `terms`

`base.py:57` names the match-terms parameter `terms: Sequence[str] | None =
None`. `youtube.py:189` and `youtube_comments.py:113` match it exactly.
`reddit.py:220,234` and `news.py:190,204` instead call the same parameter
`aliases: Sequence[str] = ()`. `runtime_checkable` Protocol `isinstance`
checks (used by `TestRegistration.test_registered_and_available` in both
test files) only look at attribute/method *names*, not parameter names, so
this passes silently today. But any caller that follows the Protocol's own
declared signature — e.g. the generic 6-way fetch loop Wave 5's
`pipeline.py` is scoped to write — breaks for exactly these two adapters:

```
reddit.PROVIDER.parse(raw, run_id, "Nubank", local_seq=1, terms=["Nu"])
TypeError: RedditProvider.parse() got an unexpected keyword argument 'terms'
news.PROVIDER.parse(raw, run_id, "Nubank", local_seq=1, terms=["Nu"])
TypeError: NewsProvider.parse() got an unexpected keyword argument 'terms'
```

Confirmed by direct execution. This is the same class of drift the prior
review (`docs/research/reviews/2026-09-02-code-review-config-providers.md`,
S1) flagged as fixed once `base.py` grew `local_seq`/`terms`; the fix landed
in the Protocol and in two of four adapters, not the other two.

### S3 — `src/sonar/providers/reddit.py:267-269`, `src/sonar/providers/news.py:230-232` — the `skipped_blank_text` counter is dead code

Both adapters count a "blank text, skipped" case in `parse_with_report`, but
in both files the field that becomes `text` is already guaranteed non-blank
by an earlier `_require_str` call before the blank check ever runs:

- `reddit.py`: posts always have a required, non-blank `title`
  (`reddit.py:249`) so `text` is at minimum the title; comments require a
  non-blank `body` (`reddit.py:253`) directly as `text` — either way
  `_require_str` already raised before `if not text:` (`reddit.py:267`)
  could see an empty string.
- `news.py`: `title` is required non-blank (`news.py:227`) and becomes
  `text` at minimum, so `if not text:` (`news.py:230`) is likewise
  unreachable.

`ParseReport.skipped_blank_text` can therefore never be non-zero (matches
`tests/test_adapters_reddit_news.py:146`, which only ever asserts it equals
`0`). Not wrong data, just a counter and a `continue` branch that document a
behavior the code cannot actually exhibit — worth removing or wiring to a
field that can genuinely be blank (e.g. an optional `body`/`snippet` alone,
if a future payload shape allows a post/result with a blank required field
to slip through some other path).

---

## Checks that passed (no finding)

- **Reddit comment `cluster_key` stays the parent post id**, including the
  `postId`-present, `postId`-absent-but-parseable-from-`url`, and
  neither-present (mention_id fallback, counted in
  `cluster_key_fallbacks`) cases — `reddit.py:269-277`, exercised by
  `tests/test_adapters_reddit_news.py:151-166`.
- **Upvotes land in `engagement`** for both reddit posts and comments
  (`upVotes` → `upvotes`), verified against
  `tests/test_adapters_reddit_news.py:180,187,204`.
- **A comment with no body does not crash uncontrolled.** Reddit
  (`_require_str` on `body`) and YouTube comments (`require` on `comment`)
  both raise the documented `AdapterSchemaError` for missing *or*
  whitespace-only body/comment fields (confirmed by direct execution for
  reddit's blank-not-missing case, which the existing tests only exercise
  via key deletion, not blanking) — this is the intended schema-drift path
  (`docs/research/2026-09-02-task-graph-and-design.md` §Error matrix
  "Payload drift"), not an unhandled crash.
- **News `_results` handles a zero-results page** (`{"results": []}`, with
  or without a sibling `errors` key) correctly: 0 mentions, no exception,
  confirmed by direct execution. An `errors`-only payload with no
  `results`/`items`/`data` key at all falls into the generic
  `AdapterSchemaError` "no list found" path (`news.py:57-74`); this is
  consistent with the error matrix's "Payload drift" row and the endpoint
  reference table (which documents only `results[...]`, no `errors[]`), so
  it is not a contract violation — flagged for confirmation once W3.7 records
  a live TinyFish error response, not a required fix.
- **`unit_cost` matches `config.SOURCE_PLAN`** for all four adapters: reddit
  (`per_call_usd + n*per_result_usd`), youtube and youtube_comment
  (`0 + n*per_result_usd`), news (`0.0` unconditionally) all match
  `SourcePlan.estimate_usd` and are pinned by
  `tests/test_adapters_reddit_news.py:117-123`,
  `tests/test_adapters_youtube.py:209-214,345-350`.
- **`run_id=None` is accepted** end-to-end for news (the `$0` sync
  endpoint): confirmed by direct execution (`news.PROVIDER.parse(raw, None,
  "Nubank", local_seq=1)` produces `Mention.run_id is None`), matching
  CONTRACTS OQ-2 ("`null` when the run returned no id ($0 sync endpoints)").
- **`matched_terms` comes from the real alias matcher.** All four adapters
  import `match_terms` from `sonar.text` (re-exported from
  `sonar.text.match`, the word-boundary regex matcher), and none locally
  reimplement a substring/`in` test.
- **Endpoint reference table shapes**: reddit's `build_input` sets
  `searches`, `sort=new`, `time=week`, `maxItems`/`maxPostCount`/
  `maxComments` all at the profile cap, and `includeMediaLinks=True`
  (`reddit.py:182-191`); youtube always sets `maxResults` and `dateFilter`
  (`youtube.py:172-180`); youtube comments send `startUrls`/`maxComments`
  (`youtube_comments.py:98-103`); news sends `input.queryParams` with
  `query`, `domain_type="news"`, `after_date`, `page` (`news.py:157-164`),
  page bounded to `MAX_PAGE=10` and the profile cap
  (`news.py:128-131,154-155`).
- **Every sample payload fixture is named as a sample** (`_sample.json` or
  `SAMPLE-hand-built-*`, per `tests/fixtures/samples/README.md`); all four
  files this review touches (`reddit_reddit-scraper-lite_sample.json`,
  `tinyfish_search_sample.json`, `youtube_sample.json`,
  `youtube_comments_sample.json`) follow the convention.
- **`cluster_key` per source matches CONTRACTS**: reddit → post id, youtube
  video → `mention_id`, youtube comment → `videoId`, news → `mention_id`;
  enforced independently by `Mention._source_rules`'s
  `expected_cluster_key` in `models.py` for the sources it can derive
  (youtube, news), and by adapter logic + tests for reddit/youtube_comment.

## Open question, not a finding

`youtube_comments.py:102` divides the profile's comment cap across
`startUrls` (`max(1, cap // len(urls))`) because the actor's real semantics
for `maxComments` — per video vs. per run — aren't confirmed
(`youtube_comments.py:10-13` documents this explicitly). The chosen formula
is safe under either interpretation (billed total never exceeds the cap) but
can under-fetch if the actor applies it per video. Worth confirming against
`docs/monid/inspect/` once real fixtures land (W3.7); no code change is
warranted without that confirmation.

---

## Fix list (disjoint files, independently applicable)

1. **`src/sonar/providers/youtube.py`** — change `parse`'s `local_seq: int =
   1` (line 188) to `local_seq: int | None = None` and add the same guard
   reddit/news use (`if local_seq is None or local_seq < 1: raise
   ValueError(...)`) before building any `raw_ref`. Update the docstring
   (lines 193-195) accordingly; it currently claims the default "only
   satisfies the Provider protocol," which is no longer true once the
   Protocol's own default (`None`) is honored.
2. **`src/sonar/providers/youtube_comments.py`** — same change, same line
   shape, at `parse`'s `local_seq: int = 1` (line 112) and its docstring
   (lines 116-118).
3. **`src/sonar/providers/reddit.py`** — rename the `aliases` keyword to
   `terms` in both `parse` (line 220) and `parse_with_report` (line 234) so
   the call matches `base.py`'s Protocol; update the one internal call site
   (`reddit.py:224`) and the docstrings that say "or an alias" accordingly.
4. **`src/sonar/providers/news.py`** — same rename, `aliases` → `terms`, in
   `parse` (line 190) and `parse_with_report` (line 204), plus the internal
   call site (`news.py:194`).
5. **`src/sonar/providers/reddit.py`** and **`src/sonar/providers/news.py`**
   — either delete the unreachable `skipped_blank_text` branch (lines
   267-269 and 230-232 respectively) and the field from `ParseReport`, or
   file a one-line note in the module docstring that it is reserved for a
   payload shape that does not exist today. Low priority; do this only if
   fixes 1-4 land first, since it touches the same two files as #3/#4 — a
   single worker should own reddit.py's #3+#5 together and news.py's #4+#5
   together to keep file ownership disjoint from #1/#2.

Fixes 1-2 (youtube.py, youtube_comments.py) and fixes 3+5 / 4+5
(reddit.py, news.py) are on disjoint files and can be applied by two
different workers in parallel.
