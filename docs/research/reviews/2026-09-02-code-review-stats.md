# Code review — statistics layer (2026-09-02)

**Scope**: `src/sonar/stats/bootstrap.py`, `frame.py`, `sov.py`, `sentiment.py`,
`events.py`, `verdict.py`, `compute.py`; `tests/test_stats.py`;
`tests/golden/stats.json`; `src/sonar/config.py`.

**Checked against**: `docs/PRE-REGISTRATION.md` v1.1.2 (§Estimands, §Cluster
bootstrap, §Verdict rule, §Abstention thresholds, §Event rule), `CONTRACTS.md`
1.1.2 (`SovEntry`, `SentimentEntry`, `BySourceEntry`, `WowNet`, `WowShare`,
`Event`, `StatsFile`, `Abstention`, §Resampling frame, §Rules), `docs/DECISIONS.md`
D012 (F1, F3, F5, F6, F7, F8, F15, F18, F19) and D013 (N1–N4).

**Commands run**: `uv run pytest -q tests/test_stats.py` → **35 passed**;
`uv run pytest -q tests/test_stats.py tests/test_published_claims.py
tests/test_models.py` → **216 passed, 5 skipped**; `uv run ruff check
src/sonar/stats/ tests/test_stats.py` → clean; `uv run mypy src/sonar/stats/`
→ clean. Six throwaway probe scripts executed under `uv run python`
(`/private/tmp/.../scratchpad/probe{1..5}_*.py`, no network), independently
re-deriving the bootstrap draws, the Holm adjustment, the two-sided p-value
and the event baseline from scratch (not by calling the library's own
functions on both sides of an assertion) and cross-checking bit-for-bit
against `compute_stats`' output for a hand-built dataset.

**Verdict: PASS** — every claim probed held under independent execution; one
S2 (a threshold that is not actually wired to `config.py` despite the module
docstrings and `test_stats.py`'s own banner claiming "every threshold is read
from `sonar.config`") and one related S3 (further duplicated constants of the
same kind) are the only findings.

---

## Claims verified by execution

All eight probes in the task brief were run and passed; each is also backed
by an existing, currently-green test, listed alongside.

1. **Paired deltas share the same resample indices.**
   `src/sonar/stats/bootstrap.py:126-137` draws one `(iterations, n_units)`
   weight matrix per chunk and multiplies it against **every** registered
   column at once (`cluster[start:stop] = _draw_weights(...) @ units`), so
   every brand/period/subset column consumes the identical per-iteration
   weight. Probe `probe1_bootstrap_pairing.py` hand-rederived the RNG draw for
   `seed=777` and matched `resample()`'s output element-for-element; probe
   `probe4_end_to_end_cross_check.py` cross-checked a full `compute_stats`
   share-WoW delta/CI/p-value against an independent NumPy bootstrap over the
   same units and seed — bit-for-bit equal. `tests/test_stats.py:997`
   (`test_property_self_delta_is_exactly_zero`, a Hypothesis property) and
   `tests/test_stats.py:783` (`test_shared_index_pairs_periods_and_brands`)
   assert `delta == 0.0` and `ci95 == (0.0, 0.0)` for mirrored (current ==
   previous) data — both green.

2. **A cluster spanning both periods is resampled as one unit.**
   `src/sonar/stats/frame.py:145-148` keys `unit_keys` by
   `(brand_order[brand], cluster_key)` only — no period component — so rows
   from the same `cluster_key` in `current` and `previous` collapse to one
   unit id. Probe `probe1_bootstrap_pairing.py` built a unit with 3 current
   rows and 5 previous rows and proved every one of 2000 iterations satisfies
   `cur_draws*5 - prev_draws*3 ≡ 0 (mod 10)`, the identity that only holds if
   both periods carry the same per-iteration unit weight. Probe
   `probe5_spanning_cluster_via_compute_stats.py` ran the full
   `build_frame`→`compute_stats` pipeline with a Reddit post spanning both
   periods among 8 other clusters: 9 distinct `cluster_key`s produced exactly
   `n_units == 9` (not 10), and the spanning post's current- and
   previous-period rows shared one `unit` id.

3. **Two-sided bootstrap `p = 2·min(P(Δ≤0), P(Δ≥0))`.**
   `src/sonar/stats/verdict.py:34-41` (`two_sided_p`). Probe
   `probe2_p_holm_signals.py` recomputed this formula independently (with the
   `min(1, ...)` clamp) over 50 random draw arrays, including NaN-laced ones,
   and matched exactly. `tests/test_stats.py:492`
   (`test_two_sided_p_is_twice_the_smaller_tail_capped_at_one`) is green.

4. **Holm's `m` counts only non-null tests.**
   `src/sonar/stats/verdict.py:44-53` (`holm`) filters `p is not None` before
   computing `m = len(indexed)`. Probe `probe2_p_holm_signals.py` compared
   `verdict.holm()` against an independently written textbook Holm step-down
   across 5 cases (including all-null and empty families) — exact match — and
   isolated the `m` effect directly: with 2 nulls among 5 tests, the smallest
   p is adjusted by `m=3`, not `m=5`. `tests/test_stats.py:500`
   (`test_holm_adjusts_over_non_null_tests_only`) and `:553`
   (`test_decide_family_holm_family_counts_only_non_null_tests`) are green.

