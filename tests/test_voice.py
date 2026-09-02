"""Voice layer tests (D006, D011): script, numbers gate, TTS, ``narrate``.

Uses the fake llm seam and a stub ElevenLabs adapter; the last class drives
the real adapter behind a stub Monid transport so the ledger row is pinned.
No network, no real model.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sonar import config
from sonar.llm.base import JsonResult, LlmUnparseable, Rate
from sonar.llm.fake import FakeBackend
from sonar.models import (
    Abstention,
    BySourceEntry,
    CostQuote,
    CoverageGap,
    DateRange,
    Digest,
    Narration,
    RunRecord,
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
from sonar.monid import BREAKER, LOCAL_DEADLINE, AlreadySubmitted, Ledger, MonidClient, MonidHalted
from sonar.providers.base import AdapterSchemaError
from sonar.providers.elevenlabs import ELEVENLABS, TtsResult
from sonar.voice import NO_NARRATION, VoiceResult, narrate
from sonar.voice.script import (
    MAX_ATTEMPTS,
    NarrationSchema,
    digest_numbers,
    extract_numbers,
    numbers_gate,
    regate,
    write_script,
)
from sonar.voice.tts import BRIEF_MP3_FILENAME, synthesize_narration
from tests.test_adapter_elevenlabs import FakeClock, Script, make_client, run_ok

MP3_BYTES = b"\xff\xfb\x90\x00" * 50
NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
HEX_ID = "abc123abc123abc123abc123"


# -- fakes ---------------------------------------------------------------------


class SequentialFake:
    """``FakeBackend`` whose ``complete_json`` answers come from a list, in order."""

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self._answers = list(answers)
        self._inner = FakeBackend()
        self.users: list[str] = []

    @property
    def rates(self) -> Mapping[str, Rate]:
        return self._inner.rates

    @property
    def calls(self) -> Any:
        return self._inner.calls

    def classify(self, batch: Any, model: str) -> Any:
        return self._inner.classify(batch, model)

    def embed(self, texts: Any, model: str) -> Any:
        return self._inner.embed(texts, model)

    def complete_json(
        self, system: str, user: str, schema: type[Any], model: str
    ) -> JsonResult[Any]:
        self.users.append(user)
        if not self._answers:
            raise LlmUnparseable(f"no more canned answers for {schema.__name__!r}")
        self._inner = FakeBackend(answers={schema.__name__: self._answers.pop(0)}, rates=self.rates)
        result: JsonResult[Any] = self._inner.complete_json(system, user, schema, model)
        return result


def _record(seq: int = 7, status: str = "SUCCEEDED", error: str | None = None) -> RunRecord:
    local = status.startswith("LOCAL_")
    return RunRecord(
        local_seq=seq,
        run_id=None if local else f"run_tts_{seq}",
        provider=config.ELEVENLABS_PROVIDER,
        endpoint=config.ELEVENLABS_ENDPOINT,
        brand=None,
        source=None,
        input_digest="0" * 24,
        submitted_at=NOW,
        completed_at=NOW,
        status=status,
        provider_http_status=None if local else 200,
        n_results=0 if local else 1,
        estimate_usd=0.01,
        cost_usd=0.0 if local else None,
        billed_units=None,
        cost_source="local" if local else "unreconciled",
        attempts=1,
        error=error,
    )


@dataclass
class StubAdapter:
    """Stands in for ``ElevenLabsProvider``; records the texts it was asked to voice."""

    record: RunRecord = field(default_factory=_record)
    result: TtsResult | None = field(
        default_factory=lambda: TtsResult(audio=MP3_BYTES, provider_error=None, character_count=11)
    )
    raises: Exception | None = None
    texts: list[str] = field(default_factory=list)
    voice_ids: list[str | None] = field(default_factory=list)

    def synthesize(
        self,
        text: str,
        *,
        client: MonidClient,
        ledger: Ledger,
        voice_id: str | None = None,
    ) -> tuple[RunRecord, TtsResult | None]:
        self.texts.append(text)
        self.voice_ids.append(voice_id)
        if self.raises is not None:
            raise self.raises
        return self.record, self.result


@pytest.fixture
def client() -> MonidClient:
    return MonidClient("monid_test_key")


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "runs.jsonl")


# -- digest fixture --------------------------------------------------------------


def make_digest(*, brand: str = "Nubank", cost_total: float = 0.42) -> Digest:
    start = NOW - timedelta(days=7)
    window = Window(
        current=DateRange(start=start, end=NOW),
        previous=DateRange(start=start - timedelta(days=7), end=start),
    )
    sov = [
        SovEntry(
            brand=brand,
            n=30,
            n_clusters=10,
            share=0.6,
            ci95=(0.5, 0.7),
            basis_sources=["reddit", "google_maps"],
            wow=WowShare(
                delta=0.05, ci95=(0.01, 0.09), verdict="SUGGESTIVE", p_raw=0.03, p_holm=0.06
            ),
        ),
        SovEntry(
            brand="Inter",
            n=10,
            n_clusters=5,
            share=0.2,
            ci95=(0.1, 0.3),
            basis_sources=["reddit", "google_maps"],
            wow=WowShare(delta=None, ci95=None, verdict="ABSTAIN", p_raw=None, p_holm=None),
        ),
    ]
    sentiment = [
        SentimentEntry(
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
            wow=WowNet(
                delta=0.1,
                ci95=(-0.05, 0.25),
                ci95_confirmed_only=(-0.03, 0.2),
                verdict="NO_CHANGE_DETECTED",
                p_raw=0.15,
                p_holm=0.3,
            ),
        ),
        SentimentEntry(
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
            wow=WowNet(
                delta=None,
                ci95=None,
                ci95_confirmed_only=None,
                verdict="ABSTAIN",
                p_raw=None,
                p_holm=None,
            ),
        ),
    ]
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
        name="Card limit complaints",
        n=15,
        n_clusters=6,
        share=0.5,
        net=0.3,
        ci95=(0.0, 0.6),
        exemplar_mention_ids=[HEX_ID, "b" * 24, "c" * 24],
        method=TopicMethod(
            embedding_model="text-embedding-3-small",
            linkage="average",
            threshold=config.TOPIC_DISTANCE_THRESHOLD,
            min_size=3,
            min_breadth=2,
        ),
    )
    top_mention = TopMention(
        mention_id=HEX_ID,
        brand=brand,
        source="reddit",
        url="https://reddit.com/r/nubank/comments/98765/test",
        quote="Great app experience overall",
        lang="en",
        label="positive",
        published_at=NOW,
        engagement_score=42,
    )
    totals = Totals(
        monid_usd=cost_total,
        monid_runs=2,
        monid_runs_billed=1,
        monid_runs_zero_results=0,
        monid_runs_failed=0,
        llm_usd=0.1,
        llm_calls={"classify": 1},
        llm_tokens=500,
        elevenlabs_usd=0.05,
        total_usd=cost_total + 0.1,
    )
    return Digest(
        brand=brand,
        competitors=["Inter"],
        window=window,
        share_of_voice=sov,
        sentiment=sentiment,
        by_source=[by_source],
        topics=[topic],
        events=[],
        top_mentions=[top_mention],
        abstentions=[
            Abstention(
                scope="brand",
                brand="Inter",
                source=None,
                reason="below_minimum",
                detail="Inter below minimums",
            )
        ],
        coverage_gaps=[CoverageGap(source="x", reason="unavailable", note="no endpoint")],
        cost=CostQuote(verdict="RECONCILED", totals=totals),
        narration=NO_NARRATION,
    )


@pytest.fixture
def digest() -> Digest:
    return make_digest()


VERIFIED_TEXT = "Nubank holds a 0.6 share of voice on 30 mentions; net sentiment 0.5. Cost $0.42."
FOREIGN_TEXT = "Nubank holds a 0.6 share of voice on 31 mentions; net sentiment 0.5. Cost $999.99."


# -- extract_numbers -------------------------------------------------------------


class TestExtractNumbers:
    @pytest.mark.parametrize(
        ("text", "values"),
        [
            ("$0.42", ["0.42"]),
            ("42 mentions", ["42"]),
            ("60%", ["60"]),
            ("60 percent", ["60"]),
            ("$1,234.50", ["1234.5"]),
            ("0.60 share", ["0.6"]),
            ("Cost was $0.42, share 60%", ["0.42", "60"]),
            ("no numbers here", []),
            ("net sentiment -0.27", ["-0.27"]),
            ("net \u22120.27", ["-0.27"]),
            ("net \u20130.27", ["-0.27"]),
            ("minus 0.27", ["-0.27"]),
            ("Minus $0.27", ["-0.27"]),
            ("-27%", ["-27"]),
            ("2026-08-26", ["2026", "8", "26"]),
            ("5-10 mentions", ["5", "10"]),
            ("60 per cent", ["60"]),
            ("60 pct", ["60"]),
        ],
    )
    def test_normalises(self, text: str, values: list[str]) -> None:
        assert [str(t.value) for t in extract_numbers(text)] == values

    @pytest.mark.parametrize(
        ("text", "decimals"),
        [("30", 0), ("0.6", 1), ("0.60", 2), ("$1,234.50", 2), ("$0.3194", 4), ("34%", 0)],
    )
    def test_decimals_as_written(self, text: str, decimals: int) -> None:
        (token,) = extract_numbers(text)
        assert token.decimals == decimals

    @pytest.mark.parametrize("text", ["60 per cent", "60 percent", "60 pct", "60%"])
    def test_percent_spellings(self, text: str) -> None:
        (token,) = extract_numbers(text)
        assert token.percent and token.candidates == (Decimal(60), Decimal("0.6"))

    def test_negative_percent_candidates(self) -> None:
        (token,) = extract_numbers("-27%")
        assert token.candidates == (Decimal(-27), Decimal("-0.27"))

    def test_rounded_candidates(self) -> None:
        assert extract_numbers("30")[0].rounded_candidates == ()
        assert extract_numbers("0.60")[0].rounded_candidates == ((Decimal("0.6"), 2),)
        assert extract_numbers("34%")[0].rounded_candidates == (
            (Decimal(34), 0),
            (Decimal("0.34"), 2),
        )

    def test_percent_flag_and_candidates(self) -> None:
        (token,) = extract_numbers("60%")
        assert token.percent
        assert token.candidates == (Decimal(60), Decimal("0.6"))
        (plain,) = extract_numbers("60")
        assert plain.candidates == (Decimal(60),)

    def test_dollar_text_kept_as_written(self) -> None:
        (token,) = extract_numbers("costs $1,234.50 today")
        assert token.text == "$1,234.50"


# -- digest_numbers ----------------------------------------------------------------


class TestDigestNumbers:
    def test_numeric_leaves(self, digest: Digest) -> None:
        nums = digest_numbers(digest)
        assert {Decimal("0.42"), Decimal(30), Decimal("0.6"), Decimal("1.44")} <= nums
        assert Decimal("-0.05") in nums

    def test_dates_do_not_vouch(self, digest: Digest) -> None:
        nums = digest_numbers(digest)
        assert Decimal(2026) not in nums
        assert Decimal(26) not in nums
        assert not numbers_gate("26 mentions", digest).verified
        assert not numbers_gate("2026 was the year.", digest).verified

    def test_identifier_digits_do_not_vouch(self, digest: Digest) -> None:
        nums = digest_numbers(digest)
        assert Decimal(123) not in nums  # from the hex mention id
        assert Decimal(98765) not in nums  # from the url

    def test_excludes_own_narration_block(self) -> None:
        digest = make_digest().model_copy(
            update={
                "narration": Narration(
                    text="$777.77", chars=7, numbers_verified=False, mp3_path=None, local_seq=None
                )
            }
        )
        assert Decimal("777.77") not in digest_numbers(digest)


# -- numbers_gate ------------------------------------------------------------------


class TestNumbersGate:
    def test_passes_when_every_number_is_in_digest(self, digest: Digest) -> None:
        gate = numbers_gate(VERIFIED_TEXT, digest)
        assert gate.verified and gate.foreign == ()
        assert len(gate.tokens) == 4

    def test_rejects_planted_foreign_numbers(self, digest: Digest) -> None:
        gate = numbers_gate(FOREIGN_TEXT, digest)
        assert not gate.verified
        assert gate.foreign == ("31", "$999.99")

    def test_percent_matches_proportion(self, digest: Digest) -> None:
        assert numbers_gate("Share of voice is 60%.", digest).verified
        assert not numbers_gate("Share of voice is 61%.", digest).verified

    def test_formatting_differences_pass(self, digest: Digest) -> None:
        assert numbers_gate("Spent $0.420 on a 0.60 share.", digest).verified

    def test_no_numbers_passes(self, digest: Digest) -> None:
        assert numbers_gate("", digest).verified
        assert numbers_gate("No figures at all.", digest).verified

    def test_foreign_listed_once_in_order(self, digest: Digest) -> None:
        gate = numbers_gate("$999.99 twice: $999.99, then 31.", digest)
        assert gate.foreign == ("$999.99", "31")

    @pytest.mark.parametrize(
        "text",
        [
            "Net sentiment is -0.27.",
            "Net sentiment is minus 0.27.",
            "Net sentiment is \u22120.27.",
            "Net sentiment is -27%.",
            "Net sentiment is minus 27 per cent.",
        ],
    )
    def test_negative_net_passes(self, text: str) -> None:
        digest = with_net(make_digest(), -0.27)
        assert numbers_gate(text, digest).verified

    def test_negative_net_requires_the_sign(self) -> None:
        digest = with_net(make_digest(), -0.27)
        gate = numbers_gate("Net sentiment is 0.27.", digest)
        assert gate.foreign == ("0.27",)
        assert numbers_gate("Net sentiment is -0.5.", make_digest()).foreign == ("-0.5",)

    def test_golden_precision_total_rounded(self) -> None:
        digest = with_totals(make_digest(), monid_usd=0.31405, total_usd=0.31940999999999997)
        assert numbers_gate("Cost $0.3194.", digest).verified
        assert numbers_gate("Cost $0.32.", digest).verified
        assert numbers_gate("Cost $0.3141.", digest).verified
        assert numbers_gate("Cost $0.3195.", digest).foreign == ("$0.3195",)

    def test_share_rounded_to_percent(self) -> None:
        digest = with_share(make_digest(), 37 / 110)
        assert numbers_gate("Share of voice 34%.", digest).verified
        assert numbers_gate("Share of voice 33.6%.", digest).verified
        assert numbers_gate("Share of voice 0.34.", digest).verified
        assert numbers_gate("Share of voice 36%.", digest).foreign == ("36%",)
        assert numbers_gate("Share of voice 0.36.", digest).foreign == ("0.36",)

    def test_bare_integer_never_rounds(self) -> None:
        digest = with_share(make_digest(), 29.6 / 100).model_copy(
            update={"topics": [], "top_mentions": []}
        )
        assert Decimal(30) in digest_numbers(digest)
        digest = with_net(make_digest(), 0.296)
        assert numbers_gate("net 0.3", digest).verified
        assert not numbers_gate("Score 296 today.", digest).verified

    def test_per_cent_passes(self, digest: Digest) -> None:
        assert numbers_gate("Share of voice is 60 per cent.", digest).verified
        assert numbers_gate("Share of voice is 60 pct.", digest).verified


def with_net(digest: Digest, net: float) -> Digest:
    first, *rest = digest.sentiment
    entry = first.model_copy(update={"net": net, "ci95": (net - 0.1, net + 0.1)})
    return digest.model_copy(update={"sentiment": [entry, *rest]})


def with_share(digest: Digest, share: float) -> Digest:
    first, *rest = digest.share_of_voice
    entry = first.model_copy(update={"share": share, "ci95": (share - 0.1, share + 0.1)})
    return digest.model_copy(update={"share_of_voice": [entry, *rest]})


def with_totals(digest: Digest, *, monid_usd: float, total_usd: float) -> Digest:
    totals = digest.cost.totals.model_copy(
        update={"monid_usd": monid_usd, "llm_usd": total_usd - monid_usd, "total_usd": total_usd}
    )
    return digest.model_copy(update={"cost": CostQuote(verdict=digest.cost.verdict, totals=totals)})


class TestRegate:
    def test_stale_cost_flips_to_unverified(self, digest: Digest) -> None:
        narration = _script("Cost $0.42.", verified=True)
        final = with_totals(digest, monid_usd=0.5, total_usd=0.6)
        regated = regate(narration, final)
        assert not regated.numbers_verified
        assert regated.text == narration.text and regated.chars == narration.chars

    def test_matching_cost_flips_to_verified(self, digest: Digest) -> None:
        narration = _script("Cost $0.42.", verified=False)
        assert regate(narration, digest).numbers_verified

    def test_unchanged_when_verdict_holds(self, digest: Digest) -> None:
        narration = _script(VERIFIED_TEXT, verified=True)
        assert regate(narration, digest) is narration

    def test_no_text_is_unchanged(self, digest: Digest) -> None:
        assert regate(NO_NARRATION, digest) is NO_NARRATION


# -- NarrationSchema ---------------------------------------------------------------


class TestNarrationSchema:
    def test_strips_and_keeps_max(self) -> None:
        assert NarrationSchema(narration="  hi  ").narration == "hi"
        long = "x" * config.NARRATION_MAX_CHARS
        assert len(NarrationSchema(narration=long).narration) == config.NARRATION_MAX_CHARS

    def test_rejects_over_budget_and_empty(self) -> None:
        with pytest.raises(ValueError, match="at most"):
            NarrationSchema(narration="x" * (config.NARRATION_MAX_CHARS + 1))
        with pytest.raises(ValueError, match="empty"):
            NarrationSchema(narration="   ")

    def test_padding_does_not_count_against_the_cap(self) -> None:
        body = "x" * config.NARRATION_MAX_CHARS
        assert NarrationSchema(narration=f"  {body}\n\n").narration == body


# -- write_script ------------------------------------------------------------------


class TestWriteScript:
    def test_verified_first_draft(self, digest: Digest) -> None:
        fake = FakeBackend(answers={"NarrationSchema": {"narration": VERIFIED_TEXT}})
        result = write_script(digest, backend=fake)
        assert result.narration.text == VERIFIED_TEXT
        assert result.narration.chars == len(VERIFIED_TEXT)
        assert result.narration.numbers_verified
        assert result.narration.mp3_path is None and result.narration.local_seq is None
        assert result.attempts == 1 and result.foreign == ()
        assert len(result.usage) == 1 and result.usage[0].model == config.LLM.classifier_model
        assert fake.calls_by_kind[("NarrationSchema", config.LLM.classifier_model)] == 1

    def test_model_override(self, digest: Digest) -> None:
        fake = FakeBackend(answers={"NarrationSchema": {"narration": VERIFIED_TEXT}})
        result = write_script(digest, backend=fake, model=config.LLM.tiebreak_model)
        assert result.usage[0].model == config.LLM.tiebreak_model

    def test_planted_number_is_rejected_then_reasked(self, digest: Digest) -> None:
        fake = SequentialFake([{"narration": FOREIGN_TEXT}, {"narration": VERIFIED_TEXT}])
        result = write_script(digest, backend=fake)
        assert result.attempts == 2
        assert result.narration.text == VERIFIED_TEXT
        assert result.narration.numbers_verified
        assert len(result.usage) == 2
        assert "31, $999.99" in fake.users[1]
        assert "not in the digest" not in fake.users[0]

    def test_rejected_twice_keeps_text_unverified(self, digest: Digest) -> None:
        fake = SequentialFake([{"narration": FOREIGN_TEXT}, {"narration": "Cost was $888.88."}])
        result = write_script(digest, backend=fake)
        assert result.attempts == MAX_ATTEMPTS
        assert result.narration.text == "Cost was $888.88."
        assert not result.narration.numbers_verified
        assert result.foreign == ("$888.88",)

    def test_over_budget_twice_is_unparseable(self, digest: Digest) -> None:
        fake = FakeBackend(
            answers={"NarrationSchema": {"narration": "x" * (config.NARRATION_MAX_CHARS + 1)}}
        )
        with pytest.raises(LlmUnparseable):
            write_script(digest, backend=fake)
        assert fake.calls_by_kind[("NarrationSchema", config.LLM.classifier_model)] == MAX_ATTEMPTS

    def test_over_budget_first_draft_is_reasked(self, digest: Digest) -> None:
        over = "x" * (config.NARRATION_MAX_CHARS + 1)
        fake = SequentialFake([{"narration": over}, {"narration": VERIFIED_TEXT}])
        result = write_script(digest, backend=fake)
        assert result.attempts == 2 and result.narration.text == VERIFIED_TEXT
        assert result.narration.numbers_verified and len(result.usage) == 1
        assert "exceeded" not in fake.users[0]
        assert f"exceeded {config.NARRATION_MAX_CHARS} characters; shorten it" in fake.users[1]
        assert "not in the digest" not in fake.users[1]

    def test_over_budget_then_foreign_keeps_text_unverified(self, digest: Digest) -> None:
        over = "x" * (config.NARRATION_MAX_CHARS + 1)
        fake = SequentialFake([{"narration": over}, {"narration": FOREIGN_TEXT}])
        result = write_script(digest, backend=fake)
        assert result.attempts == MAX_ATTEMPTS
        assert result.narration.text == FOREIGN_TEXT and not result.narration.numbers_verified

    def test_prompt_carries_digest_without_its_narration(self, digest: Digest) -> None:
        fake = SequentialFake([{"narration": VERIFIED_TEXT}])
        write_script(digest, backend=fake)
        assert '"brand":"Nubank"' in fake.users[0]
        assert '"narration"' not in fake.users[0]


# -- synthesize_narration ----------------------------------------------------------


def _script(text: str | None = VERIFIED_TEXT, verified: bool = True) -> Narration:
    return Narration(
        text=text, chars=len(text or ""), numbers_verified=verified, mp3_path=None, local_seq=None
    )


class TestSynthesizeNarration:
    def test_writes_mp3_and_links_ledger_row(
        self, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        stub = StubAdapter()
        out = synthesize_narration(
            _script(),
            client=client,
            ledger=ledger,
            out_dir=tmp_path / "s1",
            adapter=stub,
            voice_id="v1",
        )
        path = tmp_path / "s1" / BRIEF_MP3_FILENAME
        assert out.voiced and out.abstention is None
        assert out.narration.mp3_path == BRIEF_MP3_FILENAME
        assert path.read_bytes() == MP3_BYTES
        assert out.narration.local_seq == 7 and out.record is stub.record
        assert out.narration.text == VERIFIED_TEXT and out.narration.numbers_verified
        assert stub.texts == [VERIFIED_TEXT] and stub.voice_ids == ["v1"]

    def test_unverified_numbers_are_not_voiced(
        self, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        stub = StubAdapter()
        out = synthesize_narration(
            _script(FOREIGN_TEXT, verified=False),
            client=client,
            ledger=ledger,
            out_dir=tmp_path,
            adapter=stub,
        )
        assert stub.texts == []
        assert not out.voiced and out.record is None and out.abstention is None
        assert out.narration.text == FOREIGN_TEXT
        assert not (tmp_path / BRIEF_MP3_FILENAME).exists()

    def test_no_text_is_skipped(self, client: MonidClient, ledger: Ledger, tmp_path: Path) -> None:
        stub = StubAdapter()
        out = synthesize_narration(
            NO_NARRATION, client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert stub.texts == [] and out.narration == NO_NARRATION

    def test_provider_error_abstains_without_audio(
        self, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        stub = StubAdapter(
            result=TtsResult(audio=None, provider_error="voice_not_found", character_count=None)
        )
        out = synthesize_narration(
            _script(), client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert not out.voiced and out.record is stub.record
        assert out.abstention is not None
        assert out.abstention.scope == "voice" and out.abstention.reason == "provider_failed"
        assert "voice_not_found" in out.abstention.detail

    @pytest.mark.parametrize(
        ("status", "reason"),
        [
            (LOCAL_DEADLINE, "deadline"),
            ("LOCAL_REJECTED_429", "rate_limited"),
            ("LOCAL_REJECTED_500", "provider_failed"),
        ],
    )
    def test_failed_run_maps_status_to_reason(
        self, client: MonidClient, ledger: Ledger, tmp_path: Path, status: str, reason: str
    ) -> None:
        stub = StubAdapter(record=_record(status=status, error="boom"), result=None)
        out = synthesize_narration(
            _script(), client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert out.abstention is not None and out.abstention.reason == reason
        assert out.abstention.detail == "boom"
        assert out.narration.mp3_path is None

    @pytest.mark.parametrize(
        ("exc", "reason"),
        [
            (MonidHalted("breaker tripped"), "halted"),
            (AdapterSchemaError("elevenlabs", "/text-to-speech", "drift"), "schema_drift"),
            (AlreadySubmitted(_record(seq=3)), "provider_failed"),
        ],
    )
    def test_adapter_exceptions_become_abstentions(
        self, client: MonidClient, ledger: Ledger, tmp_path: Path, exc: Exception, reason: str
    ) -> None:
        stub = StubAdapter(raises=exc)
        out = synthesize_narration(
            _script(), client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert out.abstention is not None and out.abstention.reason == reason
        assert out.narration.text == VERIFIED_TEXT and not out.voiced


# -- narrate -----------------------------------------------------------------------


class TestNarrate:
    def test_end_to_end(
        self, digest: Digest, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        fake = FakeBackend(answers={"NarrationSchema": {"narration": VERIFIED_TEXT}})
        stub = StubAdapter()
        result = narrate(
            digest, backend=fake, client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert isinstance(result, VoiceResult)
        assert result.narration.text == VERIFIED_TEXT
        assert result.narration.numbers_verified
        assert result.narration.local_seq == 7
        assert result.narration.mp3_path == BRIEF_MP3_FILENAME
        assert (tmp_path / BRIEF_MP3_FILENAME).read_bytes() == MP3_BYTES
        assert result.record is stub.record and result.abstentions == ()
        assert len(result.usage) == 1
        assert digest.model_copy(update={"narration": result.narration}).narration.chars == len(
            VERIFIED_TEXT
        )

    def test_planted_number_rejected_twice_means_no_spend(
        self, digest: Digest, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        fake = SequentialFake([{"narration": FOREIGN_TEXT}, {"narration": FOREIGN_TEXT}])
        stub = StubAdapter()
        result = narrate(
            digest, backend=fake, client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert not result.narration.numbers_verified
        assert result.narration.text == FOREIGN_TEXT
        assert result.narration.mp3_path is None and result.record is None
        assert stub.texts == [] and len(result.usage) == 2

    def test_seam_failure_yields_no_narration(
        self, digest: Digest, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        stub = StubAdapter()
        result = narrate(
            digest,
            backend=FakeBackend(),
            client=client,
            ledger=ledger,
            out_dir=tmp_path,
            adapter=stub,
        )
        assert result.narration == NO_NARRATION and result.usage == ()
        (abstention,) = result.abstentions
        assert abstention.scope == "voice" and abstention.reason == "provider_failed"
        assert stub.texts == []

    def test_tts_failure_keeps_text(
        self, digest: Digest, client: MonidClient, ledger: Ledger, tmp_path: Path
    ) -> None:
        fake = FakeBackend(answers={"NarrationSchema": {"narration": VERIFIED_TEXT}})
        stub = StubAdapter(raises=MonidHalted("402"))
        result = narrate(
            digest, backend=fake, client=client, ledger=ledger, out_dir=tmp_path, adapter=stub
        )
        assert result.narration.text == VERIFIED_TEXT and result.narration.mp3_path is None
        assert [a.reason for a in result.abstentions] == ["halted"]


class TestNarrateThroughLedger:
    """``narrate`` with the real ElevenLabs adapter behind a stub Monid transport."""

    @pytest.fixture(autouse=True)
    def _reset_breaker(self) -> Iterator[None]:
        BREAKER.reset()
        yield
        BREAKER.reset()

    def test_tts_run_lands_in_the_ledger(self, digest: Digest, tmp_path: Path) -> None:
        output = {
            "audio": {
                "audio_base64": base64.b64encode(MP3_BYTES).decode(),
                "content_type": "audio/mpeg",
                "character_count": len(VERIFIED_TEXT),
            }
        }
        script = Script({("POST", "/v1/run"): [run_ok(output, "run_tts_9")]})
        ledger = Ledger(tmp_path / "runs.jsonl")
        fake = FakeBackend(answers={"NarrationSchema": {"narration": VERIFIED_TEXT}})
        result = narrate(
            digest,
            backend=fake,
            client=make_client(script, FakeClock()),
            ledger=ledger,
            out_dir=tmp_path,
            adapter=ELEVENLABS,
        )
        (row,) = ledger.records
        assert row.provider == config.ELEVENLABS_PROVIDER
        assert row.endpoint == config.ELEVENLABS_ENDPOINT
        assert row.brand is None and row.source is None
        assert row.n_results == 1
        assert row.cost_source == "unreconciled" and row.cost_usd is None
        assert row.run_id == "run_tts_9" and row.status == "SUCCEEDED"
        assert result.narration.local_seq == row.local_seq
        assert result.record == row and result.abstentions == ()
        assert result.narration.mp3_path == BRIEF_MP3_FILENAME
        assert (tmp_path / BRIEF_MP3_FILENAME).read_bytes() == MP3_BYTES
        (post,) = script.posts()
        assert post["endpoint"] == config.ELEVENLABS_ENDPOINT
        assert post["input"]["body"]["text"] == VERIFIED_TEXT
