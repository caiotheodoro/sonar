"""Average-linkage agglomerative clustering on cosine distance, in numpy, deterministic.

Given unit vectors, the pairwise cosine distance is ``1 - dot``. Clusters start
as singletons and the two clusters with the smallest average inter-cluster
distance merge (Lance-Williams update for average linkage) until that
smallest distance exceeds the cut. Ties are broken by the lowest row index
pair, so the same matrix always yields the same clusters; callers order rows by
``mention_id`` before calling.

Medoids are the members closest to the cluster centroid (mean of the unit
vectors), ties by row index, closest first.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from sonar.topics.embed import unit_rows


def cosine_distances(vectors: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Symmetric ``(n, n)`` cosine-distance matrix in ``[0, 2]`` with a zero diagonal."""
    unit = unit_rows(vectors)
    distances: npt.NDArray[np.float64] = 1.0 - unit @ unit.T
    np.clip(distances, 0.0, 2.0, out=distances)
    np.fill_diagonal(distances, 0.0)
    return distances


def average_linkage(distances: npt.NDArray[np.float64], threshold: float) -> list[list[int]]:
    """Flat clusters after merging every pair whose average-linkage distance is ``<= threshold``.

    Returns member index lists, each sorted ascending, ordered by descending
    size then by smallest member index. A ``(0, 0)`` matrix yields ``[]``.
    """
    matrix = np.asarray(distances, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError(f"distances must be square, got shape {matrix.shape}")
    n = int(matrix.shape[0])
    if n == 0:
        return []
    work = matrix.copy()
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    sizes = np.ones(n, dtype=np.float64)
    active: list[int] = list(range(n))
    while len(active) > 1:
        rows = np.array(active)
        sub = work[np.ix_(rows, rows)]
        upper = np.triu_indices(len(active), k=1)
        values = sub[upper]
        best = int(np.argmin(values))
        if values[best] > threshold:
            break
        i = active[int(upper[0][best])]
        j = active[int(upper[1][best])]
        weight_i = sizes[i]
        weight_j = sizes[j]
        for k in active:
            if k in (i, j):
                continue
            merged = (weight_i * work[i, k] + weight_j * work[j, k]) / (weight_i + weight_j)
            work[i, k] = merged
            work[k, i] = merged
        sizes[i] = weight_i + weight_j
        members[i].extend(members.pop(j))
        active.remove(j)
    clusters = [sorted(group) for group in members.values()]
    clusters.sort(key=lambda group: (-len(group), group[0]))
    return clusters


def medoid_indices(
    vectors: npt.NDArray[np.float64], members: Sequence[int], count: int
) -> list[int]:
    """The ``count`` members nearest the centroid of ``members``, nearest first, ties by index."""
    if count < 1:
        raise ValueError("count must be at least 1")
    if len(members) < count:
        raise ValueError(f"cluster of {len(members)} cannot supply {count} medoids")
    unit = unit_rows(vectors)
    rows = np.asarray(list(members), dtype=np.int64)
    centroid = unit[rows].mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm > 0.0:
        centroid = centroid / norm
    distance = 1.0 - unit[rows] @ centroid
    order = sorted(range(len(members)), key=lambda p: (float(distance[p]), int(rows[p])))
    return [int(rows[p]) for p in order[:count]]


__all__ = ["average_linkage", "cosine_distances", "medoid_indices"]
