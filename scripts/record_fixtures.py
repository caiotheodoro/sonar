#!/usr/bin/env python3
"""Record adapter fixtures from live Monid runs (design W3.7, ``tests/fixtures/README.md``).

Usage::

    uv run python scripts/record_fixtures.py --brand Nubank [--profile smoke] [--alias Nu]
        [--max-spend 0.50] [--fixtures-dir tests/fixtures] [--dry-run]

For one brand and one profile the recorder:

1. builds each adapter's ``input`` through ``build_input``; runs that need a parent
   result first (the Trustpilot and G2 review call after their lookup, the YouTube
   comment call after the video search) are built once the parent completes;
2. refuses to start when the summed ledger estimate exceeds ``--max-spend``;
3. submits every run through ``Ledger.submit`` (open-before-POST) and the real Monid
   client with the key from ``$MONID_API_KEY`` or ``~/.sonar/.env``, waiting for a
   terminal status;
4. saves every raw run body under the fixtures directory in the README layout;
5. fetches one page of ``GET /v1/runs`` into ``v1_runs_page.json`` and reconciles the
   ledger against that same page;
6. prints the per-run cost table, the totals and a ready-to-paste HANDOFF ledger row.

Nothing that reaches disk may contain the API key: every payload is redacted
structurally before it is written and every written file is scanned afterwards.
``--dry-run`` prints the planned inputs and exits before any client exists.

Exit codes: 0 recorded and reconciled; 2 bad input or missing key; 3 refused on
budget; 4 a run with an id is still unreconciled or the listing failed.

Type-check with the package sources on the path (``sonar`` ships no ``py.typed``)::

    MYPYPATH=src uv run mypy --strict scripts/record_fixtures.py tests/test_record_script.py
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, TextIO

from pydantic import ValidationError

from sonar.config import (
    MONID_RUNS_PAGE_LIMIT,
    PROFILES,
    SOURCE_PLAN,
    ProfileName,
    SourceName,
    SourcePlan,
)
from sonar.models import Query
from sonar.monid.client import (
    RUNS_PATH,
    MonidClient,
    MonidError,
    MonidHalted,
    MonidHTTPError,
    RunOutcome,
    RunRequest,
    load_api_key,
)
from sonar.monid.ledger import AlreadySubmitted, Ledger
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS

ROOT: Final = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURES_DIR: Final = ROOT / "tests" / "fixtures"
DEFAULT_MAX_SPEND_USD: Final = 0.50
DEFAULT_DEADLINE_S: Final = 300.0
DEFAULT_SETTLE_S: Final = 10.0
LEDGER_NAME: Final = "runs.jsonl"
RUNS_PAGE_NAME: Final = "v1_runs_page.json"
RECONCILE_SLACK: Final = timedelta(seconds=60)
"""Clock-skew allowance on both ends of the reconcile window (Monid vs local time)."""
REDACTED: Final = "[REDACTED]"
MIN_SECRET_LEN: Final = 8

EXIT_OK: Final = 0
EXIT_USAGE: Final = 2
EXIT_REFUSED: Final = 3
EXIT_PARTIAL: Final = 4

ADAPTER_MODULES: Final[tuple[str, ...]] = (
    "reddit",
    "youtube",
    "youtube_comments",
    "tiktok",
    "instagram",
    "google_maps",
    "facebook",
    "trustpilot",
    "g2",
    "news",
    "x",
)

SECRET_KEY_RE: Final = re.compile(
    r"authorization|api[-_]?key|token|secret|password|cookie", re.IGNORECASE
)
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"monid_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
)


class RecorderClient(MonidClient):
    """The real transport plus the single-page listing the fixture snapshot needs."""

    def runs_page(self, *, limit: int = MONID_RUNS_PAGE_LIMIT) -> dict[str, Any]:
        """One raw ``GET /v1/runs`` page, no cursor following (README: ``v1_runs_page.json``)."""
        return self._get_with_backoff(RUNS_PATH, {"limit": min(limit, MONID_RUNS_PAGE_LIMIT)})


ClientFactory = Callable[[str], RecorderClient]


@dataclass(frozen=True)
class PlannedRun:
    """One ``POST /v1/run`` whose input is known before anything is submitted."""

    source: SourceName
    provider: str
    endpoint: str
    input: dict[str, Any]
    estimate_usd: float
    role: str = "main"
    already_seq: int | None = None

    @property
    def request(self) -> RunRequest:
        return RunRequest(provider=self.provider, endpoint=self.endpoint, input=self.input)


@dataclass(frozen=True)
class DeferredRun:
    """A run whose input can only be built from a parent run's payload."""

    source: SourceName
    provider: str
    endpoint: str
    estimate_usd: float
    depends_on: str


