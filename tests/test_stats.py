"""Statistics layer (W4.3): bootstrap, share of voice, sentiment, events, verdicts.

Every threshold is read from ``sonar.config``; records are validated through
``sonar.models``; nothing here touches the network or a model.
"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sonar import config
from sonar import models as m
from sonar.stats import bootstrap, events, frame, verdict
from sonar.stats.compute import StatsResult, compute_stats

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
GOLDEN = Path(__file__).parent / "golden" / "stats.json"
BRANDS = ("Nubank", "Inter", "C6 Bank")
SOURCES: tuple[m.Source, ...] = ("reddit", "google_maps", "news", "youtube_comment", "tiktok")
TIKTOK_EMPTY = m.Abstention(
    scope="source", brand=None, source="tiktok", reason="empty", detail="no items"
)
RANK = {"NO_CHANGE_DETECTED": 0, "SUGGESTIVE": 1, "SIGNIFICANT": 2}
FAST_B = 300

# --------------------------------------------------------------------------- builders


def make_mention(
    brand: str,
    source: m.Source,
    key: str,
    *,
    cluster: str | None = None,
    published_at: datetime | None,
    engagement: int = 0,
    rating: int | None = None,
    url: str | None = None,
) -> m.Mention:
    mention_id = m.mention_id_for(source, key)
    author = m.author_hash_for(source, f"@{key}")
    cluster_key = m.expected_cluster_key(source, mention_id, author)
    if cluster_key is None:
        cluster_key = cluster if cluster is not None else key
    return m.Mention(
        mention_id=mention_id,
        brand=brand,
        source=source,
        run_id="run_01",
        native_id=key,
        url=url,
        author_hash=author,
        text=f"{brand} mention {key}",
        lang="pt",
        published_at=published_at,
        engagement={"upvotes": engagement} if engagement else {},
        rating=rating,
        cluster_key=cluster_key,
        matched_terms=[m.normalize_term(brand)],
        raw_ref="1#0",
    )


def make_label(
    mention_id: str,
    label: m.SentimentLabel,
    *,
    corroboration: m.Corroboration = "confirmed",
    about_brand: bool = True,
    status: m.LabelStatus = "ok",
    topic_id: str | None = None,
) -> m.Label:
    classifier = {"model": "gpt-5.6-luna", "label": label, "confidence": 0.9, "status": "ok"}
    tiebreak: dict[str, Any] | None = None
    deterministic: dict[str, Any] = {"kind": "none", "label": None}
    decided_by = "classifier"
    if corroboration == "irrelevant":
        about_brand = about_brand and label == "irrelevant"
    elif corroboration == "confirmed":
        deterministic = {"kind": "lexicon", "label": label}
    elif corroboration == "contested":
        other = "negative" if label != "negative" else "positive"
        classifier = {"model": "gpt-5.6-luna", "label": other, "confidence": 0.7, "status": "ok"}
        tiebreak = {"model": "gpt-5.6-terra", "label": label, "confidence": 0.8, "status": "ok"}
        deterministic = {"kind": "lexicon", "label": label}
        decided_by = "tiebreak"
    usage = (
        {"tokens": 0, "cost_usd": 0.0} if status == "cached" else {"tokens": 10, "cost_usd": 1e-5}
    )
    return m.Label.model_validate(
        {
            "mention_id": mention_id,
            "label": label,
            "about_brand": about_brand,
            "confidence": 0.9,
            "rationale": "synthetic",
            "topic_id": topic_id,
            "signals": {
                "classifier": classifier,
                "tiebreak": tiebreak,
                "deterministic": deterministic,
                "overflow": False,
            },
            "corroboration": corroboration,
            "decided_by": decided_by,
            "prompt_rev": config.PROMPT_REV,
            "status": status,
            "usage": usage,
        }
    )


def labels_for(pos: int, neg: int, neu: int) -> list[m.SentimentLabel]:
    out: list[m.SentimentLabel] = []
    for _ in range(pos):
        out.append("positive")
    for _ in range(neg):
        out.append("negative")
    for _ in range(neu):
        out.append("neutral")
    return out


def row(
    brand: str,
    source: m.Source,
    key: str,
    label: m.SentimentLabel,
    *,
    cluster: str | None = None,
    published_at: datetime | None,
    corroboration: m.Corroboration = "confirmed",
    engagement: int = 0,
    url: str | None = None,
    topic_id: str | None = None,
    about_brand: bool = True,
    status: m.LabelStatus = "ok",
) -> tuple[m.Mention, m.Label]:
    mention = make_mention(
        brand,
        source,
        key,
        cluster=cluster,
        published_at=published_at,
        engagement=engagement,
        url=url,
    )
    return mention, make_label(
        mention.mention_id,
        label,
        corroboration=corroboration,
        about_brand=about_brand,
        status=status,
        topic_id=topic_id,
    )


def at(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


CURRENT = 3.0
PREVIOUS = 10.0


def period_rows(
    brand: str,
    period_days_ago: float,
    clusters: Sequence[tuple[int, int, int]],
    *,
    tag: str,
    source: m.Source = "reddit",
    corroboration: m.Corroboration = "confirmed",
) -> list[tuple[m.Mention, m.Label]]:
    """One reddit cluster per ``(pos, neg, neu)`` triple, all in one period."""
    out: list[tuple[m.Mention, m.Label]] = []
    for c, (pos, neg, neu) in enumerate(clusters):
        cluster = f"{tag}-{brand}-c{c}"
        labels = labels_for(pos, neg, neu)
        for i, label in enumerate(labels):
            out.append(
                row(
                    brand,
                    source,
                    f"{cluster}-{i}",
                    label,
                    cluster=cluster,
                    published_at=at(period_days_ago + i * 1e-3),
                    corroboration=corroboration,
                )
            )
    return out


def mirrored_brand(
    brand: str,
    clusters: Sequence[tuple[int, int, int]],
    *,
    tag: str,
    corroboration: m.Corroboration = "confirmed",
) -> list[tuple[m.Mention, m.Label]]:
    """The same clusters in both periods: each unit carries both periods' rows."""
    out: list[tuple[m.Mention, m.Label]] = []
    for c, (pos, neg, neu) in enumerate(clusters):
        cluster = f"{tag}-{brand}-c{c}"
        labels = labels_for(pos, neg, neu)
        for i, label in enumerate(labels):
            for name, days_ago in (("cur", CURRENT), ("prev", PREVIOUS)):
                out.append(
                    row(
                        brand,
                        "reddit",
                        f"{cluster}-{name}-{i}",
                        label,
                        cluster=cluster,
                        published_at=at(days_ago + i * 1e-3),
                        corroboration=corroboration,
                    )
                )
    return out


