"""The model seam: what the pipeline may ask of an LLM, and what it gets back.

Three operations, each returning its payload together with a ``Usage`` record
(tokens and USD cost priced from ``config.LLM_RATES``):

* ``classify(batch, model)``: one ``LabelObservation`` per ``MentionText`` in
  the batch, in batch order, ids round-tripped exactly. A mention id the model
  did not answer for comes back with ``status="unparseable"``; ids the model
  invented are dropped. Model-side failures never raise: a refusal marks every
  id ``refused``, an exhausted-retry error marks every id ``error``.
* ``complete_json(system, user, schema, model)``: a parsed instance of a
  pydantic ``schema`` (structured output on the backend, canned on the fake).
  Refusals and unparseable output raise ``LlmRefusal`` / ``LlmUnparseable``.
* ``embed(texts, model)``: a float64 array of shape ``(len(texts), dim)``.

Only ``openai_backend.py`` imports ``openai``. ``SentimentLabel`` is the
CONTRACTS §Enumerations ``Label`` vocabulary. ``LabelStatus`` here is the
subset a single model call can produce: ``ok``, ``refused``, ``unparseable``,
``error``. CONTRACTS' fifth status, ``cached``, is by design not producible at
this seam: it is assigned upstream by ``sentiment/``'s label cache, which never
calls the model. ``models.py`` (W2.1) owns the full records; this module owns
only the observation the model returns.

Pricing: OpenAI bills prompt tokens served from its prompt cache
(``usage.prompt_tokens_details.cached_tokens``) at a reduced rate. ``Rate``
carries that reduced rate as ``cached_input_usd_per_mtok``; when a rate table
does not state one, cached tokens are priced at the full input rate, which
can only over-report cost, never under-report it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol, TypeVar, runtime_checkable

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sonar import config

SentimentLabel = Literal["positive", "negative", "neutral", "irrelevant"]
LabelStatus = Literal["ok", "refused", "unparseable", "error"]
LlmKind = Literal["classify", "tiebreak", "embed", "name_topic", "narrate", "ask"]

SchemaT = TypeVar("SchemaT", bound=BaseModel)

RATES_DATED: date = config.LLM_RATES_CHECKED_AT
"""Date ``config.LLM_RATES`` was last read from OpenAI pricing (D003)."""

RATIONALE_MAX_CHARS = 200
RATIONALE_MAX_WORDS: int = config.RATIONALE_MAX_WORDS
"""D004: the classifier's rationale is at most twenty whitespace-separated words."""


class LlmError(RuntimeError):
    """Base class for seam errors that are not per-id statuses."""


class LlmRateError(LlmError):
    """No price is known for the requested model; cost cannot be reported."""


class LlmRefusal(LlmError):
    """The model refused a ``complete_json`` request."""


class LlmUnparseable(LlmError):
    """The model's ``complete_json`` output did not validate against the schema."""


