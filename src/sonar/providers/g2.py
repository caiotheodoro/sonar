"""G2 adapter — two-call pattern: search_software → get_product_reviews.

Each call is its own Monid run.  The adapter resolves the brand to a
G2 product slug via ``/search_software``, then fetches one page of
reviews via ``/get_product_reviews``.  When the search returns no
results the adapter abstains cleanly (empty reviews list).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS


def _author_hash(handle: str) -> str:
    """First 16 hex of sha256 over ``g2\\n{handle}``."""
    return hashlib.sha256(f"g2\n{handle}".encode()).hexdigest()[:16]


def _mention_id(review_id: str) -> str:
    """CONTRACTS §mention_id rule: sha256 over ``g2\\n{review_id}``, first 24 hex."""
    return hashlib.sha256(f"g2\n{review_id}".encode()).hexdigest()[:24]


class G2Provider:
    """G2 adapter implementing the Provider protocol."""

    _SEARCH_ENDPOINT = "/search_software"
    _REVIEWS_ENDPOINT = "/get_product_reviews"
    _PROVIDER = "g2"

    def __init__(self) -> None:
        self._slug: str | None = None

    @property
    def source(self) -> str:
        return "g2"

    @property
    def endpoint(self) -> str:
        return self._REVIEWS_ENDPOINT

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
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "'products' must be a list",
            )
        if len(products) == 0:
            return None
        first = products[0]
        if not isinstance(first, dict):
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "expected list of dicts under 'products'",
            )
        slug = first.get("slug")
        if not isinstance(slug, str) or not slug:
            raise AdapterSchemaError(
                self._PROVIDER,
                self._SEARCH_ENDPOINT,
                "first product missing non-empty 'slug' field",
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
    ) -> list[Any]:
        """Parse a ``/get_product_reviews`` response into intermediate dicts.

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
            content = review.get("content")
            if isinstance(content, str) and content.strip():
                text_parts.append(content.strip())
            combined_text = "\n\n".join(text_parts) if text_parts else ""

            rating = review.get("rating") or review.get("starRating")
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
                    "url": None,
                    "engagement": {},
                }
            )
        return items

    def unit_cost(self, n_results: int) -> float:
        """Per-call cost: $0.05 for ``/get_product_reviews``."""
        return 0.05

    def search_unit_cost(self) -> float:
        """Per-call cost: $0.02 for ``/search_software``."""
        return 0.02

    def cluster_key(self, item: Any) -> str:
        """CONTRACTS §cluster_key for g2: ``mention_id``."""
        return str(item["mention_id"])

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None


PROVIDERS["g2"] = G2Provider()
