"""Table-driven tests for the text layer: normalise, lang, match, dedup."""

from __future__ import annotations

import pytest

from sonar.models import EXCLUSION_REASONS
from sonar.text.dedup import DEDUP_REASONS, DedupItem, dedup
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

    def test_mixed_both_above_threshold_is_other(self) -> None:
        # Both PT and EN stopword ratios exceed 0.10 with equal hits (6 vs 6):
        # neither dominates, so neither language is reported.
        text = "the a an o a os is é são i ii iii iv v vi"
        assert detect_lang(text) == "other"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Both above 0.10; PT hits (a, isso, e = 3) are 3x EN hits (a = 1).
            ("a gente precisa fazer isso agora e", "pt"),
            # Both above 0.10; PT hits (a, isso = 2) are exactly 2x EN hits (a = 1).
            ("a gente precisa fazer isso agora", "pt"),
            # Both above 0.10; EN hits (i, do, not, this, at, all = 6) dwarf PT ("do" = 1).
            ("I do not like this at all", "en"),
            # Both above 0.10; PT hits (o, a, os, a = 4) vs EN hits (the, a, a = 3): under 2x.
            ("the o a os a xx yy zz", "other"),
        ],
    )
    def test_both_above_threshold_dominance(self, text: str, expected: str) -> None:
        assert detect_lang(text) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            # Mostly PT with a single EN stopword (1/11 ≈ 0.09, below threshold).
            ("o banco é muito bom e eu gosto dele mesmo the", "pt"),
            # Mostly EN with a single PT stopword (1/10 = 0.10, not above threshold).
            ("the bank is very good and we like it muito", "en"),
        ],
    )
    def test_one_sided_minor_contamination_keeps_dominant(self, text: str, expected: str) -> None:
        assert detect_lang(text) == expected


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
        assert result.dropped == [(b, "dedup_native_id", "1#0")]

    def test_url_wins_over_text(self) -> None:
        a = _item(url="https://example.com/post", text="one", raw_ref="1#0")
        b = _item(url="https://example.com/post?utm_source=x", text="two", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 1
        assert result.dropped == [(b, "dedup_url", "1#0")]

    def test_text_key_wins(self) -> None:
        a = _item(text="same text here", raw_ref="1#0")
        b = _item(text="Same   TEXT here", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 1
        assert result.dropped == [(b, "dedup_text", "1#0")]

    def test_reasons_are_receipt_exclusion_keys(self) -> None:
        # CONTRACTS §Receipt: excluded_with_reason keys are a closed set (F22).
        assert set(DEDUP_REASONS) == {"dedup_native_id", "dedup_url", "dedup_text"}
        assert set(DEDUP_REASONS) <= EXCLUSION_REASONS

    def test_different_sources_not_deduped(self) -> None:
        a = _item(native_id="abc", source="reddit", raw_ref="1#0")
        b = _item(native_id="abc", source="youtube", raw_ref="2#0")
        result = dedup([a, b])
        assert len(result.kept) == 2

    @pytest.mark.parametrize(
        ("kwargs_a", "kwargs_b"),
        [
            ({"native_id": "abc"}, {"native_id": "abc"}),
            ({"url": "https://x.com/p"}, {"url": "https://x.com/p"}),
            ({"text": "same text here"}, {"text": "same text here"}),
        ],
    )
    def test_same_mention_two_brands_kept_once_per_brand(
        self, kwargs_a: dict[str, str], kwargs_b: dict[str, str]
    ) -> None:
        # CONTRACTS §Dedup precedence: a mention matching the brand and a
        # competitor is kept once per brand (two rows, one mention_id).
        a = _item(brand="Nubank", raw_ref="1#0", **kwargs_a)
        b = _item(brand="Inter", raw_ref="1#0", **kwargs_b)
        result = dedup([a, b])
        assert result.kept == [a, b]
        assert result.dropped == []

    def test_same_brand_still_deduped_alongside_other_brand(self) -> None:
        a = _item(native_id="abc", brand="Nubank", raw_ref="1#0")
        b = _item(native_id="abc", brand="Nubank", raw_ref="2#0")
        c = _item(native_id="abc", brand="Inter", raw_ref="2#0")
        result = dedup([a, b, c])
        assert result.kept == [a, c]
        assert result.dropped == [(b, "dedup_native_id", "1#0")]

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
