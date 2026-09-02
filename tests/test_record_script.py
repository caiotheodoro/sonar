"""End-to-end drive of ``scripts/record_fixtures.py`` against a scripted transport.

The real ``RecorderClient`` (a ``MonidClient``) and the real ``Ledger`` run; only the
HTTP layer is a ``httpx.MockTransport`` serving canned payloads. No network, and the
API key is a fake set through ``MONID_API_KEY`` so ``~/.sonar/.env`` is never read.

Type-check together with the script and the package sources on the path::

    MYPYPATH=src uv run mypy --strict scripts/record_fixtures.py tests/test_record_script.py
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from sonar.config import PROFILES, SOURCE_PLAN
from sonar.models import Query
from sonar.monid import BREAKER, Ledger
from sonar.providers import google_maps, reddit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import record_fixtures as rf

FAKE_KEY = "monid_live_TESTKEY0123456789abcdefABCDEF"
NOW = datetime(2026, 9, 2, 15, 30, tzinfo=UTC)
LISTED_AT = datetime.now(UTC).replace(microsecond=0)
REDDIT = SOURCE_PLAN["reddit"]
GMAPS = SOURCE_PLAN["google_maps"]

REDDIT_ITEMS: list[dict[str, Any]] = [
    {
        "dataType": "post",
        "id": "t3_abc123",
        "title": "Nubank raised my limit",
        "body": "Happy customer here.",
        "createdAt": "2026-09-01T10:00:00Z",
        "upVotes": 12,
        "url": "https://www.reddit.com/r/brasil/comments/abc123/nubank/",
        "username": "someone",
    },
    {
        "dataType": "comment",
        "id": "t1_def456",
        "body": "Nubank support never answers.",
        "createdAt": "2026-09-01T11:00:00Z",
        "upVotes": 3,
        "postId": "t3_abc123",
        "url": "https://www.reddit.com/r/brasil/comments/abc123/nubank/def456/",
        "username": "other",
    },
]
GMAPS_ITEMS: list[dict[str, Any]] = [
    {
        "reviewId": "r1",
        "text": "Nubank agency was quick.",
        "stars": 5,
        "publishedAtDate": "2026-08-30T12:00:00Z",
        "likesCount": 1,
        "name": "Ana",
        "title": "Nubank",
    }
]


def canned_body(run_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """A Monid run body that also plants the key where a careless echo would put it."""
    return {
        "runId": run_id,
        "status": "SUCCEEDED",
        "providerResponse": {"httpStatus": 200},
        "output": items,
        "debug": {
            "authorization": f"Bearer {FAKE_KEY}",
            "note": f"sent with {FAKE_KEY} inside a string",
        },
    }


@dataclass
class Script:
    """Routes POST /v1/run by endpoint, polls to SUCCEEDED, serves one listing page."""

    run_ids: dict[str, str]
    listing: list[dict[str, Any]]
    payloads: dict[str, list[dict[str, Any]]]
    fail_listing: bool = False
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "POST" and path == "/v1/run":
            body = json.loads(request.content)
            run_id = self.run_ids[body["endpoint"]]
            return httpx.Response(202, json={"runId": run_id, "status": "RUNNING"})
        if request.method == "GET" and path == "/v1/runs":
            if self.fail_listing:
                return httpx.Response(500, json={"error": "listing down"})
            return httpx.Response(200, json={"items": self.listing, "nextCursor": None})
        if request.method == "GET" and path.startswith("/v1/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            endpoint = next(e for e, r in self.run_ids.items() if r == run_id)
            return httpx.Response(200, json=canned_body(run_id, self.payloads[endpoint]))
        return httpx.Response(404, json={"error": f"unscripted {request.method} {path}"})

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


def listing_item(run_id: str, cost: float, billed: int) -> dict[str, Any]:
    return {
        "runId": run_id,
        "status": "SUCCEEDED",
        "providerResponse": {"httpStatus": 200},
        "price": {"per": "result"},
        "cost": {"value": cost, "currency": "USD"},
        "billedUnits": billed,
        "createdAt": LISTED_AT.isoformat(),
        "meta": {"apiKey": FAKE_KEY},
    }


def smoke_script(*, drop_from_listing: str | None = None, fail_listing: bool = False) -> Script:
    listing = [
        listing_item("run_reddit_001", 0.0314, 2),
        listing_item("run_gmaps_001", 0.000675, 1),
    ]
    if drop_from_listing is not None:
        listing = [item for item in listing if item["runId"] != drop_from_listing]
    return Script(
        run_ids={REDDIT.endpoint: "run_reddit_001", GMAPS.endpoint: "run_gmaps_001"},
        listing=listing,
        payloads={REDDIT.endpoint: REDDIT_ITEMS, GMAPS.endpoint: GMAPS_ITEMS},
        fail_listing=fail_listing,
    )


def make_factory(script: Script) -> rf.ClientFactory:
    def factory(api_key: str) -> rf.RecorderClient:
        assert api_key == FAKE_KEY
        return rf.RecorderClient(
            api_key,
            transport=httpx.MockTransport(script),
            sleep=lambda _s: None,
            clock=lambda: 0.0,
        )

    return factory


def refuse_factory(api_key: str) -> rf.RecorderClient:
    raise AssertionError("client must not be built in this mode")


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MONID_API_KEY", FAKE_KEY)
    monkeypatch.setenv("SONAR_ENV", "/nonexistent/.env")
    BREAKER.reset()
    yield
    BREAKER.reset()


def run_main(
    tmp_path: Path, script: Script | None, *extra: str, dry_run: bool = False
) -> tuple[int, str, Path]:
    fixtures = tmp_path / "fixtures"
    argv = ["--brand", "Nubank", "--alias", "Nu", "--fixtures-dir", str(fixtures), *extra]
    if dry_run:
        argv.append("--dry-run")
    import io

    out = io.StringIO()
    factory = make_factory(script) if script is not None else refuse_factory
    code = rf.main(argv, client_factory=factory, sleep=lambda _s: None, now=NOW, out=out)
    return code, out.getvalue(), fixtures


def all_text_under(path: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in path.rglob("*") if p.is_file())


# --------------------------------------------------------------------------- dry run / refusal


def test_dry_run_prints_planned_inputs_and_builds_no_client(tmp_path: Path) -> None:
    code, out, fixtures = run_main(tmp_path, None, dry_run=True)
    assert code == rf.EXIT_OK
    assert "dry run" in out
    query = Query(brand="Nubank", brand_aliases=["Nu"], profile="smoke")
    reddit_input = reddit.PROVIDER.build_input(query, now=NOW)
    gmaps_input = google_maps.PROVIDER.build_input(query, now=NOW)
    assert json.dumps(reddit_input, indent=2, ensure_ascii=False, sort_keys=True) in out
    assert json.dumps(gmaps_input, indent=2, ensure_ascii=False, sort_keys=True) in out
    assert REDDIT.endpoint in out and GMAPS.endpoint in out
    expected = PROFILES["smoke"].estimate_usd_per_brand()
    assert f"estimate total ${expected:.4f}" in out
    assert not fixtures.exists()


def test_plan_estimate_matches_profile_estimate() -> None:
    rf.import_adapters()
    query = Query(brand="Nubank", profile="smoke")
    plan = rf.build_plan(query, now=NOW)
    assert [r.source for r in plan.runs] == ["reddit", "google_maps"]
    assert plan.deferred == [] and plan.skipped == []
    assert plan.estimate_usd == pytest.approx(PROFILES["smoke"].estimate_usd_per_brand())


def test_lite_plan_defers_dependent_runs() -> None:
    rf.import_adapters()
    query = Query(brand="Nubank", profile="lite")
    plan = rf.build_plan(query, now=NOW)
    deferred = {d.source for d in plan.deferred}
    assert "youtube_comment" in deferred
    lookups = {r.source: r.endpoint for r in plan.runs if r.role == "lookup"}
    for source in ("trustpilot", "g2"):
        assert lookups.get(source) == SOURCE_PLAN[source].lookup_endpoint
        assert source in deferred
    skipped = {source for source, _ in plan.skipped}
    skipped_estimate = sum(
        source_plan.estimate_usd("lite")
        for name, source_plan in SOURCE_PLAN.items()
        if name in skipped
    )
    expected = PROFILES["lite"].estimate_usd_per_brand()
    assert plan.estimate_usd + skipped_estimate == pytest.approx(expected)


def test_refuses_when_estimate_exceeds_max_spend(tmp_path: Path) -> None:
    code, out, fixtures = run_main(tmp_path, None, "--max-spend", "0.01")
    assert code == rf.EXIT_REFUSED
    assert "REFUSED" in out
    assert not fixtures.exists()


def test_invalid_brand_exits_2(tmp_path: Path) -> None:
    code, out, _ = rf_main_with_brand(tmp_path, "!!!")
    assert code == rf.EXIT_USAGE
    assert "invalid query" in out


def rf_main_with_brand(tmp_path: Path, brand: str) -> tuple[int, str, Path]:
    import io

    out = io.StringIO()
    fixtures = tmp_path / "fixtures"
    code = rf.main(
        ["--brand", brand, "--fixtures-dir", str(fixtures), "--dry-run"],
        client_factory=refuse_factory,
        out=out,
    )
    return code, out.getvalue(), fixtures


# --------------------------------------------------------------------------- end to end


def test_smoke_records_payloads_ledger_page_and_reconciles(tmp_path: Path) -> None:
    script = smoke_script()
    code, out, fixtures = run_main(tmp_path, script)
    assert code == rf.EXIT_OK, out

    posts = script.posts()
    assert [json.loads(p.content)["endpoint"] for p in posts] == [REDDIT.endpoint, GMAPS.endpoint]
    assert all(p.headers["Authorization"] == f"Bearer {FAKE_KEY}" for p in posts)

    payloads = sorted(p.name for p in fixtures.glob("apify_*_nubank_*.json"))
    assert payloads == [
        f"apify_google-maps-reviews-scraper_nubank_{_stamp(fixtures, 2)}.json",
        f"apify_reddit-scraper-lite_nubank_{_stamp(fixtures, 1)}.json",
    ]
    reddit_payload = json.loads((fixtures / payloads[1]).read_text(encoding="utf-8"))
    assert reddit_payload["output"] == REDDIT_ITEMS
    assert reddit_payload["debug"] == {
        "authorization": rf.REDACTED,
        "note": f"sent with {rf.REDACTED} inside a string",
    }

    records = Ledger(fixtures / "runs.jsonl").records
    assert [(r.source, r.run_id) for r in records] == [
        ("reddit", "run_reddit_001"),
        ("google_maps", "run_gmaps_001"),
    ]
    assert all(r.cost_source == "/v1/runs" for r in records)
    assert [r.cost_usd for r in records] == [0.0314, 0.000675]
    assert [r.billed_units for r in records] == [2, 1]
    assert [r.n_results for r in records] == [2, 1]
    assert records[0].estimate_usd == pytest.approx(REDDIT.estimate_usd("smoke"))

    page = json.loads((fixtures / "v1_runs_page.json").read_text(encoding="utf-8"))
    assert [item["runId"] for item in page["items"]] == ["run_reddit_001", "run_gmaps_001"]
    assert page["items"][0]["meta"]["apiKey"] == rf.REDACTED

    assert "run_reddit_001" in out and "run_gmaps_001" in out
    assert "total billed (/v1/runs) $0.0321" in out
    assert "unmatched remote none" in out and "unreconciled local_seq none" in out
    assert "| W3.7 | run_reddit_001, run_gmaps_001 |" in out
    assert FAKE_KEY not in all_text_under(fixtures)
    assert FAKE_KEY not in out


def _stamp(fixtures: Path, seq: int) -> str:
    row = Ledger(fixtures / "runs.jsonl").get(seq)
    return row.submitted_at.astimezone(UTC).strftime("%Y-%m-%dT%H%M%SZ")


def test_rerun_with_same_inputs_submits_nothing(tmp_path: Path) -> None:
    first = smoke_script()
    code, _, fixtures = run_main(tmp_path, first)
    assert code == rf.EXIT_OK
    before = sorted(p.name for p in fixtures.iterdir())

    second = smoke_script()
    code, out, _ = run_main(tmp_path, second)
    assert code == rf.EXIT_OK
    assert second.posts() == []
    assert "already recorded as local_seq 1" in out
    assert "already recorded as local_seq 2" in out
    assert "estimate total $0.0000" in out
    assert sorted(p.name for p in fixtures.iterdir()) == before
    assert len(Ledger(fixtures / "runs.jsonl").records) == 2


def test_missing_listing_entry_exits_partial(tmp_path: Path) -> None:
    script = smoke_script(drop_from_listing="run_gmaps_001")
    code, out, fixtures = run_main(tmp_path, script)
    assert code == rf.EXIT_PARTIAL
    records = {r.source: r for r in Ledger(fixtures / "runs.jsonl").records}
    assert records["reddit"].cost_source == "/v1/runs"
    assert records["google_maps"].cost_source == "unreconciled"
    assert records["google_maps"].cost_usd is None
    assert "unreconciled local_seq [2]" in out


def test_listing_failure_exits_partial_and_writes_no_page(tmp_path: Path) -> None:
    script = smoke_script(fail_listing=True)
    code, out, fixtures = run_main(tmp_path, script)
    assert code == rf.EXIT_PARTIAL
    assert "GET /v1/runs failed" in out
    assert not (fixtures / "v1_runs_page.json").exists()
    assert all(r.cost_source == "unreconciled" for r in Ledger(fixtures / "runs.jsonl").records)
    assert FAKE_KEY not in all_text_under(fixtures)


# --------------------------------------------------------------------------- redaction unit


def test_redact_blanks_secret_keys_and_values() -> None:
    payload: dict[str, Any] = {
        "Authorization": "Bearer abc",
        "nested": [{"api_key": "x", "text": f"key {FAKE_KEY} here"}],
        "plain": "sk-abcdefghijklmnopqrstuvwxyz0123",
        "count": 3,
    }
    clean = rf.redact(payload, [FAKE_KEY])
    assert clean == {
        "Authorization": rf.REDACTED,
        "nested": [{"api_key": rf.REDACTED, "text": f"key {rf.REDACTED} here"}],
        "plain": rf.REDACTED,
        "count": 3,
    }
    assert payload["nested"][0]["text"].count(FAKE_KEY) == 1


def test_scrub_files_rewrites_and_assert_clean_raises(tmp_path: Path) -> None:
    leaked = tmp_path / "leak.json"
    leaked.write_text(json.dumps({"x": FAKE_KEY}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="secret survived"):
        rf.assert_clean([leaked], [FAKE_KEY])
    assert rf.scrub_files([leaked], [FAKE_KEY]) == [leaked]
    assert json.loads(leaked.read_text(encoding="utf-8")) == {"x": rf.REDACTED}
    rf.assert_clean([leaked], [FAKE_KEY])
    assert rf.scrub_files([leaked, tmp_path / "absent.json"], [FAKE_KEY]) == []


def test_payload_filename_follows_readme_layout() -> None:
    name = rf.payload_filename("apify", REDDIT.endpoint, "Nu Bank S.A.", NOW)
    assert name == "apify_reddit-scraper-lite_nu-bank-s-a_2026-09-02T153000Z.json"
