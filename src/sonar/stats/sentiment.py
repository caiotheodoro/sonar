"""Net sentiment ``(pos - neg) / (pos + neg + neu)`` over relevant mentions.

Reported per brand over the full set and over the ``confirmed``-only subset
(PRE-REGISTRATION §Estimands, §Two-signal labelling policy), and per
``(brand, source)`` for every source in ``basis_sources``. The cluster interval
and the iid interval are drawn from the same generator; their width ratio
squared is the design effect, null (``degenerate``) when the iid width is 0.

``SentimentEntry.n`` (relevant mentions, every source) gates the brand's
``below_minimum`` per period, which nulls every brand-level estimate. A
``BySourceEntry`` is nulled only by its own rule (no relevant or no labelled
row): H2 reads its ``design_effect`` under full-window minimums, not per period
(D013 N3), so a brand's per-period abstention does not hide it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sonar import config
from sonar.models import Polarity, Source
from sonar.stats.bootstrap import (
    Columns,
    FloatArray,
    Resamples,
    design_effect,
    percentile_ci,
    ratio,
    ratio_point,
)
from sonar.stats.frame import PERIODS, POLARITIES, Frame, Period, Row, count_clusters
from sonar.stats.verdict import CI, NetTest, PeriodCounts, below_minimum_detail, two_sided_p

Scope = Period | None
SCOPES: tuple[Scope, ...] = (None, *PERIODS)
Subset = str
SUBSETS: tuple[Subset, ...] = ("all", "confirmed")


@dataclass(frozen=True)
class NetEstimate:
    point: float | None
    ci95: CI | None
    ci95_iid: CI | None
    design_effect: float | None
    degenerate: str | None


@dataclass(frozen=True)
class NetStat:
    brand: str
    n: int
    n_confirmed: int
    pos: int
    neg: int
    neu: int
    estimate: NetEstimate
    current: PeriodCounts
    previous: PeriodCounts
    test: NetTest


@dataclass(frozen=True)
class SourceNetStat:
    brand: str
    source: Source
    n: int
    n_clusters: int
    pos: int
    neg: int
    neu: int
    estimate: NetEstimate
    wow_scope: bool


@dataclass(frozen=True)
class _Triple:
    """Point counts and draws for ``(pos, neg, neu)``."""

    point: tuple[int, int, int]
    cluster: tuple[FloatArray, FloatArray, FloatArray]
    iid: tuple[FloatArray, FloatArray, FloatArray]

    @property
    def labelled(self) -> int:
        return sum(self.point)

    def net_point(self) -> float | None:
        pos, neg, neu = self.point
        return ratio_point(pos - neg, pos + neg + neu)

    def net_draws(self, iid: bool = False) -> FloatArray:
        pos, neg, neu = self.iid if iid else self.cluster
        return ratio(pos - neg, pos + neg + neu)


def _period_counts(rows: Sequence[Row], period: Period) -> PeriodCounts:
    subset = [r for r in rows if r.period == period]
    return PeriodCounts(n=len(subset), n_clusters=count_clusters(subset))


def _estimate(triple: _Triple, what: str) -> NetEstimate:
    """Full-window net with both intervals and the design effect, or why it is null."""
    if triple.labelled == 0:
        return NetEstimate(None, None, None, None, f"{what}: pos + neg + neu = 0")
    point = triple.net_point()
    ci95 = percentile_ci(triple.net_draws())
    ci95_iid = percentile_ci(triple.net_draws(iid=True))
    if point is None or ci95 is None or ci95_iid is None:
        return NetEstimate(None, None, None, None, f"{what}: no defined bootstrap draw")
    effect = design_effect(ci95, ci95_iid)
    degenerate = None if effect is not None else f"{what} design_effect: iid ci95 has zero width"
    return NetEstimate(point, ci95, ci95_iid, effect, degenerate)


class SentimentPlan:
    """Registers polarity count columns per brand, subset, scope and per source."""

    def __init__(self, frame: Frame, columns: Columns) -> None:
        self.frame = frame
        rows = frame.rows
        self._brand: dict[tuple[str, Subset, Scope, Polarity], int] = {}
        self._source: dict[tuple[str, Source, Polarity], int] = {}
        for brand in frame.brands:
            of_brand = np.array([r.brand == brand for r in rows], dtype=np.bool_)
            for subset in SUBSETS:
                in_subset = np.array([subset == "all" or r.confirmed for r in rows], dtype=np.bool_)
                for scope in SCOPES:
                    in_scope = np.array(
                        [scope is None or r.period == scope for r in rows], dtype=np.bool_
                    )
                    for polarity in POLARITIES:
                        has = np.array([r.polarity == polarity for r in rows], dtype=np.bool_)
                        name = f"net:{brand}:{subset}:{scope or 'full'}:{polarity}"
                        self._brand[(brand, subset, scope, polarity)] = columns.add(
                            name, of_brand & in_subset & in_scope & has
                        )
            for source in frame.basis_sources:
                of_source = np.array([r.source == source for r in rows], dtype=np.bool_)
                for polarity in POLARITIES:
                    has = np.array([r.polarity == polarity for r in rows], dtype=np.bool_)
                    name = f"net:{brand}:{source}:{polarity}"
                    self._source[(brand, source, polarity)] = columns.add(
                        name, of_brand & of_source & has
                    )

    def _triple(self, res: Resamples, indices: Sequence[int]) -> _Triple:
        pos, neg, neu = (res.column(i) for i in indices)
        return _Triple(
            point=(pos[0], neg[0], neu[0]),
            cluster=(pos[1], neg[1], neu[1]),
            iid=(pos[2], neg[2], neu[2]),
        )

    def _brand_triple(self, res: Resamples, brand: str, subset: Subset, scope: Scope) -> _Triple:
        return self._triple(res, [self._brand[(brand, subset, scope, p)] for p in POLARITIES])

    def evaluate(self, res: Resamples) -> tuple[list[NetStat], list[SourceNetStat]]:
        brands: list[NetStat] = []
        sources: list[SourceNetStat] = []
        for brand in self.frame.brands:
            rows = self.frame.brand_rows(brand)
            current = _period_counts(rows, "current")
            previous = _period_counts(rows, "previous")
            point_detail = below_minimum_detail("net", current)
            wow_detail = below_minimum_detail("net", current, previous)
            full = self._brand_triple(res, brand, "all", None)
            pos, neg, neu = full.point
            n_confirmed = sum(1 for r in rows if r.confirmed)
            estimate = NetEstimate(None, None, None, None, None)
            delta: float | None = None
            delta_ci: CI | None = None
            confirmed_ci: CI | None = None
            confirmed_detail: str | None = None
            p_raw: float | None = None
            if point_detail is None:
                estimate = _estimate(full, "net")
            if wow_detail is None:
                cur = self._brand_triple(res, brand, "all", "current")
                prev = self._brand_triple(res, brand, "all", "previous")
                cur_point, prev_point = cur.net_point(), prev.net_point()
                if cur_point is not None and prev_point is not None:
                    delta = cur_point - prev_point
                delta_draws = cur.net_draws() - prev.net_draws()
                delta_ci = percentile_ci(delta_draws)
                p_raw = two_sided_p(delta_draws)
                if n_confirmed == 0:
                    confirmed_detail = "n_confirmed = 0"
                else:
                    cur_c = self._brand_triple(res, brand, "confirmed", "current")
                    prev_c = self._brand_triple(res, brand, "confirmed", "previous")
                    confirmed_ci = percentile_ci(cur_c.net_draws() - prev_c.net_draws())
                    if confirmed_ci is None:
                        confirmed_detail = (
                            f"n_confirmed = {n_confirmed} but no defined confirmed-only draw"
                        )
            brands.append(
                NetStat(
                    brand=brand,
                    n=len(rows),
                    n_confirmed=n_confirmed,
                    pos=pos,
                    neg=neg,
                    neu=neu,
                    estimate=estimate,
                    current=current,
                    previous=previous,
                    test=NetTest(
                        brand=brand,
                        delta=delta,
                        ci95=delta_ci,
                        ci95_confirmed_only=confirmed_ci,
                        confirmed_detail=confirmed_detail,
                        p_raw=p_raw,
                        below_minimum=wow_detail,
                    ),
                )
            )
            for source in self.frame.basis_sources:
                source_rows = [r for r in rows if r.source == source]
                triple = self._triple(res, [self._source[(brand, source, p)] for p in POLARITIES])
                what = f"by_source {source} net"
                if not source_rows:
                    source_estimate = NetEstimate(
                        None, None, None, None, f"{what}: no relevant mentions"
                    )
                else:
                    source_estimate = _estimate(triple, what)
                s_pos, s_neg, s_neu = triple.point
                sources.append(
                    SourceNetStat(
                        brand=brand,
                        source=source,
                        n=len(source_rows),
                        n_clusters=count_clusters(source_rows),
                        pos=s_pos,
                        neg=s_neg,
                        neu=s_neu,
                        estimate=source_estimate,
                        wow_scope=self.frame.wow_scope.get((brand, source), True),
                    )
                )
        return brands, sources


def source_order(source: Source) -> int:
    return config.SOURCES.index(source)


__all__ = [
    "SCOPES",
    "SUBSETS",
    "NetEstimate",
    "NetStat",
    "Scope",
    "SentimentPlan",
    "SourceNetStat",
    "Subset",
    "source_order",
]
