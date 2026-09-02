"""Narration to MP3 through the ElevenLabs adapter, as one ledger run.

The adapter (:mod:`sonar.providers.elevenlabs`) owns the Monid call and its
``RunRecord`` row; this module decides whether to spend at all (only a
narration whose numbers are verified is voiced), writes the bytes to
``<out_dir>/brief.mp3`` (D011) and fills ``mp3_path`` / ``local_seq`` on the
:class:`~sonar.models.Narration`. Any failure leaves the narration text in
place without audio (design error matrix: "ElevenLabs fails | no mp3, rest
complete") and names the reason as a ``voice``-scoped abstention.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sonar.models import AbstainReason, Abstention, Narration, RunRecord
from sonar.monid import LOCAL_DEADLINE, AlreadySubmitted, Ledger, MonidClient, MonidHalted
from sonar.providers.base import AdapterSchemaError
from sonar.providers.elevenlabs import ELEVENLABS, TtsResult

log = logging.getLogger(__name__)

BRIEF_MP3_FILENAME = "brief.mp3"
"""Where the narration audio lands inside the session output directory (D011).

``Narration.mp3_path`` stores this session-relative name, never an absolute
path, so a published ``digest.json`` carries no machine path; it resolves
against the session directory (``out/<session>/brief.mp3``).
"""


class TtsAdapter(Protocol):
    """What the voice layer needs from the ElevenLabs adapter; tests pass a stub."""

    def synthesize(
        self,
        text: str,
        *,
        client: MonidClient,
        ledger: Ledger,
        voice_id: str | None = None,
    ) -> tuple[RunRecord, TtsResult | None]: ...


@dataclass(frozen=True)
class TtsOutcome:
    """The narration after the voice run, the ledger row (if one was opened), the abstention."""

    narration: Narration
    record: RunRecord | None
    abstention: Abstention | None

    @property
    def voiced(self) -> bool:
        return self.narration.mp3_path is not None


def _abstain(reason: AbstainReason, detail: str) -> Abstention:
    return Abstention(scope="voice", brand=None, source=None, reason=reason, detail=detail[:500])


def _run_failure_reason(record: RunRecord) -> AbstainReason:
    if record.status == LOCAL_DEADLINE:
        return "deadline"
    if record.status == "LOCAL_REJECTED_429":
        return "rate_limited"
    return "provider_failed"


def synthesize_narration(
    narration: Narration,
    *,
    client: MonidClient,
    ledger: Ledger,
    out_dir: Path,
    adapter: TtsAdapter = ELEVENLABS,
    voice_id: str | None = None,
) -> TtsOutcome:
    """Voice a verified narration; return it with ``mp3_path`` and ``local_seq`` set.

    ``mp3_path`` is the session-relative :data:`BRIEF_MP3_FILENAME`; the bytes
    are written to ``<out_dir>/brief.mp3``. A narration without text is skipped silently; one whose numbers are not
    verified is skipped without spending, and the outcome says so. Failures
    of the run itself are returned as abstentions, never raised.
    """
    if narration.text is None:
        return TtsOutcome(narration=narration, record=None, abstention=None)
    if not narration.numbers_verified:
        log.warning("voice: narration numbers not verified; no audio produced")
        return TtsOutcome(narration=narration, record=None, abstention=None)

    try:
        record, result = adapter.synthesize(
            narration.text, client=client, ledger=ledger, voice_id=voice_id
        )
    except MonidHalted as exc:
        return TtsOutcome(narration, None, _abstain("halted", str(exc)))
    except AlreadySubmitted as exc:
        return TtsOutcome(narration, exc.record, _abstain("provider_failed", str(exc)))
    except AdapterSchemaError as exc:
        return TtsOutcome(narration, None, _abstain("schema_drift", str(exc)))

    if result is None:
        detail = record.error or f"text-to-speech run {record.status}"
        return TtsOutcome(narration, record, _abstain(_run_failure_reason(record), detail))
    if result.audio is None:
        detail = result.provider_error or "text-to-speech run returned no audio"
        return TtsOutcome(narration, record, _abstain("provider_failed", detail))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / BRIEF_MP3_FILENAME
    path.write_bytes(result.audio)
    voiced = narration.model_copy(
        update={"mp3_path": BRIEF_MP3_FILENAME, "local_seq": record.local_seq}
    )
    return TtsOutcome(narration=voiced, record=record, abstention=None)


__all__ = ["BRIEF_MP3_FILENAME", "TtsAdapter", "TtsOutcome", "synthesize_narration"]
