"""The resampling frame: relevant rows, their bootstrap units, periods and UTC days.

Every statistic in ``sonar.stats`` is computed over the rows this module keeps:
mention-brand pairs whose label is usable (``status`` ``ok`` or ``cached``) and
relevant (``about_brand`` and a non-empty ``matched_terms``; CONTRACTS §Label,
"relevance for stats"). The bootstrap unit is ``(brand, cluster_key)``
(PRE-REGISTRATION v1.1.2 §Cluster bootstrap, D012 F15); a unit carries every
period's rows so the shared index pairs WoW deltas.

Periods follow CONTRACTS §Digest.window: ``current = [now - 7 d, now)`` and
``previous = [now - 14 d, now - 7 d)`` by ``published_at``. A row without a
timestamp, or with one outside both periods, counts for the full-window
estimates and is dropped from WoW and events one by one (D013 A1).
``wow_scope`` is ``False`` for a ``(brand, source)`` only when every fetched
item of that source for the brand lacks ``published_at``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import numpy as np
import numpy.typing as npt

from sonar import config
from sonar.models import (
    Abstention,
    DateRange,
    Label,
    Mention,
    Polarity,
    Source,
    Window,
)

IntArray = npt.NDArray[np.int64]
Period = Literal["current", "previous"]
PERIODS: tuple[Period, ...] = ("current", "previous")
USABLE_STATUSES: frozenset[str] = frozenset({"ok", "cached"})
POLARITIES: tuple[Polarity, ...] = ("positive", "negative", "neutral")


@dataclass(frozen=True)
class Row:
    """One relevant mention-brand pair with everything the estimands read."""

    index: int
    brand: str
    source: Source
    cluster_key: str
    unit: int
    period: Period | None
    day: date | None
    polarity: Polarity | None
    confirmed: bool
    topic_id: str | None
    mention: Mention


@dataclass(frozen=True)
class Frame:
    brands: tuple[str, ...]
    rows: tuple[Row, ...]
    window: Window
    basis_sources: tuple[Source, ...]
    n_units: int
    unit_of_row: IntArray
    wow_scope: Mapping[tuple[str, Source], bool]

    def brand_rows(self, brand: str) -> list[Row]:
        return [r for r in self.rows if r.brand == brand]


def window_for(now: datetime) -> Window:
    """CONTRACTS §Digest.window from ``now`` (UTC-aware, truncated to seconds)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware (UTC)")
    end = now.astimezone(UTC).replace(microsecond=0)
    split = end - timedelta(days=config.WOW_SPLIT_DAYS)
    start = end - timedelta(days=config.WINDOW_DAYS_DEFAULT)
    return Window(
        current=DateRange(start=split, end=end),
        previous=DateRange(start=start, end=split),
    )


def period_of(published_at: datetime | None, window: Window) -> Period | None:
    if published_at is None:
        return None
    if window.current.start <= published_at < window.current.end:
        return "current"
    if window.previous.start <= published_at < window.previous.end:
        return "previous"
    return None


def is_relevant(mention: Mention, label: Label) -> bool:
    """``about_brand`` and a matched term, on a label the model actually produced."""
    return label.status in USABLE_STATUSES and label.about_brand and len(mention.matched_terms) > 0


def basis_sources_for(
    sources: Sequence[Source], abstentions: Sequence[Abstention]
) -> tuple[Source, ...]:
    """Sources that returned for every brand: a source-scoped abstention for any brand
    removes it for all (PRE-REGISTRATION §Estimands, §Abstention thresholds)."""
    abstained = {a.source for a in abstentions if a.scope == "source" and a.source is not None}
    return tuple(s for s in config.SOURCES if s in sources and s not in abstained)


def build_frame(
    brands: Sequence[str],
    rows: Sequence[tuple[Mention, Label]],
    *,
    sources: Sequence[Source],
    abstentions: Sequence[Abstention],
    now: datetime,
) -> Frame:
    """Reduce joined ``(Mention, Label)`` pairs to the frame every estimand reads.

    Rows are ordered by brand (as given) then ``mention_id`` so the iid resample
    index does not depend on the caller's order; units are ordered the same way.
    """
    if len(set(brands)) != len(brands):
        raise ValueError("brands must be distinct")
    brand_order = {b: i for i, b in enumerate(brands)}
    window = window_for(now)
    scope: dict[tuple[str, Source], bool] = {}
    kept: list[tuple[Mention, Label]] = []
    for mention, label in rows:
        if mention.brand not in brand_order:
            raise ValueError(f"row for unknown brand {mention.brand!r}")
        if label.mention_id != mention.mention_id:
            raise ValueError(
                f"label {label.mention_id} does not belong to mention {mention.mention_id}"
            )
        key = (mention.brand, mention.source)
        scope[key] = scope.get(key, False) or mention.published_at is not None
        if is_relevant(mention, label):
            kept.append((mention, label))
    kept.sort(key=lambda pair: (brand_order[pair[0].brand], pair[0].mention_id, pair[0].raw_ref))
    unit_keys = sorted(
        {(brand_order[m.brand], m.cluster_key) for m, _ in kept},
    )
    unit_index = {key: i for i, key in enumerate(unit_keys)}
    out: list[Row] = []
    for index, (mention, label) in enumerate(kept):
        polarity: Polarity | None = label.label if label.label in POLARITIES else None
        published = mention.published_at
        out.append(
            Row(
                index=index,
                brand=mention.brand,
                source=mention.source,
                cluster_key=mention.cluster_key,
                unit=unit_index[(brand_order[mention.brand], mention.cluster_key)],
                period=period_of(published, window),
                day=None if published is None else published.astimezone(UTC).date(),
                polarity=polarity,
                confirmed=label.corroboration == "confirmed",
                topic_id=label.topic_id,
                mention=mention,
            )
        )
    return Frame(
        brands=tuple(brands),
        rows=tuple(out),
        window=window,
        basis_sources=basis_sources_for(sources, abstentions),
        n_units=len(unit_keys),
        unit_of_row=np.array([r.unit for r in out], dtype=np.int64),
        wow_scope=scope,
    )


def count_clusters(rows: Sequence[Row]) -> int:
    return len({r.cluster_key for r in rows})


__all__ = [
    "PERIODS",
    "POLARITIES",
    "USABLE_STATUSES",
    "Frame",
    "Period",
    "Row",
    "basis_sources_for",
    "build_frame",
    "count_clusters",
    "is_relevant",
    "period_of",
    "window_for",
]
