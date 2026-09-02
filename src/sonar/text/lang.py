"""Language detection by stopword ratio: pt, en, other, or unknown."""

from __future__ import annotations

import re

from sonar.text.normalize import normalize

_WORD_RE = re.compile(r"[a-zà-ú]+")

_PT_STOPWORDS: frozenset[str] = frozenset({
    "a", "à", "ao", "aos", "as", "até", "com", "como", "da", "das", "de",
    "del", "dem", "depois", "do", "dos", "e", "é", "em", "entre", "era",
    "essa", "esse", "esta", "este", "eu", "foi", "isso", "isto", "já",
    "lhe", "lhes", "lo", "mais", "mas", "me", "meu", "meus", "minha",
    "minhas", "muito", "na", "nas", "não", "nem", "no", "nos", "num",
    "numa", "o", "os", "ou", "para", "pela", "pelas", "pelo", "pelos",
    "por", "qual", "quando", "que", "quem", "se", "sem", "ser", "seu",
    "seus", "sua", "suas", "são", "também", "te", "teu", "teus", "tu",
    "tua", "tuas", "um", "uma", "uns", "umas", "você", "vocês",
})

_EN_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "it", "its", "he", "she", "they", "them", "his", "her", "their",
    "this", "that", "these", "those", "i", "you", "we", "my", "your",
    "our", "not", "no", "so", "if", "then", "than", "too", "very",
    "just", "about", "above", "after", "again", "all", "also", "any",
    "because", "before", "between", "both", "each", "few", "more",
    "most", "other", "some", "such", "into", "only", "own", "same",
    "up", "out", "down", "off", "over", "under", "further", "once",
    "here", "there", "when", "where", "why", "how", "what", "which",
    "who", "whom",
})

DOMINANCE_FACTOR = 2
"""When both ratios exceed 0.10, a language wins only with this many times the other's hits."""


def detect_lang(text: str) -> str:
    """Return 'pt', 'en', 'other', or 'unknown'.

    Ratio = count of stopwords in text / total word count.
    Fewer than 5 words → 'unknown'. Exactly one ratio above 0.10 → that
    language. Both above 0.10 → the dominant language, where dominant means
    at least `DOMINANCE_FACTOR` times the other's stopword hits (words such
    as "a" and "do" sit in both lists, so short sentences routinely trip
    both thresholds); neither dominates → 'other'. Neither above 0.10 →
    'other'.
    """
    words = _WORD_RE.findall(normalize(text))
    if len(words) < 5:
        return "unknown"
    pt_hits = sum(1 for w in words if w in _PT_STOPWORDS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    pt_ratio = pt_hits / len(words)
    en_ratio = en_hits / len(words)
    if pt_ratio > 0.10 and en_ratio > 0.10:
        if pt_hits >= DOMINANCE_FACTOR * en_hits:
            return "pt"
        if en_hits >= DOMINANCE_FACTOR * pt_hits:
            return "en"
        # Genuinely mixed text: report neither language rather than guess.
        return "other"
    if pt_ratio > 0.10:
        return "pt"
    if en_ratio > 0.10:
        return "en"
    return "other"