HEALTHY_SPEC = [
    (2, 1, 0),
    (1, 1, 1),
    (0, 2, 1),
    (3, 0, 0),
    (1, 2, 0),
    (2, 0, 1),
    (1, 1, 1),
    (0, 1, 2),
]


def healthy_brand(brand: str, tag: str = "h") -> list[tuple[m.Mention, m.Label]]:
    """Meets every minimum in both periods: 8 clusters x 3 rows per period, mirrored."""
    return mirrored_brand(brand, HEALTHY_SPEC, tag=tag)


def compute(
    rows: Iterable[tuple[m.Mention, m.Label]],
    *,
    brands: Sequence[str] = BRANDS[:2],
    sources: Sequence[m.Source] = ("reddit",),
    abstentions: Sequence[m.Abstention] = (),
    b: int = FAST_B,
    seed: int = config.SEED,
    now: datetime = NOW,
    topic_names: dict[str, str] | None = None,
) -> StatsResult:
    return compute_stats(
        brands,
        list(rows),
        sources=sources,
        abstentions=abstentions,
        now=now,
        b=b,
        seed=seed,
        topic_names=topic_names,
    )


def demo_session() -> list[tuple[m.Mention, m.Label]]:
    """A fixed synthetic session: three brands, four returning sources, mixed labels."""
    rng = random.Random(config.SEED)
    labels: list[m.SentimentLabel] = ["positive", "negative", "neutral"]
    corroborations: list[m.Corroboration] = ["confirmed", "confirmed", "model_only", "contested"]
    out: list[tuple[m.Mention, m.Label]] = []
    for b_idx, brand in enumerate(BRANDS):
        lean = [0.55, 0.45, 0.35][b_idx]
        for c in range(14):
            cluster = f"post-{brand}-{c}"
            days_ago = rng.uniform(0.1, 13.9)
            for i in range(rng.randint(2, 5)):
                label = "positive" if rng.random() < lean else rng.choice(labels)
                out.append(
                    row(
                        brand,
                        "reddit",
                        f"{cluster}-{i}",
                        label,
                        cluster=cluster,
                        published_at=at(days_ago + i * 0.01),
                        corroboration=rng.choice(corroborations),
                        engagement=rng.randint(0, 50),
                        url=f"https://reddit.com/r/x/{cluster}/{i}",
                        topic_id=f"{brand.lower().replace(' ', '-')}-0{rng.randint(1, 2)}",
                    )
                )
        for i in range(12):
            label = "positive" if rng.random() < lean else rng.choice(labels)
            out.append(
                row(
                    brand,
                    "google_maps",
                    f"maps-{brand}-{i}",
                    label,
                    published_at=at(rng.uniform(0.1, 13.9)),
                    corroboration="confirmed",
                    engagement=0,
                )
            )
        for i in range(6):
            out.append(
                row(
                    brand,
                    "news",
                    f"news-{brand}-{i}",
                    rng.choice(labels),
                    published_at=at(rng.uniform(0.1, 13.9)),
                    corroboration="model_only",
                    url=f"https://news.example/{brand}/{i}",
                )
            )
        for v in range(3):
            for i in range(4):
                out.append(
                    row(
                        brand,
                        "youtube_comment",
                        f"yt-{brand}-{v}-{i}",
                        rng.choice(labels),
                        cluster=f"video-{brand}-{v}",
                        published_at=None,
                        corroboration="model_only",
                    )
                )
        out.append(
            row(
                brand,
                "reddit",
                f"off-{brand}",
                "irrelevant",
                published_at=at(2.0),
                corroboration="irrelevant",
                about_brand=False,
            )
        )
        out.append(
            row(
                brand,
                "reddit",
                f"refused-{brand}",
                "neutral",
                published_at=at(2.0),
                corroboration="model_only",
                status="refused",
            )
        )
    # A spike day for the first brand: 9 rows over 4 clusters, all on one UTC day.
    spike = at(4.0).replace(hour=15)
    for i in range(9):
        out.append(
            row(
                BRANDS[0],
                "reddit",
                f"spike-{i}",
                "negative",
                cluster=f"spike-post-{i % 4}",
                published_at=spike + timedelta(minutes=i),
                engagement=100 + i,
                url=f"https://reddit.com/r/x/spike/{i}",
                topic_id="nubank-02",
            )
        )
    return out


