# sonar

Brand and competitor listening as a pay-per-call CLI. Every run ends with a
receipt: each Monid run id with its billed cost, including the ones that
returned nothing, next to the price of the tool it replaces.

Built for Monid's "We Kill" hackathon (Sep 1 to 10, 2026).

## The kill

**Incumbent: Brand24 Team, $349 per month.** Source: brand24.com/prices,
checked 2026-09-02. The plan includes 10,000 mentions per month.

Evidence: `results/incumbent/brand24-2026-09-02.png` (full-page capture) and
`results/incumbent/archive-url.txt` (Wayback snapshot). Decision record:
`docs/DECISIONS.md`, entry D001.

Sonar replaces the Brand24 workflow a small team actually runs: a brief on
one brand and up to three competitors over the last 14 days, with share of
voice, sentiment, week-over-week change, topics, and spike detection. You pay
per Monid call, once per brief, instead of $349 per month for a seat.

## The receipt is the product

Listening tools sell a dashboard. Sonar sells the bill. Each run writes
`receipt.json` with:

- **every Monid run**, including runs that failed, timed out, or returned
  zero results, each with its run id, HTTP status, result count, and cost
  taken from `GET /v1/runs`, never estimated;
- **every OpenAI call** (classifier, tiebreak, embeddings, chat) with tokens
  and cost on a separate line;
- **the ElevenLabs narration call**, billed through Monid like the rest;
- a **verdict**: `RECONCILED` when every local run matched a billed remote
  run and nothing remote went unmatched; `PARTIAL` when reconciliation was
  incomplete; `REPLAY` when the artifacts came from fixtures, not the network;
- the **incumbent block**: Brand24 Team, `$349`, the URL, the check date;
- a **comparison**: sonar's cost for this brief, a monthly equivalent at four
  briefs per month, and the ratio against `$349`;
- **abstentions** and **what could not be checked**, named per source and per
  brand.

`sonar verify results/demo/receipt.json` exits nonzero unless the verdict is
`RECONCILED`. A judge can run it without a Monid key.

The statistics behind the digest are pre-registered before any live data is
frozen: cluster bootstrap intervals, the significance rule, abstention
thresholds, and five hypotheses with their stopping rules live in
`docs/PRE-REGISTRATION.md`. Attacks on sonar's own claims, with how we would
know each one landed, live in `docs/RED-TEAM.md`.

## Scope claimed

- **Sources**: Reddit, YouTube videos and comments, TikTok, Instagram,
  Google Maps reviews, Facebook reviews, Trustpilot, G2, and news search.
  Each source is one Monid endpoint with one adapter; `docs/COVERAGE.md`
  maps every Brand24 source to covered, partial, or not covered.
- **Analysis**: share of voice, sentiment with a two-signal policy
  (classifier plus a deterministic signal, tiebreak on disagreement),
  week-over-week deltas, topic clusters, and daily spike events.
- **Uncertainty**: cluster bootstrap 95% intervals on every share and
  sentiment number, with the design effect printed beside the naive
  interval. Verdicts are `SIGNIFICANT`, `SUGGESTIVE`, `NO_CHANGE_DETECTED`,
  or `ABSTAIN`; sonar abstains rather than reports on thin data.
- **Languages**: Portuguese and English are detected and reported as strata.
  Output is English; quotes stay in the original language.
- **Chat**: `sonar ask <brand> "question"` answers from the session's
  mentions only. Every citation must be a real mention id and every number
  must exist in the session's statistics, or the answer is marked
  `unverified`.
- **Voice**: a narrated brief of at most 900 characters, gated so every
  number in it exists in the digest.
- **Edge cases**: a brand with zero mentions still produces a receipt with
  a nonzero cost (that is hypothesis H4). Rate limits, budget exhaustion,
  provider failures, timeouts, and payload drift each have a defined
  behaviour and exit code.

## Not claimed

- **X coverage.** Monid has no X or Twitter endpoint as of 2026-09-02. The
  adapter is registered as unavailable and every receipt lists X under
  coverage gaps. Brand24 covers X; sonar does not.
