"""Orchestration: one session from a validated ``Query`` to the artifacts on disk.

``run`` is the integration layer the design names (W5.1). It owns no rule of
its own: every decision is made by the layer that owns it and this module
only sequences them, in the order plan, fetch, dedup, language, match, label
(with corroboration), topics, stats, receipt, digest, narration, tts,
reconcile, receipt, and writes ``<out_dir>/{digest.md, digest.json,
brief.mp3, receipt.json, stats.json, topics.json, mentions.jsonl,
labels.jsonl, runs.jsonl}``.

Fetch is a thread pool of :data:`MAX_WORKERS` over ``(brand, source)`` tasks.
Every Monid call goes through the caller's ``Ledger`` with a per-run deadline;
the ledger's own ``open``/``close`` are serialised behind a lock because the
file is append-only and ``local_seq`` is allocated at open time. A source that
returns nothing usable abstains with the reason the error matrix names
(``empty``, ``provider_failed``, ``rate_limited``, ``deadline``,
``unavailable``, ``schema_drift``, ``halted``); the raw payload of a schema
drift is saved under ``raw/``. A 402 trips the client's breaker: what was
fetched is still analysed, the session carries a ``halted`` abstention and
``RunResult.exit_code`` is 3. A listing failure or an unreconciled row leaves
the receipt ``PARTIAL`` and the exit code 4, so ``sonar reconcile --session``
can finish the job later.

Voice runs after the first reconcile so the narration quotes reconciled
Monid costs; the numbers gate that authorises the audio runs against that
pre-voice digest. The final digest adds the voice spend to the cost quote, so
the narration is gated once more against the digest that ships and
``numbers_verified`` holds for that digest (a narration that quoted the
pre-voice total reads ``numbers_verified=false`` with its audio still linked).

``--fixtures`` (offline replay) is :func:`fixtures_client` plus
:class:`FixtureLlm`: a ``MonidClient`` over an ``httpx.MockTransport`` that
serves the recorded run bodies and listing page from ``tests/fixtures``, and a
replaying fake for the seam that synthesises deterministic labels for ids it
has no fixture entry for. A replay receipt carries ``replay=true`` and the
verdict ``REPLAY``; it never passes ``sonar verify``.

``labels.jsonl`` lines are ``{"brand": str, "label": Label}`` because a
``Label`` has no brand field and the row key is ``(mention_id, brand)``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, TypeVar

import httpx
from pydantic import BaseModel

import sonar.providers  # noqa: F401  (registers every adapter into PROVIDERS)
from sonar import config
from sonar.config import SOURCE_PLAN, SourceName, SourcePlan
from sonar.llm.base import ClassifyBatch, ClassifyResult, JsonResult, LlmBackend
from sonar.llm.base import Usage as SeamUsage
from sonar.llm.fake import FakeBackend, LabelFixtureEntry, load_labels_fixture
from sonar.models import (
    AbstainReason,
    Abstention,
    CoverageGap,
    Digest,
    Label,
    Mention,
    Narration,
    Query,
    Receipt,
    RunRecord,
)
from sonar.monid import (
    LOCAL_BACKOFF_EXHAUSTED,
    LOCAL_DEADLINE,
    AlreadySubmitted,
    Breaker,
    Ledger,
    MonidClient,
    MonidHalted,
    RunOutcome,
    RunRequest,
    count_results,
)
from sonar.monid.ledger import ReconcileResult
from sonar.providers.base import AdapterEmpty, AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.report.digest import NO_NARRATION, build_digest, requote_cost, write_digest_files
from sonar.report.markdown import render_digest, render_receipt
from sonar.report.receipt import (
    LlmUsageTotals,
    build_receipt,
    count_mentions,
    count_unlabelled,
    unlabelled_note,
    write_receipt,
)
from sonar.sentiment import LabelCache, LabelRun, label_mentions
from sonar.stats import StatsResult, compute_stats
from sonar.text import DedupItem, dedup
from sonar.topics import CACHE_FILENAME, TopicsResult, assign_topic_ids, brand_slug, build_topics
from sonar.voice import narrate, regate

log = logging.getLogger(__name__)

MAX_WORKERS: Final[int] = 6
"""Fetch concurrency: six ``(brand, source)`` tasks in flight (design W5.1)."""
DEFAULT_RUN_DEADLINE_S: Final[float] = 300.0
RECONCILE_SLACK: Final[timedelta] = timedelta(seconds=60)
"""Clock-skew allowance on both ends of the reconcile window (Monid vs local time)."""

EXIT_OK: Final[int] = 0
EXIT_USAGE: Final[int] = 2
EXIT_HALTED: Final[int] = 3
EXIT_PARTIAL: Final[int] = 4

DIGEST_MD: Final[str] = "digest.md"
DIGEST_JSON: Final[str] = "digest.json"
RECEIPT_JSON: Final[str] = "receipt.json"
STATS_JSON: Final[str] = "stats.json"
TOPICS_JSON: Final[str] = "topics.json"
MENTIONS_JSONL: Final[str] = "mentions.jsonl"
LABELS_JSONL: Final[str] = "labels.jsonl"
RUNS_JSONL: Final[str] = "runs.jsonl"
BRIEF_MP3: Final[str] = "brief.mp3"
RAW_DIR: Final[str] = "raw"
ARTIFACTS: Final[tuple[str, ...]] = (
    DIGEST_MD,
    DIGEST_JSON,
    RECEIPT_JSON,
    STATS_JSON,
    TOPICS_JSON,
    MENTIONS_JSONL,
    LABELS_JSONL,
    RUNS_JSONL,
)
"""Every artifact a run writes; ``brief.mp3`` is added when the voice run succeeds."""

FIXTURES_DIR: Final[Path] = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
FIXTURE_RUNS_PAGE: Final[str] = "v1_runs_page.json"
FIXTURE_TTS_RUN_ID: Final[str] = "FIXTURE-TTS-RUN"
FIXTURE_MP3: Final[bytes] = b"\xff\xfb\x90\x00" * 64
"""Placeholder MPEG frames served by the offline transport so ``brief.mp3`` exists."""

LOOKUP_ROLE: Final[str] = "lookup"
SchemaT = TypeVar("SchemaT", bound=BaseModel)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def new_session_id(brand: str, now: datetime | None = None) -> str:
    """CONTRACTS session id: ``{YYYYMMDDTHHMMSSZ}-{brand slug}-{6 hex}``."""
    stamp = (now or utcnow()).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{brand_slug(brand)}-{secrets.token_hex(3)}"


def payload_of(body: Mapping[str, Any] | None) -> Any:
    """The provider payload inside a Monid run body (``output``), else the body itself."""
    if body is None:
        return None
    if "output" in body:
        return body["output"]
    return body


# --------------------------------------------------------------------------- options


@dataclass(frozen=True)
class RunOptions:
    """Knobs the CLI exposes; every default is the live-run default."""

    voice: bool = True
    replay: bool = False
    max_workers: int = MAX_WORKERS
    run_deadline_s: float = DEFAULT_RUN_DEADLINE_S
    resamples: int = config.B
    seed: int = config.SEED
    cache_dir: Path | None = None
    voice_id: str | None = None
    tts_direct: bool = False
    """Voice the brief straight through ElevenLabs (D016); the ledger row is
    ``local`` with the Monid-equivalent price as its theoretical estimate."""
    tts_api_key: str | None = None
    bounded_reconcile: bool = True
    """Join the listing only inside ``[started_at, now]``; a replay joins without bounds."""


DEFAULT_OPTIONS: Final[RunOptions] = RunOptions()


# --------------------------------------------------------------------------- plan


@dataclass(frozen=True)
class PlannedSource:
    """One ``(brand, source)`` fetch with its ledger estimate."""

    brand: str
    source: SourceName
    estimate_usd: float
    depends_on: SourceName | None = None


@dataclass(frozen=True)
class SessionPlan:
    query: Query
    brands: tuple[str, ...]
    tasks: tuple[PlannedSource, ...]
    skipped: tuple[tuple[str, SourceName, str], ...]
    """``(brand, source, reason)`` for sources that are not fetched."""

    @property
    def estimate_usd(self) -> float:
        return sum(t.estimate_usd for t in self.tasks)

    def by_brand(self, brand: str) -> list[PlannedSource]:
        return [t for t in self.tasks if t.brand == brand]


def brands_of(query: Query) -> tuple[str, ...]:
    return (query.brand, *query.competitors)


def query_for(query: Query, brand: str) -> Query:
    """The Query an adapter builds its input from: the brand itself, or one competitor.

    A competitor carries no aliases and no competitors of its own; the profile and the
    sources are the session's (``full`` caps apply to every brand of a ``full`` run).
    """
    if brand == query.brand:
        return query
    if brand not in query.competitors:
        raise ValueError(f"{brand!r} is neither the Query brand nor a competitor")
    return Query(
        brand=brand,
        brand_aliases=[],
        brand_hint=None,
        competitors=[],
        window_days=query.window_days,
        profile=query.profile,
        sources=list(query.sources),
    )


def build_plan(query: Query) -> SessionPlan:
    """Every ``(brand, source)`` the profile fetches, with estimates; never touches the network."""
    tasks: list[PlannedSource] = []
    skipped: list[tuple[str, SourceName, str]] = []
    for brand in brands_of(query):
        for source in query.sources:
            plan = SOURCE_PLAN[source]
            provider = PROVIDERS.get(source)
            if provider is None:
                skipped.append((brand, source, "no adapter registered"))
                continue
            if not provider.available:
                skipped.append(
                    (brand, source, provider.unavailable_reason or "adapter unavailable")
                )
                continue
            if plan.caps[query.profile] == 0:
                skipped.append((brand, source, f"not fetched under profile {query.profile}"))
                continue
            depends: SourceName | None = None
            if source == "youtube_comment":
                if "youtube" not in query.sources:
                    skipped.append((brand, source, "needs youtube in sources (video urls)"))
                    continue
                depends = "youtube"
            tasks.append(
                PlannedSource(
                    brand=brand,
                    source=source,
                    estimate_usd=plan.estimate_usd(query.profile),
                    depends_on=depends,
                )
            )
    fetched = {(t.brand, t.source) for t in tasks}
    kept: list[PlannedSource] = []
    for task in tasks:
        if task.depends_on is not None and (task.brand, task.depends_on) not in fetched:
            skipped.append((task.brand, task.source, f"{task.depends_on} is not fetched"))
            continue
        kept.append(task)
    return SessionPlan(
        query=query, brands=brands_of(query), tasks=tuple(kept), skipped=tuple(skipped)
    )


def plan_lines(plan: SessionPlan) -> list[str]:
    """Human-readable plan: one line per task, the skipped sources, the estimate."""
    q = plan.query
    lines = [
        (
            f"brand {q.brand!r} aliases {q.brand_aliases} competitors {q.competitors} "
            f"profile {q.profile} window {q.window_days}d"
        ),
    ]
    for task in plan.tasks:
        plan_row = SOURCE_PLAN[task.source]
        suffix = f" (after {task.depends_on})" if task.depends_on else ""
        lines.append(
            f"- {task.brand:<24} {task.source:<16} {plan_row.provider}{plan_row.endpoint:<40} "
            f"cap {plan_row.caps[q.profile]:>3} {plan_row.cap_unit:<7} est ${task.estimate_usd:.4f}"
            + suffix
        )
    for brand, source, reason in plan.skipped:
        lines.append(f"- {brand:<24} {source:<16} skipped: {reason}")
    lines.append(f"estimate total ${plan.estimate_usd:.4f} over {len(plan.brands)} brand(s)")
    return lines


# --------------------------------------------------------------------------- fetch


@dataclass
class FetchResult:
    """What one ``(brand, source)`` task produced."""

    brand: str
    source: SourceName
    mentions: list[Mention] = field(default_factory=list)
    abstention: Abstention | None = None
    notes: list[str] = field(default_factory=list)
    halted: bool = False


class _HaltedError(Exception):
    """Internal: the breaker tripped inside a task; carries the reason."""


@dataclass
class _FetchContext:
    query: Query
    client: MonidClient
    ledger: Ledger
    out_dir: Path
    options: RunOptions
    now: datetime
    lock: threading.RLock = field(default_factory=threading.RLock)
    source_locks: dict[str, threading.Lock] = field(default_factory=dict)

    def source_lock(self, source: str) -> threading.Lock:
        with self.lock:
            return self.source_locks.setdefault(source, threading.Lock())


def abstain_reason_for(outcome: RunOutcome) -> AbstainReason:
    """Error-matrix reason for a run that did not yield a usable payload."""
    status = outcome.status.upper()
    if status in (LOCAL_DEADLINE, "TIMED_OUT"):
        return "deadline"
    if status in (LOCAL_BACKOFF_EXHAUSTED, "LOCAL_REJECTED_429"):
        return "rate_limited"
    if status == "LOCAL_REJECTED_402":
        return "halted"
    return "provider_failed"


def _source_abstention(
    brand: str, source: SourceName, reason: AbstainReason, detail: str
) -> Abstention:
    return Abstention(
        scope="source", brand=brand, source=source, reason=reason, detail=detail[:500]
    )


def _submit(
    ctx: _FetchContext,
    request: RunRequest,
    *,
    brand: str,
    source: SourceName,
    estimate_usd: float,
) -> tuple[RunRecord, RunOutcome]:
    """``Ledger.submit`` with the open/close steps serialised; the wait happens unlocked."""
    with ctx.lock:
        existing = ctx.ledger.find_submitted(request.digest)
        if existing is not None:
            raise AlreadySubmitted(existing)
        if ctx.client.halted:
            raise MonidHalted(ctx.client.breaker.reason or "breaker tripped")
        opened = ctx.ledger.open(request, brand=brand, source=source, estimate_usd=estimate_usd)
    log.info(
        "fetch %s/%s: submit local_seq %d %s", brand, source, opened.local_seq, request.endpoint
    )
    outcome = ctx.client.run(request, deadline_s=ctx.options.run_deadline_s)
    n_results = count_results(outcome.body) if outcome.succeeded else 0
    with ctx.lock:
        record = ctx.ledger.close(opened.local_seq, outcome, n_results)
    log.info(
        "fetch %s/%s: local_seq %d run_id %s status %s n_results %s",
        brand,
        source,
        record.local_seq,
        record.run_id or "-",
        record.status,
        record.n_results,
    )
    return record, outcome


def _save_raw(ctx: _FetchContext, record: RunRecord, body: Any) -> Path:
    raw_dir = ctx.out_dir / RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{record.local_seq}.json"
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _build_input(adapter: Any, query: Query, now: datetime, **extra: Any) -> dict[str, Any]:
    """``build_input`` with ``now`` when the adapter accepts it (reproducible digests)."""
    try:
        result: dict[str, Any] = adapter.build_input(query, now=now, **extra)
    except TypeError:
        result = adapter.build_input(query, **extra)
    return result


def _report_notes(source: SourceName, report: Any) -> list[str]:
    """Diagnostic notes from an adapter's ``parse_with_report`` result.

    The adapters that return a report do not share one shape — reddit reports
    ``cluster_key_fallbacks``, news reports ``skipped_no_match`` — so every
    optional field is read defensively and one adapter's shape is never
    assumed of another.
    """
    notes: list[str] = []
    fallbacks = getattr(report, "cluster_key_fallbacks", 0)
    if fallbacks:
        notes.append(f"cluster key fallback: {source} {fallbacks}")
    skipped = getattr(report, "skipped_no_match", 0)
    if skipped:
        notes.append(f"{source}: {skipped} result(s) skipped, no brand match")
    no_text = getattr(report, "skipped_no_text", 0)
    if no_text:
        notes.append(f"{source}: {no_text} item(s) skipped, deleted or empty content")
    return notes


def _run_source(
    ctx: _FetchContext,
    result: FetchResult,
    adapter: Any,
    request: RunRequest,
    estimate_usd: float,
    *,
    terms: Sequence[str],
) -> tuple[RunRecord, RunOutcome, list[Mention]] | None:
    """Submit one run and parse it; on failure sets ``result.abstention`` and returns None."""
    brand, source = result.brand, result.source
    record, outcome = _submit(ctx, request, brand=brand, source=source, estimate_usd=estimate_usd)
    if outcome.status == "LOCAL_REJECTED_402":
        raise _HaltedError(outcome.error or "Monid 402")
    if not outcome.succeeded:
        reason = abstain_reason_for(outcome)
        detail = outcome.error or f"run {record.status}"
        result.abstention = _source_abstention(
            brand, source, reason, f"local_seq {record.local_seq}: {detail}"
        )
        return None
    if outcome.provider_http_status is not None and outcome.provider_http_status >= 400:
        result.abstention = _source_abstention(
            brand,
            source,
            "provider_failed",
            f"local_seq {record.local_seq}: provider HTTP {outcome.provider_http_status}",
        )
        return None
    payload = payload_of(outcome.body)
    try:
        if hasattr(adapter, "parse_with_report"):
            report = adapter.parse_with_report(
                payload, outcome.run_id, brand, local_seq=record.local_seq, terms=list(terms)
            )
            mentions: list[Mention] = list(report.mentions)
            result.notes.extend(_report_notes(source, report))
        else:
            mentions = list(
                adapter.parse(
                    payload, outcome.run_id, brand, local_seq=record.local_seq, terms=list(terms)
                )
            )
    except AdapterEmpty as exc:
        result.abstention = _source_abstention(
            brand, source, "empty", f"local_seq {record.local_seq}: {exc.detail}"
        )
        return None
    except AdapterSchemaError as exc:
        saved = _save_raw(ctx, record, outcome.body)
        result.abstention = _source_abstention(
            brand,
            source,
            "schema_drift",
            f"local_seq {record.local_seq}: {exc}; raw saved {saved.name}",
        )
        return None
    return record, outcome, mentions


def _fetch_task(ctx: _FetchContext, brand: str, source: SourceName) -> list[FetchResult]:
    """Fetch one source for one brand; ``youtube`` also yields the ``youtube_comment`` result."""
    query = ctx.query
    result = FetchResult(brand=brand, source=source)
    results = [result]
    adapter: Any = PROVIDERS[source]
    plan = SOURCE_PLAN[source]
    brand_query = query_for(query, brand)
    terms = list(query.brand_aliases) if brand == query.brand else []
    main_estimate = plan.estimate_usd(query.profile) - (
        plan.lookup_usd if plan.lookup_endpoint else 0.0
    )
    try:
        if plan.lookup_endpoint is not None:
            with ctx.source_lock(source):
                _fetch_with_lookup(ctx, result, adapter, plan, brand_query, main_estimate, terms)
        elif source == "news":
            _fetch_pages(ctx, result, adapter, plan, brand_query, terms)
        else:
            request = RunRequest(
                plan.provider, plan.endpoint, _build_input(adapter, brand_query, ctx.now)
            )
            parsed = _run_source(ctx, result, adapter, request, main_estimate, terms=terms)
            if parsed is not None:
                result.mentions = parsed[2]
            if source == "youtube" and "youtube_comment" in query.sources:
                results.append(_fetch_comments(ctx, brand, brand_query, result, terms))
    except MonidHalted as exc:
        result.halted = True
        result.abstention = _source_abstention(brand, source, "halted", str(exc))
    except _HaltedError as exc:
        result.halted = True
        result.abstention = _source_abstention(brand, source, "halted", str(exc))
    except AlreadySubmitted as exc:
        result.abstention = _source_abstention(brand, source, "provider_failed", str(exc))
    except (ValueError, RuntimeError) as exc:
        result.abstention = _source_abstention(
            brand, source, "provider_failed", f"build_input failed: {exc}"
        )
    for item in results:
        if item.abstention is None and not item.mentions:
            item.abstention = _source_abstention(
                item.brand, item.source, "empty", "zero mentions after parse"
            )
    return results


def _fetch_with_lookup(
    ctx: _FetchContext,
    result: FetchResult,
    adapter: Any,
    plan: SourcePlan,
    brand_query: Query,
    main_estimate: float,
    terms: Sequence[str],
) -> None:
    """Trustpilot and G2: the id-resolution call, then the reviews call for the resolved entity."""
    assert plan.lookup_endpoint is not None
    lookup = RunRequest(plan.provider, plan.lookup_endpoint, adapter.build_input(brand_query))
    record, outcome = _submit(
        ctx, lookup, brand=result.brand, source=result.source, estimate_usd=plan.lookup_usd
    )
    if outcome.status == "LOCAL_REJECTED_402":
        raise _HaltedError(outcome.error or "Monid 402")
    if not outcome.succeeded:
        result.abstention = _source_abstention(
            result.brand,
            result.source,
            abstain_reason_for(outcome),
            f"lookup local_seq {record.local_seq}: {outcome.error or record.status}",
        )
        return
    try:
        found = adapter.parse_search(payload_of(outcome.body))
    except AdapterSchemaError as exc:
        saved = _save_raw(ctx, record, outcome.body)
        result.abstention = _source_abstention(
            result.brand, result.source, "schema_drift", f"lookup: {exc}; raw saved {saved.name}"
        )
        return
    if found is None:
        result.abstention = _source_abstention(
            result.brand,
            result.source,
            "empty",
            "lookup found no matching entity; reviews run skipped",
        )
        return
    reviews = RunRequest(plan.provider, plan.endpoint, adapter.build_input(brand_query))
    parsed = _run_source(ctx, result, adapter, reviews, main_estimate, terms=terms)
    if parsed is not None:
        result.mentions = parsed[2]


def _fetch_pages(
    ctx: _FetchContext,
    result: FetchResult,
    adapter: Any,
    plan: SourcePlan,
    brand_query: Query,
    terms: Sequence[str],
) -> None:
    """News: one ``$0`` sync run per page; a failed page is noted, the rest still count."""
    failures: list[str] = []
    for page in adapter.pages(brand_query):
        request = RunRequest(
            plan.provider, plan.endpoint, adapter.build_input(brand_query, page=page, now=ctx.now)
        )
        page_result = FetchResult(brand=result.brand, source=result.source)
        parsed = _run_source(ctx, page_result, adapter, request, plan.per_call_usd, terms=terms)
        if parsed is None:
            assert page_result.abstention is not None
            failures.append(f"page {page}: {page_result.abstention.reason}")
            if page_result.abstention.reason in ("deadline", "rate_limited"):
                result.abstention = page_result.abstention
                break
            continue
        result.mentions.extend(parsed[2])
        result.notes.extend(page_result.notes)
        if not parsed[2]:
            break
    if failures and result.mentions:
        result.notes.append(f"news ({result.brand}): {'; '.join(failures)}")
    elif failures and result.abstention is None:
        result.abstention = _source_abstention(
            result.brand, result.source, "provider_failed", "; ".join(failures)
        )


def _fetch_comments(
    ctx: _FetchContext, brand: str, brand_query: Query, videos: FetchResult, terms: Sequence[str]
) -> FetchResult:
    """YouTube comments for the videos the video run returned (one run, capped per video)."""
    result = FetchResult(brand=brand, source="youtube_comment")
    adapter: Any = PROVIDERS.get("youtube_comment")
    plan = SOURCE_PLAN["youtube_comment"]
    if adapter is None or not adapter.available:
        result.abstention = _source_abstention(
            brand, "youtube_comment", "unavailable", "adapter unavailable"
        )
        return result
    if videos.abstention is not None and videos.abstention.reason != "empty":
        result.abstention = _source_abstention(
            brand,
            "youtube_comment",
            videos.abstention.reason,
            f"parent youtube run: {videos.abstention.detail}",
        )
        return result
    if not videos.mentions:
        result.abstention = _source_abstention(
            brand, "youtube_comment", "empty", "no videos to fetch comments for"
        )
        return result
    try:
        payload = adapter.build_input(brand_query, videos=videos.mentions)
    except ValueError as exc:
        result.abstention = _source_abstention(brand, "youtube_comment", "empty", str(exc))
        return result
    request = RunRequest(plan.provider, plan.endpoint, payload)
    parsed = _run_source(
        ctx, result, adapter, request, plan.estimate_usd(brand_query.profile), terms=terms
    )
    if parsed is not None:
        result.mentions = parsed[2]
    return result


def fetch_all(
    query: Query,
    plan: SessionPlan,
    *,
    client: MonidClient,
    ledger: Ledger,
    out_dir: Path,
    options: RunOptions,
    now: datetime,
) -> list[FetchResult]:
    """Run every planned task through a pool of ``options.max_workers`` threads."""
    ctx = _FetchContext(
        query=query, client=client, ledger=ledger, out_dir=out_dir, options=options, now=now
    )
    pending = [t for t in plan.tasks if t.depends_on is None]
    results: list[FetchResult] = []
    workers = max(1, min(options.max_workers, len(pending))) if pending else 1
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sonar-fetch") as pool:
        futures = [pool.submit(_fetch_task, ctx, t.brand, t.source) for t in pending]
        for future in futures:
            results.extend(future.result())
    order = {(t.brand, t.source): i for i, t in enumerate(plan.tasks)}
    results.sort(key=lambda r: order.get((r.brand, r.source), len(order)))
    for brand, source, reason in plan.skipped:
        results.append(
            FetchResult(
                brand=brand,
                source=source,
                abstention=_source_abstention(brand, source, "unavailable", reason),
            )
        )
    return results


# --------------------------------------------------------------------------- dedup


@dataclass(frozen=True)
class DedupOutcome:
    kept: list[Mention]
    dropped: dict[str, int]


def dedup_mentions(mentions: Sequence[Mention]) -> DedupOutcome:
    """CONTRACTS §Dedup precedence per ``(source, brand)``; keeps the original order."""
    items = [
        DedupItem(
            source=m.source,
            native_id=m.native_id,
            url=m.url,
            text=m.text,
            raw_ref=m.raw_ref,
            brand=m.brand,
        )
        for m in mentions
    ]
    result = dedup(items)
    kept_keys = {(i.brand, i.source, i.raw_ref) for i in result.kept}
    kept = [m for m in mentions if (m.brand, m.source, m.raw_ref) in kept_keys]
    dropped: Counter[str] = Counter()
    for _, reason, _ in result.dropped:
        dropped[reason] += 1
    return DedupOutcome(kept=kept, dropped=dict(dropped))


# --------------------------------------------------------------------------- result


@dataclass(frozen=True)
class RunResult:
    """What ``run`` produced and how the process should exit."""

    session_id: str
    out_dir: Path
    receipt: Receipt
    digest: Digest
    exit_code: int
    halted: bool
    written: tuple[Path, ...]

    @property
    def verdict(self) -> str:
        return self.receipt.verdict


def _reconcile(
    ledger: Ledger,
    client: MonidClient,
    *,
    started_at: datetime,
    options: RunOptions,
) -> ReconcileResult:
    if options.bounded_reconcile:
        return ledger.reconcile(
            client,
            started_at=started_at - RECONCILE_SLACK,
            reconciled_at=utcnow() + RECONCILE_SLACK,
        )
    return ledger.reconcile(client, started_at=None, reconciled_at=None)


def _llm_totals(
    label_run: LabelRun, topics: TopicsResult, voice_usage: Sequence[SeamUsage]
) -> LlmUsageTotals:
    totals = LlmUsageTotals()
    for kind, spend in label_run.spend.items():
        totals.add(kind, tokens=spend.tokens, cost_usd=spend.cost_usd, calls=spend.calls)
    for kind, usage in topics.usages:
        totals.record(kind, usage)
    for usage in voice_usage:
        totals.record("narrate", usage)
    return totals


def _write_jsonl(path: Path, lines: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def write_markdown(digest: Digest, receipt: Receipt, path: Path) -> Path:
    """``digest.md``: the digest, then the receipt card."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_digest(digest) + "\n" + render_receipt(receipt) + "\n", encoding="utf-8")
    return path


