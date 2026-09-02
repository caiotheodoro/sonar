"""Topic naming through ``complete_json``: the model proposes, code caps and falls back.

The model sees the brand, the cluster size and the medoid texts (each cut to
``config.QUOTE_MAX_CHARS``) and must return ``{"name": ...}``. Code then caps
the name at ``config.TOPIC_NAME_MAX_WORDS`` words and strips quotes and a
trailing period. A refusal, unparseable output or a missing rate never fails
the run: the topic gets a deterministic fallback name and the failure is
reported to the caller as a note.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from sonar import config
from sonar.llm.base import LlmBackend, LlmError, Usage

NAMING_SYSTEM = (
    "You name topics for a brand-listening report. You are given a brand and a few "
    "verbatim mentions that were clustered together by meaning. Reply with a short "
    f"English topic name of at most {config.TOPIC_NAME_MAX_WORDS} words that says what the "
    "mentions have in common. Do not include the brand name, quotes, hashtags or a "
    "trailing period. Never invent facts that are not in the mentions."
)

_STRIP_CHARS = "\"'“”‘’`.。 \t\r\n"


class TopicName(BaseModel):
    """Wire schema the naming model must fill (structured output; canned on the fake)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)


@dataclass(frozen=True)
class NamingOutcome:
    """The name to publish, what the call cost, and why the model's answer was not used."""

    name: str
    usage: Usage | None
    failure: str | None


def render_naming_user(brand: str, n: int, exemplars: Sequence[str]) -> str:
    """The user turn: brand, cluster size and the medoid texts, one per line, quoted and cut."""
    lines = [f"Brand: {brand}", f"Mentions in this topic: {n}", "", "Exemplars:"]
    for index, text in enumerate(exemplars, start=1):
        clipped = " ".join(text.split())[: config.QUOTE_MAX_CHARS]
        lines.append(f"{index}. {clipped}")
    return "\n".join(lines)


def cap_words(name: str, max_words: int = config.TOPIC_NAME_MAX_WORDS) -> str:
    """Whitespace-normalised name cut to ``max_words`` words, quotes and trailing period removed."""
    words = name.strip(_STRIP_CHARS).split()
    return " ".join(words[:max_words]).strip(_STRIP_CHARS)


def fallback_name(brand: str, index: int) -> str:
    """Deterministic name when the model gives none: ``"{brand} topic {index:02d}"``."""
    return f"{brand} topic {index:02d}"


def name_topic(
    backend: LlmBackend,
    model: str,
    *,
    brand: str,
    index: int,
    n: int,
    exemplars: Sequence[str],
) -> NamingOutcome:
    """Name one topic; a seam failure or an empty answer yields the fallback and a note."""
    user = render_naming_user(brand, n, exemplars)
    try:
        result = backend.complete_json(NAMING_SYSTEM, user, TopicName, model)
    except LlmError as exc:
        return NamingOutcome(
            name=fallback_name(brand, index),
            usage=None,
            failure=f"{type(exc).__name__}: {exc}",
        )
    capped = cap_words(result.value.name)
    if not capped:
        return NamingOutcome(
            name=fallback_name(brand, index),
            usage=result.usage,
            failure="model returned a blank name",
        )
    return NamingOutcome(name=capped, usage=result.usage, failure=None)


__all__ = [
    "NAMING_SYSTEM",
    "NamingOutcome",
    "TopicName",
    "cap_words",
    "fallback_name",
    "name_topic",
    "render_naming_user",
]
