# The cut

- `sonar.mp4` — 1920×1080, 74.4 s, the hackathon video. Brand24 as a product in its own screenshots, `KILLED`, Monid in its own screenshots, then the brief rebuilt on Monid with every figure read from `results/demo/`, the receipt, the ratio, the abstain and audit beats.
- `sonar.srt` — the eleven spoken lines on the video timeline (no captions are burned in; the type on screen carries each line).
- `cuts.png` — one still per hard cut, 27 in all, pulled from the rendered file (`video/capture/verify-cuts.mjs`, `--mid`). Every frame traces to a file: a reviewed screenshot under `video/public/shots/`, a number in `results/demo/` or `results/demo-empty/`, or a quoted third-party figure in `video/src/data/external-facts.json`.

Regenerate with `make video` from the repo root (`video/README.md` documents the pipeline and the gate that runs before every render). Voice: ElevenLabs "Eva" generated in the web UI, $0 Monid. Music: "Cosmic Countdown", trimmed at 19.187 s.
