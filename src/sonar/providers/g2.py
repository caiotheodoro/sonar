"""G2 adapter — two-call pattern: search_software → get_product_reviews.

Each call is its own Monid run.  The adapter resolves the brand to a
G2 product slug via ``/search_software``, then fetches one page of
reviews via ``/get_product_reviews``.  When the search returns no
results the adapter abstains cleanly (empty reviews list).

Review-object field names are an assumption.  ``docs/monid/inspect/
g2_get_product_reviews.json`` documents only the input ``queryParams``
(``slug``, ``page``, ``star_rating``); CONTRACTS OQ-5 (native id, rating,
timestamp and author field names) stays open until W3.7 records a live
payload.  ``parse`` reads each field through a small list of named
fallbacks so the first recorded fixture is a schema finding, not a crash;
W3.7 is the resolver.  G2's schema exposes no ``sort`` parameter, so the
reviews call carries none.

Review-source rule for ``matched_terms``: the reviews call is scoped to the
resolved product slug, so every review on the page is about the brand even
when the text never names it.  Terms are matched in the review text first;
when nothing matches, the normalised brand term is used.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Final, cast

from sonar.config import SOURCE_PLAN, SourcePlan
from sonar.models import Lang, Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize, normalize_url

SOURCE: Final = "g2"
PLAN: SourcePlan = SOURCE_PLAN[SOURCE]
SEARCH_ENDPOINT = "/search_software"
REVIEWS_ENDPOINT = PLAN.endpoint
SEARCH_USD_PER_CALL = 0.02
"""``/search_software`` lookup price (design D011); not a ``SOURCE_PLAN`` field."""

# Named fallbacks per field (CONTRACTS OQ-5; resolved by the W3.7 recorded fixture).
ID_KEYS: tuple[str, ...] = ("reviewId", "id")
TITLE_KEYS: tuple[str, ...] = ("title",)
TEXT_KEYS: tuple[str, ...] = ("content", "text", "body")
RATING_KEYS: tuple[str, ...] = ("rating", "starRating", "stars")
DATE_KEYS: tuple[str, ...] = ("date", "publishedAt", "createdAt")
AUTHOR_OBJECT_KEYS: tuple[str, ...] = ("author", "reviewer")
AUTHOR_NAME_KEYS: tuple[str, ...] = ("id", "name", "displayName")
URL_KEYS: tuple[str, ...] = ("url", "reviewUrl")
_LANGS: frozenset[str] = frozenset({"pt", "en", "other", "unknown"})


def _author_hash(handle: str) -> str:
    """First 16 hex of sha256 over ``g2\\n{handle}`` (CONTRACTS §Mention.author_hash)."""
    return author_hash_for(SOURCE, handle)


def _mention_id(review_id: str) -> str:
    """CONTRACTS §mention_id rule: sha256 over ``g2\\n{review_id}``, first 24 hex."""
    return mention_id_for(SOURCE, review_id)


def _drift(detail: str) -> AdapterSchemaError:
    return AdapterSchemaError(SOURCE, REVIEWS_ENDPOINT, detail)


def _first(item: dict[str, Any], keys: Sequence[str]) -> Any:
    """First non-``None`` value among *keys*, else ``None``."""
    for key in keys:
        value = item.get(key)
        if value is not None:
            return value
    return None


def _first_str(item: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _timestamp(value: Any, index: int) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _drift(f"item {index}: date is not a string ({type(value).__name__})")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _drift(f"item {index}: date {value!r} is not ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def _rating(value: Any, index: int) -> int | None:
    """Coerce a star value to ``int`` in 1-5; ``None`` passes through, anything else is drift."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise _drift(f"item {index}: rating is a boolean ({value!r})")
    if isinstance(value, str):
        if not value.strip().isdigit():
            raise _drift(f"item {index}: rating is not an integer ({value!r})")
        value = int(value.strip())
    if not isinstance(value, (int, float)) or value != int(value):
        raise _drift(f"item {index}: rating is not an integer ({value!r})")
    stars = int(value)
    if not 1 <= stars <= 5:
        raise _drift(f"item {index}: rating {stars} outside 1-5")
    return stars


def _author(item: dict[str, Any]) -> str | None:
    """Reviewer handle to hash; never returned raw to the caller."""
    for key in AUTHOR_OBJECT_KEYS:
        obj = item.get(key)
        if isinstance(obj, dict):
            handle = _first_str(obj, AUTHOR_NAME_KEYS)
            if handle:
                return handle
    return _first_str(item, ("authorName",))


