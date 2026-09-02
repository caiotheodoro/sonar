"""Voice script builder: narration ≤ 900 chars from the Digest JSON.

The narration is produced by ``complete_json`` against a pydantic schema, then
passed through :func:`numbers_gate` which rejects any number in the narration
that does not occur in the digest (integers, decimals, percentages and dollar
amounts, compared after normalising formatting).

Design ("Voice: ≤ 900 chars English from Digest JSON; number gate; one
ElevenLabs Monid run in the ledger").
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sonar import config
from sonar.llm.base import LlmBackend
from sonar.models import Digest

DIGEST_SYSTEM_PROMPT = """\
You are sonar's voice. Write a narration of at most 900 characters for a \
brand listening digest. The narration must be in English. \
Every number you mention MUST appear exactly as it does in the digest JSON \
provided. Do not invent, round, or rephrase any number. \
Reference share of voice, sentiment, week-over-week change, cost, and the \
incumbent comparison when available. \
Keep the tone factual and direct. No hedging, no filler.\
"""


class NarrationSchema(BaseModel):
    """Structured output schema for the narration call."""

    model_config = ConfigDict(extra="forbid")

    narration: str = Field(max_length=config.NARRATION_MAX_CHARS)

    @field_validator("narration")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("narration must not be empty")
        return value


# ---------------------------------------------------------------------------
# Number gate
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(
    r"""
    \$                           # dollar sign prefix
    (?P<dollar>[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)  # dollar amount (with commas)
  |
    (?P<plain>[0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)   # integer or decimal (with commas)
    %?                           # optional percent suffix
    """,
    re.VERBOSE,
)

_NORMALISE = re.compile(r"[\$,%]")


def _extract_numbers(text: str) -> set[str]:
    """Extract all numeric tokens from *text* after normalising formatting.

    Commas inside numbers (e.g. ``$1,234.56``) are stripped so the
    normalised form is ``1234.56``.
    """

    def _strip(m: re.Match[str]) -> str:
        return _NORMALISE.sub("", m.group()).replace(",", "")

    return {_strip(m) for m in _NUMBER_RE.finditer(text)}


def _digest_numbers(digest: Digest) -> set[str]:
    """Collect every number that appears in the serialised digest."""
    raw = digest.model_dump_json()
    return _extract_numbers(raw)


def numbers_gate(text: str, digest: Digest) -> bool:
    """Return ``True`` iff every number in *text* occurs in *digest*.

    Integers, decimals, percentages and dollar amounts are compared after
    stripping ``$``, ``,`` and ``%``.  A narration that mentions no numbers
    at all passes trivially.
    """
    narrated = _extract_numbers(text)
    if not narrated:
        return True
    available = _digest_numbers(digest)
    return narrated.issubset(available)


# ---------------------------------------------------------------------------
# generate_narration
# ---------------------------------------------------------------------------


def generate_narration(
    digest: Digest,
    *,
    backend: LlmBackend,
    model: str | None = None,
) -> tuple[str, bool]:
    """Build a narration from *digest* and verify every number against the digest.

    Returns ``(text, numbers_verified)``.  When the gate rejects a number the
    function retries once with the offending number removed from the prompt;
    if the second attempt also fails, the raw narration is returned with
    ``numbers_verified=False``.
    """
    model = model or config.LLM.classifier_model
    digest_json = digest.model_dump_json(indent=None)
    user_msg = (
        f"Digest JSON:\n{digest_json}\n\n"
        f"Write a narration of at most {config.NARRATION_MAX_CHARS} characters."
    )

    result = backend.complete_json(DIGEST_SYSTEM_PROMPT, user_msg, NarrationSchema, model)
    text = result.value.narration

    if numbers_gate(text, digest):
        return text, True

    retry_user = (
        f"Digest JSON:\n{digest_json}\n\n"
        f"Write a narration of at most {config.NARRATION_MAX_CHARS} characters. "
        "You MUST NOT invent any number. Every number you mention must appear "
        "in the digest JSON above."
    )
    result2 = backend.complete_json(DIGEST_SYSTEM_PROMPT, retry_user, NarrationSchema, model)
    text2 = result2.value.narration
    if numbers_gate(text2, digest):
        return text2, True
    return text2, False
