"""TikTok and Instagram adapters (W3.3) on hand-built sample payloads.

The samples under ``tests/fixtures/samples/`` are marked SAMPLE in their
filename; they stand in until W3.7 records real payloads. Every assertion
that depends on a field name is therefore a statement about the adapter's
expected schema, to be re-checked against the recorded fixture.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sonar import config
from sonar.models import Mention, Query, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError, Provider
from sonar.providers.instagram import PROVIDER as INSTAGRAM
from sonar.providers.instagram import InstagramProvider
from sonar.providers.registry import PROVIDERS
from sonar.providers.tiktok import PROVIDER as TIKTOK
from sonar.providers.tiktok import TikTokProvider

SAMPLES = Path(__file__).resolve().parent / "fixtures" / "samples"
TIKTOK_SAMPLE = SAMPLES / "SAMPLE-hand-built-tiktok_tiktok-scraper_nubank.json"
INSTAGRAM_SAMPLE = SAMPLES / "SAMPLE-hand-built-instagram_instagram-hashtag-scraper_nubank.json"
LOCAL_SEQ = 7
TERMS = ["Nubank", "Nu bank", "Nu"]


def load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def query(profile: str = "full", **overrides: Any) -> Query:
    base: dict[str, Any] = {
        "brand": "Nubank",
        "brand_aliases": ["Nu bank", "Nu"],
        "profile": profile,
    }
    base.update(overrides)
    return Query.model_validate(base)


@pytest.fixture
def tiktok_raw() -> dict[str, Any]:
    return load(TIKTOK_SAMPLE)


@pytest.fixture
def instagram_raw() -> dict[str, Any]:
    return load(INSTAGRAM_SAMPLE)


# --------------------------------------------------------------------------- registry


@pytest.mark.parametrize(
    ("provider", "source", "endpoint"),
    [
        (TIKTOK, "tiktok", "/apidojo/tiktok-scraper"),
        (INSTAGRAM, "instagram", "/apify/instagram-hashtag-scraper"),
    ],
)
def test_registered_and_available(
    provider: Provider, source: config.SourceName, endpoint: str
) -> None:
    assert PROVIDERS[source] is provider
    assert isinstance(provider, Provider)
    assert provider.source == source
    assert provider.endpoint == endpoint
    assert provider.endpoint == config.SOURCE_PLAN[source].endpoint
    assert provider.available is True
    assert provider.unavailable_reason is None


def test_wow_scope_follows_config_timestamps() -> None:
    assert TIKTOK.wow_scope is True
    assert INSTAGRAM.wow_scope is False
    assert config.SOURCE_PLAN["instagram"].has_timestamps is False


# --------------------------------------------------------------------------- build_input


def test_tiktok_build_input_full() -> None:
    assert TIKTOK.build_input(query("full")) == {
        "keywords": ["Nubank", "Nu bank", "Nu"],
        "maxItems": config.SOURCE_PLAN["tiktok"].caps["full"],
        "dateRange": "THIS_MONTH",
    }


def test_tiktok_build_input_lite_uses_lite_cap() -> None:
    assert (
        TIKTOK.build_input(query("lite"))["maxItems"] == config.SOURCE_PLAN["tiktok"].caps["lite"]
    )


def test_tiktok_build_input_smoke_is_refused() -> None:
    with pytest.raises(ValueError, match="smoke"):
        TIKTOK.build_input(query("smoke", sources=["reddit"]))


def test_instagram_build_input_derives_hashtags_from_aliases() -> None:
    assert INSTAGRAM.build_input(query("full")) == {
        "hashtags": ["nubank", "nu"],
        "resultsLimit": config.SOURCE_PLAN["instagram"].caps["full"],
    }


def test_instagram_build_input_lite_cap_and_accented_alias() -> None:
    payload = INSTAGRAM.build_input(query("lite", brand_aliases=["Nu Bank S.A.", "Ação Nu"]))
    assert payload == {
        "hashtags": ["nubank", "nubanksa", "açãonu"],
        "resultsLimit": config.SOURCE_PLAN["instagram"].caps["lite"],
    }


def test_instagram_build_input_smoke_is_refused() -> None:
    with pytest.raises(ValueError, match="smoke"):
        INSTAGRAM.build_input(query("smoke", sources=["reddit"]))


def test_build_input_accepts_mapping_query() -> None:
    mapping = {"brand": "Nubank", "brand_aliases": ["Nu"], "profile": "full"}
    assert TIKTOK.build_input(mapping)["keywords"] == ["Nubank", "Nu"]
    assert INSTAGRAM.build_input(mapping)["hashtags"] == ["nubank", "nu"]


# --------------------------------------------------------------------------- parse: tiktok


def test_tiktok_parse_sample(tiktok_raw: dict[str, Any]) -> None:
    mentions = TIKTOK.parse(
        tiktok_raw, "run_sample_tiktok_0001", "Nubank", local_seq=LOCAL_SEQ, terms=TERMS
    )
    assert all(isinstance(m, Mention) for m in mentions)
    assert [m.raw_ref for m in mentions] == ["7#0", "7#1", "7#3"]
    assert all(m.source == "tiktok" and m.brand == "Nubank" for m in mentions)
    assert all(m.run_id == "run_sample_tiktok_0001" for m in mentions)
    assert all(m.rating is None for m in mentions)

    first = mentions[0]
    assert first.native_id == "7350012345678901234"
    assert first.mention_id == mention_id_for("tiktok", "7350012345678901234")
    assert first.text.startswith("Troquei de banco pro Nubank")
    assert first.published_at == datetime(2026, 8, 30, 10, 40, 0, tzinfo=UTC)
    assert first.url == "https://www.tiktok.com/@maria.finance/video/7350012345678901234"
    assert first.author_hash == author_hash_for("tiktok", "maria.finance")
    assert first.cluster_key == first.author_hash
    assert first.engagement == {"views": 15400, "likes": 1200, "comments": 38, "shares": 12}
    assert first.matched_terms == ["nubank"]
    assert first.lang == "pt"

    second = mentions[1]
    assert second.matched_terms == ["nu bank"]
    assert second.lang == "en"
    assert second.author_hash == author_hash_for("tiktok", "joe_reviews")
    assert second.engagement == {"views": 980, "likes": 44, "comments": 9, "shares": 0}


def test_tiktok_missing_optional_fields_fall_back(tiktok_raw: dict[str, Any]) -> None:
    mentions = TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ, terms=TERMS)
    bare = mentions[2]
    assert bare.raw_ref == "7#3"
    assert bare.author_hash is None
    assert bare.cluster_key == bare.mention_id
    assert bare.published_at is None
    assert bare.engagement == {"likes": 3}
    assert bare.lang == "unknown"


def test_tiktok_cluster_key_matches_parse(tiktok_raw: dict[str, Any]) -> None:
    for mention in TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ, terms=TERMS):
        assert TIKTOK.cluster_key(mention) == mention.cluster_key


def test_tiktok_epoch_fallback_when_formatted_missing(tiktok_raw: dict[str, Any]) -> None:
    item = tiktok_raw["output"][0]
    del item["uploadedAtFormatted"]
    mention = TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ)[0]
    assert mention.published_at == datetime.fromtimestamp(1756550400, tz=UTC)


def test_tiktok_unparseable_timestamp_is_null(tiktok_raw: dict[str, Any]) -> None:
    tiktok_raw["output"][0]["uploadedAtFormatted"] = "yesterday"
    tiktok_raw["output"][0]["uploadedAt"] = "soon"
    assert TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ)[0].published_at is None


def test_tiktok_default_terms_is_brand_only(tiktok_raw: dict[str, Any]) -> None:
    """Without *terms* only the brand string matches; aliases are the caller's to pass."""
    mentions = TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ)
    assert [m.raw_ref for m in mentions] == ["7#0", "7#3"]