def _url(item: dict[str, Any]) -> str | None:
    candidate = _first_str(item, URL_KEYS)
    return normalize_url(candidate) if candidate else None


def _lang(text: str) -> Lang:
    detected = detect_lang(text)
    return cast(Lang, detected if detected in _LANGS else "unknown")


class G2Provider:
    """G2 adapter implementing the Provider protocol."""

    def __init__(self) -> None:
        self._slug: str | None = None

    @property
    def source(self) -> str:
        return SOURCE

    @property
    def endpoint(self) -> str:
        return REVIEWS_ENDPOINT

    def build_input(self, query: Any) -> dict[str, Any]:
        """Build the ``input`` payload for ``POST /v1/run``.

        First call (search): returns ``queryParams`` for ``/search_software``.
        Second call (reviews): returns ``queryParams`` for ``/get_product_reviews``
        using the cached slug from the search.
        """
        brand: str = getattr(query, "brand", str(query))
        if self._slug is not None:
            return {
                "queryParams": {
                    "slug": self._slug,
                    "page": 1,
                },
            }
        return {
            "queryParams": {
                "query": brand,
            },
        }

    def parse_search(self, raw: dict[str, Any]) -> str | None:
        """Parse a ``/search_software`` response and return the slug, or ``None``."""
        products = raw.get("products")
        if products is None:
            return None
        if not isinstance(products, list):
            raise AdapterSchemaError(SOURCE, SEARCH_ENDPOINT, "'products' must be a list")
        if len(products) == 0:
            return None
        first = products[0]
        if not isinstance(first, dict):
            raise AdapterSchemaError(
                SOURCE, SEARCH_ENDPOINT, "expected list of dicts under 'products'"
            )
        slug = first.get("slug")
        if not isinstance(slug, str) or not slug:
            raise AdapterSchemaError(
                SOURCE, SEARCH_ENDPOINT, "first product missing non-empty 'slug' field"
            )
        self._slug = slug
        return slug

    def parse(
        self,
        raw: dict[str, Any],
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Mention]:
        """Turn a ``/get_product_reviews`` body into Mention rows for *brand*.

        *local_seq* is the ledger row that saved *raw* (``raw_ref`` =
        ``"{local_seq}#{index}"``); omitting it is a caller error.  *terms* are
        the brand and alias terms to match, defaulting to the brand alone.
        Raises ``AdapterSchemaError`` on unexpected payload shape.
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("parse() needs the ledger local_seq (>= 1) to build raw_ref")
        reviews = raw.get("reviews")
        if not isinstance(reviews, list):
            raise _drift("expected 'reviews' key containing a list")
        search_terms: Sequence[str] = terms if terms else (brand,)
        mentions: list[Mention] = []
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                raise _drift(f"item {index}: not an object ({type(review).__name__})")
            native_id = _first(review, ID_KEYS)
            if not isinstance(native_id, str) or not native_id.strip():
                raise _drift(f"item {index}: review id ({ID_KEYS}) is not a non-empty string")
            text_parts = [
                part
                for part in (_first_str(review, TITLE_KEYS), _first_str(review, TEXT_KEYS))
                if part
            ]
            if not text_parts:
                continue
            text = "\n\n".join(text_parts)
            matched = match_terms(text, search_terms) or [normalize(brand)]
            handle = _author(review)
            mention_id = _mention_id(native_id)
            mentions.append(
                Mention(
                    mention_id=mention_id,
                    brand=brand,
                    source=SOURCE,
                    run_id=run_id,
                    native_id=native_id,
                    url=_url(review),
                    author_hash=_author_hash(handle) if handle else None,
                    text=text,
                    lang=_lang(text),
                    published_at=_timestamp(_first(review, DATE_KEYS), index),
                    engagement={},
                    rating=_rating(_first(review, RATING_KEYS), index),
                    cluster_key=mention_id,
                    matched_terms=matched,
                    raw_ref=f"{local_seq}#{index}",
                )
            )
        return mentions

    def unit_cost(self, n_results: int) -> float:
        """Per-call cost for ``/get_product_reviews`` (``SOURCE_PLAN``)."""
        return PLAN.per_call_usd

    def search_unit_cost(self) -> float:
        """Per-call cost for ``/search_software``."""
        return SEARCH_USD_PER_CALL

    def cluster_key(self, item: Any) -> str:
        """CONTRACTS §cluster_key: review sources cluster on ``mention_id``."""
        return str(item.mention_id)

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None


PROVIDER = G2Provider()
PROVIDERS[SOURCE] = PROVIDER

__all__ = ["PROVIDER", "REVIEWS_ENDPOINT", "SOURCE", "G2Provider"]
