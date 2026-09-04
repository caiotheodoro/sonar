"""Share of voice: ``n_brand / sum n`` over ``basis_sources`` (PRE-REGISTRATION §Estimands).

``n`` counts relevant mention-brand pairs on the sources that returned for
every compared brand; a mention matching two brands counts once for each.
The denominator sums every compared brand, abstaining ones included, so the
published shares are shares of the whole voice. Per period the brand's own
``n`` and ``n_clusters`` gate the ``below_minimum`` abstention, which nulls
the full-window share as well as the WoW delta.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sonar.stats.bootstrap import (
    Columns,
    FloatArray,
    Resamples,
    percentile_ci,
    ratio,
    ratio_point,
)
from sonar.stats.frame import PERIODS, Frame, Period, Row, count_clusters
from sonar.stats.verdict import CI, PeriodCounts, ShareTest, below_minimum_detail, two_sided_p

Scope = Period | None
SCOPES: tuple[Scope, ...] = (None, *PERIODS)


@dataclass(frozen=True)
class ShareStat:
    brand: str
    n: int
    n_clusters: int
    current: PeriodCounts
    previous: PeriodCounts
    share: float | None
    ci95: CI | None
    test: ShareTest


def _period_counts(rows: Sequence[Row], period: Period) -> PeriodCounts:
    subset = [r for r in rows if r.period == period]
    return PeriodCounts(n=len(subset), n_clusters=count_clusters(subset))


class SovPlan:
    """Registers one count column per ``(brand, scope)`` and evaluates the shares."""

    def __init__(self, frame: Frame, columns: Columns) -> None:
        self.frame = frame
        basis = set(frame.basis_sources)
        in_basis = np.array([r.source in basis for r in frame.rows], dtype=np.bool_)
        self._columns: dict[tuple[str, Scope], int] = {}
        for brand in frame.brands:
            of_brand = np.array([r.brand == brand for r in frame.rows], dtype=np.bool_)
            for scope in SCOPES:
                in_scope = np.array(
                    [scope is None or r.period == scope for r in frame.rows], dtype=np.bool_
                )
                name = f"sov:{brand}:{scope or 'full'}"
                self._columns[(brand, scope)] = columns.add(name, in_basis & of_brand & in_scope)

    def _totals(self, res: Resamples, scope: Scope) -> tuple[int, FloatArray]:
        point = 0
        draws = np.zeros(res.b, dtype=np.float64)
        for brand in self.frame.brands:
            p, cluster, _ = res.column(self._columns[(brand, scope)])
            point += p
            draws += cluster
        return point, draws

    def evaluate(self, res: Resamples) -> list[ShareStat]:
        totals = {scope: self._totals(res, scope) for scope in SCOPES}
        basis = set(self.frame.basis_sources)
        out: list[ShareStat] = []
        for brand in self.frame.brands:
            rows = [r for r in self.frame.rows if r.brand == brand and r.source in basis]
            current = _period_counts(rows, "current")
            previous = _period_counts(rows, "previous")
            point_detail = below_minimum_detail("share", current)
            wow_detail = below_minimum_detail("share", current, previous)
            share: float | None = None
            ci95: CI | None = None
            delta: float | None = None
            delta_ci: CI | None = None
            p_raw: float | None = None
            if point_detail is None:
                point, cluster, _ = res.column(self._columns[(brand, None)])
                total_point, total_draws = totals[None]
                share = ratio_point(point, total_point)
                ci95 = percentile_ci(ratio(cluster, total_draws))
                if share is None or ci95 is None:
                    share, ci95 = None, None
            if wow_detail is None:
                cur_point, cur_draws, _ = res.column(self._columns[(brand, "current")])
                prev_point, prev_draws, _ = res.column(self._columns[(brand, "previous")])
                cur_share = ratio_point(cur_point, totals["current"][0])
                prev_share = ratio_point(prev_point, totals["previous"][0])
                if cur_share is not None and prev_share is not None:
                    delta = cur_share - prev_share
                delta_draws = ratio(cur_draws, totals["current"][1]) - ratio(
                    prev_draws, totals["previous"][1]
                )
                delta_ci = percentile_ci(delta_draws)
                p_raw = two_sided_p(delta_draws)
            out.append(
                ShareStat(
                    brand=brand,
                    n=len(rows),
                    n_clusters=count_clusters(rows),
                    current=current,
                    previous=previous,
                    share=share,
                    ci95=ci95,
                    test=ShareTest(
                        brand=brand,
                        delta=delta,
                        ci95=delta_ci,
                        p_raw=p_raw,
                        below_minimum=wow_detail,
                    ),
                )
            )
        return out


__all__ = ["SCOPES", "Scope", "ShareStat", "SovPlan"]
