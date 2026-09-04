# sonar video v2 — "Brand24, killed, rebuilt on Monid"

## Context

The current cut (`video/out/sonar.mp4`, 82s) reads as a terminal screencast: tiny Geist Mono, 60% empty black frames, raw `sonar run --trace` dumps, a continuous "tape" camera that never cuts, and a soft narration that explains numbers nobody can read. Reference the user supplied (Factory AI brand reel, 15s, 24fps): hard cuts every 0.5–2s, true black + orange + white, giant condensed type as the image, real product screenshots in frames, spec-sheet plates in mono caps, halftone/scanline texture, crosshair registration marks.

Goal: a 60s cut that (1) tours Brand24 as a product with real screenshots, (2) interrupts with a KILLED stamp, (3) reveals Monid with real screenshots, (4) shows feature-by-feature how sonar reproduced the Brand24 business on Monid, (5) sells the cost tradeoff, (6) keeps the honest beats (abstain, 0.84 audit) short and positive. Robot voice (ElevenLabs "Eva", `weA4Q36twV5kwSaTEL0Q`) generated through the ElevenLabs web UI in Chrome (library voices 402 on the API for free plans, see `docs/HANDOFF.md:32`). Music: `~/Downloads/Cosmic Countdown.mp3` (225s, 100 BPM, drop at 19.2s). Nothing negative said about Brand24.

Decisions taken with the user: 60s, Brand24 marketing-site screenshots only, Monid public pages + logged-in `app.monid.ai` runs list (blurred), no burned-in captions.

Existing bugs to fix in the rewrite: caption "42 runs, 37 billed, 11 empty" overlaps (a zero-result run is still billed); `SceneEmptyRun` prints "9 runs, all billed" but `monid_runs_billed` is 7; `repo-facts.json` `sonarRev` stale.

## Design system (frontend-design pass)

Subject: a listening unit that reproduces a SaaS product. Vernacular: machine nameplates, stamped verdicts, calibration ticks, lab specimens. Real serials are real content: session `20260904T033800Z-nubank-53455a`, run `01M1PATWZXC7CCCN4ZAT22M685`, `content_digest` prefix. All come from data, never typed (gate check 1).

Generic-default check: "near-black + one vermilion accent" is a known tell, but the brief pins the reference. What makes this not the default: true `#000000` (not tinted), orange confined to ONE act (KILLED) and price figures, real screenshots as the primary image, no fades anywhere, and the scan-reveal as the single motion signature.

Palette (`video/src/theme.ts`, replace T):
- `ink #000000` ground
- `plate #EDEDE9` type, keylines
- `engrave #8A8A85` secondary mono
- `signal #FF4D00` KILLED act, price figures, abstain retract
- `shadow #141414` specimen backing only

Type: **Big Shoulders Display** 800/900 (`@remotion/google-fonts/BigShouldersDisplay`, verified installed; condensed industrial, carries stamps + act titles) + **Geist Mono** 400/500 (keep, already loaded; plates, specs, figures). Two families, clearly distinct. `@remotion/google-fonts/Archivo` has no width axis, rejected. Scale: stamp 420 / headline 160 / act title 72 / spec value 44 mono / plate label 22 mono. Plates in mono caps with slash separators (`TEAM / $349 / MO`), never middle dots.

Layout: 64px margins, 8px grid. Two frame types alternate:
```
SPECIMEN                                  STAMP
+----------------------------------+      +----------------------------------+
| +  [screenshot 1400w, keyline] + |      |                                  |
|                                  |      |      K I L L E D   (fill)        |
| +                              + |      |                                  |
| BRAND24 / PRICING / 2026-09-04   |      | WE KILL / MONID / 2026-09        |
+----------------------------------+      +----------------------------------+
```
Left-aligned plates; stamps fill width. Screenshots get a 1px plate keyline, four crosshair marks, a 3%-opacity scanline overlay, nothing else.

Motion rules: hard cuts on the 600ms beat grid (bar 2400ms). Specimens reveal by a 2px orange scanline sweeping top→bottom in 8 frames. Stamps slam: scale 1.12→1.0 in 4 frames after a 1-frame black hold. Figures count in 10 frames. No fades, no slides, no tape camera. KILLED: 3-frame 6px shake.

## Narration (Eva, robot; ~150 words, target ≤60s; retimed from measured mp3)

Numbers must exist in `results/demo/*.json` or in the new `external-facts.json` (see gates). "twenty-one topics" dropped (count not literal in JSON). Cents are spoken in words; figures on screen come from data.

