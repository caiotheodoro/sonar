"""``sonar.pipeline``: the integration layer against scripted transports and the fake seam.

The real ``MonidClient`` and ``Ledger`` run; only the HTTP layer is an
``httpx.MockTransport``. No network, no real model, no key on disk. The
offline replay uses the recorded W3.7 fixtures through ``fixtures_client``.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from sonar import pipeline
from sonar.config import SOURCE_PLAN
from sonar.llm.base import LlmBackend
from sonar.llm.fake import LabelFixtureEntry
from sonar.models import Query, Receipt, StatsFile
from sonar.monid import Breaker, Ledger, MonidClient
from sonar.pipeline import (
    ARTIFACTS,
    BRIEF_MP3,
    EXIT_HALTED,
    EXIT_OK,
    EXIT_PARTIAL,
    FIXTURES_DIR,
    MAX_WORKERS,
    FixtureLlm,
    RunOptions,
    build_plan,
    fixture_narration,
    fixtures_client,
    query_for,
    run,
)

REDDIT = SOURCE_PLAN["reddit"]
GMAPS = SOURCE_PLAN["google_maps"]
TTS_ENDPOINT = "/text-to-speech"

REDDIT_ITEMS: list[dict[str, Any]] = [
    {
        "dataType": "post",
        "id": "t3_abc123",
        "title": "Nubank raised my limit",
        "body": "Happy customer here, the app is great.",
        "createdAt": "2026-09-01T10:00:00Z",
        "upVotes": 12,
        "url": "https://www.reddit.com/r/brasil/comments/abc123/nubank/",
        "username": "someone",
    },
    {
        "dataType": "comment",
        "id": "t1_def456",
        "body": "Nubank support never answers, terrible experience.",
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
        "text": "Atendimento rápido e a conta é fácil de abrir.",
        "stars": 5,
        "publishedAtDate": "2026-08-30T12:00:00Z",
        "likesCount": 1,
        "name": "Ana",
        "title": "Nubank",
    }
]
MP3 = b"\xff\xfb\x90\x00" * 8


@dataclass
class Script:
    """Routes ``POST /v1/run`` by endpoint and lists every accepted run with a cost."""

    payloads: dict[str, list[dict[str, Any]]]
    costs: dict[str, float] = field(default_factory=dict)
    fail_listing: bool = False
    reject_402: bool = False
    hang: bool = False
    accepted: dict[str, str] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    threads: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _body(self, run_id: str, endpoint: str) -> dict[str, Any]:
        if endpoint == TTS_ENDPOINT:
            output: Any = {"audio": {"audio_base64": _b64(MP3), "character_count": 10}}
        else:
            output = self.payloads.get(endpoint, [])
        return {
            "runId": run_id,
            "status": "COMPLETED",
            "endpoint": endpoint,
            "providerResponse": {"httpStatus": 200},
            "output": output,
        }

    def listing(self) -> list[dict[str, Any]]:
        stamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return [
            {
                "runId": run_id,
                "status": "TIMED_OUT" if self.hang else "COMPLETED",
                "endpoint": endpoint,
                "providerResponse": {"httpStatus": 200},
                "cost": {"value": self.costs.get(endpoint, 0.0), "currency": "USD"},
                "billedUnits": len(self.payloads.get(endpoint, [])),
                "createdAt": stamp,
            }
            for run_id, endpoint in self.accepted.items()
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests.append(request)
            self.threads.append(threading.current_thread().name)
        path = request.url.path
        if request.method == "POST" and path == "/v1/run":
            if self.reject_402:
                return httpx.Response(402, json={"error": "insufficient credit"})
            body = json.loads(request.content)
            endpoint = body["endpoint"]
            with self.lock:
                run_id = f"RUN{len(self.accepted) + 1:03d}"
                self.accepted[run_id] = endpoint
            return httpx.Response(202, json={"runId": run_id, "status": "RUNNING"})
        if request.method == "GET" and path == "/v1/runs":
            if self.fail_listing:
                return httpx.Response(500, json={"error": "listing down"})
            return httpx.Response(200, json={"items": self.listing(), "nextCursor": None})
        if request.method == "GET" and path.startswith("/v1/runs/"):
            run_id = path.rsplit("/", 1)[-1]
            if self.hang:
                return httpx.Response(200, json={"runId": run_id, "status": "RUNNING"})
            return httpx.Response(200, json=self._body(run_id, self.accepted[run_id]))
        return httpx.Response(404, json={"error": f"unscripted {request.method} {path}"})

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def smoke_script(**overrides: Any) -> Script:
    return Script(
        payloads={REDDIT.endpoint: REDDIT_ITEMS, GMAPS.endpoint: GMAPS_ITEMS},
        costs={REDDIT.endpoint: 0.0314, GMAPS.endpoint: 0.000675, TTS_ENDPOINT: 0.005},
        **overrides,
    )


def client_for(script: Script, *, clock: Callable[[], float] | None = None) -> MonidClient:
    return MonidClient(
        "monid_test_KEY0123456789abcdef",
        transport=httpx.MockTransport(script),
        sleep=lambda _s: None,
        clock=clock or (lambda: 0.0),
        breaker=Breaker(),
    )


def smoke_query() -> Query:
    return Query(brand="Nubank", brand_aliases=["Nu"], profile="smoke")


def run_session(
    tmp_path: Path,
    script: Script,
    *,
    llm: LlmBackend | None = None,
    options: RunOptions | None = None,
    clock: Callable[[], float] | None = None,
) -> pipeline.RunResult:
    out_dir = tmp_path / "session"
    client = client_for(script, clock=clock)
    try:
        return run(
            smoke_query(),
            client,
            Ledger(out_dir / "runs.jsonl"),
            llm or FixtureLlm(),
            out_dir,
            session_id="20260902T120000Z-nubank-abc123",
            options=options or RunOptions(cache_dir=tmp_path / "cache"),
        )
    finally:
        client.close()


def artifact_names(out_dir: Path) -> set[str]:
    return {p.name for p in out_dir.iterdir() if p.is_file()}


# --------------------------------------------------------------------------- plan


class TestPlan:
    def test_smoke_plan_lists_reddit_and_maps_for_one_brand(self) -> None:
        plan = build_plan(smoke_query())
        assert [(t.brand, t.source) for t in plan.tasks] == [
            ("Nubank", "reddit"),
            ("Nubank", "google_maps"),
        ]
        assert plan.estimate_usd == pytest.approx(
            REDDIT.estimate_usd("smoke") + GMAPS.estimate_usd("smoke")
        )
        assert plan.skipped == ()

    def test_full_plan_covers_every_brand_and_defers_comments(self) -> None:
        query = Query(brand="Nubank", competitors=["Inter", "C6"], profile="full")
        plan = build_plan(query)
        assert set(plan.brands) == {"Nubank", "Inter", "C6"}
        comments = [t for t in plan.tasks if t.source == "youtube_comment"]
        assert len(comments) == 3 and all(t.depends_on == "youtube" for t in comments)
        per_brand = {b: len(plan.by_brand(b)) for b in plan.brands}
        assert per_brand == {"Nubank": 10, "Inter": 10, "C6": 10}
        assert plan.estimate_usd == pytest.approx(
            3 * sum(p.estimate_usd("full") for p in SOURCE_PLAN.values())
        )

    def test_competitor_query_carries_no_aliases(self) -> None:
        query = Query(brand="Nubank", brand_aliases=["Nu"], competitors=["Inter"], profile="lite")
        assert query_for(query, "Nubank") is query
        competitor = query_for(query, "Inter")
        assert (competitor.brand, competitor.brand_aliases, competitor.competitors) == (
            "Inter",
            [],
            [],
        )
        assert competitor.profile == "lite" and competitor.sources == query.sources
        with pytest.raises(ValueError):
            query_for(query, "Avenza")

    def test_thread_pool_width_is_six(self) -> None:
        assert MAX_WORKERS == 6 and RunOptions().max_workers == 6


class TestReportNotes:
    """`parse_with_report` returns heterogeneous report objects (reddit: cluster-key
    fallbacks; news: brand-match skips). The pipeline must not assume one shape."""

    def test_reddit_report_fallbacks_are_noted(self) -> None:
        report = SimpleNamespace(mentions=[], cluster_key_fallbacks=3)
        assert pipeline._report_notes("reddit", report) == [
            "cluster key fallback: reddit 3"
        ]

    def test_news_report_without_cluster_key_attr_does_not_raise(self) -> None:
        report = SimpleNamespace(mentions=[], skipped_no_match=0)
        assert pipeline._report_notes("news", report) == []

    def test_news_skipped_no_match_is_noted(self) -> None:
        report = SimpleNamespace(mentions=[], skipped_no_match=4)
        assert pipeline._report_notes("news", report) == [
            "news: 4 result(s) skipped, no brand match"
        ]

    def test_report_with_neither_field_is_silent(self) -> None:
        assert pipeline._report_notes("tiktok", SimpleNamespace(mentions=[])) == []

    def test_skipped_no_text_is_noted(self) -> None:
        report = SimpleNamespace(mentions=[], skipped_no_text=2)
        assert pipeline._report_notes("reddit", report) == [
            "reddit: 2 item(s) skipped, deleted or empty content"
        ]


# --------------------------------------------------------------------------- offline replay


class TestOfflineFixtures:
    def test_offline_run_produces_every_artifact_and_a_replay_receipt(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "offline"
        client = fixtures_client(FIXTURES_DIR)
        try:
            result = run(
                smoke_query(),
                client,
                Ledger(out_dir / "runs.jsonl"),
                FixtureLlm(),
                out_dir,
                session_id="20260902T120000Z-nubank-0ff1ce",
                options=RunOptions(replay=True, bounded_reconcile=False),
            )
        finally:
            client.close()
        assert result.exit_code == EXIT_OK
        names = artifact_names(out_dir)
        assert set(ARTIFACTS) <= names and BRIEF_MP3 in names
        receipt = Receipt.model_validate_json((out_dir / "receipt.json").read_text())
        assert receipt.replay is True and receipt.verdict == "REPLAY"
        assert receipt.mentions.fetched == 44 and receipt.mentions.by_source == {
            "reddit": 40,
            "google_maps": 4,
        }
        assert receipt.totals.monid_usd == pytest.approx(0.2507)
        assert receipt.totals.llm_usd > 0 and receipt.totals.total_usd > receipt.totals.monid_usd
        stats = StatsFile.model_validate_json((out_dir / "stats.json").read_text())
        assert stats.share_of_voice[0].brand == "Nubank"
        assert (
            json.loads((out_dir / "topics.json").read_text())
            == result.digest.model_dump(mode="json")["topics"]
        )
        mentions = (out_dir / "mentions.jsonl").read_text().splitlines()
        labels = [json.loads(line) for line in (out_dir / "labels.jsonl").read_text().splitlines()]
        assert len(mentions) == 44 and len(labels) == 44
        assert {row["brand"] for row in labels} == {"Nubank"}
        assert all(row["label"]["mention_id"] for row in labels)
        assert (out_dir / "brief.mp3").read_bytes() == pipeline.FIXTURE_MP3
        assert result.digest.narration.numbers_verified is True
        assert result.digest.narration.mp3_path is not None
        assert Path(result.digest.narration.mp3_path).name == BRIEF_MP3
        assert (out_dir / BRIEF_MP3) in result.written
        md = (out_dir / "digest.md").read_text()
        assert "# sonar digest — Nubank" in md and "**REPLAY**" in md

    def test_fixture_narration_quotes_only_digest_numbers(self) -> None:
        digest = {
            "brand": "Avenza",
            "cost": {"totals": {"monid_usd": 0.02, "total_usd": 0.0234}},
            "sentiment": [{"brand": "Avenza", "n": 0, "net": None}],
        }
        user = (
            f"Digest JSON:\n{json.dumps(digest)}\n\nWrite the narration (900 characters at most)."
        )
        assert fixture_narration(user) == "Avenza: no signal this brief; cost $0.02 on Monid."


# --------------------------------------------------------------------------- live paths


class TestLivePaths:
    def test_reconciled_run_exits_0_and_fetches_in_pool_threads(self, tmp_path: Path) -> None:
        script = smoke_script()
        result = run_session(tmp_path, script)
        assert result.exit_code == EXIT_OK and result.verdict == "RECONCILED"
        receipt = result.receipt
        assert receipt.replay is False
        assert receipt.mentions.fetched == 3 and receipt.mentions.deduped == 3
        assert receipt.totals.monid_usd == pytest.approx(0.0314 + 0.000675 + 0.005)
        assert receipt.totals.elevenlabs_usd == pytest.approx(0.005)
        assert receipt.reconciliation.unreconciled_local_seqs == []
        endpoints = {json.loads(r.content)["endpoint"] for r in script.posts()}
        assert endpoints == {REDDIT.endpoint, GMAPS.endpoint, TTS_ENDPOINT}
        fetch_threads = {t for t in script.threads if t.startswith("sonar-fetch")}
        assert fetch_threads, "fetch did not run on the pool"
        assert set(ARTIFACTS) <= artifact_names(result.out_dir)
        assert (result.out_dir / BRIEF_MP3).read_bytes() == MP3

    def test_zero_mentions_all_abstain_and_receipt_is_nonzero(self, tmp_path: Path) -> None:
        script = Script(
            payloads={REDDIT.endpoint: [], GMAPS.endpoint: []},
            costs={REDDIT.endpoint: 0.02, GMAPS.endpoint: 0.0, TTS_ENDPOINT: 0.001},
        )
        result = run_session(tmp_path, script)
        assert result.exit_code == EXIT_OK and result.verdict == "RECONCILED"
        receipt, digest = result.receipt, result.digest
        assert receipt.mentions.fetched == 0 and receipt.mentions.deduped == 0
        assert receipt.totals.total_usd > 0 and receipt.totals.monid_usd == pytest.approx(0.021)
        assert receipt.totals.monid_runs_zero_results == 2
        empties = [a for a in receipt.abstentions if a.scope == "source"]
        assert {(a.source, a.reason) for a in empties} == {
            ("reddit", "empty"),
            ("google_maps", "empty"),
        }
        (sov,) = digest.share_of_voice
        (sentiment,) = digest.sentiment
        assert sov.share is None and sov.ci95 is None and sov.wow.verdict == "ABSTAIN"
        assert sentiment.net is None and sentiment.wow.verdict == "ABSTAIN"
        assert sov.basis_sources == []
        assert digest.topics == [] and digest.top_mentions == []
        assert any(a.scope == "topics" for a in digest.abstentions)
        assert digest.narration.text is not None and "no signal" in digest.narration.text
        assert digest.narration.numbers_verified is True
        assert "$0.02" in digest.narration.text
        assert set(ARTIFACTS) <= artifact_names(result.out_dir)

    def test_402_halts_with_exit_3_and_still_writes_artifacts(self, tmp_path: Path) -> None:
        script = smoke_script(reject_402=True)
        result = run_session(tmp_path, script)
        assert result.exit_code == EXIT_HALTED and result.halted is True
        receipt = result.receipt
        assert any(a.scope == "session" and a.reason == "halted" for a in receipt.abstentions)
        assert all(a.reason == "halted" for a in receipt.abstentions if a.scope == "source")
        assert any(a.scope == "voice" and a.reason == "halted" for a in receipt.abstentions)
        assert receipt.mentions.fetched == 0
        assert all(r.run_id is None for r in receipt.runs)
        assert receipt.totals.monid_runs_failed >= 1
        assert len(script.posts()) <= 2, "no POST leaves the process once the breaker trips"
        assert set(ARTIFACTS) <= artifact_names(result.out_dir)
        assert BRIEF_MP3 not in artifact_names(result.out_dir)

    def test_listing_failure_leaves_partial_and_exit_4_then_reconcile_recovers(
        self, tmp_path: Path
    ) -> None:
        script = smoke_script(fail_listing=True)
        result = run_session(tmp_path, script)
        assert result.exit_code == EXIT_PARTIAL and result.verdict == "PARTIAL"
        assert result.receipt.reconciliation.fetched_at is None
        assert result.receipt.totals.monid_usd == 0.0
        assert result.receipt.reconciliation.unreconciled_local_seqs == [1, 2, 3]
        assert result.digest.cost.verdict == "PARTIAL"

        script.fail_listing = False
        client = client_for(script)
        try:
            receipt, digest, code = pipeline.reconcile_session(result.out_dir, client)
        finally:
            client.close()
        assert code == EXIT_OK and receipt.verdict == "RECONCILED"
        assert receipt.totals.monid_usd == pytest.approx(0.0314 + 0.000675 + 0.005)
        assert receipt.totals.llm_usd == result.receipt.totals.llm_usd
        assert receipt.mentions == result.receipt.mentions
        assert digest.cost.verdict == "RECONCILED"
        stored = Receipt.model_validate_json((result.out_dir / "receipt.json").read_text())
        assert stored.verdict == "RECONCILED" and stored.content_digest == receipt.content_digest
        assert "**RECONCILED**" in (result.out_dir / "digest.md").read_text()

    def test_deadline_abstains_and_never_resubmits(self, tmp_path: Path) -> None:
        script = smoke_script(hang=True)
        ticks = iter(range(10_000))
        result = run_session(
            tmp_path,
            script,
            options=RunOptions(run_deadline_s=5.0, voice=False, cache_dir=tmp_path / "cache"),
            clock=lambda: float(next(ticks)),
        )
        assert result.exit_code == EXIT_OK
        reasons = {(a.source, a.reason) for a in result.receipt.abstentions if a.scope == "source"}
        assert reasons == {("reddit", "deadline"), ("google_maps", "deadline")}
        # the listing settles the status (TIMED_OUT) and the cost; the deadline row kept its id
        assert {r.status for r in result.receipt.runs} == {"TIMED_OUT"}
        assert all(
            r.run_id is not None and r.cost_source == "/v1/runs" for r in result.receipt.runs
        )
        assert result.receipt.totals.monid_runs_failed == 2
        assert result.verdict == "RECONCILED"
        assert len(script.posts()) == 2
        assert result.digest.narration.text is None
        assert BRIEF_MP3 not in artifact_names(result.out_dir)

    def test_no_voice_makes_no_tts_run(self, tmp_path: Path) -> None:
        script = smoke_script()
        result = run_session(
            tmp_path, script, options=RunOptions(voice=False, cache_dir=tmp_path / "cache")
        )
        assert result.exit_code == EXIT_OK
        assert TTS_ENDPOINT not in {json.loads(r.content)["endpoint"] for r in script.posts()}
        assert result.receipt.totals.llm_calls["narrate"] == 0
        assert result.receipt.totals.elevenlabs_usd == 0.0

    def test_replay_artifacts_remark_the_stored_receipt(self, tmp_path: Path) -> None:
        result = run_session(tmp_path, smoke_script())
        receipt, digest = pipeline.replay_artifacts(result.out_dir)
        assert receipt.replay is True and receipt.verdict == "REPLAY"
        assert receipt.content_digest == receipt.compute_content_digest()
        assert digest.cost.verdict == "REPLAY" and digest.cost.totals == receipt.totals


# --------------------------------------------------------------------------- labeler exclusions


class TestLabelerExclusions:
    def test_excluded_rows_are_counted_under_their_reason(self, tmp_path: Path) -> None:
        """A refused classifier answer leaves no Label; the receipt still accounts for the row."""
        first = run_session(
            tmp_path / "first",
            smoke_script(),
            options=RunOptions(voice=False, cache_dir=tmp_path / "cache1"),
        )
        assert first.receipt.mentions.excluded_with_reason["refused"] == 0
        refused_id = first.digest.top_mentions[0].mention_id

        llm = FixtureLlm({refused_id: LabelFixtureEntry(status="refused", rationale="policy")})
        result = run_session(
            tmp_path / "second",
            smoke_script(),
            llm=llm,
            options=RunOptions(voice=False, cache_dir=tmp_path / "cache2"),
        )
        counts = result.receipt.mentions
        assert counts.deduped == 3 and counts.labelled == 2
        assert counts.excluded_with_reason["refused"] == 1
        failures = sum(counts.excluded_with_reason[k] for k in ("refused", "unparseable", "error"))
        assert counts.deduped == counts.labelled + failures
        assert not any(
            note.startswith("labelling:") for note in result.receipt.what_could_not_be_checked
        )
        labels = (result.out_dir / "labels.jsonl").read_text().splitlines()
        assert len(labels) == 2
        assert refused_id not in {json.loads(line)["label"]["mention_id"] for line in labels}