@dataclass
class Plan:
    runs: list[PlannedRun] = field(default_factory=list)
    deferred: list[DeferredRun] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def estimate_usd(self) -> float:
        """Sum over runs still to submit; rows already holding a run id cost nothing."""
        pending = sum(r.estimate_usd for r in self.runs if r.already_seq is None)
        return pending + sum(d.estimate_usd for d in self.deferred)


@dataclass
class Recorded:
    """What one submission produced, for the cost table."""

    planned: PlannedRun
    local_seq: int | None
    outcome: RunOutcome | None
    payload_path: Path | None
    note: str | None = None


# --------------------------------------------------------------------------- planning


def import_adapters() -> None:
    for name in ADAPTER_MODULES:
        importlib.import_module(f"sonar.providers.{name}")


def _main_estimate(plan: SourcePlan, profile: ProfileName) -> float:
    """Estimate for the billed data call(s) of one source, lookup excluded."""
    cap = plan.caps[profile]
    results = cap if plan.cap_unit == "results" else 0
    return plan.n_calls(profile) * plan.per_call_usd + results * plan.per_result_usd


def build_plan(query: Query, *, ledger: Ledger | None = None, now: datetime | None = None) -> Plan:
    """Build every adapter input for the Query profile; never touches the network."""
    profile = PROFILES[query.profile]
    plan = Plan()
    for source in profile.sources:
        source_plan = SOURCE_PLAN[source]
        provider = PROVIDERS.get(source)
        if provider is None:
            plan.skipped.append((source, "no adapter registered"))
            continue
        if not provider.available:
            plan.skipped.append((source, provider.unavailable_reason or "adapter unavailable"))
            continue
        adapter: Any = provider
        try:
            if source == "youtube_comment":
                plan.deferred.append(
                    DeferredRun(
                        source=source,
                        provider=source_plan.provider,
                        endpoint=source_plan.endpoint,
                        estimate_usd=_main_estimate(source_plan, query.profile),
                        depends_on="youtube (video urls come from its payload)",
                    )
                )
            elif source_plan.lookup_endpoint is not None:
                plan.runs.append(
                    PlannedRun(
                        source=source,
                        provider=source_plan.provider,
                        endpoint=source_plan.lookup_endpoint,
                        input=adapter.build_input(query),
                        estimate_usd=source_plan.lookup_usd,
                        role="lookup",
                    )
                )
                plan.deferred.append(
                    DeferredRun(
                        source=source,
                        provider=source_plan.provider,
                        endpoint=source_plan.endpoint,
                        estimate_usd=_main_estimate(source_plan, query.profile),
                        depends_on=f"{source} lookup {source_plan.lookup_endpoint}",
                    )
                )
            elif source == "news":
                per_page = source_plan.per_call_usd
                for page in adapter.pages(query):
                    plan.runs.append(
                        PlannedRun(
                            source=source,
                            provider=source_plan.provider,
                            endpoint=source_plan.endpoint,
                            input=adapter.build_input(query, page=page, now=now),
                            estimate_usd=per_page,
                            role=f"page {page}",
                        )
                    )
            else:
                plan.runs.append(
                    PlannedRun(
                        source=source,
                        provider=source_plan.provider,
                        endpoint=source_plan.endpoint,
                        input=_build_input(adapter, query, now),
                        estimate_usd=_main_estimate(source_plan, query.profile),
                    )
                )
        except (ValueError, RuntimeError, AttributeError) as exc:
            plan.skipped.append((source, f"build_input failed: {exc}"))
    if ledger is not None:
        plan.runs = [_mark_submitted(run, ledger) for run in plan.runs]
    return plan


def _build_input(adapter: Any, query: Query, now: datetime | None) -> dict[str, Any]:
    """Call ``build_input`` with ``now`` when the adapter accepts it (reproducible digests)."""
    if now is None:
        result: dict[str, Any] = adapter.build_input(query)
        return result
    try:
        result = adapter.build_input(query, now=now)
    except TypeError:
        result = adapter.build_input(query)
    return result


def _mark_submitted(run: PlannedRun, ledger: Ledger) -> PlannedRun:
    existing = ledger.find_submitted(run.request.digest)
    if existing is None:
        return run
    return PlannedRun(
        source=run.source,
        provider=run.provider,
        endpoint=run.endpoint,
        input=run.input,
        estimate_usd=run.estimate_usd,
        role=run.role,
        already_seq=existing.local_seq,
    )


