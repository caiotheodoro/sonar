"""Adapter tests for the YouTube video and YouTube comment providers.

The payloads under ``tests/fixtures/samples/`` are hand-built samples in the
shape the design's endpoint reference states; W3.7 replaces them with
recorded fixtures. Each adapter is tested on its sample and on a mutated copy
that must raise ``AdapterSchemaError``.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sonar import models as m
from sonar.config import SOURCE_PLAN
from sonar.providers import youtube, youtube_comments
from sonar.providers.base import AdapterEmpty, AdapterSchemaError, Provider
from sonar.providers.registry import PROVIDERS
from sonar.text import text_key

SAMPLES = Path(__file__).parent / "fixtures" / "samples"
RUN_ID = "run_yt_0001"
HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX24 = re.compile(r"^[0-9a-f]{24}$")


def load(name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture
def videos_raw() -> list[dict[str, Any]]:
    return load("youtube_sample.json")


@pytest.fixture
def comments_raw() -> list[dict[str, Any]]:
    return load("youtube_comments_sample.json")


@pytest.fixture
def query() -> m.Query:
    return m.Query(brand="Nubank", brand_aliases=["Nu"], competitors=["Inter"], profile="full")


# --------------------------------------------------------------------------- registry


class TestRegistration:
    def test_both_registered_and_available(self) -> None:
        for source, module in (("youtube", youtube), ("youtube_comment", youtube_comments)):
            provider = PROVIDERS[source]
            assert provider is module.PROVIDER
            assert isinstance(provider, Provider)
            assert provider.available is True
            assert provider.unavailable_reason is None
            assert provider.source == source

    def test_endpoints_match_config(self) -> None:
        assert youtube.PROVIDER.endpoint == SOURCE_PLAN["youtube"].endpoint
        assert youtube.PROVIDER.endpoint == "/streamers/youtube-scraper"
        assert youtube_comments.PROVIDER.endpoint == SOURCE_PLAN["youtube_comment"].endpoint
        assert youtube_comments.PROVIDER.endpoint == "/streamers/youtube-comments-scraper"
        assert youtube.PROVIDER.provider == "apify"
        assert youtube_comments.PROVIDER.provider == "apify"


# --------------------------------------------------------------------------- youtube videos


class TestYouTubeBuildInput:
    def test_full_profile_shape(self, query: m.Query) -> None:
        payload = youtube.PROVIDER.build_input(query)
        assert payload == {
            "searchQueries": ["Nubank", "Nu"],
            "maxResults": SOURCE_PLAN["youtube"].caps["full"],
            "dateFilter": "month",
            "sortingOrder": "date",
        }
        assert payload["maxResults"] == 10

    def test_lite_profile_halves_cap(self) -> None:
        q = m.Query(brand="Nubank", profile="lite")
        assert youtube.PROVIDER.build_input(q)["maxResults"] == 5

    def test_competitor_uses_only_its_name(self, query: m.Query) -> None:
        assert youtube.PROVIDER.build_input(query, brand="Inter")["searchQueries"] == ["Inter"]

    def test_max_results_never_zero(self) -> None:
        q = m.Query(brand="Nubank", profile="smoke")
        assert SOURCE_PLAN["youtube"].caps["smoke"] == 0
        with pytest.raises(ValueError, match="smoke"):
            youtube.PROVIDER.build_input(q)


class TestYouTubeParse:
    def test_sample_parses_to_mentions(self, videos_raw: list[dict[str, Any]]) -> None:
        mentions = youtube.PROVIDER.parse(
            videos_raw, RUN_ID, "Nubank", local_seq=7, terms=["Nubank", "Nu"]
        )
        # item 2 (cards without annual fee) never names the brand and is dropped
        assert [x.raw_ref for x in mentions] == ["7#0", "7#1", "7#3"]
        first = mentions[0]
        assert isinstance(first, m.Mention)
        assert first.source == "youtube"
        assert first.brand == "Nubank"
        assert first.run_id == RUN_ID
        assert first.native_id == "aB3dE5fG7hI"
        assert first.mention_id == m.mention_id_for("youtube", "aB3dE5fG7hI")
        assert HEX24.match(first.mention_id)
        assert first.cluster_key == first.mention_id
        assert youtube.PROVIDER.cluster_key(first) == first.mention_id
        assert first.url == "https://www.youtube.com/watch?v=aB3dE5fG7hI"
        assert first.text.startswith("Nubank vs Inter")
        assert "\n\n" in first.text
        assert first.text.endswith("Detalhes no vídeo.")
        assert first.lang == "pt"
        assert first.published_at == datetime(2026, 8, 27, 14, 3, 11, tzinfo=UTC)
        assert first.engagement == {"views": 48210, "likes": 1830, "comments": 412}
        assert first.rating is None
        assert first.matched_terms == ["nubank"]

    def test_author_is_hashed_never_stored(self, videos_raw: list[dict[str, Any]]) -> None:
        mentions = youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=1)
        first = mentions[0]
        assert first.author_hash == m.author_hash_for("youtube", "Canal Finanças Simples")
        assert first.author_hash is not None
        assert HEX16.match(first.author_hash)
        dumped = json.dumps([x.model_dump(mode="json") for x in mentions], ensure_ascii=False)
        assert "Canal Finanças Simples" not in dumped
        assert "Fintech Weekly" not in dumped

    def test_numeric_string_counter_and_short_z_date(
        self, videos_raw: list[dict[str, Any]]
    ) -> None:
        second = youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=1)[1]
        assert second.engagement["views"] == 1204555
        assert second.published_at == datetime(2026, 8, 12, 9, 45, 0, tzinfo=UTC)
        assert second.lang == "en"

    def test_missing_optional_fields_do_not_raise(self, videos_raw: list[dict[str, Any]]) -> None:
        sparse = youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=1)[-1]
        assert sparse.native_id == "mM4nN5bB6vV"
        assert sparse.text == "Nubank"
        assert sparse.url == "https://www.youtube.com/watch?v=mM4nN5bB6vV"
        assert sparse.author_hash is None
        assert sparse.published_at is None
        assert sparse.engagement == {}
        assert sparse.lang == "unknown"

    def test_default_terms_is_brand_alone(self, videos_raw: list[dict[str, Any]]) -> None:
        only_alias = copy.deepcopy(videos_raw[:1])
        only_alias[0]["title"] = "Cartão roxo do Nu"
        only_alias[0]["text"] = "Só o apelido aparece aqui."
        assert youtube.PROVIDER.parse(only_alias, RUN_ID, "Nubank", local_seq=1) == []
        assert (
            len(youtube.PROVIDER.parse(only_alias, RUN_ID, "Nubank", terms=["Nu"], local_seq=1))
            == 1
        )

    def test_wrapped_payload_is_accepted(self, videos_raw: list[dict[str, Any]]) -> None:
        for key in ("items", "data", "results"):
            wrapped = {key: videos_raw}
            assert len(youtube.PROVIDER.parse(wrapped, RUN_ID, "Nubank", local_seq=1)) == 3

    def test_empty_payload_is_zero_mentions(self) -> None:
        assert youtube.PROVIDER.parse([], RUN_ID, "Nubank", local_seq=1) == []
        assert youtube.PROVIDER.parse({"items": []}, RUN_ID, "Nubank", local_seq=1) == []

    def test_all_error_items_raise_adapter_empty(self) -> None:
        raw = [
            {"error": "no_results", "input": "Nubank", "url": "https://youtube.com"},
            {"errorDescription": "search returned nothing", "inputUrl": "x"},
        ]
        with pytest.raises(AdapterEmpty) as info:
            youtube.PROVIDER.parse(raw, RUN_ID, "Nubank", local_seq=1)
        assert info.value.endpoint == "/streamers/youtube-scraper"

    def test_error_items_mixed_with_real_are_skipped(
        self, videos_raw: list[dict[str, Any]]
    ) -> None:
        raw = [{"error": "one url failed", "url": "x"}, *videos_raw]
        mentions = youtube.PROVIDER.parse(
            raw, RUN_ID, "Nubank", terms=["Nubank", "Nu"], local_seq=1
        )
        assert len(mentions) == 3

    def test_mutated_sample_missing_id_raises(self, videos_raw: list[dict[str, Any]]) -> None:
        mutated = copy.deepcopy(videos_raw)
        del mutated[1]["id"]
        with pytest.raises(AdapterSchemaError) as info:
            youtube.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)
        assert info.value.provider == "apify"
        assert info.value.endpoint == "/streamers/youtube-scraper"
        assert "item 1" in info.value.detail
        assert "'id'" in info.value.detail

    def test_mutated_sample_renamed_fields_raises(self, videos_raw: list[dict[str, Any]]) -> None:
        mutated = [
            {"videoId": item.get("id"), "description": item.get("text")} for item in videos_raw
        ]
        with pytest.raises(AdapterSchemaError):
            youtube.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)

    @pytest.mark.parametrize(
        "raw",
        [
            {"status": "ok"},
            {"items": "not a list"},
            ["not an object"],
            "text",
        ],
    )
    def test_wrong_payload_shape_raises(self, raw: Any) -> None:
        with pytest.raises(AdapterSchemaError):
            youtube.PROVIDER.parse(raw, RUN_ID, "Nubank", local_seq=1)

    def test_local_seq_required(self, videos_raw: list[dict[str, Any]]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank")
        with pytest.raises(ValueError, match="local_seq"):
            youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=None)
        with pytest.raises(ValueError, match="local_seq"):
            youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=0)

    def test_local_seq_checked_before_payload(self) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            youtube.PROVIDER.parse([], RUN_ID, "Nubank", local_seq=0)


class TestYouTubeCost:
    def test_unit_cost_matches_config(self) -> None:
        plan = SOURCE_PLAN["youtube"]
        assert youtube.PROVIDER.unit_cost(0) == plan.per_call_usd == 0.0
        assert youtube.PROVIDER.unit_cost(1) == pytest.approx(0.0045)
        assert youtube.PROVIDER.unit_cost(10) == pytest.approx(plan.estimate_usd("full"))


# --------------------------------------------------------------------------- youtube comments


class TestYouTubeCommentsBuildInput:
    def test_start_urls_from_video_mentions(
        self, query: m.Query, videos_raw: list[dict[str, Any]]
    ) -> None:
        videos = youtube.PROVIDER.parse(videos_raw, RUN_ID, "Nubank", local_seq=1)
        payload = youtube_comments.PROVIDER.build_input(query, videos)
        assert payload == {
            "startUrls": [
                {"url": "https://www.youtube.com/watch?v=aB3dE5fG7hI"},
                {"url": "https://www.youtube.com/watch?v=zX9yW8vU7tS"},
                {"url": "https://www.youtube.com/watch?v=mM4nN5bB6vV"},
            ],
            "maxComments": SOURCE_PLAN["youtube_comment"].caps["full"] // 3,
            "sortCommentsBy": "newest",
        }
        assert payload["maxComments"] * 3 <= SOURCE_PLAN["youtube_comment"].caps["full"]

    def test_max_comments_is_cap_for_one_video(self, query: m.Query) -> None:
        payload = youtube_comments.PROVIDER.build_input(
            query, ["https://www.youtube.com/watch?v=aB3dE5fG7hI"]
        )
        assert payload["maxComments"] == SOURCE_PLAN["youtube_comment"].caps["full"] == 60

    def test_max_comments_never_zero_with_many_videos(self, query: m.Query) -> None:
        urls = [f"https://www.youtube.com/watch?v=v{i:010d}" for i in range(500)]
        assert youtube_comments.PROVIDER.build_input(query, urls)["maxComments"] == 1

    def test_no_videos_raises(self, query: m.Query) -> None:
        with pytest.raises(ValueError, match="video URL"):
            youtube_comments.PROVIDER.build_input(query, [])

    def test_smoke_profile_raises(self) -> None:
        q = m.Query(brand="Nubank", profile="smoke")
        with pytest.raises(ValueError, match="smoke"):
            youtube_comments.PROVIDER.build_input(q, ["https://www.youtube.com/watch?v=x"])

    def test_video_urls_dedup_and_skip_missing(self) -> None:
        urls = youtube_comments.video_urls_of(["u1", "u2", "u1", "", 42])
        assert urls == ["u1", "u2"]


class TestYouTubeCommentsParse:
    def test_sample_parses_to_mentions(self, comments_raw: list[dict[str, Any]]) -> None:
        mentions = youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank", local_seq=9)
        # item 1 talks about Inter only and is dropped for the Nubank batch
        assert [x.raw_ref for x in mentions] == ["9#0", "9#2", "9#3"]
        first = mentions[0]
        assert first.source == "youtube_comment"
        assert first.native_id == "UgzK1a2b3c4d5e6f7g8h9i0"
        assert first.mention_id == m.mention_id_for("youtube_comment", "UgzK1a2b3c4d5e6f7g8h9i0")
        assert first.cluster_key == "aB3dE5fG7hI"
        assert youtube_comments.PROVIDER.cluster_key(first) == "aB3dE5fG7hI"
        assert first.url is None
        assert first.published_at is None
        assert first.rating is None
        assert first.lang == "pt"
        assert first.engagement == {"likes": 128, "replies": 6}
        assert first.matched_terms == ["nubank"]
        assert first.author_hash == m.author_hash_for("youtube_comment", "@marina.oliveira")
        assert first.author_hash is not None
        assert HEX16.match(first.author_hash)

    def test_no_timestamp_ever(self, comments_raw: list[dict[str, Any]]) -> None:
        with_date = copy.deepcopy(comments_raw)
        for item in with_date:
            item["date"] = "2026-08-30T10:00:00Z"
        assert all(
            x.published_at is None
            for x in youtube_comments.PROVIDER.parse(with_date, RUN_ID, "Nubank", local_seq=1)
        )

    def test_handles_never_stored(self, comments_raw: list[dict[str, Any]]) -> None:
        mentions = youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank", local_seq=1)
        dumped = json.dumps([x.model_dump(mode="json") for x in mentions], ensure_ascii=False)
        assert "marina.oliveira" not in dumped
        assert "lucas.tm" not in dumped

    def test_missing_optional_fields_do_not_raise(self, comments_raw: list[dict[str, Any]]) -> None:
        sparse = youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank", local_seq=1)[-1]
        assert sparse.native_id is None
        assert sparse.author_hash is None
        assert sparse.engagement == {"likes": 44}
        assert sparse.cluster_key == "zX9yW8vU7tS"
        expected_key = text_key(sparse.text)
        assert sparse.mention_id == m.mention_id_for("youtube_comment", expected_key)

    def test_competitor_batch_matches_competitor(self, comments_raw: list[dict[str, Any]]) -> None:
        mentions = youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Inter", local_seq=1)
        assert [x.raw_ref for x in mentions] == ["1#1"]
        assert mentions[0].brand == "Inter"
        assert mentions[0].matched_terms == ["inter"]

    def test_wrapped_payload_is_accepted(self, comments_raw: list[dict[str, Any]]) -> None:
        assert (
            len(
                youtube_comments.PROVIDER.parse(
                    {"items": comments_raw}, RUN_ID, "Nubank", local_seq=1
                )
            )
            == 3
        )

    def test_mutated_sample_missing_video_id_raises(
        self, comments_raw: list[dict[str, Any]]
    ) -> None:
        mutated = copy.deepcopy(comments_raw)
        del mutated[2]["videoId"]
        with pytest.raises(AdapterSchemaError) as info:
            youtube_comments.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)
        assert info.value.endpoint == "/streamers/youtube-comments-scraper"
        assert "item 2" in info.value.detail
        assert "'videoId'" in info.value.detail

    def test_mutated_sample_missing_comment_raises(
        self, comments_raw: list[dict[str, Any]]
    ) -> None:
        mutated = copy.deepcopy(comments_raw)
        mutated[0]["comment"] = None
        with pytest.raises(AdapterSchemaError):
            youtube_comments.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)

    def test_blank_comment_raises(self, comments_raw: list[dict[str, Any]]) -> None:
        mutated = copy.deepcopy(comments_raw)
        mutated[0]["comment"] = "   "
        with pytest.raises(AdapterSchemaError):
            youtube_comments.PROVIDER.parse(mutated, RUN_ID, "Nubank", local_seq=1)

    def test_local_seq_required(self, comments_raw: list[dict[str, Any]]) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank")
        with pytest.raises(ValueError, match="local_seq"):
            youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank", local_seq=None)
        with pytest.raises(ValueError, match="local_seq"):
            youtube_comments.PROVIDER.parse(comments_raw, RUN_ID, "Nubank", local_seq=0)

    def test_local_seq_checked_before_payload(self) -> None:
        with pytest.raises(ValueError, match="local_seq"):
            youtube_comments.PROVIDER.parse([], RUN_ID, "Nubank", local_seq=0)


class TestYouTubeCommentsCost:
    def test_unit_cost_matches_config(self) -> None:
        plan = SOURCE_PLAN["youtube_comment"]
        assert youtube_comments.PROVIDER.unit_cost(0) == 0.0
        assert youtube_comments.PROVIDER.unit_cost(1) == pytest.approx(0.00225)
        assert youtube_comments.PROVIDER.unit_cost(60) == pytest.approx(plan.estimate_usd("full"))