5. **Opposite-sign CIs → `ABSTAIN` / `signals_conflict`.**
   `src/sonar/models.py:934-937` (`derive_wow_verdict`) and
   `src/sonar/stats/verdict.py:66-70` (`signals_conflict`). Probe
   `probe2_p_holm_signals.py` called `derive_wow_verdict` directly on 5 hand
   sign-combinations (opposite-sign, same-sign, straddling, and `None`
   confirmed-only) and got exactly the expected `ABSTAIN`/not-`ABSTAIN`
   result in every case; `verdict.signals_conflict` agreed. `below_minimum`
   is checked and short-circuited *before* `derive_wow_verdict` is ever
   called (`verdict.py:123-124`, `:138-139`), so the two abstain reasons can
   never both apply to one test — matching "ABSTAIN evaluated first" and
   D013 N1. `tests/test_stats.py:521` and `:964`
   (`test_signals_conflict_abstains_with_estimates_kept`) are green.

6. **`basis_sources` excludes any source that abstained for any brand.**
   `src/sonar/stats/frame.py:105-111` (`basis_sources_for`) removes a source
   for **every** brand on a single source-scoped `Abstention`, regardless of
   which brand it named. Probe `probe3_basis_sources_config_events.py`
   confirmed this directly, and also confirmed a *brand*-scoped abstention
   does **not** remove a source (only `scope == "source"` rows count).
   `tests/test_stats.py:654` is green.

7. **Events exclude the tested day from the baseline.**
   `src/sonar/stats/events.py:91` (`baseline = [len(by_day[other]) for other
   in days if other != day]`). Probe `probe3_basis_sources_config_events.py`
   built 13 quiet days (2/day) plus a 100-row spike on the tested day and
   confirmed `baseline_median == 2.0`, `baseline_mad == 0.0` — the spike does
   not leak into its own baseline. `tests/test_stats.py:669`
   (`test_event_rule_median_mad_excluding_tested_day`) is green.

8. **`below_minimum` and event thresholds are read from `config.py`.**
   `verdict.py:85-89` reads `config.MIN_MENTIONS_PER_WEEK` /
   `config.MIN_CLUSTERS_PER_WEEK` at call time; `events.py` reads
   `config.EVENT_MIN_COUNT`, `config.EVENT_MAD_MULTIPLIER`,
   `config.EVENT_MIN_CLUSTERS`. Probe
   `probe3_basis_sources_config_events.py` monkeypatched
   `config.MIN_MENTIONS_PER_WEEK` and `config.EVENT_MIN_COUNT` at runtime and
   watched `below_minimum_detail` / `threshold_for` change accordingly —
   proving these are live reads, not baked-in literals. This is where the
   S2 finding below diverges: the Holm-vs-α comparison that actually gates
   `SIGNIFICANT`/`SUGGESTIVE` does **not** live in `stats/` and does **not**
   read `config` at all.

---

## Findings

### S2 — `src/sonar/models.py:117` — `ALPHA` that gates every WoW verdict is a second, unwired copy of `config.HOLM_ALPHA`

`derive_wow_verdict` (`src/sonar/models.py:914-950`) is the sole place the
`p_holm < 0.05` / `p_raw < 0.05` comparisons happen — `sonar.stats.verdict`
only computes `p_raw`/`p_holm` and delegates the word decision to it
(`verdict.py:128`, `:147-149`). Both comparisons
(`models.py:938`: `if p_holm < ALPHA:`; `models.py:948`: `if p_raw < ALPHA:`)
use `ALPHA: Final[float] = 0.05` defined at `models.py:117` — a literal that
does not reference `config` in any way. `models.py` imports nothing from
`sonar.config` (`grep -n "^from sonar" src/sonar/models.py` — no hits),
despite `config.py:14` explicitly saying models.py *can* depend on it
("`models.py` can depend on this module and not the other way round").

`config.py:69` separately defines `HOLM_ALPHA: Final[float] = 0.05`, is
listed in `config.THRESHOLD_INDEX` (`config.py:459`), and is checked against
the PRE-REGISTRATION prose by `tests/test_config.py:45`
(`r"α=([\d.]+) \(Holm\)"`) and by `tests/test_published_claims.py`'s
`test_every_threshold_in_the_index_equals_its_constant`. Both of those tests
create the appearance that `HOLM_ALPHA` is *the* number that governs the
verdict — it is not; it is checked against the docs and then never read by
any code path that decides a verdict. `tests/test_models.py:1506` pins
`(m.MIN_CLUSTERS, m.MIN_N) == (5, 20)` as a literal, and no test anywhere
asserts `m.ALPHA == config.HOLM_ALPHA`.

