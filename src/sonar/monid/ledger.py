"""Open-before-POST ledger (``runs.jsonl``) and reconciliation against ``GET /v1/runs``.

Every Monid call gets a ``RunRecord`` row *before* the POST leaves the process,
with ``run_id=null``. The row is closed after the client returns, keyed by
``local_seq``. The file is append-only: an update is a new line with the same
``local_seq``; the last line per ``local_seq`` wins on load. A run that ever
received an id is never resubmitted through this ledger (``AlreadySubmitted``).

``RunRecord`` follows CONTRACTS §RunRecord field-for-field. ``src/sonar/models.py``
(W2.1) is the package-wide home for records; when it lands, this module can
import ``RunRecord`` from there instead of defining it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from sonar.monid.client import (
    FAILURE_STATUSES,
    MonidClient,
    MonidHalted,
    MonidHTTPError,
    RunOutcome,
    RunRequest,
)

CostSource = Literal["/v1/runs", "unreconciled"]

LOCAL_PENDING = "LOCAL_PENDING"
LOCAL_DEADLINE = "LOCAL_DEADLINE"
LOCAL_BACKOFF_EXHAUSTED = "LOCAL_BACKOFF_EXHAUSTED"
LOCAL_PREFIX = "LOCAL_"

REMOTE_TIMESTAMP_KEYS = ("createdAt", "startedAt", "submittedAt", "created_at")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunRecord(BaseModel):
    """One ledger row. Wire names as in CONTRACTS §RunRecord."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    local_seq: int = Field(ge=1)
    run_id: str | None
    provider: str
    endpoint: str
    brand: str | None
    source: str | None
    input_digest: str
    submitted_at: datetime
    completed_at: datetime | None
    status: str
    provider_http_status: int | None
    n_results: int | None
    estimate_usd: float
    cost_usd: float | None
    billed_units: int | None
    cost_source: CostSource
    attempts: int = Field(ge=1)
    error: str | None

    @field_serializer("submitted_at", "completed_at")
    def _serialize_dt(self, value: datetime | None) -> str | None:
        return _iso(value)

    @property
    def is_local(self) -> bool:
        return self.status.startswith(LOCAL_PREFIX)

    @property
    def is_failed(self) -> bool:
        return self.is_local or self.status.upper() in FAILURE_STATUSES


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

    # -- views ------------------------------------------------------------

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
        source: str | None,
        estimate_usd: float,
    ) -> RunRecord:
        """Write the pre-POST row (``run_id=null``, status ``LOCAL_PENDING``)."""
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
                status=LOCAL_PENDING,
                provider_http_status=None,
                n_results=None,
                estimate_usd=estimate_usd,
                cost_usd=None,
                billed_units=None,
                cost_source="unreconciled",
                attempts=1,
                error=None,
            )
        )

    def close(self, local_seq: int, outcome: RunOutcome, n_results: int | None) -> RunRecord:
        """Rewrite the row with what the client observed. ``n_results`` is ignored unless terminal."""
        record = self._records[local_seq]
        terminal = outcome.completed or (
            outcome.run_id is None and outcome.status.startswith(LOCAL_PREFIX)
        )
        return self._append(
            record.model_copy(
                update={
                    "run_id": outcome.run_id,
                    "status": outcome.status,
                    "completed_at": self._now() if outcome.completed else None,
                    "provider_http_status": outcome.provider_http_status,
                    "n_results": (n_results if n_results is not None else 0) if terminal else None,
                    "attempts": outcome.attempts,
                    "error": outcome.error,
                }
            )
        )

    def submit(
        self,
        client: MonidClient,
        request: RunRequest,
        *,
        brand: str | None,
        source: str | None,
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

    # -- reconcile --------------------------------------------------------

    def reconcile(
        self,
        client: MonidClient,
        *,
        started_at: datetime | None = None,
        reconciled_at: datetime | None = None,
        listing: Iterable[dict[str, Any]] | None = None,
    ) -> ReconcileResult:
        """Join ``GET /v1/runs`` onto the ledger by run id and copy billed fields.

        On a listing failure nothing is written; ``fetched_at`` is ``None`` and every
        row is reported unreconciled (receipt verdict PARTIAL, exit 4 upstream).
        """
        try:
            items = list(client.list_runs() if listing is None else listing)
        except MonidHTTPError as exc:
            return ReconcileResult(
                fetched_at=None,
                n_listed_in_window=0,
                unmatched_remote_run_ids=[],
                unreconciled_local_seqs=[
                    r.local_seq for r in self.records if r.cost_source != "/v1/runs"
                ],
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
                record.model_copy(
                    update={
                        "cost_usd": cost,
                        "billed_units": _remote_int(remote, "billedUnits"),
                        "status": status,
                        "provider_http_status": provider_status
                        if provider_status is not None
                        else record.provider_http_status,
                        "cost_source": "/v1/runs",
                    }
                )
            )

        # A run_id=null row reconciles to $0 only when the listing window is closed
        # (started_at given) and no unmatched remote run could be that row
        # (CONTRACTS §Receipt verdict rule).
        if started_at is not None and not unmatched_remote:
            for record in self.records:
                if record.run_id is None and record.cost_source != "/v1/runs":
                    if record.submitted_at < started_at:
                        continue
                    self._append(
                        record.model_copy(
                            update={"cost_usd": 0.0, "billed_units": 0, "cost_source": "/v1/runs"}
                        )
                    )

        return ReconcileResult(
            fetched_at=fetched_at,
            n_listed_in_window=len(in_window),
            unmatched_remote_run_ids=unmatched_remote,
            unreconciled_local_seqs=[
                r.local_seq for r in self.records if r.cost_source != "/v1/runs"
            ],
            error=None,
        )


def load_ledger(path: Path | str) -> list[RunRecord]:
    """Read-only helper for receipt building."""
    return Ledger(path).records


__all__ = [
    "LOCAL_BACKOFF_EXHAUSTED",
    "LOCAL_DEADLINE",
    "LOCAL_PENDING",
    "AlreadySubmitted",
    "CostSource",
    "Ledger",
    "ReconcileResult",
    "RunRecord",
    "count_results",
    "load_ledger",
    "utcnow",
]
