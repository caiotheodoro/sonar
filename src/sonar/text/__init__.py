"""Deterministic text layer: normalise, detect language, match aliases, dedup."""

from sonar.text.dedup import DedupItem, DedupResult, dedup
from sonar.text.lang import detect_lang
from sonar.text.match import match_terms
from sonar.text.normalize import TEXT_KEY_LEN, normalize, normalize_url, text_key

__all__ = [
    "TEXT_KEY_LEN",
    "DedupItem",
    "DedupResult",
    "dedup",
    "detect_lang",
    "match_terms",
    "normalize",
    "normalize_url",
    "text_key",
]