Confirmed by execution (`probe3_basis_sources_config_events.py`): setting
`config.HOLM_ALPHA = 0.20` at runtime and calling
`derive_wow_verdict(0.1, (0.05, 0.15), None, 0.1, 0.1, share=True)` still
returns `NO_CHANGE_DETECTED`, not `SIGNIFICANT`, proving the verdict path is
blind to `config.HOLM_ALPHA`.

Today both constants equal `0.05`, so no published number is currently
wrong — this is why it is S2, not S1. But this project's own established
mechanism is to change frozen thresholds via a `docs/DECISIONS.md` amendment
(already exercised three times: D012, D013, D014). The very next amendment
that touches `HOLM_ALPHA` would silently fail to reach `derive_wow_verdict`,
producing a wrong `SIGNIFICANT`/`SUGGESTIVE`/`NO_CHANGE_DETECTED` word with
no test failing anywhere — that is a wrong published number by construction,
just not one that exists yet.

**Fix**: import `config` in `models.py` and replace `ALPHA` with
`config.HOLM_ALPHA` (or delete the local constant and reference
`config.HOLM_ALPHA` directly at both call sites), and add a regression test
asserting `models.ALPHA is config.HOLM_ALPHA` (or the direct-reference
equivalent) so a future divergence fails loudly instead of silently.

### S3 — `src/sonar/models.py:105-116` — four more frozen thresholds duplicated from `config.py` with no cross-check

`WINDOW_DAYS` (`models.py:105`, mirrors `config.WINDOW_DAYS_DEFAULT`),
`TOPIC_DISTANCE_THRESHOLD` (`models.py:108`, mirrors
`config.TOPIC_DISTANCE_THRESHOLD`), `MIN_CLUSTERS`/`MIN_N`
(`models.py:110-111`, mirror `config.MIN_CLUSTERS_PER_WEEK`/
`config.MIN_MENTIONS_PER_WEEK`), and `EVENT_MIN_N`/`EVENT_MAD_MULTIPLIER`
(`models.py:115-116`, mirror `config.EVENT_MIN_COUNT`/
`config.EVENT_MAD_MULTIPLIER`) are all independently hardcoded in
`models.py`, same as `ALPHA` above. Unlike `ALPHA`, none of these sit on the
`stats/` computation path — `stats/verdict.py` and `stats/events.py` both
correctly import and use `config`'s copies for the actual numbers (verified
under finding 8 above) — these `models.py` copies are read only by
structural `pydantic` validators (`Event.n`/`n_clusters` `Field` bounds at
`models.py:1213-1214`, `BySourceEntry.meets_h2_minimums` at
`models.py:1179-1182`, used to score H2). A drift here would silently make
validation stale (accepting/rejecting the wrong shapes, or scoring H2 against
the wrong minimums) rather than corrupt a `stats.json` number directly, hence
S3, not S2 — but it is the identical unwired-duplication pattern as the
`ALPHA` finding and is cheapest to fix in the same change.

**Fix**: same as above — either import these five constants from `config` in
`models.py`, or add one test (e.g. in `tests/test_models.py`) that asserts
`(m.ALPHA, m.WINDOW_DAYS, m.TOPIC_DISTANCE_THRESHOLD, m.MIN_CLUSTERS, m.MIN_N,
m.EVENT_MIN_N, m.EVENT_MAD_MULTIPLIER) == (config.HOLM_ALPHA,
config.WINDOW_DAYS_DEFAULT, config.TOPIC_DISTANCE_THRESHOLD,
config.MIN_CLUSTERS_PER_WEEK, config.MIN_MENTIONS_PER_WEEK,
config.EVENT_MIN_COUNT, config.EVENT_MAD_MULTIPLIER)` so the two files can no
longer diverge unnoticed.

---

## Numbered fix list

1. `src/sonar/models.py:117` — import `sonar.config` and source `ALPHA` from
   `config.HOLM_ALPHA` (the constant that actually governs `SIGNIFICANT` /
   `SUGGESTIVE` in `derive_wow_verdict`, `models.py:938,948`); add a test
   pinning the two together.
2. `src/sonar/models.py:105,108,110-111,115-116` — source `WINDOW_DAYS`,
   `TOPIC_DISTANCE_THRESHOLD`, `MIN_CLUSTERS`, `MIN_N`, `EVENT_MIN_N`,
   `EVENT_MAD_MULTIPLIER` from the corresponding `config.py` constants (or
   add the equivalence test) so `models.py`'s structural validators cannot
   silently drift from a future `DECISIONS.md` amendment to `config.py`.

No other finding. Every specifically-probed claim (paired resample indices,
spanning-cluster unit identity, the two-sided p formula, Holm's non-null
`m`, `signals_conflict` → `ABSTAIN`, `basis_sources` exclusion, the event
baseline's day exclusion, and config-driven abstention/event thresholds)
held under independent execution against synthetic data, and the existing
`tests/test_stats.py` suite (including its Hypothesis property tests) is
green and already exercises the same claims by name.
