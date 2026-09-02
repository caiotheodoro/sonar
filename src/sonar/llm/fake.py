"""Replaying fake for the seam. No network, no ``openai`` import.

* ``classify``: answers from a labels fixture keyed by ``mention_id``; an id
  with no fixture entry follows the same round-trip rule as the backend and
  comes back ``unparseable``. A fixture entry may carry a failure ``status``.
* ``complete_json``: canned answers keyed by schema class name.
* ``embed``: deterministic unit vectors seeded from the text (same text, same
  vector, across processes).
* ``calls``: call count per model, and per ``(kind, model)``, so tests can
  assert tiebreak volume (the tiebreak model's classify count).

Tokens are counted as whitespace words so cost is nonzero and reproducible.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeVar

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sonar.llm.base import (
    ClassifyBatch,
    ClassifyResult,
    EmbedResult,
    JsonResult,
    LabelAnswer,
    LabelObservation,
    LabelStatus,
    LlmRefusal,
    LlmUnparseable,
    Rate,
    SentimentLabel,
    Usage,
    align_observations,
    load_rates,
    render_classify_user_message,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

DEFAULT_DIM = 32


class LabelFixtureEntry(BaseModel):
    """One row of ``tests/fixtures/labels.json``: the canned answer for a mention id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: LabelStatus = "ok"
    label: SentimentLabel | None = None
    about_brand: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = ""


class LabelsFixture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    labels: dict[str, LabelFixtureEntry]


def load_labels_fixture(path: Path) -> dict[str, LabelFixtureEntry]:
    return LabelsFixture.model_validate_json(path.read_text(encoding="utf-8")).labels


def word_tokens(*texts: str) -> int:
    return sum(len(text.split()) for text in texts)


def deterministic_vector(text: str, dim: int) -> npt.NDArray[np.float64]:
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim)
    unit: npt.NDArray[np.float64] = vec / np.linalg.norm(vec)
    return unit


class FakeBackend:
    """Seam implementation that replays fixtures and counts calls."""

    def __init__(
        self,
        labels: Mapping[str, LabelFixtureEntry] | None = None,
        *,
        answers: Mapping[str, Mapping[str, object] | BaseModel] | None = None,
        rates: Mapping[str, Rate] | None = None,
        dim: int = DEFAULT_DIM,
    ) -> None:
        self._labels: dict[str, LabelFixtureEntry] = dict(labels or {})
        self._answers: dict[str, Mapping[str, object] | BaseModel] = dict(answers or {})
        self._rates: dict[str, Rate] = dict(rates) if rates is not None else load_rates()
        self._dim = dim
        self.calls: Counter[str] = Counter()
        self.calls_by_kind: Counter[tuple[str, str]] = Counter()
        self.batches: list[tuple[str, list[str]]] = []

    @classmethod
    def from_fixture(
        cls,
        path: Path,
        *,
        answers: Mapping[str, Mapping[str, object] | BaseModel] | None = None,
        rates: Mapping[str, Rate] | None = None,
        dim: int = DEFAULT_DIM,
    ) -> FakeBackend:
        return cls(load_labels_fixture(path), answers=answers, rates=rates, dim=dim)

    @property
    def rates(self) -> Mapping[str, Rate]:
        return self._rates

    def _record(self, kind: str, model: str) -> None:
        self.calls[model] += 1
        self.calls_by_kind[(kind, model)] += 1

    def classify(self, batch: ClassifyBatch, model: str) -> ClassifyResult:
        Usage.price(model, 0, 0, self._rates)
        self._record("classify", model)
        self.batches.append((model, batch.ids))
        answers: list[LabelAnswer] = []
        failures: dict[str, LabelObservation] = {}
        for item in batch.items:
            entry = self._labels.get(item.mention_id)
            if entry is None:
                continue
            if entry.status != "ok":
                failures[item.mention_id] = LabelObservation.failed(
                    item.mention_id, entry.status, entry.rationale or None
                )
                continue
            if entry.label is None or entry.about_brand is None or entry.confidence is None:
                raise ValueError(f"fixture entry {item.mention_id!r} is status=ok but incomplete")
            answers.append(
                LabelAnswer(
                    mention_id=item.mention_id,
                    label=entry.label,
                    about_brand=entry.about_brand,
                    confidence=entry.confidence,
                    rationale=entry.rationale,
                )
            )
        observations = [
            failures.get(obs.mention_id, obs) for obs in align_observations(batch, answers)
        ]
        input_tokens = word_tokens(batch.system, render_classify_user_message(batch))
        output_tokens = 12 * len(batch.items)
        return ClassifyResult(
            observations=observations,
            usage=Usage.price(model, input_tokens, output_tokens, self._rates),
        )

    def complete_json(
        self, system: str, user: str, schema: type[SchemaT], model: str
    ) -> JsonResult[SchemaT]:
        Usage.price(model, 0, 0, self._rates)
        self._record(schema.__name__, model)
        canned = self._answers.get(schema.__name__)
        if canned is None:
            raise LlmUnparseable(f"fake has no canned answer for schema {schema.__name__!r}")
        if isinstance(canned, Mapping) and canned.get("__refusal__"):
            raise LlmRefusal(str(canned["__refusal__"]))
        try:
            value = (
                schema.model_validate(canned.model_dump())
                if isinstance(canned, BaseModel)
                else schema.model_validate(dict(canned))
            )
        except ValidationError as exc:
            raise LlmUnparseable(f"{schema.__name__}: {exc}") from exc
        output_tokens = word_tokens(json.dumps(value.model_dump(mode="json")))
        return JsonResult(
            value=value,
            usage=Usage.price(model, word_tokens(system, user), output_tokens, self._rates),
        )

    def embed(self, texts: Sequence[str], model: str) -> EmbedResult:
        Usage.price(model, 0, 0, self._rates)
        self._record("embed", model)
        if not texts:
            vectors = np.zeros((0, self._dim), dtype=np.float64)
        else:
            vectors = np.stack([deterministic_vector(t, self._dim) for t in texts]).astype(
                np.float64
            )
        return EmbedResult(
            vectors=vectors, usage=Usage.price(model, word_tokens(*texts), 0, self._rates)
        )


__all__ = [
    "DEFAULT_DIM",
    "FakeBackend",
    "LabelFixtureEntry",
    "LabelsFixture",
    "deterministic_vector",
    "load_labels_fixture",
    "word_tokens",
]
