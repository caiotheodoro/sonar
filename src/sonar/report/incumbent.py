"""The incumbent sonar is priced against: Brand24 Team.

``BRAND24_TEAM`` is the single source of the ``Receipt.incumbent`` block
(CONTRACTS §Receipt). The published-claims gate requires these values to be
identical to the README and to ``results/demo/receipt.json``; evidence for the
price is ``results/incumbent/`` and ``docs/DECISIONS.md`` D001.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final


@dataclass(frozen=True, slots=True)
class Incumbent:
    name: str
    price_usd_month: int
    url: str
    checked_at: date
    mentions_quota: int

    def to_record(self) -> dict[str, str | int]:
        """Wire form of ``Receipt.incumbent`` with ``checked_at`` as an ISO date."""
        return {
            "name": self.name,
            "price_usd_month": self.price_usd_month,
            "url": self.url,
            "checked_at": self.checked_at.isoformat(),
            "mentions_quota": self.mentions_quota,
        }


BRAND24_TEAM: Final[Incumbent] = Incumbent(
    name="Brand24 Team",
    price_usd_month=349,
    url="https://brand24.com/prices",
    checked_at=date(2026, 9, 2),
    mentions_quota=10000,
)