def dependents_for(
    query: Query, run: PlannedRun, outcome: RunOutcome, local_seq: int, plan: Plan
) -> list[PlannedRun]:
    """Runs that become buildable once *run* has a payload; failures land in ``plan.skipped``."""
    if not outcome.succeeded or outcome.body is None:
        for deferred in plan.deferred:
            if deferred.depends_on.startswith(run.source):
                plan.skipped.append((deferred.source, f"parent {run.source} run did not succeed"))
        return []
    follow: list[PlannedRun] = []
    source_plan = SOURCE_PLAN[run.source]
    adapter: Any = PROVIDERS[run.source]
    if run.role == "lookup":
        try:
            found = adapter.parse_search(outcome.body)
        except AdapterSchemaError as exc:
            plan.skipped.append((run.source, f"lookup payload drift: {exc}"))
            return []
        if found is None:
            plan.skipped.append((run.source, "lookup found no match; reviews run skipped"))
            return []
        follow.append(
            PlannedRun(
                source=run.source,
                provider=source_plan.provider,
                endpoint=source_plan.endpoint,
                input=adapter.build_input(query),
                estimate_usd=_main_estimate(source_plan, query.profile),
                role="reviews",
            )
        )
    if run.source == "youtube" and "youtube_comment" in query.sources:
        comments: Any = PROVIDERS.get("youtube_comment")
        comment_plan = SOURCE_PLAN["youtube_comment"]
        if comments is None or not comments.available:
            plan.skipped.append(("youtube_comment", "adapter unavailable"))
            return follow
        try:
            videos = adapter.parse(outcome.body, outcome.run_id, query.brand, local_seq=local_seq)
            comment_input = comments.build_input(query, videos=videos)
        except (AdapterSchemaError, ValueError) as exc:
            plan.skipped.append(("youtube_comment", f"not buildable from youtube payload: {exc}"))
            return follow
        follow.append(
            PlannedRun(
                source="youtube_comment",
                provider=comment_plan.provider,
                endpoint=comment_plan.endpoint,
                input=comment_input,
                estimate_usd=_main_estimate(comment_plan, query.profile),
                role="comments",
            )
        )
    return follow


# --------------------------------------------------------------------------- redaction


