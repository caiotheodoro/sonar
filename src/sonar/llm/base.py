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

Only ``openai_backend.py`` imports ``openai``. Label and status vocabularies
below mirror CONTRACTS §Enumerations; ``models.py`` (W2.1) owns the full
records, this module owns only the observation the model returns.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol, TypeVar, runtime_checkable

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, model_validator

SentimentLabel = Literal["positive", "negative", "neutral", "irrelevant"]
LabelStatus = Literal["ok", "refused", "unparseable", "error"]
LlmKind = Literal["classify", "tiebreak", "embed", "name_topic", "narrate", "ask"]

SchemaT = TypeVar("SchemaT", bound=BaseModel)

RATES_DATED = date(2026, 9, 2)
RATIONALE_MAX_CHARS = 200
"""Date the fallback price table below was read from OpenAI pricing."""

FALLBACK_RATES: Mapping[str, Rate]
"""Used only when ``sonar.config.LLM_RATES`` cannot be imported (Wave 2 build order)."""


class LlmError(RuntimeError):
    """Base class for seam errors that are not per-id statuses."""


class LlmRateError(LlmError):
    """No price is known for the requested model; cost cannot be reported."""


class LlmRefusal(LlmError):
    """The model refused a ``complete_json`` request."""


class LlmUnparseable(LlmError):
    """The model's ``complete_json`` output did not validate against the schema."""


class Rate(BaseModel):
    """USD per million tokens for one model id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_usd_per_mtok: float = Field(ge=0.0)
    output_usd_per_mtok: float = Field(ge=0.0)
    dated: date = RATES_DATED


FALLBACK_RATES = {
    "gpt-5.6-luna": Rate(input_usd_per_mtok=0.20, output_usd_per_mtok=1.20),
    "gpt-5.6-terra": Rate(input_usd_per_mtok=2.00, output_usd_per_mtok=12.00),
    "text-embedding-3-small": Rate(input_usd_per_mtok=0.02, output_usd_per_mtok=0.0),
}

_INPUT_KEYS = ("input_usd_per_mtok", "input_per_mtok", "input", "prompt")
_OUTPUT_KEYS = ("output_usd_per_mtok", "output_per_mtok", "output", "completion")


def coerce_rates(raw: Mapping[str, object]) -> dict[str, Rate]:
    """Normalise a ``config.LLM_RATES``-shaped table into ``Rate`` records.

    Accepts ``Rate`` instances, ``(input, output)`` pairs, or mappings whose
    input/output keys are any of ``input_usd_per_mtok``/``input``/``prompt``
    and ``output_usd_per_mtok``/``output``/``completion`` (USD per MTok). An
    optional ``dated`` key (``date`` or ISO string) is carried through.
    """
    out: dict[str, Rate] = {}
    for model, value in raw.items():
        if isinstance(value, Rate):
            out[model] = value
        elif hasattr(value, "input_usd_per_mtok") and hasattr(value, "output_usd_per_mtok"):
            # ``config.LlmRate`` (a frozen dataclass) or any object with the two attributes.
            out[model] = Rate(
                input_usd_per_mtok=float(value.input_usd_per_mtok),
                output_usd_per_mtok=float(value.output_usd_per_mtok),
            )
        elif isinstance(value, Mapping):
            out[model] = _rate_from_mapping(model, value)
        elif isinstance(value, Sequence) and not isinstance(value, str) and len(value) == 2:
            out[model] = Rate(
                input_usd_per_mtok=float(value[0]),
                output_usd_per_mtok=float(value[1]),
            )
        else:
            raise LlmRateError(f"unrecognised rate entry for {model!r}: {value!r}")
    return out


def _rate_from_mapping(model: str, value: Mapping[object, object]) -> Rate:
    def pick(keys: tuple[str, ...]) -> float:
        for key in keys:
            if key in value:
                return float(value[key])  # type: ignore[arg-type]
        raise LlmRateError(f"rate for {model!r} has none of {keys}: {sorted(map(str, value))}")

    dated_raw = value.get("dated")
    dated = (
        date.fromisoformat(dated_raw)
        if isinstance(dated_raw, str)
        else dated_raw
        if isinstance(dated_raw, date)
        else RATES_DATED
    )
    return Rate(
        input_usd_per_mtok=pick(_INPUT_KEYS), output_usd_per_mtok=pick(_OUTPUT_KEYS), dated=dated
    )


def load_rates() -> dict[str, Rate]:
    """``sonar.config.LLM_RATES`` when importable, else ``FALLBACK_RATES``."""
    try:
        config = importlib.import_module("sonar.config")
        raw = config.LLM_RATES
    except (ImportError, AttributeError):
        return dict(FALLBACK_RATES)
    if not isinstance(raw, Mapping):
        raise LlmRateError(f"sonar.config.LLM_RATES is {type(raw).__name__}, expected a mapping")
    return coerce_rates(raw)


class Usage(BaseModel):
    """Tokens and cost of one seam call, priced from the rate table at call time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _tokens_add_up(self) -> Usage:
        if self.tokens != self.input_tokens + self.output_tokens:
            raise ValueError("tokens must equal input_tokens + output_tokens")
        return self

    @classmethod
    def price(
        cls, model: str, input_tokens: int, output_tokens: int, rates: Mapping[str, Rate]
    ) -> Usage:
        try:
            rate = rates[model]
        except KeyError as exc:
            raise LlmRateError(f"no rate for model {model!r}; known: {sorted(rates)}") from exc
        cost = (
            input_tokens * rate.input_usd_per_mtok + output_tokens * rate.output_usd_per_mtok
        ) / 1_000_000
        return cls(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens=input_tokens + output_tokens,
            cost_usd=cost,
        )


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
        clipped = None if reason is None else reason[:RATIONALE_MAX_CHARS]
        return cls(mention_id=mention_id, status=status, rationale=clipped)


class LabelAnswer(BaseModel):
    """Wire schema the classifier model must fill for one mention (structured output)."""

    model_config = ConfigDict(extra="forbid")

    mention_id: str
    label: SentimentLabel
    about_brand: bool
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=RATIONALE_MAX_CHARS)


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
    "FALLBACK_RATES",
    "RATES_DATED",
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
    "coerce_rates",
    "load_rates",
    "render_classify_user_message",
]
