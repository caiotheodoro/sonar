"""PT and EN sentiment lexicons: the deterministic signal for non-review sources.

CONTRACTS §Label ``Signals.deterministic``: ``kind=lexicon`` carries the sign
of the PT/EN lexicon score (``label=null`` when the score is 0);
``kind=none`` when there is no hit at all. Language is never used to filter
(Pipeline rules), so both lexicons are always applied together.

The word lists live beside this module as ``lexicon_pt.txt`` and
``lexicon_en.txt``: one entry per line, polarity (``+`` or ``-``), a tab,
then the term. Matching is on ``sonar.text.normalize`` output at word
boundaries. Multi-word entries take precedence over their sub-words because
the alternation is ordered longest first and the scan consumes each match,
so ``não recomendo`` scores once as negative and never again as
``recomendo``; negation is therefore carried by the phrase list, not by a
window heuristic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Final, Literal

from sonar.models import Polarity
from sonar.text.normalize import normalize

LexiconLang = Literal["pt", "en"]

LEXICON_FILES: Final[Mapping[LexiconLang, str]] = {"pt": "lexicon_pt.txt", "en": "lexicon_en.txt"}
_POLARITY_MARKS: Final[Mapping[str, int]] = {"+": 1, "-": -1}


class LexiconError(ValueError):
    """A lexicon file is malformed or two files disagree on a term's polarity."""


@dataclass(frozen=True)
class LexiconHit:
    term: str
    polarity: int


@dataclass(frozen=True)
class LexiconScore:
    """Hits found in one text; ``score`` is positive hits minus negative hits."""

    hits: tuple[LexiconHit, ...]

    @property
    def score(self) -> int:
        return sum(hit.polarity for hit in self.hits)

    @property
    def n_hits(self) -> int:
        return len(self.hits)

    @property
    def sign(self) -> Polarity | None:
        """``positive``/``negative`` by the sign of ``score``; ``None`` when it is 0."""
        if self.score > 0:
            return "positive"
        if self.score < 0:
            return "negative"
        return None


class Lexicon:
    """A merged term → polarity table with a compiled word-boundary matcher."""

    def __init__(self, entries: Mapping[str, int]) -> None:
        if not entries:
            raise LexiconError("a lexicon needs at least one entry")
        self._entries: dict[str, int] = dict(entries)
        ordered = sorted(self._entries, key=lambda term: (-len(term), term))
        alternation = "|".join(re.escape(term) for term in ordered)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")

    @property
    def entries(self) -> Mapping[str, int]:
        return self._entries

    def score(self, text: str) -> LexiconScore:
        found = self._pattern.findall(normalize(text))
        return LexiconScore(hits=tuple(LexiconHit(term, self._entries[term]) for term in found))

    def sign(self, text: str) -> Polarity | None:
        return self.score(text).sign


def parse_lexicon_lines(lines: Iterable[str], *, origin: str = "<lines>") -> dict[str, int]:
    """Parse ``polarity<TAB>term`` lines; ``#`` comments and blank lines are skipped.

    Terms are normalised the same way the text will be; a term that appears
    twice with different polarities is an error, because the sign would then
    depend on file order.
    """
    out: dict[str, int] = {}
    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        mark, sep, term = line.partition("\t")
        if not sep or mark not in _POLARITY_MARKS:
            raise LexiconError(
                f"{origin}:{lineno}: expected '+<TAB>term' or '-<TAB>term', got {raw!r}"
            )
        key = normalize(term)
        if not key:
            raise LexiconError(f"{origin}:{lineno}: empty term")
        polarity = _POLARITY_MARKS[mark]
        if key in out and out[key] != polarity:
            raise LexiconError(f"{origin}:{lineno}: {key!r} listed with both polarities")
        out[key] = polarity
    return out


def load_lexicon_file(lang: LexiconLang) -> dict[str, int]:
    name = LEXICON_FILES[lang]
    text = resources.files("sonar.sentiment").joinpath(name).read_text(encoding="utf-8")
    return parse_lexicon_lines(text.splitlines(), origin=name)


def merge_entries(tables: Iterable[Mapping[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for table in tables:
        for term, polarity in table.items():
            if term in merged and merged[term] != polarity:
                raise LexiconError(f"{term!r} has opposite polarity in two lexicon files")
            merged[term] = polarity
    return merged


@cache
def load_lexicon() -> Lexicon:
    """The merged PT+EN lexicon shipped with the package, parsed once per process."""
    return Lexicon(merge_entries(load_lexicon_file(lang) for lang in LEXICON_FILES))


__all__ = [
    "LEXICON_FILES",
    "Lexicon",
    "LexiconError",
    "LexiconHit",
    "LexiconLang",
    "LexiconScore",
    "load_lexicon",
    "load_lexicon_file",
    "merge_entries",
    "parse_lexicon_lines",
]