def demo_stats(b: int = config.B_FROZEN_DEMO) -> StatsResult:
    return compute(
        demo_session(),
        brands=BRANDS,
        sources=SOURCES,
        abstentions=[TIKTOK_EMPTY],
        b=b,
        topic_names={"nubank-01": "Credit limit increases", "nubank-02": "App outage"},
    )


def golden_payload(result: StatsResult) -> dict[str, Any]:
    return {
        "b": result.b,
        "seed": result.seed,
        "n_units": result.n_units,
        "n_rows": result.n_rows,
        "stats": result.stats_file().model_dump(mode="json"),
        "abstentions": [a.model_dump(mode="json") for a in result.abstentions],
        "what_could_not_be_checked": result.what_could_not_be_checked,
    }


def assemble_digest(result: StatsResult, source_abstentions: Sequence[m.Abstention]) -> m.Digest:
    """Prove the pairing invariant: every null has its Abstention row."""
    totals = m.Totals(
        monid_usd=0.0,
        monid_runs=0,
        monid_runs_billed=0,
        monid_runs_zero_results=0,
        monid_runs_failed=0,
        llm_usd=0.0,
        llm_calls={},
        llm_tokens=0,
        elevenlabs_usd=0.0,
        total_usd=0.0,
    )
    return m.Digest(
        brand=result.share_of_voice[0].brand,
        competitors=[s.brand for s in result.share_of_voice[1:]],
        window=result.window,
        share_of_voice=result.share_of_voice,
        sentiment=result.sentiment,
        by_source=result.by_source,
        topics=[],
        events=result.events,
        top_mentions=[],
        abstentions=[*source_abstentions, *result.abstentions],
        coverage_gaps=[m.CoverageGap(source="x", reason="unavailable", note="no Monid endpoint")],
        cost=m.CostQuote(verdict="RECONCILED", totals=totals),
        narration=m.Narration(
            text=None, chars=0, numbers_verified=False, mp3_path=None, local_seq=None
        ),
    )


# --------------------------------------------------------------------------- bootstrap


def test_columns_matrix_is_int64_indicators() -> None:
    cols = bootstrap.Columns(4)
    a = cols.add("a", np.array([True, False, True, False]))
    b = cols.add("b", np.array([True, True, False, False]))
    matrix = cols.matrix()
    assert matrix.dtype == np.int64
    assert matrix[:, a].tolist() == [1, 0, 1, 0]
    assert matrix[:, b].tolist() == [1, 1, 0, 0]
    with pytest.raises(ValueError, match="already registered"):
        cols.add("a", np.zeros(4, dtype=bool))
    with pytest.raises(ValueError, match="shape"):
        cols.add("c", np.zeros(3, dtype=bool))


def test_resample_is_deterministic_and_conserves_totals() -> None:
    cols = bootstrap.Columns(6)
    cols.add("all", np.ones(6, dtype=bool))
    cols.add("half", np.array([1, 0, 1, 0, 1, 0], dtype=bool))
    units = np.array([0, 0, 1, 1, 2, 2], dtype=np.int64)
    one = bootstrap.resample(cols, units, 3, b=50, seed=config.SEED)
    two = bootstrap.resample(cols, units, 3, b=50, seed=config.SEED)
    assert np.array_equal(one.cluster, two.cluster) and np.array_equal(one.iid, two.iid)
    # Every resample draws exactly as many rows as the data has (3 units x 2 rows).
    assert set(one.cluster[:, 0].tolist()) == {6}
    assert set(one.iid[:, 0].tolist()) == {6}
    assert one.point.tolist() == [6, 3]
    other = bootstrap.resample(cols, units, 3, b=50, seed=config.SEED + 1)
    assert not np.array_equal(one.iid, other.iid)


def test_resample_empty_frame_is_all_zero() -> None:
    cols = bootstrap.Columns(0)
    cols.add("x", np.zeros(0, dtype=bool))
    res = bootstrap.resample(cols, np.zeros(0, dtype=np.int64), 0, b=5)
    assert res.cluster.shape == (5, 1) and not res.cluster.any()


def test_percentile_ci_matches_linear_interpolation_and_skips_nan() -> None:
    draws = np.array([np.nan, 1.0, 2.0, 3.0, 4.0, 5.0])
    assert bootstrap.percentile_ci(draws) == (1.1, 4.9)
    assert bootstrap.percentile_ci(np.array([np.nan, np.nan])) is None
    assert bootstrap.ratio(np.array([1.0, 2.0]), np.array([0.0, 4.0])).tolist()[1] == 0.5
    assert np.isnan(bootstrap.ratio(np.array([1.0]), np.array([0.0]))[0])


def test_design_effect_is_width_ratio_squared_or_none() -> None:
    assert bootstrap.design_effect((0.0, 0.4), (0.1, 0.3)) == pytest.approx(4.0)
    assert bootstrap.design_effect((0.2, 0.2), (0.2, 0.2)) is None


