"""Google Maps reviews adapter: ``apify /compass/google-maps-reviews-scraper``.

Input (design Appendix §Endpoint reference): ``startUrls`` built from a Google
Maps search URL for the brand name, ``maxReviews`` always set from
``config.SOURCE_PLAN`` (the actor default is ten million), ``reviewsSort``
``newest`` and ``reviewsStartDate`` at the start of the query window.

Input-path caveat (review 2026-09-02 adapters-b, F7): the endpoint reference
lists ``startUrls[]`` and ``placeIds[]`` without saying which URL shapes the
actor accepts. A ``/maps/search/<name>`` URL is a results listing, not a
resolved place page, and the actor is documented upstream as a reviews
scraper rather than a place-discovery crawler. Whether it accepts a search
URL is UNVERIFIED until the W3.7 live smoke run records a real payload; the
search URL stays the default so the demo can run without a manual place
lookup. ``build_input(..., place_id=...)`` is the fallback path: it emits
``placeIds`` instead of ``startUrls`` so the recorder can retry with a
resolved Google place id if the search URL returns nothing.

Output items carry ``reviewId``, ``text``, ``stars``, ``publishedAtDate``,
``likesCount``, ``name``, ``title`` (the place name) and a few more. Four keys
are required and their absence is schema drift (``AdapterSchemaError``); every
other key is optional and a missing or ``null`` value never raises.

Review-source rule for ``matched_terms``: a review sits on the brand's own
place page, so the brand name is often absent from the review text. Terms are
matched in ``text`` first and, when nothing matches there, in the place
``title``. An item matching neither is dropped. Rating-only reviews
(``text`` null) are skipped: a Mention needs text.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from urllib.parse import quote

from sonar.config import SOURCE_PLAN, SourcePlan
from sonar.models import Lang, Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize_url

SOURCE: Final = "google_maps"
PLAN: SourcePlan = SOURCE_PLAN[SOURCE]
PROVIDER_ID = PLAN.provider
ENDPOINT = PLAN.endpoint

SEARCH_URL = "https://www.google.com/maps/search/"
REVIEWS_SORT = "newest"
REQUIRED_KEYS: tuple[str, ...] = ("reviewId", "text", "stars", "publishedAtDate")
_ITEM_LIST_KEYS: tuple[str, ...] = ("output", "results", "items", "data")
_LANGS: frozenset[str] = frozenset({"pt", "en", "other", "unknown"})


def _drift(detail: str) -> AdapterSchemaError:
    return AdapterSchemaError(PROVIDER_ID, ENDPOINT, detail)


def _items(raw: Any) -> list[Any]:
    """Locate the item list in a Monid run body or a bare Apify dataset list."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in _ITEM_LIST_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for inner_key in _ITEM_LIST_KEYS[1:]:
                    inner = value.get(inner_key)
                    if isinstance(inner, list):
                        return inner
        provider = raw.get("providerResponse")
        if isinstance(provider, dict):
            for key in ("body", *_ITEM_LIST_KEYS):
                value = provider.get(key)
                if isinstance(value, list):
                    return value
    raise _drift("no item list found in payload (expected a list or one under output/items)")