def test_tiktok_empty_output_is_empty_not_error() -> None:
    assert TIKTOK.parse({"output": []}, "run", "Nubank", local_seq=1) == []


def test_tiktok_accepts_provider_response_wrapper(tiktok_raw: dict[str, Any]) -> None:
    wrapped = {"providerResponse": {"httpStatus": 200, "data": tiktok_raw["output"]}}
    assert len(TIKTOK.parse(wrapped, "run", "Nubank", local_seq=LOCAL_SEQ, terms=TERMS)) == 3


# --------------------------------------------------------------------------- parse: instagram


def test_instagram_parse_sample(instagram_raw: dict[str, Any]) -> None:
    mentions = INSTAGRAM.parse(
        instagram_raw, "run_sample_instagram_0001", "Nubank", local_seq=3, terms=TERMS
    )
    assert [m.raw_ref for m in mentions] == ["3#0", "3#1", "3#2"]
    assert all(m.source == "instagram" and m.rating is None for m in mentions)

    first = mentions[0]
    assert first.native_id == "3450000000000000001"
    assert first.mention_id == mention_id_for("instagram", "3450000000000000001")
    assert first.text.startswith("Recebi meu cartão roxinho")
    assert first.published_at == datetime(2026, 8, 31, 14, 22, 5, tzinfo=UTC)
    assert first.url == "https://www.instagram.com/p/C9abcDEfGh1"
    assert first.author_hash == author_hash_for("instagram", "ana.souza")
    assert first.cluster_key == first.author_hash
    assert first.engagement == {"likes": 230, "comments": 14}
    assert first.matched_terms == ["nubank"]
    assert first.lang == "pt"

    second = mentions[1]
    assert second.published_at is None, "timestamp absent stays null, never invented"
    assert second.url == "https://www.instagram.com/p/C9xyzABcDe2"
    assert second.cluster_key == first.cluster_key, "same owner, same resampling unit"
    assert second.engagement == {"likes": 41, "comments": 3, "views": 900}
    assert second.matched_terms == ["nu", "nubank"], "alias in body, brand in hashtag"
    assert second.lang == "en"

    third = mentions[2]
    assert third.author_hash is None
    assert third.cluster_key == third.mention_id
    assert third.engagement == {"likes": 5, "comments": 0}