class Rate(BaseModel):
    """USD per million tokens for one model id.

    ``cached_input_usd_per_mtok`` is the price of a prompt token served from the
    provider's prompt cache. ``None`` means the table does not state one, and
    cached tokens are then priced at ``input_usd_per_mtok``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_usd_per_mtok: float = Field(ge=0.0)
    output_usd_per_mtok: float = Field(ge=0.0)
    cached_input_usd_per_mtok: float | None = Field(default=None, ge=0.0)
    dated: date = RATES_DATED

    @model_validator(mode="after")
    def _cached_not_dearer_than_input(self) -> Rate:
        cached = self.cached_input_usd_per_mtok
        if cached is not None and cached > self.input_usd_per_mtok:
            raise ValueError("cached_input_usd_per_mtok must not exceed input_usd_per_mtok")
        return self

    @property
    def effective_cached_input_usd_per_mtok(self) -> float:
        """The rate cached prompt tokens are billed at: the stated one, else full input."""
        cached = self.cached_input_usd_per_mtok
        return self.input_usd_per_mtok if cached is None else cached


_INPUT_KEYS = ("input_usd_per_mtok", "input_per_mtok", "input", "prompt")
_OUTPUT_KEYS = ("output_usd_per_mtok", "output_per_mtok", "output", "completion")
_CACHED_KEYS = ("cached_input_usd_per_mtok", "cached_input_per_mtok", "cached_input", "cached")


def coerce_rates(raw: Mapping[str, object]) -> dict[str, Rate]:
    """Normalise a ``config.LLM_RATES``-shaped table into ``Rate`` records.

    Accepts ``Rate`` instances, objects with ``input_usd_per_mtok`` /
    ``output_usd_per_mtok`` attributes (``config.LlmRate``; an optional
    ``cached_input_usd_per_mtok`` attribute is carried through), ``(input,
    output)`` or ``(input, output, cached_input)`` tuples, or mappings whose
    keys are any of ``input_usd_per_mtok``/``input``/``prompt``,
    ``output_usd_per_mtok``/``output``/``completion`` and optionally
    ``cached_input_usd_per_mtok``/``cached_input``/``cached`` (USD per MTok).
    An optional ``dated`` key (``date`` or ISO string) is carried through.
    """
    out: dict[str, Rate] = {}
    for model, value in raw.items():
        if isinstance(value, Rate):
            out[model] = value
        elif hasattr(value, "input_usd_per_mtok") and hasattr(value, "output_usd_per_mtok"):
            cached_attr = getattr(value, "cached_input_usd_per_mtok", None)
            out[model] = Rate(
                input_usd_per_mtok=float(value.input_usd_per_mtok),
                output_usd_per_mtok=float(value.output_usd_per_mtok),
                cached_input_usd_per_mtok=None if cached_attr is None else float(cached_attr),
            )
        elif isinstance(value, Mapping):
            out[model] = _rate_from_mapping(model, value)
        elif isinstance(value, Sequence) and not isinstance(value, str) and len(value) in (2, 3):
            out[model] = Rate(
                input_usd_per_mtok=float(value[0]),
                output_usd_per_mtok=float(value[1]),
                cached_input_usd_per_mtok=float(value[2]) if len(value) == 3 else None,
            )
        else:
            raise LlmRateError(f"unrecognised rate entry for {model!r}: {value!r}")
    return out


def _rate_from_mapping(model: str, value: Mapping[object, object]) -> Rate:
    def pick(keys: tuple[str, ...]) -> float | None:
        for key in keys:
            if key in value:
                return float(value[key])  # type: ignore[arg-type]
        return None

    input_rate = pick(_INPUT_KEYS)
    output_rate = pick(_OUTPUT_KEYS)
    if input_rate is None:
        raise LlmRateError(f"rate for {model!r} has none of {_INPUT_KEYS}: {sorted(map(str, value))}")
    if output_rate is None:
        raise LlmRateError(f"rate for {model!r} has none of {_OUTPUT_KEYS}: {sorted(map(str, value))}")
    dated_raw = value.get("dated")
    dated = (
        date.fromisoformat(dated_raw)
        if isinstance(dated_raw, str)
        else dated_raw
        if isinstance(dated_raw, date)
        else RATES_DATED
    )
    return Rate(
        input_usd_per_mtok=input_rate,
        output_usd_per_mtok=output_rate,
        cached_input_usd_per_mtok=pick(_CACHED_KEYS),
        dated=dated,
    )


def load_rates() -> dict[str, Rate]:
    """``config.LLM_RATES`` (the single source of truth, D003) as ``Rate`` records."""
    raw = config.LLM_RATES
    if not isinstance(raw, Mapping):
        raise LlmRateError(f"sonar.config.LLM_RATES is {type(raw).__name__}, expected a mapping")
    return coerce_rates(raw)


class Usage(BaseModel):
    """Tokens and cost of one seam call, priced from the rate table at call time.

    ``input_tokens`` is the whole prompt as the provider counts it;
    ``cached_input_tokens`` is the part of it served from the prompt cache and
    billed at the cached rate. ``tokens`` is ``input_tokens + output_tokens``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _tokens_add_up(self) -> Usage:
        if self.tokens != self.input_tokens + self.output_tokens:
            raise ValueError("tokens must equal input_tokens + output_tokens")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens must not exceed input_tokens")
        return self

    @classmethod
    def price(
        cls,
        model: str,
        input_tokens: int,
        output_tokens: int,
        rates: Mapping[str, Rate],
        *,
        cached_input_tokens: int = 0,
    ) -> Usage:
        try:
            rate = rates[model]
        except KeyError as exc:
            raise LlmRateError(f"no rate for model {model!r}; known: {sorted(rates)}") from exc
        if cached_input_tokens > input_tokens:
            raise ValueError("cached_input_tokens must not exceed input_tokens")
        uncached = input_tokens - cached_input_tokens
        cost = (
            uncached * rate.input_usd_per_mtok
            + cached_input_tokens * rate.effective_cached_input_usd_per_mtok
            + output_tokens * rate.output_usd_per_mtok
        ) / 1_000_000
        return cls(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            tokens=input_tokens + output_tokens,
            cost_usd=cost,
        )


def rationale_word_count(text: str) -> int:
    return len(text.split())


def clip_rationale(text: str) -> str:
    """Trim free text so it satisfies both rationale caps (words, then characters)."""
    words = text.split()
    if len(words) > RATIONALE_MAX_WORDS:
        text = " ".join(words[:RATIONALE_MAX_WORDS])
    return text[:RATIONALE_MAX_CHARS]


def _check_rationale_words(value: str | None) -> str | None:
    if value is not None and rationale_word_count(value) > RATIONALE_MAX_WORDS:
        raise ValueError(
            f"rationale has {rationale_word_count(value)} words; at most {RATIONALE_MAX_WORDS}"
        )
    return value


