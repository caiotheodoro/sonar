"""Provider protocol and AdapterSchemaError.

The frozen pydantic Mention model lives in ``src/sonar/models.py``.
The protocol is defined here so adapters can import it without pulling
in the full model layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


class AdapterSchemaError(Exception):
    """Raised when a Monid payload no longer matches the expected schema."""

    def __init__(self, provider: str, endpoint: str, detail: str) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.detail = detail
        super().__init__(f"{provider} {endpoint}: {detail}")


class AdapterEmpty(Exception):
    """Raised when the provider returned no usable results.

    An empty search or an Apify actor that could not resolve the target is
    not a schema change: the adapter is fine, the query just had no hits.
    The pipeline turns this into an ``empty`` abstention for the source,
    never ``schema_drift``.
    """

    def __init__(self, provider: str, endpoint: str, detail: str) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.detail = detail
        super().__init__(f"{provider} {endpoint}: {detail}")


_ERROR_ITEM_KEYS: tuple[str, ...] = ("error", "errorDescription", "errorMessage", "errorMsg")


def is_error_item(item: Any) -> bool:
    """True for an Apify dataset row that reports a failed sub-fetch, not a result.

    Actors that find nothing (no such page, private video, no search hits)
    emit rows like ``{"error": "...", "url": "..."}`` instead of an empty
    list. Such a row is not a mention and not schema drift.
    """
    if not isinstance(item, dict):
        return False
    return any(isinstance(item.get(key), str) and item[key].strip() for key in _ERROR_ITEM_KEYS)


def first_error_text(items: Sequence[Any]) -> str:
    """The first error string among *items*, truncated — for an :class:`AdapterEmpty` detail."""
    for item in items:
        if isinstance(item, dict):
            for key in _ERROR_ITEM_KEYS:
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:160]
    return "no detail"


@runtime_checkable
class Provider(Protocol):
    """Structural contract every adapter must satisfy.

    Adapters register themselves into :data:`sonar.providers.registry.PROVIDERS`
    at import time (see ``registry.py``).
    """

    @property
    def source(self) -> str:
        """Source enum value (e.g. ``"reddit"``)."""
        ...

    @property
    def endpoint(self) -> str:
        """Monid endpoint path (e.g. ``"/trudax/reddit-scraper-lite"``)."""
        ...

    def build_input(self, query: Any) -> dict[str, Any]:
        """Build the ``input`` payload for ``POST /v1/run``.

        *query* is the validated :class:`~sonar.models.Query` (passed as
        ``Any`` here to avoid a circular import before models.py exists).
        """
        ...

    def parse(
        self,
        raw: dict[str, Any],
        run_id: str | None,
        brand: str,
        *,
        local_seq: int | None = None,
        terms: Sequence[str] | None = None,
    ) -> list[Any]:
        """Parse a Monid provider response into a list of Mention records.

        *raw* is the ``providerResponse`` body; *run_id* is the Monid run
        id (``None`` for ``$0`` sync endpoints); *brand* is the brand this
        batch was fetched for.  *local_seq* is required to build
        ``Mention.raw_ref``.

        Raises :class:`AdapterSchemaError` on unexpected payload shape.
        """
        ...

    def unit_cost(self, n_results: int) -> float:
        """Return the estimated USD cost for *n_results* items."""
        ...

    def cluster_key(self, item: Any) -> str:
        """Compute the bootstrap resampling key for one parsed item.

        *item* is a single element from the list returned by :meth:`parse`.
        """
        ...

    @property
    def available(self) -> bool:
        """Whether this adapter can currently serve requests.

        ``False`` means the endpoint is absent from the Monid catalog;
        the adapter registers but never submits runs.
        """
        ...

    @property
    def unavailable_reason(self) -> str | None:
        """Human-readable reason when ``available`` is ``False``."""
        ...
