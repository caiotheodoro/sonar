"""Monid HTTP transport.

``MonidClient.run`` posts ``{provider, endpoint, input}`` to ``POST /v1/run``.
A synchronous ``200`` body is returned as-is; a ``202`` carries a ``runId`` that
is polled on ``GET /v1/runs/{id}`` with backoff until a terminal status or the
caller's deadline. ``429`` honours ``Retry-After`` and otherwise backs off
2, 4, 8, 16 seconds (four retries, five attempts). ``402`` trips a process-wide
breaker so that no further POST leaves this process (CONTRACTS §RunRecord,
design §Error matrix); a ``402`` seen while polling or listing trips it too, but
an in-flight poll of an already-accepted run continues to its terminal state or
the deadline.

Failures are returned as data on ``RunOutcome.status`` using the ledger's local
status vocabulary (``LOCAL_REJECTED_<http>``, ``LOCAL_BACKOFF_EXHAUSTED``,
``LOCAL_DEADLINE``) so that the pipeline can abstain with exit 0. The only
exceptions raised are ``MonidHalted`` (breaker already tripped, nothing was
sent) and ``MonidHTTPError`` (``GET /v1/runs`` listing failed).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Self

import httpx

BASE_URL = "https://api.monid.ai"
RUN_PATH = "/v1/run"
RUNS_PATH = "/v1/runs"
API_KEY_VAR = "MONID_API_KEY"
ENV_PATH_VAR = "SONAR_ENV"
DEFAULT_ENV_PATH = Path.home() / ".sonar" / ".env"

# Backoff schedule for 429 without Retry-After: four retries, five attempts.
RATE_LIMIT_BACKOFF_S: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0)
MAX_ATTEMPTS = len(RATE_LIMIT_BACKOFF_S) + 1

# Monid states that mean "still running". Anything else on a 200 poll body is
# terminal (design §Endpoint reference; exact vocabulary is OQ-1).
PENDING_STATUSES = frozenset({"PENDING", "QUEUED", "RUNNING", "READY", "STARTING", "IN_PROGRESS"})
FAILURE_STATUSES = frozenset({"TIMED_OUT", "FAILED", "BLOCKED", "STOPPED", "ABORTED", "CANCELLED"})

ERROR_EXCERPT_CHARS = 500


class MonidError(Exception):
    """Base class for transport errors."""


class MonidHalted(MonidError):
    """The 402 breaker is tripped; nothing was sent."""


class MonidHTTPError(MonidError):
    """A non-run request (listing) failed with an HTTP error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class Breaker:
    """Process-wide halt flag. One instance (``BREAKER``) is shared by all clients."""

    def __init__(self) -> None:
        self.tripped = False
        self.reason: str | None = None
        self.tripped_at: datetime | None = None

    def trip(self, reason: str) -> None:
        if not self.tripped:
            self.tripped = True
            self.reason = reason
            self.tripped_at = datetime.now(UTC)

    def reset(self) -> None:
        self.tripped = False
        self.reason = None
        self.tripped_at = None