# --------------------------------------------------------------------------- verdict


def test_two_sided_p_is_twice_the_smaller_tail_capped_at_one() -> None:
    assert verdict.two_sided_p(np.array([0.5, 1.0, 2.0, -0.5])) == pytest.approx(0.5)
    assert verdict.two_sided_p(np.array([0.0, 0.0])) == 1.0
    assert verdict.two_sided_p(np.array([1.0, 2.0, 3.0, 4.0])) == 0.0
    assert verdict.two_sided_p(np.array([np.nan, -1.0, 1.0, np.nan])) == 1.0
    assert verdict.two_sided_p(np.array([np.nan])) is None


def test_holm_adjusts_over_non_null_tests_only() -> None:
    adjusted = verdict.holm([0.01, None, 0.04, 0.03])
    assert adjusted[1] is None
    assert adjusted[0] == pytest.approx(0.03)  # 3 * 0.01
    assert adjusted[3] == pytest.approx(0.06)  # max(0.03, 2 * 0.03)
    assert adjusted[2] == pytest.approx(0.06)  # max(0.06, 1 * 0.04)
    assert verdict.holm([None, None]) == [None, None]
    assert verdict.holm([0.9, 0.8]) == [1.0, 1.0]


def test_below_minimum_detail_names_the_estimand_and_period() -> None:
    ok = verdict.PeriodCounts(
        n=config.MIN_MENTIONS_PER_WEEK, n_clusters=config.MIN_CLUSTERS_PER_WEEK
    )
    assert verdict.below_minimum_detail("share", ok, ok) is None
    short = verdict.PeriodCounts(n=config.MIN_MENTIONS_PER_WEEK - 1, n_clusters=2)
    detail = verdict.below_minimum_detail("net", ok, short)
    assert detail is not None and detail.startswith("net: ")
    assert "in previous" in detail and "n_clusters=2" in detail and "in current" not in detail


def test_decide_net_signals_conflict_keeps_estimates_and_abstains_the_word() -> None:
    test = verdict.NetTest(
        brand="Nubank",
        delta=0.3,
        ci95=(0.1, 0.5),
        ci95_confirmed_only=(-0.6, -0.2),
        confirmed_detail=None,
        p_raw=0.01,
        below_minimum=None,
    )
    wow, rows = verdict.decide_net(test, 0.02)
    assert wow.verdict == "ABSTAIN" and wow.delta == 0.3 and wow.p_holm == 0.02
    assert [r.reason for r in rows] == ["signals_conflict"]


def test_decide_net_degenerate_confirmed_interval_can_be_suggestive_not_significant() -> None:
    test = verdict.NetTest(
        brand="Nubank",
        delta=0.3,
        ci95=(0.1, 0.5),
        ci95_confirmed_only=None,
        confirmed_detail="n_confirmed = 0",
        p_raw=0.001,
        below_minimum=None,
    )
    wow, rows = verdict.decide_net(test, 0.004)
    assert wow.verdict == "SUGGESTIVE"
    assert [(r.reason, r.detail) for r in rows] == [
        ("degenerate", "ci95_confirmed_only: n_confirmed = 0")
    ]


def test_decide_family_holm_family_counts_only_non_null_tests() -> None:
    share = [
        verdict.ShareTest("A", 0.1, (0.05, 0.2), 0.02, None),
        verdict.ShareTest("B", None, None, None, "share: n=3 < 20 in current"),
    ]
    net = [
        verdict.NetTest("A", 0.2, (0.1, 0.3), (0.05, 0.4), None, 0.01, None),
        verdict.NetTest("B", None, None, None, None, None, "net: n=3 < 20 in current"),
    ]
    decision = verdict.decide_family(share, net)
    # m = 2: net A adjusted 0.02, share A adjusted max(0.02, 0.02) = 0.02.
    assert decision.net["A"].p_holm == pytest.approx(0.02)
    assert decision.share["A"].p_holm == pytest.approx(0.02)
    assert decision.net["A"].verdict == "SIGNIFICANT"
    assert decision.share["A"].verdict == "SIGNIFICANT"
    assert decision.share["B"].verdict == "ABSTAIN" and decision.net["B"].verdict == "ABSTAIN"
    assert sorted((a.brand, a.reason) for a in decision.abstentions) == [
        ("B", "below_minimum"),
        ("B", "below_minimum"),
    ]


# --------------------------------------------------------------------------- frame


def test_window_is_two_seven_day_periods_ending_now() -> None:
    window = frame.window_for(NOW)
    assert window.current.end == NOW and window.current.start == NOW - timedelta(days=7)
    assert window.previous.start == NOW - timedelta(days=config.WINDOW_DAYS_DEFAULT)
    assert frame.period_of(at(0.5), window) == "current"
    assert frame.period_of(at(7.0), window) == "current"
    assert frame.period_of(at(7.5), window) == "previous"
    assert frame.period_of(at(14.0), window) == "previous"
    assert frame.period_of(at(14.5), window) is None
    assert frame.period_of(None, window) is None
    with pytest.raises(ValueError, match="timezone"):
        frame.window_for(NOW.replace(tzinfo=None))