def redact(value: Any, secrets: Sequence[str]) -> Any:
    """Structural copy with secret-looking keys blanked and secret values replaced."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            if isinstance(key, str) and SECRET_KEY_RE.search(key) and isinstance(inner, str):
                out[key] = REDACTED
            else:
                out[key] = redact(inner, secrets)
        return out
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value


def redact_text(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        if len(secret) >= MIN_SECRET_LEN and secret in text:
            text = text.replace(secret, REDACTED)
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def scrub_files(paths: Iterable[Path], secrets: Sequence[str]) -> list[Path]:
    """Rewrite any written file that still carries a secret; return the paths touched."""
    touched: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        clean = redact_text(text, secrets)
        if clean != text:
            path.write_text(clean, encoding="utf-8")
            touched.append(path)
    return touched


def assert_clean(paths: Iterable[Path], secrets: Sequence[str]) -> None:
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for secret in secrets:
            if len(secret) >= MIN_SECRET_LEN and secret in text:
                raise RuntimeError(f"secret survived redaction in {path}")


# --------------------------------------------------------------------------- files


def brand_slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-") or "brand"


def payload_filename(provider: str, endpoint: str, brand: str, when: datetime) -> str:
    segment = endpoint.rstrip("/").rsplit("/", 1)[-1] or "root"
    stamp = when.astimezone(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    return f"{provider}_{segment}_{brand_slug(brand)}_{stamp}.json"


def write_json(path: Path, payload: Any, secrets: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(redact(payload, secrets), indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def page_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("items", "runs", "data"):
        candidate = page.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


# --------------------------------------------------------------------------- recording


def record_runs(
    query: Query,
    plan: Plan,
    *,
    client: RecorderClient,
    ledger: Ledger,
    fixtures_dir: Path,
    secrets: Sequence[str],
    deadline_s: float,
    out: TextIO,
) -> list[Recorded]:
    """Submit every planned run (and the dependents it unlocks) through the ledger."""
    recorded: list[Recorded] = []
    queue: deque[PlannedRun] = deque(plan.runs)
    while queue:
        run = queue.popleft()
        label = f"{run.source} {run.provider}{run.endpoint} [{run.role}]"
        if run.already_seq is not None:
            print(f"skip   {label}: already recorded as local_seq {run.already_seq}", file=out)
            recorded.append(
                Recorded(run, run.already_seq, None, None, note="already recorded (same digest)")
            )
            continue
        print(f"submit {label} est ${run.estimate_usd:.4f}", file=out)
        try:
            row, outcome = ledger.submit(
                client,
                run.request,
                brand=query.brand,
                source=run.source,
                estimate_usd=run.estimate_usd,
                deadline_s=deadline_s,
            )
        except AlreadySubmitted as exc:
            print(f"skip   {label}: {exc}", file=out)
            recorded.append(Recorded(run, exc.record.local_seq, None, None, note=str(exc)))
            continue
        except MonidHalted as exc:
            print(f"halt   {label}: {exc}; no further run is submitted", file=out)
            recorded.append(Recorded(run, None, None, None, note=f"halted: {exc}"))
            break
        path: Path | None = None
        if outcome.body is not None:
            name = payload_filename(run.provider, run.endpoint, query.brand, row.submitted_at)
            path = write_json(fixtures_dir / name, outcome.body, secrets)
        print(
            f"       -> local_seq {row.local_seq} run_id {row.run_id or '-'} "
            f"status {row.status} n_results {row.n_results if row.n_results is not None else '-'}"
            + (f" saved {path.name}" if path else ""),
            file=out,
        )
        recorded.append(Recorded(run, row.local_seq, outcome, path))
        queue.extendleft(reversed(dependents_for(query, run, outcome, row.local_seq, plan)))
    return recorded


# --------------------------------------------------------------------------- reporting


def print_plan(query: Query, plan: Plan, max_spend: float, out: TextIO) -> None:
    print(f"brand {query.brand!r} aliases {query.brand_aliases} profile {query.profile}", file=out)
    for run in plan.runs:
        suffix = f" (already recorded as local_seq {run.already_seq})" if run.already_seq else ""
        print(f"- {run.source} {run.provider}{run.endpoint} [{run.role}]", file=out)
        print(f"  estimate ${run.estimate_usd:.4f}{suffix}", file=out)
        print(json.dumps(run.input, indent=2, ensure_ascii=False, sort_keys=True), file=out)
    for deferred in plan.deferred:
        print(f"- {deferred.source} {deferred.provider}{deferred.endpoint} [deferred]", file=out)
        print(
            f"  estimate ${deferred.estimate_usd:.4f}; input built after {deferred.depends_on}",
            file=out,
        )
    for source, reason in plan.skipped:
        print(f"- {source} skipped: {reason}", file=out)
    print(f"estimate total ${plan.estimate_usd:.4f} (max-spend ${max_spend:.2f})", file=out)


def _fmt_money(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def print_cost_table(ledger: Ledger, seqs: Sequence[int], out: TextIO) -> tuple[float, float]:
    """Print this session's rows; return (estimate total, billed total from /v1/runs)."""
    header = (
        f"{'seq':>4} {'source':<16} {'endpoint':<36} {'run_id':<28} {'status':<20} "
        f"{'n':>4} {'est_usd':>8} {'cost_usd':>9} {'source':<12} {'billed':>6}"
    )
    print(header, file=out)
    print("-" * len(header), file=out)
    est_total = 0.0
    billed_total = 0.0
    for seq in seqs:
        row = ledger.get(seq)
        est_total += row.estimate_usd
        if row.cost_source == "/v1/runs" and row.cost_usd is not None:
            billed_total += row.cost_usd
        print(
            f"{row.local_seq:>4} {row.source or '-':<16} {row.endpoint:<36} "
            f"{row.run_id or '-':<28} {row.status:<20} "
            f"{row.n_results if row.n_results is not None else '-':>4} "
            f"{_fmt_money(row.estimate_usd):>8} {_fmt_money(row.cost_usd):>9} "
            f"{row.cost_source:<12} "
            f"{row.billed_units if row.billed_units is not None else '-':>6}",
            file=out,
        )
    print("-" * len(header), file=out)
    print(f"total estimate ${est_total:.4f}  total billed (/v1/runs) ${billed_total:.4f}", file=out)
    return est_total, billed_total


def handoff_row(
    query: Query, ledger: Ledger, seqs: Sequence[int], est: float, billed: float, task: str
) -> str:
    ids = ", ".join(ledger.get(seq).run_id or "null" for seq in seqs) or "none"
    by_source = "; ".join(
        f"{ledger.get(seq).source}={ledger.get(seq).n_results}"
        for seq in seqs
        if ledger.get(seq).n_results is not None
    )
    today = datetime.now(UTC).date().isoformat()
    return (
        f"| {today} | {task} | {ids} | {est:.2f} | {billed:.2f} | "
        f"{query.profile} {query.brand}: {len(seqs)} runs; n_results {by_source or 'none'} |"
    )


