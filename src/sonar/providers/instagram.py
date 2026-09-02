"""Instagram adapter for ``apify /apify/instagram-hashtag-scraper`` (W3.3).

Input: ``hashtags`` derived from the brand and its aliases (letters and
digits only, casefolded, distinct), ``resultsLimit`` from
``config.SOURCE_PLAN``. Output items carry the caption in ``caption``, the
owner in ``ownerUsername`` and, when present, a ``timestamp``. An item
without a timestamp keeps ``published_at=null``; the source is flagged
``wow_scope=False`` (D012 F2: it counts for share and is excluded from WoW
and events), never abstained.

``cluster_key`` is the author hash (CONTRACTS §cluster_key rules), falling
back to ``mention_id`` when the payload has no owner. Field names follow
the actor's documented output and are re-checked against the recorded
fixture in W3.7.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sonar import config
from sonar.models import Lang, Mention, Source, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize_url, text_key

_PLAN = config.SOURCE_PLAN["instagram"]
_SOURCE: Source = "instagram"
_TEXT_KEY = "caption"
_POST_URL = "https://www.instagram.com/p/{short_code}/"
_ITEM_LIST_KEYS: tuple[str, ...] = ("output", "items", "data", "results")
_ENGAGEMENT: tuple[tuple[str, str], ...] = (
    ("likes", "likesCount"),
    ("comments", "commentsCount"),
    ("views", "videoViewCount"),
)


def _field(query: Any, name: str, default: Any = None) -> Any:
    if isinstance(query, Mapping):
        return query.get(name, default)
    return getattr(query, name, default)


def _terms_of(query: Any) -> list[str]:
    brand = _field(query, "brand")
    aliases = _field(query, "brand_aliases", []) or []
    if not isinstance(brand, str) or not brand.strip():
        raise ValueError("query.brand must be a non-empty string")
    return [brand, *[a for a in aliases if isinstance(a, str) and a.strip()]]


def hashtag_of(term: str) -> str:
    """Letters and digits of *term* after NFKC and casefold; ``""`` when none remain."""
    folded = unicodedata.normalize("NFKC", term).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


def hashtags_of(terms: Sequence[str]) -> list[str]:
    """Distinct hashtags for *terms* in first-seen order, empties dropped."""
    out: list[str] = []
    for term in terms:
        tag = hashtag_of(term)
        if tag and tag not in out:
            out.append(tag)
    return out


def _cap_for(query: Any) -> int:
    profile = _field(query, "profile", "full")
    if profile not in _PLAN.caps:
        raise ValueError(f"unknown profile {profile!r}")
    cap = _PLAN.caps[profile]
    if cap == 0:
        raise ValueError(f"{_SOURCE} is not fetched under profile {profile!r} (cap 0)")
    return cap


def _items(raw: Any, endpoint: str) -> list[Any]:
    """Locate the item list in a Monid run body or its ``providerResponse``."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, Mapping):
        for key in _ITEM_LIST_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return value
        nested = raw.get("providerResponse")
        if isinstance(nested, Mapping):
            for key in _ITEM_LIST_KEYS:
                value = nested.get(key)
                if isinstance(value, list):
                    return value
    raise AdapterSchemaError(
        _PLAN.provider, endpoint, f"no item list under any of {_ITEM_LIST_KEYS}"
    )


def _local_seq(raw: Any, local_seq: int | None) -> int:
    if local_seq is None and isinstance(raw, Mapping):
        value = raw.get("local_seq")
        if isinstance(value, int) and not isinstance(value, bool):
            local_seq = value
    if local_seq is None or local_seq < 1:
        raise ValueError("local_seq (ledger row, >= 1) is required to build Mention.raw_ref")
    return local_seq


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0)
    return None


