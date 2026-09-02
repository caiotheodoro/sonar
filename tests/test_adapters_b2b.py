"""Tests for Trustpilot and G2 B2B adapters (W3.5).

Each adapter is a two-call pattern: search → reviews.  Tests exercise
``parse_search``, ``parse``, and the ``build_input`` state machine on
sample payloads under ``tests/fixtures/samples/``.  Mutated copies verify
that ``AdapterSchemaError`` fires on schema drift.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sonar.providers.base import AdapterSchemaError
from sonar.providers.g2 import G2Provider
from sonar.providers.trustpilot import TrustpilotProvider

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "samples"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text())  # type: ignore[no-any-return]


# ── Trustpilot ────────────────────────────────────────────────────────


class TestTrustpilotSearch:
    def test_parse_search_returns_domain(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_search_companies_sample.json")
        domain = provider.parse_search(raw)
        assert domain == "nubank.com.br"

    def test_parse_search_stores_domain(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_search_companies_sample.json")
        provider.parse_search(raw)
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["domain"] == "nubank.com.br"
        assert "query" not in inp["queryParams"]

    def test_parse_search_empty_returns_none(self) -> None:
        provider = TrustpilotProvider()
        assert provider.parse_search({"companies": []}) is None

    def test_parse_search_missing_key_returns_none(self) -> None:
        provider = TrustpilotProvider()
        assert provider.parse_search({}) is None

    def test_build_input_search_before_domain(self) -> None:
        provider = TrustpilotProvider()
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["query"] == "Nubank"
        assert inp["queryParams"]["limit"] == 1

    def test_build_input_reviews_after_domain(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_search_companies_sample.json")
        provider.parse_search(raw)
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["domain"] == "nubank.com.br"

    def test_parse_search_mutation_no_domain_raises(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_search_companies_sample.json")
        del raw["companies"][0]["domain"]
        with pytest.raises(AdapterSchemaError):
            provider.parse_search(raw)

    def test_parse_search_mutation_not_a_list_raises(self) -> None:
        provider = TrustpilotProvider()
        with pytest.raises(AdapterSchemaError):
            provider.parse_search({"companies": "not-a-list"})


class TestTrustpilotReviews:
    def test_parse_returns_items(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_get_company_reviews_sample.json")
        items = provider.parse(raw, "run-001", "Nubank")
        assert len(items) == 2
        assert items[0]["native_id"] == "tp-review-001"
        assert items[0]["rating"] == 5
        assert items[1]["rating"] == 1

    def test_parse_text_joins_title_and_body(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_get_company_reviews_sample.json")
        items = provider.parse(raw, "run-001", "Nubank")
        assert "Great digital bank" in items[0]["text"]
        assert "changed my life" in items[0]["text"]

    def test_parse_empty_reviews(self) -> None:
        provider = TrustpilotProvider()
        items = provider.parse({"reviews": []}, "run-001", "Nubank")
        assert items == []

    def test_parse_mutation_missing_reviews_raises(self) -> None:
        provider = TrustpilotProvider()
        with pytest.raises(AdapterSchemaError):
            provider.parse({}, "run-001", "Nubank")

    def test_parse_mutation_missing_review_id_raises(self) -> None:
        provider = TrustpilotProvider()
        raw = _load("trustpilot_get_company_reviews_sample.json")
        del raw["reviews"][0]["reviewId"]
        with pytest.raises(AdapterSchemaError):
            provider.parse(raw, "run-001", "Nubank")

    def test_parse_mutation_non_dict_in_list_raises(self) -> None:
        provider = TrustpilotProvider()
        with pytest.raises(AdapterSchemaError):
            provider.parse({"reviews": ["bad"]}, "run-001", "Nubank")

    def test_cluster_key_returns_mention_id(self) -> None:
        provider = TrustpilotProvider()
        item = {"mention_id": "abc123def456abc123def456"}
        assert provider.cluster_key(item) == "abc123def456abc123def456"

    def test_unit_cost(self) -> None:
        provider = TrustpilotProvider()
        assert provider.unit_cost(10) == 0.03
        assert provider.search_unit_cost() == 0.03

    def test_source_and_endpoint(self) -> None:
        provider = TrustpilotProvider()
        assert provider.source == "trustpilot"
        assert provider.endpoint == "/get_company_reviews"
        assert provider.available is True


# ── G2 ────────────────────────────────────────────────────────────────


class TestG2Search:
    def test_parse_search_returns_slug(self) -> None:
        provider = G2Provider()
        raw = _load("g2_search_software_sample.json")
        slug = provider.parse_search(raw)
        assert slug == "nubank"

    def test_parse_search_stores_slug(self) -> None:
        provider = G2Provider()
        raw = _load("g2_search_software_sample.json")
        provider.parse_search(raw)
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["slug"] == "nubank"
        assert "query" not in inp["queryParams"]

    def test_parse_search_empty_returns_none(self) -> None:
        provider = G2Provider()
        assert provider.parse_search({"products": []}) is None

    def test_parse_search_missing_key_returns_none(self) -> None:
        provider = G2Provider()
        assert provider.parse_search({}) is None

    def test_build_input_search_before_slug(self) -> None:
        provider = G2Provider()
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["query"] == "Nubank"

    def test_build_input_reviews_after_slug(self) -> None:
        provider = G2Provider()
        raw = _load("g2_search_software_sample.json")
        provider.parse_search(raw)
        inp = provider.build_input(type("Q", (), {"brand": "Nubank"})())
        assert inp["queryParams"]["slug"] == "nubank"

    def test_parse_search_mutation_no_slug_raises(self) -> None:
        provider = G2Provider()
        raw = _load("g2_search_software_sample.json")
        del raw["products"][0]["slug"]
        with pytest.raises(AdapterSchemaError):
            provider.parse_search(raw)

    def test_parse_search_mutation_not_a_list_raises(self) -> None:
        provider = G2Provider()
        with pytest.raises(AdapterSchemaError):
            provider.parse_search({"products": "not-a-list"})


class TestG2Reviews:
    def test_parse_returns_items(self) -> None:
        provider = G2Provider()
        raw = _load("g2_get_product_reviews_sample.json")
        items = provider.parse(raw, "run-002", "Nubank")
        assert len(items) == 2
        assert items[0]["native_id"] == "g2-review-001"
        assert items[0]["rating"] == 5
        assert items[1]["rating"] == 3

    def test_parse_text_joins_title_and_content(self) -> None:
        provider = G2Provider()
        raw = _load("g2_get_product_reviews_sample.json")
        items = provider.parse(raw, "run-002", "Nubank")
        assert "Best digital bank" in items[0]["text"]
        assert "incredible digital banking" in items[0]["text"]

    def test_parse_empty_reviews(self) -> None:
        provider = G2Provider()
        items = provider.parse({"reviews": []}, "run-002", "Nubank")
        assert items == []

    def test_parse_mutation_missing_reviews_raises(self) -> None:
        provider = G2Provider()
        with pytest.raises(AdapterSchemaError):
            provider.parse({}, "run-002", "Nubank")

    def test_parse_mutation_missing_review_id_raises(self) -> None:
        provider = G2Provider()
        raw = _load("g2_get_product_reviews_sample.json")
        del raw["reviews"][0]["reviewId"]
        with pytest.raises(AdapterSchemaError):
            provider.parse(raw, "run-002", "Nubank")

    def test_parse_mutation_non_dict_in_list_raises(self) -> None:
        provider = G2Provider()
        with pytest.raises(AdapterSchemaError):
            provider.parse({"reviews": [42]}, "run-002", "Nubank")

    def test_cluster_key_returns_mention_id(self) -> None:
        provider = G2Provider()
        item = {"mention_id": "abc123def456abc123def456"}
        assert provider.cluster_key(item) == "abc123def456abc123def456"

    def test_unit_cost(self) -> None:
        provider = G2Provider()
        assert provider.unit_cost(10) == 0.05
        assert provider.search_unit_cost() == 0.02

    def test_source_and_endpoint(self) -> None:
        provider = G2Provider()
        assert provider.source == "g2"
        assert provider.endpoint == "/get_product_reviews"
        assert provider.available is True