# --------------------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="record_fixtures", description="Record adapter fixtures from live Monid runs."
    )
    parser.add_argument("--brand", required=True, help="brand to fetch (Query.brand)")
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default="smoke", help="profile (default smoke)"
    )
    parser.add_argument(
        "--alias", action="append", default=[], help="brand alias; repeat for several"
    )
    parser.add_argument(
        "--max-spend",
        type=float,
        default=DEFAULT_MAX_SPEND_USD,
        help=f"refuse when the ledger estimate exceeds this (default {DEFAULT_MAX_SPEND_USD})",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="where payloads, runs.jsonl and v1_runs_page.json go",
    )
    parser.add_argument(
        "--deadline", type=float, default=DEFAULT_DEADLINE_S, help="seconds to wait per run"
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=DEFAULT_SETTLE_S,
        help="pause before GET /v1/runs so Apify billing settles",
    )
    parser.add_argument(
        "--runs-limit",
        type=int,
        default=MONID_RUNS_PAGE_LIMIT,
        help="GET /v1/runs page size (max 100)",
    )
    parser.add_argument("--task", default="W3.7", help="task id printed in the HANDOFF row")
    parser.add_argument(
        "--dry-run", action="store_true", help="print planned inputs and exit; no network"
    )
    return parser


def default_client_factory(api_key: str) -> RecorderClient:
    return RecorderClient(api_key)


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = default_client_factory,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    out: TextIO = sys.stdout,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        query = Query(brand=args.brand, brand_aliases=list(args.alias), profile=args.profile)
    except ValidationError as exc:
        print(f"invalid query: {exc}", file=out)
        return EXIT_USAGE

    import_adapters()
    fixtures_dir: Path = args.fixtures_dir
    ledger_path = fixtures_dir / LEDGER_NAME
    ledger = Ledger(ledger_path) if ledger_path.exists() else None
    plan = build_plan(query, ledger=ledger, now=now)
    print_plan(query, plan, args.max_spend, out)

    if plan.estimate_usd > args.max_spend:
        print(
            f"REFUSED: estimate ${plan.estimate_usd:.4f} exceeds --max-spend ${args.max_spend:.2f}; "
            "nothing submitted",
            file=out,
        )
        return EXIT_REFUSED
    if args.dry_run:
        print("dry run: no run submitted, no network access", file=out)
        return EXIT_OK

    try:
        api_key = load_api_key()
    except MonidError as exc:
        print(f"no API key: {exc}", file=out)
        return EXIT_USAGE
    secrets = [api_key]
    session_start = datetime.now(UTC)
    ledger = ledger or Ledger(ledger_path)
    client = client_factory(api_key)
    try:
        recorded = record_runs(
            query,
            plan,
            client=client,
            ledger=ledger,
            fixtures_dir=fixtures_dir,
            secrets=secrets,
            deadline_s=args.deadline,
            out=out,
        )
        seqs = [r.local_seq for r in recorded if r.local_seq is not None]
        submitted = [r for r in recorded if r.outcome is not None]
        written = [r.payload_path for r in recorded if r.payload_path is not None]
        code = EXIT_OK
        if submitted:
            if any(r.outcome is not None and r.outcome.run_id for r in submitted):
                sleep(args.settle_seconds)
            page_path = fixtures_dir / RUNS_PAGE_NAME
            try:
                page = client.runs_page(limit=args.runs_limit)
            except MonidHTTPError as exc:
                print(f"GET /v1/runs failed: {exc}; ledger rows stay unreconciled", file=out)
                code = EXIT_PARTIAL
            else:
                write_json(page_path, page, secrets)
                written.append(page_path)
                result = ledger.reconcile(
                    client,
                    started_at=session_start - RECONCILE_SLACK,
                    reconciled_at=datetime.now(UTC) + RECONCILE_SLACK,
                    listing=page_items(page),
                )
                print(
                    f"reconcile: {result.n_listed_in_window} listed in window; "
                    f"unmatched remote {result.unmatched_remote_run_ids or 'none'}; "
                    f"unreconciled local_seq {result.unreconciled_local_seqs or 'none'}",
                    file=out,
                )
                if any(seq in result.unreconciled_local_seqs for seq in seqs):
                    code = EXIT_PARTIAL
        for source, reason in plan.skipped:
            print(f"skipped {source}: {reason}", file=out)
        written.append(ledger_path)
        touched = scrub_files(written, secrets)
        for path in touched:
            print(f"redacted a secret that reached {path.name}", file=out)
        assert_clean(written, secrets)
        est, billed = print_cost_table(ledger, seqs, out)
        print("HANDOFF row:", file=out)
        print(handoff_row(query, ledger, seqs, est, billed, args.task), file=out)
        return code
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