BREAKER = Breaker()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def input_digest(payload: dict[str, Any]) -> str:
    """First 24 hex of sha256 over canonical JSON of the request ``input``."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()[:24]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = line.removeprefix("export ")
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_api_key(env: dict[str, str] | None = None) -> str:
    """Return the Monid key from the process env, else from ``$SONAR_ENV`` / ``~/.sonar/.env``."""
    source = os.environ if env is None else env
    direct = source.get(API_KEY_VAR, "").strip()
    if direct:
        return direct
    env_path = Path(source.get(ENV_PATH_VAR) or DEFAULT_ENV_PATH).expanduser()
    key = _parse_env_file(env_path).get(API_KEY_VAR, "").strip()
    if not key:
        raise MonidError(
            f"{API_KEY_VAR} not set and not found in {env_path}; run scripts/setup-wizard.sh"
        )
    return key


@dataclass(frozen=True)
class RunRequest:
    """Body of ``POST /v1/run``."""

    provider: str
    endpoint: str
    input: dict[str, Any] = field(default_factory=dict)

    def body(self) -> dict[str, Any]:
        return {"provider": self.provider, "endpoint": self.endpoint, "input": self.input}

    @property
    def digest(self) -> str:
        return input_digest(self.input)


@dataclass
class RunOutcome:
    """What ``MonidClient.run`` observed. ``completed`` is true only on a terminal Monid status."""

    run_id: str | None
    status: str
    http_status: int | None
    provider_http_status: int | None
    body: dict[str, Any] | None
    attempts: int
    error: str | None
    completed: bool

    @property
    def succeeded(self) -> bool:
        return self.completed and self.status.upper() not in FAILURE_STATUSES


def _excerpt(response: httpx.Response) -> str:
    return response.text[:ERROR_EXCERPT_CHARS]


def _json_body(response: httpx.Response) -> dict[str, Any] | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else {"output": data}


def _provider_http_status(body: dict[str, Any] | None) -> int | None:
    if not body:
        return None
    provider = body.get("providerResponse")
    if isinstance(provider, dict):
        value = provider.get("httpStatus")
        if isinstance(value, int):
            return value
    return None


def _run_id(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    for key in ("runId", "run_id", "id"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _status(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    value = body.get("status")
    return value if isinstance(value, str) and value else None


def _retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if header is None:
        return None
    header = header.strip()
    if header.isdigit():
        return float(header)
    try:
        when = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class MonidClient:
    """Thin transport over ``httpx.Client``. ``sleep`` and ``clock`` are injectable for tests."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        breaker: Breaker = BREAKER,
        poll_initial_s: float = 1.0,
        poll_max_s: float = 10.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else load_api_key()
        self._sleep = sleep
        self._clock = clock
        self._breaker = breaker
        self._poll_initial = poll_initial_s
        self._poll_max = poll_max_s
        self._http = httpx.Client(
            base_url=base_url,
            transport=transport,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

    @property
    def halted(self) -> bool:
        return self._breaker.tripped

    @property
    def breaker(self) -> Breaker:
        return self._breaker

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- run --------------------------------------------------------------

    def run(self, request: RunRequest, *, deadline_s: float = 300.0) -> RunOutcome:
        """Submit one run and wait for it. Never raises on HTTP status; see module docstring."""
        if self._breaker.tripped:
            raise MonidHalted(self._breaker.reason or "breaker tripped")
        deadline = self._clock() + deadline_s
        attempts = 0
        body = request.body()
        while True:
            if self._breaker.tripped:
                raise MonidHalted(self._breaker.reason or "breaker tripped")
            attempts += 1
            try:
                response = self._http.post(RUN_PATH, content=canonical_json(body))
            except httpx.HTTPError as exc:
                return RunOutcome(
                    run_id=None,
                    status="LOCAL_REJECTED_0",
                    http_status=None,
                    provider_http_status=None,
                    body=None,
                    attempts=attempts,
                    error=f"{type(exc).__name__}: {exc}"[:ERROR_EXCERPT_CHARS],
                    completed=False,
                )
            code = response.status_code
            if code == 200:
                data = _json_body(response)
                status = _status(data) or "SUCCEEDED"
                return RunOutcome(
                    run_id=_run_id(data),
                    status=status,
                    http_status=code,
                    provider_http_status=_provider_http_status(data),
                    body=data,
                    attempts=attempts,
                    error=None,
                    completed=True,
                )
            if code == 202:
                data = _json_body(response)
                run_id = _run_id(data)
                if run_id is None:
                    return RunOutcome(
                        run_id=None,
                        status="LOCAL_REJECTED_202",
                        http_status=code,
                        provider_http_status=None,
                        body=data,
                        attempts=attempts,
                        error="202 without runId: " + _excerpt(response),
                        completed=False,
                    )
                return self._poll(run_id, data, attempts, deadline)
            if code == 429:
                if attempts >= MAX_ATTEMPTS:
                    return RunOutcome(
                        run_id=None,
                        status="LOCAL_BACKOFF_EXHAUSTED",
                        http_status=code,
                        provider_http_status=None,
                        body=_json_body(response),
                        attempts=attempts,
                        error=_excerpt(response) or "429 after retries",
                        completed=False,
                    )
                wait = _retry_after(response)
                if wait is None:
                    wait = RATE_LIMIT_BACKOFF_S[attempts - 1]
                if self._clock() + wait > deadline:
                    return RunOutcome(
                        run_id=None,
                        status="LOCAL_DEADLINE",
                        http_status=code,
                        provider_http_status=None,
                        body=None,
                        attempts=attempts,
                        error=f"429 backoff of {wait:g}s exceeds deadline",
                        completed=False,
                    )
                self._sleep(wait)
                continue
            if code == 402:
                self._breaker.trip("Monid 402: " + (_excerpt(response) or "payment required"))
            data = _json_body(response)
            if code >= 500:
                recovered_id = _run_id(data)
                if recovered_id is not None:
                    # A 5xx whose body still carries the runId: Monid created the
                    # run before the gateway erred. Poll it — it completes and
                    # bills regardless, and dropping it here would orphan it
                    # (verdict PARTIAL, unmatched_remote_run_ids).
                    return self._poll(recovered_id, data, attempts, deadline)
                if attempts < MAX_ATTEMPTS:
                    wait = RATE_LIMIT_BACKOFF_S[attempts - 1]
                    if self._clock() + wait <= deadline:
                        self._sleep(wait)
                        continue
            return RunOutcome(
                run_id=None,
                status=f"LOCAL_REJECTED_{code}",
                http_status=code,
                provider_http_status=None,
                body=data,
                attempts=attempts,
                error=_excerpt(response) or f"HTTP {code}",
                completed=False,
            )

    def _poll(
        self,
        run_id: str,
        first_body: dict[str, Any] | None,
        attempts: int,
        deadline: float,
    ) -> RunOutcome:
        """Poll ``GET /v1/runs/{id}`` until terminal or the deadline. Never resubmits."""
        wait = self._poll_initial
        last_body = first_body
        last_code: int | None = 202
        last_error: str | None = None
        while True:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return RunOutcome(
                    run_id=run_id,
                    status="LOCAL_DEADLINE",
                    http_status=last_code,
                    provider_http_status=_provider_http_status(last_body),
                    body=last_body,
                    attempts=attempts,
                    error=last_error or f"deadline reached while {_status(last_body) or 'pending'}",
                    completed=False,
                )
            self._sleep(min(wait, remaining))
            wait = min(wait * 2, self._poll_max)
            try:
                response = self._http.get(f"{RUNS_PATH}/{run_id}")
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:ERROR_EXCERPT_CHARS]
                continue
            last_code = response.status_code
            if last_code == 429:
                retry = _retry_after(response)
                if retry is not None:
                    wait = retry
                continue
            if last_code == 402:
                # Decision: a 402 mid-poll trips the breaker (no further POST leaves this
                # process) but does not abort this poll. The run was already accepted and
                # may still reach a terminal state; the row keeps its run_id either way
                # (deadline -> LOCAL_DEADLINE) and is priced from the listing, never resubmitted.
                self._breaker.trip("Monid 402 while polling: " + _excerpt(response))
                last_error = _excerpt(response)
                continue
            if last_code >= 400:
                last_error = f"HTTP {last_code}: {_excerpt(response)}"
                continue
            data = _json_body(response)
            if data is not None:
                last_body = data
            status = _status(data)
            if last_code == 202 or status is None or status.upper() in PENDING_STATUSES:
                continue
            return RunOutcome(
                run_id=_run_id(data) or run_id,
                status=status,
                http_status=last_code,
                provider_http_status=_provider_http_status(data),
                body=data,
                attempts=attempts,
                error=None if status.upper() not in FAILURE_STATUSES else status,
                completed=True,
            )

    # -- listing ----------------------------------------------------------

    def iter_runs(self, *, limit: int = 100) -> Iterator[dict[str, Any]]:
        """Page ``GET /v1/runs`` by cursor. Raises ``MonidHTTPError`` on any non-2xx after 429 retries."""
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": min(limit, 100)}
            if cursor:
                params["cursor"] = cursor
            page = self._get_with_backoff(RUNS_PATH, params)
            items: list[Any] = []
            for key in ("items", "runs", "data"):
                candidate = page.get(key)
                if isinstance(candidate, list):
                    items = candidate
                    break
            for item in items:
                if isinstance(item, dict):
                    yield item
            next_cursor = page.get("nextCursor") or page.get("cursor") or page.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    def list_runs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return list(self.iter_runs(limit=limit))

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._get_with_backoff(f"{RUNS_PATH}/{run_id}", None)

    def _get_with_backoff(self, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        attempts = 0
        while True:
            attempts += 1
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as exc:
                raise MonidHTTPError(0, f"{type(exc).__name__}: {exc}") from exc
            code = response.status_code
            if code == 429 and attempts < MAX_ATTEMPTS:
                wait = _retry_after(response)
                self._sleep(RATE_LIMIT_BACKOFF_S[attempts - 1] if wait is None else wait)
                continue
            if code >= 400:
                if code == 402:
                    self._breaker.trip("Monid 402 on listing: " + _excerpt(response))
                raise MonidHTTPError(code, _excerpt(response))
            data = _json_body(response)
            if data is None:
                raise MonidHTTPError(code, "non-JSON body: " + _excerpt(response))
            return data
