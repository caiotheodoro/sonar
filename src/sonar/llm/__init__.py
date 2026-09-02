"""The LLM seam: ``LlmBackend`` protocol, OpenAI backend, replaying fake.

``sonar.llm`` re-exports the protocol and records only; import the backend
from ``sonar.llm.openai_backend`` (the sole ``openai`` importer) and the fake
from ``sonar.llm.fake``.
"""

from sonar.llm.base import (
    ClassifyBatch,
    ClassifyResult,
    EmbedResult,
    JsonResult,
    LabelObservation,
    LlmBackend,
    LlmError,
    LlmRateError,
    LlmRefusal,
    LlmUnparseable,
    MentionText,
    Rate,
    Usage,
    load_rates,
)

__all__ = [
    "ClassifyBatch",
    "ClassifyResult",
    "EmbedResult",
    "JsonResult",
    "LabelObservation",
    "LlmBackend",
    "LlmError",
    "LlmRateError",
    "LlmRefusal",
    "LlmUnparseable",
    "MentionText",
    "Rate",
    "Usage",
    "load_rates",
]