def test_frame_keeps_relevant_rows_and_orders_units_by_brand() -> None:
    rows = [
        row("Inter", "reddit", "b1", "positive", cluster="pb", published_at=at(1)),
        row("Nubank", "reddit", "a1", "positive", cluster="pa", published_at=at(1)),
        row("Nubank", "reddit", "a2", "neutral", cluster="pa", published_at=None),
        row(
            "Nubank",
            "reddit",
            "a3",
            "irrelevant",
            published_at=at(1),
            corroboration="irrelevant",
            about_brand=False,
        ),
        row(
            "Nubank",
            "reddit",
            "a4",
            "neutral",
            published_at=at(1),
            status="error",
            corroboration="model_only",
        ),
        row(
            "Nubank",
            "youtube_comment",
            "y1",
            "negative",
            cluster="vid",
            published_at=None,
            corroboration="model_only",
        ),
    ]
    built = frame.build_frame(
        ["Nubank", "Inter"], rows, sources=["reddit", "youtube_comment"], abstentions=[], now=NOW
    )
    assert [r.brand for r in built.rows] == ["Nubank", "Nubank", "Nubank", "Inter"]
    assert built.n_units == 3 and sorted(built.unit_of_row.tolist()) == [0, 0, 1, 2]
    units = {r.cluster_key: r.unit for r in built.rows}
    assert units == {"pa": 0, "vid": 1, "pb": 2}
    assert built.wow_scope == {
        ("Nubank", "reddit"): True,
        ("Nubank", "youtube_comment"): False,
        ("Inter", "reddit"): True,
    }
    assert built.basis_sources == ("reddit", "youtube_comment")
    assert sorted(str(r.period) for r in built.rows) == ["None", "None", "current", "current"]


def test_frame_rejects_unknown_brand_and_mismatched_label() -> None:
    mention, label = row("Nubank", "reddit", "a1", "positive", published_at=at(1))
    with pytest.raises(ValueError, match="unknown brand"):
        frame.build_frame(
            ["Inter"], [(mention, label)], sources=["reddit"], abstentions=[], now=NOW
        )
    other = make_label(m.mention_id_for("reddit", "zzz"), "positive")
    with pytest.raises(ValueError, match="does not belong"):
        frame.build_frame(
            ["Nubank"], [(mention, other)], sources=["reddit"], abstentions=[], now=NOW
        )


def test_basis_sources_drop_a_source_abstained_for_any_brand() -> None:
    abst = m.Abstention(scope="source", brand="Inter", source="news", reason="deadline", detail="x")
    assert frame.basis_sources_for(["news", "reddit", "g2"], [abst]) == ("reddit", "g2")


# --------------------------------------------------------------------------- events


def test_event_days_are_fourteen_utc_dates_ending_today() -> None:
    days = events.event_days(NOW)
    assert len(days) == config.EVENT_BASELINE_DAYS
    assert days[-1] == date(2026, 9, 2) and days[0] == date(2026, 8, 20)
    assert events.event_days(datetime(2026, 9, 2, 23, 30, tzinfo=UTC))[-1] == date(2026, 9, 2)


def test_event_rule_median_mad_excluding_tested_day() -> None:
    rows: list[tuple[m.Mention, m.Label]] = []
    # Quiet baseline: two rows per day on twelve days, one cluster each.
    for d in range(1, 13):
        for i in range(2):
            rows.append(
                row(
                    "Nubank",
                    "reddit",
                    f"q{d}-{i}",
                    "neutral",
                    cluster=f"q{d}",
                    published_at=at(d + 1.2),
                )
            )
    # Tested day (yesterday): nine rows across four clusters, one with the top engagement.
    for i in range(9):
        rows.append(
            row(
                "Nubank",
                "reddit",
                f"s{i}",
                "negative",
                cluster=f"s{i % 4}",
                published_at=at(0.9) + timedelta(minutes=i),
                engagement=10 + (50 if i == 3 else 0),
                url=f"https://r/{i}",
            )
        )
    built = frame.build_frame(["Nubank"], rows, sources=["reddit"], abstentions=[], now=NOW)
    found = events.detect_events(built, NOW)
    assert len(found) == 1
    event = found[0]
    assert event.date == at(0.9).date() and event.n == 9 and event.n_clusters == 4
    # Baseline over the other 13 days: twelve 2s and one 0 (today) -> median 2, MAD 0.
    assert event.baseline_median == 2.0 and event.baseline_mad == 0.0
    assert event.threshold == max(config.EVENT_MIN_COUNT, 2.0)
    assert event.exhibit_url == "https://r/3" and event.label == "nubank"


def test_event_needs_breadth_and_topic_name_wins_the_label() -> None:
    rows: list[tuple[m.Mention, m.Label]] = []
    for i in range(8):
        rows.append(
            row(
                "Nubank",
                "reddit",
                f"one{i}",
                "negative",
                cluster="single",
                published_at=at(0.5),
                topic_id="nubank-01",
            )
        )
    built = frame.build_frame(["Nubank"], rows, sources=["reddit"], abstentions=[], now=NOW)
    assert events.detect_events(built, NOW) == []
    wide = [
        row(
            "Nubank",
            "reddit",
            f"w{i}",
            "negative",
            cluster=f"c{i % 3}",
            published_at=at(0.5),
            topic_id="nubank-01",
        )
        for i in range(8)
    ]
    built = frame.build_frame(["Nubank"], wide, sources=["reddit"], abstentions=[], now=NOW)
    found = events.detect_events(
        built, NOW, {"nubank-01": "Card blocked after the update again today"}
    )
    assert len(found) == 1 and found[0].label == "Card blocked after the update again"


