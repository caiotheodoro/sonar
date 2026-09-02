"""W3.1 adapter tests: Reddit (apify /trudax/reddit-scraper-lite) and News (tinyfish /search).

Payloads are the hand-built samples under ``tests/fixtures/samples/`` until
W3.7 records real fixtures. Each adapter is exercised on the sample and on
a mutated copy that must raise ``AdapterSchemaError``.
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
from sonar.providers import news, reddit
from sonar.providers.base import AdapterSchemaError, Provider
from sonar.providers.registry import PROVIDERS

SAMPLES = Path(__file__).parent / "fixtures" / "samples"
NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
RUN_ID = "run_01J6ZREDDIT0000000000000"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture
def reddit_raw() -> dict[str, Any]:
    return _load("reddit_reddit-scraper-lite_sample.json")


@pytest.fixture
def news_raw() -> dict[str, Any]:
    return _load("tinyfish_search_sample.json")


@pytest.fixture
def query() -> Query:
    return Query(
        brand="Nubank",
        brand_aliases=["Nu"],
        competitors=["Inter", "C6 Bank"],
        profile="full",
    )


# ---------------------------------------------------------------------------
# registration and protocol
# ---------------------------------------------------------------------------


class TestRegistration:
    @pytest.mark.parametrize(
        ("source", "module_provider", "endpoint", "provider_name"),
        [
            ("reddit", reddit.PROVIDER, "/trudax/reddit-scraper-lite", "apify"),
            ("news", news.PROVIDER, "/search", "tinyfish"),
        ],
    )
    def test_registered_and_available(
        self,
        source: config.SourceName,
        module_provider: reddit.RedditProvider | news.NewsProvider,
        endpoint: str,
        provider_name: str,
    ) -> None:
        assert PROVIDERS[source] is module_provider
        assert module_provider.provider == provider_name
        assert isinstance(module_provider, Provider)
        assert module_provider.source == source
        assert module_provider.endpoint == endpoint
        assert module_provider.available is True
        assert module_provider.unavailable_reason is None
        assert module_provider.endpoint == config.SOURCE_PLAN[source].endpoint


class TestProtocolSignature:
    """``parse`` must accept the keyword names ``base.Provider`` declares."""

    def test_reddit_parse_with_protocol_keywords(self, reddit_raw: dict[str, Any]) -> None:
        provider: Provider = reddit.PROVIDER
        mentions = provider.parse(reddit_raw, RUN_ID, "Nubank", local_seq=1, terms=["Nu"])
        assert {m.native_id for m in mentions} == {
            "t3_1abc123",
            "t1_c0mm3nt1",
            "t1_c0mm3nt2",
            "t1_orphan01",
            "t3_1linkpost",
        }
        assert provider.parse(reddit_raw, RUN_ID, "Nubank", local_seq=1, terms=None) == (
            provider.parse(reddit_raw, RUN_ID, "Nubank", local_seq=1)
        )

    def test_news_parse_with_protocol_keywords(self, news_raw: dict[str, Any]) -> None:
        provider: Provider = news.PROVIDER
        mentions = provider.parse(news_raw, None, "Nubank", local_seq=1, terms=["Nu"])
        assert len(mentions) == 3
        assert all(m.run_id is None for m in mentions)
        assert provider.parse(news_raw, None, "Nubank", local_seq=1, terms=None) == (
            provider.parse(news_raw, None, "Nubank", local_seq=1)
        )

    def test_aliases_keyword_is_gone(
        self, reddit_raw: dict[str, Any], news_raw: dict[str, Any]
    ) -> None:
        legacy: dict[str, Any] = {"aliases": ["Nu"]}
        with pytest.raises(TypeError, match="aliases"):
            reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank", local_seq=1, **legacy)
        with pytest.raises(TypeError, match="aliases"):
            news.PROVIDER.parse(news_raw, None, "Nubank", local_seq=1, **legacy)

    def test_brand_is_always_matched_and_terms_deduplicated(self, news_raw: dict[str, Any]) -> None:
        with_dup = news.PROVIDER.parse(
            news_raw, None, "Nubank", local_seq=1, terms=["Nubank", "Nu"]
        )
        plain = news.PROVIDER.parse(news_raw, None, "Nubank", local_seq=1, terms=["Nu"])
        assert with_dup == plain
        assert all("nubank" in m.matched_terms or "nu" in m.matched_terms for m in plain)


# ---------------------------------------------------------------------------
# reddit: build_input
# ---------------------------------------------------------------------------


class TestRedditBuildInput:
    def test_exact_actor_input_for_brand(self, query: Query) -> None:
        assert reddit.PROVIDER.build_input(query, now=NOW) == {
            "searches": ["Nubank", "Nu"],
            "sort": "new",
            "time": "week",
            "maxItems": 40,
            "maxPostCount": 15,
            "maxComments": 2,
            "postDateLimit": "2026-08-19",
            "includeMediaLinks": True,
        }

    def test_competitor_searches_only_its_name(self, query: Query) -> None:
        built = reddit.PROVIDER.build_input(query, brand="Inter", now=NOW)
        assert built["searches"] == ["Inter"]

    def test_unknown_brand_rejected(self, query: Query) -> None:
        with pytest.raises(ValueError, match="neither"):
            reddit.PROVIDER.build_input(query, brand="Itaú", now=NOW)

    @pytest.mark.parametrize(("profile", "cap"), [("smoke", 40), ("lite", 20), ("full", 40)])
    def test_caps_follow_config(self, profile: Any, cap: int) -> None:
        q = Query(brand="Nubank", profile=profile, sources=["reddit"])
        built = reddit.PROVIDER.build_input(q, now=NOW)
        plan = config.SOURCE_PLAN["reddit"]
        assert cap == plan.caps[profile]
        assert (plan.max_posts, plan.max_comments_per_post) == (15, 2)
        # D014: the item cap follows the profile; the post/comment split is fixed
        assert (built["maxItems"], built["maxPostCount"], built["maxComments"]) == (cap, 15, 2)

    def test_unit_cost_matches_config(self) -> None:
        plan = config.SOURCE_PLAN["reddit"]
        assert reddit.PROVIDER.unit_cost(0) == pytest.approx(plan.per_call_usd)
        assert reddit.PROVIDER.unit_cost(40) == pytest.approx(plan.estimate_usd("full"))
        assert reddit.PROVIDER.unit_cost(40) == pytest.approx(0.02 + 40 * 0.0057)
        with pytest.raises(ValueError):
            reddit.PROVIDER.unit_cost(-1)


# ---------------------------------------------------------------------------
# reddit: parse
# ---------------------------------------------------------------------------


class TestRedditParse:
    def test_posts_and_comments_become_mentions(self, reddit_raw: dict[str, Any]) -> None:
        report = reddit.PROVIDER.parse_with_report(
            reddit_raw, RUN_ID, "Nubank", local_seq=7, terms=["Nu"]
        )
        by_native = {m.native_id: m for m in report.mentions}
        # 6 items: 5 match Nubank/Nu, the r/personalfinance post does not
        assert set(by_native) == {
            "t3_1abc123",
            "t1_c0mm3nt1",
            "t1_c0mm3nt2",
            "t1_orphan01",
            "t3_1linkpost",
        }
        assert report.skipped_no_match == 1
        assert report.inherited_from == {}
        assert {m.match_kind for m in report.mentions} == {"text"}
        assert not hasattr(report, "skipped_blank_text")
        assert all(isinstance(m, Mention) for m in report.mentions)
        assert all(m.source == "reddit" and m.brand == "Nubank" for m in report.mentions)
        assert all(m.run_id == RUN_ID and m.rating is None for m in report.mentions)

    def test_cluster_key_is_post_id(self, reddit_raw: dict[str, Any]) -> None:
        report = reddit.PROVIDER.parse_with_report(
            reddit_raw, RUN_ID, "Nubank", local_seq=7, terms=["Nu"]
        )
        by_native = {m.native_id: m for m in report.mentions}
        post = by_native["t3_1abc123"]
        assert post.cluster_key == "t3_1abc123"
        # comment with postId
        assert by_native["t1_c0mm3nt1"].cluster_key == "t3_1abc123"
        # comment without postId: post id parsed from the url
        assert by_native["t1_c0mm3nt2"].cluster_key == "t3_1zzz999"
        # comment with neither: mention_id fallback, counted
        orphan = by_native["t1_orphan01"]
        assert orphan.cluster_key == orphan.mention_id
        assert report.cluster_key_fallbacks == 1
        assert reddit.PROVIDER.cluster_key(post) == post.cluster_key

    def test_field_mapping(self, reddit_raw: dict[str, Any]) -> None:
        mentions = reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank", local_seq=7, terms=["Nu"])
        post = mentions[0]
        assert post.mention_id == mention_id_for("reddit", "t3_1abc123")
        assert post.text.startswith("Nubank mudou o limite do cartão sem avisar\n\nAcordei hoje")
        assert post.url == (
            "https://www.reddit.com/r/investimentos/comments/1abc123/"
            "nubank_mudou_o_limite_do_cartao"
        )
        assert post.author_hash == author_hash_for("reddit", "investidor_pt")
        assert "investidor_pt" not in post.model_dump_json()
        assert post.published_at == datetime(2026, 8, 30, 13, 42, 10, tzinfo=UTC)
        assert post.engagement == {"upvotes": 87, "comments": 14}
        assert post.lang == "pt"
        assert post.matched_terms == ["nubank"]
        assert post.raw_ref == "7#0"

        comment = mentions[1]
        assert comment.text.startswith("Mesmo problema aqui com o Nu")
        assert comment.engagement == {"upvotes": 12, "replies": 2}
        assert comment.matched_terms == ["nu"]
        assert comment.raw_ref == "7#1"

    def test_raw_ref_index_counts_skipped_items(self, reddit_raw: dict[str, Any]) -> None:
        mentions = reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank", local_seq=3, terms=["Nu"])
        refs = {m.native_id: m.raw_ref for m in mentions}
        # item 3 (r/personalfinance) is skipped; item 4 keeps zero-based index 4
        assert refs["t1_orphan01"] == "3#4"
        assert refs["t3_1linkpost"] == "3#5"

    def test_missing_optional_fields_never_raise(self, reddit_raw: dict[str, Any]) -> None:
        mentions = reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank", local_seq=1, terms=["Nu"])
        by_native = {m.native_id: m for m in mentions}
        orphan = by_native["t1_orphan01"]
        assert orphan.url is None
        assert orphan.published_at == datetime(2026, 8, 30, 8, 0, 0, tzinfo=UTC)
        assert orphan.engagement == {"upvotes": 1204}
        assert orphan.lang == "en"
        link_post = by_native["t3_1linkpost"]
        assert link_post.text == "Nubank anuncia novo produto"
        assert link_post.author_hash is None
        assert link_post.published_at is None
        assert link_post.engagement == {"comments": 0}

    def test_accepts_bare_list_payload(self, reddit_raw: dict[str, Any]) -> None:
        as_list = reddit_raw["items"]
        assert len(reddit.PROVIDER.parse(as_list, RUN_ID, "Nubank", local_seq=1)) == 5

    def test_comment_without_alias_inherits_its_matched_post(
        self, reddit_raw: dict[str, Any]
    ) -> None:
        # D014: "Mesmo problema aqui com o Nu" matches nothing without the alias,
        # but its parent t3_1abc123 is a text match in the same payload.
        report = reddit.PROVIDER.parse_with_report(reddit_raw, RUN_ID, "Nubank", local_seq=1)
        by_native = {m.native_id: m for m in report.mentions}
        assert set(by_native) == {
            "t3_1abc123",
            "t1_c0mm3nt1",
            "t1_c0mm3nt2",
            "t1_orphan01",
            "t3_1linkpost",
        }
        comment = by_native["t1_c0mm3nt1"]
        assert comment.match_kind == "inherited"
        assert comment.matched_terms == by_native["t3_1abc123"].matched_terms == ["nubank"]
        assert comment.cluster_key == "t3_1abc123"
        assert report.inherited_from == {"t1_c0mm3nt1": "t3_1abc123"}
        assert {by_native[n].match_kind for n in by_native if n != "t1_c0mm3nt1"} == {"text"}
        assert report.skipped_no_match == 1

    def test_comment_under_absent_or_unmatched_post_is_dropped(
        self, reddit_raw: dict[str, Any]
    ) -> None:
        raw = copy.deepcopy(reddit_raw)
        for item in raw["items"]:
            if item["id"] == "t1_c0mm3nt1":
                item["postId"] = "t3_notinpayload"
                item["url"] = None
            if item["id"] == "t3_1abc123":
                item["title"] = "Unrelated"
                item["body"] = "Nothing about the bank."
        report = reddit.PROVIDER.parse_with_report(raw, RUN_ID, "Nubank", local_seq=1)
        assert "t1_c0mm3nt1" not in {m.native_id for m in report.mentions}
        assert report.inherited_from == {}
        assert report.skipped_no_match == 3

    def test_competitor_gets_no_rows_when_absent(self, reddit_raw: dict[str, Any]) -> None:
        assert reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Inter", local_seq=1) == []

    def test_local_seq_required(self, reddit_raw: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank")
        with pytest.raises(ValueError, match="local_seq"):
            reddit.PROVIDER.parse(reddit_raw, RUN_ID, "Nubank", local_seq=0)

    @pytest.mark.parametrize(
        ("index", "field"),
        [(0, "id"), (0, "dataType"), (0, "title"), (1, "body")],
    )
    def test_mutated_required_field_raises(
        self, reddit_raw: dict[str, Any], index: int, field: str
    ) -> None:
        mutated = copy.deepcopy(reddit_raw)
        del mutated["items"][index][field]
        with pytest.raises(AdapterSchemaError) as info:
            reddit.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1, terms=["Nu"])
        assert info.value.provider == "apify"
        assert info.value.endpoint == "/trudax/reddit-scraper-lite"
        assert field in info.value.detail

    def test_unknown_data_type_raises(self, reddit_raw: dict[str, Any]) -> None:
        mutated = copy.deepcopy(reddit_raw)
        mutated["items"][0]["dataType"] = "media"
        with pytest.raises(AdapterSchemaError, match="dataType"):
            reddit.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)

    @pytest.mark.parametrize("payload", [{"error": "boom"}, "text", 42, {"items": "no"}])
    def test_wrong_envelope_raises(self, payload: Any) -> None:
        with pytest.raises(AdapterSchemaError):
            reddit.PROVIDER.parse(payload, RUN_ID, "Nubank", local_seq=1)

    def test_non_object_item_raises(self, reddit_raw: dict[str, Any]) -> None:
        mutated = copy.deepcopy(reddit_raw)
        mutated["items"].insert(0, "junk")
        with pytest.raises(AdapterSchemaError, match="expected object"):
            reddit.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)


class TestRedditTimestamp:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-08-30T13:42:10.000Z", datetime(2026, 8, 30, 13, 42, 10, tzinfo=UTC)),
            ("2026-08-30T10:42:10-03:00", datetime(2026, 8, 30, 13, 42, 10, tzinfo=UTC)),
            ("2026-08-30T13:42:10", datetime(2026, 8, 30, 13, 42, 10, tzinfo=UTC)),
            (1788076800, datetime(2026, 8, 30, 8, 0, 0, tzinfo=UTC)),
            (1788076800000, datetime(2026, 8, 30, 8, 0, 0, tzinfo=UTC)),
            ("yesterday", None),
            ("", None),
            (None, None),
            (True, None),
        ],
    )
    def test_parse_timestamp(self, value: Any, expected: datetime | None) -> None:
        assert reddit.parse_timestamp(value) == expected


# ---------------------------------------------------------------------------
# news: build_input
# ---------------------------------------------------------------------------


class TestNewsBuildInput:
    def test_exact_query_params_shape(self, query: Query) -> None:
        assert news.PROVIDER.build_input(query, page=1, now=NOW) == {
            "queryParams": {
                "query": "Nubank",
                "domain_type": "news",
                "after_date": "2026-08-19",
                "page": 1,
            }
        }

    def test_competitor_query(self, query: Query) -> None:
        built = news.PROVIDER.build_input(query, brand="C6 Bank", page=2, now=NOW)
        assert built["queryParams"]["query"] == "C6 Bank"
        assert built["queryParams"]["page"] == 2

    @pytest.mark.parametrize(("profile", "n_pages"), [("full", 3), ("lite", 2)])
    def test_pages_follow_config(self, profile: Any, n_pages: int) -> None:
        q = Query(brand="Nubank", profile=profile, sources=["news"])
        assert list(news.PROVIDER.pages(q)) == list(range(1, n_pages + 1))
        assert n_pages == config.SOURCE_PLAN["news"].caps[profile]
        assert n_pages <= news.MAX_PAGE
        for page in news.PROVIDER.pages(q):
            assert news.PROVIDER.build_input(q, page=page, now=NOW)["queryParams"]["page"] == page

    def test_page_outside_cap_rejected(self, query: Query) -> None:
        with pytest.raises(ValueError, match="page"):
            news.PROVIDER.build_input(query, page=4, now=NOW)
        with pytest.raises(ValueError, match="page"):
            news.PROVIDER.build_input(query, page=0, now=NOW)

    def test_smoke_profile_has_no_pages(self) -> None:
        q = Query(brand="Nubank", profile="smoke", sources=["reddit"])
        assert list(news.PROVIDER.pages(q)) == []
        with pytest.raises(ValueError, match="not fetched"):
            news.PROVIDER.build_input(q, page=1, now=NOW)

    def test_free(self) -> None:
        assert news.PROVIDER.unit_cost(0) == 0.0
        assert news.PROVIDER.unit_cost(30) == 0.0
        assert config.SOURCE_PLAN["news"].estimate_usd("full") == 0.0

    def test_fallback_documented_not_implemented(self) -> None:
        assert "context.dev" in news.FALLBACK_ENDPOINT
        assert not hasattr(news.PROVIDER, "fallback")


# ---------------------------------------------------------------------------
# news: parse
# ---------------------------------------------------------------------------


class TestNewsParse:
    def test_results_become_mentions(self, news_raw: dict[str, Any]) -> None:
        report = news.PROVIDER.parse_with_report(
            news_raw, RUN_ID, "Nubank", local_seq=11, terms=["Nu"]
        )
        assert len(report.mentions) == 3
        assert report.skipped_no_match == 1
        assert [m.raw_ref for m in report.mentions] == ["11#0", "11#1", "11#3"]
        assert all(m.source == "news" and m.native_id is None for m in report.mentions)
        assert all(m.rating is None and m.engagement == {} for m in report.mentions)

    def test_cluster_key_is_mention_id(self, news_raw: dict[str, Any]) -> None:
        for m in news.PROVIDER.parse(news_raw, RUN_ID, "Nubank", local_seq=1, terms=["Nu"]):
            assert m.cluster_key == m.mention_id
            assert news.PROVIDER.cluster_key(m) == m.mention_id

    def test_field_mapping(self, news_raw: dict[str, Any]) -> None:
        first, second, third = news.PROVIDER.parse(
            news_raw, RUN_ID, "Nubank", local_seq=1, terms=["Nu"]
        )
        assert first.url == "https://www.valor.com.br/financas/2026/08/31/nubank-conta-global.ghtml"
        assert first.mention_id == mention_id_for("news", first.url)
        assert first.text.startswith(
            "Nubank lança conta global para clientes no Brasil\n\nO Nubank"
        )
        assert first.author_hash == author_hash_for("news", "Valor Econômico")
        assert "Valor" not in first.model_dump_json()
        assert first.published_at == datetime(2026, 8, 31, 0, 0, 0, tzinfo=UTC)
        assert first.lang == "pt"
        assert first.matched_terms == ["nubank"]

        assert second.published_at == datetime(2026, 8, 28, 14, 30, 0, tzinfo=UTC)
        assert second.lang == "en"

        assert third.text == "Nu Pagamentos amplia crédito para pequenas empresas"
        assert third.author_hash is None
        assert third.published_at is None
        assert third.matched_terms == ["nu"]

    def test_same_url_same_mention_id_across_brands(self, news_raw: dict[str, Any]) -> None:
        q_brand = news.PROVIDER.parse(news_raw, RUN_ID, "Nubank", local_seq=1)
        q_other = news.PROVIDER.parse(news_raw, "run_other", "Nubank", local_seq=2)
        assert [m.mention_id for m in q_brand] == [m.mention_id for m in q_other]

    def test_accepts_nested_and_bare_shapes(self, news_raw: dict[str, Any]) -> None:
        bare = news_raw["results"]
        nested = {"data": {"results": news_raw["results"]}}
        n = len(news.PROVIDER.parse(news_raw, RUN_ID, "Nubank", local_seq=1))
        assert len(news.PROVIDER.parse(bare, RUN_ID, "Nubank", local_seq=1)) == n
        assert len(news.PROVIDER.parse(nested, RUN_ID, "Nubank", local_seq=1)) == n

    def test_local_seq_required(self, news_raw: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            news.PROVIDER.parse(news_raw, RUN_ID, "Nubank")

    @pytest.mark.parametrize(("index", "field"), [(0, "url"), (0, "title"), (1, "url")])
    def test_mutated_required_field_raises(
        self, news_raw: dict[str, Any], index: int, field: str
    ) -> None:
        mutated = copy.deepcopy(news_raw)
        del mutated["results"][index][field]
        with pytest.raises(AdapterSchemaError) as info:
            news.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)
        assert info.value.provider == "tinyfish"
        assert info.value.endpoint == "/search"
        assert field in info.value.detail

    def test_empty_url_is_a_schema_error(self, news_raw: dict[str, Any]) -> None:
        mutated = copy.deepcopy(news_raw)
        mutated["results"][0]["url"] = "   "
        with pytest.raises(AdapterSchemaError, match="url"):
            news.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)

    @pytest.mark.parametrize("payload", [{"error": "boom"}, "text", None, {"results": {}}])
    def test_wrong_envelope_raises(self, payload: Any) -> None:
        with pytest.raises(AdapterSchemaError):
            news.PROVIDER.parse(payload, RUN_ID, "Nubank", local_seq=1)

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-08-31", datetime(2026, 8, 31, tzinfo=UTC)),
            ("2026-08-28T14:30:00Z", datetime(2026, 8, 28, 14, 30, tzinfo=UTC)),
            ("2026-08-28T11:30:00-03:00", datetime(2026, 8, 28, 14, 30, tzinfo=UTC)),
            ("last week", None),
            (None, None),
            (1756540800, None),
        ],
    )
    def test_parse_date(self, value: Any, expected: datetime | None) -> None:
        assert news.parse_date(value) == expected
