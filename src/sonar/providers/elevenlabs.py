"""ElevenLabs adapter — text-to-speech via Monid.

Implements a :class:`VoiceProvider` protocol (not the mention-producing
:class:`~sonar.providers.base.Provider`) because this adapter produces
audio bytes, not Mention records.  It is therefore not registered in
:data:`sonar.providers.registry.PROVIDERS`, which is keyed by
:data:`~sonar.models.Source`.

D011 resolved CONTRACTS OQ-6: body carries ``text``, ``model_id``
(``eleven_flash_v2_5``) and ``voice_id``; the run output carries an
``audio`` object with a signed ``download_link``; ``audio_base64`` is
only present when the save failed and is a fallback, not the primary
path.  Billed units are characters; price is $0.05 / 1 000 characters.

Every Monid call this adapter makes (``/voices`` and ``/text-to-speech``)
goes through :class:`~sonar.monid.MonidClient` and
:class:`~sonar.monid.Ledger` so it has a ``RunRecord`` row and gets the
client's 429 backoff and 402 breaker (CONTRACTS §RunRecord: "Every Monid
call, including the ElevenLabs voice run ... has a row").

Two failure modes of a COMPLETED ``/text-to-speech`` run are kept apart:

* the documented provider error (unknown/unauthorized ``voice_id`` or an
  exhausted ElevenLabs quota — ``docs/monid/inspect/elevenlabs_text-to-
  speech.json`` notes) comes back as a COMPLETED run carrying the error
  as data, no audio, no charge.  :meth:`ElevenLabsProvider.parse_tts`
  returns it as :attr:`TtsResult.provider_error` and never raises;
* a payload with neither an ``audio`` object nor an error shape is
  schema drift and raises :class:`AdapterSchemaError`, the pipeline's
  ``schema_drift`` abstention signal.

Text is capped at ``NARRATION_MAX_CHARS`` (900, design "Voice: ≤ 900
chars") inside :meth:`ElevenLabsProvider.build_input`, and anything above
the provider ceiling of 5 000 characters is refused before any money is
spent.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from sonar.config import (
    ELEVENLABS_ENDPOINT,
    ELEVENLABS_MODEL_ID,
    ELEVENLABS_PROVIDER,
    ELEVENLABS_USD_PER_1K_CHARS,
    ELEVENLABS_VOICES_ENDPOINT,
    NARRATION_MAX_CHARS,
)
from sonar.monid import Ledger, MonidClient, RunRecord, RunRequest
from sonar.providers.base import AdapterSchemaError

log = logging.getLogger(__name__)

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
"""The inspect schema's default ``voice_id`` (Rachel); used when ``/voices`` yields nothing."""

PROVIDER_MAX_CHARS = 5000
"""Hard ceiling of ``/text-to-speech`` ``text`` (inspect ``maxLength``)."""

ERROR_MAX_CHARS = 500
"""Provider error excerpts are bounded like ``RunRecord.error``."""

_PROVIDER_ERROR_KEYS = ("error", "detail", "message")

_TTS_NOT_OBJECT = "expected object payload"
_TTS_INPUT_MISSING = "missing 'audio' object in provider response"
_AUDIO_EXPIRED = "audio object expired (Monid retention passed); re-run to regenerate"
_AUDIO_OBJECT_MISSING = "missing 'download_link' or 'audio_base64' in audio object"
_VOICES_PARSE_ERROR = "voices response is not a list"
_VOICE_ENTRY_MISSING = "voice entry missing 'voice_id'"


@dataclass(frozen=True)
class TtsResult:
    """What a COMPLETED ``/text-to-speech`` run produced.

    Exactly one of ``audio`` / ``provider_error`` is set.  ``provider_error``
    is the documented no-charge case (unknown voice, exhausted quota).
    """

    audio: bytes | None
    provider_error: str | None
    character_count: int | None

    @property
    def ok(self) -> bool:
        return self.audio is not None


@runtime_checkable
class VoiceProvider(Protocol):
    """Structural contract for adapters that produce audio, not mentions."""

    @property
    def provider(self) -> str: ...

    @property
    def endpoint(self) -> str: ...

    def build_input(self, text: str) -> dict[str, Any]: ...

    def parse_tts(self, provider_response: Any) -> TtsResult: ...

    def estimate_cost(self, n_chars: int) -> float: ...


def run_payload(body: Any) -> Any:
    """Return the provider payload inside a Monid run body.

    A run body wraps the provider's response under ``output``; a sync
    ``200`` may return the provider body directly.  Anything else is
    handed back unchanged for the parser to validate.
    """
    if isinstance(body, dict) and "output" in body:
        return body["output"]
    return body


