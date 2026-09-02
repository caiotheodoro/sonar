"""Embeddings for topic clustering: fetched through the LLM seam, cached to ``embeddings.npy``.

The cache is one structured numpy array saved with ``np.save`` (no pickle):
a ``key`` column (first 24 hex of sha256 over ``"{model}\\n{text}"``) and a
``vector`` column (float64, one row per key). Keying by model and text means a
mention fetched for two brands, or in two sessions, is embedded once; a
different embedding model never serves a stale vector. Rows are unit-normalised
before use so cosine distance is ``1 - dot``.

``embed_texts`` makes at most one seam call for the keys the cache lacks. If the
cached rows have a different width than the vectors the model returned (a
rewritten cache from another model id with the same name), the cache is
discarded and every text is embedded in one more call.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from sonar.llm.base import LlmBackend, LlmUnparseable, Usage

KEY_HEX = 24
CACHE_FILENAME = "embeddings.npy"
_KEY_FIELD = "key"
_VECTOR_FIELD = "vector"


def embedding_key(model: str, text: str) -> str:
    """Cache key for one (model, text) pair: first 24 hex of sha256 over ``"{model}\\n{text}"``."""
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()[:KEY_HEX]


def unit_rows(vectors: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Rows scaled to unit length; an all-zero row is left as is (its norm is treated as 1)."""
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError(f"expected a 2-d array of vectors, got shape {matrix.shape}")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    out: npt.NDArray[np.float64] = matrix / norms
    return out


@dataclass(frozen=True)
class EmbeddingBatch:
    """Unit vectors for ``keys`` in order, plus what the seam charged for the misses."""

    keys: tuple[str, ...]
    vectors: npt.NDArray[np.float64]
    usages: tuple[Usage, ...]
    cache_hits: int
    cache_misses: int

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1]) if self.vectors.ndim == 2 else 0


class EmbeddingCache:
    """``embeddings.npy`` on disk as a ``key -> vector`` mapping; ``path=None`` caches nothing."""

    def __init__(self, path: Path | None) -> None:
        self.path = path

    def load(self) -> dict[str, npt.NDArray[np.float64]]:
        """Cached vectors, or ``{}`` when the file is absent or not a cache this module wrote."""
        if self.path is None or not self.path.exists():
            return {}
        array = np.load(self.path, allow_pickle=False)
        names = array.dtype.names
        if names != (_KEY_FIELD, _VECTOR_FIELD) or array.ndim != 1:
            return {}
        if array.dtype[_VECTOR_FIELD].ndim != 1:
            return {}
        out: dict[str, npt.NDArray[np.float64]] = {}
        for row in array:
            key = str(row[_KEY_FIELD])
            vector = np.asarray(row[_VECTOR_FIELD], dtype=np.float64)
            out[key] = vector
        return out

    def save(self, entries: dict[str, npt.NDArray[np.float64]]) -> None:
        """Write every entry as one structured array; a no-op when caching is off or empty."""
        if self.path is None or not entries:
            return
        keys = sorted(entries)
        dim = int(entries[keys[0]].shape[0])
        dtype = np.dtype([(_KEY_FIELD, f"U{KEY_HEX}"), (_VECTOR_FIELD, np.float64, (dim,))])
        array = np.empty(len(keys), dtype=dtype)
        for index, key in enumerate(keys):
            vector = entries[key]
            if vector.shape != (dim,):
                raise ValueError(f"cache entry {key} has shape {vector.shape}, expected ({dim},)")
            array[index] = (key, vector)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.path, array, allow_pickle=False)


def _call(
    backend: LlmBackend, texts: Sequence[str], model: str
) -> tuple[list[npt.NDArray[np.float64]], Usage]:
    result = backend.embed(list(texts), model)
    vectors = np.asarray(result.vectors, dtype=np.float64)
    if vectors.ndim != 2 or vectors.shape[0] != len(texts) or vectors.shape[1] == 0:
        raise LlmUnparseable(
            f"embeddings: asked for {len(texts)} vectors, got array of shape {vectors.shape}"
        )
    unit = unit_rows(vectors)
    return [unit[i] for i in range(unit.shape[0])], result.usage


def embed_texts(
    backend: LlmBackend, texts: Sequence[str], model: str, cache: EmbeddingCache
) -> EmbeddingBatch:
    """Unit embeddings for ``texts`` in order, one seam call for the keys the cache lacks.

    Raises whatever the backend raises on failure; the caller turns that into
    an ``embedding_failed`` abstention. ``texts`` may be empty (no call is made).
    """
    keys = [embedding_key(model, text) for text in texts]
    cached = cache.load()
    text_for_key: dict[str, str] = {}
    for key, text in zip(keys, texts, strict=True):
        text_for_key.setdefault(key, text)
    missing = [key for key in text_for_key if key not in cached]
    hits = len(text_for_key) - len(missing)
    usages: list[Usage] = []
    if missing:
        vectors, usage = _call(backend, [text_for_key[key] for key in missing], model)
        usages.append(usage)
        new_dim = vectors[0].shape[0]
        stale = any(vector.shape[0] != new_dim for vector in cached.values())
        if stale:
            all_keys = list(text_for_key)
            vectors, usage = _call(backend, [text_for_key[key] for key in all_keys], model)
            usages.append(usage)
            cached = dict(zip(all_keys, vectors, strict=True))
            hits = 0
            missing = all_keys
        else:
            cached.update(zip(missing, vectors, strict=True))
        cache.save(cached)
    if keys:
        matrix = np.stack([cached[key] for key in keys]).astype(np.float64)
    else:
        matrix = np.zeros((0, 0), dtype=np.float64)
    return EmbeddingBatch(
        keys=tuple(keys),
        vectors=matrix,
        usages=tuple(usages),
        cache_hits=hits,
        cache_misses=len(missing),
    )


__all__ = [
    "CACHE_FILENAME",
    "KEY_HEX",
    "EmbeddingBatch",
    "EmbeddingCache",
    "embed_texts",
    "embedding_key",
    "unit_rows",
]
