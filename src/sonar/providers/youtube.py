"""YouTube video adapter: Apify ``streamers/youtube-scraper`` through Monid.

Endpoint reference (design appendix, verified 2026-09-02):

* input ``searchQueries[]``, ``maxResults``, ``dateFilter``, ``sortingOrder``;
* output items ``id, title, url, viewCount, date, likes, channelName,
  commentsCount, text``;
* price 0.0045 USD per result (``config.SOURCE_PLAN["youtube"]``).

``maxResults`` is always set from the profile cap because the actor treats
``0`` as unlimited (Pipeline rules: "Always set ``maxResults`` (YouTube)").

Each video becomes one :class:`~sonar.models.Mention` with ``native_id`` the
video id, ``cluster_key = mention_id`` (CONTRACTS §cluster_key rules for
``youtube`` videos, enforced by the model validator) and ``text`` the title
and description joined by ``"\\n\\n"`` (CONTRACTS §Mention.text for
post-shaped items; the description alone when the title is empty).

The helpers ``items_of``, ``require``, ``optional_str``, ``optional_int``,
``parse_datetime`` and ``engagement_of`` are shared with
:mod:`sonar.providers.youtube_comments`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sonar.config import SOURCE_PLAN, SourcePlan
from sonar.models import Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterEmpty, AdapterSchemaError, first_error_text, is_error_item
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize_url

PLAN: SourcePlan = SOURCE_PLAN["youtube"]
DATE_FILTER = "month"
SORTING_ORDER = "date"
VIDEO_URL = "https://www.youtube.com/watch?v={video_id}"

# --------------------------------------------------------------------------- helpers


def items_of(raw: Any, provider: str, endpoint: str) -> list[dict[str, Any]]:
    """Return the item list of an Apify dataset payload.

    Accepts the bare item array or an object wrapping it under ``items``,
    ``data`` or ``results`` (Monid wraps ``providerResponse`` bodies; the
    exact wrapper is pinned by the recorded fixtures of W3.7). Anything else
    is a schema drift.
    """
    items: Any = raw
    if isinstance(raw, dict):
        for key in ("items", "data", "results"):
            if key in raw:
                items = raw[key]
                break
        else:
            raise AdapterSchemaError(
                provider, endpoint, "payload object has no items/data/results array"
            )
    if not isinstance(items, list):
        raise AdapterSchemaError(provider, endpoint, f"items is {type(items).__name__}, not list")
    out: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AdapterSchemaError(
                provider, endpoint, f"item {index} is {type(item).__name__}, not object"
            )
        out.append(item)
    return out


def require(item: dict[str, Any], field: str, index: int, provider: str, endpoint: str) -> str:
    """Return a required non-empty string field or raise :class:`AdapterSchemaError`."""
    value = item.get(field)
    if value is None:
        raise AdapterSchemaError(provider, endpoint, f"item {index} lacks required field {field!r}")
    if not isinstance(value, str) or not value.strip():
        raise AdapterSchemaError(
            provider, endpoint, f"item {index} field {field!r} must be a non-empty string"
        )
    return value


def optional_str(item: dict[str, Any], field: str) -> str | None:
    """Return a string field, or ``None`` when absent, null, blank or not a string."""
    value = item.get(field)
    if isinstance(value, str) and value.strip():
        return value
    return None


def optional_int(item: dict[str, Any], field: str) -> int | None:
    """Return an integer field, tolerating numeric strings; ``None`` when unusable."""
    value = item.get(field)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        digits = value.strip().replace(",", "")
        if digits.isdigit():
            return int(digits)
    return None


def parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp to an aware UTC datetime; ``None`` when unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def engagement_of(item: dict[str, Any], mapping: Sequence[tuple[str, str]]) -> dict[str, int]:
    """Map payload counters to CONTRACTS engagement keys, omitting absent ones."""
    out: dict[str, int] = {}
    for field, key in mapping:
        value = optional_int(item, field)
        if value is not None and value >= 0:
            out[key] = value
    return out


def search_terms(query: Any, brand: str | None = None) -> list[str]:
    """Brand plus aliases from the Query; a competitor gets only its own name."""
    if brand is not None and brand != query.brand:
        return [brand]
    return [query.brand, *query.brand_aliases]


# --------------------------------------------------------------------------- adapter


class YouTubeProvider:
    """Apify ``streamers/youtube-scraper`` adapter (source ``youtube``)."""

    _ENGAGEMENT: tuple[tuple[str, str], ...] = (
        ("viewCount", "views"),
        ("likes", "likes"),
        ("commentsCount", "comments"),
    )

    @property
    def source(self) -> str:
        return PLAN.source

    @property
    def provider(self) -> str:
        return PLAN.provider

    @property
    def endpoint(self) -> str:
        return PLAN.endpoint

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def build_input(self, query: Any, brand: str | None = None) -> dict[str, Any]:
        """Actor input for ``POST /v1/run`` (passed to Apify unchanged).

        ``searchQueries`` are the brand and its aliases (``brand`` selects a
        competitor, which has no aliases). ``maxResults`` is the profile cap
        and is never ``0``: a profile that does not fetch YouTube raises
        ``ValueError`` before any run exists.
        """
        cap = PLAN.caps[query.profile]
        if cap <= 0:
            raise ValueError(f"youtube is not fetched under profile {query.profile!r}")
        return {
            "searchQueries": search_terms(query, brand),
            "maxResults": cap,
            "dateFilter": DATE_FILTER,
            "sortingOrder": SORTING_ORDER,
        }

    def parse(
        self,
        raw: Any,
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Mention]:
        """Turn the provider response into Mention rows for *brand*.

        ``local_seq`` is the ledger row that saved *raw* (``raw_ref`` is
        ``"{local_seq}#{index}"``); it is required and must be ``>= 1``,
        ``ValueError`` otherwise, before any item is read. ``terms`` are the
        brand terms to match (default: the brand alone); items without a
        match are not emitted (CONTRACTS §Mention.matched_terms).
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("local_seq (ledger row of the raw payload) is required, >= 1")
        source = PLAN.source
        match_on = list(terms) if terms else [brand]
        mentions: list[Mention] = []
        all_items = items_of(raw, self.provider, self.endpoint)
        if all_items and all(is_error_item(it) for it in all_items):
            raise AdapterEmpty(
                self.provider,
                self.endpoint,
                f"{len(all_items)} item(s), all provider errors: {first_error_text(all_items)}",
            )
        for index, item in enumerate(all_items):
            if is_error_item(item):
                continue
            video_id = require(item, "id", index, self.provider, self.endpoint)
            title = optional_str(item, "title")
            description = optional_str(item, "text")
            if title is None and description is None:
                raise AdapterSchemaError(
                    self.provider, self.endpoint, f"item {index} has neither title nor text"
                )
            parts = [p for p in (title, description) if p is not None]
            text = "\n\n".join(parts)
            matched = match_terms(text, match_on)
            if not matched:
                continue
            url = optional_str(item, "url") or VIDEO_URL.format(video_id=video_id)
            channel = optional_str(item, "channelName")
            mention_id = mention_id_for(source, video_id)
            record: dict[str, Any] = {
                "mention_id": mention_id,
                "brand": brand,
                "source": source,
                "run_id": run_id,
                "native_id": video_id,
                "url": normalize_url(url),
                "author_hash": author_hash_for(source, channel) if channel else None,
                "text": text,
                "lang": detect_lang(text),
                "published_at": parse_datetime(item.get("date")),
                "engagement": engagement_of(item, self._ENGAGEMENT),
                "rating": None,
                "cluster_key": mention_id,
                "matched_terms": matched,
                "raw_ref": f"{local_seq}#{index}",
            }
            mentions.append(Mention.model_validate(record))
        return mentions

    def unit_cost(self, n_results: int) -> float:
        """Estimated USD for *n_results* billed results plus the per-call price."""
        return PLAN.per_call_usd + n_results * PLAN.per_result_usd

    def cluster_key(self, item: Mention) -> str:
        """CONTRACTS §cluster_key rules: a video is its own cluster."""
        return item.mention_id


PROVIDER = YouTubeProvider()
PROVIDERS[PROVIDER.source] = PROVIDER

__all__ = [
    "PLAN",
    "PROVIDER",
    "YouTubeProvider",
    "engagement_of",
    "items_of",
    "optional_int",
    "optional_str",
    "parse_datetime",
    "require",
    "search_terms",
]
