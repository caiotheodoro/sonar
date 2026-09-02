"""Voice layer: script the digest, gate its numbers, voice it (D006, D011).

:func:`narrate` is the pipeline entry: Digest → :class:`~sonar.models.Narration`
with ``mp3_path`` and ``local_seq`` set when the ElevenLabs run succeeded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sonar.llm.base import LlmBackend, LlmError, Usage
from sonar.models import Abstention, Digest, Narration, RunRecord
from sonar.monid import Ledger, MonidClient
from sonar.providers.elevenlabs import ELEVENLABS
from sonar.report.digest import NO_NARRATION
from sonar.voice.script import (
    GateResult,
    NarrationSchema,
    ScriptResult,
    digest_numbers,
    extract_numbers,
    numbers_gate,
    regate,
    write_script,
)
from sonar.voice.tts import BRIEF_MP3_FILENAME, TtsAdapter, TtsOutcome, synthesize_narration

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceResult:
    """What ``narrate`` produced: the narration, seam usage, the voice run row, abstentions."""

    narration: Narration
    usage: tuple[Usage, ...]
    record: RunRecord | None
    abstentions: tuple[Abstention, ...]


def narrate(
    digest: Digest,
    *,
    backend: LlmBackend,
    client: MonidClient,
    ledger: Ledger,
    out_dir: Path,
    model: str | None = None,
    adapter: TtsAdapter = ELEVENLABS,
    voice_id: str | None = None,
) -> VoiceResult:
    """Script, gate and voice *digest*; never raises on seam or Monid failure.

    A seam failure yields no narration and a ``voice``/``provider_failed``
    abstention. A narration that fails the numbers gate twice is kept as text
    with ``numbers_verified=false`` and is not voiced.
    """
    try:
        script = write_script(digest, backend=backend, model=model)
    except LlmError as exc:
        log.warning("voice: narration call failed: %s", exc)
        abstention = Abstention(
            scope="voice",
            brand=None,
            source=None,
            reason="provider_failed",
            detail=f"narration: {exc}"[:500],
        )
        return VoiceResult(NO_NARRATION, (), None, (abstention,))
    if script.foreign:
        log.warning(
            "voice: numbers not in digest after %d attempts: %s", script.attempts, script.foreign
        )
    outcome = synthesize_narration(
        script.narration,
        client=client,
        ledger=ledger,
        out_dir=out_dir,
        adapter=adapter,
        voice_id=voice_id,
    )
    abstentions = (outcome.abstention,) if outcome.abstention is not None else ()
    return VoiceResult(outcome.narration, script.usage, outcome.record, abstentions)


__all__ = [
    "BRIEF_MP3_FILENAME",
    "NO_NARRATION",
    "GateResult",
    "NarrationSchema",
    "ScriptResult",
    "TtsAdapter",
    "TtsOutcome",
    "VoiceResult",
    "digest_numbers",
    "extract_numbers",
    "narrate",
    "numbers_gate",
    "regate",
    "synthesize_narration",
    "write_script",
]