```
A  Brand24. Social listening. Twenty-five million sources. Mentions. Sentiment. Share of voice. Reports.
   A Team seat: three hundred forty-nine dollars a month.
B  (no voice; stamp + hit)
C  Rebuilt on Monid. One key. One balance. Seventeen hundred tools, paid per call.
   Reddit. YouTube. TikTok. Instagram. Google Maps. News. Voice, too.
D  This is sonar. One brief: a brand, three competitors, fourteen days, ten sources.
   Forty-two calls. Three hundred forty-one mentions. Sentiment and share of voice, each with an interval.
   Topics. A spoken summary. Every number cited to a real post.
E  Total: two dollars and twenty cents. Four briefs a month: eight dollars eighty-one.
   Thirty-nine point six times under the seat.
F  When data is thin, sonar abstains. Our own label audit, zero point eight four, printed on the receipt.
G  The receipt is the product. The code is open. Hashtag monid.
```

## Storyboard (27 shots, 100 BPM grid; ms are targets, final snap to measured cues)

| # | act | ms | kind | content (all values from data) |
|---|---|---|---|---|
| 1 | A | 0–1200 | plate | typewriter `SUBJECT / BRAND24 / SOCIAL LISTENING` |
| 2 | A | 1200–3600 | shot | `brand24-home.png` hero |
| 3 | A | 3600–5400 | shot | `brand24-mentions.png` (features: mentions feed) |
| 4 | A | 5400–6600 | shot | `brand24-sentiment.png` |
| 5 | A | 6600–7800 | shot | `brand24-sov.png` share of voice / reports |
| 6 | A | 7800–9600 | shot | `brand24-ai.png` AI insights / Brand Assistant |
| 7 | A | 9600–12000 | shot | `brand24-pricing.png`, orange keyline on Team; plate `TEAM / $349 / MO / 10,000 MENTIONS` from `receipt.incumbent` |
| 8 | B | 12000–14400 | stamp | 1f black, then full-bleed signal `KILLED`, shake; plate `WE KILL / MONID / 2026-09` |
| 9 | C | 14400–16800 | shot | `monid-home.png` |
| 10 | C | 16800–18600 | shot | `monid-tools.png` directory |
| 11 | C | 18600–20400 | shot | `monid-tool-reddit.png` (trudax/reddit-scraper-lite, per-call price) |
| 12 | C | 20400–22200 | shot | `monid-docs-run.png` POST /v1/run |
| 13 | C | 22200–24000 | shot | `monid-app-runs.png` (blurred), plate `42 RUNS / RECONCILED` |
| 14 | D | 24000–26400 | stamp | `SONAR`, plate `LISTENING UNIT / {sonar_rev} / {session}` |
| 15 | D | 26400–28800 | card | brief: `NUBANK` vs `ITAÚ / C6 BANK / PICPAY`, `14 DAYS / 10 SOURCES`, source ids as mono row |
| 16 | D | 28800–31200 | cast | `run_trace` at ×6, 16 rows, framed as a specimen (only terminal shot) |
| 17 | D | 31200–33600 | card | `MENTIONS → 341` with `by_source` bars |
| 18 | D | 33600–36000 | card | `SENTIMENT` net + CI, `SHARE OF VOICE` 29% [23, 36] (ReadLine) |
| 19 | D | 36000–38400 | card | `TOPICS / EVENTS` + two citation chips from `top_mentions` |
| 20 | D | 38400–40800 | card | `VOICE → ElevenLabs on Monid`, `elevenlabs_usd` plate |
| 21 | E | 40800–43200 | receipt | rows MONID / MODEL / VOICE / TOTAL from `totals` |
| 22 | E | 43200–45600 | card | `$349` vs `$2.20` ReadLines, same axis |
| 23 | E | 45600–48000 | stamp | `39.6×` giant, plate `4 BRIEFS / MO / $8.81` |
| 24 | F | 48000–50400 | card | `PICPAY / NOT ENOUGH DATA / ABSTAINED` retract gesture |
| 25 | F | 50400–52800 | card | audit 0.84 with 0.85 tick, plate `PRINTED ON THE RECEIPT` |
| 26 | G | 52800–55200 | shot | `receipt.json` rendered as specimen, `RECONCILED` stamp |
| 27 | G | 55200–60000 | stamp | `github.com/caiotheodoro/sonar` / `#monid` |

## Architecture (video/)

