# REPRODUCTION.md — from a fresh clone

Two paths. The offline path costs $0: it verifies the frozen demo, replays
it, and runs the whole pipeline against recorded fixtures without a key.
The live path spends Monid and OpenAI credit and needs keys. W8.1 ran this
file verbatim (2026-09-04) and replaced every command that did not exit 0.

## Prerequisites

- `git`, `uv` (Python 3.12 is pinned in `pyproject.toml`), `make`.
- Node 20 and `pnpm` only for the video and the Monid CLI.
- `ffmpeg` and `ffprobe` only for the video duration check.

## Offline path (no keys, no spend)

```bash
git clone https://github.com/caiotheodoro/sonar.git
cd sonar
make sync                       # uv sync; installs sonar into .venv
make validate                   # mypy, pytest, privacy gate, placeholder check, published-claims gate
uv run sonar verify results/demo/receipt.json
uv run sonar render --from results/demo
uv run sonar run --fixtures --profile smoke Nubank --out out/repro
```

Expected: `make validate` exits 0; `sonar verify` prints `RECONCILED`
and exits 0; `render --from` prints the stored receipt and digest under a
REPLAY banner with verdict `REPLAY`; `run --fixtures` runs the whole
pipeline (fetch, dedup, label, stats, topics, receipt) against the recorded
run bodies under `tests/fixtures/` with a fake model seam, touches neither
Monid nor OpenAI, and writes a receipt whose verdict is `REPLAY` (so
`sonar verify out/repro/receipt.json` exits 1 by design: a replay is never
passed off as live).

What this does not do: recompute the frozen `results/demo/stats.json` from
`mentions.jsonl` and `labels.jsonl`. Determinism of the statistics at seed
777 is covered by `tests/test_stats.py` (golden bootstrap results), which
`make validate` runs; `sonar render` re-renders stored artifacts only.

The empty-brand edge case reproduces the same way:

```bash
uv run sonar verify results/demo-empty/receipt.json
```

Expected: `RECONCILED`, every source abstained with reason `empty`, and
`totals.monid_usd` greater than zero.

## Live path (keys required, spends credit)

```bash
bash scripts/setup-wizard.sh            # writes ~/.sonar/.env; see docs/HANDOFF.md
uv run sonar doctor                     # keys, reachability, wallet balance; $0
uv run sonar plan --profile lite <brand> --vs <competitor>   # prints estimate, no calls
uv run sonar run  --profile lite <brand> --vs <competitor> --trace
uv run sonar reconcile --session <session_id>   # 10 minutes after the run
uv run sonar verify out/<session_id>/receipt.json
uv run sonar ask <brand> "What are people complaining about this week?" --session <session_id>
uv run sonar spend
```

Expected: `run` exits 0 and prints the receipt card with the incumbent
price beside the measured cost; `reconcile` then `verify` print
`RECONCILED`; `ask` returns an answer whose citations are mention ids in
the session; `spend` prints session and ledger totals for
`docs/HANDOFF.md`. A `lite` run costs about $0.75 in Monid credit and
under $0.50 in OpenAI credit.

Exit codes are the error matrix in the design reference: 2 for a bad
query, 3 for a Monid 402 (breaker), 4 when `GET /v1/runs` fails and the
receipt is `PARTIAL`, 0 for everything else including empty results.

## Claims and privacy gates

```bash
make check-claims     # $349 identical in report/incumbent.py, README, demo receipt; narration numbers present in results/demo
make privacy-gate     # no raw author handles under results/
make check-placeholders
```

All three exit 0 on the shipped tree.

## Video

```bash
cd video
pnpm install
pnpm lint
pnpm collect          # repo facts, cast JSON, screenshot dims
pnpm shots            # every on-screen claim traces to results/, a cast, or a reviewed screenshot
pnpm render           # writes video/out/sonar.mp4
pnpm srt              # writes video/out/sonar.srt (the cues on the video timeline)
ffprobe -v error -show_entries format=duration -of csv=p=0 out/sonar.mp4
```

Expected: duration ≤ 90 s (the current cut is 74.4 s), 1920×1080, captions as the
`out/sonar.srt` sidecar (nothing is burned in; the type on screen carries the
line).

## Claude Code skill

```bash
ls skill/sonar/SKILL.md
```

Point Claude Code at `skill/sonar/` and ask for a brand brief; the skill
runs the same `sonar run` command and pastes the receipt.

## Open questions

- **OQ-REP-1 — RESOLVED (W8.1, 2026-09-04).** `sonar render` shipped as
  `render --from DIR` with no `--resamples`/`--seed`, and it re-renders
  stored artifacts rather than recomputing statistics. The offline block
  above now runs the three commands that exist (`verify`, `render --from`,
  `run --fixtures`); the seed-777 determinism claim lives in
  `tests/test_stats.py`. See `docs/HANDOFF.md`, 2026-09-03 entry.
- **OQ-REP-2** Whether `make sync` also installs the `@monid-ai/cli`
  through pnpm or leaves it to the wizard. Resolves at W1.7 when the
  Makefile is written; the wizard already handles the install, so the
  offline path never needs it either way.
- **OQ-REP-3 — RESOLVED (W8.3, 2026-09-04).** The cut is committed in the
  repository as `results/video/sonar.mp4` (with `sonar.srt` and the
  `cuts.png` provenance strip); `make video` regenerates all three.