def test_mad_and_median_helpers() -> None:
    assert events.median([1, 5, 2]) == 2.0
    assert events.mad([1, 5, 2], 2.0) == 1.0
    assert events.threshold_for(1.0, 0.5) == float(config.EVENT_MIN_COUNT)
    assert events.threshold_for(4.0, 1.0) == 4.0 + config.EVENT_MAD_MULTIPLIER
    with pytest.raises(ValueError):
        events.median([])


# --------------------------------------------------------------------------- end to end


def test_compute_stats_records_validate_and_pair_every_null() -> None:
    result = demo_stats(b=FAST_B)
    digest = assemble_digest(result, [TIKTOK_EMPTY])
    assert [s.brand for s in digest.share_of_voice] == list(BRANDS)
    assert result.share_of_voice[0].basis_sources == [
        "reddit",
        "youtube_comment",
        "google_maps",
        "news",
    ]
    assert [(e.brand, e.source) for e in result.by_source][:4] == [
        (BRANDS[0], "reddit"),
        (BRANDS[0], "youtube_comment"),
        (BRANDS[0], "google_maps"),
        (BRANDS[0], "news"),
    ]
    yt = [e for e in result.by_source if e.source == "youtube_comment"]
    assert all(not e.wow_scope for e in yt)
    assert result.what_could_not_be_checked == [
        f"youtube_comment: items lacking a timestamp, excluded from WoW and events ({b})"
        for b in BRANDS
    ]
    assert any(e.date == at(4.0).date() and e.label == "App outage" for e in result.events)
    stats = result.stats_file()
    assert m.StatsFile.model_validate_json(stats.model_dump_json()) == stats


def test_shared_index_pairs_periods_and_brands() -> None:
    """Two brands with mirrored data have equal shares and exactly zero deltas."""
    rows = healthy_brand("Nubank", "a") + healthy_brand("Inter", "b")
    result = compute(rows)
    for entry in result.share_of_voice:
        assert entry.share == 0.5 and entry.wow.delta == 0.0 and entry.wow.ci95 == (0.0, 0.0)
        assert entry.wow.p_raw == 1.0 and entry.wow.verdict == "NO_CHANGE_DETECTED"
    for sent in result.sentiment:
        assert sent.wow.delta == 0.0 and sent.wow.verdict == "NO_CHANGE_DETECTED"


def test_below_minimum_nulls_everything_and_pairs_rows() -> None:
    rows = healthy_brand("Nubank") + period_rows("Inter", CURRENT, [(3, 2, 0)] * 8, tag="cur")
    result = compute(rows)
    inter_sov = result.share_of_voice[1]
    inter_sent = result.sentiment[1]
    assert inter_sov.share is None and inter_sov.ci95 is None and inter_sov.wow.verdict == "ABSTAIN"
    assert inter_sent.net is None and inter_sent.design_effect is None
    assert inter_sent.wow.is_below_minimum
    reasons = sorted((a.brand, a.reason, a.detail.split(":")[0]) for a in result.abstentions)
    assert reasons == [("Inter", "below_minimum", "net"), ("Inter", "below_minimum", "share")]
    assert "n=0" in next(a.detail for a in result.abstentions if a.detail.startswith("share"))
    # The healthy brand still reports, and its share counts Inter's rows in the denominator.
    nubank = result.share_of_voice[0]
    assert nubank.share == pytest.approx(48 / (48 + 40))
    # by_source stands on its own rule (H2 minimums are full-window).
    inter_source = next(e for e in result.by_source if e.brand == "Inter")
    assert inter_source.net is not None and inter_source.n == 40
    assemble_digest(result, [])


def test_zero_iid_width_is_degenerate_design_effect() -> None:
    spec = [(3, 0, 0)] * 8
    rows = period_rows("Nubank", CURRENT, spec, tag="c") + period_rows(
        "Nubank", PREVIOUS, spec, tag="p"
    )
    rows += healthy_brand("Inter")
    result = compute(rows)
    nubank = result.sentiment[0]
    assert nubank.net == 1.0 and nubank.ci95 == (1.0, 1.0) and nubank.ci95_iid == (1.0, 1.0)
    assert nubank.design_effect is None and nubank.has_degenerate_design_effect
    degenerate = [a for a in result.abstentions if a.reason == "degenerate" and a.brand == "Nubank"]
    assert {a.source for a in degenerate} == {None, "reddit"}
    assemble_digest(result, [])


def test_no_confirmed_rows_gives_null_confirmed_interval_and_never_significant() -> None:
    spec_prev = [(0, 3, 0)] * 10
    spec_cur = [(3, 0, 0)] * 10
    rows = period_rows("Nubank", CURRENT, spec_cur, tag="c", corroboration="model_only")
    rows += period_rows("Nubank", PREVIOUS, spec_prev, tag="p", corroboration="model_only")
    rows += healthy_brand("Inter")
    result = compute(rows)
    nubank = result.sentiment[0]
    assert nubank.n_confirmed == 0 and nubank.wow.ci95_confirmed_only is None
    assert nubank.wow.p_holm is not None and nubank.wow.p_holm < config.HOLM_ALPHA
    assert nubank.wow.verdict == "SUGGESTIVE"
    details = [
        a.detail for a in result.abstentions if a.reason == "degenerate" and a.brand == "Nubank"
    ]
    assert "ci95_confirmed_only: n_confirmed = 0" in details
    assemble_digest(result, [])