def _stage(name: str, started: float) -> float:
    now = time.monotonic()
    log.info("stage %s: %.2fs", name, now - started)
    return now


def run(
    query: Query,
    monid_client: MonidClient,
    ledger: Ledger,
    llm: LlmBackend,
    out_dir: Path,
    *,
    session_id: str | None = None,
    now: datetime | None = None,
    options: RunOptions = DEFAULT_OPTIONS,
) -> RunResult:
    """One session end to end; see the module docstring for the order and the exit codes."""
    started_at = now or utcnow()
    session = session_id or new_session_id(query.brand, started_at)
    out_dir.mkdir(parents=True, exist_ok=True)
    brands = list(brands_of(query))
    clock = time.monotonic()

    plan = build_plan(query)
    log.info("session %s: %d tasks, estimate $%.4f", session, len(plan.tasks), plan.estimate_usd)
    clock = _stage("plan", clock)

    fetched = fetch_all(
        query,
        plan,
        client=monid_client,
        ledger=ledger,
        out_dir=out_dir,
        options=options,
        now=started_at,
    )
    halted = monid_client.halted or any(r.halted for r in fetched)
    all_mentions = [m for r in fetched for m in r.mentions]
    source_abstentions = [r.abstention for r in fetched if r.abstention is not None]
    notes: list[str] = [n for r in fetched for n in r.notes]
    coverage_gaps = [
        CoverageGap(source=source, reason="unavailable", note=f"{brand}: {reason}")
        for brand, source, reason in plan.skipped
    ]
    clock = _stage("fetch", clock)

    deduped = dedup_mentions(all_mentions)
    kept = deduped.kept
    clock = _stage("dedup", clock)

    langs = Counter(m.lang for m in kept)
    kinds = Counter(m.match_kind for m in kept)
    log.info("language strata %s; match kinds %s", dict(langs), dict(kinds))
    clock = _stage("language+match", clock)

    cache_dir = options.cache_dir
    label_cache = LabelCache(cache_dir / "labels.jsonl") if cache_dir is not None else None
    label_run = label_mentions(
        kept, llm, brand_hints={query.brand: query.brand_hint}, cache=label_cache, seed=options.seed
    )
    labels = label_run.by_key()
    rows: list[tuple[Mention, Label]] = [
        (m, labels[(m.brand, m.mention_id)]) for m in kept if (m.brand, m.mention_id) in labels
    ]
    clock = _stage("label+corroborate", clock)

    topics = build_topics(
        rows,
        llm,
        cache_path=cache_dir / CACHE_FILENAME if cache_dir is not None else None,
        resamples=options.resamples,
        seed=options.seed,
    )
    rows = assign_topic_ids(rows, topics.assignments)
    labels = {(m.brand, m.mention_id): label for m, label in rows}
    notes.extend(topics.notes)
    topic_abstentions = list(topics.abstentions)
    covered = {t.brand for t in topics.topics} | {a.brand for a in topic_abstentions}
    for brand in brands:
        if brand not in covered:
            topic_abstentions.append(
                Abstention(
                    scope="topics",
                    brand=brand,
                    source=None,
                    reason="below_minimum",
                    detail=f"no topics: 0 relevant mentions, min_size {config.TOPIC_MIN_SIZE}",
                )
            )
    clock = _stage("topics", clock)

    stats: StatsResult = compute_stats(
        brands,
        rows,
        sources=list(query.sources),
        abstentions=source_abstentions,
        now=started_at,
        b=options.resamples,
        seed=options.seed,
        topic_names={t.topic_id: t.name for t in topics.topics},
    )
    notes.extend(stats.what_could_not_be_checked)
    clock = _stage("stats", clock)

    session_abstentions: list[Abstention] = []
    if halted:
        session_abstentions.append(
            Abstention(
                scope="session",
                brand=None,
                source=None,
                reason="halted",
                detail=(monid_client.breaker.reason or "Monid 402: breaker tripped")[:500],
            )
        )

    reconciliation = _reconcile(ledger, monid_client, started_at=started_at, options=options)
    clock = _stage("reconcile", clock)

    label_keyed = {(mention_id, brand): label for (brand, mention_id), label in labels.items()}
    mention_counts = count_mentions(
        fetched=len(all_mentions), kept=kept, labels=label_keyed, dedup_dropped=deduped.dropped
    )
    # Rows the labeler excluded (refused, unparseable, error after the SDK retries) carry no
    # Label, so ``count_mentions`` cannot see them; they are counted here under their reason.
    excluded_with_reason = dict(mention_counts.excluded_with_reason)
    for exclusion in label_run.excluded:
        excluded_with_reason[exclusion.reason] += 1
    mention_counts = mention_counts.model_copy(
        update={"excluded_with_reason": excluded_with_reason}
    )
    unlabelled = count_unlabelled(kept, label_keyed) - len(label_run.excluded)
    if unlabelled > 0:
        notes.append(
            unlabelled_note(unlabelled, "the labeler returned neither a label nor a reason")
        )

    def receipt_for(voice_usage: Sequence[SeamUsage], voice_abst: Sequence[Abstention]) -> Receipt:
        return build_receipt(
            session_id=session,
            query=query,
            runs=ledger.records,
            reconciliation=reconciliation,
            llm=_llm_totals(label_run, topics, voice_usage),
            mentions=mention_counts,
            audit=label_run.audit,
            abstentions=[*source_abstentions, *session_abstentions, *voice_abst],
            what_could_not_be_checked=notes,
            started_at=started_at,
            finished_at=utcnow(),
            replay=options.replay,
        )

    def digest_for(receipt: Receipt, narration: Narration) -> Digest:
        return build_digest(
            query=query,
            window=stats.window,
            share_of_voice=stats.share_of_voice,
            sentiment=stats.sentiment,
            by_source=stats.by_source,
            topics=topics.topics,
            events=stats.events,
            mentions=kept,
            labels=label_keyed,
            abstentions=[*stats.abstentions, *topic_abstentions],
            coverage_gaps=coverage_gaps,
            receipt=receipt,
            narration=narration,
        )

    receipt = receipt_for((), ())
    digest = digest_for(receipt, NO_NARRATION)
    clock = _stage("receipt+digest", clock)

    narration = NO_NARRATION
    voice_usage: tuple[SeamUsage, ...] = ()
    voice_abstentions: tuple[Abstention, ...] = ()
    if options.voice:
        voice = narrate(
            digest,
            backend=llm,
            client=monid_client,
            ledger=ledger,
            out_dir=out_dir,
            voice_id=options.voice_id,
            direct=options.tts_direct,
            api_key=options.tts_api_key,
        )
        narration, voice_usage, voice_abstentions = voice.narration, voice.usage, voice.abstentions
        if voice.record is not None and voice.record.run_id is not None:
            reconciliation = _reconcile(
                ledger, monid_client, started_at=started_at, options=options
            )
        clock = _stage("narration+tts", clock)

    receipt = receipt_for(voice_usage, voice_abstentions)
    digest = digest_for(receipt, narration)
    if narration.text is not None:
        regated = regate(narration, digest)
        if regated.numbers_verified != narration.numbers_verified:
            log.warning(
                "voice: numbers_verified %s against the final digest", regated.numbers_verified
            )
            narration = regated
            digest = digest_for(receipt, narration)

    written: list[Path] = [write_receipt(receipt, out_dir / RECEIPT_JSON)]
    written.extend(write_digest_files(digest, out_dir).values())
    written.append(write_markdown(digest, receipt, out_dir / DIGEST_MD))
    written.append(_write_jsonl(out_dir / MENTIONS_JSONL, [m.model_dump_json() for m in kept]))
    written.append(
        _write_jsonl(
            out_dir / LABELS_JSONL,
            [
                json.dumps(
                    {"brand": m.brand, "label": label.model_dump(mode="json")}, ensure_ascii=False
                )
                for m, label in rows
            ],
        )
    )
    runs_path = out_dir / RUNS_JSONL
    if ledger.path.resolve() != runs_path.resolve():
        written.append(_write_jsonl(runs_path, [r.model_dump_json() for r in ledger.records]))
    else:
        written.append(runs_path)
    if narration.mp3_path is not None:
        written.append(out_dir / Path(narration.mp3_path).name)
    _stage("write", clock)

    if halted:
        code = EXIT_HALTED
    elif not options.replay and receipt.verdict != "RECONCILED":
        code = EXIT_PARTIAL
    else:
        code = EXIT_OK
    return RunResult(
        session_id=session,
        out_dir=out_dir,
        receipt=receipt,
        digest=digest,
        exit_code=code,
        halted=halted,
        written=tuple(written),
    )