class MentionText(BaseModel):
    """One classifier input: the mention id that must round-trip, and its verbatim text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mention_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ClassifyBatch(BaseModel):
    """A classifier call: the frozen system prompt (owned by ``sentiment/``) and the items."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    system: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    brand_hint: str | None = None
    items: list[MentionText] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_distinct(self) -> ClassifyBatch:
        ids = [item.mention_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("mention_id values in a batch must be distinct")
        return self

    @property
    def ids(self) -> list[str]:
        return [item.mention_id for item in self.items]


class LabelObservation(BaseModel):
    """What one model call said about one mention. Code, not the model, decides the label."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mention_id: str = Field(min_length=1)
    status: LabelStatus
    label: SentimentLabel | None = None
    about_brand: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, max_length=RATIONALE_MAX_CHARS)

    @field_validator("rationale")
    @classmethod
    def _rationale_word_cap(cls, value: str | None) -> str | None:
        return _check_rationale_words(value)

    @model_validator(mode="after")
    def _ok_is_complete(self) -> LabelObservation:
        complete = (
            self.label is not None and self.about_brand is not None and self.confidence is not None
        )
        if self.status == "ok" and not complete:
            raise ValueError("status=ok requires label, about_brand and confidence")
        if self.status != "ok" and complete:
            raise ValueError(f"status={self.status} must not carry a complete observation")
        return self

    @classmethod
    def failed(
        cls, mention_id: str, status: LabelStatus, reason: str | None = None
    ) -> LabelObservation:
        clipped = None if reason is None else clip_rationale(reason)
        return cls(mention_id=mention_id, status=status, rationale=clipped)


class LabelAnswer(BaseModel):
    """Wire schema the classifier model must fill for one mention (structured output)."""

    model_config = ConfigDict(extra="forbid")

    mention_id: str
    label: SentimentLabel
    about_brand: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(
        max_length=RATIONALE_MAX_CHARS,
        description=f"At most {RATIONALE_MAX_WORDS} words.",
    )

    @field_validator("rationale")
    @classmethod
    def _rationale_word_cap(cls, value: str) -> str:
        checked = _check_rationale_words(value)
        assert checked is not None
        return checked


class LabelAnswers(BaseModel):
    """Wire schema for a whole classifier batch."""

    model_config = ConfigDict(extra="forbid")

    labels: list[LabelAnswer]


def align_observations(
    batch: ClassifyBatch, answers: Sequence[LabelAnswer]
) -> list[LabelObservation]:
    """Enforce the round-trip rule: batch order, first answer per id wins, missing → unparseable."""
    wanted = set(batch.ids)
    by_id: dict[str, LabelAnswer] = {}
    for answer in answers:
        if answer.mention_id in wanted and answer.mention_id not in by_id:
            by_id[answer.mention_id] = answer
    out: list[LabelObservation] = []
    for mention_id in batch.ids:
        found = by_id.get(mention_id)
        if found is None:
            out.append(LabelObservation.failed(mention_id, "unparseable", "id missing from answer"))
        else:
            out.append(
                LabelObservation(
                    mention_id=mention_id,
                    status="ok",
                    label=found.label,
                    about_brand=found.about_brand,
                    confidence=found.confidence,
                    rationale=found.rationale,
                )
            )
    return out


@dataclass(frozen=True)
class ClassifyResult:
    observations: list[LabelObservation]
    usage: Usage

    def by_id(self) -> dict[str, LabelObservation]:
        return {obs.mention_id: obs for obs in self.observations}


@dataclass(frozen=True)
class JsonResult[T: BaseModel]:
    value: T
    usage: Usage


@dataclass(frozen=True)
class EmbedResult:
    vectors: npt.NDArray[np.float64]
    usage: Usage


@runtime_checkable
class LlmBackend(Protocol):
    """The seam. ``sentiment/``, ``topics/``, ``chat/`` and ``voice/`` see only this."""

    @property
    def rates(self) -> Mapping[str, Rate]: ...

    def classify(self, batch: ClassifyBatch, model: str) -> ClassifyResult: ...

    def complete_json(
        self, system: str, user: str, schema: type[SchemaT], model: str
    ) -> JsonResult[SchemaT]: ...

    def embed(self, texts: Sequence[str], model: str) -> EmbedResult: ...


def render_classify_user_message(batch: ClassifyBatch) -> str:
    """The user turn for a classifier call: brand, hint, and the items as a JSON array."""
    header = f"Brand: {batch.brand}"
    if batch.brand_hint:
        header += f"\nBrand hint: {batch.brand_hint}"
    items = [item.model_dump() for item in batch.items]
    return (
        f"{header}\n\nReturn one entry per mention_id below, every id exactly once.\n\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )


__all__ = [
    "RATES_DATED",
    "RATIONALE_MAX_CHARS",
    "RATIONALE_MAX_WORDS",
    "ClassifyBatch",
    "ClassifyResult",
    "EmbedResult",
    "JsonResult",
    "LabelAnswer",
    "LabelAnswers",
    "LabelObservation",
    "LabelStatus",
    "LlmBackend",
    "LlmError",
    "LlmKind",
    "LlmRateError",
    "LlmRefusal",
    "LlmUnparseable",
    "MentionText",
    "Rate",
    "SentimentLabel",
    "Usage",
    "align_observations",
    "clip_rationale",
    "coerce_rates",
    "load_rates",
    "rationale_word_count",
    "render_classify_user_message",
]