def _timestamp(value: Any, index: int) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _drift(f"item {index}: publishedAtDate is not a string ({type(value).__name__})")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise _drift(f"item {index}: publishedAtDate {value!r} is not ISO 8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0)


def _rating(value: Any, index: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
        raise _drift(f"item {index}: stars is not an integer ({value!r})")
    stars = int(value)
    if not 1 <= stars <= 5:
        raise _drift(f"item {index}: stars {stars} outside 1-5")
    return stars


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _author(item: dict[str, Any]) -> str | None:
    for key in ("reviewerId", "name"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _lang(text: str) -> Lang:
    detected = detect_lang(text)
    return cast(Lang, detected if detected in _LANGS else "unknown")


class GoogleMapsProvider:
    """Adapter for ``apify /compass/google-maps-reviews-scraper``."""

    @property
    def source(self) -> str:
        return SOURCE

    @property
    def endpoint(self) -> str:
        return ENDPOINT

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def build_input(
        self,
        query: Any,
        *,
        brand: str | None = None,
        now: datetime | None = None,
        place_id: str | None = None,
    ) -> dict[str, Any]:
        """Actor input for one brand (the Query brand unless *brand* names a competitor).

        Default path: ``startUrls`` with a Maps search URL for the brand name
        (acceptance unverified, see the module docstring). When *place_id* is
        given the input carries ``placeIds`` instead and the brand name is not
        used, so the recorder can retry with a resolved place id.
        """
        name = query.brand if brand is None else brand
        cap = PLAN.caps[query.profile]
        if cap == 0:
            raise ValueError(f"{SOURCE} is not fetched under profile {query.profile}")
        start = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(days=query.window_days)
        target: dict[str, Any]
        if place_id is None:
            target = {"startUrls": [{"url": SEARCH_URL + quote(name, safe="")}]}
        else:
            if not place_id.strip():
                raise ValueError("place_id must be a non-empty Google place id when given")
            target = {"placeIds": [place_id.strip()]}
        return {
            **target,
            "maxReviews": cap,
            "reviewsSort": REVIEWS_SORT,
            "reviewsStartDate": start.date().isoformat(),
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
        """Turn the run body into Mention rows for *brand*.

        *run_id* is the Monid run id; Apify runs always carry one, but the
        :class:`~sonar.providers.base.Provider` protocol allows ``None`` for
        sync endpoints, so it is passed through to ``Mention.run_id`` as-is. *local_seq*
        is the ledger row that saved *raw* (``raw_ref`` = ``"{local_seq}#{index}"``)
        and is keyword-only with a ``None`` default so the signature stays
        compatible with :class:`~sonar.providers.base.Provider`; omitting it is
        a caller error, never a silent reference. *terms* are the brand and
        alias terms to match, defaulting to the brand alone.
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("parse() needs the ledger local_seq (>= 1) to build raw_ref")
        search_terms: Sequence[str] = terms if terms else (brand,)
        mentions: list[Mention] = []
        for index, item in enumerate(_items(raw)):
            if not isinstance(item, dict):
                raise _drift(f"item {index}: not an object ({type(item).__name__})")
            missing = [key for key in REQUIRED_KEYS if key not in item]
            if missing:
                raise _drift(f"item {index}: missing required keys {missing}")
            native_id = item["reviewId"]
            if not isinstance(native_id, str) or not native_id.strip():
                raise _drift(f"item {index}: reviewId is not a non-empty string")
            text = item["text"]
            if text is None:
                continue
            if not isinstance(text, str):
                raise _drift(f"item {index}: text is not a string ({type(text).__name__})")
            if not text.strip():
                continue
            matched = match_terms(text, search_terms)
            if not matched:
                title = item.get("title")
                if isinstance(title, str):
                    matched = match_terms(title, search_terms)
            if not matched:
                continue
            review_url = item.get("reviewUrl")
            url = normalize_url(review_url) if isinstance(review_url, str) and review_url else None
            handle = _author(item)
            mention_id = mention_id_for(SOURCE, native_id)
            engagement: dict[str, int] = {}
            likes = _count(item.get("likesCount"))
            if likes is not None:
                engagement["likes"] = likes
            mentions.append(
                Mention(
                    mention_id=mention_id,
                    brand=brand,
                    source=SOURCE,
                    run_id=run_id,
                    native_id=native_id,
                    url=url,
                    author_hash=author_hash_for(SOURCE, handle) if handle else None,
                    text=text,
                    lang=_lang(text),
                    published_at=_timestamp(item["publishedAtDate"], index),
                    engagement=engagement,
                    rating=_rating(item["stars"], index),
                    cluster_key=mention_id,
                    matched_terms=matched,
                    raw_ref=f"{local_seq}#{index}",
                )
            )
        return mentions

    def unit_cost(self, n_results: int) -> float:
        return n_results * PLAN.per_result_usd + PLAN.per_call_usd

    def cluster_key(self, item: Any) -> str:
        """CONTRACTS §cluster_key: review sources cluster on ``mention_id``."""
        return str(item.mention_id)


PROVIDER = GoogleMapsProvider()
PROVIDERS[SOURCE] = PROVIDER

__all__ = ["ENDPOINT", "PROVIDER", "REQUIRED_KEYS", "SOURCE", "GoogleMapsProvider"]
