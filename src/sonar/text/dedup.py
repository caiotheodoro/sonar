"""Dedup by native_id → normalised url → text_key, returning kept and dropped."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sonar.text.normalize import normalize_url, text_key

DedupReason = Literal["dedup_native_id", "dedup_url", "dedup_text"]
"""Coded drop reason; each value is a `Receipt.mentions.excluded_with_reason` key."""

DEDUP_REASONS: tuple[DedupReason, ...] = ("dedup_native_id", "dedup_url", "dedup_text")
"""Every `DedupReason` value, in precedence order (CONTRACTS §Dedup precedence)."""


@dataclass(frozen=True)
class DedupItem:
    """Minimal item for dedup; adapters project Mention-like records into this."""

    source: str
    native_id: str | None
    url: str | None
    text: str
    raw_ref: str
    brand: str


Dropped = tuple[DedupItem, DedupReason, str]
"""A dropped item, the coded rule that dropped it, and the winner's `raw_ref`."""


@dataclass(frozen=True)
class DedupResult:
    """Return value of dedup: kept items and dropped items with coded reasons."""

    kept: list[DedupItem]
    dropped: list[Dropped]


def _sort_key(item: DedupItem) -> tuple[int, int]:
    """Lower local_seq then lower item index wins."""
    seq_str, idx_str = item.raw_ref.split("#")
    return int(seq_str), int(idx_str)


def dedup(items: Sequence[DedupItem]) -> DedupResult:
    """Dedup within each `(source, brand)` group following the precedence rules.

    1. (source, native_id) – two items with same source and non-null native_id are one
    2. normalised url – among native_id=null survivors, equal URLs are one
    3. text_key – among native_id=null and url=null survivors, equal text_key is one

    Dedup never merges across sources, and never across brands: a mention
    matching the brand and a competitor is kept once per brand
    (CONTRACTS §Dedup precedence). Within a group the first item by
    `raw_ref` order (lower local_seq, then lower item index) wins.
    """
    kept: list[DedupItem] = []
    dropped: list[Dropped] = []

    by_group: dict[tuple[str, str], list[DedupItem]] = {}
    for item in items:
        by_group.setdefault((item.source, item.brand), []).append(item)

    for group_items in by_group.values():
        sorted_items = sorted(group_items, key=_sort_key)
        _dedup_group(sorted_items, kept, dropped)

    return DedupResult(kept=kept, dropped=dropped)


def _dedup_group(
    items: list[DedupItem],
    kept: list[DedupItem],
    dropped: list[Dropped],
) -> None:
    """Dedup a list of items that share one `(source, brand)`."""
    seen_native: dict[str, DedupItem] = {}
    seen_url: dict[str, DedupItem] = {}
    seen_text: dict[str, DedupItem] = {}

    for item in items:
        # Rule 1: native_id
        if item.native_id is not None:
            if item.native_id in seen_native:
                dropped.append((item, "dedup_native_id", seen_native[item.native_id].raw_ref))
                continue
            seen_native[item.native_id] = item
            kept.append(item)
            continue

        # Rule 2: normalised url
        if item.url is not None:
            norm_url = normalize_url(item.url)
            if norm_url in seen_url:
                dropped.append((item, "dedup_url", seen_url[norm_url].raw_ref))
                continue
            seen_url[norm_url] = item
            kept.append(item)
            continue

        # Rule 3: text_key
        tk = text_key(item.text)
        if tk in seen_text:
            dropped.append((item, "dedup_text", seen_text[tk].raw_ref))
            continue
        seen_text[tk] = item
        kept.append(item)
