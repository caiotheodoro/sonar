"""Provider registry — the single lookup table for all adapters.

Adapters register themselves at import time by mutating :data:`PROVIDERS`.
The pipeline resolves ``PROVIDERS[source]`` and checks ``.available``
before submitting a run.

Example adapter registration (from ``x.py``)::

    from sonar.providers.registry import PROVIDERS
    PROVIDERS["x"] = _XProvider()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sonar.providers.base import Provider

PROVIDERS: dict[str, Provider] = {}
"""Source-keyed adapter registry.

Every source in the :data:`sonar.models.Source` enum must have an entry
here.  An adapter with ``available=False`` is still registered so the
pipeline can report it as a coverage gap rather than a bug.
"""
