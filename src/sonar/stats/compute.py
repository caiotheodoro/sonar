"""One call from joined ``(Mention, Label)`` rows to every ``StatsFile`` record."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sonar import config
from sonar.models import (
    Abstention,
    BySourceEntry,
    Event,
    Label,
    Mention,
    SentimentEntry,
    Source,
    SovEntry,
    StatsFile,
    Window,
    WowNet,
)
from sonar.stats.bootstrap import Columns, resample
from sonar.stats.events import detect_events
from sonar.stats.frame import build_frame
from sonar.stats.sentiment import NetStat, SentimentPlan, SourceNetStat
from sonar.stats.sov import SovPlan
from sonar.stats.verdict import decide_family


@dataclass(frozen=True)
class StatsResult:
    """Everything ``stats.json`` carries, plus the abstention rows this layer adds."""

    share_of_voice: list[SovEntry]
    sentiment: list[SentimentEntry]
    by_source: list[BySourceEntry]
    events: list[Event]
    window: Window
    abstentions: list[Abstention]
    what_could_not_be_checked: list[str]
    b: int
    seed: int
    n_units: int
    n_rows: int

    def stats_file(self) -> StatsFile:
        return StatsFile(
            share_of_voice=self.share_of_voice,
            sentiment=self.sentiment,
            by_source=self.by_source,
            events=self.events,
            window=self.window,
        )


def _degenerate(brand: str, source: Source | None, detail: str) -> Abstention:
    return Abstention(scope="brand", brand=brand, source=source, reason="degenerate", detail=detail)


def compute_stats(
    brands: Sequence[str],
    rows: Sequence[tuple[Mention, Label]],
    *,
    sources: Sequence[Source],
    abstentions: Sequence[Abstention],
    now: datetime,
    b: int = config.B,
    seed: int = config.SEED,
    topic_names: Mapping[str, str] | None = None,
) -> StatsResult:
    """Share of voice, sentiment, per-source sentiment, WoW verdicts and events.

    ``brands`` is the brand followed by its competitors; ``rows`` are the
    mention-brand pairs joined with their labels; ``sources`` are the query's
    sources and ``abstentions`` the source-scoped rows the fetch produced (they
    decide ``basis_sources``). ``now`` closes the 14-day window.
    """
    frame = build_frame(brands, rows, sources=sources, abstentions=abstentions, now=now)
    columns = Columns(len(frame.rows))
    sov_plan = SovPlan(frame, columns)
    sentiment_plan = SentimentPlan(frame, columns)
    res = resample(columns, frame.unit_of_row, frame.n_units, b=b, seed=seed)
    shares = sov_plan.evaluate(res)
    nets, per_source = sentiment_plan.evaluate(res)
    decision = decide_family([s.test for s in shares], [n.test for n in nets])

    share_of_voice: list[SovEntry] = []
    sentiment: list[SentimentEntry] = []
    by_source: list[BySourceEntry] = []
    added: list[Abstention] = []
    by_brand_rows = {
        brand: [a for a in decision.abstentions if a.brand == brand] for brand in brands
    }
    net_by_brand = {n.brand: n for n in nets}
    source_by_brand: dict[str, list[SourceNetStat]] = {brand: [] for brand in brands}
    for stat in per_source:
        source_by_brand[stat.brand].append(stat)

    for share_stat in shares:
        brand = share_stat.brand
        share_of_voice.append(
            SovEntry(
                brand=brand,
                n=share_stat.n,
                n_clusters=share_stat.n_clusters,
                share=share_stat.share,
                ci95=share_stat.ci95,
                basis_sources=list(frame.basis_sources),
                wow=decision.share[brand],
            )
        )
        net_stat = net_by_brand[brand]
        sentiment.append(_sentiment_entry(net_stat, decision.net[brand]))
        added.extend(by_brand_rows[brand])
        if net_stat.estimate.degenerate is not None:
            added.append(_degenerate(brand, None, net_stat.estimate.degenerate))
        for source_stat in source_by_brand[brand]:
            by_source.append(_by_source_entry(source_stat))
            if source_stat.estimate.degenerate is not None:
                added.append(
                    _degenerate(brand, source_stat.source, source_stat.estimate.degenerate)
                )

    unchecked = [
        f"{source}: items lacking a timestamp, excluded from WoW and events ({brand})"
        for brand in brands
        for source in frame.basis_sources
        if not frame.wow_scope.get((brand, source), True)
    ]
    return StatsResult(
        share_of_voice=share_of_voice,
        sentiment=sentiment,
        by_source=by_source,
        events=detect_events(frame, now, topic_names),
        window=frame.window,
        abstentions=added,
        what_could_not_be_checked=unchecked,
        b=res.b,
        seed=res.seed,
        n_units=res.n_units,
        n_rows=res.n_rows,
    )


def _sentiment_entry(stat: NetStat, wow: WowNet) -> SentimentEntry:
    return SentimentEntry(
        brand=stat.brand,
        n=stat.n,
        n_confirmed=stat.n_confirmed,
        pos=stat.pos,
        neg=stat.neg,
        neu=stat.neu,
        net=stat.estimate.point,
        ci95=stat.estimate.ci95,
        ci95_iid=stat.estimate.ci95_iid,
        design_effect=stat.estimate.design_effect,
        wow=wow,
    )


def _by_source_entry(stat: SourceNetStat) -> BySourceEntry:
    return BySourceEntry(
        brand=stat.brand,
        source=stat.source,
        n=stat.n,
        n_clusters=stat.n_clusters,
        pos=stat.pos,
        neg=stat.neg,
        neu=stat.neu,
        net=stat.estimate.point,
        ci95=stat.estimate.ci95,
        ci95_iid=stat.estimate.ci95_iid,
        design_effect=stat.estimate.design_effect,
        wow_scope=stat.wow_scope,
    )


__all__ = ["StatsResult", "compute_stats"]