One timing rule: everything authored in absolute ms on the video timeline, converted to frames in one function `msToFrame(ms) = round(ms*FPS/1000)`. No accumulated scene durations, no tape camera.

Three measured clocks, one resolver:
- `src/data/beat-grid.json` — generated by `capture/beat-grid.py` (numpy only, ffmpeg-piped PCM, spectral-flux autocorrelation; flags `--bpm`, `--offset-ms`, `--tap "3.01,9.02"` override). Fields: `bpm`, `beatsMs[]`, `hitsMs[]`, `trimStartMs`, `trackSha256`, `source`.
- `src/data/narration.json` v2 — cues `{id, act, text, spoken, startMs, endMs}` with times **relative to narration.mp3**, measured by `capture/measure-cues.mjs` (ffmpeg `silencedetect`, must find exactly N segments for N cues or exit 1 with both lists). Header carries `voice {Eva, weA4Q36twV5kwSaTEL0Q, web UI, $0 Monid}` and `measured.mp3Sha256`. Replaces `retime-captions.mjs` (character-proportional guessing).
- `src/data/storyboard.json` — the cut. `narration.offsetMs`, `music {src, volume, duckTo, fadeOutMs}`, `acts[]`, `shots[]` where each shot has `start` anchor `{ms}|{beat:i}|{hit:i}|{cue:id, edge, offsetMs}`, optional `snap:"beat"`, and a `kind` union: `shot{src,crop?,move?,facts?}` | `stamp{text,variant,sub?}` | `card{card}` | `cast{src,speed,rows,castFromMs}` | `receipt{rows,results}`. Contiguous: shot i ends where i+1 starts; only the last shot has `end`.

`src/timeline/resolve.mjs` (+ `resolve.d.mts`; plain ESM so the gate imports the same code) → `resolveTimeline({storyboard, cues, grid, fps})` returns `{shots: ResolvedShot[], totalFrames, acts, narrationFrom, cueFrame(), beatFrames, hitFrames}`. Throws with the shot id on: non-increasing starts, shot < `minShotMs` (400), unknown anchor, `totalMs > capMs` (90000), narration ending after the video. `src/timeline/index.ts` evaluates it at import (`TIMELINE`). `capture/resolve-timeline.mjs --report` prints the table (id, act, kind, startMs, snap Δ, frames); `--srt out/sonar.srt` writes a caption sidecar (insurance for `docs/REPRODUCTION.md:83` which says captions burned in; that line changes to "captions in out/sonar.srt").

New source files:
- `src/timeline/{types.ts, resolve.mjs, resolve.d.mts, index.ts}`
- `src/data/{storyboard.json, beat-grid.json, external-facts.json, shots.json}`; `src/data/facts.ts` (`fact(id)` throws on unknown id, same discipline as `results.ts`)
- `src/shots/ShotView.tsx` — switch on `kind`; each shot is a `<Sequence from durationInFrames premountFor={15} name={id}>` in `Main.tsx`
- `src/components/Screenshot.tsx` (`<Img src={staticFile("shots/x.png")} pauseWhenLoading delayRenderTimeoutInMilliseconds={60000}>`, keyline + crosshairs + scanline overlay + scan reveal, `crop` from `shots.json` dims, `move: hold|push|pan-down`), `Plate.tsx` (mono caption plate), `Stamp.tsx` (slam-in, `killed` variant = full-bleed signal + shake), `FactChip.tsx` (the only way an external number reaches the screen), `ReceiptRows.tsx` (extracted from `SceneReceipt`; row ids `runs|billed|zero|failed|verdict|monid|llm|voice|total|monthly|mentions`; no "all billed" literal)
- `src/cards/{index.ts, Brief, MapMentions, MapSentimentSov, MapTopics, MapVoice, PriceVsBrief, Ratio, PicPayAbstain, Audit, Outro}.tsx` — ported from the six scenes; `CARDS` map keyed by id, gate reads the keys
- `src/shots/CastShot.tsx` wraps `TerminalCast` with negative `startFrame` so a shot opens mid-run
- `capture/{beat-grid.py, measure-cues.mjs, resolve-timeline.mjs, shoot.mjs, shots.manifest.json, collect-shots.mjs, verify-cuts.mjs}`

