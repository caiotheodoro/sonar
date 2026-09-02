"""Text-to-speech via the ElevenLabs adapter.

Turns narration text into MP3 bytes through the ElevenLabs adapter
(``src/sonar/providers/elevenlabs.py``) so the run lands in the ledger.

Design: "one ElevenLabs Monid run in the ledger."
"""

from __future__ import annotations

from sonar.providers.elevenlabs import (
    ELEVENLABS,
    ElevenLabsProvider,
)


def synthesize_narration(
    text: str,
    *,
    provider: ElevenLabsProvider = ELEVENLABS,
    voice_id: str | None = None,
) -> dict[str, object]:
    """Build the Monid input payload for a narration TTS run.

    Returns the dict that should be passed to ``ledger.submit`` as the
    ``RunRequest.input`` body.  The actual HTTP call is made by the
    pipeline layer, which owns the ``MonidClient`` and ``Ledger``.

    This function validates the text and builds the payload without
    touching the network, keeping the voice layer testable offline.
    """
    return provider.build_input(text, voice_id)
