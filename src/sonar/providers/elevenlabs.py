"""ElevenLabs adapter — text-to-speech via Monid.

Implements a :class:`VoiceProvider` protocol (not the mention-producing
:class:`~sonar.providers.base.Provider`) because this adapter produces
audio bytes, not Mention records.

D011 resolved CONTRACTS OQ-6: body carries ``text``, ``model_id``
(``eleven_flash_v2_5``) and ``voice_id``; the run output carries an
``audio`` object with a signed ``download_link``; ``audio_base64`` is
only present when the save failed and is a fallback, not the primary
path.  Billed units are characters; price is $0.05 / 1 000 characters.
A provider error inside a COMPLETED run yields no audio and no charge.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from sonar.config import (
    ELEVENLABS_ENDPOINT,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_PROVIDER,
    ELEVENLABS_USD_PER_1K_CHARS,
    ELEVENLABS_VOICES_ENDPOINT,
)
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS

log = logging.getLogger(__name__)

_TTS_INPUT_MISSING = "missing 'audio' object in provider response"
_AUDIO_OBJECT_MISSING = "missing 'download_link' or 'audio_base64' in audio object"
_VOICES_PARSE_ERROR = "voices response is not a list"
_VOICE_ENTRY_MISSING = "voice entry missing 'voice_id'"


@runtime_checkable
class VoiceProvider(Protocol):
    """Structural contract for adapters that produce audio, not mentions."""

    @property
    def provider(self) -> str: ...

    @property
    def endpoint(self) -> str: ...

    def build_input(self, text: str) -> dict[str, Any]: ...

    def download_audio(self, provider_response: dict[str, Any]) -> bytes: ...

    def estimate_cost(self, n_chars: int) -> float: ...


class ElevenLabsProvider:
    """ElevenLabs ``/text-to-speech`` adapter for Monid.

    Produces MP3 bytes via the ``VoiceProvider`` protocol.
    """

    @property
    def provider(self) -> str:
        return ELEVENLABS_PROVIDER

    @property
    def endpoint(self) -> str:
        return ELEVENLABS_ENDPOINT

    def build_input(self, text: str) -> dict[str, Any]:
        """Build the ``input.body`` payload for ``POST /v1/run``."""
        return {
            "body": {
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_id": "21m00Tcm4TlvDq8ikWAM",
            }
        }

    def download_audio(self, provider_response: dict[str, Any]) -> bytes:
        """Download MP3 bytes from the run output.

        Primary path: ``audio.download_link`` (signed URL, ~1 h expiry).
        Fallback: ``audio_base64`` (inline when Monid save failed).

        Raises :class:`AdapterSchemaError` when the provider response
        contains no usable audio data (e.g. a provider error inside a
        COMPLETED run).
        """
        audio = provider_response.get("audio")
        if not isinstance(audio, dict):
            raise AdapterSchemaError(
                ELEVENLABS_PROVIDER,
                ELEVENLABS_ENDPOINT,
                _TTS_INPUT_MISSING,
            )

        download_link = audio.get("download_link")
        if isinstance(download_link, str) and download_link:
            with httpx.Client(timeout=30) as client:
                resp = client.get(download_link)
                resp.raise_for_status()
                return resp.content

        audio_b64 = audio.get("audio_base64")
        if isinstance(audio_b64, str) and audio_b64:
            return base64.b64decode(audio_b64)

        raise AdapterSchemaError(
            ELEVENLABS_PROVIDER,
            ELEVENLABS_ENDPOINT,
            _AUDIO_OBJECT_MISSING,
        )

    def estimate_cost(self, n_chars: int) -> float:
        """Estimated USD cost for *n_chars* characters."""
        return (n_chars / 1000) * ELEVENLABS_USD_PER_1K_CHARS

    def list_voices(self, http_client: httpx.Client | None = None) -> list[dict[str, Any]]:
        """List available voices via Monid ``/voices`` endpoint.

        Returns a list of dicts each containing at least ``voice_id``.
        Pass an ``http_client`` for connection reuse; a temporary client
        is created when ``None``.
        """
        payload: dict[str, Any] = {"body": {}}
        if http_client is None:
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    "https://api.monid.ai/v1/run",
                    json={
                        "provider": ELEVENLABS_PROVIDER,
                        "endpoint": ELEVENLABS_VOICES_ENDPOINT,
                        "input": payload,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        else:
            resp = http_client.post(
                "https://api.monid.ai/v1/run",
                json={
                    "provider": ELEVENLABS_PROVIDER,
                    "endpoint": ELEVENLABS_VOICES_ENDPOINT,
                    "input": payload,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return self._parse_voices(data)

    def _parse_voices(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate and return the voices list from a Monid response body."""
        voices = data.get("voices") if isinstance(data, dict) else None
        if not isinstance(voices, list):
            raise AdapterSchemaError(
                ELEVENLABS_PROVIDER,
                ELEVENLABS_VOICES_ENDPOINT,
                _VOICES_PARSE_ERROR,
            )
        for entry in voices:
            if not isinstance(entry, dict) or "voice_id" not in entry:
                raise AdapterSchemaError(
                    ELEVENLABS_PROVIDER,
                    ELEVENLABS_VOICES_ENDPOINT,
                    _VOICE_ENTRY_MISSING,
                )
        return voices

    def resolve_voice(
        self,
        name: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> str:
        """Return a ``voice_id`` by name match or the first available voice."""
        voices = self.list_voices(http_client=http_client)
        if not voices:
            raise AdapterSchemaError(
                ELEVENLABS_PROVIDER,
                ELEVENLABS_VOICES_ENDPOINT,
                "no voices available",
            )
        if name is not None:
            for v in voices:
                if v.get("name") == name:
                    return str(v["voice_id"])
        return str(voices[0]["voice_id"])


ELEVENLABS = ElevenLabsProvider()

PROVIDERS["elevenlabs"] = ELEVENLABS  # type: ignore[assignment]
