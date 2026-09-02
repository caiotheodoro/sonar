"""Facebook reviews adapter: ``apify /apify/facebook-reviews-scraper``.

Input (design Appendix §Endpoint reference): ``startUrls`` from the brand's
Facebook page reviews URL derived from the first brand alias (or the brand
name when there is no alias), ``resultsLimit`` from ``config.SOURCE_PLAN`` and
``onlyReviewsNewerThan`` at the start of the query window. An alias that is
already a ``facebook.com`` URL is used as the page URL directly.

Output items carry ``text``, ``date``, ``isRecommended``, ``likesCount``,
``commentsCount``, ``pageName``, ``url``, ``user{id, name}`` and sometimes an
``id``. Three keys are required and their absence is schema drift
(``AdapterSchemaError``); every other key is optional and a missing or
``null`` value never raises.

Facebook reviews carry a recommendation flag, not stars. CONTRACTS OQ-3:
``rating`` is 5 when ``isRecommended`` is true and 1 when false, so the
deterministic rating bucket still applies; ``null`` stays ``null``.

Review-source rule for ``matched_terms`` (``docs/DECISIONS.md`` D014): the
run is scoped to the page the adapter resolved to the brand, so every review
carries ``matched_terms = [normalized brand]`` with ``match_kind = "entity"``
whether or not the text names the brand; the model's ``about_brand`` gate is
still required downstream. Items with ``text`` null are skipped: a Mention
needs text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from urllib.parse import urlparse

from sonar.config import SOURCE_PLAN, SourcePlan
from sonar.models import Lang, Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterEmpty, AdapterSchemaError, first_error_text, is_error_item
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, normalize, normalize_url, text_key

SOURCE: Final = "facebook"
PLAN: SourcePlan = SOURCE_PLAN[SOURCE]
PROVIDER_ID = PLAN.provider
ENDPOINT = PLAN.endpoint

PAGE_URL = "https://www.facebook.com/"
REVIEWS_SUFFIX = "/reviews"
RATING_RECOMMENDED = 5
RATING_NOT_RECOMMENDED = 1
REQUIRED_KEYS: tuple[str, ...] = ("text", "date", "isRecommended")
_ITEM_LIST_KEYS: tuple[str, ...] = ("output", "results", "items", "data")
_LANGS: frozenset[str] = frozenset({"pt", "en", "other", "unknown"})
_SLUG_DROP = re.compile(r"[^a-z0-9.]+")


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


def page_url(alias: str) -> str:
    """Facebook reviews URL for a brand alias or an explicit facebook.com URL."""
    candidate = alias.strip()
    parsed = urlparse(candidate if "://" in candidate else "https://" + candidate)
    if parsed.netloc.lower().endswith("facebook.com"):
        path = parsed.path.rstrip("/").removesuffix(REVIEWS_SUFFIX)
        return PAGE_URL + path.lstrip("/") + REVIEWS_SUFFIX
    slug = _SLUG_DROP.sub("", candidate.casefold()).strip(".")
    if not slug:
        raise ValueError(f"cannot derive a Facebook page slug from {alias!r}")
    return PAGE_URL + slug + REVIEWS_SUFFIX


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
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _drift(f"item {index}: isRecommended is not a boolean ({value!r})")
    return RATING_RECOMMENDED if value else RATING_NOT_RECOMMENDED


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _author(item: dict[str, Any]) -> str | None:
    user = item.get("user")
    if not isinstance(user, dict):
        return None
    for key in ("id", "name"):
        value = user.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _lang(text: str) -> Lang:
    detected = detect_lang(text)
    return cast(Lang, detected if detected in _LANGS else "unknown")


class FacebookProvider:
    """Adapter for ``apify /apify/facebook-reviews-scraper``."""

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
    ) -> dict[str, Any]:
        """Actor input for one brand.

        The Query brand uses its first alias (or the brand name) for the page
        slug; a competitor named in *brand* uses its own name.
        """
        cap = PLAN.caps[query.profile]
        if cap == 0:
            raise ValueError(f"{SOURCE} is not fetched under profile {query.profile}")
        if brand is None or brand == query.brand:
            alias = query.brand_aliases[0] if query.brand_aliases else query.brand
        else:
            alias = brand
        start = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(days=query.window_days)
        return {
            "startUrls": [{"url": page_url(alias)}],
            "resultsLimit": cap,
            "onlyReviewsNewerThan": start.date().isoformat(),
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
        a caller error, never a silent reference. *terms* is accepted for the
        protocol and unused: every review of the resolved page is an entity
        match on *brand* (D014).
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("parse() needs the ledger local_seq (>= 1) to build raw_ref")
        del terms
        matched = [normalize(brand) or brand]
        mentions: list[Mention] = []
        all_items = _items(raw)
        if all_items and all(is_error_item(it) for it in all_items):
            raise AdapterEmpty(
                PROVIDER_ID,
                ENDPOINT,
                f"{len(all_items)} item(s), all provider errors: {first_error_text(all_items)}",
            )
        for index, item in enumerate(all_items):
            if not isinstance(item, dict):
                raise _drift(f"item {index}: not an object ({type(item).__name__})")
            if is_error_item(item):
                continue
            missing = [key for key in REQUIRED_KEYS if key not in item]
            if missing:
                raise _drift(f"item {index}: missing required keys {missing}")
            text = item["text"]
            if text is None:
                continue
            if not isinstance(text, str):
                raise _drift(f"item {index}: text is not a string ({type(text).__name__})")
            if not text.strip():
                continue
            raw_id = item.get("id")
            native_id = raw_id if isinstance(raw_id, str) and raw_id.strip() else None
            raw_url = item.get("url")
            url = normalize_url(raw_url) if isinstance(raw_url, str) and raw_url else None
            key = native_id or url or text_key(text)
            mention_id = mention_id_for(SOURCE, key)
            handle = _author(item)
            engagement: dict[str, int] = {}
            for wire, ours in (("likesCount", "likes"), ("commentsCount", "comments")):
                count = _count(item.get(wire))
                if count is not None:
                    engagement[ours] = count
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
                    published_at=_timestamp(item["date"], index),
                    engagement=engagement,
                    rating=_rating(item["isRecommended"], index),
                    cluster_key=mention_id,
                    matched_terms=list(matched),
                    match_kind="entity",
                    raw_ref=f"{local_seq}#{index}",
                )
            )
        return mentions

    def unit_cost(self, n_results: int) -> float:
        return n_results * PLAN.per_result_usd + PLAN.per_call_usd

    def cluster_key(self, item: Any) -> str:
        """CONTRACTS §cluster_key: review sources cluster on ``mention_id``."""
        return str(item.mention_id)


PROVIDER = FacebookProvider()
PROVIDERS[SOURCE] = PROVIDER

__all__ = [
    "ENDPOINT",
    "PROVIDER",
    "RATING_NOT_RECOMMENDED",
    "RATING_RECOMMENDED",
    "REQUIRED_KEYS",
    "SOURCE",
    "FacebookProvider",
    "page_url",
]
