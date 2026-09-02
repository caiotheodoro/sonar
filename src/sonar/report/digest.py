"""Build the Digest (CONTRACTS §Digest) and its side files from the analysis outputs.

``build_digest`` joins what ``stats/`` (share of voice, sentiment, by-source,
events, abstentions), ``topics/`` and the labeler produced with the receipt.
It computes nothing statistical: the only derivations here are the
``top_mentions`` ranking (engagement score, then recency, then id; D012 F23),
the topic ordering, the always-present X coverage gap and the ``cost`` quote,
which is copied from the receipt and never recomputed.

``stats_file_for`` is the ``StatsFile`` record for ``stats.json`` and
``write_digest_files`` writes ``digest.json``, ``stats.json`` and
``topics.json`` in one step (D012 F21).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Final

from sonar import config
from sonar.models import (
    Abstention,
    BySourceEntry,
    CostQuote,
    CoverageGap,
    Digest,
    Event,
    Label,
    Mention,
    Narration,
    Query,
    Receipt,
    SentimentEntry,
    SovEntry,
    StatsFile,
    Topic,
    TopMention,
    Window,
)

X_COVERAGE_GAP: Final[CoverageGap] = CoverageGap(
    source="x", reason="unavailable", note="X/Twitter has no Monid endpoint (verified 2026-09-02)"
)
"""Always in ``Digest.coverage_gaps`` (CONTRACTS §Digest)."""

NO_NARRATION: Final[Narration] = Narration(
    text=None, chars=0, numbers_verified=False, mp3_path=None, local_seq=None
)
"""The narration block of a run without voice (``--no-voice``, or the ElevenLabs run failed)."""


def quote_for(text: str) -> str:
    """The verbatim quote of a top mention: the first ``QUOTE_MAX_CHARS`` characters."""
    return text[: config.QUOTE_MAX_CHARS]


def is_relevant(label: Label) -> bool:
    """Relevance for the digest: ``about_brand`` and a sentiment label (not ``irrelevant``).

    A Mention always carries ``matched_terms`` (a row with no match is never emitted),
    so the regex half of the relevance rule holds by construction.
    """
    return label.status in ("ok", "cached") and label.about_brand and label.label != "irrelevant"


def rank_top_mentions(
    mentions: Iterable[Mention],
    labels: Mapping[tuple[str, str], Label],
    *,
    brands: Sequence[str],
    per_brand: int = config.TOP_MENTIONS_PER_BRAND,
) -> list[TopMention]:
    """At most ``per_brand`` relevant rows per brand, grouped in ``brands`` order.

    Within a brand the rows sort by ``engagement_score`` descending, then
    ``published_at`` descending (null last), then ``mention_id`` ascending
    (``TopMention.sort_key``). Brands absent from ``brands`` are not listed.
    """
    candidates: dict[str, list[TopMention]] = {brand: [] for brand in brands}
    for row in mentions:
        bucket = candidates.get(row.brand)
        if bucket is None:
            continue
        label = labels.get((row.mention_id, row.brand))
        if label is None or not is_relevant(label):
            continue
        bucket.append(
            TopMention(
                mention_id=row.mention_id,
                brand=row.brand,
                source=row.source,
                url=row.url,
                quote=quote_for(row.text),
                lang=row.lang,
                label=label.label,
                published_at=row.published_at,
                engagement_score=row.engagement_score,
            )
        )
    out: list[TopMention] = []
    for brand in brands:
        out.extend(sorted(candidates[brand], key=lambda t: t.sort_key)[:per_brand])
    return out


def _merge_abstentions(*groups: Iterable[Abstention]) -> list[Abstention]:
    seen: set[tuple[str, str | None, str | None, str, str]] = set()
    out: list[Abstention] = []
    for group in groups:
        for row in group:
            key = (row.scope, row.brand, row.source, row.reason, row.detail)
            if key not in seen:
                seen.add(key)
                out.append(row)
    return out


def _with_x_gap(gaps: Iterable[CoverageGap]) -> list[CoverageGap]:
    out = list(gaps)
    if not any(g.source == "x" and g.reason == "unavailable" for g in out):
        out.insert(0, X_COVERAGE_GAP)
    return out


def build_digest(
    *,
    query: Query,
    window: Window,
    share_of_voice: Sequence[SovEntry],
    sentiment: Sequence[SentimentEntry],
    by_source: Sequence[BySourceEntry],
    topics: Sequence[Topic],
    events: Sequence[Event],
    mentions: Sequence[Mention],
    labels: Mapping[tuple[str, str], Label],
    abstentions: Sequence[Abstention],
    coverage_gaps: Sequence[CoverageGap],
    receipt: Receipt,
    narration: Narration = NO_NARRATION,
) -> Digest:
    """The analysis output for ``digest.json``.

    ``abstentions`` are the stats layer's rows (one per null estimate); the receipt's
    rows (source- and session-level) are merged in so the digest lists every abstention
    of the session once. ``cost`` is quoted from ``receipt``.
    """
    brands = [query.brand, *query.competitors]
    return Digest(
        brand=query.brand,
        competitors=list(query.competitors),
        window=window,
        share_of_voice=list(share_of_voice),
        sentiment=list(sentiment),
        by_source=list(by_source),
        topics=sorted(topics, key=lambda t: (t.brand, t.topic_id)),
        events=sorted(events, key=lambda e: (e.brand, e.date)),
        top_mentions=rank_top_mentions(mentions, labels, brands=brands),
        abstentions=_merge_abstentions(receipt.abstentions, abstentions),
        coverage_gaps=_with_x_gap(coverage_gaps),
        cost=CostQuote(verdict=receipt.verdict, totals=receipt.totals),
        narration=narration,
    )


def stats_file_for(digest: Digest) -> StatsFile:
    """``stats.json``: the Digest's numbers, field by field (CONTRACTS §StatsFile)."""
    return StatsFile.from_digest(digest)


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def digest_json(digest: Digest) -> str:
    return _dump(digest.model_dump(mode="json"))


def stats_json(digest: Digest) -> str:
    return _dump(stats_file_for(digest).model_dump(mode="json"))


def topics_json(digest: Digest) -> str:
    return _dump([t.model_dump(mode="json") for t in digest.topics])


def write_digest_files(digest: Digest, directory: Path) -> dict[str, Path]:
    """Write ``digest.json``, ``stats.json`` and ``topics.json`` together (D012 F21)."""
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "digest.json": digest_json(digest),
        "stats.json": stats_json(digest),
        "topics.json": topics_json(digest),
    }
    written: dict[str, Path] = {}
    for name, text in files.items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        written[name] = path
    return written


__all__ = [
    "NO_NARRATION",
    "X_COVERAGE_GAP",
    "build_digest",
    "digest_json",
    "is_relevant",
    "quote_for",
    "rank_top_mentions",
    "stats_file_for",
    "stats_json",
    "topics_json",
    "write_digest_files",
]
