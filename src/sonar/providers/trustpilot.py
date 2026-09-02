"""Trustpilot adapter — two-call pattern: search_companies → get_company_reviews.

Each call is its own Monid run.  The adapter resolves the brand to a
Trustpilot company domain via ``/search_companies``, then fetches one page
of reviews via ``/get_company_reviews``.  When the search returns no
results the adapter abstains cleanly (empty reviews list).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS


def _author_hash(handle: str) -> str:
    """First 16 hex of sha256 over ``trustpilot\\n{handle}``."""
    return hashlib.sha256(f"trustpilot\n{handle}".encode()).hexdigest()[:16]


def _mention_id(review_id: str) -> str:
    """CONTRACTS §mention_id rule: sha256 over ``trustpilot\\n{review_id}``, first 24 hex."""
    return hashlib.sha256(f"trustpilot\n{review_id}".encode()).hexdigest()[:24]


class TrustpilotProvider:
    """Trustpilot adapter implementing the Provider protocol."""

    _SEARCH_ENDPOINT = "/search_companies"
    _REVIEWS_ENDPOINT = "/get_company_reviews"
    _PROVIDER = "trustpilot"

    def __init__(self) -> None:
        self._domain: str | None = None

    @property
    def source(self) -> str:
        return "trustpilot"

    @property
    def endpoint(self) -> str:
        return self._REVIEWS_ENDPOINT

    def build_input(self, query: Any) -> dict[str, Any]:
        """Build the ``input`` payload for ``POST /v1/run``.

        First call (search): returns ``queryParams`` for ``/search_companies``.
        Second call (reviews): returns ``queryParams`` for ``/get_company_reviews``
        using the cached domain from the search.
        """
        brand: str = getattr(query, "brand", str(query))
        if self._domain is not None:
            return {
                "queryParams": {
                    "domain": self._domain,
                    "page": 1,
                },
            }
        return {
            "queryParams": {
                "query": brand,
                "limit": 1,
                "page": 1,
            },
        }

    def parse_search(self, raw: dict[str, Any]) -> str | None:
        """Parse a ``/search_companies`` response and return the domain, or ``None``."""
        companies = raw.get("companies")
        if companies is None:
            return None
        if not isinstance(companies, list):
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "'companies' must be a list",
            )
        if len(companies) == 0:
            return None
        first = companies[0]
        if not isinstance(first, dict):
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "expected list of dicts under 'companies'",
            )
        domain = first.get("domain")
        if not isinstance(domain, str) or not domain:
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "first company missing non-empty 'domain' field",
            )
        self._domain = domain
        return domain

    def parse(
        self,
        raw: dict[str, Any],
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Any]:
        """Parse a ``/get_company_reviews`` response into intermediate dicts.

        Returns a list of dicts, each carrying the fields needed to build
        a ``Mention`` record.  Raises ``AdapterSchemaError`` on unexpected
        payload shape.
        """
        reviews = raw.get("reviews")
        if not isinstance(reviews, list):
            raise AdapterSchemaError(
                self._PROVIDER,
                self._REVIEWS_ENDPOINT,
                "expected 'reviews' key containing a list",
            )
        items: list[dict[str, Any]] = []
        for review in reviews:
            if not isinstance(review, dict):
                raise AdapterSchemaError(
                    self._PROVIDER,
                    self._REVIEWS_ENDPOINT,
                    "expected list of dicts under 'reviews'",
                )
            review_id = review.get("reviewId")
            if not isinstance(review_id, str) or not review_id:
                raise AdapterSchemaError(
                    self._PROVIDER,
                    self._REVIEWS_ENDPOINT,
                    "review missing non-empty 'reviewId' field",
                )
            text_parts: list[str] = []
            title = review.get("title")
            if isinstance(title, str) and title.strip():
                text_parts.append(title.strip())
            text = review.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
            combined_text = "\n\n".join(text_parts) if text_parts else ""

            rating = review.get("rating")
            if rating is not None:
                try:
                    rating = int(rating)
                except (TypeError, ValueError):
                    rating = None

            author_obj = review.get("author") or {}
            author_name = ""
            if isinstance(author_obj, dict):
                author_name = str(author_obj.get("name", "") or "")

            items.append(
                {
                    "native_id": review_id,
                    "text": combined_text,
                    "rating": rating,
                    "author_name": author_name,
                    "published_at": review.get("date"),
                    "url": review.get("source", {}).get("url")
                    if isinstance(review.get("source"), dict)
                    else None,
                    "engagement": {},
                }
            )
        return items

    def unit_cost(self, n_results: int) -> float:
        """Per-call cost: $0.03 for ``/get_company_reviews``."""
        return 0.03

    def search_unit_cost(self) -> float:
        """Per-call cost: $0.03 for ``/search_companies``."""
        return 0.03

    def cluster_key(self, item: Any) -> str:
        """CONTRACTS §cluster_key for trustpilot: ``mention_id``."""
        return str(item["mention_id"])

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None


PROVIDERS["trustpilot"] = TrustpilotProvider()