# --------------------------------------------------------------------------- reconcile later


def reconcile_session(
    session_dir: Path, client: MonidClient, *, now: datetime | None = None
) -> tuple[Receipt, Digest, int]:
    """``sonar reconcile --session``: rejoin the listing, rewrite the receipt and the digest cost.

    Every block that does not depend on the ledger (mentions, audit, abstentions, LLM
    totals, what could not be checked) is carried over from the stored receipt.
    """
    receipt_path = session_dir / RECEIPT_JSON
    stored = Receipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    digest = Digest.model_validate_json((session_dir / DIGEST_JSON).read_text(encoding="utf-8"))
    ledger = Ledger(session_dir / RUNS_JSONL)
    fetched_at = now or utcnow()
    result = ledger.reconcile(
        client,
        started_at=stored.timestamps.started_at - RECONCILE_SLACK,
        reconciled_at=fetched_at + RECONCILE_SLACK,
    )
    llm = LlmUsageTotals(
        usd=stored.totals.llm_usd,
        tokens=stored.totals.llm_tokens,
        calls=dict(stored.totals.llm_calls),
    )
    receipt = build_receipt(
        session_id=stored.session_id,
        query=stored.query,
        runs=ledger.records,
        reconciliation=result,
        llm=llm,
        mentions=stored.mentions,
        audit=stored.audit,
        abstentions=stored.abstentions,
        what_could_not_be_checked=stored.what_could_not_be_checked,
        started_at=stored.timestamps.started_at,
        finished_at=stored.timestamps.finished_at,
        replay=stored.replay,
        sonar_rev=stored.sonar_rev,
    )
    digest = requote_cost(digest, receipt)
    write_receipt(receipt, receipt_path)
    write_digest_files(digest, session_dir)
    write_markdown(digest, receipt, session_dir / DIGEST_MD)
    code = EXIT_OK if receipt.verdict == "RECONCILED" else EXIT_PARTIAL
    return receipt, digest, code