Modified: `manifest.ts` (constants + RESULTS/RESULTS_EMPTY/PUBLISHED only), `Main.tsx` (hard-cut sequences, narration `<Sequence from={narrationFrom}>`, music `<Audio volume={f => base*duck(f)*fadeOut(f)}>`, `TapeGround` kept as ground), `Root.tsx`, `StatusStrip.tsx` (act-based, keeps the `POST /v1/run ×N` counter), `theme.ts`, `fonts.ts`, `emit-voicescript.mjs` (joins cues with `<break time="0.9s" />`, prints char count), `check-shot-reality.mjs`, `package.json` scripts (`timeline`, `cuts`, `shoot`, `measure`, `srt`), `README.md`, `docs/HANDOFF.md` (W7.6 row), `docs/REPRODUCTION.md`, `scripts/privacy_gate.py`, `tests/test_published_claims.py`, `Makefile` `video` target.

Deleted: `components/{Camera,CaptionOverlay,GridGround,Panels}.tsx`, `beats.ts`, `scenes/Scene*.tsx` (6), `capture/{retime-captions,generate-voice}.mjs`, `public/narration.txt`, `data/voice-rates.json`. `public/music.mp3` and `public/narration.mp3` replaced in place (old `narration.runs.jsonl` stays as W7.2 ledger evidence).

## Gates

`capture/check-shot-reality.mjs` rewrite (imports `resolve.mjs`):
1. Literal scan over `src/{cards,shots,components}` — existing 3 regexes + `/all billed/i`.
2. Number provenance: numbers in cue `text|spoken` and storyboard `text|sub|label` ⊆ numbers in `results/demo/*.json` ∪ `results/demo-empty/*.json` ∪ external facts (`value` and `display`, e.g. `25 million`, `1,700+`→`1700`). A fact counts only if its `shot` PNG + sidecar are `git ls-files` tracked. Cross-check `fact("brand24.price.team").value === receipt.incumbent.price_usd_month`.
3. Casts: ids from storyboard `kind:"cast"`, header `command` matches `sonar`.
4. Timeline: `resolveTimeline` throws = fail; `totalMs ≤ 90000`, note if > 66000; every act has ≥1 shot in declared order; card ids ∈ `CARDS`; receipt rows ∈ row ids.
5. Shots: every `kind:"shot"` src and every `fact.shot` has `public/shots/<name>.png` + `<name>.json` sidecar `{url, captured_at, viewport, width, height, pii_reviewed, redactions[]}` tracked; sidecar dims == PNG IHDR; crop in bounds; `pii_reviewed === true`; sidecar url host == fact `source_url` host.
6. Freshness: `sha256(music.mp3) === beatGrid.trackSha256`; `sha256(narration.mp3) === narration.measured.mp3Sha256`; `collect-shots` output deep-equals `shots.json`. Failure names the script to re-run.
7. Wording: `/(\d+) billed, (\d+) (empty|zero)/` and "all billed" when `monid_runs !== monid_runs_billed` → fail.

`tests/test_published_claims.py`: existing number test gains demo-empty + external facts + storyboard stamp text; new tests `test_every_external_fact_is_backed_by_a_tracked_reviewed_screenshot`, `test_the_external_incumbent_price_matches_the_constant` (== `BRAND24_TEAM.price_usd_month`), `test_every_storyboard_shot_is_committed`, `test_narration_does_not_say_all_billed_when_runs_were_free`.

`scripts/privacy_gate.py`: new `shots` section — every tracked `video/public/shots/*.png` needs a tracked sidecar with `pii_reviewed: true`; host `app.monid.ai` requires non-empty `redactions`; if `tesseract` is on PATH, OCR + run the key/email patterns (else print a skip note).

## Capture workflow

Screenshots (`capture/shots.manifest.json`, names `<site>-<page>`): `brand24-home`, `brand24-mentions`, `brand24-sentiment`, `brand24-sov`, `brand24-ai`, `brand24-pricing`, `monid-home`, `monid-tools`, `monid-tool-reddit` (`trudax/reddit-scraper-lite`, the actor sonar ran), `monid-docs-run`, `monid-app-runs`. Viewport 1920×1080, DPR 1, full-page clipped ≤ 1920×3000 only for pan-down shots.
1. Explore with claude-in-chrome (`tabs_context_mcp` → `tabs_create_mcp` → `navigate` → `find`) to confirm page states, scroll targets (Brand24 features page sections: "Master Media Monitoring", "AI Driven Feature" → Sentiment / Topic Analysis "Share of Voice 26.99%" / AI Insights, "Brand24 for Enterprise" → reports) and the selectors to blur on `app.monid.ai` (balance, email, key fragments). `monid.ai/tools` is JS-rendered (server fetch shows an empty registry), so confirm in the browser.
2. `open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-shoot"`; log into app.monid.ai there once.
3. `cd video && node capture/shoot.mjs --cdp http://127.0.0.1:9222` (Playwright, already a devDependency; injects `filter: blur(12px)` on redaction selectors, writes PNG + sidecar). `--only <name>` to redo one.
4. Read each PNG, then set `pii_reviewed: true`; `node capture/collect-shots.mjs`; `git add public/shots`.

