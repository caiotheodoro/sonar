"""Retrieval for ``sonar ask``: the top-k relevant mentions of a brand for a question.

Cosine over unit embeddings fetched through the seam and cached in the
session's ``embeddings.npy`` (the topics layer's cache; a mention embedded by
the run or an earlier question is not embedded again). When the seam fails,
retrieval falls back to lexical overlap and says so in ``note`` (design error
matrix: "chat lexical fallback, stated").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sonar import config
from sonar.chat.store import EMBEDDINGS_NPY, SessionStore
from sonar.llm.base import LlmBackend, LlmError, Usage
from sonar.models import Mention
from sonar.text import normalize
from sonar.topics import EmbeddingCache, embed_texts

RetrievalMethod = Literal["cosine", "lexical"]
MIN_TOKEN_CHARS = 3
"""Lexical fallback ignores tokens shorter than this."""


@dataclass(frozen=True)
class Retrieval:
    """The mentions placed in context, how they were ranked, and what the seam charged."""

    mentions: tuple[Mention, ...]
    method: RetrievalMethod
    usage: tuple[Usage, ...]
    note: str | None
    candidates: int

    @property
    def ids(self) -> list[str]:
        return [m.mention_id for m in self.mentions]

    def describe(self) -> str:
        """One line for the terminal: method, pool size, and the fallback reason if any."""
        line = f"retrieval: {self.method} over {self.candidates} relevant mention(s), top {len(self.mentions)}"
        if self.note:
            line += f" ({self.note})"
        return line


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in normalize(text).split() if len(t) >= MIN_TOKEN_CHARS)


def lexical_rank(question: str, mentions: Sequence[Mention], top_k: int) -> list[Mention]:
    """Token overlap with the question, ties by engagement then ``mention_id``."""
    asked = _tokens(question)
    scored = [(len(asked & _tokens(m.text)), m.engagement_score, m) for m in mentions]
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].mention_id))
    return [m for _, _, m in scored[:top_k]]


def cosine_rank(
    question: str,
    mentions: Sequence[Mention],
    top_k: int,
    *,
    backend: LlmBackend,
    model: str,
    cache: EmbeddingCache,
) -> tuple[list[Mention], tuple[Usage, ...]]:
    """Dot product of unit vectors (cosine), ties by ``mention_id``; one seam call at most."""
    batch = embed_texts(backend, [question, *(m.text for m in mentions)], model, cache)
    vectors = batch.vectors
    scores = vectors[1:] @ vectors[0]
    order = sorted(range(len(mentions)), key=lambda i: (-float(scores[i]), mentions[i].mention_id))
    return [mentions[i] for i in order[:top_k]], batch.usages


def retrieve(
    store: SessionStore,
    mentions: Sequence[Mention],
    question: str,
    backend: LlmBackend,
    *,
    model: str | None = None,
    top_k: int = config.CHAT_TOP_K,
) -> Retrieval:
    """Top-``top_k`` of *mentions* for *question*; cosine, else lexical with the reason stated."""
    if not mentions:
        return Retrieval(mentions=(), method="lexical", usage=(), note=None, candidates=0)
    model = model or config.LLM.embedding_model
    cache = EmbeddingCache(store.session_dir / EMBEDDINGS_NPY)
    try:
        ranked, usage = cosine_rank(
            question, mentions, top_k, backend=backend, model=model, cache=cache
        )
    except (LlmError, ValueError, OSError) as exc:
        note = f"lexical fallback, embedding failed: {type(exc).__name__}: {str(exc)[:120]}"
        return Retrieval(
            mentions=tuple(lexical_rank(question, mentions, top_k)),
            method="lexical",
            usage=(),
            note=note,
            candidates=len(mentions),
        )
    return Retrieval(
        mentions=tuple(ranked),
        method="cosine",
        usage=tuple(usage),
        note=None,
        candidates=len(mentions),
    )


__all__ = [
    "MIN_TOKEN_CHARS",
    "Retrieval",
    "RetrievalMethod",
    "cosine_rank",
    "lexical_rank",
    "retrieve",
]