def replay_artifacts(session_dir: Path) -> tuple[Receipt, Digest]:
    """``sonar render --from``: the stored receipt and digest re-marked as a replay."""
    receipt = Receipt.model_validate_json((session_dir / RECEIPT_JSON).read_text(encoding="utf-8"))
    digest = Digest.model_validate_json((session_dir / DIGEST_JSON).read_text(encoding="utf-8"))
    replayed = receipt.model_copy(
        update={"replay": True, "verdict": "REPLAY"}
    ).with_content_digest()
    return replayed, requote_cost(digest, replayed)


# --------------------------------------------------------------------------- offline replay


def _fixture_bodies(fixtures_dir: Path) -> dict[str, dict[str, Any]]:
    """Recorded run bodies keyed by endpoint (the first file per endpoint, by name)."""
    bodies: dict[str, dict[str, Any]] = {}
    for path in sorted(fixtures_dir.glob("*.json")):
        if path.name in (FIXTURE_RUNS_PAGE, "labels.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        endpoint = data.get("endpoint")
        run_id = data.get("runId")
        if isinstance(endpoint, str) and isinstance(run_id, str) and endpoint not in bodies:
            bodies[endpoint] = data
    return bodies


def _fixture_tts_body() -> dict[str, Any]:
    return {
        "runId": FIXTURE_TTS_RUN_ID,
        "status": "COMPLETED",
        "providerResponse": {"httpStatus": 200},
        "output": {
            "audio": {
                "audio_base64": base64.b64encode(FIXTURE_MP3).decode("ascii"),
                "content_type": "audio/mpeg",
                "character_count": 0,
            }
        },
    }


def fixture_transport(fixtures_dir: Path = FIXTURES_DIR) -> httpx.MockTransport:
    """An ``httpx`` transport that replays the recorded fixtures; no network."""
    bodies = _fixture_bodies(fixtures_dir)
    by_run_id = {body["runId"]: body for body in bodies.values()}
    page_path = fixtures_dir / FIXTURE_RUNS_PAGE
    page: dict[str, Any] = (
        json.loads(page_path.read_text(encoding="utf-8")) if page_path.exists() else {"items": []}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/run":
            payload = json.loads(request.content)
            endpoint = payload.get("endpoint")
            if endpoint == config.ELEVENLABS_ENDPOINT:
                return httpx.Response(202, json={"runId": FIXTURE_TTS_RUN_ID, "status": "RUNNING"})
            body = bodies.get(endpoint)
            if body is None:
                return httpx.Response(404, json={"error": f"no recorded fixture for {endpoint}"})
            return httpx.Response(202, json={"runId": body["runId"], "status": "RUNNING"})
        if request.method == "GET" and path == "/v1/runs":
            return httpx.Response(200, json={**page, "nextCursor": None})
        if request.method == "GET" and path.startswith("/v1/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            if run_id == FIXTURE_TTS_RUN_ID:
                return httpx.Response(200, json=_fixture_tts_body())
            body = by_run_id.get(run_id)
            if body is None:
                return httpx.Response(404, json={"error": f"unknown run {run_id}"})
            return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": f"unscripted {request.method} {path}"})

    return httpx.MockTransport(handler)


def fixtures_client(fixtures_dir: Path = FIXTURES_DIR) -> MonidClient:
    """A ``MonidClient`` over :func:`fixture_transport` with its own breaker and no sleeps."""
    return MonidClient(
        "monid_test_fixtures_replay_key",
        transport=fixture_transport(fixtures_dir),
        sleep=lambda _s: None,
        breaker=Breaker(),
    )


def _decimal_text(value: float) -> str:
    return format(Decimal(repr(value)), "f")


def fixture_label(mention_id: str) -> LabelFixtureEntry:
    """A deterministic ``ok`` label for an id the fixture has no entry for."""
    digest = hashlib.sha256(mention_id.encode("utf-8")).digest()
    label = ("positive", "negative", "neutral")[digest[0] % 3]
    confidence = 0.65 + (digest[1] % 30) / 100
    return LabelFixtureEntry(
        status="ok",
        label=label,  # type: ignore[arg-type]
        about_brand=True,
        confidence=round(confidence, 2),
        rationale="offline fixture label",
    )


def fixture_narration(user: str) -> str:
    """A narration whose every number is in the digest JSON the prompt carries.

    Quotes the reconciled Monid cost (``cost.totals.monid_usd``), which the voice
    spend does not change in a replay, so the final digest still contains it.
    """
    marker = "Digest JSON:\n"
    start = user.find(marker)
    if start < 0:
        return "Offline replay; no signal."
    text = user[start + len(marker) :]
    end = text.find("\n\nWrite the narration")
    if end >= 0:
        text = text[:end]
    digest = json.loads(text)
    brand = digest.get("brand", "the brand")
    cost = _decimal_text(float(digest["cost"]["totals"]["monid_usd"]))
    sentiment = digest.get("sentiment") or []
    n = int(sentiment[0]["n"]) if sentiment else 0
    if n == 0:
        return f"{brand}: no signal this brief; cost ${cost} on Monid."
    net = sentiment[0].get("net")
    net_text = "not enough data" if net is None else _decimal_text(float(net))
    return (
        f"{brand}: {n} relevant mentions this brief; net sentiment {net_text}; "
        f"cost ${cost} on Monid."
    )


class FixtureLlm(FakeBackend):
    """The seam for an offline run: fixture labels, deterministic fill-ins, canned answers.

    ``classify`` answers from the labels fixture and synthesises a label for any id
    it lacks; ``complete_json`` returns a narration built from the digest in the
    prompt and a fixed topic name, so no canned answer is ever missing.
    """

    def __init__(self, labels: Mapping[str, LabelFixtureEntry] | None = None) -> None:
        super().__init__(labels, answers={"TopicName": {"name": "Offline fixture topic"}})

    def classify(self, batch: ClassifyBatch, model: str) -> ClassifyResult:
        for item in batch.items:
            if item.mention_id not in self._labels:
                self._labels[item.mention_id] = fixture_label(item.mention_id)
        return super().classify(batch, model)

    def complete_json(
        self, system: str, user: str, schema: type[SchemaT], model: str
    ) -> JsonResult[SchemaT]:
        if schema.__name__ == "NarrationSchema":
            value = schema.model_validate({"narration": fixture_narration(user)})
            usage = SeamUsage.price(
                model, len(user.split()), len(value.model_dump_json().split()), self._rates
            )
            self._record(schema.__name__, model)
            return JsonResult(value=value, usage=usage)
        return super().complete_json(system, user, schema, model)


def fixture_llm(labels_path: Path | None = None) -> FixtureLlm:
    labels: dict[str, LabelFixtureEntry] = {}
    if labels_path is not None and labels_path.exists():
        labels = load_labels_fixture(labels_path)
    return FixtureLlm(labels)


ClientFactory = Callable[[str], MonidClient]
LlmFactory = Callable[[str], LlmBackend]

__all__ = [
    "ARTIFACTS",
    "BRIEF_MP3",
    "DEFAULT_RUN_DEADLINE_S",
    "DIGEST_JSON",
    "DIGEST_MD",
    "EXIT_HALTED",
    "EXIT_OK",
    "EXIT_PARTIAL",
    "EXIT_USAGE",
    "FIXTURES_DIR",
    "LABELS_JSONL",
    "MAX_WORKERS",
    "MENTIONS_JSONL",
    "RECEIPT_JSON",
    "RUNS_JSONL",
    "STATS_JSON",
    "TOPICS_JSON",
    "ClientFactory",
    "DedupOutcome",
    "FetchResult",
    "FixtureLlm",
    "LlmFactory",
    "PlannedSource",
    "RunOptions",
    "RunResult",
    "SessionPlan",
    "abstain_reason_for",
    "brands_of",
    "build_plan",
    "dedup_mentions",
    "fetch_all",
    "fixture_label",
    "fixture_llm",
    "fixture_narration",
    "fixture_transport",
    "fixtures_client",
    "new_session_id",
    "payload_of",
    "plan_lines",
    "query_for",
    "reconcile_session",
    "replay_artifacts",
    "run",
    "write_markdown",
]