def test_signals_conflict_abstains_with_estimates_kept() -> None:
    rows: list[tuple[m.Mention, m.Label]] = []
    rows += period_rows("Nubank", CURRENT, [(0, 2, 0)] * 12, tag="cc", corroboration="confirmed")
    rows += period_rows("Nubank", CURRENT, [(4, 0, 0)] * 12, tag="cm", corroboration="model_only")
    rows += period_rows("Nubank", PREVIOUS, [(2, 0, 0)] * 12, tag="pc", corroboration="confirmed")
    rows += period_rows("Nubank", PREVIOUS, [(0, 4, 0)] * 12, tag="pm", corroboration="model_only")
    rows += healthy_brand("Inter")
    result = compute(rows)
    wow = result.sentiment[0].wow
    assert wow.verdict == "ABSTAIN" and wow.delta is not None and wow.delta > 0
    assert wow.ci95 is not None and wow.ci95[0] > 0
    assert wow.ci95_confirmed_only is not None and wow.ci95_confirmed_only[1] < 0
    assert [a.reason for a in result.abstentions if a.brand == "Nubank"] == ["signals_conflict"]
    assemble_digest(result, [])


def test_clear_effect_is_significant_with_holm() -> None:
    rows = period_rows("Nubank", CURRENT, [(3, 0, 0)] * 10, tag="c")
    rows += period_rows("Nubank", PREVIOUS, [(0, 3, 0)] * 10, tag="p")
    rows += healthy_brand("Inter")
    result = compute(rows, b=config.B)
    wow = result.sentiment[0].wow
    assert wow.verdict == "SIGNIFICANT" and wow.p_raw == 0.0 and wow.p_holm == 0.0
    assert wow.delta == 2.0 and wow.ci95 == (2.0, 2.0)
    # Share moved too: Nubank owns every current-period cluster it had before as well.
    assert result.share_of_voice[0].wow.verdict == "NO_CHANGE_DETECTED"


def test_empty_session_abstains_every_brand() -> None:
    result = compute([], brands=BRANDS, sources=SOURCES, abstentions=[TIKTOK_EMPTY])
    assert all(s.share is None and s.n == 0 for s in result.share_of_voice)
    assert all(s.net is None and s.wow.verdict == "ABSTAIN" for s in result.sentiment)
    assert all(e.net is None for e in result.by_source)
    assert result.events == [] and result.n_units == 0
    assemble_digest(result, [TIKTOK_EMPTY])


def test_rows_outside_the_window_count_for_share_only() -> None:
    rows = healthy_brand("Nubank") + healthy_brand("Inter")
    stale = [
        row("Nubank", "reddit", f"old{i}", "positive", cluster="old", published_at=at(20.0))
        for i in range(5)
    ]
    with_stale = compute(rows + stale)
    without = compute(rows)
    assert with_stale.sentiment[0].n == without.sentiment[0].n + 5
    assert with_stale.share_of_voice[0].n == without.share_of_voice[0].n + 5
    assert with_stale.sentiment[0].wow.delta == without.sentiment[0].wow.delta
    assert with_stale.share_of_voice[0].wow.delta == without.share_of_voice[0].wow.delta


# --------------------------------------------------------------------------- golden


