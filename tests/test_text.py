"""Table-driven tests for the text layer: normalise, lang, match, dedup."""

from __future__ import annotations

import pytest

from sonar.text.dedup import DedupItem, dedup
from sonar.text.lang import detect_lang
from sonar.text.match import match_terms
from sonar.text.normalize import TEXT_KEY_LEN, normalize, normalize_url, text_key

# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    @pytest.mark.parametrize(
        ("input_", "expected"),
        [
            ("Hello World", "hello world"),
            ("  extra   spaces  ", "extra spaces"),
            ("NÃO", "não"),
            ("Café", "café"),
        ],
    )
    def test_unicode_normalization(self, input_: str, expected: str) -> None:
        assert normalize(input_) == expected

    def test_urls_stripped(self) -> None:
        assert "http" not in normalize("see https://example.com/path?q=1 info")

    def test_handles_stripped(self) -> None:
        assert "@" not in normalize("hello @user thanks")

    def test_text_key_truncation(self) -> None:
        long = "word " * 100
        assert len(text_key(long)) == TEXT_KEY_LEN

    def test_text_key_short(self) -> None:
        assert text_key("hi") == normalize("hi")


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------

class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("input_", "expected"),
        [
            ("HTTP://Example.Com/Path/", "http://example.com/Path"),
            ("https://a.com/b?utm_source=x&utm_medium=y&id=1", "https://a.com/b?id=1"),
            ("https://a.com/b?q=hello", "https://a.com/b?q=hello"),
        ],
    )
    def test_url_normalization(self, input_: str, expected: str) -> None:
        assert normalize_url(input_) == expected


# ---------------------------------------------------------------------------
# detect_lang
# ---------------------------------------------------------------------------

_LANG_CASES: list[tuple[str, str]] = [
    # Portuguese
    ("o banco é muito bom e eu gosto dele", "pt"),
    ("não gosto disso de jeito nenhum", "pt"),
    ("ela foi ao mercado e comprou frutas", "pt"),
    ("isso é muito importante para nós", "pt"),
    ("a gente precisa fazer isso agora", "pt"),
    # English
    ("the bank is very good and I like it", "en"),
    ("I do not like this at all", "en"),
    ("she went to the store and bought fruits", "en"),
    ("this is very important for us", "en"),
    ("we need to do this right now", "en"),
    # Unknown (too short)
    ("hello", "unknown"),
    ("banco", "unknown"),
    # Other (mixed/nonsense)
    ("xyzzy foobar baz quux plugh wibble", "other"),
]


class TestDetectLang:
    @pytest.mark.parametrize(("text", "expected"), _LANG_CASES)
    def test_lang_detection(self, text: str, expected: str) -> None:
        assert detect_lang(text) == expected

    def test_ambiguous_picks_dominant(self) -> None:
        text = "the a an o a os is é são i ii iii iv v vi"
        result = detect_lang(text)
        assert result in ("pt", "en")  # dominant language wins


# ---------------------------------------------------------------------------
# match_terms — homonym negatives
# ---------------------------------------------------------------------------

class TestMatchTerms:
    @pytest.mark.parametrize(
        ("text", "terms", "expected"),
        [
            # basic match
            ("Nubank is great", ["Nubank"], ["nubank"]),
            # multi-match
            ("Nubank vs Inter both good", ["Nubank", "Inter"], ["nubank", "inter"]),
            # case-insensitive
            ("NUBANK is the best", ["nubank"], ["nubank"]),
            # no match
            ("something completely different", ["Nubank"], []),
        ],
    )
    def test_basic_matching(self, text: str, terms: list[str], expected: list[str]) -> None:
        assert match_terms(text, terms) == expected

    @pytest.mark.parametrize(
        ("text", "terms", "expected"),
        [
            # "inter" must NOT match inside "internet"
            ("internet is fast", ["inter"], []),
            # "inter" must match as standalone word
            ("I use Inter bank", ["Inter"], ["inter"]),
            # "it" must NOT match inside "bit", "fit", "unit"
            ("unit testing is good", ["it"], []),
            # "it" matches as standalone word
            ("it is a good day", ["it"], ["it"]),
            # "a" must NOT match inside "apple"
            ("apple is a fruit", ["a"], ["a"]),
            # "a" standalone
            ("i ate a banana", ["a"], ["a"]),
            # "ban" must NOT match inside "banco"
            ("banco do brasil", ["ban"], []),
            # "ban" matches standalone
            ("ban this user", ["ban"], ["ban"]),
        ],
    )
    def test_homonym_negatives(self, text: str, terms: list[str], expected: list[str]) -> None:
        assert match_terms(text, terms) == expected

    def test_empty_terms(self) -> None:
        assert match_terms("hello", []) == []


# ---------------------------------------------------------------------------
# dedup
# ---------------------------------------------------------------------------

def _item(
    native_id: str | None = None,
    url: str | None = None,
    text: str = "default text",
    raw_ref: str = "1#0",
    source: str = "reddit",
    brand: str = "Nubank",
) -> DedupItem:
    return DedupItem(
        source=source,
        native_id=native_id,
        url=url,
        text=text,
        raw_ref=raw_ref,
        brand=brand,
    )


class TestDedup:
    def test_native_id_wins_over_url(self) -> None:
        a = _item(native_id="abc", url="https://x.com/1", raw_ref="1#0")
        b = _item(native_id="abc", url="https://x.com/2", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 1
        assert len(result.dropped) == 1
        assert "duplicate native_id" in result.dropped[0][1]

    def test_url_wins_over_text(self) -> None:
        a = _item(url="https://example.com/post", raw_ref="1#0")
        b = _item(url="https://example.com/post", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 1

    def test_text_key_wins(self) -> None:
        a = _item(text="same text here", raw_ref="1#0")
        b = _item(text="same text here", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 1

    def test_different_sources_not_deduped(self) -> None:
        a = _item(native_id="abc", source="reddit", raw_ref="1#0")
        b = _item(native_id="abc", source="youtube", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 2

    def test_lower_raw_ref_wins(self) -> None:
        a = _item(url="https://example.com/x", raw_ref="2#0")
        b = _item(url="https://example.com/x", raw_ref="1#0")
        result = dedup([a, b])
        assert len(result.kept) == 1
        assert result.kept[0].raw_ref == "1#0"

    def test_empty_input(self) -> None:
        result = dedup([])
        assert result.kept == []
        assert result.dropped == []