def test_instagram_cluster_key_matches_parse(instagram_raw: dict[str, Any]) -> None:
    for mention in INSTAGRAM.parse(instagram_raw, "run", "Nubank", local_seq=3, terms=TERMS):
        assert INSTAGRAM.cluster_key(mention) == mention.cluster_key


def test_instagram_falls_back_to_shortcode_url_when_url_missing(
    instagram_raw: dict[str, Any],
) -> None:
    del instagram_raw["output"][0]["url"]
    mention = INSTAGRAM.parse(instagram_raw, "run", "Nubank", local_seq=3)[0]
    assert mention.url == "https://www.instagram.com/p/C9abcDEfGh1"


def test_instagram_no_id_uses_shortcode_then_text_key(instagram_raw: dict[str, Any]) -> None:
    item = instagram_raw["output"][0]
    del item["id"]
    mention = INSTAGRAM.parse(instagram_raw, "run", "Nubank", local_seq=3)[0]
    assert mention.native_id == "C9abcDEfGh1"
    del item["shortCode"]
    del item["url"]
    mention = INSTAGRAM.parse(instagram_raw, "run", "Nubank", local_seq=3)[0]
    assert mention.native_id is None
    assert mention.url is None
    assert mention.mention_id == mention_id_for("instagram", mention.text.casefold()[:200])


def test_instagram_empty_output_is_empty_not_error() -> None:
    assert INSTAGRAM.parse({"output": []}, "run", "Nubank", local_seq=1) == []


# --------------------------------------------------------------------------- schema drift


def test_tiktok_mutated_sample_without_text_key_raises(tiktok_raw: dict[str, Any]) -> None:
    mutated = copy.deepcopy(tiktok_raw)
    for item in mutated["output"]:
        del item["title"]
    with pytest.raises(AdapterSchemaError) as info:
        TIKTOK.parse(mutated, "run", "Nubank", local_seq=LOCAL_SEQ)
    assert info.value.provider == "apify"
    assert info.value.endpoint == "/apidojo/tiktok-scraper"
    assert "title" in info.value.detail


def test_tiktok_text_of_wrong_type_raises(tiktok_raw: dict[str, Any]) -> None:
    tiktok_raw["output"][1]["title"] = {"text": "nested"}
    with pytest.raises(AdapterSchemaError):
        TIKTOK.parse(tiktok_raw, "run", "Nubank", local_seq=LOCAL_SEQ)


def test_instagram_mutated_sample_without_caption_raises(instagram_raw: dict[str, Any]) -> None:
    mutated = copy.deepcopy(instagram_raw)
    for item in mutated["output"]:
        del item["caption"]
    with pytest.raises(AdapterSchemaError) as info:
        INSTAGRAM.parse(mutated, "run", "Nubank", local_seq=3)
    assert info.value.provider == "apify"
    assert info.value.endpoint == "/apify/instagram-hashtag-scraper"
    assert "caption" in info.value.detail


@pytest.mark.parametrize("provider", [TIKTOK, INSTAGRAM])
@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"output": "not a list"},
        {"output": [42]},
        {"providerResponse": {"httpStatus": 200}},
    ],
)
def test_payload_without_item_list_raises(
    provider: TikTokProvider | InstagramProvider, raw: dict[str, Any]
) -> None:
    with pytest.raises(AdapterSchemaError):
        provider.parse(raw, "run", "Nubank", local_seq=1)


@pytest.mark.parametrize("provider", [TIKTOK, INSTAGRAM])
def test_parse_requires_local_seq_for_raw_ref(provider: TikTokProvider | InstagramProvider) -> None:
    with pytest.raises(ValueError, match="local_seq"):
        provider.parse({"output": []}, "run", "Nubank")


@pytest.mark.parametrize("provider", [TIKTOK, INSTAGRAM])
def test_parse_reads_local_seq_from_payload(provider: TikTokProvider | InstagramProvider) -> None:
    assert provider.parse({"output": [], "local_seq": 2}, "run", "Nubank") == []


# --------------------------------------------------------------------------- unit cost


def test_tiktok_unit_cost_is_per_result() -> None:
    plan = config.SOURCE_PLAN["tiktok"]
    assert TIKTOK.unit_cost(0) == 0.0
    assert TIKTOK.unit_cost(1) == pytest.approx(plan.per_result_usd)
    assert TIKTOK.unit_cost(40) == pytest.approx(plan.estimate_usd("full"))


def test_instagram_unit_cost_is_per_call() -> None:
    plan = config.SOURCE_PLAN["instagram"]
    assert INSTAGRAM.unit_cost(0) == pytest.approx(plan.per_call_usd)
    assert INSTAGRAM.unit_cost(30) == pytest.approx(plan.per_call_usd)
    assert INSTAGRAM.unit_cost(30) == pytest.approx(plan.estimate_usd("full"))
