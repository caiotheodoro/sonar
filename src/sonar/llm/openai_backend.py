"""OpenAI implementation of the seam. The only module in ``sonar`` that imports ``openai``.

Structured output: ``chat.completions.parse`` with the pydantic schema as
``response_format`` so the model is constrained to the schema. Usage is
priced from the rate table at call time. SDK retries default to 4 (Error
matrix: "SDK retries ×4, then excluded with reason").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

import httpx2
import numpy as np
import openai
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

from sonar.llm.base import (
    ClassifyBatch,
    ClassifyResult,
    EmbedResult,
    JsonResult,
    LabelAnswers,
    LabelObservation,
    LlmRefusal,
    LlmUnparseable,
    Rate,
    Usage,
    align_observations,
    load_rates,
    render_classify_user_message,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

DEFAULT_MAX_RETRIES = 4


class OpenAIBackend:
    """Seam implementation over the OpenAI SDK.

    ``http_client`` lets tests plug an ``httpx2.Client`` (the SDK's HTTP stack) with a
    ``MockTransport``;
    no test may reach the network. ``rates`` defaults to ``config.LLM_RATES``.
    """

    def __init__(
        self,
        api_key: str,
        *,
        rates: Mapping[str, Rate] | None = None,
        http_client: httpx2.Client | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._rates: dict[str, Rate] = dict(rates) if rates is not None else load_rates()
        self._client = openai.OpenAI(
            api_key=api_key,
            http_client=http_client,
            max_retries=max_retries,
            base_url=base_url,
            timeout=timeout,
        )

    @property
    def rates(self) -> Mapping[str, Rate]:
        return self._rates

    def _usage(self, model: str, input_tokens: int, output_tokens: int) -> Usage:
        return Usage.price(model, input_tokens, output_tokens, self._rates)

    def classify(self, batch: ClassifyBatch, model: str) -> ClassifyResult:
        # Price the batch even on failure: an unknown model must fail loudly before any call.
        self._usage(model, 0, 0)
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": batch.system},
            {"role": "user", "content": render_classify_user_message(batch)},
        ]
        try:
            completion = self._client.chat.completions.parse(
                model=model, messages=messages, response_format=LabelAnswers, temperature=0.0
            )
        except openai.OpenAIError as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            return ClassifyResult(
                observations=[LabelObservation.failed(i, "error", reason) for i in batch.ids],
                usage=self._usage(model, 0, 0),
            )
        except ValidationError as exc:
            # The SDK raises when the model's JSON does not validate against the schema.
            reason = f"schema validation failed: {str(exc)[:200]}"
            return ClassifyResult(
                observations=[LabelObservation.failed(i, "unparseable", reason) for i in batch.ids],
                usage=self._usage(model, 0, 0),
            )
        usage = self._usage_of(completion.usage, model)
        message = completion.choices[0].message
        if message.refusal:
            reason = f"refused: {message.refusal[:200]}"
            return ClassifyResult(
                observations=[LabelObservation.failed(i, "refused", reason) for i in batch.ids],
                usage=usage,
            )
        parsed = message.parsed
        if parsed is None:
            return ClassifyResult(
                observations=[
                    LabelObservation.failed(i, "unparseable", "no parsed content")
                    for i in batch.ids
                ],
                usage=usage,
            )
        return ClassifyResult(observations=align_observations(batch, parsed.labels), usage=usage)

    def complete_json(
        self, system: str, user: str, schema: type[SchemaT], model: str
    ) -> JsonResult[SchemaT]:
        self._usage(model, 0, 0)
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            completion = self._client.chat.completions.parse(
                model=model, messages=messages, response_format=schema, temperature=0.0
            )
        except ValidationError as exc:
            raise LlmUnparseable(f"{schema.__name__}: {exc}") from exc
        message = completion.choices[0].message
        usage = self._usage_of(completion.usage, model)
        if message.refusal:
            raise LlmRefusal(message.refusal)
        if message.parsed is None:
            raise LlmUnparseable(f"{schema.__name__}: model returned no parsed content")
        return JsonResult(value=message.parsed, usage=usage)

    def embed(self, texts: Sequence[str], model: str) -> EmbedResult:
        self._usage(model, 0, 0)
        if not texts:
            return EmbedResult(
                vectors=np.zeros((0, 0), dtype=np.float64), usage=self._usage(model, 0, 0)
            )
        response = self._client.embeddings.create(
            model=model, input=list(texts), encoding_format="float"
        )
        rows = sorted(response.data, key=lambda d: d.index)
        if len(rows) != len(texts):
            raise LlmUnparseable(f"embeddings: asked for {len(texts)} vectors, got {len(rows)}")
        vectors = np.asarray([row.embedding for row in rows], dtype=np.float64)
        usage = self._usage(model, response.usage.prompt_tokens, 0)
        return EmbedResult(vectors=vectors, usage=usage)

    def _usage_of(self, usage: openai.types.CompletionUsage | None, model: str) -> Usage:
        if usage is None:
            return self._usage(model, 0, 0)
        return self._usage(model, usage.prompt_tokens, usage.completion_tokens)


__all__ = ["DEFAULT_MAX_RETRIES", "OpenAIBackend"]
