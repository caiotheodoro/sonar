"""Event days: ``n_day >= max(5, median + 3 * MAD)`` and ``n_clusters_day >= 3``.

PRE-REGISTRATION v1.1.2 §Event rule. Days are UTC calendar days; the baseline
is the daily count of the brand's relevant, timestamped mentions over the 14
consecutive UTC days ending on ``now``'s date, excluding the tested day (D012
F19), with zero counts for empty days. MAD is the unscaled median absolute
deviation. Each event carries ``baseline_median``, ``baseline_mad`` and
``threshold`` so the rule can be re-derived from the digest.

``label`` is the name of the day's largest topic when the caller supplies
topic names, else the first matched term of the day's highest-engagement
mention; ``exhibit_url`` is that mention's url (CONTRACTS §Digest.events).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta

import numpy as np

from sonar import config
from sonar.models import Event
from sonar.stats.frame import Frame, Row, count_clusters

LABEL_MAX_WORDS = 6


def event_days(now: datetime) -> list[date]:
    """The ``config.EVENT_BASELINE_DAYS`` consecutive UTC dates ending on ``now``'s date."""
    end = now.astimezone(UTC).date()
    days = config.EVENT_BASELINE_DAYS
    return [end - timedelta(days=days - 1 - i) for i in range(days)]


def median(values: Sequence[int | float]) -> float:
    if not values:
        raise ValueError("median of an empty baseline")
    return float(np.median(np.array(values, dtype=np.float64)))


def mad(values: Sequence[int | float], center: float) -> float:
    return median([abs(v - center) for v in values])


def threshold_for(baseline_median: float, baseline_mad: float) -> float:
    return max(
        float(config.EVENT_MIN_COUNT),
        baseline_median + config.EVENT_MAD_MULTIPLIER * baseline_mad,
    )


def _exhibit(rows: Sequence[Row]) -> Row:
    """Highest ``engagement_score``, then ``published_at`` descending, then ``mention_id``."""

    def key(row: Row) -> tuple[int, float, str]:
        stamp = row.mention.published_at
        seconds = stamp.timestamp() if stamp is not None else -math.inf
        return (-row.mention.engagement_score, -seconds, row.mention.mention_id)

    return min(rows, key=key)


def _label(rows: Sequence[Row], exhibit: Row, topic_names: Mapping[str, str]) -> str:
    topics = Counter(r.topic_id for r in rows if r.topic_id is not None)
    if topics:
        largest = min(topics, key=lambda t: (-topics[t], t))
        name = topic_names.get(largest)
        if name:
            return " ".join(name.split()[:LABEL_MAX_WORDS])
    return " ".join(exhibit.mention.matched_terms[0].split()[:LABEL_MAX_WORDS])


def detect_events(
    frame: Frame, now: datetime, topic_names: Mapping[str, str] | None = None
) -> list[Event]:
    names: Mapping[str, str] = topic_names or {}
    days = event_days(now)
    out: list[Event] = []
    for brand in frame.brands:
        by_day: dict[date, list[Row]] = {d: [] for d in days}
        for row in frame.brand_rows(brand):
            if row.day is not None and row.day in by_day:
                by_day[row.day].append(row)
        for day in days:
            rows = by_day[day]
            if not rows:
                continue
            baseline = [len(by_day[other]) for other in days if other != day]
            center = median(baseline)
            spread = mad(baseline, center)
            threshold = threshold_for(center, spread)
            n_clusters = count_clusters(rows)
            if len(rows) < threshold or n_clusters < config.EVENT_MIN_CLUSTERS:
                continue
            exhibit = _exhibit(rows)
            out.append(
                Event(
                    brand=brand,
                    date=day,
                    n=len(rows),
                    n_clusters=n_clusters,
                    baseline_median=center,
                    baseline_mad=spread,
                    threshold=threshold,
                    label=_label(rows, exhibit, names),
                    exhibit_url=exhibit.mention.url,
                )
            )
    return out


__all__ = [
    "LABEL_MAX_WORDS",
    "detect_events",
    "event_days",
    "mad",
    "median",
    "threshold_for",
]
