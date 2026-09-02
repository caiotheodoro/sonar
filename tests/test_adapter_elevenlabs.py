"""Tests for the ElevenLabs adapter (W3.6).

Uses hand-built sample payloads under ``tests/fixtures/samples/`` (marked
``*_sample.json`` so the fixtures README rule is not violated).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Self

import pytest

from sonar.config import ELEVENLABS_ENDPOINT, ELEVENLABS_MODEL_ID, ELEVENLABS_USD_PER_1K_CHARS
from sonar.providers.base import AdapterSchemaError
from sonar.providers.elevenlabs import ElevenLabsProvider

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "samples"
TTS_SAMPLE = FIXTURES / "elevenlabs_tts_sample.json"
VOICES_SAMPLE = FIXTURES / "elevenlabs_voices_sample.json"


def _load(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    result: dict[str, Any] = json.loads(path.read_text())
    return result


class TestElevenLabsProvider:
    def test_properties(self) -> None:
        p = ElevenLabsProvider()
        assert p.provider == "elevenlabs"
        assert p.endpoint == ELEVENLABS_ENDPOINT

    def test_build_input(self) -> None:
        p = ElevenLabsProvider()
        inp = p.build_input("Hello world")
        assert inp["body"]["text"] == "Hello world"
        assert inp["body"]["model_id"] == ELEVENLABS_MODEL_ID
        assert "voice_id" in inp["body"]

    def test_estimate_cost(self) -> None:
        p = ElevenLabsProvider()
        assert p.estimate_cost(1000) == pytest.approx(ELEVENLABS_USD_PER_1K_CHARS)
        assert p.estimate_cost(500) == pytest.approx(ELEVENLABS_USD_PER_1K_CHARS / 2)
        assert p.estimate_cost(0) == 0.0

    def test_download_audio_fallback_base64(self) -> None:
        """Fallback path: audio_base64 when download_link absent."""
        original = b"\xff\xfb\x90\x00" * 50
        resp: dict[str, Any] = {
            "audio": {
                "audio_base64": base64.b64encode(original).decode(),
                "content_type": "audio/mpeg",
                "character_count": 25,
            }
        }
        p = ElevenLabsProvider()
        assert p.download_audio(resp) == original

    def test_download_audio_from_link(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Primary path: audio.download_link is fetched via httpx."""
        mp3_bytes = b"\xff\xfb\x90\x00" * 100

        class _FakeResponse:
            def raise_for_status(self) -> None:
                pass

            @property
            def content(self) -> bytes:
                return mp3_bytes

        class _FakeClient:
            def __init__(self, **_kw: Any) -> None:
                pass

            def __enter__(self) -> Self:
                return self

            def __exit__(self, *_a: object) -> None:
                pass

            def get(self, _url: str) -> _FakeResponse:
                return _FakeResponse()

        monkeypatch.setattr("sonar.providers.elevenlabs.httpx.Client", _FakeClient)
        p = ElevenLabsProvider()
        resp: dict[str, Any] = {
            "audio": {
                "download_link": "https://cdn.monid.ai/audio/test.mp3",
                "content_type": "audio/mpeg",
                "character_count": 45,
            }
        }
        result = p.download_audio(resp)
        assert result == mp3_bytes

    def test_download_audio_no_audio_raises(self) -> None:
        """Provider error: no audio object → AdapterSchemaError."""
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError, match="missing 'audio'"):
            p.download_audio({})

    def test_download_audio_no_link_or_base64_raises(self) -> None:
        """Audio object present but empty → AdapterSchemaError."""
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError, match="missing 'download_link'"):
            p.download_audio({"audio": {"content_type": "audio/mpeg"}})


class TestParseSample:
    def test_parse_sample_has_download_link(self) -> None:
        """The TTS sample payload has the expected shape."""
        sample = _load("elevenlabs_tts_sample.json")
        assert "audio" in sample
        audio = sample["audio"]
        assert isinstance(audio.get("download_link"), str)
        assert "character_count" in audio

    def test_parse_sample_mutation_no_audio(self) -> None:
        """Mutated payload (no audio) must be rejected by download_audio."""
        sample = _load("elevenlabs_tts_sample.json")
        mutated = {k: v for k, v in sample.items() if k != "audio"}
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError):
            p.download_audio(mutated)

    def test_parse_sample_mutation_empty_audio(self) -> None:
        """Mutated payload (audio={} ) must be rejected."""
        sample = _load("elevenlabs_tts_sample.json")
        sample["audio"] = {}
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError):
            p.download_audio(sample)


class TestVoicesSample:
    def test_voices_sample_shape(self) -> None:
        """The voices sample payload has the expected shape."""
        sample = _load("elevenlabs_voices_sample.json")
        assert "voices" in sample
        voices = sample["voices"]
        assert isinstance(voices, list)
        assert len(voices) >= 1
        for v in voices:
            assert "voice_id" in v
            assert "name" in v

    def test_voices_parse_error_not_list(self) -> None:
        """Non-list response must be rejected."""
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError, match="not a list"):
            p._parse_voices({"not_voices": True})

    def test_voices_parse_error_missing_voice_id(self) -> None:
        """Voice entry without voice_id must be rejected."""
        p = ElevenLabsProvider()
        with pytest.raises(AdapterSchemaError, match="missing 'voice_id'"):
            p._parse_voices({"voices": [{"name": "Rachel"}]})