Narration (Eva, ElevenLabs web UI via claude-in-chrome):
1. `node capture/emit-voicescript.mjs` → `VOICE-SCRIPT.md` paste block with `<break>` tags between cues; check char count against the free-plan quota shown in the UI.
2. elevenlabs.io → Text to Speech → add voice "Eva" from library → model Eleven Multilingual v2 (v3 only if break tags misbehave) → paste → Generate → Download → `video/public/narration.mp3`. The user may need to click Download themselves; say so.
3. `ffmpeg -i narration.mp3 -af loudnorm=I=-16:TP=-1.5:LRA=9 -ar 44100 -b:a 160k` → replace, then `node capture/measure-cues.mjs`. Fallback if one take won't segment: generate per cue into `public/narration/<id>.mp3` and assemble with `adelay/amix` in a small `assemble-narration.mjs`.

Music:
```sh
ffplay -ss 19.2 -t 12 "$HOME/Downloads/Cosmic Countdown.mp3"   # audition in-points: 19.2s (first strong onsets) or 41.2s
ffmpeg -i "$HOME/Downloads/Cosmic Countdown.mp3" -ss 19.200 -t 62 \
  -af "loudnorm=I=-20:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.25,afade=t=out:st=59.5:d=2.5" -ar 44100 -b:a 192k video/public/music.mp3
uv run python video/capture/beat-grid.py video/public/music.mp3   # expect ~100 BPM; --tap to override
```
Record source and licence of "Cosmic Countdown" in HANDOFF (user-supplied; provenance unknown to the repo).

## Sequencing

1. Timeline core + gate rewrite against the *current* narration.mp3 re-measured by `measure-cues.mjs` (proves the pipeline before new assets). `pnpm lint`, `pnpm shots` green with placeholder storyboard.
2. Components/cards port, `Main.tsx`/`Root.tsx` swap, delete tape files, theme + fonts (Big Shoulders Display 800/900 added, Space Grotesk dropped).
3. Assets, in parallel: music trim + beat grid; screenshots + sidecars; narration v2 + measure.
4. Author the real storyboard (table above) against measured cues and beats; iterate in `pnpm dev` with `pnpm timeline` and `pnpm cuts` (one still per cut boundary in `out/cuts/`).
5. Python tests, privacy gate, docs (README shot table from `pnpm timeline`, HANDOFF W7.6 row, REPRODUCTION caption line, X-post draft refresh), render, SocialCard re-still.

## Verification

```sh
cd video && pnpm lint
node capture/collect-repo-facts.mjs && node capture/emit-cast-json.mjs && node capture/collect-shots.mjs
pnpm shots && pnpm cuts && pnpm render && pnpm srt
ffprobe -v error -show_entries format=duration:stream=width,height,codec_type -of default=nw=1 out/sonar.mp4   # ~60s, 1920x1080, audio
ffmpeg -i out/sonar.mp4 -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
cd .. && make validate && uv run pytest -rsx tests/test_published_claims.py
```
Then extract a contact sheet (`ffmpeg -vf "fps=2,scale=520:-1,tile=6x5"`) and read it: every frame must carry either a screenshot or ≥120px type; no frame mostly empty; KILLED lands on a hit; numbers legible at 520px wide. Separate validator: a fresh subagent reviews the contact sheet + script against this plan's design rules (no fades, orange only in KILLED/prices, nothing negative about Brand24).

## Risks

- ElevenLabs free plan may block library voices in the web UI too, or the quota may be short; fallback is Eva through a paid month, or a different robotic voice the plan allows. Decide when the UI is open.
- `monid.ai/tools` and `app.monid.ai` are JS apps; capture only over CDP with the logged-in profile. Blur before `pii_reviewed`.
- Large PNGs: DPR 1, clip ≤ 3000px, `premountFor`; `verify-cuts` catches blank first frames; add `prefetch()` if one appears.
- Beat detector may lock to half/double tempo; `--tap` override, and act changes snap to `hitsMs`, so the fine grid costs little.
- `record-casts` unchanged; the single cast shot reuses the existing `run_trace` cast at ×6 (no new Monid spend).
