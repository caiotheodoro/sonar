"""WoW tests: two-sided bootstrap p, Holm over the non-null tests, the verdict word.

PRE-REGISTRATION v1.1.2 §Verdict rule and §Abstention thresholds. The per-test
p is ``2 * min(P(delta <= 0), P(delta >= 0))`` over the shared resamples; Holm
runs over the family brands x {net WoW, share WoW} restricted to the tests
with a non-null ``p_raw`` (D013 N2). The verdict word itself is
:func:`sonar.models.derive_wow_verdict`, evaluated ABSTAIN first, then
SIGNIFICANT, SUGGESTIVE, NO_CHANGE_DETECTED (D013 N1); this module decides the
abstention *reason* and pairs every null with an ``Abstention`` row:

* ``below_minimum``: ``n < 20`` or ``n_clusters < 5`` in either period, with
  the estimand's own ``n`` (``SovEntry.n`` for share, ``SentimentEntry.n`` for
  net); every estimate is null.
* ``signals_conflict``: the full-set and confirmed-only intervals exclude 0
  with opposite signs; estimates are kept, only the word abstains.
* ``degenerate``: minimums met but the estimate is undefined (a confirmed-only
  interval with ``n_confirmed = 0``, or no defined bootstrap draw at all).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sonar import config
from sonar.models import Abstention, WowNet, WowShare, derive_wow_verdict
from sonar.stats.bootstrap import FloatArray

CI = tuple[float, float]


def two_sided_p(draws: FloatArray) -> float | None:
    """``min(1, 2 * min(P(d <= 0), P(d >= 0)))`` over the defined draws."""
    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return None
    le = float(np.mean(finite <= 0.0))
    ge = float(np.mean(finite >= 0.0))
    return min(1.0, 2.0 * min(le, ge))


def holm(p_raw: Sequence[float | None]) -> list[float | None]:
    """Holm step-down adjusted p-values over the non-null entries; nulls stay null."""
    indexed = sorted(((p, i) for i, p in enumerate(p_raw) if p is not None), key=lambda t: t)
    m = len(indexed)
    out: list[float | None] = [None] * len(p_raw)
    running = 0.0
    for rank, (p, i) in enumerate(indexed):
        running = max(running, min(1.0, (m - rank) * p))
        out[i] = running
    return out


def ci_sign(ci: CI) -> int:
    """``+1`` / ``-1`` when the interval excludes 0 on that side, else ``0``."""
    lo, hi = ci
    if lo > 0.0:
        return 1
    if hi < 0.0:
        return -1
    return 0


def signals_conflict(ci95: CI, ci95_confirmed_only: CI | None) -> bool:
    if ci95_confirmed_only is None:
        return False
    full, confirmed = ci_sign(ci95), ci_sign(ci95_confirmed_only)
    return full != 0 and confirmed != 0 and full != confirmed


@dataclass(frozen=True)
class PeriodCounts:
    n: int
    n_clusters: int


def below_minimum_detail(
    estimand: str, current: PeriodCounts, previous: PeriodCounts | None = None
) -> str | None:
    """The ``Abstention.detail`` when a period misses a minimum, else ``None``.

    ``previous=None`` checks the current period only: the level estimates
    (``net``, ``share``) need the minimums in the current period, the
    week-over-week delta needs them in both (PRE-REGISTRATION v1.1.3, A5 /
    ``docs/DECISIONS.md`` D018).
    """
    failures: list[str] = []
    periods = [("current", current)]
    if previous is not None:
        periods.append(("previous", previous))
    for name, counts in periods:
        if counts.n < config.MIN_MENTIONS_PER_WEEK:
            failures.append(f"n={counts.n} < {config.MIN_MENTIONS_PER_WEEK} in {name}")
        if counts.n_clusters < config.MIN_CLUSTERS_PER_WEEK:
            failures.append(
                f"n_clusters={counts.n_clusters} < {config.MIN_CLUSTERS_PER_WEEK} in {name}"
            )
    if not failures:
        return None
    return f"{estimand}: " + "; ".join(failures)


@dataclass(frozen=True)
class ShareTest:
    brand: str
    delta: float | None
    ci95: CI | None
    p_raw: float | None
    below_minimum: str | None


@dataclass(frozen=True)
class NetTest:
    brand: str
    delta: float | None
    ci95: CI | None
    ci95_confirmed_only: CI | None
    confirmed_detail: str | None
    p_raw: float | None
    below_minimum: str | None


def _brand_row(brand: str, reason: str, detail: str) -> Abstention:
    return Abstention.model_validate(
        {"scope": "brand", "brand": brand, "source": None, "reason": reason, "detail": detail}
    )


def decide_share(test: ShareTest, p_holm: float | None) -> tuple[WowShare, list[Abstention]]:
    if test.below_minimum is not None:
        return _abstained_share(), [_brand_row(test.brand, "below_minimum", test.below_minimum)]
    if test.delta is None or test.ci95 is None or test.p_raw is None or p_holm is None:
        detail = "share WoW: no defined bootstrap draw"
        return _abstained_share(), [_brand_row(test.brand, "degenerate", detail)]
    verdict = derive_wow_verdict(test.delta, test.ci95, None, test.p_raw, p_holm, share=True)
    return (
        WowShare(
            delta=test.delta, ci95=test.ci95, verdict=verdict, p_raw=test.p_raw, p_holm=p_holm
        ),
        [],
    )


def decide_net(test: NetTest, p_holm: float | None) -> tuple[WowNet, list[Abstention]]:
    if test.below_minimum is not None:
        return _abstained_net(), [_brand_row(test.brand, "below_minimum", test.below_minimum)]
    if test.delta is None or test.ci95 is None or test.p_raw is None or p_holm is None:
        detail = "net WoW: no defined bootstrap draw"
        return _abstained_net(), [_brand_row(test.brand, "degenerate", detail)]
    rows: list[Abstention] = []
    if test.ci95_confirmed_only is None:
        detail = test.confirmed_detail or "n_confirmed = 0"
        rows.append(_brand_row(test.brand, "degenerate", f"ci95_confirmed_only: {detail}"))
    verdict = derive_wow_verdict(
        test.delta, test.ci95, test.ci95_confirmed_only, test.p_raw, p_holm
    )
    if verdict == "ABSTAIN":
        if not signals_conflict(test.ci95, test.ci95_confirmed_only):
            raise AssertionError("ABSTAIN with estimates reported must be a signals conflict")
        rows.append(
            _brand_row(
                test.brand,
                "signals_conflict",
                f"net WoW: full-set ci95={list(test.ci95)} and confirmed-only "
                f"ci95={list(test.ci95_confirmed_only or ())} exclude 0 with opposite signs",
            )
        )
    wow = WowNet(
        delta=test.delta,
        ci95=test.ci95,
        ci95_confirmed_only=test.ci95_confirmed_only,
        verdict=verdict,
        p_raw=test.p_raw,
        p_holm=p_holm,
    )
    return wow, rows


def _abstained_share() -> WowShare:
    return WowShare(delta=None, ci95=None, verdict="ABSTAIN", p_raw=None, p_holm=None)


def _abstained_net() -> WowNet:
    return WowNet(
        delta=None, ci95=None, ci95_confirmed_only=None, verdict="ABSTAIN", p_raw=None, p_holm=None
    )


@dataclass(frozen=True)
class FamilyDecision:
    share: dict[str, WowShare]
    net: dict[str, WowNet]
    p_holm_share: dict[str, float | None]
    p_holm_net: dict[str, float | None]
    abstentions: list[Abstention]


def decide_family(share_tests: Sequence[ShareTest], net_tests: Sequence[NetTest]) -> FamilyDecision:
    """Holm over brands x {net WoW, share WoW} with non-null ``p_raw``, then every verdict."""
    family: list[float | None] = [t.p_raw for t in net_tests] + [t.p_raw for t in share_tests]
    adjusted = holm(family)
    net_adjusted = adjusted[: len(net_tests)]
    share_adjusted = adjusted[len(net_tests) :]
    share: dict[str, WowShare] = {}
    net: dict[str, WowNet] = {}
    p_holm_share: dict[str, float | None] = {}
    p_holm_net: dict[str, float | None] = {}
    rows: list[Abstention] = []
    for test, p_holm in zip(net_tests, net_adjusted, strict=True):
        net[test.brand], extra = decide_net(test, p_holm)
        p_holm_net[test.brand] = p_holm
        rows.extend(extra)
    for share_test, p_holm in zip(share_tests, share_adjusted, strict=True):
        share[share_test.brand], extra = decide_share(share_test, p_holm)
        p_holm_share[share_test.brand] = p_holm
        rows.extend(extra)
    return FamilyDecision(share, net, p_holm_share, p_holm_net, rows)


__all__ = [
    "CI",
    "FamilyDecision",
    "NetTest",
    "PeriodCounts",
    "ShareTest",
    "below_minimum_detail",
    "ci_sign",
    "decide_family",
    "decide_net",
    "decide_share",
    "holm",
    "signals_conflict",
    "two_sided_p",
]
