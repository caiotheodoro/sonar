"""Tests for Trustpilot and G2 B2B adapters (W3.5).

Each adapter is a two-call pattern: search → reviews.  Tests exercise
``parse_search``, ``parse``, the ``build_input`` state machine and the
``parse`` → ``cluster_key`` chain on sample payloads under
``tests/fixtures/samples/``.  Mutated copies verify that
``AdapterSchemaError`` fires on schema drift and that no raw reviewer name
survives into a ``Mention``.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sonar.models import Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.g2 import G2Provider
from sonar.providers.trustpilot import REVIEWS_SORT, TrustpilotProvider

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "samples"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((_FIXTURES / name).read_text())
    return data


def _query(brand: str = "Nubank") -> Any:
    return type("Q", (), {"brand": brand})()


@pytest.fixture
def tp_search() -> dict[str, Any]:
    return _load("trustpilot_search_companies_sample.json")


@pytest.fixture
def tp_reviews() -> dict[str, Any]:
    return _load("trustpilot_get_company_reviews_sample.json")


@pytest.fixture
def g2_search() -> dict[str, Any]:
    return _load("g2_search_software_sample.json")


@pytest.fixture
def g2_reviews() -> dict[str, Any]:
    return _load("g2_get_product_reviews_sample.json")


# ── Trustpilot ────────────────────────────────────────────────────────


class TestTrustpilotSearch:
    def test_parse_search_returns_domain(self, tp_search: dict[str, Any]) -> None:
        assert TrustpilotProvider().parse_search(tp_search) == "nubank.com.br"

    def test_parse_search_stores_domain(self, tp_search: dict[str, Any]) -> None:
        provider = TrustpilotProvider()
        provider.parse_search(tp_search)
        inp = provider.build_input(_query())
        assert inp["queryParams"]["domain"] == "nubank.com.br"
        assert "query" not in inp["queryParams"]

    def test_parse_search_empty_returns_none(self) -> None:
        assert TrustpilotProvider().parse_search({"companies": []}) is None

    def test_parse_search_missing_key_returns_none(self) -> None:
        assert TrustpilotProvider().parse_search({}) is None

    def test_build_input_search_before_domain(self) -> None:
        inp = TrustpilotProvider().build_input(_query())
        assert inp["queryParams"]["query"] == "Nubank"
        assert inp["queryParams"]["limit"] == 1
        assert "sort" not in inp["queryParams"]

    def test_build_input_reviews_sets_sort(self, tp_search: dict[str, Any]) -> None:
        provider = TrustpilotProvider()
        provider.parse_search(tp_search)
        params = provider.build_input(_query())["queryParams"]
        assert params == {"domain": "nubank.com.br", "page": 1, "sort": REVIEWS_SORT}
        assert REVIEWS_SORT == "recency"

    def test_parse_search_mutation_no_domain_raises(self, tp_search: dict[str, Any]) -> None:
        del tp_search["companies"][0]["domain"]
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse_search(tp_search)

    def test_parse_search_mutation_not_a_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse_search({"companies": "not-a-list"})


class TestTrustpilotReviews:
    def test_parse_returns_mentions(self, tp_reviews: dict[str, Any]) -> None:
        items = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)
        assert len(items) == 2
        assert all(isinstance(m, Mention) for m in items)
        assert [m.raw_ref for m in items] == ["1#0", "1#1"]
        assert {m.source for m in items} == {"trustpilot"}
        assert {m.run_id for m in items} == {"run-001"}
        assert [m.rating for m in items] == [5, 1]

    def test_fields_of_first_item(self, tp_reviews: dict[str, Any]) -> None:
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=7)[0]
        assert first.native_id == "tp-review-001"
        assert first.mention_id == mention_id_for("trustpilot", "tp-review-001")
        assert first.cluster_key == first.mention_id
        assert first.published_at == datetime(2026, 8, 15, 10, 30, tzinfo=UTC)
        assert first.matched_terms == ["nubank"]
        assert first.match_kind == "entity"
        assert first.engagement == {}
        assert first.lang == "en"
        assert first.url == "https://www.trustpilot.com/reviews/nubank.com.br"

    def test_parse_text_joins_title_and_body(self, tp_reviews: dict[str, Any]) -> None:
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.text.startswith("Great digital bank\n\n")
        assert "changed my life" in first.text

    def test_author_is_hashed_never_raw(self, tp_reviews: dict[str, Any]) -> None:
        mentions = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)
        assert mentions[0].author_hash == author_hash_for("trustpilot", "Maria S.")
        assert mentions[1].author_hash == author_hash_for("trustpilot", "João P.")
        dumped = json.dumps([m.model_dump(mode="json") for m in mentions], ensure_ascii=False)
        assert "Maria S." not in dumped
        assert "João P." not in dumped
        assert "author_name" not in dumped

    def test_cluster_key_chains_from_parse(self, tp_reviews: dict[str, Any]) -> None:
        provider = TrustpilotProvider()
        first = provider.parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert provider.cluster_key(first) == mention_id_for("trustpilot", "tp-review-001")

    def test_run_id_none_is_allowed(self, tp_reviews: dict[str, Any]) -> None:
        first = TrustpilotProvider().parse(tp_reviews, None, "Nubank", local_seq=1)[0]
        assert first.run_id is None

    def test_aliases_do_not_change_entity_terms(self, tp_reviews: dict[str, Any]) -> None:
        tp_reviews["reviews"][0]["text"] = "Roxinho is the best card."
        first = TrustpilotProvider().parse(
            tp_reviews, "run-001", "Nubank", local_seq=1, terms=["Nubank", "roxinho"]
        )[0]
        assert first.matched_terms == ["nubank"]
        assert first.match_kind == "entity"

    def test_unmatched_text_is_still_an_entity_match(self, tp_reviews: dict[str, Any]) -> None:
        # D014: the reviews call is scoped to the resolved domain
        tp_reviews["reviews"][0]["title"] = "Fine"
        tp_reviews["reviews"][0]["text"] = "Card arrived in two days."
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.matched_terms == ["nubank"]
        assert first.match_kind == "entity"

    def test_parse_requires_local_seq(self, tp_reviews: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank")

    def test_parse_empty_reviews(self) -> None:
        assert TrustpilotProvider().parse({"reviews": []}, "run-001", "Nubank", local_seq=1) == []

    def test_parse_skips_review_without_text(self, tp_reviews: dict[str, Any]) -> None:
        del tp_reviews["reviews"][0]["title"]
        tp_reviews["reviews"][0]["text"] = None
        items = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)
        assert [m.native_id for m in items] == ["tp-review-002"]
        assert items[0].raw_ref == "1#1"

    def test_parse_mutation_missing_reviews_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse({}, "run-001", "Nubank", local_seq=1)

    def test_parse_mutation_missing_review_id_raises(self, tp_reviews: dict[str, Any]) -> None:
        del tp_reviews["reviews"][0]["reviewId"]
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)

    def test_parse_fallback_id_key(self, tp_reviews: dict[str, Any]) -> None:
        tp_reviews["reviews"][0]["id"] = tp_reviews["reviews"][0].pop("reviewId")
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.native_id == "tp-review-001"

    def test_parse_mutation_non_dict_in_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse({"reviews": ["bad"]}, "run-001", "Nubank", local_seq=1)

    @pytest.mark.parametrize("bad", [True, False, 0, 6, 4.5, "five", [5], {}])
    def test_rating_out_of_range_or_wrong_type_raises(
        self, tp_reviews: dict[str, Any], bad: Any
    ) -> None:
        tp_reviews["reviews"][0]["rating"] = bad
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)

    @pytest.mark.parametrize(("value", "expected"), [(None, None), ("4", 4), (3.0, 3), (2, 2)])
    def test_rating_coercion(
        self, tp_reviews: dict[str, Any], value: Any, expected: int | None
    ) -> None:
        tp_reviews["reviews"][0]["rating"] = value
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.rating == expected

    def test_rating_fallback_key(self, tp_reviews: dict[str, Any]) -> None:
        tp_reviews["reviews"][0]["stars"] = tp_reviews["reviews"][0].pop("rating")
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.rating == 5

    def test_published_at_absent_stays_null(self, tp_reviews: dict[str, Any]) -> None:
        del tp_reviews["reviews"][0]["date"]
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.published_at is None

    def test_published_at_naive_is_utc(self, tp_reviews: dict[str, Any]) -> None:
        tp_reviews["reviews"][0]["date"] = "2026-08-15T10:30:00"
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.published_at == datetime(2026, 8, 15, 10, 30, tzinfo=UTC)

    def test_published_at_bad_string_raises(self, tp_reviews: dict[str, Any]) -> None:
        tp_reviews["reviews"][0]["date"] = "yesterday"
        with pytest.raises(AdapterSchemaError):
            TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)

    def test_author_absent_is_null(self, tp_reviews: dict[str, Any]) -> None:
        del tp_reviews["reviews"][0]["author"]
        first = TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)[0]
        assert first.author_hash is None
        assert first.cluster_key == first.mention_id

    def test_parse_does_not_mutate_input(self, tp_reviews: dict[str, Any]) -> None:
        before = copy.deepcopy(tp_reviews)
        TrustpilotProvider().parse(tp_reviews, "run-001", "Nubank", local_seq=1)
        assert tp_reviews == before

    def test_unit_cost(self) -> None:
        provider = TrustpilotProvider()
        assert provider.unit_cost(10) == 0.03
        assert provider.search_unit_cost() == 0.03

    def test_source_and_endpoint(self) -> None:
        provider = TrustpilotProvider()
        assert provider.source == "trustpilot"
        assert provider.endpoint == "/get_company_reviews"
        assert provider.available is True
        assert provider.unavailable_reason is None


# ── G2 ────────────────────────────────────────────────────────────────


class TestG2Search:
    def test_parse_search_returns_slug(self, g2_search: dict[str, Any]) -> None:
        assert G2Provider().parse_search(g2_search) == "nubank"

    def test_parse_search_stores_slug(self, g2_search: dict[str, Any]) -> None:
        provider = G2Provider()
        provider.parse_search(g2_search)
        inp = provider.build_input(_query())
        assert inp["queryParams"]["slug"] == "nubank"
        assert "query" not in inp["queryParams"]

    def test_parse_search_empty_returns_none(self) -> None:
        assert G2Provider().parse_search({"products": []}) is None

    def test_parse_search_missing_key_returns_none(self) -> None:
        assert G2Provider().parse_search({}) is None

    def test_build_input_search_before_slug(self) -> None:
        inp = G2Provider().build_input(_query())
        assert inp["queryParams"] == {"query": "Nubank"}

    def test_build_input_reviews_after_slug(self, g2_search: dict[str, Any]) -> None:
        provider = G2Provider()
        provider.parse_search(g2_search)
        assert provider.build_input(_query())["queryParams"] == {"slug": "nubank", "page": 1}

    def test_parse_search_mutation_no_slug_raises(self, g2_search: dict[str, Any]) -> None:
        del g2_search["products"][0]["slug"]
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse_search(g2_search)

    def test_parse_search_mutation_not_a_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse_search({"products": "not-a-list"})


class TestG2Reviews:
    def test_parse_returns_mentions(self, g2_reviews: dict[str, Any]) -> None:
        items = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)
        assert len(items) == 2
        assert all(isinstance(m, Mention) for m in items)
        assert [m.raw_ref for m in items] == ["1#0", "1#1"]
        assert {m.source for m in items} == {"g2"}
        assert {m.run_id for m in items} == {"run-002"}
        assert [m.rating for m in items] == [5, 3]

    def test_fields_of_first_item(self, g2_reviews: dict[str, Any]) -> None:
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=4)[0]
        assert first.native_id == "g2-review-001"
        assert first.mention_id == mention_id_for("g2", "g2-review-001")
        assert first.cluster_key == first.mention_id
        assert first.published_at == datetime(2026, 8, 10, 9, 0, tzinfo=UTC)
        assert first.matched_terms == ["nubank"]
        assert first.match_kind == "entity"
        assert first.engagement == {}
        assert first.lang == "en"
        assert first.url is None
        assert first.raw_ref == "4#0"

    def test_parse_text_joins_title_and_content(self, g2_reviews: dict[str, Any]) -> None:
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.text.startswith("Best digital bank in Brazil\n\n")
        assert "incredible digital banking" in first.text

    def test_author_is_hashed_never_raw(self, g2_reviews: dict[str, Any]) -> None:
        mentions = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)
        assert mentions[0].author_hash == author_hash_for("g2", "Ana Costa")
        assert mentions[1].author_hash == author_hash_for("g2", "Carlos Lima")
        dumped = json.dumps([m.model_dump(mode="json") for m in mentions], ensure_ascii=False)
        assert "Ana Costa" not in dumped
        assert "Carlos Lima" not in dumped
        assert "Tech Corp" not in dumped
        assert "author_name" not in dumped

    def test_cluster_key_chains_from_parse(self, g2_reviews: dict[str, Any]) -> None:
        provider = G2Provider()
        first = provider.parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert provider.cluster_key(first) == mention_id_for("g2", "g2-review-001")

    def test_run_id_none_is_allowed(self, g2_reviews: dict[str, Any]) -> None:
        first = G2Provider().parse(g2_reviews, None, "Nubank", local_seq=1)[0]
        assert first.run_id is None

    def test_unmatched_text_is_still_an_entity_match(self, g2_reviews: dict[str, Any]) -> None:
        # D014: the reviews call is scoped to the resolved slug
        g2_reviews["reviews"][0]["title"] = "Fine"
        g2_reviews["reviews"][0]["content"] = "Onboarding took a week."
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.matched_terms == ["nubank"]
        assert first.match_kind == "entity"

    def test_parse_requires_local_seq(self, g2_reviews: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            G2Provider().parse(g2_reviews, "run-002", "Nubank")

    def test_parse_empty_reviews(self) -> None:
        assert G2Provider().parse({"reviews": []}, "run-002", "Nubank", local_seq=1) == []

    def test_parse_skips_review_without_text(self, g2_reviews: dict[str, Any]) -> None:
        del g2_reviews["reviews"][0]["title"]
        del g2_reviews["reviews"][0]["content"]
        items = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)
        assert [m.native_id for m in items] == ["g2-review-002"]
        assert items[0].raw_ref == "1#1"

    def test_parse_mutation_missing_reviews_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse({}, "run-002", "Nubank", local_seq=1)

    def test_parse_mutation_missing_review_id_raises(self, g2_reviews: dict[str, Any]) -> None:
        del g2_reviews["reviews"][0]["reviewId"]
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)

    def test_parse_mutation_non_dict_in_list_raises(self) -> None:
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse({"reviews": [42]}, "run-002", "Nubank", local_seq=1)

    @pytest.mark.parametrize("bad", [True, False, 0, 6, 4.5, "five", [5], {}])
    def test_rating_out_of_range_or_wrong_type_raises(
        self, g2_reviews: dict[str, Any], bad: Any
    ) -> None:
        g2_reviews["reviews"][0]["rating"] = bad
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)

    def test_rating_falls_back_to_star_rating(self, g2_reviews: dict[str, Any]) -> None:
        del g2_reviews["reviews"][0]["rating"]
        g2_reviews["reviews"][0]["starRating"] = "4"
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.rating == 4

    def test_rating_absent_is_null(self, g2_reviews: dict[str, Any]) -> None:
        del g2_reviews["reviews"][0]["rating"]
        del g2_reviews["reviews"][0]["starRating"]
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.rating is None

    def test_published_at_offset_is_normalised(self, g2_reviews: dict[str, Any]) -> None:
        g2_reviews["reviews"][0]["date"] = "2026-08-10T06:00:00-03:00"
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.published_at == datetime(2026, 8, 10, 9, 0, tzinfo=UTC)

    def test_published_at_non_string_raises(self, g2_reviews: dict[str, Any]) -> None:
        g2_reviews["reviews"][0]["date"] = 1755853200
        with pytest.raises(AdapterSchemaError):
            G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)

    def test_author_absent_is_null(self, g2_reviews: dict[str, Any]) -> None:
        del g2_reviews["reviews"][0]["author"]
        first = G2Provider().parse(g2_reviews, "run-002", "Nubank", local_seq=1)[0]
        assert first.author_hash is None

    def test_unit_cost(self) -> None:
        provider = G2Provider()
        assert provider.unit_cost(10) == 0.05
        assert provider.search_unit_cost() == 0.02

    def test_source_and_endpoint(self) -> None:
        provider = G2Provider()
        assert provider.source == "g2"
        assert provider.endpoint == "/get_product_reviews"
        assert provider.available is True
        assert provider.unavailable_reason is None
