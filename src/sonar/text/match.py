"""Word-boundary alias matching for brand and competitor terms."""

from __future__ import annotations

import re
from collections.abc import Sequence

from sonar.text.normalize import normalize


def _build_pattern(terms: Sequence[str]) -> re.Pattern[str]:
    """Build a compiled regex matching any term at word boundaries."""
    escaped = [re.escape(normalize(t)) for t in terms]
    pattern = r"(?:^|(?<=\s)|(?<=\b))(" + "|".join(escaped) + r")(?:\s|$|(?=\b))"
    return re.compile(pattern, re.IGNORECASE)


def match_terms(text: str, terms: Sequence[str]) -> list[str]:
    """Return the normalised terms found in *text* at word boundaries.

    Substring matches inside other words (e.g. 'inter' inside 'internet')
    are rejected by the word-boundary anchors.
    """
    if not terms:
        return []
    norm = normalize(text)
    pattern = _build_pattern(terms)
    hits = pattern.findall(norm)
    # deduplicate preserving first-seen order
    seen: set[str] = set()
    result: list[str] = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            result.append(h)
    return result
