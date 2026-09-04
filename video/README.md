# Sonar video

The hackathon cut, built with Remotion from the assay pipeline. Every number on
screen is imported from the frozen demo run under `results/demo/`
(`receipt.json`, `stats.json`, `digest.json`) through the typed loader in
`src/data/results.ts`; nothing in a scene is typed by hand. A missing file or a
missing cited field stops the bundle before a frame is drawn.

## Rules the cut has to satisfy

- Sixty to ninety seconds, 1080p, captions burned in.
- The first five seconds show what died: the incumbent's monthly price beside
  the receipt's measured cost, side by side on screen.
- A visible Monid call (the `POST /v1/run` trace).
- `#monid` in the outro, with the repository URL.

## Shot list

Timings below are measured from the real `public/narration.mp3` (Rachel runs
slower than the 130 wpm the storyboard assumed — 127 wpm over 162 words is
76.7 s of voice, not the ~64 s target); they sum to 82.2 s, leaving 7.8 s
under the cap. Scene boundaries are not typed by hand: `src/manifest.ts`
derives them from `narration.json`'s measured `startMs`/`endMs` per scene
(`sceneDurationsFrames`), so a re-timed narration reflows this table's actual
cut automatically, though the numbers below still have to be updated by hand
to describe it.

| # | Beat | Scene id | Timing | Shows | Source of every number |
|---|------|----------|-------:|-------|------------------------|
| 1 | The price that died | `price-died` | 0–11.8 s | The incumbent's list price drawn full width, then this brief's measured total on the same axis — no verdict word yet | `results/demo/receipt.json` (`incumbent.price_usd_month`, `totals.total_usd`) |
| 2 | Live `POST /v1/run` | `live-trace` | 11.8–20.6 s | A fresh `sonar run --trace`, replayed from `public/casts/run_trace.cast`; the status strip flips to `POST /v1/run ×1` | cast (W7.3) |
| 3 | The receipt | `receipt` | 20.6–33.9 s | Receipt rows on the tape: run counts, the money split, then `verdict RECONCILED` (earned here); read-line ceremony for the `39.6×` ratio; `×N` counts to 42 | `results/demo/receipt.json` (`totals`, `comparison`, `mentions`, `audit`) |
| 4 | `sonar ask` with citations | `ask` | 33.9–53.9 s | Share of voice for Nubank/Itaú/C6 as one static group; PicPay takes the read-line abstain gesture; a sentiment strip; then `public/casts/ask.cast` with `[1] [2]` docking to real mention URLs; a persistent `X/Twitter — unavailable` chip | cast (W7.3) and `results/demo/{stats,digest}.json` (`share_of_voice[]`+`ci95`, `sentiment[]`, `top_mentions[]`, `coverage_gaps[0]`) |
| 5 | The zero-mention run | `empty-run` | 53.9–70.8 s | Zephyrium Bank from `public/casts/empty_run.cast`: `mentions.fetched → 0`, `verdict RECONCILED`, all 9 runs still billed; then the read-line for `audit 0.84` with a static tick at the `0.85` bar | cast (W7.3), `results/demo-empty/*` (RESULTS_EMPTY), `results/demo/receipt.json` (`audit.agreement`), `src/data/repo-facts.json` (`auditBar`) |
| 6 | Outro | `outro` | 70.8–82.2 s | The two beat-1 read-lines replayed verbatim — price faint, cost amber; `github.com/caiotheodoro/sonar`, `#monid` | `results/demo/receipt.json` and `src/manifest.ts` (`PUBLISHED`) |

`TOTAL_FRAMES` is derived from the scene durations and the manifest throws if
the sum passes ninety seconds.

## What is scaffolded and what is not

Present: the composition `Sonar`, the manifest, the typed results loader, six
placeholder scenes that already render the bound figures, caption overlay,
cast replay, the capture scripts, and the narration placeholder.

Filled by later tasks:

- W7.2 writes `src/data/narration.json` (cues with a `scene` tag, absolute
  `startMs`/`endMs`), speaks it through sonar's own voice path so the
  ElevenLabs run lands on the receipt, and saves `public/narration.mp3`. Then
  `narrationSrc` in the manifest points at it.
- W7.3 records the casts with `capture/record-casts.mjs` into `public/casts/`
  (`doctor`, `run_trace`, `ask`, `empty_run`). Runs that spend credit require
  `SONAR_CAPTURE_SPEND=1`.
- W7.4 replaces the placeholder scenes under `src/scenes/`.
- W7.5 cuts to length, burns captions, exports 1080p.

## Commands

```sh
pnpm install
pnpm lint                              # tsc --noEmit; passes without results/demo
pnpm shots                             # capture/check-shot-reality.mjs
node capture/collect-repo-facts.mjs    # src/data/repo-facts.json (add --tests for the count)
node capture/retime-captions.mjs       # cue times from public/narration.mp3
node capture/emit-voicescript.mjs      # VOICE-SCRIPT.md from narration.json
node capture/generate-voice.mjs        # public/narration.txt for sonar's TTS path
node capture/record-casts.mjs [id ...] # doctor run_trace ask empty_run
pnpm dev                               # Remotion studio; needs results/demo
pnpm render                            # out/sonar.mp4; needs results/demo
```

`pnpm lint` passes on a tree without `results/demo` because the three files
are imported through the `@results` alias, which falls back to an `unknown`
declaration in `src/results.d.ts`. Bundling has no fallback:
`remotion.config.ts` refuses to start without the directory, and the loader
throws on the first cited field that is absent or mistyped.
