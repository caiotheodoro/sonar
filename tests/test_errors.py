"""Monid transport error matrix with a stub httpx transport. No network."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from sonar.monid import (
    BREAKER,
    AlreadySubmitted,
    Ledger,
    MonidClient,
    MonidHalted,
    RunRecord,
    RunRequest,
)

Handler = Callable[[httpx.Request], httpx.Response]


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
    """Serves scripted responses per (method, path); records every request."""

    responses: dict[tuple[str, str], list[httpx.Response]]
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        queue = self.responses.get(key)
        if not queue:
            return httpx.Response(500, json={"error": f"unscripted {key}"})
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


def make_client(script: Script, clock: FakeClock) -> MonidClient:
    return MonidClient(
        "monid_test_key",
        transport=httpx.MockTransport(script),
        sleep=clock.sleep,
        clock=clock.monotonic,
        poll_initial_s=1.0,
        poll_max_s=4.0,
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


REQUEST = RunRequest(
    "apify", "/trudax/reddit-scraper-lite", {"searches": ["Nubank"], "maxItems": 5}
)


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# -- 429 → 429 → 200 ------------------------------------------------------


def test_rate_limit_backs_off_then_succeeds(ledger: Ledger, clock: FakeClock) -> None:
    script = Script(
        {
            ("POST", "/v1/run"): [
                httpx.Response(429, json={"error": "slow down"}),
                httpx.Response(429, json={"error": "slow down"}, headers={"Retry-After": "7"}),
                httpx.Response(
                    200,
                    json={
                        "runId": "run_sync_1",
                        "status": "SUCCEEDED",
                        "providerResponse": {"httpStatus": 200},
                        "output": [{"id": 1}, {"id": 2}, {"id": 3}],
                    },
                ),
            ]
        }
    )
    client = make_client(script, clock)
    record, outcome = ledger.submit(
        client, REQUEST, brand="Nubank", source="reddit", estimate_usd=0.05
    )
    assert len(script.posts()) == 3
    assert clock.sleeps == [2.0, 7.0], "first backoff is 2s, second honours Retry-After"
    assert outcome.attempts == 3
    assert record.status == "SUCCEEDED"
    assert record.run_id == "run_sync_1"
    assert record.provider_http_status == 200
    assert record.n_results == 3
    assert record.attempts == 3
    assert record.error is None
    assert record.cost_usd is None and record.cost_source == "unreconciled"
    for request in script.posts():
        assert request.headers["Authorization"] == "Bearer monid_test_key"
        assert json.loads(request.content) == REQUEST.body()

    lines = read_lines(ledger.path)
    assert [line["run_id"] for line in lines] == [None, "run_sync_1"]
    assert lines[0]["status"] == "LOCAL_PENDING"
    assert lines[0]["local_seq"] == lines[1]["local_seq"] == 1
    assert lines[1]["submitted_at"].endswith("Z")


def test_rate_limit_exhausts_after_four_retries(ledger: Ledger, clock: FakeClock) -> None:
    script = Script({("POST", "/v1/run"): [httpx.Response(429, text="busy")]})
    client = make_client(script, clock)
    record, _ = ledger.submit(client, REQUEST, brand="b", source="reddit", estimate_usd=0.0)
    assert len(script.posts()) == 5
    assert clock.sleeps == [2.0, 4.0, 8.0, 16.0]
    assert record.status == "LOCAL_BACKOFF_EXHAUSTED"
    assert record.run_id is None
    assert record.attempts == 5
    assert record.n_results == 0
    assert record.error == "busy"
    assert not BREAKER.tripped


# -- 402 breaker ----------------------------------------------------------


def test_402_trips_breaker_and_blocks_further_posts(
    ledger: Ledger, clock: FakeClock, tmp_path: Path
) -> None:
    script = Script(
        {("POST", "/v1/run"): [httpx.Response(402, json={"error": "insufficient credit"})]}
    )
    client = make_client(script, clock)
    record, _ = ledger.submit(client, REQUEST, brand="b", source="reddit", estimate_usd=0.1)
    assert record.status == "LOCAL_REJECTED_402"
    assert record.run_id is None
    assert "insufficient credit" in (record.error or "")
    assert BREAKER.tripped and client.halted

    second = RunRequest("apify", "/streamers/youtube-scraper", {"searchQueries": ["Nubank"]})
    with pytest.raises(MonidHalted):
        ledger.submit(client, second, brand="b", source="youtube", estimate_usd=0.1)
    assert len(script.posts()) == 1, "no POST after the breaker tripped"
    assert len(ledger.records) == 1, "a halted call writes no ledger row"

    # Process-wide: a fresh client on another ledger is halted too.
    other = make_client(Script({("POST", "/v1/run"): [httpx.Response(200, json={})]}), clock)
    with pytest.raises(MonidHalted):
        other.run(REQUEST)
    with pytest.raises(MonidHalted):
        Ledger(tmp_path / "other.jsonl").submit(
            other, REQUEST, brand="b", source="reddit", estimate_usd=0.0
        )


# -- deadline: abstain, keep id, never resubmit -----------------------------


def test_deadline_keeps_run_id_and_never_resubmits(ledger: Ledger, clock: FakeClock) -> None:
    script = Script(
        {
            ("POST", "/v1/run"): [httpx.Response(202, json={"runId": "run_async_9"})],
            ("GET", "/v1/runs/run_async_9"): [
                httpx.Response(200, json={"runId": "run_async_9", "status": "RUNNING"})
            ],
        }
    )
    client = make_client(script, clock)
    record, outcome = ledger.submit(
        client, REQUEST, brand="b", source="reddit", estimate_usd=0.2, deadline_s=10.0
    )
    assert outcome.completed is False
    assert record.status == "LOCAL_DEADLINE"
    assert record.run_id == "run_async_9"
    assert record.completed_at is None
    assert record.n_results is None
    assert record.cost_source == "unreconciled"
    assert clock.now >= 10.0
    assert len(script.posts()) == 1
    polls = [r for r in script.requests if r.method == "GET"]
    assert polls, "the run was polled"
    assert clock.sleeps[0] == 1.0 and max(clock.sleeps) <= 4.0

    with pytest.raises(AlreadySubmitted) as excinfo:
        ledger.submit(client, REQUEST, brand="b", source="reddit", estimate_usd=0.2)
    assert excinfo.value.record.run_id == "run_async_9"
    assert len(script.posts()) == 1, "deadline never resubmits"

    # Survives a process restart: the guard is on the file, not the instance.
    reloaded = Ledger(ledger.path)
    assert reloaded.records[0].run_id == "run_async_9"
    with pytest.raises(AlreadySubmitted):
        reloaded.submit(client, REQUEST, brand="b", source="reddit", estimate_usd=0.2)
    assert len(script.posts()) == 1


def test_async_run_polls_to_terminal_status(ledger: Ledger, clock: FakeClock) -> None:
    script = Script(
        {
            ("POST", "/v1/run"): [httpx.Response(202, json={"runId": "run_async_2"})],
            ("GET", "/v1/runs/run_async_2"): [
                httpx.Response(202, json={"runId": "run_async_2", "status": "PENDING"}),
                httpx.Response(429, headers={"Retry-After": "3"}),
                httpx.Response(503, text="upstream"),
                httpx.Response(
                    200,
                    json={
                        "runId": "run_async_2",
                        "status": "FAILED",
                        "providerResponse": {"httpStatus": 500},
                        "output": [],
                    },
                ),
            ],
        }
    )
    client = make_client(script, clock)
    record, outcome = ledger.submit(
        client, REQUEST, brand="b", source="reddit", estimate_usd=0.2, deadline_s=60.0
    )
    assert len(script.posts()) == 1
    assert outcome.completed and not outcome.succeeded
    assert record.status == "FAILED"
    assert record.provider_http_status == 500
    assert record.n_results == 0
    assert record.completed_at is not None
    assert record.error == "FAILED"
    assert 3.0 in clock.sleeps, "Retry-After honoured while polling"


# -- reconcile --------------------------------------------------------------


def listing_page(items: list[dict[str, Any]], cursor: str | None) -> httpx.Response:
    body: dict[str, Any] = {"items": items}
    if cursor:
        body["nextCursor"] = cursor
    return httpx.Response(200, json=body)


def submit_sync(ledger: Ledger, clock: FakeClock, run_id: str, request: RunRequest) -> RunRecord:
    script = Script(
        {("POST", "/v1/run"): [httpx.Response(200, json={"runId": run_id, "output": [1, 2]})]}
    )
    record, _ = ledger.submit(
        make_client(script, clock), request, brand="b", source="reddit", estimate_usd=0.1
    )
    return record


def test_reconcile_failure_leaves_ledger_untouched(ledger: Ledger, clock: FakeClock) -> None:
    submit_sync(ledger, clock, "run_a", REQUEST)
    before = ledger.path.read_text()
    script = Script({("GET", "/v1/runs"): [httpx.Response(500, text="listing exploded")]})
    result = ledger.reconcile(make_client(script, clock), started_at=datetime.now(UTC))
    assert result.fetched_at is None
    assert result.unreconciled_local_seqs == [1]
    assert result.unmatched_remote_run_ids == []
    assert result.error is not None and "listing exploded" in result.error
    assert ledger.path.read_text() == before
    assert ledger.records[0].cost_source == "unreconciled"
    assert ledger.records[0].cost_usd is None


def test_reconcile_joins_by_run_id_and_pages_by_cursor(ledger: Ledger, clock: FakeClock) -> None:
    started = datetime.now(UTC) - timedelta(minutes=5)
    submit_sync(ledger, clock, "run_a", REQUEST)
    submit_sync(
        ledger, clock, "run_b", RunRequest("apify", "/streamers/youtube-scraper", {"q": "x"})
    )
    # A locally rejected row (no run id) that should reconcile to $0.
    rejected = Script({("POST", "/v1/run"): [httpx.Response(503, text="down")]})
    ledger.submit(
        make_client(rejected, clock),
        RunRequest("apify", "/apidojo/tiktok-scraper", {"k": "y"}),
        brand="b",
        source="tiktok",
        estimate_usd=0.01,
    )
    assert ledger.records[2].status == "LOCAL_REJECTED_503"

    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    script = Script(
        {
            ("GET", "/v1/runs"): [
                listing_page(
                    [
                        {
                            "runId": "run_a",
                            "status": "SUCCEEDED",
                            "createdAt": stamp,
                            "providerResponse": {"httpStatus": 200},
                            "cost": {"value": 0.0485, "currency": "USD"},
                            "billedUnits": 5,
                        }
                    ],
                    "page2",
                ),
                listing_page(
                    [
                        {
                            "runId": "run_b",
                            "status": "FAILED",
                            "createdAt": stamp,
                            "providerResponse": {"httpStatus": 502},
                            "cost": {"value": 0, "currency": "USD"},
                            "billedUnits": 0,
                        },
                        {
                            "runId": "run_old",
                            "status": "SUCCEEDED",
                            "createdAt": "2020-01-01T00:00:00Z",
                            "cost": {"value": 9.9, "currency": "USD"},
                        },
                    ],
                    None,
                ),
            ]
        }
    )
    result = ledger.reconcile(make_client(script, clock), started_at=started)
    gets = [r for r in script.requests if r.method == "GET"]
    assert len(gets) == 2
    assert gets[0].url.params.get("cursor") is None
    assert gets[1].url.params.get("cursor") == "page2"
    assert gets[0].url.params.get("limit") == "100"

    assert result.fetched_at is not None
    assert result.n_listed_in_window == 2, "run_old is outside the window"
    assert result.unmatched_remote_run_ids == []
    assert result.unreconciled_local_seqs == []

    a, b, c = ledger.records
    assert (a.cost_usd, a.billed_units, a.cost_source) == (0.0485, 5, "/v1/runs")
    assert a.provider_http_status == 200
    assert (b.cost_usd, b.billed_units, b.status, b.provider_http_status) == (0.0, 0, "FAILED", 502)
    assert b.cost_source == "/v1/runs"
    assert (c.run_id, c.cost_usd, c.cost_source) == (None, 0.0, "/v1/runs")
    assert Ledger(ledger.path).records == ledger.records


def test_reconcile_reports_unmatched_remote_and_keeps_null_rows_unreconciled(
    ledger: Ledger, clock: FakeClock
) -> None:
    started = datetime.now(UTC) - timedelta(minutes=5)
    submit_sync(ledger, clock, "run_a", REQUEST)
    rejected = Script({("POST", "/v1/run"): [httpx.Response(503, text="down")]})
    ledger.submit(
        make_client(rejected, clock),
        RunRequest("apify", "/apidojo/tiktok-scraper", {"k": "y"}),
        brand="b",
        source="tiktok",
        estimate_usd=0.01,
    )
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    script = Script(
        {
            ("GET", "/v1/runs"): [
                listing_page(
                    [
                        {
                            "runId": "run_a",
                            "status": "SUCCEEDED",
                            "createdAt": stamp,
                            "cost": {"value": 0.02},
                            "billedUnits": 2,
                        },
                        {
                            "runId": "run_ghost",
                            "status": "SUCCEEDED",
                            "createdAt": stamp,
                            "cost": {"value": 0.03},
                            "billedUnits": 3,
                        },
                    ],
                    None,
                )
            ]
        }
    )
    result = ledger.reconcile(make_client(script, clock), started_at=started)
    assert result.unmatched_remote_run_ids == ["run_ghost"]
    assert result.unreconciled_local_seqs == [2], "the null-id row cannot be cleared"
    assert ledger.records[0].cost_source == "/v1/runs"
    assert ledger.records[1].cost_source == "unreconciled"
