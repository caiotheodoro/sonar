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

Target timings; they sum to 78 s, leaving 12 s under the cap for the final cut.

| # | Beat | Scene id | Target | Shows | Source of every number |
|---|------|----------|-------:|-------|------------------------|
| 1 | The price that died | `price-died` | 0–5 s | The incumbent's list price on the left, this brief's measured total on the right, the verdict badge | `results/demo/receipt.json` (`incumbent.price_usd_month`, `totals.total_usd`, `verdict`) |
| 2 | Live `POST /v1/run` | `live-trace` | 5–25 s | `sonar run --trace` on the demo brand, replayed from `public/casts/run_trace.cast`, run list beside it | cast (W7.3) and `results/demo/receipt.json` (`runs[]`, `totals.monid_runs*`) |
| 3 | The receipt | `receipt` | 25–40 s | The receipt scrolling from `public/casts/receipt.cast`: every run including failed and empty, totals, the monthly comparison | `results/demo/receipt.json` (`totals`, `comparison`, `mentions`) |
| 4 | `sonar ask` with citations | `ask` | 40–58 s | The assistant answering from `public/casts/ask.cast`, footnotes resolving to mention ids, the topic table | cast (W7.3) and `results/demo/digest.json` (`top_mentions[]`, `topics[]`) |
| 5 | The sparse-coverage run | `empty-run` | 58–70 s | Avenza: barely any coverage — a receipt that still lists every run and its cost, a digest that draws no conclusions (every estimate abstains), from `public/casts/avenza_empty.cast` | cast (W7.3) and `results/demo-empty/receipt.json`, bound by W7.2 |
| 6 | Outro | `outro` | 70–78 s | `github.com/caiotheodoro/sonar`, `#monid`, the price and the measured cost one last time | `results/demo/receipt.json` and `src/manifest.ts` (`PUBLISHED`) |

Scene durations live in `src/manifest.ts` and are the only place timing is
set; `TOTAL_FRAMES` is derived from them and the manifest throws if the sum
passes ninety seconds.

## What is scaffolded and what is not

Present: the composition `Sonar`, the manifest, the typed results loader, six
placeholder scenes that already render the bound figures, caption overlay,
cast replay, the capture scripts, and the narration placeholder.

Filled by later tasks:

- W7.2 writes `src/data/narration.json` (cues with a `scene` tag, absolute
  `startMs`/`endMs`), speaks it through sonar's own voice path so the
  ElevenLabs run lands on the receipt, and saves `public/narration.mp3`. Then
  `narrationSrc` in the manifest points at it.
- W7.3 records the five casts with `capture/record-casts.mjs` into
  `public/casts/`. Runs that spend credit require `SONAR_CAPTURE_SPEND=1`.
- W7.4 replaces the placeholder scenes under `src/scenes/`.
- W7.5 cuts to length, burns captions, exports 1080p.

## Commands

```sh
pnpm install
pnpm lint                              # tsc --noEmit; passes without results/demo
pnpm check                             # capture/check-shot-reality.mjs
node capture/retime-captions.mjs       # cue times from public/narration.mp3
node capture/emit-voicescript.mjs      # VOICE-SCRIPT.md from narration.json
node capture/generate-voice.mjs        # public/narration.txt for sonar's TTS path
node capture/record-casts.mjs [id ...] # doctor run_trace receipt ask avenza_empty
pnpm dev                               # Remotion studio; needs results/demo
pnpm render                            # out/sonar.mp4; needs results/demo
```

`pnpm lint` passes on a tree without `results/demo` because the three files
are imported through the `@results` alias, which falls back to an `unknown`
declaration in `src/results.d.ts`. Bundling has no fallback:
`remotion.config.ts` refuses to start without the directory, and the loader
throws on the first cited field that is absent or mistyped.