- **Influencer scoring.** Brand24 ranks authors by reach and influence. Sonar
  stores authors as hashes and never ranks them.
- **Email alerts.** Brand24 sends scheduled and threshold alerts by email.
  Sonar is a process that exits when the brief is done. Spike detection runs
  inside a brief, and nothing is sent anywhere.

Sonar also does not claim to reproduce Brand24's sample. The sources are
different, the caps are different, and the receipt says which sources
contributed to each number.

## Quickstart

Prerequisites: Python 3.12 or newer, `uv`, Node.js for the Monid CLI, a
Monid API key, and an OpenAI API key.

```bash
git clone https://github.com/caiotheodoro/sonar
cd sonar
bash scripts/setup-wizard.sh      # writes ~/.sonar/.env: Monid key, budget, OpenAI key
uv sync
uv run sonar doctor               # checks keys, endpoints, and the wallet
uv run sonar plan --profile lite Nubank --vs Inter    # cost estimate, no spend
uv run sonar run  --profile lite Nubank --vs Inter    # live run, prints the receipt
uv run sonar ask Nubank "what are people complaining about this week?"
uv run sonar verify out/<session>/receipt.json
```

Profiles and their approximate Monid cost per brief:

| Profile | Sources | Brands | Approximate cost |
|---|---|---|---|
| `smoke` | Reddit and Google Maps | 1 | $0.30 |
| `lite` | all sources, halved caps | brand plus 1 competitor | $0.75 |
| `full` | all sources, full caps | brand plus 3 competitors | $2.80 |

To see the pipeline without a key or any spend:

```bash
uv run sonar render --from results/demo
```

This replays the frozen demo artifacts and prints the same digest and
receipt under a `REPLAY` banner. Fresh-clone reproduction steps are in
`docs/REPRODUCTION.md`.

## Price versus measured cost

The side-by-side below is filled from `results/demo/receipt.json` once the
demo run is frozen. Until then the sonar column is an open question.

| | Brand24 Team | sonar, one `full` brief |
|---|---|---|
| Price | $349 per month | measured in `results/demo/receipt.json`, totals block |
| Mentions | 10,000 per month quota | `mentions.deduped` in the same receipt |
| Failed and empty runs | not itemised | listed in `runs`, each with its cost |
| Interval on every number | none published | 95% cluster bootstrap, 10,000 resamples |
| Verdict | none | `RECONCILED`, or `sonar verify` fails |

**Open question OQ-README-1: measured cost of one `full` brief.** Resolved
when the demo freeze lands `results/demo/receipt.json` with verdict
`RECONCILED`; the number in that file's `totals.total_usd` replaces this
paragraph, and the published-claims test fails if the README and the receipt
disagree.

**Open question OQ-README-2: agreement on the blind hand check.** Resolved
when the 50-label hand check under `results/handcheck/` is finished; the
agreement figure is published here and in `docs/PRE-REGISTRATION.md`
whether or not it clears the 0.85 threshold of hypothesis H5.

## Layout

| Path | What it is |
|---|---|
| `src/sonar/` | the CLI: providers, text, sentiment, topics, stats, report, chat, voice |
| `skill/sonar/` | the Claude Code skill wrapping the CLI, with a human spend-approval gate |
| `CONTRACTS.md` | every record the pipeline emits, field by field |
| `docs/PRE-REGISTRATION.md` | frozen statistics and hypotheses H1 to H5 |
| `docs/DECISIONS.md` | D001 onward, each with a reversal clause |
| `docs/RED-TEAM.md` | numbered attacks on sonar's own claims |
| `docs/COVERAGE.md` | Brand24's source list, row by row |
| `docs/REPRODUCTION.md` | commands from a fresh clone |
| `docs/HANDOFF.md` | spend ledger and operator notes |
| `results/incumbent/` | Brand24 price evidence |
| `results/demo/` | frozen demo artifacts: receipt, digest, stats, topics, narration |
| `results/demo-empty/` | the zero-mention brand's receipt |
| `tests/` | offline tests on recorded fixtures; `make validate` runs everything |

## License

MIT. See `LICENSE`.
