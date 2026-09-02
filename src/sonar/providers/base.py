"""Provider protocol and AdapterSchemaError.

W2.1 owns ``src/sonar/models.py`` and will define the frozen pydantic
Mention model.  The protocol is defined here so adapters can import it
without pulling in the full model layer.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class AdapterSchemaError(Exception):
    """Raised when a Monid payload no longer matches the expected schema."""

    def __init__(self, provider: str, endpoint: str, detail: str) -> None:
        self.provider = provider
        self.endpoint = endpoint
        self.detail = detail
        super().__init__(f"{provider} {endpoint}: {detail}")


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
        self, raw: dict[str, Any], run_id: str, brand: str
    ) -> list[Any]:
        """Parse a Monid provider response into a list of Mention records.

        *raw* is the ``providerResponse`` body; *run_id* is the Monid run
        id; *brand* is the brand this batch was fetched for.

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
