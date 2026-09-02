"""Report layer: receipt (golden, hand-summed totals, verdicts, verify), digest, Markdown.

The golden ``tests/golden/receipt.json`` is a PARTIAL receipt on purpose: it carries
a zero-result billed run, a succeeded ``$0`` sync run with no id, a locally rejected
run, a provider failure, the ElevenLabs voice run and one unreconciled run that
contributes nothing and is listed. Its totals are summed by hand below, digit by
digit, not read back from the code.

The golden embeds ``models.SCHEMA_REV`` and the content digest over it, so a
``schema_rev`` bump regenerates it (and nothing else changes)::

    uv run python -c "from tests.test_receipt import build_golden_receipt as b; \
        from sonar.report.receipt import receipt_json as j; \
        open('tests/golden/receipt.json', 'w').write(j(b()))"
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from sonar import __version__, config
from sonar.llm.fake import FakeBackend
from sonar.models import (
    SCHEMA_REV,
    Abstention,
    Audit,
    BySourceEntry,
    CoverageGap,
    DateRange,
    Label,
    Mention,
    MentionCounts,
    Query,
    Receipt,
    Reconciliation,
    RunRecord,
    SentimentEntry,
    SovEntry,
    StatsFile,
    Window,
    WowNet,
    WowShare,
    input_digest_for,
    mention_id_for,
)
from sonar.monid.ledger import ReconcileResult
from sonar.report import markdown
from sonar.report.digest import (
    X_COVERAGE_GAP,
    build_digest,
    rank_top_mentions,
    requote_cost,
    stats_file_for,
    write_digest_files,
)
from sonar.report.incumbent import BRAND24_TEAM
from sonar.report.receipt import (
    VERIFY_INVALID,
    VERIFY_NOT_RECONCILED,
    VERIFY_OK,
    X_NOT_CHECKED,
    LlmUsageTotals,
    build_audit,
    build_receipt,
    count_mentions,
    count_unlabelled,
    load_receipt,
    receipt_json,
    resolve_sonar_rev,
    unlabelled_note,
    verify_receipt,
    verify_receipt_file,
    write_receipt,
)

GOLDEN = Path(__file__).parent / "golden" / "receipt.json"

T0 = datetime(2026, 9, 2, 9, 0, 0, tzinfo=UTC)
FINISHED = T0 + timedelta(minutes=10)
RECONCILED_AT = T0 + timedelta(minutes=11)
SESSION = "20260902T090000Z-nubank-a1b2c3"
SONAR_REV = "0.1.0+82d0ab5"

# --------------------------------------------------------------------------- fixture inputs


def query() -> Query:
    return Query(brand="Nubank", competitors=["Inter"], profile="lite")


def run(**overrides: Any) -> RunRecord:
    base: dict[str, Any] = {
        "local_seq": 1,
        "run_id": "01RUN1",
        "provider": "apify",
        "endpoint": "/trudax/reddit-scraper-lite",
        "brand": "Nubank",
        "source": "reddit",
        "input_digest": input_digest_for({"searches": ["Nubank"], "maxItems": 20}),
        "submitted_at": T0,
        "completed_at": T0 + timedelta(seconds=90),
        "status": "COMPLETED",
        "provider_http_status": 200,
        "n_results": 40,
        "estimate_usd": 0.248,
        "cost_usd": 0.248,
        "billed_units": 40,
        "cost_source": "/v1/runs",
        "attempts": 1,
        "error": None,
    }
    base.update(overrides)
    return RunRecord.model_validate(base)


def ledger_rows() -> list[RunRecord]:
    """Eight rows, deliberately out of order so ``build_receipt`` has to sort them."""
    rows = [
        run(),
        run(
            local_seq=2,
            run_id="01RUN2",
            endpoint="/compass/google-maps-reviews-scraper",
            source="google_maps",
            input_digest=input_digest_for({"placeIds": ["nubank"], "maxReviews": 25}),
            submitted_at=T0 + timedelta(seconds=90),
            completed_at=T0 + timedelta(seconds=150),
            n_results=50,
            estimate_usd=0.03375,
            cost_usd=0.03375,
            billed_units=50,
        ),
        # Zero-result run that was still billed (the fixed per-call part of the price, H4).
        run(
            local_seq=3,
            run_id="01RUN3",
            brand="Inter",
            input_digest=input_digest_for({"searches": ["Inter"], "maxItems": 20}),
            submitted_at=T0 + timedelta(seconds=150),
            completed_at=T0 + timedelta(seconds=200),
            n_results=0,
            estimate_usd=0.248,
            cost_usd=0.02,
            billed_units=0,
        ),
        # Succeeded $0 sync run that returned no run id: local, not failed (D013 N6).
        run(
            local_seq=4,
            run_id=None,
            provider="tinyfish",
            endpoint="/search",
            source="news",
            input_digest=input_digest_for({"queryParams": {"query": "Nubank"}}),
            submitted_at=T0 + timedelta(seconds=200),
            completed_at=T0 + timedelta(seconds=205),
            n_results=3,
            estimate_usd=0.0,
            cost_usd=0.0,
            billed_units=None,
            cost_source="local",
        ),
        # Rejected locally by HTTP 402 before a run id existed: local, failed.
        run(
            local_seq=5,
            run_id=None,
            endpoint="/apidojo/tiktok-scraper",
            source="tiktok",
            input_digest=input_digest_for({"keywords": ["Nubank"], "maxItems": 20}),
            submitted_at=T0 + timedelta(seconds=205),
            completed_at=None,
            status="LOCAL_REJECTED_402",
            provider_http_status=None,
            n_results=0,
            estimate_usd=0.009,
            cost_usd=0.0,
            billed_units=None,
            cost_source="local",
            error="402 Payment Required: insufficient balance",
        ),
        # Provider failure, reconciled at $0 with zero results.
        run(
            local_seq=6,
            run_id="01RUN6",
            endpoint="/streamers/youtube-scraper",
            brand="Inter",
            source="youtube",
            input_digest=input_digest_for({"searchQueries": ["Inter"], "maxResults": 5}),
            submitted_at=T0 + timedelta(seconds=210),
            completed_at=T0 + timedelta(seconds=260),
            status="FAILED",
            provider_http_status=500,
            n_results=0,
            estimate_usd=0.0225,
            cost_usd=0.0,
            billed_units=0,
            error="FAILED",
        ),
        # The ElevenLabs voice run: a Monid run with brand and source null.
        run(
            local_seq=7,
            run_id="01RUN7",
            provider="elevenlabs",
            endpoint="/text-to-speech",
            brand=None,
            source=None,
            input_digest=input_digest_for({"text": "Nubank led share of voice."}),
            submitted_at=T0 + timedelta(seconds=400),
            completed_at=T0 + timedelta(seconds=405),
            n_results=1,
            estimate_usd=0.0015,
            cost_usd=0.0123,
            billed_units=30,
        ),
        # Not yet in the listing: contributes $0 and is listed as unreconciled.
        run(
            local_seq=8,
            run_id="01RUN8",
            endpoint="/compass/google-maps-reviews-scraper",
            brand="Inter",
            source="google_maps",
            input_digest=input_digest_for({"placeIds": ["inter"], "maxReviews": 25}),
            submitted_at=T0 + timedelta(seconds=260),
            completed_at=T0 + timedelta(seconds=320),
            n_results=25,
            estimate_usd=0.016875,
            cost_usd=None,
            billed_units=None,
            cost_source="unreconciled",
        ),
    ]
    return [rows[6], rows[0], rows[7], rows[2], rows[1], rows[4], rows[3], rows[5]]


def llm_usage() -> LlmUsageTotals:
    totals = LlmUsageTotals()
    totals.add("classify", tokens=3000, cost_usd=0.0021, calls=3)
    totals.add("tiebreak", tokens=400, cost_usd=0.0026)
    totals.add("embed", tokens=2000, cost_usd=0.00004)
    totals.add("name_topic", tokens=300, cost_usd=0.00012)
    totals.add("narrate", tokens=500, cost_usd=0.0005)
    return totals


def mention_counts() -> MentionCounts:
    return MentionCounts(
        fetched=118,
        deduped=110,
        labelled=100,
        excluded_with_reason={
            "not_about_brand": 6,
            "irrelevant_label": 2,
            "refused": 1,
            "unparseable": 0,
            "error": 0,
            "dedup_native_id": 5,
            "dedup_url": 2,
            "dedup_text": 1,
        },
        by_source={"reddit": 37, "google_maps": 70, "news": 3},
        by_brand={"Nubank": 85, "Inter": 25},
    )


def audit() -> Audit:
    return Audit(n_sample=10, n_agree=9, agreement=0.9, tiebreak_calls=14, tiebreak_overflow=2)


def abstentions() -> list[Abstention]:
    return [
        Abstention(
            scope="source",
            brand="Inter",
            source="reddit",
            reason="empty",
            detail="0 results from /trudax/reddit-scraper-lite",
        ),
        Abstention(
            scope="source",
            brand="Nubank",
            source="tiktok",
            reason="halted",
            detail="Monid 402: breaker stopped the session before the run was accepted",
        ),
        Abstention(
            scope="source",
            brand="Inter",
            source="youtube",
            reason="provider_failed",
            detail="FAILED, provider HTTP 500",
        ),
    ]


def reconcile_result(**overrides: Any) -> ReconcileResult:
    base: dict[str, Any] = {
        "fetched_at": RECONCILED_AT,
        "n_listed_in_window": 5,
        "unmatched_remote_run_ids": [],
        "unreconciled_local_seqs": [8],
        "error": None,
    }
    base.update(overrides)
    return ReconcileResult(**base)


def build_golden_receipt(**overrides: Any) -> Receipt:
    kwargs: dict[str, Any] = {
        "session_id": SESSION,
        "query": query(),
        "runs": ledger_rows(),
        "reconciliation": reconcile_result(),
        "llm": llm_usage(),
        "mentions": mention_counts(),
        "audit": audit(),
        "abstentions": abstentions(),
        "what_could_not_be_checked": [
            "youtube_comment: items lacking a timestamp, excluded from WoW and events",
            "cluster key fallback: reddit 2",
        ],
        "started_at": T0,
        "finished_at": FINISHED,
        "sonar_rev": SONAR_REV,
    }
    kwargs.update(overrides)
    return build_receipt(**kwargs)


def reconciled_rows() -> list[RunRecord]:
    """The golden rows after ``GET /v1/runs`` priced the last run."""
    out: list[RunRecord] = []
    for row in ledger_rows():
        if row.local_seq == 8:
            row = RunRecord.model_validate(
                {
                    **row.model_dump(),
                    "cost_usd": 0.016875,
                    "billed_units": 25,
                    "cost_source": "/v1/runs",
                }
            )
        out.append(row)
    return out


def build_reconciled_receipt(**overrides: Any) -> Receipt:
    kwargs: dict[str, Any] = {
        "runs": reconciled_rows(),
        "reconciliation": reconcile_result(n_listed_in_window=6, unreconciled_local_seqs=[]),
    }
    kwargs.update(overrides)
    return build_golden_receipt(**kwargs)


# --------------------------------------------------------------------------- golden


def test_golden_receipt_matches_byte_for_byte() -> None:
    receipt = build_golden_receipt()
    assert GOLDEN.is_file(), f"missing golden {GOLDEN}"
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == receipt.model_dump(mode="json")
    assert receipt_json(receipt) == GOLDEN.read_text(encoding="utf-8")


def test_golden_round_trips_and_digest_is_self_consistent() -> None:
    stored = load_receipt(GOLDEN)
    assert stored.content_digest == stored.compute_content_digest()
    assert re.fullmatch(r"[0-9a-f]{64}", stored.content_digest)
    assert stored.schema_rev == SCHEMA_REV
    assert stored.verdict == "PARTIAL"
    assert stored.verdict == stored.derived_verdict


def test_totals_are_hand_summed() -> None:
    totals = build_golden_receipt().totals
    # /v1/runs rows: seq1 0.248 + seq2 0.03375 + seq3 0.02 + seq6 0.0 + seq7 0.0123.
    # seq4 and seq5 are local ($0 by construction); seq8 is unreconciled and adds nothing.
    assert math.isclose(totals.monid_usd, 0.248 + 0.03375 + 0.02 + 0.0 + 0.0123)
    assert math.isclose(totals.monid_usd, 0.31405)
    assert totals.monid_runs == 8
    assert totals.monid_runs_billed == 4  # seq1, seq2, seq3, seq7
    assert totals.monid_runs_zero_results == 3  # seq3, seq5, seq6
    assert totals.monid_runs_failed == 2  # seq5 LOCAL_REJECTED_402, seq6 FAILED
    assert math.isclose(totals.elevenlabs_usd, 0.0123)
    assert math.isclose(totals.llm_usd, 0.0021 + 0.0026 + 0.00004 + 0.00012 + 0.0005)
    assert math.isclose(totals.llm_usd, 0.00536)
    assert totals.llm_tokens == 3000 + 400 + 2000 + 300 + 500 == 6200
    assert totals.llm_calls == {
        "classify": 3,
        "tiebreak": 1,
        "embed": 1,
        "name_topic": 1,
        "narrate": 1,
        "ask": 0,
    }
    assert math.isclose(totals.total_usd, 0.31405 + 0.00536)
    assert math.isclose(totals.total_usd, 0.31941)


def test_comparison_against_the_incumbent_price() -> None:
    receipt = build_golden_receipt()
    assert receipt.incumbent.name == BRAND24_TEAM.name
    assert receipt.incumbent.price_usd_month == BRAND24_TEAM.price_usd_month
    assert receipt.incumbent.url == BRAND24_TEAM.url
    assert receipt.incumbent.checked_at == BRAND24_TEAM.checked_at
    assert receipt.incumbent.mentions_quota == BRAND24_TEAM.mentions_quota
    cmp = receipt.comparison
    assert cmp.briefs_per_month_assumed == config.BRIEFS_PER_MONTH_ASSUMED
    equiv = 0.31941 * config.BRIEFS_PER_MONTH_ASSUMED
    assert math.isclose(cmp.sonar_usd_month_equiv, equiv)
    assert cmp.ratio is not None
    assert math.isclose(cmp.ratio, BRAND24_TEAM.price_usd_month / equiv)
    assert cmp.mentions_this_brief == 110


def test_zero_result_run_is_present_and_billed() -> None:
    receipt = build_golden_receipt()
    zero = [r for r in receipt.runs if r.n_results == 0]
    assert [r.local_seq for r in zero] == [3, 5, 6]
    billed_empty = receipt.runs[2]
    assert billed_empty.run_id == "01RUN3"
    assert billed_empty.n_results == 0
    assert billed_empty.cost_usd == 0.02
    assert receipt.totals.monid_runs_zero_results == 3
    assert receipt.totals.total_usd > config.H4_MIN_TOTAL_USD_EXCLUSIVE


def test_unreconciled_run_contributes_zero_and_is_listed() -> None:
    receipt = build_golden_receipt()
    row = receipt.runs[7]
    assert row.local_seq == 8 and row.cost_source == "unreconciled" and row.cost_usd is None
    assert receipt.reconciliation.unreconciled_local_seqs == [8]
    assert receipt.verdict == "PARTIAL"
    without = build_golden_receipt(runs=[r for r in ledger_rows() if r.local_seq != 8])
    assert math.isclose(without.totals.monid_usd, receipt.totals.monid_usd)
    assert without.totals.monid_runs == 7


def test_local_rows_follow_d013_n6() -> None:
    receipt = build_golden_receipt()
    sync = receipt.runs[3]
    rejected = receipt.runs[4]
    assert sync.run_id is None and sync.cost_source == "local" and sync.status == "COMPLETED"
    assert rejected.run_id is None and rejected.status == "LOCAL_REJECTED_402"
    assert receipt.totals.monid_runs_failed == 2
    assert 4 not in receipt.reconciliation.unreconciled_local_seqs
    assert 5 not in receipt.reconciliation.unreconciled_local_seqs


def test_runs_are_ordered_by_local_seq_and_all_kept() -> None:
    receipt = build_golden_receipt()
    assert [r.local_seq for r in receipt.runs] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert any(r.run_id is None for r in receipt.runs)


def test_what_could_not_be_checked_leads_with_x_and_has_no_duplicates() -> None:
    receipt = build_golden_receipt(
        what_could_not_be_checked=[X_NOT_CHECKED, "cluster key fallback: reddit 2", X_NOT_CHECKED]
    )
    assert receipt.what_could_not_be_checked == [X_NOT_CHECKED, "cluster key fallback: reddit 2"]


# --------------------------------------------------------------------------- verdict transitions


def test_verdict_partial_to_reconciled_to_replay() -> None:
    partial = build_golden_receipt()
    assert partial.verdict == "PARTIAL"
    reconciled = build_reconciled_receipt()
    assert reconciled.verdict == "RECONCILED"
    assert reconciled.reconciliation.unreconciled_local_seqs == []
    assert math.isclose(reconciled.totals.monid_usd, 0.31405 + 0.016875)
    replay = build_reconciled_receipt(replay=True)
    assert replay.verdict == "REPLAY"
    assert replay.replay is True


def test_verdict_partial_when_a_remote_run_has_no_ledger_row() -> None:
    receipt = build_reconciled_receipt(
        reconciliation=reconcile_result(
            n_listed_in_window=7, unmatched_remote_run_ids=["01STRAY"], unreconciled_local_seqs=[]
        )
    )
    assert receipt.verdict == "PARTIAL"
    assert receipt.reconciliation.unmatched_remote_run_ids == ["01STRAY"]


def test_verdict_partial_when_listing_failed() -> None:
    receipt = build_golden_receipt(
        reconciliation=reconcile_result(fetched_at=None, n_listed_in_window=0, error="HTTP 500")
    )
    assert receipt.verdict == "PARTIAL"
    assert receipt.timestamps.reconciled_at is None
    assert receipt.reconciliation.unreconciled_local_seqs == [8]


def test_reconciliation_model_is_accepted_as_input() -> None:
    rec = Reconciliation(
        fetched_at=RECONCILED_AT,
        n_listed_in_window=6,
        unmatched_remote_run_ids=[],
        unreconciled_local_seqs=[],
    )
    receipt = build_golden_receipt(runs=reconciled_rows(), reconciliation=rec)
    assert receipt.verdict == "RECONCILED"


def test_local_rows_never_block_reconciled() -> None:
    receipt = build_reconciled_receipt()
    assert any(r.cost_source == "local" for r in receipt.runs)
    assert receipt.verdict == "RECONCILED"


# --------------------------------------------------------------------------- verify


def test_verify_exits_nonzero_unless_reconciled(tmp_path: Path) -> None:
    partial_path = write_receipt(build_golden_receipt(), tmp_path / "partial" / "receipt.json")
    result = verify_receipt_file(partial_path)
    assert result.exit_code == VERIFY_NOT_RECONCILED
    assert not result.ok
    assert result.derived_verdict == "PARTIAL"
    assert any("unreconciled local_seq: 8" in p for p in result.problems)

    ok_path = write_receipt(build_reconciled_receipt(), tmp_path / "ok" / "receipt.json")
    ok = verify_receipt_file(ok_path)
    assert ok.exit_code == VERIFY_OK == 0
    assert ok.ok and ok.problems == ()

    replay_path = write_receipt(
        build_reconciled_receipt(replay=True), tmp_path / "replay" / "receipt.json"
    )
    replay = verify_receipt_file(replay_path)
    assert replay.exit_code == VERIFY_NOT_RECONCILED
    assert any("replay" in p.lower() for p in replay.problems)


def test_verify_rejects_a_tampered_receipt(tmp_path: Path) -> None:
    receipt = build_reconciled_receipt()
    payload = receipt.model_dump(mode="json")
    payload["totals"]["monid_usd"] = 0.0
    payload["totals"]["total_usd"] = payload["totals"]["llm_usd"]
    payload["comparison"]["sonar_usd_month_equiv"] = (
        payload["totals"]["total_usd"] * config.BRIEFS_PER_MONTH_ASSUMED
    )
    payload["comparison"]["ratio"] = (
        BRAND24_TEAM.price_usd_month / payload["comparison"]["sonar_usd_month_equiv"]
    )
    for row in payload["runs"]:
        if row["cost_source"] == "/v1/runs":
            row["cost_usd"] = 0.0
    payload["totals"]["monid_runs_billed"] = 0
    payload["totals"]["elevenlabs_usd"] = 0.0
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_receipt_file(path)
    assert result.exit_code == VERIFY_INVALID
    assert result.digest_matches is False

    forged_verdict = receipt.model_copy(update={"verdict": "PARTIAL"}).with_content_digest()
    result = verify_receipt(forged_verdict)
    assert result.exit_code == VERIFY_INVALID
    assert any("stored verdict PARTIAL" in p for p in result.problems)


def test_verify_unreadable_or_invalid_file_exits_2(tmp_path: Path) -> None:
    assert verify_receipt_file(tmp_path / "missing.json").exit_code == VERIFY_INVALID
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert verify_receipt_file(bad).exit_code == VERIFY_INVALID


def sonar_verify(path: Path) -> int:
    """What ``sonar verify <path>`` does: print the problems, return the exit status."""
    result = verify_receipt_file(path)
    return result.exit_code


def test_sonar_verify_style_entry_point(tmp_path: Path) -> None:
    assert sonar_verify(write_receipt(build_golden_receipt(), tmp_path / "a.json")) != 0
    assert sonar_verify(write_receipt(build_reconciled_receipt(), tmp_path / "b.json")) == 0


# --------------------------------------------------------------------------- inputs from the seam


def test_llm_usage_records_fake_backend_calls() -> None:
    backend = FakeBackend()
    totals = LlmUsageTotals()
    embed = backend.embed(["Nubank subiu o limite", "Inter caiu"], config.LLM.embedding_model)
    totals.record("embed", embed.usage)
    assert totals.calls["embed"] == 1
    assert totals.tokens == embed.usage.tokens == 6  # whitespace words in the fake
    assert totals.usd == pytest.approx(embed.usage.cost_usd)
    assert totals.usd > 0.0
    other = LlmUsageTotals()
    other.add("ask", tokens=10, cost_usd=0.001)
    totals.merge(other)
    assert totals.calls["ask"] == 1 and totals.tokens == 16
    with pytest.raises(ValueError):
        totals.add("classify", tokens=-1, cost_usd=0.0)


def test_comparison_ratio_is_null_when_nothing_was_spent() -> None:
    free = [r for r in ledger_rows() if r.local_seq in (4, 5)]
    receipt = build_golden_receipt(
        runs=free,
        llm=LlmUsageTotals(),
        reconciliation=reconcile_result(n_listed_in_window=0, unreconciled_local_seqs=[]),
    )
    assert receipt.totals.total_usd == 0.0
    assert receipt.comparison.sonar_usd_month_equiv == 0.0
    assert receipt.comparison.ratio is None
    assert receipt.verdict == "RECONCILED"


def test_resolve_sonar_rev_reads_git_head(tmp_path: Path) -> None:
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("82d0ab5f" + "0" * 32 + "\n", encoding="utf-8")
    assert resolve_sonar_rev(tmp_path) == f"{__version__}+82d0ab5"
    (git / "refs" / "heads" / "main").unlink()
    (git / "packed-refs").write_text(
        "# pack-refs\n" + "abc1234" + "f" * 33 + " refs/heads/main\n", encoding="utf-8"
    )
    assert resolve_sonar_rev(tmp_path) == f"{__version__}+abc1234"
    assert resolve_sonar_rev(tmp_path / "nowhere") == f"{__version__}+nogit"
    assert re.fullmatch(rf"{re.escape(__version__)}\+([0-9a-f]{{7}}|nogit)", resolve_sonar_rev())


# --------------------------------------------------------------------------- mentions and audit


def mention(brand: str, key: str, **overrides: Any) -> Mention:
    mid = mention_id_for("reddit", key)
    base: dict[str, Any] = {
        "mention_id": mid,
        "brand": brand,
        "source": "reddit",
        "run_id": "01RUN1",
        "native_id": key,
        "url": f"https://reddit.com/r/x/comments/{key}",
        "author_hash": None,
        "text": f"{brand} post {key}",
        "lang": "pt",
        "published_at": T0 - timedelta(days=1),
        "engagement": {"upvotes": 1},
        "rating": None,
        "cluster_key": key,
        "matched_terms": [brand.lower()],
        "raw_ref": "1#0",
    }
    base.update(overrides)
    return Mention.model_validate(base)


def label(mid: str, **overrides: Any) -> Label:
    base: dict[str, Any] = {
        "mention_id": mid,
        "label": "positive",
        "about_brand": True,
        "confidence": 0.9,
        "rationale": "praises the card",
        "topic_id": None,
        "signals": {
            "classifier": {
                "model": config.LLM.classifier_model,
                "label": "positive",
                "confidence": 0.9,
                "status": "ok",
            },
            "tiebreak": None,
            "deterministic": {"kind": "lexicon", "label": "positive"},
            "overflow": False,
        },
        "corroboration": "confirmed",
        "decided_by": "classifier",
        "prompt_rev": config.PROMPT_REV,
        "status": "ok",
        "usage": {"tokens": 100, "cost_usd": 0.0001},
    }
    base.update(overrides)
    return Label.model_validate(base)


def test_count_mentions_carries_every_exclusion_key() -> None:
    rows = [mention("Nubank", f"p{i}") for i in range(6)]
    rows.append(mention("Inter", "p0", text="Inter and Nubank", matched_terms=["inter"]))
    labels: dict[tuple[str, str], Label] = {
        (rows[0].mention_id, "Nubank"): label(rows[0].mention_id),
        (rows[1].mention_id, "Nubank"): label(
            rows[1].mention_id, about_brand=False, corroboration="irrelevant"
        ),
        (rows[2].mention_id, "Nubank"): label(
            rows[2].mention_id,
            label="irrelevant",
            corroboration="irrelevant",
            signals={
                "classifier": {
                    "model": config.LLM.classifier_model,
                    "label": "irrelevant",
                    "confidence": 0.9,
                    "status": "ok",
                },
                "tiebreak": None,
                "deterministic": {"kind": "none", "label": None},
                "overflow": False,
            },
        ),
        (rows[3].mention_id, "Nubank"): label(rows[3].mention_id, status="refused"),
        (rows[4].mention_id, "Nubank"): label(
            rows[4].mention_id, status="cached", usage={"tokens": 0, "cost_usd": 0.0}
        ),
        (rows[6].mention_id, "Inter"): label(rows[6].mention_id),
    }
    counts = count_mentions(
        fetched=12, kept=rows, labels=labels, dedup_dropped={"dedup_native_id": 4, "dedup_url": 1}
    )
    assert counts.fetched == 12
    assert counts.deduped == 7
    assert (
        counts.labelled == 5
    )  # rows 0, 1, 2, 4 and the Inter row; row 3 refused, row 5 unlabelled
    assert counts.excluded_with_reason == {
        "not_about_brand": 1,
        "irrelevant_label": 1,
        "refused": 1,
        "unparseable": 0,
        "error": 0,
        "dedup_native_id": 4,
        "dedup_url": 1,
        "dedup_text": 0,
    }
    assert counts.by_source == {"reddit": 7}
    assert counts.by_brand == {"Nubank": 6, "Inter": 1}
    with pytest.raises(ValueError, match="not an excluded_with_reason key"):
        count_mentions(fetched=0, kept=[], labels={}, dedup_dropped={"dedup_other": 1})
    # Row 5 has no Label: in ``deduped`` but neither labelled nor excluded.
    unlabelled = count_unlabelled(rows, labels)
    assert unlabelled == 1
    kept_side = counts.labelled + sum(
        counts.excluded_with_reason[k] for k in ("refused", "unparseable", "error")
    )
    assert counts.deduped == kept_side + unlabelled


def test_unlabelled_rows_are_named_in_what_could_not_be_checked() -> None:
    rows = [mention("Nubank", f"p{i}") for i in range(3)]
    labels = {(rows[0].mention_id, "Nubank"): label(rows[0].mention_id)}
    assert count_unlabelled(rows, labels) == 2
    assert count_unlabelled(rows, {}) == 3
    assert count_unlabelled([], {}) == 0
    note = unlabelled_note(2, "402 breaker halted the labeler")
    assert note == "labelling: 2 deduped rows never labelled (402 breaker halted the labeler)"
    receipt = build_golden_receipt(what_could_not_be_checked=[note])
    assert receipt.what_could_not_be_checked == [X_NOT_CHECKED, note]
    with pytest.raises(ValueError, match="non-zero"):
        unlabelled_note(0, "402 breaker halted the labeler")
    with pytest.raises(ValueError, match="reason"):
        unlabelled_note(2, "  ")


def test_build_audit_counts_ok_tiebreaks_in_the_sample() -> None:
    def tiebroken(mid: str, tiebreak_label: str, status: str = "ok", **overrides: Any) -> Label:
        return label(
            mid,
            signals={
                "classifier": {
                    "model": config.LLM.classifier_model,
                    "label": "positive",
                    "confidence": 0.5,
                    "status": "ok",
                },
                "tiebreak": {
                    "model": config.LLM.tiebreak_model,
                    "label": tiebreak_label,
                    "confidence": 0.8,
                    "status": status,
                },
                "deterministic": {"kind": "none", "label": None},
                "overflow": False,
            },
            corroboration="model_only"
            if status != "ok"
            else overrides.pop("corroboration", "confirmed"),
            **overrides,
        )

    a, b, c, d = (mention_id_for("reddit", k) for k in ("a", "b", "c", "d"))
    rows = [
        ("Nubank", tiebroken(a, "positive")),  # sample, agrees
        (
            "Nubank",
            tiebroken(
                b, "negative", label="negative", corroboration="contested", decided_by="tiebreak"
            ),
        ),
        ("Nubank", tiebroken(c, "positive", status="error")),  # sample, failed call: not counted
        (
            "Nubank",
            label(
                d,
                signals={
                    "classifier": {
                        "model": config.LLM.classifier_model,
                        "label": "positive",
                        "confidence": 0.5,
                        "status": "ok",
                    },
                    "tiebreak": None,
                    "deterministic": {"kind": "none", "label": None},
                    "overflow": True,
                },
                corroboration="model_only",
            ),
        ),
    ]
    result = build_audit(
        [(lab.mention_id, brand, lab) for brand, lab in rows],
        audit_sample=[(a, "Nubank"), (b, "Nubank"), (c, "Nubank")],
    )
    assert result == Audit(
        n_sample=2, n_agree=1, agreement=0.5, tiebreak_calls=3, tiebreak_overflow=1
    )
    empty = build_audit([], audit_sample=[])
    assert empty.agreement is None and empty.n_sample == 0


# --------------------------------------------------------------------------- digest


def window() -> Window:
    return Window(
        current=DateRange(start=T0 - timedelta(days=7), end=T0),
        previous=DateRange(start=T0 - timedelta(days=14), end=T0 - timedelta(days=7)),
    )


def abstained_stats(
    brand: str, n: int
) -> tuple[SovEntry, SentimentEntry, BySourceEntry, Abstention]:
    wow_share = WowShare(delta=None, ci95=None, verdict="ABSTAIN", p_raw=None, p_holm=None)
    wow_net = WowNet(
        delta=None, ci95=None, ci95_confirmed_only=None, verdict="ABSTAIN", p_raw=None, p_holm=None
    )
    sov = SovEntry(
        brand=brand,
        n=n,
        n_clusters=min(n, 4),
        share=None,
        ci95=None,
        basis_sources=[],
        wow=wow_share,
    )
    sent = SentimentEntry(
        brand=brand,
        n=n,
        n_confirmed=0,
        pos=0,
        neg=0,
        neu=0,
        net=None,
        ci95=None,
        ci95_iid=None,
        design_effect=None,
        wow=wow_net,
    )
    by_source = BySourceEntry(
        brand=brand,
        source="reddit",
        n=n,
        n_clusters=min(n, 4),
        pos=0,
        neg=0,
        neu=0,
        net=None,
        ci95=None,
        ci95_iid=None,
        design_effect=None,
        wow_scope=True,
    )
    row = Abstention(
        scope="brand",
        brand=brand,
        source=None,
        reason="below_minimum",
        detail=f"n={n} < {config.MIN_MENTIONS_PER_WEEK} in the previous period",
    )
    return sov, sent, by_source, row


def digest_inputs() -> tuple[list[Mention], dict[tuple[str, str], Label]]:
    rows = [
        mention("Nubank", "low", engagement={"upvotes": 2, "comments": 1}),
        mention("Nubank", "high", engagement={"upvotes": 40, "comments": 9}),
        mention(
            "Nubank", "tie_older", engagement={"upvotes": 10}, published_at=T0 - timedelta(days=3)
        ),
        mention(
            "Nubank", "tie_newer", engagement={"upvotes": 10}, published_at=T0 - timedelta(days=1)
        ),
        mention("Nubank", "tie_null", engagement={"upvotes": 10}, published_at=None),
        mention("Nubank", "none", engagement={}),
        mention("Nubank", "skip_irrelevant", engagement={"upvotes": 999}),
        mention("Nubank", "skip_unlabelled", engagement={"upvotes": 998}),
        mention("Inter", "inter1", engagement={"upvotes": 3}, text="Inter " + "x" * 300),
    ]
    labels: dict[tuple[str, str], Label] = {
        (r.mention_id, r.brand): label(r.mention_id)
        for r in rows
        if r.native_id != "skip_unlabelled"
    }
    skip = mention_id_for("reddit", "skip_irrelevant")
    labels[(skip, "Nubank")] = label(skip, about_brand=False, corroboration="irrelevant")
    return rows, labels


def build_test_digest(receipt: Receipt | None = None) -> Any:
    receipt = receipt or build_golden_receipt()
    rows, labels = digest_inputs()
    nubank = abstained_stats("Nubank", 8)
    inter = abstained_stats("Inter", 1)
    return build_digest(
        query=query(),
        window=window(),
        share_of_voice=[nubank[0], inter[0]],
        sentiment=[nubank[1], inter[1]],
        by_source=[nubank[2], inter[2]],
        topics=[],
        events=[],
        mentions=rows,
        labels=labels,
        abstentions=[nubank[3], inter[3], receipt.abstentions[0]],
        coverage_gaps=[],
        receipt=receipt,
    )


def test_top_mentions_ordered_by_engagement_then_recency_then_id() -> None:
    digest = build_test_digest()
    nubank = [t for t in digest.top_mentions if t.brand == "Nubank"]
    keys = [t.mention_id for t in nubank]
    ids = {
        k: mention_id_for("reddit", k)
        for k in ("high", "tie_newer", "tie_older", "tie_null", "low", "none")
    }
    assert keys == [
        ids["high"],
        ids["tie_newer"],
        ids["tie_older"],
        ids["tie_null"],
        ids["low"],
        ids["none"],
    ]
    assert [t.engagement_score for t in nubank] == [49, 10, 10, 10, 3, 0]
    assert mention_id_for("reddit", "skip_irrelevant") not in keys
    assert mention_id_for("reddit", "skip_unlabelled") not in keys
    inter = [t for t in digest.top_mentions if t.brand == "Inter"]
    assert len(inter) == 1 and len(inter[0].quote) == config.QUOTE_MAX_CHARS
    assert digest.top_mentions[:6] == nubank  # brand first, then competitors


def test_top_mentions_capped_per_brand() -> None:
    rows = [mention("Nubank", f"m{i:02d}", engagement={"upvotes": i}) for i in range(15)]
    labels = {(r.mention_id, "Nubank"): label(r.mention_id) for r in rows}
    top = rank_top_mentions(rows, labels, brands=["Nubank"])
    assert len(top) == config.TOP_MENTIONS_PER_BRAND == 10
    assert [t.engagement_score for t in top] == list(range(14, 4, -1))


def test_digest_quotes_cost_from_receipt_and_adds_x_gap() -> None:
    receipt = build_golden_receipt()
    digest = build_test_digest(receipt)
    assert digest.cost.verdict == receipt.verdict == "PARTIAL"
    assert digest.cost.totals == receipt.totals
    assert digest.coverage_gaps[0] == X_COVERAGE_GAP
    # Receipt abstentions are merged once; the stats rows come after them.
    assert digest.abstentions.count(receipt.abstentions[0]) == 1
    assert all(a in digest.abstentions for a in receipt.abstentions)
    assert digest.narration.text is None and digest.narration.chars == 0
    custom_gap = CoverageGap(source="x", reason="unavailable", note="custom")
    digest2 = build_digest(
        query=query(),
        window=window(),
        share_of_voice=digest.share_of_voice,
        sentiment=digest.sentiment,
        by_source=digest.by_source,
        topics=[],
        events=[],
        mentions=[],
        labels={},
        abstentions=digest.abstentions,
        coverage_gaps=[custom_gap],
        receipt=receipt,
    )
    assert digest2.coverage_gaps == [custom_gap]


def test_requote_cost_changes_only_cost() -> None:
    before = build_golden_receipt()
    after = build_reconciled_receipt()
    assert after.totals != before.totals and after.verdict != before.verdict
    digest = build_test_digest(before)
    requoted = requote_cost(digest, after)
    assert requoted.cost.verdict == after.verdict == "RECONCILED"
    assert requoted.cost.totals == after.totals
    assert digest.cost.totals == before.totals  # the input is not mutated
    dumped, redumped = digest.model_dump(mode="json"), requoted.model_dump(mode="json")
    assert {k for k in dumped if dumped[k] != redumped[k]} == {"cost"}
    assert requote_cost(requoted, after) == requoted


def test_stats_file_is_the_digest_numbers_and_files_are_written(tmp_path: Path) -> None:
    digest = build_test_digest()
    stats = stats_file_for(digest)
    assert isinstance(stats, StatsFile)
    dumped = digest.model_dump(mode="json")
    assert stats.model_dump(mode="json") == {
        k: dumped[k] for k in ("share_of_voice", "sentiment", "by_source", "events", "window")
    }
    written = write_digest_files(digest, tmp_path / "out")
    assert sorted(written) == ["digest.json", "stats.json", "topics.json"]
    assert json.loads(written["stats.json"].read_text(encoding="utf-8")) == stats.model_dump(
        mode="json"
    )
    assert json.loads(written["topics.json"].read_text(encoding="utf-8")) == []
    assert json.loads(written["digest.json"].read_text(encoding="utf-8")) == dumped


# --------------------------------------------------------------------------- markdown


def test_receipt_markdown_prints_zero_result_and_zero_cost_rows() -> None:
    receipt = build_golden_receipt()
    text = markdown.render_receipt(receipt)
    lines = {line for line in text.splitlines() if line.startswith("| ")}
    assert any(
        line.startswith("| 3 | 01RUN3 |") and "| 0 | $0.2480 | $0.0200 | /v1/runs |" in line
        for line in lines
    )
    assert any(
        line.startswith("| 4 | — | tinyfish /search |")
        and "| 3 | $0.0000 | $0.0000 | local |" in line
        for line in lines
    )
    assert any(
        line.startswith("| 5 | — |") and "LOCAL_REJECTED_402 | 0 |" in line for line in lines
    )
    assert any(
        line.startswith("| 6 | 01RUN6 |")
        and "| FAILED | 0 | $0.0225 | $0.0000 | /v1/runs |" in line
        for line in lines
    )
    assert any(
        line.startswith("| 8 | 01RUN8 |") and "| unreconciled | unreconciled |" in line
        for line in lines
    )
    assert sum(1 for line in lines if re.match(r"\| [1-8] \| ", line)) == 8
    assert markdown.PARTIAL_BANNER in text
    assert "| Price | $349 per month | $0.3194 this brief |" in text
    assert "| **Total** | **$0.3194** |" in text
    assert "| Monid runs with zero results | 3 |" in text
    assert f"- {X_NOT_CHECKED}" in text
    assert receipt.content_digest in text


def test_receipt_markdown_banners_follow_the_verdict() -> None:
    assert markdown.RECONCILED_BANNER in markdown.render_receipt(build_reconciled_receipt())
    assert markdown.REPLAY_BANNER in markdown.render_receipt(build_reconciled_receipt(replay=True))


def test_digest_markdown_renders_every_section() -> None:
    digest = build_test_digest()
    text = markdown.render_digest(digest)
    for heading in (
        "## Share of voice",
        "## Sentiment",
        "## By source",
        "## Topics",
        "## Events",
        "## Top mentions",
        "## Abstentions",
        "## Coverage gaps",
        "## Narration",
    ):
        assert heading in text
    assert "| Nubank | 8 | 4 | — | — | — | — | ABSTAIN | — |" in text
    assert "| x | unavailable |" in text
    assert "Cost verdict **PARTIAL**, total $0.3194" in text
    assert "No narration for this run." in text


def test_receipt_markdown_billed_cells_sum_to_the_monid_line() -> None:
    receipt = build_golden_receipt()
    text = markdown.render_receipt(receipt)
    billed_cells: list[Decimal] = []
    monid_line: str | None = None
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if re.fullmatch(r"[1-8]", cells[0]):
            cell = cells[8]
            if cell.startswith("$"):
                billed_cells.append(Decimal(cell[1:]))
            else:
                assert cell == markdown.UNRECONCILED_CELL
        elif cells[0] == "Monid billed":
            monid_line = cells[1]
    assert len(billed_cells) == 7  # seq 8 is unreconciled
    assert monid_line == "$0.3141"
    assert f"${sum(billed_cells)}" == monid_line
    # The double of 0.31405 is below the half; the ledger's decimal is not.
    assert f"${receipt.totals.monid_usd:.4f}" == "$0.3140"


def test_money_cells() -> None:
    assert markdown.usd(0.0) == "$0.0000"
    assert markdown.usd(None) == "unreconciled"
    assert markdown.usd(0.31941) == "$0.3194"
    assert markdown.usd(0.03375) == "$0.0338"
    assert markdown.usd(0.31405) == "$0.3141"
    assert markdown.usd(0.00005) == "$0.0001"
    assert markdown.usd(1.0) == "$1.0000"
    assert markdown.usd(1e-07) == "$0.0000"
    assert markdown.usd(349) == "$349.0000"
    assert markdown.ratio_cell(None) == "—"
    assert markdown.ratio_cell(273.16) == "273.2×"
    assert markdown.text_cell("a|b\nc") == "a\\|b c"