def _lang(text: str) -> Lang:
    detected = detect_lang(text)
    if detected == "pt":
        return "pt"
    if detected == "en":
        return "en"
    if detected == "other":
        return "other"
    return "unknown"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _engagement(item: Mapping[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, payload_key in _ENGAGEMENT:
        value = _int_or_none(item.get(payload_key))
        if value is not None:
            out[key] = value
    return out


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | str):
        text = str(value).strip()
        return text or None
    return None


def _author_handle(item: Mapping[str, Any]) -> str | None:
    for key in ("ownerUsername", "ownerId"):
        handle = _str_or_none(item.get(key))
        if handle is not None:
            return handle
    owner = item.get("owner")
    if isinstance(owner, Mapping):
        for key in ("username", "id"):
            handle = _str_or_none(owner.get(key))
            if handle is not None:
                return handle
    return None


def _url(item: Mapping[str, Any]) -> str | None:
    value = _str_or_none(item.get("url"))
    if value is None:
        short_code = _str_or_none(item.get("shortCode"))
        if short_code is None:
            return None
        value = _POST_URL.format(short_code=short_code)
    return normalize_url(value)


class InstagramProvider:
    """Adapter for ``apify /apify/instagram-hashtag-scraper``."""

    @property
    def source(self) -> str:
        return _SOURCE

    @property
    def endpoint(self) -> str:
        return _PLAN.endpoint

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    @property
    def wow_scope(self) -> bool:
        """``False``: hashtag items may lack ``timestamp`` (D012 F2, `BySourceEntry.wow_scope`)."""
        return _PLAN.has_timestamps

    def build_input(self, query: Any) -> dict[str, Any]:
        hashtags = hashtags_of(_terms_of(query))
        if not hashtags:
            raise ValueError("no hashtag can be derived from the brand and its aliases")
        return {"hashtags": hashtags, "resultsLimit": _cap_for(query)}

    def parse(
        self,
        raw: dict[str, Any],
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Mention]:
        """Turn one run payload into Mention rows for *brand*.

        *terms* are the brand and alias strings matched at word boundaries;
        they default to ``[brand]``. Items with no match, or with an empty
        caption, are skipped. A missing optional field never raises; a
        missing ``caption`` key raises :class:`AdapterSchemaError`.
        """
        seq = _local_seq(raw, local_seq)
        match_against = list(terms) if terms else [brand]
        mentions: list[Mention] = []
        for index, item in enumerate(_items(raw, self.endpoint)):
            if not isinstance(item, Mapping):
                raise AdapterSchemaError(
                    _PLAN.provider,
                    self.endpoint,
                    f"item {index} is {type(item).__name__}, not object",
                )
            text = self._text(item, index)
            if not text.strip():
                continue
            matched = match_terms(text, match_against)
            if not matched:
                continue
            native_id = _str_or_none(item.get("id")) or _str_or_none(item.get("shortCode"))
            url = _url(item)
            key = native_id or url or text_key(text)
            mention_id = mention_id_for(_SOURCE, key)
            handle = _author_handle(item)
            author_hash = author_hash_for(_SOURCE, handle) if handle is not None else None
            # Validated from a dict so ``run_id`` follows CONTRACTS 1.1.0 (D012 F12,
            # ``str | None``) once models.py adopts it; the model stays the judge.
            mentions.append(
                Mention.model_validate(
                    {
                        "mention_id": mention_id,
                        "brand": brand,
                        "source": _SOURCE,
                        "run_id": run_id,
                        "native_id": native_id,
                        "url": url,
                        "author_hash": author_hash,
                        "text": text,
                        "lang": _lang(text),
                        "published_at": _parse_timestamp(item.get("timestamp")),
                        "engagement": _engagement(item),
                        "rating": None,
                        "cluster_key": author_hash if author_hash is not None else mention_id,
                        "matched_terms": matched,
                        "raw_ref": f"{seq}#{index}",
                    }
                )
            )
        return mentions

    def _text(self, item: Mapping[str, Any], index: int) -> str:
        if _TEXT_KEY not in item:
            raise AdapterSchemaError(
                _PLAN.provider, self.endpoint, f"item {index}: required key {_TEXT_KEY!r} absent"
            )
        value = item[_TEXT_KEY]
        if value is None:
            return ""
        if not isinstance(value, str):
            raise AdapterSchemaError(
                _PLAN.provider,
                self.endpoint,
                f"item {index}: {_TEXT_KEY} is {type(value).__name__}, expected string",
            )
        return value

    def unit_cost(self, n_results: int) -> float:
        """Billed per call; *n_results* does not change the price."""
        return _PLAN.per_call_usd + max(n_results, 0) * _PLAN.per_result_usd

    def cluster_key(self, item: Any) -> str:
        if isinstance(item, Mention):
            return item.author_hash if item.author_hash is not None else item.mention_id
        raise TypeError(f"cluster_key expects a Mention, got {type(item).__name__}")


PROVIDER = InstagramProvider()
PROVIDERS[_SOURCE] = PROVIDER

__all__ = ["PROVIDER", "InstagramProvider", "hashtag_of", "hashtags_of"]
