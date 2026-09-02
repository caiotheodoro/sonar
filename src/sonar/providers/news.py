"""News adapter: Monid ``tinyfish /search`` with ``domain_type=news``.

Endpoint reference (design appendix, verified 2026-09-02): ``$0``,
synchronous, input ``input.queryParams{query, domain_type=news,
recency_minutes | after_date, language, page <= 10}``; output
``results[{title, snippet, url, date, site_name}]``. Caps come from
``config.SOURCE_PLAN["news"]``: pages per brand (``full`` 3, ``lite`` 2,
``smoke`` 0), never more than :data:`MAX_PAGE`.

Because the endpoint is free and synchronous, Monid returns no ``runId``
(CONTRACTS OQ-2); ``Mention.run_id`` is ``null`` and ``raw_ref`` is the
durable back-reference through the ledger ``local_seq``.

Documented fallback path (not implemented): ``context.dev`` news search,
:data:`FALLBACK_ENDPOINT`. If TinyFish disappears from the Monid catalog,
the adapter is swapped behind the same ``build_input``/``parse`` surface;
until then :attr:`NewsProvider.available` is ``True`` and there is no
second code path to drift.

``cluster_key`` for news is the ``mention_id`` (CONTRACTS §cluster_key
rules); ``author_hash`` hashes ``site_name`` (the publisher is the only
author-like handle the payload carries) and is ``null`` when absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sonar import config
from sonar.models import Lang, Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.text import detect_lang, match_terms, normalize_url

_SOURCE: Final = "news"
_PLAN = config.SOURCE_PLAN[_SOURCE]
_RESULT_KEYS = ("results", "items", "data")
_LANGS: dict[str, Lang] = {"pt": "pt", "en": "en", "other": "other", "unknown": "unknown"}


def _match_terms_for(brand: str, terms: Sequence[str] | None) -> list[str]:
    """Match list for :func:`sonar.text.match_terms`: *brand* first, then *terms* (deduplicated)."""
    out = [brand]
    for term in terms or ():
        if term not in out:
            out.append(term)
    return out


MAX_PAGE = 10
"""TinyFish ``/search`` accepts ``page`` 1..10 (design appendix)."""

FALLBACK_ENDPOINT = "context.dev news search"
"""Documented fallback if TinyFish leaves the Monid catalog; not implemented."""


@dataclass(frozen=True, slots=True)
class ParseReport:
    """Result of :meth:`NewsProvider.parse_with_report`."""

    mentions: list[Mention]
    skipped_no_match: int


def _results(raw: Any, endpoint: str) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in _RESULT_KEYS:
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = value.get("results")
                if isinstance(nested, list):
                    return nested
        raise AdapterSchemaError(
            _PLAN.provider, endpoint, f"payload has no list under any of {_RESULT_KEYS}"
        )
    raise AdapterSchemaError(
        _PLAN.provider, endpoint, f"payload is {type(raw).__name__}, expected list or object"
    )


def _require_str(item: dict[str, Any], key: str, index: int, endpoint: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterSchemaError(
            _PLAN.provider, endpoint, f"result {index}: required field {key!r} missing or empty"
        )
    return value


def _optional_str(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def parse_date(value: Any) -> datetime | None:
    """ISO 8601 date or datetime string to aware UTC; ``None`` when absent or unparseable."""
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
    return parsed.astimezone(UTC)


class NewsProvider:
    """Adapter for ``tinyfish /search`` (``domain_type=news``)."""

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

    def pages(self, query: Any) -> range:
        """Page numbers to fetch for the Query profile: ``range(1, cap + 1)``, empty when 0."""
        cap = min(_PLAN.caps[query.profile], MAX_PAGE)
        return range(1, cap + 1)

    def build_input(
        self,
        query: Any,
        *,
        brand: str | None = None,
        page: int = 1,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Monid ``input`` for one page: ``{"queryParams": {...}}``.

        *brand* selects the Query brand (default) or one competitor; the
        query string is that name alone, aliases are matched at parse time.
        *page* must fall inside :meth:`pages`. *now* fixes ``after_date``
        (start of the window) for reproducible input digests.
        """
        target = query.brand if brand is None else brand
        if target != query.brand and target not in query.competitors:
            raise ValueError(f"{target!r} is neither the Query brand nor a competitor")
        allowed = self.pages(query)
        if len(allowed) == 0:
            raise ValueError(f"news is not fetched in profile {query.profile!r}")
        if page not in allowed:
            raise ValueError(f"page must be in {allowed.start}..{allowed.stop - 1}, got {page}")
        start = (now or datetime.now(UTC)).astimezone(UTC) - timedelta(days=query.window_days)
        return {
            "queryParams": {
                "query": target,
                "domain_type": "news",
                "after_date": start.date().isoformat(),
                "page": page,
            }
        }

    def unit_cost(self, n_results: int) -> float:
        """TinyFish search is free: ``0.0`` for any count."""
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
        """Mentions of *brand* (or one of *terms*) in the search results; see :meth:`parse_with_report`."""
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
        """Parse one page of ``/search`` results into Mention rows for *brand*.

        *local_seq* is the ledger row that saved *raw* (``raw_ref``). *terms*
        are extra match terms (the brand aliases); results matching neither
        *brand* nor one of *terms* are dropped. Text is ``title`` and
        ``snippet`` joined by a blank line (post-shaped item).
        Missing ``snippet``, ``date`` or ``site_name`` degrade to their
        null forms; a missing ``url`` or ``title`` raises
        :class:`AdapterSchemaError`.
        """
        if local_seq is None or local_seq < 1:
            raise ValueError("local_seq (ledger row of the raw payload) is required, >= 1")
        endpoint = self.endpoint
        match_on = _match_terms_for(brand, terms)
        mentions: list[Mention] = []
        no_match = 0
        for index, item in enumerate(_results(raw, endpoint)):
            if not isinstance(item, dict):
                raise AdapterSchemaError(
                    _PLAN.provider, endpoint, f"result {index}: expected object"
                )
            raw_url = _require_str(item, "url", index, endpoint).strip()
            title = _require_str(item, "title", index, endpoint).strip()
            snippet = (_optional_str(item, "snippet") or "").strip()
            text = f"{title}\n\n{snippet}" if snippet else title
            matched = match_terms(text, match_on)
            if not matched:
                no_match += 1
                continue
            url = normalize_url(raw_url)
            mention_id = mention_id_for(_SOURCE, url)
            site = _optional_str(item, "site_name")
            row: dict[str, Any] = {
                "mention_id": mention_id,
                "brand": brand,
                "source": _SOURCE,
                "run_id": run_id,
                "native_id": None,
                "url": url,
                "author_hash": author_hash_for(_SOURCE, site) if site else None,
                "text": text,
                "lang": _LANGS.get(detect_lang(text), "unknown"),
                "published_at": parse_date(item.get("date")),
                "engagement": {},
                "rating": None,
                "cluster_key": mention_id,
                "matched_terms": matched,
                "raw_ref": f"{local_seq}#{index}",
            }
            mentions.append(Mention.model_validate(row))
        return ParseReport(mentions=mentions, skipped_no_match=no_match)


PROVIDER = NewsProvider()
PROVIDERS[_SOURCE] = PROVIDER
