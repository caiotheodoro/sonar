"""Round-trips and rule checks for every CONTRACTS record in `sonar.models`."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from sonar import config
from sonar import models as m

T0 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
MID = m.mention_id_for("reddit", "abc123")
MID2 = m.mention_id_for("news", "https://example.com/story")
MID3 = m.mention_id_for("youtube", "dQw4w9WgXcQ")
AUTHOR = m.author_hash_for("tiktok", "@someone")
SESSION = "20260902T120000Z-nubank-0a1b2c"


# --------------------------------------------------------------------------- builders


def query(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "brand": "Nubank",
        "brand_aliases": ["Nu"],
        "brand_hint": "Brazilian digital bank",
        "competitors": ["Inter", "C6 Bank"],
        "window_days": 14,
        "profile": "full",
    }
    base.update(overrides)
    return base


def mention(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "mention_id": MID,
        "brand": "Nubank",
        "source": "reddit",
        "run_id": "run_01",
        "native_id": "abc123",
        "url": "https://reddit.com/r/x/comments/abc123",
        "author_hash": m.author_hash_for("reddit", "u/someone"),
        "text": "Nubank subiu o limite\n\nMuito bom",
        "lang": "pt",
        "published_at": T0,
        "engagement": {"upvotes": 12, "comments": 3},
        "rating": None,
        "cluster_key": "post_parent_id",
        "matched_terms": ["nubank"],
        "raw_ref": "1#0",
    }
    base.update(overrides)
    return base


def label(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "mention_id": MID,
        "label": "positive",
        "about_brand": True,
        "confidence": 0.91,
        "rationale": "Praises the credit limit increase.",
        "topic_id": "nubank-01",
        "signals": {
            "classifier": {
                "model": "gpt-5.6-luna",
                "label": "positive",
                "confidence": 0.91,
                "status": "ok",
            },
            "tiebreak": None,
            "deterministic": {"kind": "lexicon", "label": "positive"},
            "overflow": False,
        },
        "corroboration": "confirmed",
        "decided_by": "classifier",
        "prompt_rev": "p1",
        "status": "ok",
        "usage": {"tokens": 320, "cost_usd": 0.00021},
    }
    base.update(overrides)
    return base


def run(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "local_seq": 1,
        "run_id": "run_01",
        "provider": "apify",
        "endpoint": "/trudax/reddit-scraper-lite",
        "brand": "Nubank",
        "source": "reddit",
        "input_digest": m.input_digest_for({"searches": ["Nubank"], "maxItems": 40}),
        "submitted_at": T0,
        "completed_at": T0 + timedelta(seconds=40),
        "status": "SUCCEEDED",
        "provider_http_status": 200,
        "n_results": 40,
        "estimate_usd": 0.02,
        "cost_usd": 0.02,
        "billed_units": 40,
        "cost_source": "/v1/runs",
        "attempts": 1,
        "error": None,
    }
    base.update(overrides)
    return base


def topic(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "topic_id": "nubank-01",
        "brand": "Nubank",
        "name": "Credit limit increases",
        "n": 12,
        "n_clusters": 7,
        "share": 0.3,
        "net": 0.5,
        "ci95": [0.1, 0.8],
        "exemplar_mention_ids": [MID, MID2, MID3],
        "method": {"embedding_model": "text-embedding-3-small", "threshold": 0.35},
    }
    base.update(overrides)
    return base


def totals(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "monid_usd": 0.02,
        "monid_runs": 1,
        "monid_runs_billed": 1,
        "monid_runs_zero_results": 0,
        "monid_runs_failed": 0,
        "llm_usd": 0.01,
        "llm_calls": {"classify": 40, "tiebreak": 4},
        "llm_tokens": 12000,
        "elevenlabs_usd": 0.0,
        "total_usd": 0.03,
    }
    base.update(overrides)
    return base


def excluded(**counts: int) -> dict[str, int]:
    """Every one of the eight `excluded_with_reason` keys, zero unless overridden."""
    return {key: counts.get(key, 0) for key in sorted(m.EXCLUSION_REASONS)}


def receipt(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_rev": m.SCHEMA_REV,
        "sonar_rev": "0.1.0+82d0ab5",
        "session_id": SESSION,
        "timestamps": {
            "started_at": T0,
            "finished_at": T0 + timedelta(minutes=5),
            "reconciled_at": T0 + timedelta(minutes=6),
        },
        "replay": False,
        "verdict": "RECONCILED",
        "query": query(),
        "runs": [run()],
        "totals": totals(),
        "reconciliation": {
            "fetched_at": T0 + timedelta(minutes=6),
            "n_listed_in_window": 1,
            "unmatched_remote_run_ids": [],
            "unreconciled_local_seqs": [],
        },
        "incumbent": {
            "url": "https://brand24.com/prices/",
            "checked_at": date(2026, 9, 2),
        },
        "comparison": {
            "sonar_usd_month_equiv": 0.12,
            "ratio": 349 / 0.12,
            "mentions_this_brief": 40,
        },
        "mentions": {
            "fetched": 40,
            "deduped": 38,
            "labelled": 36,
            "excluded_with_reason": excluded(not_about_brand=2),
            "by_source": {"reddit": 38},
            "by_brand": {"Nubank": 38},
        },
        "audit": {
            "n_sample": 4,
            "n_agree": 3,
            "agreement": 0.75,
            "tiebreak_calls": 4,
            "tiebreak_overflow": 0,
        },
        "abstentions": [
            {
                "scope": "source",
                "brand": None,
                "source": "instagram",
                "reason": "empty",
                "detail": "hashtag search returned no items",
            }
        ],
        "what_could_not_be_checked": [
            "X/Twitter: no Monid endpoint",
            "youtube_comment: items lacking a timestamp, excluded from WoW and events",
        ],
        "content_digest": "",
    }
    base.update(overrides)
    return base


def digest(**overrides: Any) -> dict[str, Any]:
    now = T0
    wow_net = {
        "delta": 0.1,
        "ci95": [0.02, 0.2],
        "ci95_confirmed_only": [-0.01, 0.25],
        "verdict": "SUGGESTIVE",
        "p_raw": 0.03,
        "p_holm": 0.06,
    }
    wow_share = {
        "delta": -0.05,
        "ci95": [-0.2, 0.1],
        "verdict": "NO_CHANGE_DETECTED",
        "p_raw": 0.4,
        "p_holm": 0.8,
    }
    base: dict[str, Any] = {
        "brand": "Nubank",
        "competitors": ["Inter"],
        "window": {
            "current": {"start": now - timedelta(days=7), "end": now},
            "previous": {"start": now - timedelta(days=14), "end": now - timedelta(days=7)},
        },
        "share_of_voice": [
            {
                "brand": "Nubank",
                "n": 38,
                "n_clusters": 20,
                "share": 0.6,
                "ci95": [0.5, 0.7],
                "basis_sources": ["reddit", "news"],
                "wow": wow_share,
            }
        ],
        "sentiment": [
            {
                "brand": "Nubank",
                "n": 36,
                "n_confirmed": 30,
                "pos": 20,
                "neg": 6,
                "neu": 10,
                "net": 0.39,
                "ci95": [0.2, 0.55],
                "ci95_iid": [0.25, 0.5],
                "design_effect": 1.96,
                "wow": wow_net,
            }
        ],
        "by_source": [
            {
                "brand": "Nubank",
                "source": "reddit",
                "n": 36,
                "n_clusters": 20,
                "pos": 20,
                "neg": 6,
                "neu": 10,
                "net": 0.39,
                "ci95": [0.2, 0.55],
                "ci95_iid": [0.25, 0.5],
                "design_effect": 1.96,
                "wow_scope": True,
            }
        ],
        "topics": [topic()],
        "events": [
            {
                "brand": "Nubank",
                "date": date(2026, 8, 30),
                "n": 9,
                "n_clusters": 4,
                "baseline_median": 2.0,
                "baseline_mad": 1.0,
                "threshold": 5.0,
                "label": "Credit limit increases",
                "exhibit_url": "https://reddit.com/r/x/comments/abc123",
            }
        ],
        "top_mentions": [
            {
                "mention_id": MID,
                "brand": "Nubank",
                "source": "reddit",
                "url": "https://reddit.com/r/x/comments/abc123",
                "quote": "Nubank subiu o limite",
                "lang": "pt",
                "label": "positive",
                "published_at": T0,
                "engagement_score": 15,
            }
        ],
        "abstentions": [],
        "coverage_gaps": [{"source": "x", "reason": "unavailable", "note": "no Monid endpoint"}],
        "cost": {"verdict": "RECONCILED", "totals": totals()},
        "narration": {
            "text": "Nubank led share of voice this week.",
            "chars": len("Nubank led share of voice this week."),
            "numbers_verified": True,
            "mp3_path": "results/x/brief.mp3",
            "local_seq": 2,
        },
    }
    base.update(overrides)
    return base


def answer(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "session_id": SESSION,
        "brand": "Nubank",
        "question": "What did people say about the credit limit?",
        "answer": "Most mentions praise the limit increase.",
        "citations": [MID],
        "verified_numbers": ["36"],
        "retrieved": [MID, MID2],
        "model": "gpt-5.6-terra",
        "usage": {"tokens": 900, "cost_usd": 0.002},
        "status": "ok",
    }
    base.update(overrides)
    return base


def stats_file(**overrides: Any) -> dict[str, Any]:
    d = digest()
    base: dict[str, Any] = {k: d[k] for k in m.StatsFile.model_fields}
    base.update(overrides)
    return base


BUILDERS: dict[str, Any] = {
    "Query": query,
    "Mention": mention,
    "Label": label,
    "RunRecord": run,
    "Topic": topic,
    "Receipt": receipt,
    "Digest": digest,
    "StatsFile": stats_file,
    "Answer": answer,
}


# --------------------------------------------------------------------------- round trips


@pytest.mark.parametrize("name", sorted(m.RECORDS))
def test_every_contract_record_round_trips_through_json(name: str) -> None:
    model = m.RECORDS[name]
    original = model.model_validate(BUILDERS[name]())
    text = original.model_dump_json()
    restored = model.model_validate_json(text)
    assert restored == original
    assert json.loads(text) == restored.model_dump(mode="json")


@pytest.mark.parametrize("name", sorted(m.RECORDS))
def test_every_record_is_frozen_and_forbids_extras(name: str) -> None:
    model = m.RECORDS[name]
    record = model.model_validate(BUILDERS[name]())
    with pytest.raises(ValidationError):
        setattr(record, next(iter(model.model_fields)), "changed")
    with pytest.raises(ValidationError, match="extra"):
        model.model_validate({**BUILDERS[name](), "unexpected_field": 1})


def test_records_dict_names_every_contract_record() -> None:
    assert set(m.RECORDS) == {
        "Query",
        "Mention",
        "Label",
        "RunRecord",
        "Topic",
        "Receipt",
        "Digest",
        "StatsFile",
        "Answer",
    }
    assert m.SCHEMA_REV == "1.1.0"


def test_datetimes_serialize_as_utc_second_precision_z() -> None:
    record = m.RunRecord.model_validate(
        run(submitted_at="2026-09-02T09:00:00.250-03:00", completed_at=None)
    )
    dumped = record.model_dump(mode="json")
    assert dumped["submitted_at"] == "2026-09-02T12:00:00Z"
    assert dumped["completed_at"] is None
    with pytest.raises(ValidationError, match="timezone-aware"):
        m.RunRecord.model_validate(run(submitted_at="2026-09-02T09:00:00"))


def test_source_enum_has_exactly_ten_members_and_no_x() -> None:
    assert len(m.SOURCES) == 10
    assert "x" not in m.SOURCES
    with pytest.raises(ValidationError):
        m.Mention.model_validate(mention(source="x"))


# --------------------------------------------------------------------------- Query validators


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"brand": "N"}, "brand must be 2-64"),
        ({"brand": " N "}, "brand must be 2-64"),
        ({"brand": "x" * 65}, "brand must be 2-64"),
        ({"brand": "!!!"}, "punctuation-only"),
        ({"brand_aliases": ["--"]}, "punctuation-only"),
        ({"competitors": ["I"]}, "competitors entry must be 2-64"),
        ({"brand_aliases": ["nubank"]}, "duplicates brand"),
        ({"brand_aliases": ["NU", "nu"]}, "duplicates brand_aliases"),
        ({"competitors": ["Inter", "INTER"]}, "duplicates competitors"),
        ({"competitors": ["Nubank"]}, "duplicates brand"),
        ({"competitors": ["Inter", "C6", "Itau", "Bradesco"]}, "at most 3"),
        ({"profile": "lite", "competitors": ["Inter", "C6 Bank"]}, "at most 1 entries under"),
        ({"profile": "smoke", "competitors": ["Inter"]}, "at most 0 entries under"),
        ({"sources": ["reddit", "x"]}, "non-members"),
        ({"sources": ["reddit", "reddit"]}, "distinct"),
        (
            {"profile": "smoke", "competitors": [], "sources": ["reddit", "news"]},
            "smoke allows only",
        ),
        ({"brand_hint": "h" * 121}, "at most 120"),
        ({"window_days": 0}, "fixed at 14"),
        ({"window_days": 7}, "fixed at 14"),
        ({"window_days": 28}, "fixed at 14"),
    ],
)
def test_query_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.Query.model_validate(query(**overrides))


def test_query_trims_terms_and_keeps_canonical_spelling() -> None:
    q = m.Query.model_validate(query(brand="  Nubank ", competitors=[" Inter "]))
    assert q.brand == "Nubank"
    assert q.competitors == ["Inter"]


def test_query_distinctness_is_case_insensitive_after_normalization() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        m.Query.model_validate(query(brand="Nubank", competitors=["NUBANK"]))
    with pytest.raises(ValidationError, match="duplicates"):
        m.Query.model_validate(query(brand="Café", brand_aliases=["CAFÉ"]))


def test_query_reports_first_failure_in_contract_order() -> None:
    both_bad = query(brand="!!", competitors=["Inter", "C6", "Itau", "Bradesco", "Santander"])
    with pytest.raises(ValidationError, match="punctuation-only"):
        m.Query.model_validate(both_bad)
    too_many_and_bad_source = query(
        competitors=["Inter", "C6", "Itau", "Bradesco"], sources=["reddit", "x"]
    )
    with pytest.raises(ValidationError, match="at most 3"):
        m.Query.model_validate(too_many_and_bad_source)
    lite_over_cap_and_bad_window = query(profile="lite", window_days=7)
    with pytest.raises(ValidationError, match="at most 1"):
        m.Query.model_validate(lite_over_cap_and_bad_window)
    bad_window_and_bad_source = query(window_days=7, sources=["reddit", "x"])
    with pytest.raises(ValidationError, match="fixed at 14"):
        m.Query.model_validate(bad_window_and_bad_source)


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("full", list(m.SOURCES)),
        ("lite", list(m.SOURCES)),
        ("smoke", ["reddit", "google_maps"]),
    ],
)
def test_query_sources_default_to_profile_list(profile: str, expected: list[str]) -> None:
    q = m.Query.model_validate(query(profile=profile, competitors=[]))
    assert q.sources == expected
    assert q.profile == profile


def test_query_window_days_is_fixed_at_14() -> None:
    assert m.WINDOW_DAYS == 14
    assert m.Query.model_validate(query(window_days=14)).window_days == 14
    with pytest.raises(ValidationError, match="fixed at 14"):
        m.Query.model_validate(query(window_days="21"))
    with pytest.raises(ValidationError, match="window_days"):
        m.Query.model_validate(query(window_days=14.5))


def test_query_competitor_cap_is_profile_aware() -> None:
    assert m.Query.model_validate(query(profile="lite", competitors=["Inter"])).profile == "lite"
    assert m.Query.model_validate(query(profile="smoke", competitors=[])).competitors == []
    assert len(m.Query.model_validate(query(competitors=["Inter", "C6", "Itau"])).competitors) == 3
    with pytest.raises(ValidationError, match="at most 1 entries under profile lite"):
        m.Query.model_validate(query(profile="lite", competitors=["Inter", "C6"]))


def test_query_profile_tables_match_config() -> None:
    """models.py mirrors config.PROFILES rather than importing it; keep them equal."""
    for name, profile in config.PROFILES.items():
        assert tuple(m.PROFILE_SOURCES[name]) == tuple(profile.sources)
        assert m.MAX_COMPETITORS_BY_PROFILE[name] == profile.max_competitors
    assert m.WINDOW_DAYS == config.WINDOW_DAYS_DEFAULT
    assert m.TOPIC_DISTANCE_THRESHOLD == config.TOPIC_DISTANCE_THRESHOLD


def test_query_defaults() -> None:
    q = m.Query.model_validate({"brand": "Nubank"})
    assert q.brand_aliases == []
    assert q.brand_hint is None
    assert q.competitors == []
    assert q.window_days == 14
    assert q.profile == "full"
    assert q.sources == list(m.SOURCES)


# --------------------------------------------------------------------------- cluster_key rule


@pytest.mark.parametrize("source", sorted(m.MENTION_ID_CLUSTER_SOURCES))
def test_cluster_key_is_mention_id_for_video_review_and_news_sources(source: str) -> None:
    rating = 4 if source in m.REVIEW_SOURCES else None
    ok = m.Mention.model_validate(
        mention(source=source, rating=rating, cluster_key=MID, native_id=None, url=None)
    )
    assert ok.cluster_key == ok.mention_id
    with pytest.raises(ValidationError, match="cluster_key"):
        m.Mention.model_validate(mention(source=source, rating=rating, cluster_key="other"))


@pytest.mark.parametrize("source", sorted(m.AUTHOR_CLUSTER_SOURCES))
def test_cluster_key_is_author_hash_for_tiktok_and_instagram(source: str) -> None:
    ok = m.Mention.model_validate(mention(source=source, author_hash=AUTHOR, cluster_key=AUTHOR))
    assert ok.cluster_key == AUTHOR
    with pytest.raises(ValidationError, match="cluster_key"):
        m.Mention.model_validate(mention(source=source, author_hash=AUTHOR, cluster_key=MID))
    fallback = m.Mention.model_validate(mention(source=source, author_hash=None, cluster_key=MID))
    assert fallback.cluster_key == fallback.mention_id
    with pytest.raises(ValidationError, match="cluster_key"):
        m.Mention.model_validate(mention(source=source, author_hash=None, cluster_key="anything"))


def test_cluster_key_for_reddit_is_the_post_id_from_the_payload() -> None:
    post = m.Mention.model_validate(mention(source="reddit", cluster_key="abc123"))
    assert post.cluster_key == "abc123"
    comment = m.Mention.model_validate(mention(source="reddit", cluster_key="parent_post"))
    assert comment.cluster_key == "parent_post"
    with pytest.raises(ValidationError):
        m.Mention.model_validate(mention(source="reddit", cluster_key=""))


def test_cluster_key_for_youtube_comment_is_the_video_id() -> None:
    row = m.Mention.model_validate(
        mention(source="youtube_comment", cluster_key="dQw4w9WgXcQ", published_at=None)
    )
    assert row.cluster_key == "dQw4w9WgXcQ"
    assert row.published_at is None


def test_expected_cluster_key_covers_every_source() -> None:
    for source in m.SOURCES:
        expected = m.expected_cluster_key(source, MID, AUTHOR)
        if source in m.MENTION_ID_CLUSTER_SOURCES:
            assert expected == MID
        elif source in m.AUTHOR_CLUSTER_SOURCES:
            assert expected == AUTHOR
        else:
            assert expected is None
    assert m.expected_cluster_key("tiktok", MID, None) == MID


# --------------------------------------------------------------------------- Mention rules


def test_mention_id_rule_matches_contract() -> None:
    expected = hashlib.sha256(b"reddit\nabc123").hexdigest()[:24]
    assert m.mention_id_for("reddit", "abc123") == expected
    assert len(expected) == 24
    assert (
        m.author_hash_for("tiktok", "@someone")
        == (hashlib.sha256(b"tiktok\n@someone").hexdigest()[:16])
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"mention_id": "ABC"}, "pattern"),
        ({"author_hash": "xyz"}, "pattern"),
        ({"text": "   "}, "non-whitespace"),
        ({"engagement": {"stars": 1}}, "not allowed"),
        ({"rating": 5}, "rating must be null"),
        ({"source": "g2", "rating": 6, "cluster_key": MID}, "rating must be 1-5"),
        ({"matched_terms": []}, "at least 1"),
        ({"raw_ref": "1-0"}, "pattern"),
        ({"url": ""}, "null when absent"),
    ],
)
def test_mention_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.Mention.model_validate(mention(**overrides))


def test_review_source_may_carry_rating_or_null() -> None:
    maps = mention(source="google_maps", cluster_key=MID)
    assert m.Mention.model_validate({**maps, "rating": 2}).rating == 2
    assert m.Mention.model_validate({**maps, "rating": None}).rating is None


def test_mention_engagement_allows_negative_reddit_scores() -> None:
    row = m.Mention.model_validate(mention(engagement={"upvotes": -4}))
    assert row.engagement == {"upvotes": -4}


def test_mention_allows_empty_engagement_and_null_optionals() -> None:
    row = m.Mention.model_validate(
        mention(engagement={}, native_id=None, url=None, author_hash=None, published_at=None)
    )
    assert row.engagement == {}
    assert row.model_dump(mode="json")["published_at"] is None
    assert row.engagement_score == 0


def test_mention_run_id_is_nullable_and_raw_ref_carries_local_seq() -> None:
    sync = m.Mention.model_validate(mention(run_id=None, raw_ref="7#3"))
    assert sync.run_id is None
    assert sync.local_seq == 7
    assert sync.model_dump(mode="json")["run_id"] is None
    with pytest.raises(ValidationError, match="null when absent"):
        m.Mention.model_validate(mention(run_id=""))
    with pytest.raises(ValidationError, match="null when absent"):
        m.Mention.model_validate(mention(run_id="  "))


def test_mention_engagement_score_sums_numeric_values() -> None:
    row = m.Mention.model_validate(mention(engagement={"upvotes": 12, "comments": 3}))
    assert row.engagement_score == 15
    assert m.engagement_score_for({"upvotes": -4, "comments": 1}) == -3
    assert m.engagement_score_for({}) == 0


# --------------------------------------------------------------------------- Label rules


def test_label_tiebreak_path_and_cached_usage() -> None:
    tb = {"model": "gpt-5.6-terra", "label": "negative", "confidence": 0.8, "status": "ok"}
    contested = m.Label.model_validate(
        label(
            label="negative",
            signals={**label()["signals"], "tiebreak": tb},
            corroboration="contested",
            decided_by="tiebreak",
        )
    )
    assert contested.decided_by == "tiebreak"
    with pytest.raises(ValidationError, match="requires a tiebreak signal"):
        m.Label.model_validate(label(decided_by="tiebreak"))
    cached = m.Label.model_validate(label(status="cached", usage={"tokens": 0, "cost_usd": 0.0}))
    assert cached.usage.cost_usd == 0.0
    with pytest.raises(ValidationError, match="cached labels"):
        m.Label.model_validate(label(status="cached"))


def test_label_irrelevant_corroboration_rule() -> None:
    with pytest.raises(ValidationError, match="irrelevant"):
        m.Label.model_validate(label(about_brand=False))
    with pytest.raises(ValidationError, match="irrelevant"):
        m.Label.model_validate(label(label="irrelevant"))
    ok = m.Label.model_validate(label(about_brand=False, corroboration="irrelevant"))
    assert ok.corroboration == "irrelevant"


def test_label_overflow_keeps_classifier_label_as_model_only() -> None:
    no_det = {**label()["signals"], "deterministic": {"kind": "none", "label": None}}
    overflow = m.Label.model_validate(
        label(signals={**no_det, "overflow": True}, corroboration="model_only", confidence=0.4)
    )
    assert overflow.signals.overflow is True
    assert overflow.decided_by == "classifier"
    with pytest.raises(ValidationError, match="never confirmed"):
        m.Label.model_validate(label(signals={**label()["signals"], "overflow": True}))
    tb = {"model": "gpt-5.6-terra", "label": "positive", "confidence": 0.8, "status": "ok"}
    with pytest.raises(ValidationError, match="tiebreak is null"):
        m.Label.model_validate(
            label(signals={**no_det, "overflow": True, "tiebreak": tb}, corroboration="model_only")
        )
    with pytest.raises(ValidationError, match="overflow"):
        m.Signals.model_validate({k: v for k, v in label()["signals"].items() if k != "overflow"})
    irrelevant = m.Label.model_validate(
        label(signals={**no_det, "overflow": True}, about_brand=False, corroboration="irrelevant")
    )
    assert irrelevant.corroboration == "irrelevant"


def test_label_rejects_long_rationale_and_bad_signal_shapes() -> None:
    with pytest.raises(ValidationError, match="20 words"):
        m.Label.model_validate(label(rationale=" ".join(["w"] * 21)))
    with pytest.raises(ValidationError, match="kind none"):
        m.DeterministicSignal.model_validate({"kind": "none", "label": "positive"})
    with pytest.raises(ValidationError, match="kind rating"):
        m.DeterministicSignal.model_validate({"kind": "rating", "label": None})
    assert m.DeterministicSignal.model_validate({"kind": "lexicon", "label": None}).label is None
    with pytest.raises(ValidationError):
        m.ModelSignal.model_validate({**label()["signals"]["classifier"], "confidence": 1.5})


# --------------------------------------------------------------------------- RunRecord rules


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "LOCAL_REJECTED_402"}, "run_id null"),
        ({"status": "LOCAL_SOMETHING", "run_id": None}, "local status must be"),
        ({"cost_source": "unreconciled"}, "null until reconciled"),
        ({"cost_source": "/v1/runs", "cost_usd": None}, "requires cost_usd"),
        ({"local_seq": 0}, "greater than or equal to 1"),
        ({"attempts": 0}, "greater than or equal to 1"),
        ({"input_digest": "nothex"}, "pattern"),
        ({"run_id": " "}, "null when absent"),
        ({"error": "x" * 501}, "at most 500"),
        (
            {
                "run_id": None,
                "status": "LOCAL_REJECTED_402",
                "cost_usd": None,
                "cost_source": "unreconciled",
            },
            "cost_source=local",
        ),
        ({"cost_source": "local", "cost_usd": 0.0}, "only for rows with run_id null"),
        (
            {
                "run_id": None,
                "status": "LOCAL_BACKOFF_EXHAUSTED",
                "cost_usd": 0.5,
                "cost_source": "local",
            },
            "carry cost_usd=0.0",
        ),
        (
            {
                "run_id": None,
                "status": "LOCAL_BACKOFF_EXHAUSTED",
                "cost_usd": None,
                "cost_source": "local",
            },
            "carry cost_usd=0.0",
        ),
    ],
)
def test_run_record_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.RunRecord.model_validate(run(**overrides))


def test_run_record_local_statuses() -> None:
    rejected = m.RunRecord.model_validate(
        run(
            run_id=None,
            status="LOCAL_REJECTED_402",
            completed_at=None,
            n_results=None,
            cost_usd=0.0,
            billed_units=None,
            cost_source="local",
            error="insufficient credit",
        )
    )
    assert rejected.is_local_status
    assert rejected.cost_source == "local"
    deadline = m.RunRecord.model_validate(
        run(status="LOCAL_DEADLINE", cost_usd=None, cost_source="unreconciled", n_results=None)
    )
    assert deadline.run_id == "run_01"
    voice = m.RunRecord.model_validate(
        run(provider="elevenlabs", endpoint="/text-to-speech", brand=None, source=None)
    )
    assert voice.source is None
    zero = m.RunRecord.model_validate(run(n_results=0, cost_usd=0.0))
    assert zero.n_results == 0


def test_run_record_sync_endpoint_without_run_id_is_local_by_construction() -> None:
    """OQ-2: a `$0` sync run that returned no id reconciles as local with cost 0."""
    sync = m.RunRecord.model_validate(
        run(
            provider="tinyfish",
            endpoint="/search",
            source="news",
            run_id=None,
            status="SUCCEEDED",
            cost_usd=0.0,
            billed_units=0,
            cost_source="local",
        )
    )
    assert sync.run_id is None
    assert sync.cost_source == "local"
    assert sync.cost_usd == 0.0


def test_input_digest_uses_canonical_json() -> None:
    a = m.input_digest_for({"b": 1, "a": [1, 2]})
    b = m.input_digest_for({"a": [1, 2], "b": 1})
    assert a == b
    assert m.canonical_json({"b": 1, "a": "é"}) == b'{"a":"\xc3\xa9","b":1}'


# --------------------------------------------------------------------------- Topic rules


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"n": 2}, "below method.min_size"),
        ({"n_clusters": 1}, "below method.min_breadth"),
        ({"n": 5, "n_clusters": 6}, "cannot exceed n"),
        ({"name": "one two three four five six seven"}, "6 words"),
        ({"exemplar_mention_ids": [MID, MID2]}, "at least 3"),
        ({"ci95": [0.9, 0.1]}, "exceeds upper"),
        ({"topic_id": "Nubank-1"}, "pattern"),
        ({"method": {"embedding_model": "e", "threshold": 0.3, "min_size": 4}}, "min_size"),
        ({"method": {"embedding_model": "e", "threshold": 0.3, "linkage": "single"}}, "linkage"),
    ],
)
def test_topic_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.Topic.model_validate(topic(**overrides))


def test_topic_method_defaults() -> None:
    t = m.Topic.model_validate(topic())
    assert t.method.linkage == "average"
    assert t.method.min_size == 3
    assert t.method.min_breadth == 2
    assert t.ci95 == (0.1, 0.8)


# --------------------------------------------------------------------------- Receipt verdict rule


def reconciliation(**overrides: Any) -> m.Reconciliation:
    base: dict[str, Any] = {
        "fetched_at": T0,
        "n_listed_in_window": 1,
        "unmatched_remote_run_ids": [],
        "unreconciled_local_seqs": [],
    }
    base.update(overrides)
    return m.Reconciliation.model_validate(base)


def test_verdict_rule_replay_wins() -> None:
    runs = [m.RunRecord.model_validate(run())]
    assert m.derive_verdict(True, runs, reconciliation()) == "REPLAY"
    assert m.derive_verdict(True, [], reconciliation(unmatched_remote_run_ids=["r9"])) == "REPLAY"


def test_verdict_rule_reconciled_requires_every_run_from_listing_and_no_unmatched() -> None:
    reconciled_rows = [
        m.RunRecord.model_validate(run()),
        m.RunRecord.model_validate(
            run(
                local_seq=2,
                run_id=None,
                status="LOCAL_REJECTED_429",
                completed_at=None,
                n_results=None,
                cost_usd=0.0,
                billed_units=None,
                cost_source="local",
                error="rate limited",
            )
        ),
    ]
    assert m.derive_verdict(False, reconciled_rows, reconciliation()) == "RECONCILED"
    only_local = [reconciled_rows[1]]
    assert m.derive_verdict(False, only_local, reconciliation()) == "RECONCILED"
    assert m.derive_verdict(False, [], reconciliation()) == "RECONCILED"
    unmatched = reconciliation(unmatched_remote_run_ids=["run_99"])
    assert m.derive_verdict(False, reconciled_rows, unmatched) == "PARTIAL"


def test_verdict_rule_partial_when_any_run_unreconciled() -> None:
    rows = [
        m.RunRecord.model_validate(run()),
        m.RunRecord.model_validate(
            run(
                local_seq=2,
                run_id="run_02",
                cost_usd=None,
                billed_units=None,
                cost_source="unreconciled",
            )
        ),
    ]
    assert m.derive_verdict(False, rows, reconciliation(unreconciled_local_seqs=[2])) == "PARTIAL"


def test_receipt_round_trips_each_verdict_and_exposes_derived_verdict() -> None:
    reconciled = m.Receipt.model_validate(receipt())
    assert reconciled.verdict == reconciled.derived_verdict == "RECONCILED"

    partial_run = run(
        local_seq=2,
        run_id="run_02",
        cost_usd=None,
        billed_units=None,
        cost_source="unreconciled",
        n_results=None,
        completed_at=None,
    )
    partial = m.Receipt.model_validate(
        receipt(
            verdict="PARTIAL",
            runs=[run(), partial_run],
            totals=totals(monid_runs=2),
            reconciliation={
                "fetched_at": None,
                "n_listed_in_window": 0,
                "unmatched_remote_run_ids": [],
                "unreconciled_local_seqs": [2],
            },
            timestamps={"started_at": T0, "finished_at": T0, "reconciled_at": None},
        )
    )
    assert partial.derived_verdict == "PARTIAL"
    assert m.Receipt.model_validate_json(partial.model_dump_json()) == partial

    replay = m.Receipt.model_validate(receipt(replay=True, verdict="REPLAY"))
    assert replay.derived_verdict == "REPLAY"

    tampered = m.Receipt.model_validate(receipt(verdict="PARTIAL"))
    assert tampered.verdict != tampered.derived_verdict


def test_receipt_content_digest_recomputes_over_canonical_json() -> None:
    card = m.Receipt.model_validate(receipt()).with_content_digest()
    assert len(card.content_digest) == 64
    assert card.compute_content_digest() == card.content_digest
    payload = card.model_dump(mode="json")
    payload["content_digest"] = ""
    expected = hashlib.sha256(m.canonical_json(payload)).hexdigest()
    assert card.content_digest == expected
    reloaded = m.Receipt.model_validate_json(card.model_dump_json())
    assert reloaded.compute_content_digest() == card.content_digest
    edited = card.model_copy(update={"sonar_rev": "0.1.0+deadbee"})
    assert edited.compute_content_digest() != card.content_digest


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"runs": [run(local_seq=2), run(local_seq=1)]}, "strictly increasing"),
        ({"totals": totals(monid_runs=3)}, "equal len"),
        ({"totals": totals(monid_runs_billed=0)}, "cost_usd > 0"),
        ({"totals": totals(monid_runs_zero_results=1)}, "n_results = 0"),
        ({"session_id": "bad"}, "pattern"),
        ({"content_digest": "abc"}, "pattern"),
        ({"incumbent": {"url": "u", "checked_at": "2026-09-02", "price_usd_month": 299}}, "349"),
        (
            {"comparison": {"sonar_usd_month_equiv": 0.0, "ratio": 1.0, "mentions_this_brief": 0}},
            "ratio must be null",
        ),
        (
            {"mentions": {**receipt()["mentions"], "excluded_with_reason": {"other": 1}}},
            "not allowed",
        ),
        (
            {
                "mentions": {
                    **receipt()["mentions"],
                    "excluded_with_reason": {"not_about_brand": 2, "no_matched_terms": 1},
                }
            },
            "not allowed",
        ),
        (
            {"mentions": {**receipt()["mentions"], "excluded_with_reason": {"not_about_brand": 2}}},
            "must carry every key, missing",
        ),
        ({"totals": totals(monid_usd=0.05, total_usd=0.06)}, "monid_usd must sum"),
        ({"totals": totals(total_usd=0.5)}, "monid_usd \\+ llm_usd"),
        (
            {
                "comparison": {
                    "sonar_usd_month_equiv": 0.5,
                    "ratio": 698.0,
                    "mentions_this_brief": 0,
                }
            },
            "briefs_per_month",
        ),
        (
            {"comparison": {"sonar_usd_month_equiv": 0.12, "ratio": 1.0, "mentions_this_brief": 0}},
            "ratio must equal",
        ),
    ],
)
def test_receipt_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.Receipt.model_validate(receipt(**overrides))


def test_receipt_requires_audit_and_counts_local_rows_as_failed() -> None:
    with pytest.raises(ValidationError, match="audit"):
        m.Receipt.model_validate({k: v for k, v in receipt().items() if k != "audit"})
    local_row = run(
        local_seq=2,
        run_id=None,
        status="LOCAL_REJECTED_402",
        completed_at=None,
        n_results=None,
        cost_usd=0.0,
        billed_units=None,
        cost_source="local",
        error="insufficient credit",
    )
    with pytest.raises(ValidationError, match="monid_runs_failed counts every run_id=null"):
        m.Receipt.model_validate(receipt(runs=[run(), local_row], totals=totals(monid_runs=2)))
    card = m.Receipt.model_validate(
        receipt(
            runs=[run(), local_row],
            totals=totals(monid_runs=2, monid_runs_failed=1),
        )
    )
    assert card.derived_verdict == "RECONCILED"
    assert card.reconciliation.unreconciled_local_seqs == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"n_agree": 5}, "n_agree cannot exceed n_sample"),
        ({"n_sample": 5, "n_agree": 5, "agreement": 1.0}, "cannot exceed calls"),
        ({"n_sample": 0, "n_agree": 0, "agreement": 0.0}, "null when n_sample is 0"),
        ({"agreement": None}, "equal n_agree / n_sample"),
        ({"agreement": 0.5}, "equal n_agree / n_sample"),
        ({"tiebreak_overflow": -1}, "greater than or equal to 0"),
    ],
)
def test_audit_rejects(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        m.Audit.model_validate({**receipt()["audit"], **overrides})


def test_audit_agreement_is_null_only_when_sample_is_empty() -> None:
    empty = m.Audit.model_validate(
        {
            "n_sample": 0,
            "n_agree": 0,
            "agreement": None,
            "tiebreak_calls": 3,
            "tiebreak_overflow": 2,
        }
    )
    assert empty.agreement is None
    full = m.Audit.model_validate(
        {
            "n_sample": 3,
            "n_agree": 1,
            "agreement": 1 / 3,
            "tiebreak_calls": 9,
            "tiebreak_overflow": 0,
        }
    )
    assert full.agreement == pytest.approx(1 / 3)


def test_receipt_unreconciled_seqs_must_match_ledger() -> None:
    with pytest.raises(ValidationError, match="unreconciled_local_seqs"):
        m.Receipt.model_validate(
            receipt(
                reconciliation={
                    "fetched_at": T0,
                    "n_listed_in_window": 1,
                    "unmatched_remote_run_ids": [],
                    "unreconciled_local_seqs": [1],
                }
            )
        )


# --------------------------------------------------------------------------- Digest rules


def test_digest_requires_x_coverage_gap_and_topic_order() -> None:
    with pytest.raises(ValidationError, match="coverage_gaps"):
        m.Digest.model_validate(digest(coverage_gaps=[]))
    two = [topic(topic_id="nubank-02"), topic(topic_id="nubank-01")]
    with pytest.raises(ValidationError, match="ordered by brand"):
        m.Digest.model_validate(digest(topics=two))


def test_digest_caps_top_mentions_per_brand() -> None:
    eleven = [digest()["top_mentions"][0]] * 11
    with pytest.raises(ValidationError, match="at most 10 per brand"):
        m.Digest.model_validate(digest(top_mentions=eleven))
    ok = m.Digest.model_validate(
        digest(top_mentions=eleven[:10] + [{**eleven[0], "brand": "Inter"}])
    )
    assert len(ok.top_mentions) == 11


def test_date_range_rejects_end_before_start() -> None:
    with pytest.raises(ValidationError, match="end precedes start"):
        m.DateRange.model_validate({"start": T0, "end": T0 - timedelta(days=1)})


def wow_net(**overrides: Any) -> dict[str, Any]:
    base = dict(digest()["sentiment"][0]["wow"])
    base.update(overrides)
    return base


def wow_share(**overrides: Any) -> dict[str, Any]:
    base = dict(digest()["share_of_voice"][0]["wow"])
    base.update(overrides)
    return base


NULL_WOW_NET: dict[str, Any] = {
    "delta": None,
    "ci95": None,
    "ci95_confirmed_only": None,
    "verdict": "ABSTAIN",
    "p_raw": None,
    "p_holm": None,
}
NULL_WOW_SHARE: dict[str, Any] = {
    "delta": None,
    "ci95": None,
    "verdict": "ABSTAIN",
    "p_raw": None,
    "p_holm": None,
}


@pytest.mark.parametrize(
    ("delta", "ci95", "confirmed", "p_raw", "p_holm", "expected"),
    [
        (0.2, (0.1, 0.3), (0.05, 0.3), 0.001, 0.004, "SIGNIFICANT"),
        (0.2, (0.1, 0.3), (-0.05, 0.3), 0.001, 0.004, "SUGGESTIVE"),
        (0.2, (0.1, 0.3), (0.05, 0.3), 0.03, 0.06, "SUGGESTIVE"),
        (0.02, (-0.1, 0.2), (-0.1, 0.2), 0.4, 0.8, "NO_CHANGE_DETECTED"),
        (0.2, (0.1, 0.3), (-0.3, -0.05), 0.001, 0.004, "ABSTAIN"),
        (-0.2, (-0.3, -0.1), (0.05, 0.3), 0.4, 0.8, "ABSTAIN"),
        (-0.2, (-0.3, -0.1), (-0.3, -0.05), 0.001, 0.004, "SIGNIFICANT"),
        (0.0, (-0.1, 0.1), (-0.1, 0.1), 0.01, 0.04, "SUGGESTIVE"),
        (0.2, (0.1, 0.3), None, 0.001, 0.004, "SIGNIFICANT"),
        (0.2, (-0.1, 0.3), None, 0.001, 0.004, "SIGNIFICANT"),
        (0.2, (0.1, 0.3), None, 0.03, 0.06, "SUGGESTIVE"),
        (0.2, (0.1, 0.3), None, 0.05, 0.1, "NO_CHANGE_DETECTED"),
    ],
)
def test_derive_wow_verdict_follows_the_holm_rule(
    delta: float,
    ci95: tuple[float, float],
    confirmed: tuple[float, float] | None,
    p_raw: float,
    p_holm: float,
    expected: str,
) -> None:
    assert m.derive_wow_verdict(delta, ci95, confirmed, p_raw, p_holm) == expected


def test_wow_net_below_minimum_is_all_null_and_conflict_keeps_values() -> None:
    below = m.WowNet.model_validate(NULL_WOW_NET)
    assert below.is_below_minimum
    with pytest.raises(ValidationError, match="require verdict ABSTAIN"):
        m.WowNet.model_validate({**NULL_WOW_NET, "verdict": "NO_CHANGE_DETECTED"})
    with pytest.raises(ValidationError, match="all null .* or all reported"):
        m.WowNet.model_validate({**NULL_WOW_NET, "p_raw": 0.5})
    with pytest.raises(ValidationError, match="all null .* or all reported"):
        m.WowNet.model_validate(wow_net(ci95_confirmed_only=None))
    conflict = m.WowNet.model_validate(
        wow_net(
            delta=0.2,
            ci95=[0.1, 0.3],
            ci95_confirmed_only=[-0.3, -0.05],
            verdict="ABSTAIN",
            p_raw=0.001,
            p_holm=0.004,
        )
    )
    assert conflict.verdict == "ABSTAIN"
    assert conflict.p_holm == 0.004
    assert not conflict.is_below_minimum
    with pytest.raises(ValidationError, match="contradicts"):
        m.WowNet.model_validate(
            wow_net(
                delta=0.2,
                ci95=[0.1, 0.3],
                ci95_confirmed_only=[-0.3, -0.05],
                verdict="SIGNIFICANT",
                p_raw=0.001,
                p_holm=0.004,
            )
        )


def test_wow_net_verdict_must_match_the_rule() -> None:
    significant = m.WowNet.model_validate(
        wow_net(
            delta=0.2,
            ci95=[0.1, 0.3],
            ci95_confirmed_only=[0.05, 0.3],
            verdict="SIGNIFICANT",
            p_raw=0.001,
            p_holm=0.004,
        )
    )
    assert significant.verdict == "SIGNIFICANT"
    with pytest.raises(ValidationError, match="expected SUGGESTIVE"):
        m.WowNet.model_validate(wow_net(verdict="SIGNIFICANT"))
    with pytest.raises(ValidationError, match="expected SUGGESTIVE"):
        m.WowNet.model_validate(wow_net(verdict="NO_CHANGE_DETECTED"))
    with pytest.raises(ValidationError, match="expected SUGGESTIVE"):
        m.WowNet.model_validate(
            wow_net(ci95_confirmed_only=[-0.05, 0.3], verdict="SIGNIFICANT", p_holm=0.01)
        )


def test_wow_share_may_be_significant_and_abstains_all_null() -> None:
    significant = m.WowShare.model_validate(
        wow_share(delta=0.2, ci95=[0.1, 0.3], verdict="SIGNIFICANT", p_raw=0.001, p_holm=0.004)
    )
    assert significant.verdict == "SIGNIFICANT"
    with pytest.raises(ValidationError, match="expected SIGNIFICANT"):
        m.WowShare.model_validate(
            wow_share(delta=0.2, ci95=[0.1, 0.3], verdict="SUGGESTIVE", p_raw=0.001, p_holm=0.004)
        )
    with pytest.raises(ValidationError, match="expected NO_CHANGE_DETECTED"):
        m.WowShare.model_validate(wow_share(verdict="SUGGESTIVE"))
    below = m.WowShare.model_validate(NULL_WOW_SHARE)
    assert below.delta is None
    with pytest.raises(ValidationError, match="null on a share ABSTAIN"):
        m.WowShare.model_validate({**NULL_WOW_SHARE, "p_raw": 0.5})
    with pytest.raises(ValidationError, match="reported unless ABSTAIN"):
        m.WowShare.model_validate(wow_share(ci95=None))


def test_digest_entry_count_rules() -> None:
    sentiment = {**digest()["sentiment"][0], "n_confirmed": 99}
    with pytest.raises(ValidationError, match="n_confirmed cannot exceed"):
        m.SentimentEntry.model_validate(sentiment)
    with pytest.raises(ValidationError, match="pos \\+ neg \\+ neu cannot exceed n"):
        m.SentimentEntry.model_validate({**digest()["sentiment"][0], "n": 30})
    by_source = {**digest()["by_source"][0], "n": 0, "pos": 0, "neg": 0, "neu": 0, "net": 0.0}
    with pytest.raises(ValidationError, match="net must be null"):
        m.BySourceEntry.model_validate(by_source)
    nulls = {"net": None, "ci95": None, "ci95_iid": None, "design_effect": None, "n_clusters": 0}
    assert m.BySourceEntry.model_validate({**by_source, **nulls}).net is None
    with pytest.raises(ValidationError, match="at most 240"):
        m.TopMention.model_validate({**digest()["top_mentions"][0], "quote": "q" * 241})
    with pytest.raises(ValidationError, match="chars must equal"):
        m.Narration.model_validate({**digest()["narration"], "chars": 1})
    silent = m.Narration.model_validate(
        {"text": None, "chars": 0, "numbers_verified": False, "mp3_path": None, "local_seq": None}
    )
    assert silent.text is None
    with pytest.raises(ValidationError, match="greater than or equal to 5"):
        m.Event.model_validate({**digest()["events"][0], "n": 4})


def test_sov_entry_share_and_ci95_are_null_together() -> None:
    sov = digest()["share_of_voice"][0]
    below = m.SovEntry.model_validate(
        {**sov, "n": 4, "n_clusters": 3, "share": None, "ci95": None, "wow": NULL_WOW_SHARE}
    )
    assert below.has_null_estimate
    with pytest.raises(ValidationError, match="null together"):
        m.SovEntry.model_validate({**sov, "share": None})
    with pytest.raises(ValidationError, match="null together"):
        m.SovEntry.model_validate({**sov, "ci95": None})
    with pytest.raises(ValidationError, match="basis_sources must be distinct"):
        m.SovEntry.model_validate({**sov, "basis_sources": ["reddit", "reddit"]})
    with pytest.raises(ValidationError, match="n_clusters cannot exceed n"):
        m.SovEntry.model_validate({**sov, "n_clusters": 99})


def test_sentiment_entry_null_rules_and_design_effect_formula() -> None:
    sent = digest()["sentiment"][0]
    assert m.SentimentEntry.model_validate(sent).design_effect == pytest.approx(1.96)
    with pytest.raises(ValidationError, match="design_effect must equal"):
        m.SentimentEntry.model_validate({**sent, "design_effect": 1.5})
    empty = m.SentimentEntry.model_validate(
        {
            **sent,
            "pos": 0,
            "neg": 0,
            "neu": 0,
            "n_confirmed": 0,
            "net": None,
            "ci95": None,
            "ci95_iid": None,
            "design_effect": None,
            "wow": NULL_WOW_NET,
        }
    )
    assert empty.has_null_estimate
    assert empty.labelled == 0
    with pytest.raises(ValidationError, match="net must be null when pos \\+ neg \\+ neu is 0"):
        m.SentimentEntry.model_validate({**sent, "pos": 0, "neg": 0, "neu": 0})
    with pytest.raises(ValidationError, match="are null when net is"):
        m.SentimentEntry.model_validate({**sent, "net": None})
    with pytest.raises(ValidationError, match="ci95 and ci95_iid are reported when net is"):
        m.SentimentEntry.model_validate({**sent, "ci95_iid": None, "design_effect": None})
    degenerate = m.SentimentEntry.model_validate(
        {**sent, "ci95_iid": [0.4, 0.4], "design_effect": None}
    )
    assert degenerate.design_effect is None
    with pytest.raises(ValidationError, match="null when the iid width is 0"):
        m.SentimentEntry.model_validate({**sent, "ci95_iid": [0.4, 0.4]})


def test_by_source_entry_gains_intervals_design_effect_and_wow_scope() -> None:
    row = m.BySourceEntry.model_validate(digest()["by_source"][0])
    assert row.ci95 == (0.2, 0.55)
    assert row.ci95_iid == (0.25, 0.5)
    assert row.design_effect == pytest.approx(1.96)
    assert row.wow_scope is True
    assert row.h2_scored is True
    with pytest.raises(ValidationError, match="wow_scope"):
        m.BySourceEntry.model_validate(
            {k: v for k, v in digest()["by_source"][0].items() if k != "wow_scope"}
        )
    with pytest.raises(ValidationError, match="design_effect must equal"):
        m.BySourceEntry.model_validate({**digest()["by_source"][0], "design_effect": 2.5})
    with pytest.raises(ValidationError, match="are null when net is"):
        m.BySourceEntry.model_validate({**digest()["by_source"][0], "net": None})
    no_stamps = m.BySourceEntry.model_validate(
        {**digest()["by_source"][0], "source": "youtube_comment", "wow_scope": False}
    )
    assert no_stamps.wow_scope is False
    assert no_stamps.h2_scored is True
    author_clustered = m.BySourceEntry.model_validate(
        {**digest()["by_source"][0], "source": "tiktok"}
    )
    assert author_clustered.h2_scored is False
    assert m.H2_SCORED_SOURCES == {"reddit", "youtube_comment"}


def test_event_threshold_rule() -> None:
    assert m.event_threshold(2.0, 1.0) == 5.0
    assert m.event_threshold(4.0, 2.0) == 10.0
    event = digest()["events"][0]
    with pytest.raises(ValidationError, match="threshold must equal"):
        m.Event.model_validate({**event, "threshold": 6.0})
    with pytest.raises(ValidationError, match="threshold must equal"):
        m.Event.model_validate({**event, "baseline_mad": 2.0})
    with pytest.raises(ValidationError, match="n >= threshold"):
        m.Event.model_validate(
            {**event, "baseline_median": 4.0, "baseline_mad": 2.0, "threshold": 10.0}
        )
    spike = m.Event.model_validate(
        {**event, "n": 12, "baseline_median": 4.0, "baseline_mad": 2.0, "threshold": 10.0}
    )
    assert spike.threshold == 10.0
    with pytest.raises(ValidationError, match="baseline_mad"):
        m.Event.model_validate({k: v for k, v in event.items() if k != "baseline_mad"})
    with pytest.raises(ValidationError, match="n_clusters cannot exceed n"):
        m.Event.model_validate({**event, "n_clusters": 10})


def test_top_mentions_sort_by_engagement_then_published_then_mention_id() -> None:
    first = digest()["top_mentions"][0]
    later = {**first, "mention_id": MID2, "source": "news", "engagement_score": 15}
    earlier = {
        **first,
        "mention_id": MID3,
        "source": "youtube",
        "engagement_score": 15,
        "published_at": T0 - timedelta(days=1),
    }
    unstamped = {**first, "mention_id": MID, "engagement_score": 15, "published_at": None}
    top = {**first, "mention_id": MID, "engagement_score": 40, "published_at": None}
    ordered = sorted([later, earlier, unstamped], key=lambda t: t["mention_id"])
    ordered.sort(key=lambda t: (t["published_at"] is None, -(t["published_at"] or T0).timestamp()))
    ok = m.Digest.model_validate(digest(top_mentions=[top, *ordered]))
    keys = [t.sort_key for t in ok.top_mentions]
    assert keys == sorted(keys)
    with pytest.raises(ValidationError, match="engagement_score desc"):
        m.Digest.model_validate(digest(top_mentions=[first, top]))
    with pytest.raises(ValidationError, match="engagement_score desc"):
        m.Digest.model_validate(digest(top_mentions=[earlier, later]))
    with pytest.raises(ValidationError, match="engagement_score desc"):
        m.Digest.model_validate(digest(top_mentions=[unstamped, later]))
    with pytest.raises(ValidationError, match="engagement_score"):
        m.TopMention.model_validate({k: v for k, v in first.items() if k != "engagement_score"})
    negative = m.TopMention.model_validate({**first, "engagement_score": -3})
    assert negative.engagement_score == -3


def test_window_is_two_contiguous_seven_day_periods() -> None:
    window = digest()["window"]
    with pytest.raises(ValidationError, match="previous.end must equal current.start"):
        m.Window.model_validate(
            {
                **window,
                "previous": {"start": T0 - timedelta(days=15), "end": T0 - timedelta(days=8)},
            }
        )
    with pytest.raises(ValidationError, match="current period must span exactly 7 days"):
        m.Window.model_validate({**window, "current": {"start": T0 - timedelta(days=6), "end": T0}})
    with pytest.raises(ValidationError, match="previous period must span exactly 7 days"):
        m.Window.model_validate(
            {
                **window,
                "previous": {"start": T0 - timedelta(days=13), "end": T0 - timedelta(days=7)},
            }
        )
    assert m.PERIOD_DAYS == 7


def abstention(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "scope": "brand",
        "brand": "Nubank",
        "source": None,
        "reason": "below_minimum",
        "detail": "n < 20 in the previous period",
    }
    base.update(overrides)
    return base


def test_digest_pairs_every_null_estimate_with_an_abstention() -> None:
    sov_null = {
        **digest()["share_of_voice"][0],
        "share": None,
        "ci95": None,
        "wow": NULL_WOW_SHARE,
    }
    with pytest.raises(ValidationError, match="share_of_voice Nubank"):
        m.Digest.model_validate(digest(share_of_voice=[sov_null]))
    ok = m.Digest.model_validate(digest(share_of_voice=[sov_null], abstentions=[abstention()]))
    assert ok.share_of_voice[0].share is None

    wow_only = {**digest()["sentiment"][0], "wow": NULL_WOW_NET}
    with pytest.raises(ValidationError, match="sentiment.wow Nubank"):
        m.Digest.model_validate(digest(sentiment=[wow_only]))
    assert m.Digest.model_validate(digest(sentiment=[wow_only], abstentions=[abstention()]))

    by_source_null = {
        **digest()["by_source"][0],
        "net": None,
        "ci95": None,
        "ci95_iid": None,
        "design_effect": None,
    }
    with pytest.raises(ValidationError, match="by_source Nubank/reddit"):
        m.Digest.model_validate(digest(by_source=[by_source_null]))
    per_source = abstention(source="reddit", detail="n < 20 for reddit")
    assert m.Digest.model_validate(digest(by_source=[by_source_null], abstentions=[per_source]))
    assert m.Digest.model_validate(digest(by_source=[by_source_null], abstentions=[abstention()]))
    other_source = abstention(source="news")
    with pytest.raises(ValidationError, match="by_source Nubank/reddit"):
        m.Digest.model_validate(digest(by_source=[by_source_null], abstentions=[other_source]))
    other_brand = abstention(brand="Inter")
    with pytest.raises(ValidationError, match="by_source Nubank/reddit"):
        m.Digest.model_validate(digest(by_source=[by_source_null], abstentions=[other_brand]))

    topic_null = topic(share=None, net=None, ci95=None)
    with pytest.raises(ValidationError, match="topics nubank-01"):
        m.Digest.model_validate(digest(topics=[topic_null]))
    topics_row = abstention(scope="topics", reason="below_minimum")
    assert m.Digest.model_validate(digest(topics=[topic_null], abstentions=[topics_row]))
    with pytest.raises(ValidationError, match="topics nubank-01"):
        m.Digest.model_validate(digest(topics=[topic_null], abstentions=[abstention()]))


def test_topic_estimates_are_nullable_and_threshold_is_fixed() -> None:
    null_topic = m.Topic.model_validate(topic(share=None, net=None, ci95=None))
    assert null_topic.has_null_estimate
    assert m.Topic.model_validate(topic(share=None)).has_null_estimate
    with pytest.raises(ValidationError, match="ci95 is null iff net is null"):
        m.Topic.model_validate(topic(net=None))
    with pytest.raises(ValidationError, match="ci95 is null iff net is null"):
        m.Topic.model_validate(topic(ci95=None))
    with pytest.raises(ValidationError, match="fixed at 0.35"):
        m.Topic.model_validate(topic(method={"embedding_model": "e", "threshold": 0.3}))
    default = m.TopicMethod.model_validate({"embedding_model": "e"})
    assert default.threshold == 0.35


def test_stats_file_is_the_digest_numbers_byte_for_byte() -> None:
    d = m.Digest.model_validate(digest())
    stats = m.StatsFile.from_digest(d)
    dumped = stats.model_dump(mode="json")
    full = d.model_dump(mode="json")
    assert set(dumped) == {"share_of_voice", "sentiment", "by_source", "events", "window"}
    for key, value in dumped.items():
        assert value == full[key]
    assert m.StatsFile.model_validate_json(stats.model_dump_json()) == stats
    with pytest.raises(ValidationError, match="extra"):
        m.StatsFile.model_validate({**stats_file(), "topics": d.model_dump(mode="json")["topics"]})


def test_abstention_accepts_pre_registered_and_contract_reasons() -> None:
    reasons = (
        "empty",
        "provider_failed",
        "rate_limited",
        "deadline",
        "unavailable",
        "schema_drift",
        "below_minimum",
        "halted",
    )
    for reason in reasons:
        row = m.Abstention.model_validate(abstention(brand="Inter", reason=reason, detail=""))
        assert row.reason == reason
    topics = m.Abstention.model_validate(abstention(scope="topics", reason="embedding_failed"))
    assert topics.reason == "embedding_failed"
    conflict = m.Abstention.model_validate(abstention(reason="signals_conflict"))
    assert conflict.reason == "signals_conflict"
    with pytest.raises(ValidationError, match="topics-only"):
        m.Abstention.model_validate(abstention(reason="embedding_failed"))
    with pytest.raises(ValidationError, match="scope must be brand"):
        m.Abstention.model_validate(abstention(scope="topics", reason="signals_conflict"))
    with pytest.raises(ValidationError):
        m.Abstention.model_validate(abstention(reason="bored"))
    with pytest.raises(ValidationError):
        m.Abstention.model_validate(abstention(scope="source", reason="no_timestamps"))


# --------------------------------------------------------------------------- Answer rules


def test_answer_refused_carries_empty_answer() -> None:
    refused = m.Answer.model_validate(
        answer(status="refused", answer="", citations=[], retrieved=[])
    )
    assert refused.retrieved == []
    with pytest.raises(ValidationError, match="empty answer"):
        m.Answer.model_validate(answer(status="refused"))
    with pytest.raises(ValidationError, match="at most 20"):
        m.Answer.model_validate(answer(retrieved=[MID] * 21))
    with pytest.raises(ValidationError, match="pattern"):
        m.Answer.model_validate(answer(citations=["not-a-mention-id"]))
    empty_store = m.Answer.model_validate(
        answer(status="refused", answer="", citations=[], retrieved=[], model="")
    )
    assert empty_store.model == ""


def test_answer_verified_numbers_replaces_numbers_verified() -> None:
    row = m.Answer.model_validate(answer(verified_numbers=["36", "0.39"]))
    assert row.verified_numbers == ["36", "0.39"]
    legacy = {k: v for k, v in answer().items() if k != "verified_numbers"}
    with pytest.raises(ValidationError, match="verified_numbers"):
        m.Answer.model_validate(legacy)
    with pytest.raises(ValidationError, match="extra"):
        m.Answer.model_validate({**legacy, "numbers_verified": []})


def test_canonical_json_refuses_nan() -> None:
    with pytest.raises(ValueError):
        m.canonical_json({"delta": float("nan")})
