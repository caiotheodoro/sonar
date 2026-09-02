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

_LANG_RATIOS = {
    "pt": _PT_STOPWORDS,
    "en": _EN_STOPWORDS,
}


def detect_lang(text: str) -> str:
    """Return 'pt', 'en', 'other', or 'unknown'.

    Ratio = count of stopwords in text / total word count.
    Above 0.10 → that language; both above 0.10 → 'other';
    fewer than 5 words → 'unknown'.
    """
    words = _WORD_RE.findall(normalize(text))
    if len(words) < 5:
        return "unknown"
    pt_hits = sum(1 for w in words if w in _PT_STOPWORDS)
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    pt_ratio = pt_hits / len(words)
    en_ratio = en_hits / len(words)
    if pt_ratio > 0.10 and en_ratio > 0.10:
        # Both above threshold — pick the dominant one
        return "pt" if pt_ratio >= en_ratio else "en"
    if pt_ratio > 0.10:
        return "pt"
    if en_ratio > 0.10:
        return "en"
    return "other"
