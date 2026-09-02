"""Voice script: an English narration of at most 900 characters from the Digest.

The narration comes from the llm seam's ``complete_json`` against
:class:`NarrationSchema` and then passes the numbers gate
(:func:`numbers_gate`): every number in the narration (integer, decimal,
percentage or dollar amount, with an optional sign, compared after
normalising formatting) must occur in the digest, otherwise the narration
carries ``numbers_verified=false`` and nothing is spent on audio (D006;
CONTRACTS §Digest ``narration``).

A rejected first draft is re-asked once with the foreign numbers listed; a
first draft that does not validate (over budget, empty) is re-asked once
with a request to shorten it.

The pipeline gates the narration against the digest it was written from and
then, once the final receipt is quoted into the digest (``requote_cost``),
re-gates it with :func:`regate` before writing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sonar import config
from sonar.llm.base import LlmBackend, LlmUnparseable, Usage
from sonar.models import Digest, Narration

NARRATION_SYSTEM_PROMPT = """\
You narrate a brand listening digest for a spoken brief.
Write in English, at most {max_chars} characters, plain sentences, no headings or lists.
Cover share of voice, sentiment, the week-over-week verdicts, the top topic and the cost.
Every number you say must come from the digest JSON: state it with at most two decimals, \
rounded, never converted between units; do not invent or estimate any number. A share \
written as 0.6 may be read as 60%. Name abstentions as "not enough data" without \
inventing figures.\
"""
"""Frozen system prompt for the narration call (``{max_chars}`` is filled at call time)."""

MAX_ATTEMPTS = 2
"""One draft plus one re-ask when the numbers gate or the schema rejects the draft."""

_ID_KEYS = frozenset({"mention_id", "exemplar_mention_ids", "topic_id", "url", "mp3_path"})
"""String fields whose digits are identifiers, not figures the narration may quote."""


class NarrationSchema(BaseModel):
    """Structured output of the narration call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    narration: str = Field(max_length=config.NARRATION_MAX_CHARS)

    @field_validator("narration", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        """Padding does not count against the cap."""
        return value.strip() if isinstance(value, str) else value

    @field_validator("narration")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("narration must not be empty")
        return value


# ---------------------------------------------------------------------------
# Numbers gate
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"""
    (?:(?P<minus>\bminus\s+)|(?P<sign>(?<![\d.])[-−–]))?   # optional sign or the word minus
    (?P<dollar>\$)?                                # optional dollar sign
    (?P<digits>\d{1,3}(?:,\d{3})+|\d+)             # 1,234 or 1234
    (?P<fraction>\.\d+)?                           # optional decimals
    \s?(?P<percent>%|(?:percent|per\s?cent|pct)\b)?  # optional percent
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True)
class NumberToken:
    """One number as written in a text, with its normalised value.

    ``decimals`` is the number of decimal places written (``0.60`` → 2,
    ``$1,234.50`` → 2, ``30`` → 0); it sets the precision a digest value is
    rounded to when matching.
    """

    text: str
    value: Decimal
    percent: bool
    decimals: int = 0

    @property
    def candidates(self) -> tuple[Decimal, ...]:
        """Values that count as a match: ``60%`` matches ``60`` or ``0.6``."""
        if self.percent:
            return (self.value, self.value / Decimal(100))
        return (self.value,)

    @property
    def rounded_candidates(self) -> tuple[tuple[Decimal, int], ...]:
        """``(value, places)`` pairs a digest value may round to (ROUND_HALF_UP).

        A token with decimals matches a digest value rounded to that many
        places; a percent token also matches a proportion rounded to two more
        places (``34%`` ↔ ``0.336…``). A bare integer that is not a percent has
        no rounded candidates, so ``30`` never vouches for ``29.6``.
        """
        if self.percent:
            return (
                (self.value, self.decimals),
                (self.value / Decimal(100), self.decimals + 2),
            )
        if self.decimals >= 1:
            return ((self.value, self.decimals),)
        return ()


def _normalise(raw: str) -> Decimal:
    """``1,234.50`` → ``1234.5``; ``60`` stays ``60`` (no exponent form)."""
    value = Decimal(raw.replace(",", "")).normalize()
    if value == value.to_integral_value():
        return value.quantize(Decimal(1))
    return value


def extract_numbers(text: str) -> list[NumberToken]:
    """Every number in *text*, in order of appearance.

    ``$1,234.50`` → ``1234.5``; ``60%`` → ``60`` flagged percent; ``0.42`` →
    ``0.42``; ``-0.27``, ``−0.27`` and ``minus 0.27`` → ``-0.27``.
    """
    out: list[NumberToken] = []
    for match in _NUMBER_RE.finditer(text):
        fraction = match.group("fraction") or ""
        raw = match.group("digits") + fraction
        try:
            value = _normalise(raw)
        except InvalidOperation:  # pragma: no cover - the regex only yields valid decimals
            continue
        if match.group("sign") or match.group("minus"):
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
    elif isinstance(value, Decimal):
        into.add(_normalise(str(value)))
    elif isinstance(value, str):
        if key in _ID_KEYS:
            return
        into.update(token.value for token in extract_numbers(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            _leaf_numbers(v, str(k), into)
    elif isinstance(value, list | tuple):
        for v in value:
            _leaf_numbers(v, key, into)


def digest_numbers(digest: Digest) -> frozenset[Decimal]:
    """Every number the narration may quote: numeric leaves and text fields.

    Identifier fields (mention ids, topic ids, urls) are skipped so their digits
    do not vouch for a figure the model made up; dates contribute nothing, so a
    window day never vouches for a count.
    """
    found: set[Decimal] = set()
    _leaf_numbers(digest.model_dump(mode="python", exclude={"narration"}), None, found)
    return frozenset(found)


def _quantize(value: Decimal, places: int) -> Decimal | None:
    try:
        return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _matches(token: NumberToken, available: frozenset[Decimal]) -> bool:
    if any(candidate in available for candidate in token.candidates):
        return True
    for candidate, places in token.rounded_candidates:
        if any(_quantize(value, places) == candidate for value in available):
            return True
    return False


@dataclass(frozen=True)
class GateResult:
    """Outcome of :func:`numbers_gate`: the tokens found and the ones the digest lacks."""

    tokens: tuple[NumberToken, ...]
    foreign: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return not self.foreign


def numbers_gate(text: str, digest: Digest) -> GateResult:
    """Check every number in *text* against *digest*.

    A number passes when any of its normalised candidates occurs in the digest,
    or when a digest value rounded (ROUND_HALF_UP) to the decimals the number
    was written with equals it; a bare integer must match exactly. The ones
    that do not pass are returned as written, deduplicated, in order.
    """
    available = digest_numbers(digest)
    tokens = tuple(extract_numbers(text))
    foreign: list[str] = []
    for token in tokens:
        if _matches(token, available):
            continue
        if token.text not in foreign:
            foreign.append(token.text)
    return GateResult(tokens=tokens, foreign=tuple(foreign))


def regate(narration: Narration, digest: Digest) -> Narration:
    """Re-run the numbers gate on *digest* and return *narration* with ``numbers_verified`` updated.

    Called after the final receipt is quoted into the digest so that
    ``numbers_verified`` holds against the digest that ships. A narration
    without text is returned unchanged.
    """
    if narration.text is None:
        return narration
    verified = numbers_gate(narration.text, digest).verified
    if verified == narration.numbers_verified:
        return narration
    return narration.model_copy(update={"numbers_verified": verified})


@dataclass(frozen=True)
class ScriptResult:
    """The narration record, the seam usage of every attempt and the last foreign numbers."""

    narration: Narration
    usage: tuple[Usage, ...]
    attempts: int
    foreign: tuple[str, ...]


def _user_message(digest_json: str, foreign: tuple[str, ...], over_budget: bool) -> str:
    parts = [
        f"Digest JSON:\n{digest_json}",
        f"Write the narration ({config.NARRATION_MAX_CHARS} characters at most).",
    ]
    if foreign:
        parts.append(
            "Your previous draft used numbers that are not in the digest: "
            + ", ".join(foreign)
            + ". Remove them or replace them with numbers taken from the digest."
        )
    if over_budget:
        parts.append(
            f"Your previous draft exceeded {config.NARRATION_MAX_CHARS} characters; shorten it."
        )
    return "\n\n".join(parts)


def write_script(digest: Digest, *, backend: LlmBackend, model: str | None = None) -> ScriptResult:
    """Draft the narration and gate its numbers, re-asking once on a rejection.

    Returns a :class:`~sonar.models.Narration` with ``mp3_path`` and ``local_seq``
    unset. After two rejected drafts the last text is kept with
    ``numbers_verified=false`` so the digest shows what was said and why no
    audio was made. A draft that fails the schema (over budget, empty) is
    re-asked once with a request to shorten it; the second such failure
    propagates as ``LlmUnparseable``. Other seam errors (``LlmError``)
    propagate to the caller.
    """
    model = model or config.LLM.classifier_model
    system = NARRATION_SYSTEM_PROMPT.format(max_chars=config.NARRATION_MAX_CHARS)
    digest_json = digest.model_dump_json(exclude={"narration"})
    usage: list[Usage] = []
    foreign: tuple[str, ...] = ()
    over_budget = False
    text = ""
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        user = _user_message(digest_json, foreign, over_budget)
        try:
            result = backend.complete_json(system, user, NarrationSchema, model)
        except LlmUnparseable:
            if attempts >= MAX_ATTEMPTS:
                raise
            over_budget = True
            continue
        usage.append(result.usage)
        text = result.value.narration
        gate = numbers_gate(text, digest)
        foreign = gate.foreign
        if gate.verified:
            break
    narration = Narration(
        text=text,
        chars=len(text),
        numbers_verified=not foreign,
        mp3_path=None,
        local_seq=None,
    )
    return ScriptResult(narration=narration, usage=tuple(usage), attempts=attempts, foreign=foreign)


__all__ = [
    "MAX_ATTEMPTS",
    "NARRATION_SYSTEM_PROMPT",
    "GateResult",
    "NarrationSchema",
    "NumberToken",
    "ScriptResult",
    "digest_numbers",
    "extract_numbers",
    "numbers_gate",
    "regate",
    "write_script",
]
