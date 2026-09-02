"""Reddit adapter: Monid ``apify /trudax/reddit-scraper-lite``.

Endpoint reference (design appendix, verified 2026-09-02): price
``0.0057/result + 0.02/call``; input ``searches[]``, ``sort=new``,
``time=week``, ``maxItems``, ``maxPostCount``, ``maxComments``,
``postDateLimit``, ``includeMediaLinks=true``; output items carry
``dataType`` (``post`` | ``comment``), ``id``, ``body``, ``title``,
``createdAt``, ``upVotes``, ``communityName``, ``url``, ``username``.

``includeMediaLinks=true`` is required: without it the actor omits
``upVotes`` and ``engagement`` would be empty for every item.

Posts and comments both become :class:`~sonar.models.Mention` rows. The
``cluster_key`` is the post id (CONTRACTS §cluster_key rules): a post's own
``id``; a comment's ``postId``, else the post id parsed from the comment
``url``, else the ``mention_id`` fallback, which is counted so the pipeline
can write "cluster key fallback: reddit <count>" into
``Receipt.what_could_not_be_checked``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sonar import config
from sonar.models import Lang, Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize_url

_SOURCE: Final = "reddit"
_PLAN = config.SOURCE_PLAN[_SOURCE]
_ITEM_KEYS = ("items", "data", "results")
_POST_URL_RE = re.compile(r"/comments/([A-Za-z0-9]+)(?:[/?#]|$)")
_ENGAGEMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("upVotes", "upvotes"),
    ("numberOfComments", "comments"),
    ("numberOfreplies", "replies"),
    ("numberOfReplies", "replies"),
)
_LANGS: dict[str, Lang] = {"pt": "pt", "en": "en", "other": "other", "unknown": "unknown"}


def _match_terms_for(brand: str, terms: Sequence[str] | None) -> list[str]:
    """Match list for :func:`sonar.text.match_terms`: *brand* first, then *terms* (deduplicated)."""
    out = [brand]
    for term in terms or ():
        if term not in out:
            out.append(term)
    return out


@dataclass(frozen=True, slots=True)
class ParseReport:
    """Result of :meth:`RedditProvider.parse_with_report`."""

    mentions: list[Mention]
    cluster_key_fallbacks: int
    skipped_no_match: int


def _terms_for(query: Any, brand: str) -> list[str]:
    """Search and match terms: the Query brand carries its aliases, a competitor only itself."""
    if brand == query.brand:
        return [query.brand, *query.brand_aliases]
    return [brand]


def _items(raw: Any, endpoint: str) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in _ITEM_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return value
        raise AdapterSchemaError(
            _PLAN.provider, endpoint, f"payload has no list under any of {_ITEM_KEYS}"
        )
    raise AdapterSchemaError(
        _PLAN.provider, endpoint, f"payload is {type(raw).__name__}, expected list or object"
    )


def _require_str(item: dict[str, Any], key: str, index: int, endpoint: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterSchemaError(
            _PLAN.provider, endpoint, f"item {index}: required field {key!r} missing or empty"
        )
    return value


def _optional_str(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_int(item: dict[str, Any], key: str) -> int | None:
    value = item.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def parse_timestamp(value: Any) -> datetime | None:
    """ISO 8601 string or epoch seconds/milliseconds to aware UTC; ``None`` when unparseable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        seconds = float(value)
        if seconds > 1e11:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _post_id_from_url(url: str | None) -> str | None:
    if url is None:
        return None
    found = _POST_URL_RE.search(url)
    if found is None:
        return None
    return f"t3_{found.group(1)}"


