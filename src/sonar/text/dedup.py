"""Dedup by native_id → normalised url → text_key, returning kept and dropped."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sonar.text.normalize import normalize_url, text_key


@dataclass(frozen=True)
class DedupItem:
    """Minimal item for dedup; adapters project Mention-like records into this."""

    source: str
    native_id: str | None
    url: str | None
    text: str
    raw_ref: str
    brand: str


@dataclass(frozen=True)
class DedupResult:
    """Return value of dedup: kept items and dropped items with reasons."""

    kept: list[DedupItem]
    dropped: list[tuple[DedupItem, str]]


def _sort_key(item: DedupItem) -> tuple[int, int]:
    """Lower local_seq then lower item index wins."""
    seq_str, idx_str = item.raw_ref.split("#")
    return int(seq_str), int(idx_str)


def dedup(items: Sequence[DedupItem]) -> DedupResult:
    """Dedup within a single source following the precedence rules.

    1. (source, native_id) – two items with same source and non-null native_id are one
    2. normalised url – among native_id=null survivors, equal URLs are one
    3. text_key – among native_id=null and url=null survivors, equal text_key is one

    Returns the first item by raw_ref order as the winner.
    """
    kept: list[DedupItem] = []
    dropped: list[tuple[DedupItem, str]] = []

    # Group by source first (dedup never merges across sources)
    by_source: dict[str, list[DedupItem]] = {}
    for item in items:
        by_source.setdefault(item.source, []).append(item)

    for source_items in by_source.values():
        sorted_items = sorted(source_items, key=_sort_key)
        _dedup_group(sorted_items, kept, dropped)

    return DedupResult(kept=kept, dropped=dropped)


def _dedup_group(
    items: list[DedupItem],
    kept: list[DedupItem],
    dropped: list[tuple[DedupItem, str]],
) -> None:
    """Dedup a list of items from the same source."""
    seen_native: dict[str, DedupItem] = {}
    seen_url: dict[str, DedupItem] = {}
    seen_text: dict[str, DedupItem] = {}

    for item in items:
        # Rule 1: native_id
        if item.native_id is not None:
            key = f"native:{item.source}:{item.native_id}"
            if key in seen_native:
                dropped.append((item, f"duplicate native_id of {seen_native[key].raw_ref}"))
                continue
            seen_native[key] = item
            kept.append(item)
            continue

        # Rule 2: normalised url
        if item.url is not None:
            norm_url = normalize_url(item.url)
            url_key = f"url:{item.source}:{norm_url}"
            if url_key in seen_url:
                dropped.append((item, f"duplicate url of {seen_url[url_key].raw_ref}"))
                continue
            seen_url[url_key] = item
            kept.append(item)
            continue

        # Rule 3: text_key
        tk = text_key(item.text)
        text_key_val = f"text:{item.source}:{tk}"
        if text_key_val in seen_text:
            dropped.append((item, f"duplicate text_key of {seen_text[text_key_val].raw_ref}"))
            continue
        seen_text[text_key_val] = item
        kept.append(item)
