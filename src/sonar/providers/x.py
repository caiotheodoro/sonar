"""X/Twitter adapter — registered as unavailable.

Monid's catalog had no X/Twitter endpoint on 2026-09-02.  The adapter
is registered in :data:`sonar.providers.registry.PROVIDERS` so the
pipeline can report it as a coverage gap rather than a missing adapter.
"""

from __future__ import annotations

from typing import Any

from sonar.providers.registry import PROVIDERS

_UNAVAILABLE_REASON = "Monid catalog has no X/Twitter endpoint (verified 2026-09-02)"


class _XProvider:
    """Stub provider for X/Twitter.  ``available`` is always ``False``."""

    @property
    def source(self) -> str:
        return "x"

    @property
    def endpoint(self) -> str:
        raise RuntimeError("X/Twitter endpoint unavailable")

    def build_input(self, query: Any) -> dict[str, Any]:
        raise RuntimeError("X/Twitter endpoint unavailable")

    def parse(self, raw: Any, run_id: str, brand: str) -> list[Any]:
        raise RuntimeError("X/Twitter endpoint unavailable")

    def unit_cost(self, n_results: int) -> float:
        raise RuntimeError("X/Twitter endpoint unavailable")

    def cluster_key(self, item: Any) -> str:
        raise RuntimeError("X/Twitter endpoint unavailable")

    @property
    def available(self) -> bool:
        return False

    @property
    def unavailable_reason(self) -> str:
        return _UNAVAILABLE_REASON


PROVIDERS["x"] = _XProvider()