class RedditProvider:
    """Adapter for ``apify /trudax/reddit-scraper-lite``."""

    @property
    def source(self) -> str:
        return _SOURCE

    @property
    def endpoint(self) -> str:
        return _PLAN.endpoint

    @property
    def provider(self) -> str:
        return _PLAN.provider

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def cap(self, query: Any) -> int:
        """Per-brand result cap for the Query profile (``config.SOURCE_PLAN``)."""
        return _PLAN.caps[query.profile]

    def build_input(
        self, query: Any, *, brand: str | None = None, now: datetime | None = None
    ) -> dict[str, Any]:
        """Apify actor input, passed to Monid as ``input`` unchanged.

        *brand* selects which of the Query's brands this run fetches (default
        ``query.brand``, whose aliases become extra searches). *now* fixes
        ``postDateLimit`` (start of the 14-day window) for reproducible digests.
        """
        target = query.brand if brand is None else brand
        if target != query.brand and target not in query.competitors:
            raise ValueError(f"{target!r} is neither the Query brand nor a competitor")
        cap = self.cap(query)
        if cap <= 0:
            raise ValueError(f"reddit is not fetched in profile {query.profile!r}")
        start = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(days=query.window_days)
        return {
            "searches": _terms_for(query, target),
            "sort": "new",
            "time": "week",
            "maxItems": cap,
            "maxPostCount": cap,
            "maxComments": cap,
            "postDateLimit": start.date().isoformat(),
            "includeMediaLinks": True,
        }

    def unit_cost(self, n_results: int) -> float:
        """``0.02`` per call plus ``0.0057`` per returned item."""
        if n_results < 0:
            raise ValueError("n_results must be >= 0")
        return _PLAN.per_call_usd + n_results * _PLAN.per_result_usd

    def cluster_key(self, item: Any) -> str:
        if not isinstance(item, Mention):
            raise TypeError("cluster_key expects a Mention produced by parse()")
        return item.cluster_key

    def parse(
        self,
        raw: Any,
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Mention]:
        """Mentions of *brand* (or one of *terms*) in the actor output; see :meth:`parse_with_report`."""
        return self.parse_with_report(raw, run_id, brand, local_seq=local_seq, terms=terms).mentions

    def parse_with_report(
        self,
        raw: Any,
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> ParseReport:
        """Parse the ``providerResponse`` body into Mention rows for *brand*.

        *local_seq* is the ledger row that saved *raw* (``raw_ref``). *terms*
        are extra match terms (the brand aliases); items whose text matches
        neither *brand* nor one of *terms* are dropped, never emitted.
        Missing optional fields degrade to ``null``/``{}``; a missing required
        field (``id``, ``dataType``, a post ``title``, a comment ``body``)
        raises :class:`AdapterSchemaError`.
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("local_seq (ledger row of the raw payload) is required, >= 1")
        endpoint = self.endpoint
        match_on = _match_terms_for(brand, terms)
        mentions: list[Mention] = []
        fallbacks = 0
        no_match = 0
        for index, item in enumerate(_items(raw, endpoint)):
            if not isinstance(item, dict):
                raise AdapterSchemaError(_PLAN.provider, endpoint, f"item {index}: expected object")
            data_type = _require_str(item, "dataType", index, endpoint).strip().lower()
            native_id = _require_str(item, "id", index, endpoint).strip()
            if data_type == "post":
                title = _require_str(item, "title", index, endpoint).strip()
                body = (_optional_str(item, "body") or "").strip()
                text = f"{title}\n\n{body}" if body else title
            elif data_type == "comment":
                text = _require_str(item, "body", index, endpoint).strip()
            else:
                raise AdapterSchemaError(
                    _PLAN.provider, endpoint, f"item {index}: unknown dataType {data_type!r}"
                )
            matched = match_terms(text, match_on)
            if not matched:
                no_match += 1
                continue
            mention_id = mention_id_for(_SOURCE, native_id)
            raw_url = _optional_str(item, "url")
            url = normalize_url(raw_url) if raw_url is not None else None
            handle = _optional_str(item, "username")
            if data_type == "post":
                cluster_key = native_id
            else:
                parent = _optional_str(item, "postId") or _post_id_from_url(raw_url)
                if parent is None:
                    fallbacks += 1
                    cluster_key = mention_id
                else:
                    cluster_key = parent.strip()
            engagement: dict[str, int] = {}
            for field, key in _ENGAGEMENT_FIELDS:
                value = _optional_int(item, field)
                if value is not None and key not in engagement:
                    engagement[key] = value
            row: dict[str, Any] = {
                "mention_id": mention_id,
                "brand": brand,
                "source": _SOURCE,
                "run_id": run_id,
                "native_id": native_id,
                "url": url,
                "author_hash": author_hash_for(_SOURCE, handle) if handle else None,
                "text": text,
                "lang": _LANGS.get(detect_lang(text), "unknown"),
                "published_at": parse_timestamp(item.get("createdAt")),
                "engagement": engagement,
                "rating": None,
                "cluster_key": cluster_key,
                "matched_terms": matched,
                "raw_ref": f"{local_seq}#{index}",
            }
            mentions.append(Mention.model_validate(row))
        return ParseReport(
            mentions=mentions,
            cluster_key_fallbacks=fallbacks,
            skipped_no_match=no_match,
        )


PROVIDER = RedditProvider()
PROVIDERS[_SOURCE] = PROVIDER
