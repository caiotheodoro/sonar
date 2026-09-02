"""Adapter tests for the two review-site sources: Google Maps and Facebook.

Both adapters are exercised on a hand-built sample payload under
``tests/fixtures/samples/`` (marked ``SAMPLE-hand-built-`` in the filename; the
recorded fixtures land with W3.7) and on a mutated copy that must raise
``AdapterSchemaError``.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sonar.config import SOURCE_PLAN
from sonar.models import Mention, Query, author_hash_for, mention_id_for
from sonar.providers import facebook, google_maps
from sonar.providers.base import AdapterSchemaError, Provider
from sonar.providers.registry import PROVIDERS

SAMPLES = Path(__file__).parent / "fixtures" / "samples"
GMAPS_SAMPLE = SAMPLES / "SAMPLE-hand-built-apify_google-maps-reviews-scraper_nubank.json"
FB_SAMPLE = SAMPLES / "SAMPLE-hand-built-apify_facebook-reviews-scraper_nubank.json"

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
WINDOW_START = "2026-08-19"


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


@pytest.fixture
def gmaps_raw() -> dict[str, Any]:
    return _load(GMAPS_SAMPLE)


@pytest.fixture
def fb_raw() -> dict[str, Any]:
    return _load(FB_SAMPLE)


def _query(profile: str = "full", aliases: list[str] | None = None) -> Query:
    return Query(brand="Nubank", brand_aliases=aliases or [], profile=profile)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- registry


class TestRegistry:
    @pytest.mark.parametrize(
        ("source", "module", "endpoint"),
        [
            ("google_maps", google_maps, "/compass/google-maps-reviews-scraper"),
            ("facebook", facebook, "/apify/facebook-reviews-scraper"),
        ],
    )
    def test_registered_and_available(self, source: str, module: Any, endpoint: str) -> None:
        provider = PROVIDERS[source]
        assert provider is module.PROVIDER
        assert isinstance(provider, Provider)
        assert provider.source == source
        assert provider.endpoint == endpoint
        assert provider.endpoint == SOURCE_PLAN[source].endpoint  # type: ignore[index]
        assert provider.available is True
        assert provider.unavailable_reason is None


# --------------------------------------------------------------------------- google maps: input


class TestGoogleMapsBuildInput:
    def test_exact_input_shape_full(self) -> None:
        payload = google_maps.PROVIDER.build_input(_query("full"), now=NOW)
        assert payload == {
            "startUrls": [{"url": "https://www.google.com/maps/search/Nubank"}],
            "maxReviews": 50,
            "reviewsSort": "newest",
            "reviewsStartDate": WINDOW_START,
        }

    @pytest.mark.parametrize(("profile", "cap"), [("smoke", 50), ("lite", 25), ("full", 50)])
    def test_max_reviews_always_set_from_config(self, profile: str, cap: int) -> None:
        payload = google_maps.PROVIDER.build_input(_query(profile), now=NOW)
        assert payload["maxReviews"] == cap == SOURCE_PLAN["google_maps"].caps[profile]  # type: ignore[index]

    def test_search_url_is_percent_encoded(self) -> None:
        query = Query(brand="Banco do Brasil", profile="full")
        payload = google_maps.PROVIDER.build_input(query, now=NOW)
        assert payload["startUrls"] == [
            {"url": "https://www.google.com/maps/search/Banco%20do%20Brasil"}
        ]

    def test_competitor_brand_overrides_query_brand(self) -> None:
        query = Query(brand="Nubank", competitors=["Inter"], profile="full")
        payload = google_maps.PROVIDER.build_input(query, brand="Inter", now=NOW)
        assert payload["startUrls"] == [{"url": "https://www.google.com/maps/search/Inter"}]

    def test_start_date_follows_window_days(self) -> None:
        payload = google_maps.PROVIDER.build_input(_query("full"), now=NOW)
        assert payload["reviewsStartDate"] == "2026-08-19"

    def test_unit_cost_matches_config(self) -> None:
        plan = SOURCE_PLAN["google_maps"]
        assert google_maps.PROVIDER.unit_cost(10) == pytest.approx(10 * plan.per_result_usd)
        assert google_maps.PROVIDER.unit_cost(0) == pytest.approx(0.0)


# --------------------------------------------------------------------------- google maps: parse


class TestGoogleMapsParse:
    def test_parses_sample_into_mentions(self, gmaps_raw: dict[str, Any]) -> None:
        mentions = google_maps.PROVIDER.parse(
            gmaps_raw, "run_sample_gmaps_0001", "Nubank", local_seq=3
        )
        assert all(isinstance(m, Mention) for m in mentions)
        # item 2 has text null (rating-only review) and is skipped, not an error
        assert [m.raw_ref for m in mentions] == ["3#0", "3#1", "3#3"]
        assert {m.source for m in mentions} == {"google_maps"}
        assert {m.brand for m in mentions} == {"Nubank"}
        assert {m.run_id for m in mentions} == {"run_sample_gmaps_0001"}

    def test_fields_of_first_item(self, gmaps_raw: dict[str, Any]) -> None:
        first = google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1)[0]
        item = gmaps_raw["output"][0]
        assert first.native_id == item["reviewId"]
        assert first.mention_id == mention_id_for("google_maps", item["reviewId"])
        assert first.rating == 5
        assert first.published_at == datetime(2026, 8, 28, 14, 3, 11, tzinfo=UTC)
        assert first.engagement == {"likes": 3}
        assert first.text == item["text"]
        assert first.lang == "pt"
        assert first.matched_terms == ["nubank"]
        assert first.url is not None
        assert "utm_source" not in first.url

    def test_author_handle_is_hashed_never_stored(self, gmaps_raw: dict[str, Any]) -> None:
        mentions = google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1)
        first = mentions[0]
        assert first.author_hash == author_hash_for("google_maps", "104839203847561203948")
        # the public review permalink embeds the reviewer id; every other field must not
        dumped = json.dumps([m.model_dump(mode="json", exclude={"url"}) for m in mentions])
        assert "Ana Paula" not in dumped
        assert "104839203847561203948" not in dumped

    def test_author_falls_back_to_name_when_reviewer_id_null(
        self, gmaps_raw: dict[str, Any]
    ) -> None:
        last = google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1)[-1]
        assert last.author_hash == author_hash_for("google_maps", "Rafael T.")

    def test_cluster_key_is_mention_id(self, gmaps_raw: dict[str, Any]) -> None:
        for m in google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1):
            assert m.cluster_key == m.mention_id
            assert google_maps.PROVIDER.cluster_key(m) == m.mention_id

    def test_missing_optional_fields_do_not_raise(self, gmaps_raw: dict[str, Any]) -> None:
        last = google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1)[-1]
        assert last.published_at is None
        assert last.url is None
        assert last.rating == 3

    def test_place_title_carries_brand_when_text_does_not(
        self, gmaps_raw: dict[str, Any]
    ) -> None:
        second = google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank", local_seq=1)[1]
        assert "nubank" not in second.text.lower()
        assert second.matched_terms == ["nubank"]
        assert second.lang == "en"

    def test_item_matching_neither_text_nor_title_is_dropped(
        self, gmaps_raw: dict[str, Any]
    ) -> None:
        raw = copy.deepcopy(gmaps_raw)
        for item in raw["output"]:
            item["title"] = "Some Other Place"
        mentions = google_maps.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)
        assert [m.raw_ref for m in mentions] == ["1#0"]

    def test_aliases_extend_matched_terms(self, gmaps_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(gmaps_raw)
        raw["output"][0]["text"] = "O roxinho resolveu tudo em um minuto."
        first = google_maps.PROVIDER.parse(
            raw, "run_x", "Nubank", local_seq=1, terms=["Nubank", "roxinho"]
        )[0]
        assert first.matched_terms == ["roxinho"]

    def test_accepts_bare_item_list(self, gmaps_raw: dict[str, Any]) -> None:
        bare: list[dict[str, Any]] = gmaps_raw["output"]
        mentions = google_maps.PROVIDER.parse(bare, "run_x", "Nubank", local_seq=1)
        assert len(mentions) == 3


class TestGoogleMapsSchemaDrift:
    @pytest.mark.parametrize("field", ["reviewId", "text", "stars", "publishedAtDate"])
    def test_missing_required_field_raises(self, gmaps_raw: dict[str, Any], field: str) -> None:
        raw = copy.deepcopy(gmaps_raw)
        del raw["output"][0][field]
        with pytest.raises(AdapterSchemaError) as info:
            google_maps.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)
        assert info.value.provider == "apify"
        assert info.value.endpoint == "/compass/google-maps-reviews-scraper"
        assert field in info.value.detail

    def test_no_item_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            google_maps.PROVIDER.parse({"status": "SUCCEEDED"}, "run_x", "Nubank", local_seq=1)

    def test_non_object_item_raises(self, gmaps_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(gmaps_raw)
        raw["output"][1] = "not an object"
        with pytest.raises(AdapterSchemaError):
            google_maps.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)

    def test_bad_timestamp_raises(self, gmaps_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(gmaps_raw)
        raw["output"][0]["publishedAtDate"] = "yesterday"
        with pytest.raises(AdapterSchemaError):
            google_maps.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)

    def test_missing_local_seq_is_a_caller_error(self, gmaps_raw: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            google_maps.PROVIDER.parse(gmaps_raw, "run_x", "Nubank")

    def test_nested_item_list_is_found(self, gmaps_raw: dict[str, Any]) -> None:
        nested = {"output": {"items": gmaps_raw["output"]}}
        assert len(google_maps.PROVIDER.parse(nested, "run_x", "Nubank", local_seq=1)) == 3

    def test_out_of_range_stars_raises(self, gmaps_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(gmaps_raw)
        raw["output"][0]["stars"] = 7
        with pytest.raises(AdapterSchemaError):
            google_maps.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)


# --------------------------------------------------------------------------- facebook: input


class TestFacebookBuildInput:
    def test_exact_input_shape_full(self) -> None:
        payload = facebook.PROVIDER.build_input(_query("full"), now=NOW)
        assert payload == {
            "startUrls": [{"url": "https://www.facebook.com/nubank/reviews"}],
            "resultsLimit": 30,
            "onlyReviewsNewerThan": WINDOW_START,
        }

    @pytest.mark.parametrize(("profile", "cap"), [("lite", 15), ("full", 30)])
    def test_results_limit_from_config(self, profile: str, cap: int) -> None:
        payload = facebook.PROVIDER.build_input(_query(profile), now=NOW)
        assert payload["resultsLimit"] == cap == SOURCE_PLAN["facebook"].caps[profile]  # type: ignore[index]

    def test_profile_without_facebook_cap_refuses(self) -> None:
        with pytest.raises(ValueError, match="smoke"):
            facebook.PROVIDER.build_input(_query("smoke"), now=NOW)

    def test_page_url_derived_from_first_alias(self) -> None:
        query = Query(brand="Nu Pagamentos S.A.", brand_aliases=["Nubank"], profile="full")
        payload = facebook.PROVIDER.build_input(query, now=NOW)
        assert payload["startUrls"] == [{"url": "https://www.facebook.com/nubank/reviews"}]

    def test_alias_that_is_a_facebook_url_is_used_directly(self) -> None:
        query = Query(
            brand="Nubank",
            brand_aliases=["https://www.facebook.com/NubankBrasil/"],
            profile="full",
        )
        payload = facebook.PROVIDER.build_input(query, now=NOW)
        assert payload["startUrls"] == [
            {"url": "https://www.facebook.com/NubankBrasil/reviews"}
        ]

    def test_competitor_uses_its_own_name(self) -> None:
        query = Query(brand="Nubank", competitors=["Banco Inter"], profile="full")
        payload = facebook.PROVIDER.build_input(query, brand="Banco Inter", now=NOW)
        assert payload["startUrls"] == [{"url": "https://www.facebook.com/bancointer/reviews"}]

    def test_unit_cost_matches_config(self) -> None:
        plan = SOURCE_PLAN["facebook"]
        expected = 10 * plan.per_result_usd + plan.per_call_usd
        assert facebook.PROVIDER.unit_cost(10) == pytest.approx(expected)
        assert facebook.PROVIDER.unit_cost(0) == pytest.approx(plan.per_call_usd)


# --------------------------------------------------------------------------- facebook: parse


class TestFacebookParse:
    def test_parses_sample_into_mentions(self, fb_raw: dict[str, Any]) -> None:
        mentions = facebook.PROVIDER.parse(fb_raw, "run_sample_fb_0001", "Nubank", local_seq=7)
        assert all(isinstance(m, Mention) for m in mentions)
        # item 2 has text null and is skipped
        assert [m.raw_ref for m in mentions] == ["7#0", "7#1", "7#3"]
        assert {m.source for m in mentions} == {"facebook"}

    def test_is_recommended_maps_to_rating_per_oq3(self, fb_raw: dict[str, Any]) -> None:
        mentions = facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1)
        assert [m.rating for m in mentions] == [5, 1, None]

    def test_fields_of_first_item(self, fb_raw: dict[str, Any]) -> None:
        first = facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1)[0]
        item = fb_raw["output"][0]
        assert first.native_id == item["id"]
        assert first.mention_id == mention_id_for("facebook", item["id"])
        assert first.published_at == datetime(2026, 8, 30, 11, 12, 13, tzinfo=UTC)
        assert first.engagement == {"likes": 12, "comments": 2}
        assert first.url == "https://www.facebook.com/nubank/posts/1029384756102938"
        assert first.lang == "pt"
        assert first.matched_terms == ["nubank"]

    def test_author_handle_is_hashed_never_stored(self, fb_raw: dict[str, Any]) -> None:
        mentions = facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1)
        assert mentions[0].author_hash == author_hash_for("facebook", "100004455667788")
        assert mentions[-1].author_hash == author_hash_for("facebook", "Pedro")
        dumped = json.dumps([m.model_dump(mode="json") for m in mentions])
        assert "Juliana" not in dumped
        assert "100004455667788" not in dumped

    def test_cluster_key_is_mention_id(self, fb_raw: dict[str, Any]) -> None:
        for m in facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1):
            assert m.cluster_key == m.mention_id
            assert facebook.PROVIDER.cluster_key(m) == m.mention_id

    def test_mention_id_falls_back_to_url_then_text(self, fb_raw: dict[str, Any]) -> None:
        mentions = facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1)
        second = mentions[1]
        assert second.native_id is not None
        last = mentions[-1]
        assert last.native_id is None
        assert last.url is None
        assert last.published_at is None
        assert last.mention_id == mention_id_for("facebook", "cartão chegou em três dias.")

    def test_page_name_carries_brand_when_text_does_not(self, fb_raw: dict[str, Any]) -> None:
        second = facebook.PROVIDER.parse(fb_raw, "run_x", "Nubank", local_seq=1)[1]
        assert "nubank" not in second.text.lower()
        assert second.matched_terms == ["nubank"]
        assert second.lang == "en"

    def test_item_matching_neither_text_nor_page_is_dropped(self, fb_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(fb_raw)
        for item in raw["output"]:
            item["pageName"] = "Another Page"
        mentions = facebook.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)
        assert [m.raw_ref for m in mentions] == ["1#0"]


class TestFacebookSchemaDrift:
    @pytest.mark.parametrize("field", ["text", "date", "isRecommended"])
    def test_missing_required_field_raises(self, fb_raw: dict[str, Any], field: str) -> None:
        raw = copy.deepcopy(fb_raw)
        del raw["output"][0][field]
        with pytest.raises(AdapterSchemaError) as info:
            facebook.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)
        assert info.value.provider == "apify"
        assert info.value.endpoint == "/apify/facebook-reviews-scraper"
        assert field in info.value.detail

    def test_no_item_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            facebook.PROVIDER.parse({"status": "SUCCEEDED"}, "run_x", "Nubank", local_seq=1)

    def test_non_boolean_is_recommended_raises(self, fb_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(fb_raw)
        raw["output"][0]["isRecommended"] = "yes"
        with pytest.raises(AdapterSchemaError):
            facebook.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)

    def test_bad_timestamp_raises(self, fb_raw: dict[str, Any]) -> None:
        raw = copy.deepcopy(fb_raw)
        raw["output"][0]["date"] = "last week"
        with pytest.raises(AdapterSchemaError):
            facebook.PROVIDER.parse(raw, "run_x", "Nubank", local_seq=1)
