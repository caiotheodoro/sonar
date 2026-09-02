"""Per-topic estimates: share, net sentiment, and a cluster bootstrap interval on net.

The bootstrap unit is the mention's ``cluster_key`` (PRE-REGISTRATION §Cluster
bootstrap): each unit carries its positive, negative and neutral counts; a
resample draws units with replacement, sums the counts and recomputes net.
The percentile interval at ``config.CI_LEVEL`` is taken over the resamples
whose denominator is positive. Seed and resample count come from ``config``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from sonar import config
from sonar.models import SentimentLabel


@dataclass(frozen=True)
class PolarCounts:
    """Positive, negative and neutral label counts; ``irrelevant`` labels count in none."""

    pos: int = 0
    neg: int = 0
    neu: int = 0

    @property
    def total(self) -> int:
        return self.pos + self.neg + self.neu

    def add(self, label: SentimentLabel) -> PolarCounts:
        if label == "positive":
            return PolarCounts(self.pos + 1, self.neg, self.neu)
        if label == "negative":
            return PolarCounts(self.pos, self.neg + 1, self.neu)
        if label == "neutral":
            return PolarCounts(self.pos, self.neg, self.neu + 1)
        return self


def net_of(counts: PolarCounts) -> float | None:
    """``(pos - neg) / (pos + neg + neu)``; ``None`` when the denominator is zero."""
    if counts.total == 0:
        return None
    return (counts.pos - counts.neg) / counts.total


def share_of(n: int, relevant_total: int) -> float | None:
    """``n / relevant_total``; ``None`` when the divisor is zero."""
    if relevant_total <= 0:
        return None
    return n / relevant_total


def net_ci95(
    units: Sequence[PolarCounts],
    *,
    resamples: int = config.B,
    seed: int = config.SEED,
    level: float = config.CI_LEVEL,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval on net over ``units`` resampled with replacement.

    ``None`` when no unit carries a polar label. A resample whose drawn units
    carry no polar label is skipped; if every resample is skipped the interval
    collapses to the point estimate.
    """
    if not units:
        return None
    pos = np.array([u.pos for u in units], dtype=np.float64)
    neg = np.array([u.neg for u in units], dtype=np.float64)
    neu = np.array([u.neu for u in units], dtype=np.float64)
    total = pos.sum() + neg.sum() + neu.sum()
    if total == 0.0:
        return None
    point = float((pos.sum() - neg.sum()) / total)
    if resamples < 1:
        raise ValueError("resamples must be at least 1")
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(units), size=(resamples, len(units)))
    pos_sum = pos[draws].sum(axis=1)
    neg_sum = neg[draws].sum(axis=1)
    denom = pos_sum + neg_sum + neu[draws].sum(axis=1)
    valid = denom > 0.0
    if not bool(valid.any()):
        return (point, point)
    nets = (pos_sum[valid] - neg_sum[valid]) / denom[valid]
    tail = (1.0 - level) / 2.0 * 100.0
    lo = float(np.percentile(nets, tail))
    hi = float(np.percentile(nets, 100.0 - tail))
    return (lo, hi)


__all__ = ["PolarCounts", "net_ci95", "net_of", "share_of"]
