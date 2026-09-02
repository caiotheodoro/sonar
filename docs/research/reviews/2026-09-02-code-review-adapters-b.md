# Code review — adapters batch B (2026-09-02)

**Scope**: `src/sonar/providers/tiktok.py`, `instagram.py`, `google_maps.py`,
`facebook.py`, `trustpilot.py`, `g2.py`, `elevenlabs.py`,
`tests/test_adapters_short_video.py`, `tests/test_adapters_reviews.py`,
`tests/test_adapters_b2b.py`, `tests/test_adapter_elevenlabs.py`,
`tests/fixtures/samples/`.

**Checked against**: `docs/research/2026-09-02-task-graph-and-design.md`
Endpoint reference table and Pipeline rules, `docs/monid/inspect/{trustpilot,
g2,elevenlabs}_*.json`, `CONTRACTS.md` (Mention, cluster_key rules,
author_hash rule, OQ-3, OQ-5, OQ-6), `src/sonar/config.py` `SOURCE_PLAN`.

**Command run**: `uv run pytest tests/test_adapters_short_video.py
tests/test_adapters_reviews.py tests/test_adapters_b2b.py
tests/test_adapter_elevenlabs.py -q` → **139 passed, 0 failed**. All four
files are green, but green here does not mean correct — see F2 below: the
suite never exercises the code path that breaks.

**Verdict: FAIL** — the Trustpilot and G2 adapters do not implement the
`Provider` protocol they are registered under (no `Mention` is ever
produced, a raw reviewer name is carried in the parsed output, and
`cluster_key()` raises `KeyError` on the adapter's own `parse()` output);
TikTok's `build_input` drops a field the endpoint reference table lists as
input; ElevenLabs' `/voices` path bypasses the Monid client/ledger entirely.
All tests pass because none of them drive the code through the path that's
broken.

---

## Findings

### F1 — S1 — `src/sonar/providers/trustpilot.py`, `src/sonar/providers/g2.py` — the two-call adapters never produce a `Mention`, and leak the raw reviewer name

`src/sonar/providers/base.py:50-68` types `Provider.parse()` as returning
"a list of Mention records." Every other adapter in scope (`tiktok.py:249`,
`instagram.py:265`, `google_maps.py:209`, `facebook.py:237`) calls
`Mention(...)`/`Mention.model_validate(...)`. `trustpilot.py:100-171` and
`g2.py:98-167` do not — `parse()` returns a `list[dict]` of intermediate,
untyped fields (`native_id, text, rating, author_name, published_at, url,
engagement`) and stops there. Nothing else in the repo converts these dicts
into a `Mention` (`grep -rn "Mention(" src/sonar/providers/trustpilot.py
src/sonar/providers/g2.py` — 0 hits; `pipeline.py` does not exist yet).
Concretely:

1. **Raw name leak** (violates CONTRACTS `Mention.author_hash`: "the raw
   handle is never stored"). `trustpilot.py:153-156,163` and
   `g2.py:151-154,161` put the review author's real name straight into the
   output dict under `"author_name"` — for the shipped sample fixtures that
   is literally `"Maria S."`, `"João P."`, `"Ana Costa"`, `"Carlos Lima"`
   (`tests/fixtures/samples/trustpilot_get_company_reviews_sample.json:9,29`,
   `tests/fixtures/samples/g2_get_product_reviews_sample.json:9,27`). Both
   files define a correct `_author_hash()` helper
   (`trustpilot.py:19-21`, `g2.py:19-21`) that is **never called** — dead
   code sitting next to the exact bug it would fix. No test asserts the raw
   name's absence (contrast `test_adapters_reviews.py:144-151,318-324`,
   which does this for google_maps/facebook by dumping the parsed Mentions
   to JSON and asserting the raw name/id is not in it).
2. **`cluster_key()` is unreachable without a hand-fed dict.**
   `trustpilot.py:181-183` and `g2.py:177-179` do
   `return str(item["mention_id"])`, but `parse()`'s own output (point 1's
   dict shape) never has a `"mention_id"` key — a `_mention_id()` helper is
   defined (`trustpilot.py:24-26`, `g2.py:24-26`) and, like `_author_hash`,
   never called. `provider.cluster_key(provider.parse(raw, ...)[0])` raises
   `KeyError` today. `tests/test_adapters_b2b.py:119-122` and `:226-229`
   test `cluster_key` only against a literal
   `{"mention_id": "abc123def456abc123def456"}` built by hand — the test
   never calls `parse()` and feeds its output to `cluster_key()`, so the
   break is invisible to the suite.
