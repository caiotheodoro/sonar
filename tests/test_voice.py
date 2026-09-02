"""Tests for the voice layer: script, numbers gate, and TTS stub.

Uses the fake LLM backend and a stub ElevenLabs adapter.  No network, no
real model calls.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from sonar import config
from sonar.llm.base import JsonResult, LlmUnparseable, Rate, Usage
from sonar.llm.fake import FakeBackend
from sonar.models import (
    Abstention,
    BySourceEntry,
    CostQuote,
    CoverageGap,
    DateRange,
    Digest,
    Narration,
    SentimentEntry,
    SovEntry,
    Topic,
    TopicMethod,
    TopMention,
    Totals,
    Window,
    WowNet,
    WowShare,
)
from sonar.voice.script import (
    NarrationSchema,
    _digest_numbers,
    _extract_numbers,
    generate_narration,
    numbers_gate,
)
from sonar.voice.tts import synthesize_narration

# ---------------------------------------------------------------------------
# Sequential-answer wrapper for FakeBackend (list of canned answers)
# ---------------------------------------------------------------------------


class _SequentialFake:
    """Wraps FakeBackend so ``complete_json`` returns answers from a list in order."""

    def __init__(
        self,
        answers: list[dict[str, Any]],
        rates: Mapping[str, Rate] | None = None,
    ) -> None:
        self._answers = list(answers)
        self._index = 0
        self._inner = FakeBackend(rates=rates)
        self.calls = self._inner.calls
        self.calls_by_kind = self._inner.calls_by_kind

    @property
    def rates(self) -> Mapping[str, Rate]:
        return self._inner.rates

    def classify(self, batch: Any, model: str) -> Any:
        return self._inner.classify(batch, model)

    def complete_json(
        self, system: str, user: str, schema: type, model: str
    ) -> JsonResult[Any]:
        Usage.price(model, 0, 0, self._inner._rates)
        self._inner._record(schema.__name__, model)
        if self._index >= len(self._answers):
            raise LlmUnparseable(f"no more canned answers for {schema.__name__!r}")
        canned = self._answers[self._index]
        self._index += 1
        value = schema.model_validate(canned)
        output_tokens = len(value.model_dump_json()) // 4
        return JsonResult(
            value=value,
            usage=Usage.price(model, len(system) + len(user), output_tokens, self._inner._rates),
        )

    def embed(self, texts: Any, model: str) -> Any:
        return self._inner.embed(texts, model)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)


def _make_digest(*, brand: str = "Nubank", cost_total: float = 0.42) -> Digest:
    """Build a minimal valid Digest for testing."""
    start = _now() - timedelta(days=7)
    end = _now()
    prev_start = start - timedelta(days=7)
    prev_end = start

    window = Window(
        current=DateRange(start=start, end=end),
        previous=DateRange(start=prev_start, end=prev_end),
    )

    wow_share = WowShare(
        delta=0.05,
        ci95=(0.01, 0.09),
        verdict="SUGGESTIVE",
        p_raw=0.03,
        p_holm=0.06,
    )
    sov_entry = SovEntry(
        brand=brand,
        n=30,
        n_clusters=10,
        share=0.6,
        ci95=(0.5, 0.7),
        basis_sources=["reddit", "google_maps"],
        wow=wow_share,
    )
    comp_wow = WowShare(
        delta=None, ci95=None, verdict="ABSTAIN", p_raw=None, p_holm=None
    )
    comp_sov = SovEntry(
        brand="Inter",
        n=10,
        n_clusters=5,
        share=0.2,
        ci95=(0.1, 0.3),
        basis_sources=["reddit", "google_maps"],
        wow=comp_wow,
    )

    wow_net = WowNet(
        delta=0.1,
        ci95=(-0.05, 0.25),
        ci95_confirmed_only=(-0.03, 0.20),
        verdict="NO_CHANGE_DETECTED",
        p_raw=0.15,
        p_holm=0.30,
    )
    sent = SentimentEntry(
        brand=brand,
        n=30,
        n_confirmed=20,
        pos=15,
        neg=5,
        neu=10,
        net=0.5,
        ci95=(0.2, 0.8),
        ci95_iid=(0.25, 0.75),
        design_effect=1.44,
        wow=wow_net,
    )
    comp_net = WowNet(
        delta=None, ci95=None, ci95_confirmed_only=None,
        verdict="ABSTAIN", p_raw=None, p_holm=None,
    )
    comp_sent = SentimentEntry(
        brand="Inter",
        n=10,
        n_confirmed=5,
        pos=4,
        neg=3,
        neu=3,
        net=0.1,
        ci95=(-0.3, 0.5),
        ci95_iid=(-0.3, 0.5),
        design_effect=1.0,
        wow=comp_net,
    )

    by_source = BySourceEntry(
        brand=brand,
        source="reddit",
        n=20,
        n_clusters=8,
        pos=10,
        neg=3,
        neu=7,
        net=0.43,
        ci95=(0.1, 0.7),
        ci95_iid=(0.1, 0.7),
        design_effect=1.0,
        wow_scope=True,
    )

    topic = Topic(
        topic_id=f"{brand.lower()}-00",
        brand=brand,
        name="Customer complaints",
        n=15,
        n_clusters=6,
        share=0.5,
        net=0.3,
        ci95=(0.0, 0.6),
        exemplar_mention_ids=["a" * 24, "b" * 24, "c" * 24],
        method=TopicMethod(
            embedding_model="text-embedding-3-small",
            linkage="average",
            threshold=config.TOPIC_DISTANCE_THRESHOLD,
            min_size=3,
            min_breadth=2,
        ),
    )

    top_mention = TopMention(
        mention_id="d" * 24,
        brand=brand,
        source="reddit",
        url="https://reddit.com/r/nubank/test",
        quote="Great app experience overall",
        lang="en",
        label="positive",
        published_at=_now(),
        engagement_score=42,
    )

    totals = Totals(
        monid_usd=cost_total,
        monid_runs=2,
        monid_runs_billed=1,
        monid_runs_zero_results=0,
        monid_runs_failed=0,
        llm_usd=0.10,
        llm_calls={"classify": 1},
        llm_tokens=500,
        elevenlabs_usd=0.05,
        total_usd=cost_total + 0.10,
    )

    return Digest(
        brand=brand,
        competitors=["Inter"],
        window=window,
        share_of_voice=[sov_entry, comp_sov],
        sentiment=[sent, comp_sent],
        by_source=[by_source],
        topics=[topic],
        events=[],
        top_mentions=[top_mention],
        abstentions=[
            Abstention(
                scope="brand", brand="Inter", source=None,
                reason="below_minimum", detail="Inter below minimums",
            ),
        ],
        coverage_gaps=[
            CoverageGap(source="x", reason="unavailable", note="no endpoint")
        ],
        cost=CostQuote(verdict="RECONCILED", totals=totals),
        narration=Narration(
            text=None, chars=0, numbers_verified=False,
            mp3_path=None, local_seq=None,
        ),
    )


# ---------------------------------------------------------------------------
# numbers_gate unit tests
# ---------------------------------------------------------------------------


class TestExtractNumbers:
    def test_dollar_amount(self) -> None:
        assert _extract_numbers("$0.42") == {"0.42"}

    def test_integer(self) -> None:
        assert _extract_numbers("42 mentions") == {"42"}

    def test_percentage(self) -> None:
        assert _extract_numbers("60%") == {"60"}

    def test_comma_separated(self) -> None:
        assert _extract_numbers("$1,234.56") == {"1234.56"}

    def test_mixed(self) -> None:
        result = _extract_numbers("Cost was $0.42, share 60%")
        assert result == {"0.42", "60"}


class TestNumbersGate:
    def test_passes_when_all_numbers_in_digest(self) -> None:
        digest = _make_digest(cost_total=0.42)
        text = "The cost is $0.42 and share is 0.6."
        assert numbers_gate(text, digest) is True

    def test_rejects_foreign_number(self) -> None:
        digest = _make_digest(cost_total=0.42)
        text = "The cost is $999.99."
        assert numbers_gate(text, digest) is False

    def test_passes_empty_narration(self) -> None:
        digest = _make_digest()
        assert numbers_gate("", digest) is True

    def test_passes_no_numbers(self) -> None:
        digest = _make_digest()
        assert numbers_gate("No numbers here.", digest) is True

    def test_rejects_one_foreign_among_real(self) -> None:
        digest = _make_digest(cost_total=0.42)
        text = "Cost is $0.42, but also $999.99."
        assert numbers_gate(text, digest) is False


class TestDigestNumbers:
    def test_collects_from_digest(self) -> None:
        digest = _make_digest(cost_total=0.42)
        nums = _digest_numbers(digest)
        assert "0.42" in nums
        assert "30" in nums  # sov_entry.n
        assert "0.6" in nums  # share


# ---------------------------------------------------------------------------
# generate_narration tests
# ---------------------------------------------------------------------------


class TestGenerateNarration:
    def test_returns_narration_from_fake(self) -> None:
        digest = _make_digest()
        narration_text = "Nubank leads with share 0.6 and cost $0.42."
        fake = FakeBackend(
            answers={"NarrationSchema": {"narration": narration_text}}
        )
        text, verified = generate_narration(digest, backend=fake)
        assert text == narration_text
        assert verified is True

    def test_retry_on_foreign_number(self) -> None:
        digest = _make_digest(cost_total=0.42)
        # First attempt has a foreign number, second is clean
        fake = _SequentialFake([
            {"narration": "Cost is $999.99."},
            {"narration": "Cost is $0.42."},
        ])
        text, verified = generate_narration(digest, backend=fake)
        assert text == "Cost is $0.42."
        assert verified is True

    def test_returns_false_when_both_fail(self) -> None:
        digest = _make_digest(cost_total=0.42)
        fake = _SequentialFake([
            {"narration": "Cost is $999.99."},
            {"narration": "Also $888.88."},
        ])
        text, verified = generate_narration(digest, backend=fake)
        assert verified is False
        assert "$888.88" in text


# ---------------------------------------------------------------------------
# NarrationSchema tests
# ---------------------------------------------------------------------------


class TestNarrationSchema:
    def test_valid(self) -> None:
        schema = NarrationSchema(narration="Hello world")
        assert schema.narration == "Hello world"

    def test_max_length(self) -> None:
        long = "x" * config.NARRATION_MAX_CHARS
        schema = NarrationSchema(narration=long)
        assert len(schema.narration) == config.NARRATION_MAX_CHARS

    def test_exceeds_max_length(self) -> None:
        with pytest.raises(Exception, match="String should have at most"):
            NarrationSchema(narration="x" * (config.NARRATION_MAX_CHARS + 1))

    def test_empty_rejected(self) -> None:
        with pytest.raises(Exception, match="narration must not be empty"):
            NarrationSchema(narration="")


# ---------------------------------------------------------------------------
# TTS stub tests
# ---------------------------------------------------------------------------


class TestSynthesizeNarration:
    def test_builds_input_payload(self) -> None:
        text = "Hello from sonar."
        payload = synthesize_narration(text)
        assert isinstance(payload, dict)
        assert "body" in payload
        assert payload["body"]["text"] == text
        assert payload["body"]["model_id"] == config.ELEVENLABS_MODEL_ID

    def test_empty_text_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            synthesize_narration("")

    def test_custom_voice_id(self) -> None:
        payload = synthesize_narration("Test", voice_id="custom-voice")
        assert payload["body"]["voice_id"] == "custom-voice"
