"""Cluster bootstrap with one shared resample index (PRE-REGISTRATION v1.1.2).

Ported from ``assay/scripts/intervals.py``: one index per iteration, shared by
every estimand, so paired differences are honest. Here the units are the
``(brand, cluster_key)`` pairs of the session and the index is drawn once per
iteration over all of them; every period, brand and estimand reads the same
draw (D012 F15).

Every published estimate is a ratio of counts (share, net, and their WoW
deltas), so a resample is fully described by how many times each unit was
drawn. :class:`Columns` collects row-level indicator masks; the per-unit
totals ``A`` (units x columns) are integers, the draw weights ``W`` (iterations
x units) are integers, and ``W @ A`` is computed in ``int64`` exactly, so the
golden file is bit-stable across machines. The iid bootstrap (rows as units,
ignoring cluster structure) is drawn beside it from the same generator for the
design effect ``(cluster width / iid width)^2``.

Intervals are percentile intervals at ``config.CI_LEVEL`` with linear
interpolation between order statistics, as in the ported script. A draw whose
denominator is zero is undefined (``NaN``) and left out of the percentile and
of the p-value; an estimate with no defined draw has no interval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import numpy.typing as npt

from sonar import config

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

CHUNK_ITERATIONS: Final[int] = 512
"""Iterations drawn per chunk; bounds the ``(iterations, units)`` index in memory."""


class Columns:
    """Named row-level indicator columns; each estimand is a ratio of their weighted sums."""

    def __init__(self, n_rows: int) -> None:
        self._n_rows = n_rows
        self._masks: list[BoolArray] = []
        self._names: dict[str, int] = {}

    def add(self, name: str, mask: BoolArray) -> int:
        if name in self._names:
            raise ValueError(f"column {name!r} already registered")
        if mask.shape != (self._n_rows,):
            raise ValueError(f"column {name!r} has shape {mask.shape}, expected ({self._n_rows},)")
        index = len(self._masks)
        self._names[name] = index
        self._masks.append(mask.astype(np.bool_))
        return index

    def index(self, name: str) -> int:
        return self._names[name]

    def __len__(self) -> int:
        return len(self._masks)

    @property
    def n_rows(self) -> int:
        return self._n_rows

    def matrix(self) -> IntArray:
        """``(rows, columns)`` indicator matrix in ``int64``."""
        if not self._masks:
            return np.zeros((self._n_rows, 0), dtype=np.int64)
        return np.stack(self._masks, axis=1).astype(np.int64)


@dataclass(frozen=True)
class Resamples:
    """Weighted column sums: the data itself and every bootstrap iteration."""

    point: IntArray
    cluster: IntArray
    iid: IntArray
    b: int
    seed: int
    n_units: int
    n_rows: int

    def column(self, index: int) -> tuple[int, FloatArray, FloatArray]:
        """``(point, cluster draws, iid draws)`` for one column."""
        return (
            int(self.point[index]),
            self.cluster[:, index].astype(np.float64),
            self.iid[:, index].astype(np.float64),
        )


def aggregate_units(rows: IntArray, unit_of_row: IntArray, n_units: int) -> IntArray:
    """Sum row columns into ``(units, columns)`` totals."""
    totals = np.zeros((n_units, rows.shape[1]), dtype=np.int64)
    np.add.at(totals, unit_of_row, rows)
    return totals


def _draw_weights(rng: np.random.Generator, iterations: int, n: int) -> IntArray:
    """One index of ``n`` draws with replacement per iteration, as unit counts."""
    index = rng.integers(0, n, size=(iterations, n))
    return np.stack([np.bincount(row, minlength=n) for row in index]).astype(np.int64)


def resample(
    columns: Columns,
    unit_of_row: IntArray,
    n_units: int,
    *,
    b: int = config.B,
    seed: int = config.SEED,
) -> Resamples:
    """Draw ``b`` shared cluster resamples and ``b`` iid resamples from ``seed``."""
    if b < 1:
        raise ValueError("b must be at least 1")
    rows = columns.matrix()
    n_rows, n_cols = rows.shape
    if unit_of_row.shape != (n_rows,):
        raise ValueError("unit_of_row must have one entry per row")
    point = rows.sum(axis=0, dtype=np.int64)
    cluster = np.zeros((b, n_cols), dtype=np.int64)
    iid = np.zeros((b, n_cols), dtype=np.int64)
    if n_rows == 0 or n_units == 0:
        return Resamples(point, cluster, iid, b, seed, n_units, n_rows)
    units = aggregate_units(rows, unit_of_row, n_units)
    rng = np.random.default_rng(seed)
    for start in range(0, b, CHUNK_ITERATIONS):
        stop = min(start + CHUNK_ITERATIONS, b)
        cluster[start:stop] = _draw_weights(rng, stop - start, n_units) @ units
        iid[start:stop] = _draw_weights(rng, stop - start, n_rows) @ rows
    return Resamples(point, cluster, iid, b, seed, n_units, n_rows)


def ratio(num: FloatArray, den: FloatArray) -> FloatArray:
    """Element-wise ``num / den``; ``NaN`` where the denominator is zero."""
    out = np.full(num.shape, np.nan, dtype=np.float64)
    np.divide(num, den, out=out, where=den != 0)
    return out


def ratio_point(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def percentile_ci(draws: FloatArray, level: float = config.CI_LEVEL) -> tuple[float, float] | None:
    """Percentile interval over the defined draws; ``None`` when none is defined."""
    finite = draws[np.isfinite(draws)]
    if finite.size == 0:
        return None
    tail = 100.0 * (1.0 - level) / 2.0
    lo, hi = np.percentile(finite, [tail, 100.0 - tail])
    return float(lo), float(hi)


def width(ci: tuple[float, float]) -> float:
    return ci[1] - ci[0]


def design_effect(cluster_ci: tuple[float, float], iid_ci: tuple[float, float]) -> float | None:
    """``(cluster width / iid width)^2``; ``None`` (degenerate) when the iid width is 0."""
    iid_width = width(iid_ci)
    if iid_width == 0.0:
        return None
    return (width(cluster_ci) / iid_width) ** 2


__all__ = [
    "CHUNK_ITERATIONS",
    "BoolArray",
    "Columns",
    "FloatArray",
    "IntArray",
    "Resamples",
    "aggregate_units",
    "design_effect",
    "percentile_ci",
    "ratio",
    "ratio_point",
    "resample",
    "width",
]
