# REPRODUCTION.md — from a fresh clone

Two paths. The offline path costs $0 and reproduces the frozen demo
numbers at seed 777. The live path spends Monid and OpenAI credit and
needs keys. W8.1 runs this file verbatim from a temporary directory and
edits any command that does not exit 0.

## Prerequisites

- `git`, `uv` (Python 3.12 is pinned in `pyproject.toml`), `make`.
- Node 20 and `pnpm` only for the video and the Monid CLI.
- `ffmpeg` and `ffprobe` only for the video duration check.

## Offline path (no keys, no spend)

```bash
git clone https://github.com/caiotheodoro/sonar.git
cd sonar
make sync                       # uv sync; installs sonar into .venv
make validate                   # ruff, mypy, pytest, privacy gate, placeholder check
uv run sonar verify results/demo/receipt.json
uv run sonar render results/demo --resamples 10000 --seed 777 --out out/repro
diff <(python -m json.tool results/demo/stats.json) <(python -m json.tool out/repro/stats.json)
```

Expected: `make validate` exits 0; `sonar verify` prints `RECONCILED`
and exits 0; the `diff` prints nothing. `render` re-runs the statistics
from the frozen mentions and labels without touching Monid or OpenAI.

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
pnpm render           # writes video/out/sonar.mp4
ffprobe -v error -show_entries format=duration -of csv=p=0 out/sonar.mp4
```

Expected: duration ≤ 90 s, 1920×1080, captions burned in.

## Claude Code skill

```bash
ls skill/sonar/SKILL.md
```

Point Claude Code at `skill/sonar/` and ask for a brand brief; the skill
runs the same `sonar run` command and pastes the receipt.

## Open questions

- **OQ-REP-1** The exact flags of `sonar render` (`--resamples`, `--seed`,
  `--out`) are fixed at W5.1 when `cli.py` lands. Resolves when W5.1's
  done-check passes; if a flag name differs, W5.1 edits this file in the
  same commit.
- **OQ-REP-2** Whether `make sync` also installs the `@monid-ai/cli`
  through pnpm or leaves it to the wizard. Resolves at W1.7 when the
  Makefile is written; the wizard already handles the install, so the
  offline path never needs it either way.
- **OQ-REP-3** The video host (HF dataset or GitHub release asset) is
  chosen at W8.3; the README link is the only place it appears, so this
  file does not change.
