# Sonar video

The hackathon cut, built with Remotion. Seventy-four seconds of hard cuts on
the music's beat grid (the Eva take runs 69.6 s; the storyboard targeted 60): a tour of Brand24 as a product in its own screenshots, a
`KILLED` stamp, Monid in its own screenshots, then how sonar rebuilt the
feature set on Monid — every figure read from the frozen demo run under
`results/demo/` and `results/demo-empty/` through the typed loader in
`src/data/results.ts`, every third-party number quoted from
`src/data/external-facts.json` with a reviewed screenshot as its citation.
Nothing in a card is typed by hand. A missing file, a missing cited field, or
a storyboard that does not resolve stops the bundle before a frame is drawn.

## Rules the cut has to satisfy

- Sixty to ninety seconds, 1080p. Captions ship as `out/sonar.srt` (the type
  on screen carries every spoken line; nothing is burned in).
- The incumbent's price beside the measured cost on screen (`price-vs-brief`).
- A visible Monid call (`monid-docs-run`, then the `run_trace` cast).
- `#monid` in the outro, with the repository URL.
- Nothing negative said about the incumbent; the gate greps for it.

## The system

Three measured clocks, one resolver, no accumulated durations:

| Clock | File | Written by |
|---|---|---|
| music beat grid | `src/data/beat-grid.json` | `capture/beat-grid.py` (numpy spectral flux; `--tap` to override) |
| narration cues | `src/data/narration.json` (`startMs`/`endMs` are mp3-relative) | `capture/measure-cues.mjs` (ffmpeg silencedetect; N cues must give N segments) |
| the cut | `src/data/storyboard.json` (anchors: `{ms}`, `{beat:i}`, `{hit:i}`, `{cue:id}`) | by hand |

`src/timeline/resolve.mjs` turns anchors into absolute milliseconds and then
frames in one function; Remotion (`src/timeline/index.ts`) and the gate
(`capture/check-shot-reality.mjs`) import the same file, so the cut the
renderer draws is the cut the gate checked.