def _error_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("status", "code", "message", "detail", "error"):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                parts.append(inner.strip())
        if parts:
            return ": ".join(parts)
    return None


def provider_error(payload: Any) -> str | None:
    """The provider error carried by a COMPLETED run, or ``None``.

    A payload that has an ``audio`` object is never an error.  Otherwise
    the first non-empty ``error`` / ``detail`` / ``message`` value (string
    or object with ``status``/``code``/``message``) is returned, truncated
    to ``ERROR_MAX_CHARS``.
    """
    if not isinstance(payload, dict) or isinstance(payload.get("audio"), dict):
        return None
    for key in _PROVIDER_ERROR_KEYS:
        text = _error_text(payload.get(key))
        if text is not None:
            return text[:ERROR_MAX_CHARS]
    return None


def _tts_counter(body: dict[str, Any] | None) -> int:
    payload = run_payload(body)
    return 1 if isinstance(payload, dict) and isinstance(payload.get("audio"), dict) else 0


def _voices_list(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        voices = payload.get("voices")
        if isinstance(voices, list):
            return voices
    return None


def _voices_counter(body: dict[str, Any] | None) -> int:
    voices = _voices_list(run_payload(body))
    return len(voices) if voices is not None else 0


class ElevenLabsProvider:
    """ElevenLabs ``/text-to-speech`` and ``/voices`` adapter for Monid."""

    @property
    def provider(self) -> str:
        return ELEVENLABS_PROVIDER

    @property
    def endpoint(self) -> str:
        return ELEVENLABS_ENDPOINT

    # -- input ----------------------------------------------------------------

    def build_input(self, text: str, voice_id: str | None = None) -> dict[str, Any]:
        """Build the ``input`` payload for ``POST /v1/run``.

        *text* is capped at ``NARRATION_MAX_CHARS``.  Text above
        ``PROVIDER_MAX_CHARS`` or empty text is refused with ``ValueError``
        before anything is submitted.
        """
        if not text.strip():
            raise ValueError("text-to-speech text is empty")
        if len(text) > PROVIDER_MAX_CHARS:
            raise ValueError(
                f"text-to-speech text is {len(text)} chars; provider ceiling is "
                f"{PROVIDER_MAX_CHARS} (narration budget is {NARRATION_MAX_CHARS})"
            )
        if len(text) > NARRATION_MAX_CHARS:
            log.warning("elevenlabs: text of %d chars capped to %d", len(text), NARRATION_MAX_CHARS)
            text = text[:NARRATION_MAX_CHARS]
        return {
            "body": {
                "text": text,
                "model_id": ELEVENLABS_MODEL_ID,
                "voice_id": voice_id or DEFAULT_VOICE_ID,
            }
        }

    def estimate_cost(self, n_chars: int) -> float:
        """Estimated USD cost for *n_chars* characters."""
        return (n_chars / 1000) * ELEVENLABS_USD_PER_1K_CHARS

    # -- text-to-speech -------------------------------------------------------

    def parse_tts(self, provider_response: Any) -> TtsResult:
        """Turn a COMPLETED run's provider payload into :class:`TtsResult`.

        Primary path: ``audio.download_link`` (signed URL, ~1 h expiry).
        Fallback: ``audio.audio_base64`` (inline when the Monid save failed).
        The documented provider error is returned as data; any other
        payload without a usable ``audio`` object raises
        :class:`AdapterSchemaError`.
        """
        if not isinstance(provider_response, dict):
            raise AdapterSchemaError(ELEVENLABS_PROVIDER, ELEVENLABS_ENDPOINT, _TTS_NOT_OBJECT)

        error = provider_error(provider_response)
        if error is not None:
            log.warning("elevenlabs: provider error in COMPLETED run: %s", error)
            return TtsResult(audio=None, provider_error=error, character_count=None)

        audio = provider_response.get("audio")
        if not isinstance(audio, dict):
            raise AdapterSchemaError(ELEVENLABS_PROVIDER, ELEVENLABS_ENDPOINT, _TTS_INPUT_MISSING)
        if audio.get("expired") is True:
            raise AdapterSchemaError(ELEVENLABS_PROVIDER, ELEVENLABS_ENDPOINT, _AUDIO_EXPIRED)

        count = audio.get("character_count")
        character_count = count if isinstance(count, int) and not isinstance(count, bool) else None

        download_link = audio.get("download_link")
        if isinstance(download_link, str) and download_link:
            with httpx.Client(timeout=30) as client:
                resp = client.get(download_link)
                resp.raise_for_status()
                return TtsResult(
                    audio=resp.content, provider_error=None, character_count=character_count
                )

        audio_b64 = audio.get("audio_base64")
        if isinstance(audio_b64, str) and audio_b64:
            return TtsResult(
                audio=base64.b64decode(audio_b64),
                provider_error=None,
                character_count=character_count,
            )

        raise AdapterSchemaError(ELEVENLABS_PROVIDER, ELEVENLABS_ENDPOINT, _AUDIO_OBJECT_MISSING)

    def synthesize(
        self,
        text: str,
        *,
        client: MonidClient,
        ledger: Ledger,
        voice_id: str | None = None,
        deadline_s: float = 120.0,
    ) -> tuple[RunRecord, TtsResult | None]:
        """Run ``/text-to-speech`` as a ledger run and parse its output.

        Returns the closed ``RunRecord`` and the parsed result, or ``None``
        for the result when the run did not succeed (its ``LOCAL_*`` or
        Monid failure status is on the record).  Raises
        :class:`~sonar.monid.MonidHalted` when the 402 breaker is tripped
        and :class:`~sonar.monid.AlreadySubmitted` when this exact input
        already holds a run id in *ledger*.
        """
        payload = self.build_input(text, voice_id)
        request = RunRequest(ELEVENLABS_PROVIDER, ELEVENLABS_ENDPOINT, payload)
        record, outcome = ledger.submit(
            client,
            request,
            brand=None,
            source=None,
            estimate_usd=self.estimate_cost(len(payload["body"]["text"])),
            deadline_s=deadline_s,
            counter=_tts_counter,
        )
        if not outcome.succeeded:
            log.warning("elevenlabs: text-to-speech run %s: %s", outcome.status, outcome.error)
            return record, None
        return record, self.parse_tts(run_payload(outcome.body))

    # -- voices ---------------------------------------------------------------

    def list_voices(
        self,
        client: MonidClient,
        ledger: Ledger,
        *,
        deadline_s: float = 60.0,
    ) -> list[dict[str, Any]] | None:
        """Run the free ``/voices`` endpoint as a ledger run.

        Returns the voice entries (each with at least ``voice_id``), or
        ``None`` when the run did not succeed (status on the ledger row).
        Raises :class:`AdapterSchemaError` on an unexpected payload shape,
        :class:`~sonar.monid.MonidHalted` when the breaker is tripped and
        :class:`~sonar.monid.AlreadySubmitted` on a second call against
        the same ledger (the input is constant, so its digest is too).
        """
        request = RunRequest(ELEVENLABS_PROVIDER, ELEVENLABS_VOICES_ENDPOINT, {})
        _record, outcome = ledger.submit(
            client,
            request,
            brand=None,
            source=None,
            estimate_usd=0.0,
            deadline_s=deadline_s,
            counter=_voices_counter,
        )
        if not outcome.succeeded:
            log.warning("elevenlabs: voices run %s: %s", outcome.status, outcome.error)
            return None
        return self.parse_voices(run_payload(outcome.body))

    def parse_voices(self, payload: Any) -> list[dict[str, Any]]:
        """Validate and return the voices list from a ``/voices`` payload.

        Accepts either ``{"voices": [...]}`` or a bare list.
        """
        voices = _voices_list(payload)
        if voices is None:
            raise AdapterSchemaError(
                ELEVENLABS_PROVIDER, ELEVENLABS_VOICES_ENDPOINT, _VOICES_PARSE_ERROR
            )
        out: list[dict[str, Any]] = []
        for entry in voices:
            if not isinstance(entry, dict) or not isinstance(entry.get("voice_id"), str):
                raise AdapterSchemaError(
                    ELEVENLABS_PROVIDER, ELEVENLABS_VOICES_ENDPOINT, _VOICE_ENTRY_MISSING
                )
            out.append(entry)
        return out

    def resolve_voice(
        self,
        name: str | None = None,
        *,
        client: MonidClient,
        ledger: Ledger,
    ) -> str:
        """Pick a ``voice_id``: by *name*, else the first listed, else the default.

        Falls back to ``DEFAULT_VOICE_ID`` when the ``/voices`` run did not
        succeed or listed nothing, so a voice lookup failure never blocks
        narration (design: "ElevenLabs fails | no mp3, rest complete").
        """
        voices = self.list_voices(client, ledger)
        if not voices:
            log.warning("elevenlabs: no voices listed; using default %s", DEFAULT_VOICE_ID)
            return DEFAULT_VOICE_ID
        if name is not None:
            for entry in voices:
                if entry.get("name") == name:
                    return str(entry["voice_id"])
            log.warning("elevenlabs: voice %r not listed; using first voice", name)
        return str(voices[0]["voice_id"])


ELEVENLABS = ElevenLabsProvider()
