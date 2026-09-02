# Verification — adapters-a / adapters-b fix lists (2026-09-02)

**Method**: read the current code in `src/sonar/providers/` against each
review's fix-list item, then constructed the failing input each item claims
is now rejected/handled and ran it directly (throwaway scripts under
`/private/tmp/.../scratchpad/probe_a.py`, `probe_b1.py`, `probe_b2.py`,
`probe_b3.py`; no network, sample payloads from `tests/fixtures/samples/`).
Also ran `uv run pytest -q` once: **674 passed**.

## Review A — `2026-09-02-code-review-adapters-a.md` (5 items)

| # | Item | File:line | Status | Evidence |
|---|------|-----------|--------|----------|
| A1 | `youtube.py` `local_seq` typed `int \| None = None` + guard | `src/sonar/providers/youtube.py:199,210-211` | VERIFIED | `parse()` with `local_seq` omitted, `=0`, and `=None` all raise `ValueError: local_seq (ledger row of the raw payload) is required, >= 1` on `youtube_sample.json` — direct execution, no silent `"1#<index>"` default. |
| A2 | `youtube_comments.py` same fix | `src/sonar/providers/youtube_comments.py:112` (guard at 123-124) | VERIFIED | Same three inputs against `youtube_comments_sample.json` all raise the identical `ValueError`. |
| A3 | `reddit.py` `aliases`→`terms` rename (`parse`/`parse_with_report`) | `src/sonar/providers/reddit.py:221-240` | VERIFIED | `reddit.PROVIDER.parse(raw, "run1", "Nubank", local_seq=1, terms=["Nu"])` succeeds (5 mentions); calling with the old `aliases=` keyword now raises `TypeError: RedditProvider.parse() got an unexpected keyword argument 'aliases'`, confirming the rename actually happened rather than just being additive. |
| A4 | `news.py` same rename | `src/sonar/providers/news.py:192-211` | VERIFIED | Same pattern on `tinyfish_search_sample.json`: `terms=` accepted (3 mentions), `aliases=` now raises `TypeError`. |
| A5 | Remove dead `skipped_blank_text` (reddit.py, news.py) | `src/sonar/providers/reddit.py:58-61`, `src/sonar/providers/news.py:61-63` | VERIFIED | `ParseReport` dataclass fields are now `['mentions', 'cluster_key_fallbacks', 'skipped_no_match']` (reddit) and `['mentions', 'skipped_no_match']` (news) — the field and its `continue` branch are gone entirely (deletion option taken, not the "leave a note" option), confirmed by `dataclasses.fields()` at runtime and by `grep -rn skipped_blank_text src/sonar/providers/` returning zero source hits. |

**Review A verdict: all 5 items VERIFIED.** No regressions found; `isinstance(provider, Provider)` still holds for all four adapters.

## Review B — `2026-09-02-code-review-adapters-b.md` (8 items)