def test_golden_stats_json_seed_777() -> None:
    result = demo_stats()
    payload = golden_payload(result)
    assert payload["b"] == config.B_FROZEN_DEMO and payload["seed"] == config.SEED
    if os.environ.get("SONAR_UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    expected = json.loads(GOLDEN.read_text())
    assert payload == expected
    assemble_digest(result, [TIKTOK_EMPTY])


# --------------------------------------------------------------------------- properties

cluster_spec = st.tuples(st.integers(0, 4), st.integers(0, 4), st.integers(0, 3)).filter(
    lambda t: sum(t) > 0
)
period_spec = st.lists(cluster_spec, min_size=5, max_size=9).filter(
    lambda cs: sum(map(sum, cs)) >= config.MIN_MENTIONS_PER_WEEK
)
brand_spec = st.tuples(period_spec, period_spec)

PROPERTY = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def brand_rows(
    brand: str,
    spec: tuple[Sequence[tuple[int, int, int]], Sequence[tuple[int, int, int]]],
    tag: str,
) -> list[tuple[m.Mention, m.Label]]:
    current, previous = spec
    return period_rows(brand, CURRENT, current, tag=f"{tag}c") + period_rows(
        brand, PREVIOUS, previous, tag=f"{tag}p"
    )


@PROPERTY
@given(a=brand_spec, b=brand_spec, c=brand_spec)
def test_property_shares_sum_to_one(a: Any, b: Any, c: Any) -> None:
    rows = (
        brand_rows("Nubank", a, "a") + brand_rows("Inter", b, "b") + brand_rows("C6 Bank", c, "c")
    )
    result = compute(rows, brands=BRANDS)
    shares = [s.share for s in result.share_of_voice]
    assert all(s is not None for s in shares)
    assert sum(s for s in shares if s is not None) == pytest.approx(1.0)


@PROPERTY
@given(a=brand_spec, b=brand_spec)
def test_property_point_inside_ci(a: Any, b: Any) -> None:
    result = compute(brand_rows("Nubank", a, "a") + brand_rows("Inter", b, "b"))
    for sov in result.share_of_voice:
        assert sov.share is not None and sov.ci95 is not None
        assert sov.ci95[0] <= sov.share <= sov.ci95[1]
        assert sov.wow.delta is not None and sov.wow.ci95 is not None
        assert sov.wow.ci95[0] <= sov.wow.delta <= sov.wow.ci95[1]
    for sent in result.sentiment:
        assert sent.net is not None and sent.ci95 is not None and sent.ci95_iid is not None
        assert sent.ci95[0] <= sent.net <= sent.ci95[1]
        assert sent.ci95_iid[0] <= sent.net <= sent.ci95_iid[1]
        assert sent.wow.delta is not None and sent.wow.ci95 is not None
        assert sent.wow.ci95[0] <= sent.wow.delta <= sent.wow.ci95[1]
    for entry in result.by_source:
        assert entry.net is not None and entry.ci95 is not None
        assert entry.ci95[0] <= entry.net <= entry.ci95[1]


homogeneous = st.lists(
    st.tuples(st.sampled_from(["positive", "negative"]), st.integers(6, 12)),
    min_size=6,
    max_size=10,
).filter(lambda cs: len({sign for sign, _ in cs}) == 2)


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(clusters=homogeneous)
def test_property_cluster_ci_at_least_as_wide_as_iid_when_clusters_are_homogeneous(
    clusters: list[tuple[str, int]],
) -> None:
    spec = [((n, 0, 0) if sign == "positive" else (0, n, 0)) for sign, n in clusters]
    rows = period_rows("Nubank", CURRENT, spec, tag="c") + period_rows(
        "Nubank", PREVIOUS, spec, tag="p"
    )
    rows += healthy_brand("Inter")
    result = compute(rows, b=config.B)
    nubank = result.sentiment[0]
    assert nubank.ci95 is not None and nubank.ci95_iid is not None
    assert bootstrap.width(nubank.ci95) >= bootstrap.width(nubank.ci95_iid)
    assert nubank.design_effect is not None and nubank.design_effect >= 1.0


@PROPERTY
@given(sizes=st.lists(st.integers(3, 6), min_size=8, max_size=10))
def test_property_verdict_monotone_in_the_effect(sizes: list[int]) -> None:
    total = sum(sizes)
    previous = [(n - n // 2, n // 2, 0) for n in sizes]
    base = sum(n - n // 2 for n in sizes)
    ranks: list[int] = []
    p_values: list[float] = []
    # Effects from zero (current mirrors previous) up to every current row positive.
    for flipped in [*range(base, total, max(1, (total - base) // 5)), total]:
        remaining = flipped
        current: list[tuple[int, int, int]] = []
        for n in sizes:
            pos = min(n, remaining)
            remaining -= pos
            current.append((pos, n - pos, 0))
        rows = brand_rows("Nubank", (current, previous), "n") + healthy_brand("Inter")
        wow = compute(rows).sentiment[0].wow
        assert wow.verdict != "ABSTAIN" and wow.p_raw is not None
        ranks.append(RANK[wow.verdict])
        p_values.append(wow.p_raw)
    assert ranks == sorted(ranks)
    assert p_values == sorted(p_values, reverse=True)
    assert ranks[0] == RANK["NO_CHANGE_DETECTED"] and ranks[-1] == RANK["SIGNIFICANT"]


@PROPERTY
@given(spec=period_spec, other=period_spec)
def test_property_self_delta_is_exactly_zero(spec: Any, other: Any) -> None:
    """The same clusters in both periods: every delta is 0.0 in every draw."""
    rows = mirrored_brand("Nubank", spec, tag="self") + mirrored_brand("Inter", other, tag="o")
    result = compute(rows)
    for wow in (result.sentiment[0].wow, result.share_of_voice[0].wow):
        assert wow.delta == 0.0 and wow.ci95 == (0.0, 0.0) and wow.p_raw == 1.0
        assert wow.verdict == "NO_CHANGE_DETECTED"
    assert result.sentiment[0].wow.ci95_confirmed_only == (0.0, 0.0)


small_period = st.lists(cluster_spec, min_size=1, max_size=8)


@PROPERTY
@given(current=small_period, previous=small_period)
def test_property_abstention_below_minimums(current: Any, previous: Any) -> None:
    rows = brand_rows("Nubank", (current, previous), "n") + healthy_brand("Inter")
    result = compute(rows)
    sent = result.sentiment[0]
    sov = result.share_of_voice[0]
    expected_below = any(
        len(spec) < config.MIN_CLUSTERS_PER_WEEK
        or sum(map(sum, spec)) < config.MIN_MENTIONS_PER_WEEK
        for spec in (current, previous)
    )
    assert sent.wow.is_below_minimum == expected_below
    assert (sov.share is None) == expected_below and (sent.net is None) == expected_below
    below = [a for a in result.abstentions if a.brand == "Nubank" and a.reason == "below_minimum"]
    assert (len(below) == 2) == expected_below
    assert result.sentiment[1].wow.verdict != "ABSTAIN"
    assemble_digest(result, [])
