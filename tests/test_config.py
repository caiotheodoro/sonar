"""Every threshold in the PRE-REGISTRATION index equals its config constant.

The doc is read at run time, so the version line is checked for shape and
floor (1.1.0 carried amendments A1/A2, D012) rather than a hardcoded string:
a later patch amendment must not turn this gate red on its own.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from sonar import config
from sonar.report.incumbent import BRAND24_TEAM

PRE_REG = Path(__file__).resolve().parents[1] / "docs" / "PRE-REGISTRATION.md"


def threshold_index() -> str:
    text = PRE_REG.read_text(encoding="utf-8")
    match = re.search(r"## Threshold index\n(.*)\Z", text, flags=re.DOTALL)
    assert match is not None, "PRE-REGISTRATION.md has no '## Threshold index' section"
    return match.group(1)


def number(pattern: str, text: str) -> float:
    match = re.search(pattern, text)
    assert match is not None, f"pattern {pattern!r} not found in threshold index"
    return float(match.group(1))


INDEX = threshold_index()


@pytest.mark.parametrize(
    ("pattern", "constant"),
    [
        (r"(\d+) %, B=", config.CI_LEVEL * 100),
        (r"B=(\d+) live", config.B_LIVE),
        (r"B=(\d+) frozen demo", config.B_FROZEN_DEMO),
        (r"seed (\d+)", config.SEED),
        (r"α=([\d.]+) \(Holm\)", config.HOLM_ALPHA),
        (r"n_clusters < (\d+)", config.MIN_CLUSTERS_PER_WEEK),
        (r"n < (\d+) in either period", config.MIN_MENTIONS_PER_WEEK),
        (r"n_day ≥ max\((\d+), median", config.EVENT_MIN_COUNT),
        (r"median \+ (\d+)·MAD", config.EVENT_MAD_MULTIPLIER),
        (r"n_clusters_day ≥ (\d+)", config.EVENT_MIN_CLUSTERS),
        (r"(\d+)-day baseline", config.EVENT_BASELINE_DAYS),
        (r"confidence < ([\d.]+)", config.TIEBREAK_CONFIDENCE_THRESHOLD),
        (r"cap (\d+) %", config.TIEBREAK_CAP_FRACTION * 100),
        (r"audit (\d+) %", config.AUDIT_SAMPLE_FRACTION * 100),
        (r"H1: < \$([\d.]+)", config.H1_MAX_TOTAL_USD),
        (r"H2: ≥ ([\d.]+)", config.H2_MIN_DESIGN_EFFECT),
        (r"H3: ≥ ([\d.]+)", config.H3_MIN_AGREEMENT),
        (r"H4: > \$([\d.]+)", config.H4_MIN_TOTAL_USD_EXCLUSIVE),
        (r"H5: ≥ ([\d.]+) on", config.H5_MIN_AGREEMENT),
        (r"on (\d+) labels", config.H5_N_LABELS),
        (r"distance cut ([\d.]+)", config.TOPIC_DISTANCE_THRESHOLD),
        (r"min_size (\d+)", config.TOPIC_MIN_SIZE),
        (r"min_breadth (\d+)", config.TOPIC_MIN_BREADTH),
    ],
)
def test_threshold_index_matches_constant(pattern: str, constant: float) -> None:
    assert number(pattern, INDEX) == pytest.approx(constant)


def test_threshold_index_mapping_covers_every_constant() -> None:
    expected = {
        "ci_level": 0.95,
        "b_live": 2000,
        "b_frozen_demo": 10000,
        "seed": 777,
        "holm_alpha": 0.05,
        "min_clusters_per_week": 5,
        "min_mentions_per_week": 20,
        "event_min_count": 5,
        "event_mad_multiplier": 3.0,
        "event_min_clusters": 3,
        "event_baseline_days": 14,
        "tiebreak_confidence_threshold": 0.6,
        "tiebreak_cap_fraction": 0.40,
        "audit_sample_fraction": 0.10,
        "h1_max_total_usd": 5.0,
        "h2_min_design_effect": 1.5,
        "h3_min_agreement": 0.85,
        "h4_min_total_usd_exclusive": 0.0,
        "h5_min_agreement": 0.85,
        "h5_n_labels": 50,
        "topic_distance_threshold": 0.35,
        "topic_min_size": 3,
        "topic_min_breadth": 2,
    }
    assert dict(config.THRESHOLD_INDEX) == expected
    assert config.B == config.B_LIVE


def pre_registration_version() -> tuple[int, int, int]:
    """Semver of the frozen doc, read from its ``**Version**`` line at run time."""
    text = PRE_REG.read_text(encoding="utf-8")
    match = re.search(r"^\*\*Version\*\*: (\d+)\.(\d+)\.(\d+)$", text, flags=re.MULTILINE)
    assert match is not None, "PRE-REGISTRATION.md has no '**Version**: X.Y.Z' line"
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def test_pre_registration_frozen_banner_and_version() -> None:
    text = PRE_REG.read_text(encoding="utf-8")
    assert "FROZEN TEXT" in text
    assert "**Frozen**: 2026-09-02" in text
    # A1/A2 (D012) landed in 1.1.0, A3 (D013) in 1.1.1 and A4 (D014) in 1.1.2;
    # anything older predates the wording and thresholds this file checks.
    assert pre_registration_version() >= (1, 1, 2)
    assert "**Amended**: 2026-09-02, A1, A2, A3 and A4" in text


# --- source plan ----------------------------------------------------------


def test_source_plan_has_exactly_the_ten_contract_sources() -> None:
    assert tuple(config.SOURCE_PLAN) == config.SOURCES
    assert len(config.SOURCES) == 10
    assert "x" not in config.SOURCE_PLAN
    for name, plan in config.SOURCE_PLAN.items():
        assert plan.source == name
        assert set(plan.caps) == {"smoke", "lite", "full"}


def test_cluster_rules_follow_contracts_table() -> None:
    rules = {s: p.cluster_rule for s, p in config.SOURCE_PLAN.items()}
    assert rules == {
        "reddit": "post_id",
        "youtube_comment": "video_id",
        "tiktok": "author_hash",
        "instagram": "author_hash",
        "youtube": "mention_id",
        "google_maps": "mention_id",
        "facebook": "mention_id",
        "trustpilot": "mention_id",
        "g2": "mention_id",
        "news": "mention_id",
    }


def test_rating_and_timestamp_flags_follow_contracts() -> None:
    rated = {s for s, p in config.SOURCE_PLAN.items() if p.has_rating}
    assert rated == set(config.REVIEW_SOURCES) == {"google_maps", "facebook", "trustpilot", "g2"}
    no_ts = {s for s, p in config.SOURCE_PLAN.items() if not p.has_timestamps}
    assert no_ts == {"youtube_comment", "instagram"}
    assert config.COMMENT_SOURCES == {"reddit", "youtube_comment", "tiktok", "instagram"}


def test_endpoint_reference_prices_and_full_caps() -> None:
    plan = config.SOURCE_PLAN
    assert (plan["reddit"].per_result_usd, plan["reddit"].per_call_usd) == (0.0057, 0.02)
    assert plan["youtube"].per_result_usd == 0.0045
    assert plan["youtube_comment"].per_result_usd == 0.00225
    assert plan["tiktok"].per_result_usd == 0.00045
    assert plan["instagram"].per_call_usd == 0.00345
    assert plan["google_maps"].per_result_usd == 0.000675
    assert (plan["facebook"].per_result_usd, plan["facebook"].per_call_usd) == (0.003, 0.001)
    assert (plan["trustpilot"].per_call_usd, plan["trustpilot"].lookup_usd) == (0.03, 0.03)
    assert (plan["g2"].per_call_usd, plan["g2"].lookup_usd) == (0.05, 0.02)
    assert plan["news"].estimate_usd("full") == 0.0
    full_caps = {s: p.caps["full"] for s, p in plan.items()}
    assert full_caps == {
        "reddit": 40,
        "youtube": 10,
        "youtube_comment": 60,
        "tiktok": 40,
        "instagram": 30,
        "google_maps": 50,
        "facebook": 30,
        "trustpilot": 1,
        "g2": 1,
        "news": 3,
    }


def test_profiles_match_pipeline_rules() -> None:
    smoke, lite, full = (config.PROFILES[p] for p in ("smoke", "lite", "full"))
    assert smoke.sources == ("reddit", "google_maps")
    assert smoke.max_competitors == 0
    assert lite.sources == full.sources == config.SOURCES
    assert (lite.max_competitors, full.max_competitors) == (1, 3)
    assert config.MAX_COMPETITORS == 3
    for source in config.SOURCES:
        plan = config.SOURCE_PLAN[source]
        assert plan.caps["smoke"] == (plan.caps["full"] if source in smoke.sources else 0)
        assert 0 < plan.caps["lite"] <= plan.caps["full"]
    # Design estimates: ≈ $0.7 per brand full (≈ $2.8 for brand + 3), ≈ $0.3 smoke.
    assert full.estimate_usd_per_brand() == pytest.approx(0.704, abs=0.01)
    assert full.estimate_usd(4) == pytest.approx(2.8, abs=0.05)
    assert smoke.estimate_usd(1) == pytest.approx(0.3, abs=0.03)
    assert lite.estimate_usd_per_brand() < full.estimate_usd_per_brand()
    assert all(p.resamples == config.B_LIVE for p in config.PROFILES.values())


# --- LLM ------------------------------------------------------------------


def test_llm_defaults_and_env_overrides() -> None:
    default = config.resolve_llm({})
    assert default.classifier_model == "gpt-5.6-luna"
    assert default.tiebreak_model == "gpt-5.6-terra"
    assert default.embedding_model == config.EMBEDDING_MODEL_DEFAULT
    assert default["classifier_model"] == default.classifier_model
    overridden = config.resolve_llm(
        {
            "SONAR_CLASSIFIER_MODEL": "alt-classifier",
            "SONAR_TIEBREAK_MODEL": "alt-tiebreak",
            "SONAR_EMBEDDING_MODEL": "alt-embedding",
        }
    )
    assert overridden == config.LlmModels("alt-classifier", "alt-tiebreak", "alt-embedding")
    assert config.resolve_llm({"SONAR_CLASSIFIER_MODEL": "  "}) == default


def test_llm_rates_dated_and_priced_per_decisions_d003() -> None:
    assert config.LLM_RATES_CHECKED_AT == date(2026, 9, 2)
    luna = config.LLM_RATES["gpt-5.6-luna"]
    terra = config.LLM_RATES["gpt-5.6-terra"]
    assert (luna.input_usd_per_mtok, luna.output_usd_per_mtok) == (0.20, 1.20)
    assert (terra.input_usd_per_mtok, terra.output_usd_per_mtok) == (2.00, 12.00)
    assert config.EMBEDDING_MODEL_DEFAULT in config.LLM_RATES
    assert config.llm_cost_usd("gpt-5.6-luna", 1_000_000, 1_000_000) == pytest.approx(1.40)
    assert config.llm_cost_usd("gpt-5.6-terra", 500_000) == pytest.approx(1.00)
    with pytest.raises(KeyError):
        config.llm_cost_usd("not-a-model", 1)
    assert config.PROMPT_REV


# --- incumbent ------------------------------------------------------------


def test_incumbent_constant_matches_contracts_and_readme() -> None:
    assert BRAND24_TEAM.name == "Brand24 Team"
    assert BRAND24_TEAM.price_usd_month == 349
    assert BRAND24_TEAM.url == "https://brand24.com/prices"
    assert BRAND24_TEAM.checked_at == date(2026, 9, 2)
    assert BRAND24_TEAM.mentions_quota == 10000
    assert BRAND24_TEAM.to_record()["checked_at"] == "2026-09-02"
    readme = (PRE_REG.parents[1] / "README.md").read_text(encoding="utf-8")
    assert "$349 per month" in readme
    assert "checked 2026-09-02" in readme
    assert config.BRIEFS_PER_MONTH_ASSUMED == 4
