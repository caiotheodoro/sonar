"""Sentiment layer: frozen prompt, PT/EN lexicons, batched labeler with cache, two-signal rules.

The model observes; code decides (``rules``). Entry point: ``label_mentions``.
"""

from sonar.sentiment.cache import CACHE_PATH, LabelCache
from sonar.sentiment.labeler import (
    BATCH_SIZE,
    Exclusion,
    LabeledRow,
    Labeler,
    LabelRun,
    label_mentions,
)
from sonar.sentiment.lexicon import Lexicon, load_lexicon
from sonar.sentiment.prompt import CLASSIFIER_SYSTEM, PROMPT_REV, TIEBREAK_SYSTEM

__all__ = [
    "BATCH_SIZE",
    "CACHE_PATH",
    "CLASSIFIER_SYSTEM",
    "PROMPT_REV",
    "TIEBREAK_SYSTEM",
    "Exclusion",
    "LabelCache",
    "LabelRun",
    "LabeledRow",
    "Labeler",
    "Lexicon",
    "label_mentions",
    "load_lexicon",
]
