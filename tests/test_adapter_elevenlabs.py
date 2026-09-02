"""Tests for the ElevenLabs adapter (W3.6).

Uses hand-built sample payloads under ``tests/fixtures/samples/`` (named
``*_sample.json`` or ``SAMPLE-hand-built-*`` so the fixtures README rule is
not violated).  The Monid transport is a stub ``httpx.MockTransport``; no
test touches the network.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import httpx
import pytest

from sonar.config import (
    ELEVENLABS_ENDPOINT,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_USD_PER_1K_CHARS,
    ELEVENLABS_VOICES_ENDPOINT,
    NARRATION_MAX_CHARS,
)
from sonar.monid import BREAKER, AlreadySubmitted, Ledger, MonidClient, MonidHalted
from sonar.providers.base import AdapterSchemaError
from sonar.providers.elevenlabs import (
    DEFAULT_VOICE_ID,
    PROVIDER_MAX_CHARS,
    ElevenLabsProvider,
    TtsResult,
    VoiceProvider,
    provider_error,
    run_payload,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "samples"
TTS_SAMPLE = "elevenlabs_tts_sample.json"
VOICES_SAMPLE = "elevenlabs_voices_sample.json"
PROVIDER_ERROR_SAMPLE = "SAMPLE-hand-built-elevenlabs_text-to-speech_provider-error.json"
SCHEMA_DRIFT_SAMPLE = "SAMPLE-hand-built-elevenlabs_text-to-speech_schema-drift.json"

MP3_BYTES = b"\xff\xfb\x90\x00" * 50


def _load(name: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return result


# -- stub transport (same shape as tests/test_errors.py) --------------------


@dataclass
class FakeClock:
    now: float = 0.0
    sleeps: list[float] = field(default_factory=list)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


@dataclass
class Script:
    responses: dict[tuple[str, str], list[httpx.Response]]
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.responses.get((request.method, request.url.path))
        if not queue:
            return httpx.Response(500, json={"error": "unscripted"})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def posts(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for r in self.requests:
            if r.method == "POST":
                body: dict[str, Any] = json.loads(r.content)
                out.append(body)
        return out


def make_client(script: Script, clock: FakeClock) -> MonidClient:
    return MonidClient(
        "monid_test_key",
        transport=httpx.MockTransport(script),
        sleep=clock.sleep,
        clock=clock.monotonic,
        poll_initial_s=1.0,
        poll_max_s=4.0,
    )


def run_ok(output: Any, run_id: str = "run_1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "runId": run_id,
            "status": "SUCCEEDED",
            "providerResponse": {"httpStatus": 200},
            "output": output,
        },
    )


@pytest.fixture(autouse=True)
def _reset_breaker() -> Iterator[None]:
    BREAKER.reset()
    yield
    BREAKER.reset()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    return Ledger(tmp_path / "runs.jsonl")


@pytest.fixture
def provider() -> ElevenLabsProvider:
    return ElevenLabsProvider()


# -- protocol, input, cost ----------------------------------------------------


class TestBasics:
    def test_properties(self, provider: ElevenLabsProvider) -> None:
        assert provider.provider == "elevenlabs"
        assert provider.endpoint == ELEVENLABS_ENDPOINT
        assert isinstance(provider, VoiceProvider)

    def test_build_input(self, provider: ElevenLabsProvider) -> None:
        inp = provider.build_input("Hello world")
        assert inp["body"]["text"] == "Hello world"
        assert inp["body"]["model_id"] == ELEVENLABS_MODEL_ID
        assert inp["body"]["voice_id"] == DEFAULT_VOICE_ID

    def test_build_input_explicit_voice(self, provider: ElevenLabsProvider) -> None:
        inp = provider.build_input("Hello", voice_id="pNInz6obpgDQGcFmaJgB")
        assert inp["body"]["voice_id"] == "pNInz6obpgDQGcFmaJgB"

    def test_build_input_caps_at_narration_budget(self, provider: ElevenLabsProvider) -> None:
        text = "x" * (NARRATION_MAX_CHARS + 300)
        inp = provider.build_input(text)
        assert len(inp["body"]["text"]) == NARRATION_MAX_CHARS
        assert inp["body"]["text"] == text[:NARRATION_MAX_CHARS]

    def test_build_input_exact_budget_untouched(self, provider: ElevenLabsProvider) -> None:
        text = "y" * NARRATION_MAX_CHARS
        assert provider.build_input(text)["body"]["text"] == text

    def test_build_input_refuses_above_provider_ceiling(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(ValueError, match=str(PROVIDER_MAX_CHARS)):
            provider.build_input("z" * (PROVIDER_MAX_CHARS + 1))

    def test_build_input_refuses_empty(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(ValueError, match="empty"):
            provider.build_input("   ")

    def test_estimate_cost(self, provider: ElevenLabsProvider) -> None:
        assert provider.estimate_cost(1000) == pytest.approx(ELEVENLABS_USD_PER_1K_CHARS)
        assert provider.estimate_cost(500) == pytest.approx(ELEVENLABS_USD_PER_1K_CHARS / 2)
        assert provider.estimate_cost(0) == 0.0


# -- parse_tts: audio, provider error, schema drift ---------------------------


class TestParseTts:
    def test_base64_fallback(self, provider: ElevenLabsProvider) -> None:
        payload = {
            "audio": {
                "audio_base64": base64.b64encode(MP3_BYTES).decode(),
                "content_type": "audio/mpeg",
                "character_count": 25,
            }
        }
        result = provider.parse_tts(payload)
        assert result.ok
        assert result.audio == MP3_BYTES
        assert result.provider_error is None
        assert result.character_count == 25

    def test_download_link_primary(
        self, provider: ElevenLabsProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetched: list[str] = []

        class _FakeResponse:
            def raise_for_status(self) -> None:
                pass

            @property
            def content(self) -> bytes:
                return MP3_BYTES

        class _FakeClient:
            def __init__(self, **_kw: Any) -> None:
                pass

            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_a: object) -> None:
                pass

            def get(self, url: str) -> _FakeResponse:
                fetched.append(url)
                return _FakeResponse()

        monkeypatch.setattr("sonar.providers.elevenlabs.httpx.Client", _FakeClient)
        sample = _load(TTS_SAMPLE)
        result = provider.parse_tts(sample)
        assert result.audio == MP3_BYTES
        assert fetched == [sample["audio"]["download_link"]]
        assert result.character_count == 45

    def test_provider_error_is_data_not_exception(self, provider: ElevenLabsProvider) -> None:
        """Documented case: unknown voice_id / exhausted quota → COMPLETED run, error as data."""
        result = provider.parse_tts(_load(PROVIDER_ERROR_SAMPLE))
        assert isinstance(result, TtsResult)
        assert not result.ok
        assert result.audio is None
        assert result.provider_error is not None
        assert "voice_not_found" in result.provider_error
        assert "was not found" in result.provider_error

    @pytest.mark.parametrize(
        "payload",
        [
            {"error": "quota_exceeded"},
            {"error": {"message": "quota exceeded", "code": "quota_exceeded"}},
            {"message": "Unauthorized voice"},
            {"detail": "voice not found"},
        ],
    )
    def test_provider_error_shapes(
        self, provider: ElevenLabsProvider, payload: dict[str, Any]
    ) -> None:
        result = provider.parse_tts(payload)
        assert result.audio is None
        assert result.provider_error

    def test_schema_drift_raises(self, provider: ElevenLabsProvider) -> None:
        """A renamed payload with no error keys is drift, not a provider error."""
        with pytest.raises(AdapterSchemaError, match="missing 'audio'"):
            provider.parse_tts(_load(SCHEMA_DRIFT_SAMPLE))

    def test_sample_without_audio_raises(self, provider: ElevenLabsProvider) -> None:
        sample = _load(TTS_SAMPLE)
        mutated = {k: v for k, v in sample.items() if k != "audio"}
        with pytest.raises(AdapterSchemaError):
            provider.parse_tts(mutated)

    def test_empty_audio_object_raises(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(AdapterSchemaError, match="missing 'download_link'"):
            provider.parse_tts({"audio": {"content_type": "audio/mpeg"}})

    def test_expired_audio_raises(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(AdapterSchemaError, match="expired"):
            provider.parse_tts({"audio": {"expired": True}})

    def test_non_dict_raises(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(AdapterSchemaError, match="expected object"):
            provider.parse_tts(["not", "a", "dict"])

    def test_provider_error_helper_ignores_valid_audio(self) -> None:
        sample = _load(TTS_SAMPLE)
        assert provider_error(sample) is None
        assert provider_error({**sample, "message": "ok"}) is None

    def test_run_payload_unwraps_output(self) -> None:
        assert run_payload({"runId": "r", "output": {"audio": {}}}) == {"audio": {}}
        assert run_payload({"voices": []}) == {"voices": []}
        assert run_payload({"output": [1, 2]}) == [1, 2]
        assert run_payload(None) is None


# -- /voices through client + ledger -----------------------------------------


class TestVoicesRun:
    def test_list_voices_writes_ledger_row(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        sample = _load(VOICES_SAMPLE)
        script = Script({("POST", "/v1/run"): [run_ok(sample, "run_voices_1")]})
        client = make_client(script, clock)

        voices = provider.list_voices(client, ledger)

        assert voices is not None
        assert [v["voice_id"] for v in voices] == [v["voice_id"] for v in sample["voices"]]
        (post,) = script.posts()
        assert post == {
            "provider": "elevenlabs",
            "endpoint": ELEVENLABS_VOICES_ENDPOINT,
            "input": {},
        }
        assert script.requests[0].headers["Authorization"] == "Bearer monid_test_key"

        (row,) = ledger.records
        assert row.provider == "elevenlabs"
        assert row.endpoint == ELEVENLABS_VOICES_ENDPOINT
        assert row.brand is None
        assert row.source is None
        assert row.run_id == "run_voices_1"
        assert row.status == "SUCCEEDED"
        assert row.n_results == 2
        assert row.estimate_usd == 0.0
        assert row.cost_source == "unreconciled"
        assert row.provider_http_status == 200

    def test_list_voices_accepts_bare_list_output(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        sample = _load(VOICES_SAMPLE)
        script = Script({("POST", "/v1/run"): [run_ok(sample["voices"])]})
        voices = provider.list_voices(make_client(script, clock), ledger)
        assert voices is not None
        assert len(voices) == 2
        assert ledger.records[0].n_results == 2

    def test_list_voices_rejected_returns_none_and_records_local_row(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [httpx.Response(500, json={"error": "boom"})]})
        assert provider.list_voices(make_client(script, clock), ledger) is None
        (row,) = ledger.records
        assert row.status == "LOCAL_REJECTED_500"
        assert row.run_id is None
        assert row.cost_source == "local"
        assert row.cost_usd == 0.0

    def test_list_voices_backs_off_on_429(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        sample = _load(VOICES_SAMPLE)
        script = Script(
            {
                ("POST", "/v1/run"): [
                    httpx.Response(429, json={"error": "slow down"}),
                    httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "7"}),
                    run_ok(sample),
                ]
            }
        )
        voices = provider.list_voices(make_client(script, clock), ledger)
        assert voices is not None and len(voices) == 2
        assert clock.sleeps == [2.0, 7.0]
        assert ledger.records[0].attempts == 3

    def test_402_trips_breaker_for_next_call(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script(
            {("POST", "/v1/run"): [httpx.Response(402, json={"error": "payment required"})]}
        )
        client = make_client(script, clock)
        assert provider.list_voices(client, ledger) is None
        assert ledger.records[0].status == "LOCAL_REJECTED_402"
        assert client.halted
        with pytest.raises(MonidHalted):
            provider.synthesize("Hello", client=client, ledger=ledger)
        assert len(script.posts()) == 1

    def test_second_voices_run_refused_by_ledger(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok(_load(VOICES_SAMPLE))]})
        client = make_client(script, clock)
        provider.list_voices(client, ledger)
        with pytest.raises(AlreadySubmitted):
            provider.list_voices(client, ledger)

    def test_list_voices_drift_raises(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok({"items": [{"id": "x"}]})]})
        with pytest.raises(AdapterSchemaError, match="not a list"):
            provider.list_voices(make_client(script, clock), ledger)
        assert ledger.records[0].status == "SUCCEEDED"

    def test_parse_voices_entry_missing_voice_id(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(AdapterSchemaError, match="missing 'voice_id'"):
            provider.parse_voices({"voices": [{"name": "Rachel"}]})

    def test_parse_voices_not_list(self, provider: ElevenLabsProvider) -> None:
        with pytest.raises(AdapterSchemaError, match="not a list"):
            provider.parse_voices({"not_voices": True})


class TestResolveVoice:
    def test_by_name(self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock) -> None:
        script = Script({("POST", "/v1/run"): [run_ok(_load(VOICES_SAMPLE))]})
        voice = provider.resolve_voice("Adam", client=make_client(script, clock), ledger=ledger)
        assert voice == "pNInz6obpgDQGcFmaJgB"

    def test_first_when_no_name(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok(_load(VOICES_SAMPLE))]})
        voice = provider.resolve_voice(None, client=make_client(script, clock), ledger=ledger)
        assert voice == "21m00Tcm4TlvDq8ikWAM"

    def test_default_when_run_fails(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [httpx.Response(503, json={"error": "down"})]})
        voice = provider.resolve_voice("Adam", client=make_client(script, clock), ledger=ledger)
        assert voice == DEFAULT_VOICE_ID
        assert ledger.records[0].status == "LOCAL_REJECTED_503"

    def test_default_when_no_voices(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok({"voices": []})]})
        voice = provider.resolve_voice(None, client=make_client(script, clock), ledger=ledger)
        assert voice == DEFAULT_VOICE_ID


# -- /text-to-speech through client + ledger ---------------------------------


class TestSynthesize:
    def test_success_rows_and_audio(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        output = {
            "audio": {
                "audio_base64": base64.b64encode(MP3_BYTES).decode(),
                "content_type": "audio/mpeg",
                "character_count": 11,
            }
        }
        script = Script({("POST", "/v1/run"): [run_ok(output, "run_tts_1")]})
        record, result = provider.synthesize(
            "Hello world", client=make_client(script, clock), ledger=ledger
        )
        assert result is not None and result.audio == MP3_BYTES
        (post,) = script.posts()
        assert post["endpoint"] == ELEVENLABS_ENDPOINT
        assert post["input"]["body"]["text"] == "Hello world"
        assert record.run_id == "run_tts_1"
        assert record.status == "SUCCEEDED"
        assert record.n_results == 1
        assert record.estimate_usd == pytest.approx(provider.estimate_cost(11))
        assert record.cost_source == "unreconciled"
        assert record.brand is None and record.source is None

    def test_provider_error_run_is_completed_without_audio(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok(_load(PROVIDER_ERROR_SAMPLE), "run_tts_2")]})
        record, result = provider.synthesize(
            "Hello", client=make_client(script, clock), ledger=ledger, voice_id="nope"
        )
        assert result is not None
        assert result.audio is None
        assert result.provider_error is not None and "voice_not_found" in result.provider_error
        assert record.status == "SUCCEEDED"
        assert record.run_id == "run_tts_2"
        assert record.n_results == 0

    def test_rejected_run_returns_no_result(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [httpx.Response(500, json={"error": "boom"})]})
        record, result = provider.synthesize(
            "Hello", client=make_client(script, clock), ledger=ledger
        )
        assert result is None
        assert record.status == "LOCAL_REJECTED_500"
        assert record.cost_source == "local"

    def test_estimate_uses_capped_length(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        output = {"audio": {"audio_base64": base64.b64encode(MP3_BYTES).decode()}}
        script = Script({("POST", "/v1/run"): [run_ok(output)]})
        record, _ = provider.synthesize(
            "w" * (NARRATION_MAX_CHARS + 500), client=make_client(script, clock), ledger=ledger
        )
        assert record.estimate_usd == pytest.approx(provider.estimate_cost(NARRATION_MAX_CHARS))
        assert len(script.posts()[0]["input"]["body"]["text"]) == NARRATION_MAX_CHARS

    def test_drift_raises_after_row_closed(
        self, provider: ElevenLabsProvider, ledger: Ledger, clock: FakeClock
    ) -> None:
        script = Script({("POST", "/v1/run"): [run_ok(_load(SCHEMA_DRIFT_SAMPLE))]})
        with pytest.raises(AdapterSchemaError):
            provider.synthesize("Hello", client=make_client(script, clock), ledger=ledger)
        assert ledger.records[0].status == "SUCCEEDED"


# -- /text-to-speech straight to ElevenLabs (D016) --------------------------


@dataclass
class DirectScript:
    """Stub for the ElevenLabs REST call; records the one request it gets."""

    response: httpx.Response
    request: httpx.Request | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.request = request
        return self.response


def direct_transport(script: DirectScript) -> httpx.MockTransport:
    return httpx.MockTransport(script)


class TestSynthesizeDirect:
    def test_success_writes_local_row_with_theoretical_cost(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(200, content=MP3_BYTES))
        record, result = provider.synthesize_direct(
            "Hello world",
            ledger=ledger,
            api_key="xi_key_123",
            transport=direct_transport(script),
        )
        assert result is not None and result.audio == MP3_BYTES
        assert result.character_count == len("Hello world")
        assert record.run_id is None
        assert record.status == "COMPLETED"
        assert record.cost_source == "local"
        assert record.cost_usd == 0.0
        assert record.n_results == 1
        assert record.provider == "elevenlabs"
        assert record.endpoint == ELEVENLABS_ENDPOINT
        assert record.estimate_usd == pytest.approx(provider.estimate_cost(len("Hello world")))
        assert record.brand is None and record.source is None

    def test_request_carries_key_model_and_voice(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(200, content=MP3_BYTES))
        provider.synthesize_direct(
            "Hi",
            ledger=ledger,
            api_key="xi_key_123",
            voice_id="pNInz6obpgDQGcFmaJgB",
            transport=direct_transport(script),
        )
        req = script.request
        assert req is not None
        assert req.url.host == "api.elevenlabs.io"
        assert req.url.path == "/v1/text-to-speech/pNInz6obpgDQGcFmaJgB"
        assert req.headers["xi-api-key"] == "xi_key_123"
        body = json.loads(req.content)
        assert body["text"] == "Hi"
        assert body["model_id"] == ELEVENLABS_MODEL_ID

    def test_estimate_uses_capped_length(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(200, content=MP3_BYTES))
        record, _ = provider.synthesize_direct(
            "w" * (NARRATION_MAX_CHARS + 400),
            ledger=ledger,
            api_key="k",
            transport=direct_transport(script),
        )
        assert record.estimate_usd == pytest.approx(provider.estimate_cost(NARRATION_MAX_CHARS))
        assert json.loads(script.request.content)["text"] == "w" * NARRATION_MAX_CHARS  # type: ignore[union-attr]

    def test_empty_text_refused_before_any_row(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            provider.synthesize_direct("   ", ledger=ledger, api_key="k")
        assert ledger.records == []

    def test_auth_failure_is_a_failed_local_row(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(401, json={"detail": "invalid api key"}))
        record, result = provider.synthesize_direct(
            "Hello", ledger=ledger, api_key="bad", transport=direct_transport(script)
        )
        assert result is None
        assert record.status == "LOCAL_REJECTED_401"
        assert record.cost_source == "local"
        assert record.cost_usd == 0.0

    def test_validation_error_is_provider_error_no_charge(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(422, json={"detail": "voice_id not found"}))
        record, result = provider.synthesize_direct(
            "Hello", ledger=ledger, api_key="k", voice_id="nope", transport=direct_transport(script)
        )
        assert result is not None
        assert result.audio is None
        assert result.provider_error is not None and "voice_id" in result.provider_error
        assert record.status == "COMPLETED"
        assert record.n_results == 0
        assert record.cost_usd == 0.0

    def test_network_error_is_a_failed_local_row(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        def boom(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        record, result = provider.synthesize_direct(
            "Hello", ledger=ledger, api_key="k", transport=httpx.MockTransport(boom)
        )
        assert result is None
        assert record.status == "LOCAL_BACKOFF_EXHAUSTED"
        assert record.cost_source == "local"

    def test_second_call_same_text_refused_by_ledger(
        self, provider: ElevenLabsProvider, ledger: Ledger
    ) -> None:
        script = DirectScript(httpx.Response(200, content=MP3_BYTES))
        provider.synthesize_direct(
            "Hello", ledger=ledger, api_key="k", transport=direct_transport(script)
        )
        with pytest.raises(AlreadySubmitted):
            provider.synthesize_direct(
                "Hello", ledger=ledger, api_key="k", transport=direct_transport(script)
            )


# -- sample shapes -------------------------------------------------------------


class TestSamples:
    def test_tts_sample_shape(self) -> None:
        sample = _load(TTS_SAMPLE)
        assert isinstance(sample["audio"].get("download_link"), str)
        assert "character_count" in sample["audio"]

    def test_voices_sample_shape(self) -> None:
        voices = _load(VOICES_SAMPLE)["voices"]
        assert isinstance(voices, list) and len(voices) >= 1
        for v in voices:
            assert "voice_id" in v and "name" in v

    def test_provider_error_sample_has_no_audio(self) -> None:
        sample = _load(PROVIDER_ERROR_SAMPLE)
        assert "audio" not in sample
        assert provider_error(sample) is not None

    def test_schema_drift_sample_has_no_error_keys(self) -> None:
        sample = _load(SCHEMA_DRIFT_SAMPLE)
        assert "audio" not in sample
        assert provider_error(sample) is None