3. **Timestamps stay raw strings.** `trustpilot.py:164`
   (`"published_at": review.get("date")`) and `g2.py:162`
   (`"published_at": review.get("date")`) never parse the ISO string into a
   `datetime`, unlike every other adapter's `_timestamp`/`_parse_timestamp`
   helper.
4. **`rating` has no range or bool guard.** `trustpilot.py:146-151` does
   `int(rating)` with a bare try/except; `g2.py:144-149` the same. Neither
   checks `1 <= rating <= 5` (CONTRACTS: "rating (1–5 review sources)") or
   rejects a JSON boolean (`isinstance(True, int)` is `True` in Python, so a
   boolean rating silently becomes `1`), unlike `google_maps.py:86-94`'s
   explicit `_rating()` which does both.

None of this shows up in `uv run pytest tests/test_adapters_b2b.py -q`
because the suite tests `parse_search`, `parse`, and `cluster_key` as three
independent units and never chains real `parse()` output into
`cluster_key()`, and never asserts anything about the author field at all.

### F2 — S1 — `src/sonar/providers/tiktok.py:198-203` — `build_input` never sets `sortType`

The Endpoint reference table (`docs/research/2026-09-02-task-graph-and-design.md:262`)
lists TikTok's input fields as "`keywords[]`, `maxItems`, `dateRange`,
`sortType`" — four fields, verbatim, the same table row the task brief
names. `TikTokProvider.build_input` (lines 198-203) returns exactly three:

```python
def build_input(self, query: Any) -> dict[str, Any]:
    return {
        "keywords": _terms_of(query),
        "maxItems": _cap_for(query),
        "dateRange": _DATE_RANGE,
    }
```

`sortType` is absent — not defaulted, not omitted-on-purpose per a comment,
just missing. Every other source in this design that has a determinism
knob sets it explicitly and says why (`reddit sort=new`, google_maps
`reviewsSort=newest`); TikTok's own reference-table entry has one and the
adapter drops it, so two runs of the same query have no documented
guarantee of consistent ordering. `tests/test_adapters_short_video.py:91-96`
(`test_tiktok_build_input_full`) asserts the exact three-key dict, so it
currently locks in the omission as "correct" rather than catching it.

### F3 — S1 — `tests/fixtures/samples/*` mislabel `g2_get_product_reviews_sample.json` — G2 schema has no `content`/`title` review fields documented, only `starRating`

Lower-confidence than F1/F2 but concrete: `docs/monid/inspect/g2_get_product_reviews.json`
documents only the **input** (`queryParams: star_rating, page, slug`); it
says nothing about the shape of a returned review object. CONTRACTS OQ-5
("Trustpilot and G2 native id, rating, timestamp and author field names")
lists "Resolved by: W0.3 `docs/monid/inspect/*.json`" — but those files
never resolve it; they carry no `output` schema at all. The field names
`g2.py:139-144,158,144` (`content`, `title`, `reviewId`, `rating` **or**
`starRating`) and `trustpilot.py:138-143` (`text`, `title`, `reviewId`,
`date`) are unverified guesses baked into both the adapter and its own
hand-built sample fixture — self-consistent, not schema-verified. Flagging
because OQ-5 is marked resolved on paper when the cited evidence doesn't
contain what it's cited for; this is not a runtime bug today.

### F4 — S2 — `src/sonar/providers/elevenlabs.py:121-153` — `list_voices`/`resolve_voice` bypass the Monid client and ledger

