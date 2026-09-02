"""Open-before-POST ledger (``runs.jsonl``) and reconciliation against ``GET /v1/runs``.

Every Monid call gets a ``RunRecord`` row *before* the POST leaves the process,
with ``run_id=null``. The row is closed after the client returns, keyed by
``local_seq``. The file is append-only: an update is a new line with the same
``local_seq``; the last line per ``local_seq`` wins on load. A run that ever
received an id is never resubmitted through this ledger (``AlreadySubmitted``).

``RunRecord`` and ``CostSource`` are imported from ``sonar.models``, the
package-wide home for wire records; every row written here passes that
model's validators (CONTRACTS §RunRecord, D012 F12/F13, D013 N6). In short:

* ``run_id=null`` rows are ``cost_source="local"`` with ``cost_usd=0.0`` at
  write time — every ``LOCAL_*`` failure without an id and a succeeded ``$0``
  sync run that returned no id (OQ-2). They never appear in
  ``unreconciled_local_seqs``.
* rows with a ``run_id`` are ``unreconciled`` (``cost_usd=null``) until the
  listing shows them; ``LOCAL_DEADLINE`` keeps its id and stays unreconciled.
* a local row counts as failed iff its status starts with ``LOCAL_``
  (:func:`is_failed`).

The pre-POST row carries the Monid pending status ``PENDING`` rather than a
``LOCAL_`` value: CONTRACTS enumerates the local statuses exhaustively as
``LOCAL_REJECTED_<http>``, ``LOCAL_BACKOFF_EXHAUSTED`` and ``LOCAL_DEADLINE``,
and ``sonar.models.RunRecord`` rejects any other ``LOCAL_`` value. A row left
at ``PENDING`` after a crash between ``open`` and ``close`` therefore reads as
a run that never reached a terminal state, ``run_id=null``, local, ``$0``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sonar.models import CostSource, RunRecord, Source
from sonar.monid.client import (
    FAILURE_STATUSES,
    MonidClient,
    MonidHalted,
    MonidHTTPError,
    RunOutcome,
    RunRequest,
)

PENDING = "PENDING"
# Name kept for the ``sonar.monid`` re-export; the value is the pre-POST status above.
LOCAL_PENDING = PENDING
LOCAL_DEADLINE = "LOCAL_DEADLINE"
LOCAL_BACKOFF_EXHAUSTED = "LOCAL_BACKOFF_EXHAUSTED"
LOCAL_PREFIX = "LOCAL_"

REMOTE_TIMESTAMP_KEYS = ("createdAt", "startedAt", "submittedAt", "created_at")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def is_failed(record: RunRecord) -> bool:
    """D013 N6: a row is failed iff its status starts with ``LOCAL_`` or is a Monid failure state.

    A succeeded run with ``run_id=null`` from a sync endpoint is ``local`` and not failed.
    """
    return record.status.startswith(LOCAL_PREFIX) or record.status.upper() in FAILURE_STATUSES


def _updated(record: RunRecord, **changes: Any) -> RunRecord:
    """Copy with changes, re-running the model validators (``model_copy`` would skip them)."""
    return RunRecord.model_validate({**record.model_dump(), **changes})


class AlreadySubmitted(Exception):
    """A record with this ``input_digest`` already holds a Monid run id."""

    def __init__(self, record: RunRecord) -> None:
        self.record = record
        super().__init__(
            f"local_seq {record.local_seq} already has run_id {record.run_id} "
            f"(status {record.status}); not resubmitting"
        )


@dataclass
class ReconcileResult:
    """Outcome of ``Ledger.reconcile``; maps onto ``Receipt.reconciliation``."""

    fetched_at: datetime | None
    n_listed_in_window: int
    unmatched_remote_run_ids: list[str] = field(default_factory=list)
    unreconciled_local_seqs: list[int] = field(default_factory=list)
    error: str | None = None


def count_results(body: dict[str, Any] | None) -> int:
    """Generic item count: the first top-level list under output/results/items/data, else 0.

    Adapters that know the payload shape pass their own counter to ``Ledger.submit``.
    """
    if not body:
        return 0
    for key in ("output", "results", "items", "data"):
        value = body.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            for inner_key in ("results", "items", "data"):
                inner = value.get(inner_key)
                if isinstance(inner, list):
                    return len(inner)
    return 0


def _parse_remote_ts(item: dict[str, Any]) -> datetime | None:
    for key in REMOTE_TIMESTAMP_KEYS:
        raw = item.get(key)
        if isinstance(raw, str) and raw:
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        if isinstance(raw, (int, float)):
            seconds = float(raw) / (1000.0 if raw > 1e11 else 1.0)
            return datetime.fromtimestamp(seconds, tz=UTC)
    return None


def _remote_cost(item: dict[str, Any]) -> float | None:
    cost = item.get("cost")
    if isinstance(cost, dict):
        value = cost.get("value")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _remote_int(item: dict[str, Any], key: str) -> int | None:
    value = item.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _remote_provider_status(item: dict[str, Any]) -> int | None:
    provider = item.get("providerResponse")
    if isinstance(provider, dict):
        return _remote_int(provider, "httpStatus")
    return None


def _remote_run_id(item: dict[str, Any]) -> str | None:
    for key in ("runId", "run_id", "id"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


class Ledger:
    """Append-only ``runs.jsonl`` with in-memory last-wins view keyed by ``local_seq``."""

    def __init__(self, path: Path | str, *, now: Callable[[], datetime] = utcnow) -> None:
        self.path = Path(path)
        self._now = now
        self._records: dict[int, RunRecord] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = RunRecord.model_validate_json(line)
                    self._records[record.local_seq] = record

    @property
    def records(self) -> list[RunRecord]:
        return [self._records[seq] for seq in sorted(self._records)]

    def get(self, local_seq: int) -> RunRecord:
        return self._records[local_seq]

    def find_submitted(self, digest: str) -> RunRecord | None:
        """The record for this input digest that already holds a run id, if any."""
        for record in self.records:
            if record.input_digest == digest and record.run_id is not None:
                return record
        return None

    def unreconciled_seqs(self) -> list[int]:
        """Rows with a ``run_id`` not yet matched in the listing; never a ``local`` row (D012 F13)."""
        return [r.local_seq for r in self.records if r.cost_source == "unreconciled"]

    # -- writes -----------------------------------------------------------

    def _append(self, record: RunRecord) -> RunRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(record.model_dump_json() + "\n")
        self._records[record.local_seq] = record
        return record

    def open(
        self,
        request: RunRequest,
        *,
        brand: str | None,
        source: Source | None,
        estimate_usd: float,
    ) -> RunRecord:
        """Write the pre-POST row (``run_id=null``, status ``PENDING``, local ``$0`` by construction)."""
        seq = max(self._records, default=0) + 1
        return self._append(
            RunRecord(
                local_seq=seq,
                run_id=None,
                provider=request.provider,
                endpoint=request.endpoint,
                brand=brand,
                source=source,
                input_digest=request.digest,
                submitted_at=self._now(),
                completed_at=None,
                status=PENDING,
                provider_http_status=None,
                n_results=None,
                estimate_usd=estimate_usd,
                cost_usd=0.0,
                billed_units=None,
                cost_source="local",
                attempts=1,
                error=None,
            )
        )

    def close(self, local_seq: int, outcome: RunOutcome, n_results: int | None) -> RunRecord:
        """Rewrite the row with what the client observed. ``n_results`` is ignored unless terminal.

        ``cost_source`` is settled here, at write time: a row without a ``run_id`` is
        ``local`` with ``cost_usd=0.0`` (it was never accepted by Monid, so the listing
        can never price it); a row with a ``run_id`` — including ``LOCAL_DEADLINE``,
        which keeps its id — is ``unreconciled`` until :meth:`reconcile` matches it.
        """
        record = self._records[local_seq]
        terminal = outcome.completed or (
            outcome.run_id is None and outcome.status.startswith(LOCAL_PREFIX)
        )
        local = outcome.run_id is None
        cost_source: CostSource = "local" if local else "unreconciled"
        return self._append(
            _updated(
                record,
                run_id=outcome.run_id,
                status=outcome.status,
                completed_at=self._now() if outcome.completed else None,
                provider_http_status=outcome.provider_http_status,
                n_results=(n_results if n_results is not None else 0) if terminal else None,
                attempts=outcome.attempts,
                error=outcome.error,
                cost_usd=0.0 if local else None,
                billed_units=None,
                cost_source=cost_source,
            )
        )

    def submit(
        self,
        client: MonidClient,
        request: RunRequest,
        *,
        brand: str | None,
        source: Source | None,
        estimate_usd: float,
        deadline_s: float = 300.0,
        counter: Callable[[dict[str, Any] | None], int] = count_results,
    ) -> tuple[RunRecord, RunOutcome]:
        """open → POST/poll → close. Refuses to resubmit an input that already has a run id."""
        existing = self.find_submitted(request.digest)
        if existing is not None:
            raise AlreadySubmitted(existing)
        if client.halted:
            raise MonidHalted(client.breaker.reason or "breaker tripped")
        opened = self.open(request, brand=brand, source=source, estimate_usd=estimate_usd)
        outcome = client.run(request, deadline_s=deadline_s)
        n_results = counter(outcome.body) if outcome.succeeded else 0
        return self.close(opened.local_seq, outcome, n_results), outcome

    def reconcile(
        self,
        client: MonidClient,
        *,
        started_at: datetime | None = None,
        reconciled_at: datetime | None = None,
        listing: Iterable[dict[str, Any]] | None = None,
    ) -> ReconcileResult:
        """Join ``GET /v1/runs`` onto the ledger by run id and copy billed fields.

        Only rows with a ``run_id`` take part; ``local`` rows were settled at write
        time and are never listed as unreconciled. On a listing failure nothing is
        written; ``fetched_at`` is ``None`` and every row with a ``run_id`` still
        unmatched is reported (receipt verdict PARTIAL, exit 4 upstream).
        """
        try:
            items = list(client.list_runs() if listing is None else listing)
        except MonidHTTPError as exc:
            return ReconcileResult(
                fetched_at=None,
                n_listed_in_window=0,
                unmatched_remote_run_ids=[],
                unreconciled_local_seqs=self.unreconciled_seqs(),
                error=str(exc),
            )
        fetched_at = self._now()
        window_end = reconciled_at or fetched_at
        in_window: dict[str, dict[str, Any]] = {}
        for item in items:
            run_id = _remote_run_id(item)
            if run_id is None:
                continue
            ts = _parse_remote_ts(item)
            if ts is not None and started_at is not None and ts < started_at:
                continue
            if ts is not None and ts > window_end:
                continue
            in_window[run_id] = item

        local_ids = {r.run_id for r in self.records if r.run_id is not None}
        unmatched_remote = sorted(rid for rid in in_window if rid not in local_ids)

        for record in self.records:
            if record.run_id is None:
                continue
            remote = in_window.get(record.run_id)
            if remote is None:
                continue
            cost = _remote_cost(remote)
            if cost is None:
                continue
            remote_status = remote.get("status")
            status = (
                remote_status if isinstance(remote_status, str) and remote_status else record.status
            )
            provider_status = _remote_provider_status(remote)
            self._append(
                _updated(
                    record,
                    cost_usd=cost,
                    billed_units=_remote_int(remote, "billedUnits"),
                    status=status,
                    provider_http_status=provider_status
                    if provider_status is not None
                    else record.provider_http_status,
                    cost_source="/v1/runs",
                )
            )

        return ReconcileResult(
            fetched_at=fetched_at,
            n_listed_in_window=len(in_window),
            unmatched_remote_run_ids=unmatched_remote,
            unreconciled_local_seqs=self.unreconciled_seqs(),
            error=None,
        )


def load_ledger(path: Path | str) -> list[RunRecord]:
    """Read-only helper for receipt building."""
    return Ledger(path).records


__all__ = [
    "LOCAL_BACKOFF_EXHAUSTED",
    "LOCAL_DEADLINE",
    "LOCAL_PENDING",
    "PENDING",
    "AlreadySubmitted",
    "CostSource",
    "Ledger",
    "ReconcileResult",
    "RunRecord",
    "count_results",
    "is_failed",
    "load_ledger",
    "utcnow",
]