Look: true black, plate white, one signal orange spent in one place (the
`KILLED` act, the price figures, an abstention's retract). Big Shoulders for
stamps and act titles, Geist Mono for plates, specs, figures and the one
terminal shot. Three gestures in the whole cut: the scan (a screenshot
revealed top-to-bottom by one orange line), the slam (a stamp lands from 1.12×
to 1× in four frames), the count (a figure runs up over ten frames). No fades.

## Sound and micro-motion

Every effect is synthesised by `capture/sfx.py` (numpy, seeded, 48 kHz
mono, each under 500 ms, peak −6 dBFS) into `public/sfx/`: `tick`, `key`,
`shutter`, `click`, `blip`, `sweep`, `whoosh`, `hit`, `stamp`, `chime`. No
recordings, no licences; replace any file with a recording of the same name
and record its licence in `docs/HANDOFF.md`. `storyboard.json` `sfx.volume`
is the bus.

A sound is attached to the thing that moves, at the frame it moves, by the
component that draws it (`components/Sfx.tsx`): a key per typed character,
a blip per receipt or bar row, a click when a chip or citation lands, a
sweep under every scan and read-line, a tick on every count step and every
cast line, a hit under `KILLED` (the music drops to 15 % for six frames), a
stamp under `SONAR`, `RECONCILED` and the ratio landing, a chime on the
outro. `components/CutTrack.tsx` adds a tick on every hard cut and a whoosh
on every act change, from `TIMELINE`. One sound per visual event, none
under a still frame.

Moves on a screenshot: `hold`, `push` (1 → 1.03), `pan-down`, `zoom`
(`zoom: [from, to]` toward `focus`), `punch` (instant cut-in at `at`), and
`flash` (one-frame plate flash with a shutter, for the photo burst). Act A
opens with six tight crops of the tracked Brand24 captures at one beat
each, then the pricing page zooms onto the Team card.

## Shot list

`pnpm timeline` prints the resolved table (start, end, frames, and which shots
each cue lands on). Seven acts, twenty-seven shots:

| Act | Shots | Shows | Source of every number |
|---|---|---|---|
| brand24 | `a0`–`a7`, `p1`–`p6` | plate `SUBJECT / BRAND24`; brand24.com home; a six-shot photo burst (dashboard, reach numbers, sentiment chart, AI insights panel, positives gauge, Team card) with shutters; features, AI insights, reach + sentiment panel; pricing wide, then a zoom onto the Team seat with its chip | `public/shots/brand24-*.png`, `external-facts.json` (`brand24.sources`, `brand24.price.team` == `receipt.incumbent.price_usd_month`) |
| killed | `b1` | full-bleed `KILLED` on the bar line, `WE KILL / MONID HACKATHON` | — |
| monid | `c1`–`c5` | monid.ai home (tool-count chip), tools, social-media tools, the Reddit tool page (per-call prices), `POST /v1/run` in the API reference | `public/shots/monid-*.png`, `external-facts.json` (`monid.tools`) |
| rebuild | `d0`–`d6` | `SONAR` stamp with the session id; the brief (brand, competitors, window, sources); the real `run_trace` cast at ×6; mentions by source; share of voice + sentiment with intervals; topics + two real citations + the X gap; the voice line | `results/demo/receipt.json`, `stats.json`, `digest.json`, `public/casts/run_trace.cast` |
| receipt | `e1`–`e3` | receipt rows (runs, came-back-empty, failed, Monid, model, voice, total); the seat and the brief on one axis; the ratio, giant, with the 4-brief monthly figure | `results/demo/receipt.json` (`totals`, `comparison`, `incumbent`) |
| honest | `f1`–`f2` | PicPay's share of voice abstains (grey dash, same gesture); the label audit read against the bar from `src/sonar/config.py` | `results/demo/stats.json`, `receipt.json` (`audit`), `src/data/repo-facts.json` (`auditBar`) |
| outro | `g1`–`g2` | `RECONCILED` stamped over the receipt's own rows; "The receipt is the product.", the repo, `#monid` | `results/demo/receipt.json`, `src/manifest.ts` (`PUBLISHED`) |

## Assets and how they are made

- **Screenshots** — `capture/shots.manifest.json` lists the pages;
  `pnpm shoot` (Playwright) captures each into `public/shots/<name>.png` with
  a `<name>.json` sidecar (`url`, `captured_at`, dims, `redactions`,
  `pii_reviewed`). Cookie-consent chrome is hidden before the shot. Look at
  every PNG, then set `pii_reviewed: true`; `pnpm collect` writes the dims
  into `src/data/shots.json`. Logged-in pages: launch Chrome with
  `--remote-debugging-port=9222 --user-data-dir=$HOME/chrome-shoot`, sign in
  there, then `node capture/shoot.mjs --cdp http://127.0.0.1:9222 --only <name>`.
- **Narration** — `node capture/emit-voicescript.mjs` writes
  `VOICE-SCRIPT.md`, one paragraph per cue with a `<break>` between them.
  Paste it into the ElevenLabs web UI (voice Eva, `weA4Q36twV5kwSaTEL0Q`,
  Eleven Multilingual v2), download, save as `public/narration.mp3`, then
  `pnpm measure` (the breaks are what the measurer finds; when the voice
  also pauses that long inside a cue, the extra segments are merged back by
  character share and the merge is printed). Library voices are
  402 through the API on the free plan (`docs/HANDOFF.md`, W7.2), which is
  why this is a browser step.
- **Music** — `public/music.mp3` is "Cosmic Countdown" trimmed from
  19.187 s to 62 s at −20 LUFS; `uv run python capture/beat-grid.py
  public/music.mp3 --trim-start-ms 19187` rebuilds the grid (bars fall on
  beat indices 4k). Provenance of the track is recorded in `docs/HANDOFF.md`.
- **Casts** — unchanged: `capture/record-casts.mjs` records real sonar runs
  into `public/casts/`, `capture/emit-cast-json.mjs` pre-parses them.

## Commands

```
pnpm lint         # tsc
pnpm collect      # repo facts + cast JSON + screenshot dims
pnpm timeline     # the resolved cut, as a table
pnpm shots        # the gate (below); run before every render
pnpm preview      # out/preview.mp4 at half scale
pnpm cuts         # one still per cut from the render → out/cuts.png
pnpm render       # out/sonar.mp4
pnpm srt          # out/sonar.srt
pnpm still:social # ../results/social/receipt-card.png (1200×630 share card, same numbers)
```

`make video` from the repo root runs the whole chain and copies
`sonar.mp4`, `sonar.srt` and `cuts.png` into `results/video/`, which is
what the README links.

## The gate

`pnpm shots` (`capture/check-shot-reality.mjs`) fails on any of:

1. a literal dollar amount, verdict, digest, or the words "all billed" in
   `src/{cards,shots,components}`;
2. a number in the narration or a stamp that is not in `results/demo`,
   `results/demo-empty`, or an external fact whose screenshot is tracked;
   `brand24.price.team` must equal the receipt's incumbent price;
3. a cast that was not recorded from a sonar command;
4. a storyboard that does not resolve (non-contiguous, out of act order,
   over the 90 s cap, unknown card or receipt row, unmeasured narration);
5. a screenshot that is missing, untracked, unreviewed, mis-sized, or from a
   different host than the fact that cites it;
6. a stale generated file (`beat-grid.json`, `narration.json` measurement,
   `shots.json`) — the failure names the script to re-run;
7. wording that pairs "billed" with "empty" as a partition, or says anything
   negative about the incumbent;
8. a sound name in `src/sfx.ts` with no tracked 48 kHz mono WAV under
   500 ms in `public/sfx/`, or a `zoom`/`punch`/`focus`/`flash` field the
   storyboard uses wrongly.

`tests/test_published_claims.py` mirrors 2 and 5 in Python and
`scripts/privacy_gate.py` checks every tracked screenshot's sidecar (and OCRs
the PNGs when `tesseract` is on PATH).

## Verification

- `ffprobe out/sonar.mp4`: 1920×1080, 74.4 s, audio track present.
- `pnpm cuts` then look at `out/cuts.png`: every frame carries a screenshot
  or ≥120 px type, no frame mostly empty, `KILLED` on the bar line.
- `pnpm lint`, `pnpm shots`, `make validate`: green.
