"""Round-trips and rule checks for every CONTRACTS record in `sonar.models`."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

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
            "excluded_with_reason": {"not_about_brand": 2},
            "by_source": {"reddit": 38},
            "by_brand": {"Nubank": 38},
        },
        "abstentions": [
            {
                "scope": "source",
                "brand": None,
                "source": "instagram",
                "reason": "no_timestamps",
                "detail": "hashtag items carry no timestamp",
            }
        ],
        "what_could_not_be_checked": ["X/Twitter: no Monid endpoint"],
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
        "numbers_verified": [],
        "retrieved": [MID, MID2],
        "model": "gpt-5.6-terra",
        "usage": {"tokens": 900, "cost_usd": 0.002},
        "status": "ok",
    }
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
        "Answer",
    }


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
        ({"sources": ["reddit", "x"]}, "non-members"),
        ({"sources": ["reddit", "reddit"]}, "distinct"),
        ({"profile": "smoke", "sources": ["reddit", "news"]}, "smoke allows only"),
        ({"brand_hint": "h" * 121}, "at most 120"),
        ({"window_days": 0}, "greater than or equal to 1"),
        ({"window_days": 32}, "less than or equal to 31"),
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


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("full", list(m.SOURCES)),
        ("lite", list(m.SOURCES)),
        ("smoke", ["reddit", "google_maps"]),
    ],
)
def test_query_sources_default_to_profile_list(profile: str, expected: list[str]) -> None:
    q = m.Query.model_validate(query(profile=profile))
    assert q.sources == expected
    assert q.profile == profile


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
            cost_usd=None,
            billed_units=None,
            cost_source="unreconciled",
            error="insufficient credit",
        )
    )
    assert rejected.is_local_status
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
                billed_units=0,
                cost_source="/v1/runs",
                error="rate limited",
            )
        ),
    ]
    assert m.derive_verdict(False, reconciled_rows, reconciliation()) == "RECONCILED"
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


def test_wow_verdict_and_p_value_rules() -> None:
    abstain = m.WowNet.model_validate(
        {
            "delta": 0.0,
            "ci95": [-1.0, 1.0],
            "ci95_confirmed_only": [-1.0, 1.0],
            "verdict": "ABSTAIN",
            "p_raw": None,
            "p_holm": None,
        }
    )
    assert abstain.p_holm is None
    with pytest.raises(ValidationError, match="null on ABSTAIN"):
        m.WowNet.model_validate({**abstain.model_dump(), "p_raw": 0.5})
    with pytest.raises(ValidationError, match="reported unless"):
        m.WowNet.model_validate({**abstain.model_dump(), "verdict": "NO_CHANGE_DETECTED"})
    significant = m.WowNet.model_validate(
        {
            "delta": 0.2,
            "ci95": [0.1, 0.3],
            "ci95_confirmed_only": [0.05, 0.3],
            "verdict": "SIGNIFICANT",
            "p_raw": 0.001,
            "p_holm": 0.004,
        }
    )
    assert significant.verdict == "SIGNIFICANT"
    with pytest.raises(ValidationError, match="report SUGGESTIVE"):
        m.WowShare.model_validate(
            {
                "delta": 0.2,
                "ci95": [0.1, 0.3],
                "verdict": "SIGNIFICANT",
                "p_raw": 0.001,
                "p_holm": 0.004,
            }
        )


def test_digest_entry_count_rules() -> None:
    sentiment = {**digest()["sentiment"][0], "n_confirmed": 99}
    with pytest.raises(ValidationError, match="n_confirmed cannot exceed"):
        m.SentimentEntry.model_validate(sentiment)
    by_source = {**digest()["by_source"][0], "n": 0, "pos": 0, "neg": 0, "neu": 0, "net": 0.0}
    with pytest.raises(ValidationError, match="net must be null"):
        m.BySourceEntry.model_validate(by_source)
    assert m.BySourceEntry.model_validate({**by_source, "net": None}).net is None
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


def test_abstention_accepts_pre_registered_and_contract_reasons() -> None:
    for reason in (
        "empty",
        "provider_failed",
        "rate_limited",
        "deadline",
        "unavailable",
        "schema_drift",
        "no_timestamps",
        "below_minimum",
        "halted",
        "embedding_failed",
    ):
        row = m.Abstention.model_validate(
            {"scope": "brand", "brand": "Inter", "source": None, "reason": reason, "detail": ""}
        )
        assert row.reason == reason
    with pytest.raises(ValidationError):
        m.Abstention.model_validate(
            {"scope": "brand", "brand": "Inter", "source": None, "reason": "bored", "detail": ""}
        )


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


def test_canonical_json_refuses_nan() -> None:
    with pytest.raises(ValueError):
        m.canonical_json({"delta": float("nan")})