`list_voices()` (lines 121-153) makes its own `httpx.Client(...).post(...)`
directly to a hardcoded literal `"https://api.monid.ai/v1/run"` (lines 132,
144) instead of going through `sonar.monid.client` (module layout:
"`monid/client.py`, `monid/ledger.py` — run/poll/list; open-before-POST
ledger; reconcile"; the string doesn't even reuse
`config.MONID_API_BASE`). Every other adapter in scope only builds
`dict`s (`build_input`) and parses response bodies (`parse`) — none of them
touch the network. A real `/voices` call made this way gets none of
`monid/client.py`'s 429 backoff, 402 breaker, or ledger row — it directly
contradicts `CONTRACTS.md:203` ("Every Monid call, including the ElevenLabs
voice run and calls that never received a run id, has a row"). No test
exercises this path over real network (`test_adapter_elevenlabs.py` only
unit-tests the private `_parse_voices` on fabricated dicts), so it doesn't
show up as a failure, only as an architectural hole that will fire the
first time `resolve_voice()` is actually called from the pipeline.

### F5 — S2 — `src/sonar/providers/elevenlabs.py:82-115` — `download_audio` can't tell schema drift from the documented "unknown voice" case

`docs/monid/inspect/elevenlabs_text-to-speech.json` notes (line 153): "An
unknown/unauthorized `voice_id` or an exhausted ElevenLabs quota returns a
**COMPLETED** run with the provider error as data — no charge." That is a
named, expected failure mode, distinct from a genuine payload-shape change.
`download_audio()` (lines 82-115) has exactly one failure path for both:
no usable `audio.download_link`/`audio_base64` → raise
`AdapterSchemaError`. There is no fixture or test for the documented
provider-error shape (only `elevenlabs_tts_sample.json`, which has a valid
`audio.download_link`, and hand-mutated "delete the audio key" cases in
`test_adapter_elevenlabs.py:122-136`, which is a stand-in for real drift,
not for the documented error). Since `AdapterSchemaError` is also the
signal the pipeline is meant to use for `schema_drift` abstentions
(Error matrix: "Payload drift | `AdapterSchemaError`, raw saved,
`schema_drift`"), a legitimate "bad voice_id, no charge, try again" would
currently abstain the same way as "Monid changed the response shape" —
worth a distinct signal (or at least a comment/decision noting the
conflation is intentional) before W4.5 wires this into the pipeline.

### F6 — S2 — `src/sonar/providers/trustpilot.py:47-68` — second-call `build_input` never sets `sort`

`docs/monid/inspect/trustpilot_get_company_reviews.json` exposes `sort`,
`stars`, and `keyword` as optional `queryParams` alongside the required
`domain`; the reviews-call branch of `build_input` (lines 55-61) sets only
`domain` and `page`. Unlike Google Maps (`reviewsSort: "newest"`, chosen
deliberately per the Pipeline rule so the fetch is deterministic and
window-aligned) or Facebook/Reddit's explicit sort fields, Trustpilot's
adapter has no ordering guarantee: two calls for the same domain have no
documented reason to return the same page 1, which matters for a tool that
compares this week to last week. (G2's schema has no `sort` field at all,
so `g2.py` isn't in the same position — not flagged.)

### F7 — S2 — `src/sonar/providers/google_maps.py:38,149` — `startUrls` points at a Maps *search* page, not a resolved place

```python
SEARCH_URL = "https://www.google.com/maps/search/"
...
"startUrls": [{"url": SEARCH_URL + quote(name, safe="")}],
```

The design doc's Endpoint reference table only says `startUrls[]`/
`placeIds[]` for `compass/google-maps-reviews-scraper`, without saying
which URL shapes are accepted. A `/maps/search/<query>` URL is a results
listing, not a single business's place page — the review-scraper actor
(as opposed to the general Maps crawler) is documented upstream as
expecting a resolved place URL or a place ID, since it does not itself do
place discovery/disambiguation. This can't be confirmed without a live
call (out of scope here, and the task disallows network), so it's flagged
rather than asserted broken — but it's exactly the risk the task brief
names ("Google Maps `startUrls` is a URL the actor accepts") and should be
checked against the real actor's docs, or against the first live
`sonar record` run (W3.7), before relying on it for the demo.

### F8 — S3 — `src/sonar/providers/elevenlabs.py:72-80` — `build_input` has no defensive cap on `text` length

Design ("Voice: ≤ 900 chars ... number gate") puts the 900-char cap in
`voice/*` (W4.5), not this adapter (W3.6), so this is not a contract
violation as scoped. But `build_input` also does not guard the provider's
own hard ceiling (`docs/monid/inspect/elevenlabs_text-to-speech.json`:
`text.maxLength: 5000`, "split longer texts into multiple runs"). If
`voice/*` ever fails to cap before calling this adapter, nothing here stops
an oversized, 5×-costlier-per-char (relative to the 900-char narration
budget) request from going out. Cheap to add a `len(text) > 5000` guard
that raises before spending money; not required by the current scope, but
worth a one-line note either way.

---

## Things checked and found correct

- Facebook `isRecommended → rating 5|1` (OQ-3) exactly matches
  `facebook.py:107-112`, tested at `test_adapters_reviews.py:303-305`
  (`[5, 1, None]`), including the `null` passthrough.
- Google Maps `maxReviews` is set from `SOURCE_PLAN` for every profile with
  cap > 0 (never left at an actor default) —
  `google_maps.py:144-146`, `test_adapters_reviews.py:88-91`
  (`test_max_reviews_always_set_from_config`, parametrized over smoke/lite/
  full). `reviewsSort="newest"` and `reviewsStartDate` derived from
  `window_days` are both set unconditionally
  (`google_maps.py:150-153`, `test_adapters_reviews.py:79-87,105-107`).
- Facebook `resultsLimit`/`onlyReviewsNewerThan` are both always set the
  same way (`facebook.py:168-179`, `test_adapters_reviews.py:247-262`).
- No raw handle/author name survives into a `Mention` for tiktok,
  instagram, google_maps, facebook: `Mention` (per `CONTRACTS.md:120-136`)
  has no raw-author field at all, only `author_hash`, so it's structurally
  impossible for these four; google_maps/facebook additionally assert this
  by dumping parsed Mentions to JSON and checking the raw string's absence
  (`test_adapters_reviews.py:144-151,318-324`).
- Instagram items without a `timestamp` key correctly get
  `published_at=None`, never invented (`instagram.py:276`,
  `test_adapters_short_video.py:234-235`: `"timestamp absent stays null,
  never invented"`), and the source's `wow_scope` property correctly
  reports `False` (`instagram.py:213-216`,
  `test_adapters_short_video.py:82-85`).
- `config.SOURCE_PLAN` ids/endpoints/prices for all seven sources in scope
  (tiktok, instagram, google_maps, facebook, trustpilot, g2, elevenlabs)
  match the Endpoint reference table and D011 exactly:
  tiktok 0.00045/result, instagram 0.00345/call, google_maps 0.000675/result,
  facebook 0.003/result+0.001/call, trustpilot 0.03 (call) + 0.03 (lookup),
  g2 0.05 (call) + 0.02 (lookup), elevenlabs `eleven_flash_v2_5`
  $0.05/1000 chars.
- ElevenLabs `voice_id` sits under `input.body.voice_id` exactly per
  `docs/monid/inspect/elevenlabs_text-to-speech.json:32-37`
  (`elevenlabs.py:74-80`); `estimate_cost` computes from characters
  (`n_chars / 1000 * ELEVENLABS_USD_PER_1K_CHARS`,
  `elevenlabs.py:117-119`, tested `test_adapter_elevenlabs.py:44-48`), and
  the primary `download_link` / fallback `audio_base64` order matches the
  inspect notes and D011 exactly (`elevenlabs.py:100-109`, tested
  `:50-99`).
- Trustpilot/G2 are correctly two Monid runs (search → id, then reviews),
  correctly abstain to an empty list on an empty search
  (`parse_search` returns `None` on `{"companies": []}"`/`{"products":
  []}` and on a missing key, `trustpilot.py:70-98`, `g2.py:68-96`, tested
  `test_adapters_b2b.py:46-52,154-160`), and both endpoints are correctly
  addressed with `queryParams` (not `body`) per the `"method": "GET"`
  inspect schemas — the required fields (`query` for search, `domain`/
  `slug` for reviews) are present on every call.
- TikTok/Instagram `AdapterSchemaError` is raised on a missing required
  text key, non-list item payload, and non-string text value, and never on
  a merely-absent optional field — same pattern as google_maps/facebook.

---

## Fix list (independently applicable, disjoint files)

1. **`src/sonar/providers/tiktok.py`** — add `"sortType": <value>` to
   `build_input` (line ~202), picking and documenting the actual enum value
   the reference table implies (check the real actor schema at the next
   `monid inspect` opportunity, or record the chosen literal with a
   one-line rationale comment the way `_DATE_RANGE` already has one).
   Update `test_adapters_short_video.py:91-96` to assert the new key.

2. **`src/sonar/providers/trustpilot.py`** — rewrite `parse()` to build and
   return `Mention.model_validate({...})` per-item like the other four
   adapters: use the existing (currently dead) `_author_hash()` for
   `author_hash` and drop `author_name` from the output entirely; use the
   existing (currently dead) `_mention_id()` for `mention_id`; parse
   `review.get("date")` into a `datetime` with the same
   `fromisoformat`-plus-UTC-normalize pattern `google_maps.py:72-83` uses;
   validate `rating` is `1 <= int(rating) <= 5` and reject a `bool` before
   casting, matching `google_maps.py:86-94`; set `cluster_key` to the
   computed `mention_id` directly in the `Mention`, and simplify
   `cluster_key(item)` to `return str(item.mention_id)` (matching
   `google_maps.py:232-234`, `facebook.py:260-262`) now that `item` is a
   real `Mention`. Also add `sort` to the second-call `queryParams` in
   `build_input` (F6) and pick+document a value.

3. **`src/sonar/providers/g2.py`** — same fix as (2), mirrored: real
   `Mention.model_validate(...)` output from `parse()`, use the existing
   `_author_hash()`/`_mention_id()`, parse `date` to `datetime`, validate
   `rating` range/bool-guard, simplify `cluster_key`.

4. **`tests/test_adapters_b2b.py`** — after (2)/(3) land, replace the
   dict-shaped assertions (`items[0]["native_id"]`, `items[0]["rating"]`,
   etc.) with `Mention` attribute assertions matching the pattern in
   `test_adapters_reviews.py`, and add the same "raw name not in dumped
   JSON" assertion those tests use (`test_adapters_reviews.py:144-151`) so
   this exact bug class can't come back silently. Add a test that calls
   `provider.cluster_key(provider.parse(raw, "run", "Nubank",
   local_seq=1)[0])` directly (no hand-built dict) for both providers, so
   the KeyError this review found would have failed CI.

5. **`src/sonar/providers/elevenlabs.py`** — route `list_voices()` through
   `sonar.monid.client` (or, if that module isn't available to this worker
   yet, at minimum replace the hardcoded literal with
   `config.MONID_API_BASE + "/run"` and leave a `# TODO(W2.3 integration)`
   pointing at the ledger requirement) rather than a private `httpx.Client`
   call; this is the one change in this list that may need coordination
   with whoever owns `monid/client.py`, so land it as its own commit and
   flag it for that worker if the client isn't ready.

6. **`src/sonar/providers/elevenlabs.py`** — give the "unknown/unauthorized
   voice_id, no charge" case (F5) a distinct exception or a distinguishable
   `AdapterSchemaError.detail` string (e.g. check for a `provider_response
   .get("error")`/similar shape the fixture doesn't have yet — add a
   `SAMPLE-hand-built-elevenlabs_provider_error.json` fixture once the real
   error shape is known) rather than letting it fall through the same path
   as genuine schema drift; note the decision either way in a code comment
   if the conflation turns out to be intentional.

7. **`src/sonar/providers/google_maps.py`** — confirm against the live
   `compass/google-maps-reviews-scraper` actor (or the W3.7 fixture, once
   recorded) whether a `/maps/search/<name>` URL actually returns that
   business's reviews; if not, resolve to a place URL/place ID first (the
   actor likely supports a `searchStringsArray`-style discovery step, or
   Monid's own catalog may expose a resolver) before the demo brand run.

8. **`CONTRACTS.md`** — OQ-5's "Resolved by" cell cites
   `docs/monid/inspect/*.json`, but those files carry no output schema for
   the review objects (F3); either point it at wherever the field names
   were actually sourced, or reopen it pending a fixture recorded from a
   real run.
