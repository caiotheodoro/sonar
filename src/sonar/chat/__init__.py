"""Chat layer (W5.2): store, retrieval, gates, ``ask`` and the REPL behind ``sonar ask``."""

from sonar.chat.ask import (
    MAX_ATTEMPTS,
    SYSTEM_PROMPT,
    AnswerSchema,
    AskResult,
    append_answer,
    ask,
    read_answers,
    render_answer,
)
from sonar.chat.command import cmd_ask, register
from sonar.chat.gates import (
    CitationsGate,
    NumbersGate,
    available_numbers,
    citations_gate,
    clean_for_numbers,
    extract_numbers,
    numbers_gate,
    strip_citations,
)
from sonar.chat.retrieve import Retrieval, retrieve
from sonar.chat.store import ANSWERS_JSONL, EMBEDDINGS_NPY, SessionStore, StoreError

__all__ = [
    "ANSWERS_JSONL",
    "EMBEDDINGS_NPY",
    "MAX_ATTEMPTS",
    "SYSTEM_PROMPT",
    "AnswerSchema",
    "AskResult",
    "CitationsGate",
    "NumbersGate",
    "Retrieval",
    "SessionStore",
    "StoreError",
    "append_answer",
    "ask",
    "available_numbers",
    "citations_gate",
    "clean_for_numbers",
    "cmd_ask",
    "extract_numbers",
    "numbers_gate",
    "read_answers",
    "register",
    "render_answer",
    "retrieve",
    "strip_citations",
]