| # | Item | File:line | Status | Evidence |
|---|------|-----------|--------|----------|
| B1 | `trustpilot.py`: emit real `Mention`, hashed author, `cluster_key = mention_id`, `sort` set, rating guarded | `src/sonar/providers/trustpilot.py:203-262` (parse), `:56-58` (`_author_hash`), `:272-274` (`cluster_key`), `:170` (`sort: "recency"`), `:101-116` (`_rating`) | VERIFIED | `parse()` on `trustpilot_get_company_reviews_sample.json` returns `list[Mention]` (not dicts); dumping the parsed mentions to JSON contains neither `"Maria S."` nor `"João P."` (both present in the raw fixture); `cluster_key(parse()[0])` returns `mention_id` directly, no `KeyError`; `published_at` is a real `datetime`; a boolean rating (`True`) raises `AdapterSchemaError: ... rating is a boolean`; a rating of `7` raises `AdapterSchemaError: ... rating 7 outside 1-5`; second-call `build_input` includes `"sort": "recency"`. |
| B2 | `g2.py`: same fix, mirrored | `src/sonar/providers/g2.py:195-254`, `:54-56`, `:264-266`, `:99-114` | VERIFIED | Identical checks against `g2_get_product_reviews_sample.json`: real `Mention` list, `"Ana Costa"`/`"Carlos Lima"` absent from the dump, `cluster_key` chains cleanly, `published_at` is a `datetime`, bool/out-of-range rating both raise `AdapterSchemaError`. G2's `build_input` correctly omits `sort` (its schema has none — matches the review's own note that G2 "isn't in the same position" as trustpilot on F6, not a gap). |
| B3 | `tiktok.py`: `build_input` sets `sortType` | `src/sonar/providers/tiktok.py:203-209` (`_SORT_TYPE = "DATE_POSTED"` at line 34) | VERIFIED | `build_input` now returns 4 keys including `"sortType": "DATE_POSTED"`; `tests/test_adapters_short_video.py:91-102` asserts the new key and that it's a real actor enum member. |
| B4 | `elevenlabs.py`: `list_voices`/`resolve_voice` through the Monid client + ledger | `src/sonar/providers/elevenlabs.py:301-330` (`list_voices`), `:351-373` (`resolve_voice`) | VERIFIED | Both now require `client: MonidClient, ledger: Ledger` keyword-only params (confirmed via `inspect.signature`) and `list_voices` body calls `ledger.submit(client, request, ...)` (confirmed by source inspection: `"ledger.submit" in inspect.getsource(...)` is `True`). The old hardcoded `"https://api.monid.ai/v1/run"` literal and private `httpx.Client(...).post(...)` call are gone (`"api.monid.ai" in source` is `False`). The one remaining `httpx.Client` call (line 248) is the signed-`download_link` audio *fetch*, not a Monid API call, and is unreachable in these tests since the provider-error/schema-drift fixtures both return before reaching it. |
| B5 | `elevenlabs.py`: provider-error vs schema-drift distinction, with fixtures | `src/sonar/providers/elevenlabs.py:139-153` (`provider_error`), `:220-263` (`parse_tts`) | VERIFIED | `parse_tts()` on `SAMPLE-hand-built-elevenlabs_text-to-speech_provider-error.json` (the documented `voice_not_found` shape) returns `TtsResult(provider_error="voice_not_found: ...", audio=None)` — no exception. `parse_tts()` on `SAMPLE-hand-built-elevenlabs_text-to-speech_schema-drift.json` (an `mp3_url`-shaped payload, not the documented error or audio shape) raises `AdapterSchemaError: missing 'audio' object in provider response`. The two failure modes are now distinguishable by return type vs. exception, and both fixtures cited by the review exist and are wired into `tests/test_adapter_elevenlabs.py` (`PROVIDER_ERROR_SAMPLE`, `SCHEMA_DRIFT_SAMPLE`, lines 43-44 and used through ~line 532). |
| B6 | `elevenlabs.py`: 900-char narration cap | `src/sonar/providers/elevenlabs.py:203-205`, `NARRATION_MAX_CHARS = 900` (config) | VERIFIED | `build_input("a"*950)` truncates to exactly 900 chars (with a `log.warning`), not a raise. |
| B7 | `elevenlabs.py`: 5000-char provider ceiling guard | `src/sonar/providers/elevenlabs.py:63,198-202`, `PROVIDER_MAX_CHARS = 5000` | VERIFIED | `build_input("a"*5001)` raises `ValueError: text-to-speech text is 5001 chars; provider ceiling is 5000 ...` before any run is submitted; `"a"*5000` is accepted (then truncated to 900 by B6's cap). |
| B8 | `google_maps.py`: `placeIds` fallback path | `src/sonar/providers/google_maps.py:146-176` (`build_input(..., place_id=...)`) | VERIFIED (fallback exists) — underlying F7 question stays open, as the review itself said it must | `build_input(query)` with no `place_id` still emits `startUrls` (search-URL path, default, unchanged); `build_input(query, place_id="ChIJ...")` emits `placeIds: ["ChIJ..."]` and *not* `startUrls`; a blank/whitespace `place_id` raises `ValueError`. `tests/test_adapters_reviews.py:109-137` covers all three cases. This delivers exactly what F7's fix list asked for as the immediate code change (a documented fallback path) — it does **not** and cannot resolve whether the default search-URL path actually returns a business's reviews from the live actor, which F7 itself said requires a live call out of scope for this task. Module docstring (`google_maps.py:7-16`) states this residual risk explicitly. |

**Review B verdict: all 8 items VERIFIED as implemented** (B8's underlying live-actor question is explicitly out of scope for static verification, as the original review itself acknowledged).

## New defect found during verification (not one of the 13 counted items)

**`CONTRACTS.md:467` — OQ-5's "Resolved by" cell still cites `docs/monid/inspect/*.json`, unchanged.** Review B's own fix list (item 8, not separately named in this task's item list but part of the same review) said this citation is wrong because those files carry no output schema for trustpilot/G2 review objects — the field names in `trustpilot.py`/`g2.py` are unverified guesses, not resolved by the cited files. The code fixes (B1/B2) are real and correct against the current guessed field names, but the doc still overclaims resolution. This is a documentation-accuracy gap, not a code bug — flagged for completeness, not blocking B1/B2.

## Verdict: PASS

All 13 code-fix items across both reviews (5 in adapters-a, 8 in adapters-b)
are VERIFIED by direct execution against real sample fixtures, not just by
reading the diff or trusting commit messages. `uv run pytest -q` is green
(674 passed). No regressions or new runtime defects were found; the one gap
found is a stale documentation citation, not a code fault.

### Fix list for anything not VERIFIED

None — every item was VERIFIED. The single follow-up worth tracking:

1. Update `CONTRACTS.md:467` OQ-5's "Resolved by" cell to stop citing
   `docs/monid/inspect/*.json` as the source of trustpilot/G2 field names
   (it documents only the request `queryParams`, not the review-object
   output shape) — either point it at where the names actually came from,
   or reopen OQ-5 pending a real recorded fixture (W3.7).
