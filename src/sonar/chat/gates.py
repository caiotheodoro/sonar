"""The two gates code applies to a model answer (CONTRACTS §Answer, design Pipeline rules).

* Citations: every cited id must be a ``mention_id`` in the session store.
  Unknown ids are stripped from the citation list and from the answer text
  (``[<id>]`` markers and bare ids).
* Numbers: every numeric token in the answer must occur in ``stats.json``,
  ``topics.json`` or a retrieved mention. A token matches when its normalised
  value (``60%`` also as ``0.6``) is present exactly, or when an available
  value rounded half-up to the decimals the token was written with equals it;
  a bare integer must match exactly. Citation markers, bare mention ids and
  ISO dates are removed before extraction, so an id's hex digits and a window
  day never count as figures.

The caller decides what a failed gate means (re-ask once, then ``unverified``).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from sonar.models import Mention, StatsFile, Topic

_ID_KEYS = frozenset(
    {
        "mention_id",
        "exemplar_mention_ids",
        "topic_id",
        "url",
        "native_id",
        "raw_ref",
        "cluster_key",
        "author_hash",
        "run_id",
        "exhibit_url",
    }
)
"""Fields whose digits are identifiers or addresses, not figures an answer may quote."""

_HEX24_RE = re.compile(r"(?<![0-9a-zA-Z])[0-9a-f]{24}(?![0-9a-zA-Z])")
_MARKER_RE = re.compile(r"\[\s*([0-9a-f]{24})\s*\]")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?\b")
_NUMBER_RE = re.compile(
    r"""
    (?<![\w.])
    (?P<sign>[-−–])?
    (?P<dollar>\$)?
    (?P<digits>\d{1,3}(?:,\d{3})+|\d+)
    (?P<fraction>\.\d+)?
    \s?(?P<percent>%|percent\b|per\s?cent\b|pct\b)?
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class NumberToken:
    """One number as written, its normalised value, and the precision it was written with."""

    text: str
    value: Decimal
    percent: bool
    decimals: int

    @property
    def exact(self) -> tuple[Decimal, ...]:
        return (self.value, self.value / Decimal(100)) if self.percent else (self.value,)

    @property
    def rounded(self) -> tuple[tuple[Decimal, int], ...]:
        """``(value, places)`` an available value may round to; none for a bare integer."""
        if self.percent:
            return ((self.value, self.decimals), (self.value / Decimal(100), self.decimals + 2))
        if self.decimals >= 1:
            return ((self.value, self.decimals),)
        return ()


def _normalise(raw: str) -> Decimal:
    value = Decimal(raw.replace(",", "")).normalize()
    if value == value.to_integral_value():
        return value.quantize(Decimal(1))
    return value


def clean_for_numbers(text: str) -> str:
    """The answer text with citation markers, bare mention ids and ISO dates removed."""
    text = _MARKER_RE.sub(" ", text)
    text = _HEX24_RE.sub(" ", text)
    return _ISO_DATE_RE.sub(" ", text)


def extract_numbers(text: str) -> list[NumberToken]:
    """Every number in *text* in order of appearance (``$1,234.50`` → ``1234.5``)."""
    out: list[NumberToken] = []
    for match in _NUMBER_RE.finditer(text):
        fraction = match.group("fraction") or ""
        try:
            value = _normalise(match.group("digits") + fraction)
        except InvalidOperation:  # pragma: no cover - the regex only yields valid decimals
            continue
        if match.group("sign"):
            value = -value
        out.append(
            NumberToken(
                text=match.group(0).strip(),
                value=value,
                percent=bool(match.group("percent")),
                decimals=max(len(fraction) - 1, 0),
            )
        )
    return out


def _leaf_numbers(value: Any, key: str | None, into: set[Decimal]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        into.add(_normalise(repr(value) if isinstance(value, float) else str(value)))
    elif isinstance(value, str):
        if key not in _ID_KEYS:
            into.update(token.value for token in extract_numbers(_ISO_DATE_RE.sub(" ", value)))
    elif isinstance(value, dict):
        for k, v in value.items():
            _leaf_numbers(v, str(k), into)
    elif isinstance(value, list | tuple):
        for v in value:
            _leaf_numbers(v, key, into)


def available_numbers(
    stats: StatsFile | None, topics: Sequence[Topic], mentions: Sequence[Mention]
) -> frozenset[Decimal]:
    """Every value an answer may quote: numeric leaves and text numbers of the three sources."""
    found: set[Decimal] = set()
    if stats is not None:
        _leaf_numbers(stats.model_dump(mode="python"), None, found)
    for topic in topics:
        _leaf_numbers(topic.model_dump(mode="python"), None, found)
    for mention in mentions:
        _leaf_numbers(mention.model_dump(mode="python"), None, found)
    return frozenset(found)


def _quantize(value: Decimal, places: int) -> Decimal | None:
    try:
        return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _matches(token: NumberToken, available: frozenset[Decimal]) -> bool:
    if any(candidate in available for candidate in token.exact):
        return True
    return any(
        _quantize(value, places) == candidate
        for candidate, places in token.rounded
        for value in available
    )


@dataclass(frozen=True)
class NumbersGate:
    """Numbers found in the answer split into the verified and the foreign, as written."""

    verified: tuple[str, ...]
    foreign: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.foreign


def numbers_gate(text: str, available: frozenset[Decimal]) -> NumbersGate:
    verified: list[str] = []
    foreign: list[str] = []
    for token in extract_numbers(clean_for_numbers(text)):
        bucket = verified if _matches(token, available) else foreign
        if token.text not in bucket:
            bucket.append(token.text)
    return NumbersGate(verified=tuple(verified), foreign=tuple(foreign))


@dataclass(frozen=True)
class CitationsGate:
    """Cited ids split into the ones the store holds and the ones it does not."""

    kept: tuple[str, ...]
    unknown: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.unknown


def citations_gate(citations: Sequence[str], known: Collection[str]) -> CitationsGate:
    """Deduplicate in order; an id is kept iff it is in *known*."""
    kept: list[str] = []
    unknown: list[str] = []
    for cited in citations:
        cited = cited.strip()
        bucket = kept if cited in known else unknown
        if cited and cited not in bucket:
            bucket.append(cited)
    return CitationsGate(kept=tuple(kept), unknown=tuple(unknown))


def strip_citations(text: str, unknown: Collection[str]) -> str:
    """Remove ``[<id>]`` markers and bare occurrences of every unknown id, tidying spaces."""
    for cited in unknown:
        text = re.sub(r"\[\s*" + re.escape(cited) + r"\s*\]", "", text)
        text = text.replace(cited, "")
    text = re.sub(r"[ \t]+([.,;:!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


__all__ = [
    "CitationsGate",
    "NumberToken",
    "NumbersGate",
    "available_numbers",
    "citations_gate",
    "clean_for_numbers",
    "extract_numbers",
    "numbers_gate",
    "strip_citations",
]
