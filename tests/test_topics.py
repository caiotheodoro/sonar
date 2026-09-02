"""W4.2 topics layer: embed cache, clustering, estimates, naming, builder, golden.

No network: every model call goes through ``sonar.llm.fake.FakeBackend``. The
golden ``tests/golden/topics.json`` is generated from the hand-built sample
payloads under ``tests/fixtures/samples/`` (parsed by the registered adapters)
and labels replayed by the fake; regenerate with ``SONAR_UPDATE_GOLDEN=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import sonar.providers  # noqa: F401 - registers every adapter
from sonar import config
from sonar.llm.base import (
    ClassifyBatch,
    LlmRefusal,
    LlmUnparseable,
    MentionText,
)
from sonar.llm.fake import FakeBackend, LabelFixtureEntry, deterministic_vector
from sonar.models import SCHEMA_REV, Label, Mention, SentimentLabel, Topic, mention_id_for
from sonar.providers.registry import PROVIDERS
from sonar.topics import (
    CACHE_FILENAME,
    EmbeddingCache,
    PolarCounts,
    Row,
    TopicName,
    TopicsResult,
    assign_topic_ids,
    average_linkage,
    brand_slug,
    build_topics,
    cap_words,
    cosine_distances,
    embed_texts,
    embedding_key,
    fallback_name,
    is_relevant,
    medoid_indices,
    name_topic,
    net_ci95,
    net_of,
    share_of,
    topic_id_for,
)
from sonar.topics.name import render_naming_user

SAMPLES = Path(__file__).parent / "fixtures" / "samples"
GOLDEN = Path(__file__).parent / "golden" / "topics.json"
GOLDEN_DIM = 3
"""Width of the fake's embeddings for the golden: low enough that random unit
vectors fall inside the 0.35 cosine cut and form clusters on thirty mentions."""

SAMPLE_FILES: dict[str, str] = {
    "reddit": "reddit_reddit-scraper-lite_sample.json",
    "news": "tinyfish_search_sample.json",
    "youtube": "youtube_sample.json",
    "youtube_comment": "youtube_comments_sample.json",
    "tiktok": "SAMPLE-hand-built-tiktok_tiktok-scraper_nubank.json",
    "instagram": "SAMPLE-hand-built-instagram_instagram-hashtag-scraper_nubank.json",
    "google_maps": "SAMPLE-hand-built-apify_google-maps-reviews-scraper_nubank.json",
    "facebook": "SAMPLE-hand-built-apify_facebook-reviews-scraper_nubank.json",
    "trustpilot": "trustpilot_get_company_reviews_sample.json",
    "g2": "g2_get_product_reviews_sample.json",
}
BRAND_TERMS: dict[str, list[str]] = {"Nubank": ["Nubank", "Nu"], "Inter": ["Inter"]}
CANNED_NAME = "Card limit and account access complaints today"
"""Seven words: the layer must cap it at ``config.TOPIC_NAME_MAX_WORDS``."""
ANSWERS: dict[str, dict[str, object]] = {"TopicName": {"name": CANNED_NAME}}
LABEL_CYCLE: tuple[SentimentLabel, ...] = (
    "positive",
    "negative",
    "neutral",
    "positive",
    "irrelevant",
    "negative",
    "positive",
)


# --------------------------------------------------------------------------- builders


def sample_mentions() -> list[Mention]:
    """Every sample payload parsed by its adapter for each brand, one row per (brand, id)."""
    rows: dict[tuple[str, str], Mention] = {}
    for brand, terms in BRAND_TERMS.items():
        for source, name in SAMPLE_FILES.items():
            raw = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
            for mention in PROVIDERS[source].parse(raw, "run_x", brand, local_seq=1, terms=terms):
                rows.setdefault((brand, mention.mention_id), mention)
    return [rows[key] for key in sorted(rows)]


def fake_label_entry(mention_id: str) -> LabelFixtureEntry:
    """Deterministic canned label per mention id: a label cycle, every seventh not about brand."""
    bucket = int(mention_id[:8], 16)
    label = LABEL_CYCLE[bucket % len(LABEL_CYCLE)]
    about_brand = bucket % 7 != 3
    if not about_brand:
        label = "irrelevant"
    return LabelFixtureEntry(
        status="ok",
        label=label,
        about_brand=about_brand,
        confidence=0.9,
        rationale="canned",
    )


def label_from(mention: Mention, observation: Any, *, status: str = "ok") -> Label:
    """A CONTRACTS ``Label`` from a fake classifier observation: model_only, no tiebreak."""
    irrelevant = (not observation.about_brand) or observation.label == "irrelevant"
    return Label.model_validate(
        {
            "mention_id": mention.mention_id,
            "label": observation.label,
            "about_brand": observation.about_brand,
            "confidence": observation.confidence,
            "rationale": observation.rationale or "",
            "topic_id": None,
            "signals": {
                "classifier": {
                    "model": config.LLM.classifier_model,
                    "label": observation.label,
                    "confidence": observation.confidence,
                    "status": "ok",
                },
                "tiebreak": None,
                "deterministic": {"kind": "none", "label": None},
                "overflow": False,
            },
            "corroboration": "irrelevant" if irrelevant else "model_only",
            "decided_by": "classifier",
            "prompt_rev": config.PROMPT_REV,
            "status": status,
            "usage": {"tokens": 0, "cost_usd": 0.0},
        }
    )


def labelled_rows(mentions: list[Mention], backend: FakeBackend) -> list[Row]:
    """Classify every brand's mentions through the fake and join the labels back."""
    rows: list[Row] = []
    for brand in sorted({m.brand for m in mentions}):
        batch_mentions = [m for m in mentions if m.brand == brand]
        batch = ClassifyBatch(
            system="classify",
            brand=brand,
            items=[MentionText(mention_id=m.mention_id, text=m.text) for m in batch_mentions],
        )
        by_id = backend.classify(batch, config.LLM.classifier_model).by_id()
        for mention in batch_mentions:
            observation = by_id[mention.mention_id]
            assert observation.status == "ok", observation
            rows.append((mention, label_from(mention, observation)))
    return rows


def golden_backend(dim: int = GOLDEN_DIM) -> FakeBackend:
    labels = {m.mention_id: fake_label_entry(m.mention_id) for m in sample_mentions()}
    return FakeBackend(labels, answers=ANSWERS, dim=dim)


def golden_rows(backend: FakeBackend) -> list[Row]:
    return labelled_rows(sample_mentions(), backend)


def golden_payload(result: TopicsResult) -> dict[str, Any]:
    payload = {
        "schema_rev": SCHEMA_REV,
        "fake_dim": GOLDEN_DIM,
        "topics": [t.model_dump(mode="json") for t in result.topics],
        "assignments": [
            {"brand": brand, "mention_id": mention_id, "topic_id": topic_id}
            for (brand, mention_id), topic_id in sorted(result.assignments.items())
        ],
        "abstentions": [a.model_dump(mode="json") for a in result.abstentions],
        "notes": list(result.notes),
    }
    round_tripped: dict[str, Any] = json.loads(json.dumps(payload))
    return round_tripped


def synthetic_mention(index: int, brand: str = "Nubank", cluster_key: str | None = None) -> Mention:
    native = f"syn{index:03d}"
    mention_id = mention_id_for("reddit", native)
    return Mention.model_validate(
        {
            "mention_id": mention_id,
            "brand": brand,
            "source": "reddit",
            "run_id": "run_syn",
            "native_id": native,
            "url": None,
            "author_hash": None,
            "text": f"{brand} mention number {index} about the app",
            "lang": "en",
            "published_at": None,
            "engagement": {},
            "rating": None,
            "cluster_key": cluster_key or f"post_{index}",
            "matched_terms": [brand.casefold()],
            "raw_ref": f"1#{index}",
        }
    )


def synthetic_label(mention: Mention, label: SentimentLabel, *, about_brand: bool = True) -> Label:
    class Observation:
        def __init__(self) -> None:
            self.label = label
            self.about_brand = about_brand
            self.confidence = 0.9
            self.rationale = "synthetic"

    return label_from(mention, Observation())


class SameVectorBackend(FakeBackend):
    """Fake whose embeddings are one of a few fixed directions, chosen by a text marker."""

    def __init__(self, directions: dict[str, np.ndarray], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._directions = directions

    def embed(self, texts: Any, model: str) -> Any:
        result = super().embed(texts, model)
        vectors = np.stack(
            [
                next(
                    (v for marker, v in self._directions.items() if marker in text),
                    deterministic_vector(text, len(next(iter(self._directions.values())))),
                )
                for text in texts
            ]
        ).astype(np.float64)
        return type(result)(vectors=vectors, usage=result.usage)


class FailingEmbedBackend(FakeBackend):
    def embed(self, texts: Any, model: str) -> Any:
        raise LlmUnparseable("embeddings: transport failed after retries")


def rows_in_direction(count: int, marker: str, start: int = 0, **label_kwargs: Any) -> list[Row]:
    rows: list[Row] = []
    for i in range(start, start + count):
        mention = synthetic_mention(i)
        mention = mention.model_copy(update={"text": f"{marker} {mention.text}"})
        rows.append((mention, synthetic_label(mention, label_kwargs.get("label", "positive"))))
    return rows


def directions(dim: int = 4) -> dict[str, np.ndarray]:
    eye = np.eye(dim)
    return {"ALPHA": eye[0], "BETA": eye[1], "GAMMA": eye[2], "DELTA": eye[3]}


# --------------------------------------------------------------------------- clustering


class TestClustering:
    def test_cosine_distance_matrix_is_symmetric_with_zero_diagonal(self) -> None:
        vectors = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        d = cosine_distances(vectors)
        assert d.shape == (3, 3)
        assert np.allclose(d, d.T)
        assert np.allclose(np.diag(d), 0.0)
        assert d[0, 1] == pytest.approx(1.0)
        assert d[0, 2] == pytest.approx(1.0 - 1.0 / np.sqrt(2.0))

    def test_merges_only_below_the_cut(self) -> None:
        close = np.array([[1.0, 0.0], [0.99, 0.14], [0.0, 1.0], [0.14, 0.99]])
        clusters = average_linkage(cosine_distances(close), config.TOPIC_DISTANCE_THRESHOLD)
        assert clusters == [[0, 1], [2, 3]]
        assert average_linkage(cosine_distances(close), 0.0) == [[0], [1], [2], [3]]

    def test_average_linkage_uses_mean_distance_not_single_link(self) -> None:
        # Chain a-b-c: a~b and b~c are within the cut, a~c is far. Single linkage
        # would merge all three; average linkage must stop after (a, b) because
        # the mean distance from c to {a, b} exceeds the cut.
        angles = np.array([0.0, 0.7, 1.4])
        vectors = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        d = cosine_distances(vectors)
        cut = float(d[0, 1]) + 1e-9
        assert d[1, 2] <= cut < (d[0, 2] + d[1, 2]) / 2
        assert average_linkage(d, cut) == [[0, 1], [2]]

    def test_ties_break_by_lowest_index_pair(self) -> None:
        # Two equally close pairs, (0, 3) and (1, 2), everything else far apart:
        # both merge, the flat clusters are ordered by size then lowest member.
        d = np.full((4, 4), 1.0)
        np.fill_diagonal(d, 0.0)
        d[0, 3] = d[3, 0] = 0.1
        d[1, 2] = d[2, 1] = 0.1
        assert average_linkage(d, 0.5) == [[0, 3], [1, 2]]
        # A chain 0-1, 0-3, 1-2 at the same distance: (0, 1) merges first (lowest
        # pair), then the average distance from {0, 1} to 2 or 3 is (1 + 0.1) / 2,
        # above a 0.5 cut, so average linkage stops where single linkage would not.
        d[0, 1] = d[1, 0] = 0.1
        assert average_linkage(d, 0.5) == [[0, 1], [2], [3]]
        # At 0.6 the tie between 2 and 3 (both 0.55 from {0, 1}) goes to the lower index.
        assert average_linkage(d, 0.6) == [[0, 1, 2], [3]]

    def test_empty_and_singleton(self) -> None:
        assert average_linkage(np.zeros((0, 0)), 0.35) == []
        assert average_linkage(np.zeros((1, 1)), 0.35) == [[0]]

    def test_rejects_non_square(self) -> None:
        with pytest.raises(ValueError, match="square"):
            average_linkage(np.zeros((2, 3)), 0.35)

    def test_medoids_closest_to_centroid_first(self) -> None:
        vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.6, 0.6]])
        assert medoid_indices(vectors, [0, 1, 2, 3], 3) == [3, 1, 0]
        with pytest.raises(ValueError, match="cannot supply"):
            medoid_indices(vectors, [0, 1], 3)
        with pytest.raises(ValueError, match="at least 1"):
            medoid_indices(vectors, [0, 1], 0)

    def test_deterministic_on_fake_embeddings(self) -> None:
        texts = [f"mention {i}" for i in range(25)]
        vectors = np.stack([deterministic_vector(t, GOLDEN_DIM) for t in texts])
        first = average_linkage(cosine_distances(vectors), config.TOPIC_DISTANCE_THRESHOLD)
        second = average_linkage(cosine_distances(vectors), config.TOPIC_DISTANCE_THRESHOLD)
        assert first == second
        assert sorted(i for c in first for i in c) == list(range(25))


# --------------------------------------------------------------------------- estimates


class TestEstimates:
    def test_net_and_share(self) -> None:
        counts = PolarCounts().add("positive").add("positive").add("negative").add("irrelevant")
        assert counts == PolarCounts(pos=2, neg=1, neu=0)
        assert net_of(counts) == pytest.approx(1.0 / 3.0)
        assert net_of(PolarCounts()) is None
        assert share_of(3, 12) == pytest.approx(0.25)
        assert share_of(3, 0) is None

    def test_ci95_is_seeded_and_brackets_the_point(self) -> None:
        units = [PolarCounts(2, 0, 0), PolarCounts(0, 1, 1), PolarCounts(1, 1, 0)]
        first = net_ci95(units, resamples=500)
        second = net_ci95(units, resamples=500)
        assert first == second
        assert first is not None
        lo, hi = first
        assert lo <= net_of(PolarCounts(3, 2, 1)) <= hi  # type: ignore[operator]
        assert net_ci95(units, resamples=500, seed=1) != first

    def test_ci95_null_without_polar_labels(self) -> None:
        assert net_ci95([]) is None
        assert net_ci95([PolarCounts(), PolarCounts()]) is None

    def test_ci95_collapses_to_point_when_every_resample_is_empty(self) -> None:
        # One polar unit among many empty ones with a single resample that can miss it.
        units = [PolarCounts()] * 40 + [PolarCounts(1, 0, 0)]
        for seed in range(50):
            ci = net_ci95(units, resamples=1, seed=seed)
            assert ci is not None
            if ci == (1.0, 1.0):
                break
        else:
            pytest.fail("expected at least one resample to miss the only polar unit")

    def test_ci95_rejects_zero_resamples(self) -> None:
        with pytest.raises(ValueError, match="resamples"):
            net_ci95([PolarCounts(1, 0, 0)], resamples=0)


# --------------------------------------------------------------------------- naming


class TestNaming:
    def test_cap_words_and_strip(self) -> None:
        assert cap_words(' "Card limit and account access complaints today." ') == (
            "Card limit and account access complaints"
        )
        assert cap_words("one two", max_words=1) == "one"
        assert cap_words("   ") == ""

    def test_name_goes_through_complete_json_and_is_capped(self) -> None:
        fake = FakeBackend(answers=ANSWERS)
        outcome = name_topic(
            fake, config.LLM.classifier_model, brand="Nubank", index=1, n=4, exemplars=["a", "b"]
        )
        assert outcome.name == "Card limit and account access complaints"
        assert len(outcome.name.split()) == config.TOPIC_NAME_MAX_WORDS
        assert outcome.failure is None
        assert outcome.usage is not None and outcome.usage.cost_usd > 0.0
        assert fake.calls_by_kind[("TopicName", config.LLM.classifier_model)] == 1

    @pytest.mark.parametrize(
        ("answers", "expected_error"),
        [
            ({"TopicName": {"__refusal__": "no"}}, "LlmRefusal"),
            ({"TopicName": {"nope": 1}}, "LlmUnparseable"),
            ({}, "LlmUnparseable"),
        ],
    )
    def test_seam_failures_fall_back(
        self, answers: dict[str, dict[str, object]], expected_error: str
    ) -> None:
        fake = FakeBackend(answers=answers)
        outcome = name_topic(
            fake, config.LLM.classifier_model, brand="C6 Bank", index=3, n=5, exemplars=["x"]
        )
        assert outcome.name == fallback_name("C6 Bank", 3) == "C6 Bank topic 03"
        assert outcome.usage is None
        assert outcome.failure is not None and outcome.failure.startswith(expected_error)

    def test_blank_name_falls_back_but_keeps_usage(self) -> None:
        fake = FakeBackend(answers={"TopicName": {"name": '"."'}})
        outcome = name_topic(
            fake, config.LLM.classifier_model, brand="Nubank", index=2, n=3, exemplars=["x"]
        )
        assert outcome.name == "Nubank topic 02"
        assert outcome.usage is not None
        assert outcome.failure == "model returned a blank name"

    def test_user_prompt_clips_exemplars_to_quote_cap(self) -> None:
        long_text = "word " * 400
        user = render_naming_user("Nubank", 7, [long_text, "short\n\nline"])
        lines = user.splitlines()
        assert lines[0] == "Brand: Nubank"
        assert lines[1] == "Mentions in this topic: 7"
        assert lines[-2].startswith("1. ")
        assert len(lines[-2]) - len("1. ") == config.QUOTE_MAX_CHARS
        assert lines[-1] == "2. short line"

    def test_schema_forbids_extras(self) -> None:
        with pytest.raises(ValueError):
            TopicName.model_validate({"name": "x", "extra": 1})
        with pytest.raises(ValueError):
            TopicName.model_validate({"name": ""})

    def test_refusal_and_unparseable_are_llm_errors(self) -> None:
        assert issubclass(LlmRefusal, Exception) and issubclass(LlmUnparseable, Exception)


# --------------------------------------------------------------------------- embed cache


class TestEmbedCache:
    def test_key_depends_on_model_and_text(self) -> None:
        assert embedding_key("m", "t") != embedding_key("m2", "t")
        assert embedding_key("m", "t") != embedding_key("m", "t2")
        assert len(embedding_key("m", "t")) == 24

    def test_writes_npy_and_serves_hits_without_a_call(self, tmp_path: Path) -> None:
        path = tmp_path / CACHE_FILENAME
        fake = FakeBackend(dim=5)
        model = config.LLM.embedding_model
        cache = EmbeddingCache(path)
        first = embed_texts(fake, ["a", "b", "a"], model, cache)
        assert path.exists()
        assert first.cache_hits == 0 and first.cache_misses == 2
        assert first.vectors.shape == (3, 5)
        assert np.allclose(first.vectors[0], first.vectors[2])
        assert np.allclose(np.linalg.norm(first.vectors, axis=1), 1.0)
        assert len(first.usages) == 1 and fake.calls_by_kind[("embed", model)] == 1

        second = embed_texts(fake, ["b", "a"], model, cache)
        assert second.cache_hits == 2 and second.cache_misses == 0
        assert second.usages == ()
        assert fake.calls_by_kind[("embed", model)] == 1
        assert np.allclose(second.vectors[1], first.vectors[0])

        third = embed_texts(fake, ["c", "a"], model, cache)
        assert third.cache_hits == 1 and third.cache_misses == 1
        assert fake.calls_by_kind[("embed", model)] == 2
        assert fake.batches == []  # embed does not record classify batches
        loaded = np.load(path, allow_pickle=False)
        assert loaded.dtype.names == ("key", "vector")
        assert set(loaded["key"]) == {embedding_key(model, t) for t in ("a", "b", "c")}

    def test_no_cache_path_means_no_file_and_a_call_each_time(self, tmp_path: Path) -> None:
        fake = FakeBackend(dim=3)
        model = config.LLM.embedding_model
        embed_texts(fake, ["a"], model, EmbeddingCache(None))
        embed_texts(fake, ["a"], model, EmbeddingCache(None))
        assert fake.calls_by_kind[("embed", model)] == 2
        assert list(tmp_path.iterdir()) == []

    def test_empty_input_makes_no_call(self) -> None:
        fake = FakeBackend(dim=3)
        batch = embed_texts(fake, [], config.LLM.embedding_model, EmbeddingCache(None))
        assert batch.keys == () and batch.vectors.shape == (0, 0)
        assert fake.calls == {}

    def test_width_mismatch_rebuilds_the_cache(self, tmp_path: Path) -> None:
        path = tmp_path / CACHE_FILENAME
        model = config.LLM.embedding_model
        embed_texts(FakeBackend(dim=4), ["a"], model, EmbeddingCache(path))
        wider = FakeBackend(dim=6)
        batch = embed_texts(wider, ["a", "b"], model, EmbeddingCache(path))
        assert batch.vectors.shape == (2, 6)
        assert batch.cache_hits == 0 and batch.cache_misses == 2
        assert wider.calls_by_kind[("embed", model)] == 2
        assert np.load(path, allow_pickle=False)["vector"].shape == (2, 6)

    def test_foreign_npy_is_ignored_not_trusted(self, tmp_path: Path) -> None:
        path = tmp_path / CACHE_FILENAME
        np.save(path, np.zeros((3, 3)))
        assert EmbeddingCache(path).load() == {}
        batch = embed_texts(
            FakeBackend(dim=2), ["a"], config.LLM.embedding_model, EmbeddingCache(path)
        )
        assert batch.cache_misses == 1
        assert np.load(path, allow_pickle=False).dtype.names == ("key", "vector")

    def test_short_vector_count_is_unparseable(self) -> None:
        class ShortBackend(FakeBackend):
            def embed(self, texts: Any, model: str) -> Any:
                result = super().embed(texts, model)
                return type(result)(vectors=result.vectors[:-1], usage=result.usage)

        with pytest.raises(LlmUnparseable, match="asked for 2"):
            embed_texts(
                ShortBackend(dim=2), ["a", "b"], config.LLM.embedding_model, EmbeddingCache(None)
            )


# --------------------------------------------------------------------------- builder


class TestBuild:
    def test_brand_slug_and_topic_id(self) -> None:
        assert brand_slug("Nubank") == "nubank"
        assert brand_slug("C6 Bank") == "c6-bank"
        assert brand_slug("Café Ünïcode!!") == "cafe-unicode"
        assert brand_slug("!!!") == "brand"
        assert topic_id_for("C6 Bank", 7) == "c6-bank-07"
        Topic.model_validate(
            {
                "topic_id": topic_id_for("C6 Bank", 1),
                "brand": "C6 Bank",
                "name": "x",
                "n": 3,
                "n_clusters": 2,
                "share": None,
                "net": None,
                "ci95": None,
                "exemplar_mention_ids": [mention_id_for("reddit", str(i)) for i in range(3)],
                "method": {"embedding_model": "m"},
            }
        )

    def test_relevance_filter(self) -> None:
        mention = synthetic_mention(1)
        assert is_relevant((mention, synthetic_label(mention, "neutral")))
        assert is_relevant((mention, synthetic_label(mention, "irrelevant")))
        assert not is_relevant((mention, synthetic_label(mention, "irrelevant", about_brand=False)))
        cached = label_from(mention, synthetic_label(mention, "positive"), status="cached")
        assert is_relevant((mention, cached))
        errored = synthetic_label(mention, "positive").model_copy(update={"status": "error"})
        assert not is_relevant((mention, errored))
        other = synthetic_mention(2)
        assert not is_relevant((other, synthetic_label(mention, "positive")))

    def test_two_topics_with_ids_shares_nets_exemplars_and_assignments(
        self, tmp_path: Path
    ) -> None:
        rows = rows_in_direction(5, "ALPHA") + rows_in_direction(3, "BETA", start=5)
        rows += rows_in_direction(2, "GAMMA", start=8)
        # a negative label inside ALPHA so net is not trivially 1.0
        alpha_mention, _ = rows[0]
        rows[0] = (alpha_mention, synthetic_label(alpha_mention, "negative"))
        backend = SameVectorBackend(directions(), answers=ANSWERS)
        result = build_topics(rows, backend, cache_path=tmp_path / CACHE_FILENAME)

        assert [t.topic_id for t in result.topics] == ["nubank-01", "nubank-02"]
        alpha, beta = result.topics
        assert (alpha.n, alpha.n_clusters) == (5, 5)
        assert (beta.n, beta.n_clusters) == (3, 3)
        assert alpha.share == pytest.approx(5 / 10) and beta.share == pytest.approx(3 / 10)
        assert alpha.net == pytest.approx((4 - 1) / 5) and beta.net == pytest.approx(1.0)
        assert alpha.net is not None and alpha.ci95 is not None
        assert alpha.ci95[0] <= alpha.net <= alpha.ci95[1]
        assert beta.ci95 == (1.0, 1.0)
        assert alpha.name == "Card limit and account access complaints"
        assert alpha.method.embedding_model == config.LLM.embedding_model
        assert alpha.method.threshold == config.TOPIC_DISTANCE_THRESHOLD
        assert len(alpha.exemplar_mention_ids) == config.TOPIC_EXEMPLARS
        alpha_ids = {m.mention_id for m, _ in rows[:5]}
        assert set(alpha.exemplar_mention_ids) <= alpha_ids
        assert result.abstentions == []
        assert result.notes == []
        assert {v for v in result.assignments.values()} == {"nubank-01", "nubank-02"}
        assert len(result.assignments) == 8
        assert result.llm_calls() == {"embed": 1, "name_topic": 2}
        assert result.llm_usd > 0.0
        assert (tmp_path / CACHE_FILENAME).exists()

        assigned = assign_topic_ids(rows, result.assignments)
        assert [label.topic_id for _, label in assigned[:5]] == ["nubank-01"] * 5
        assert [label.topic_id for _, label in assigned[5:8]] == ["nubank-02"] * 3
        assert [label.topic_id for _, label in assigned[8:]] == [None, None]

    def test_ordering_by_descending_n_then_breadth_then_mention_id(self) -> None:
        # ALPHA: 3 mentions over 3 keys; BETA: 3 mentions over 2 keys. Equal n, ALPHA first.
        alpha = rows_in_direction(3, "ALPHA", start=10)
        beta_rows: list[Row] = []
        for i, key in ((0, "shared"), (1, "shared"), (2, "solo")):
            mention = synthetic_mention(i, cluster_key=key)
            mention = mention.model_copy(update={"text": f"BETA {mention.text}"})
            beta_rows.append((mention, synthetic_label(mention, "neutral")))
        result = build_topics(beta_rows + alpha, SameVectorBackend(directions(), answers=ANSWERS))
        assert [(t.topic_id, t.n, t.n_clusters) for t in result.topics] == [
            ("nubank-01", 3, 3),
            ("nubank-02", 3, 2),
        ]

    def test_null_estimates_are_paired_with_below_minimum(self) -> None:
        # Three mentions, three keys, but only two polar labels: share and net null.
        rows = rows_in_direction(3, "ALPHA")
        m, _ = rows[2]
        rows[2] = (m, synthetic_label(m, "irrelevant"))
        result = build_topics(rows, SameVectorBackend(directions(), answers=ANSWERS))
        (topic,) = result.topics
        assert topic.has_null_estimate
        assert topic.share is None and topic.net is None and topic.ci95 is None
        (row,) = result.abstentions
        assert row.scope == "topics" and row.brand == "Nubank" and row.source is None
        assert row.reason == "below_minimum"
        assert row.detail.startswith("nubank-01: 2 labelled mentions over 2 cluster keys")

    def test_polar_breadth_below_minimum_is_null_even_with_enough_labels(self) -> None:
        rows: list[Row] = []
        for i, key in ((0, "k1"), (1, "k1"), (2, "k1"), (3, "k2")):
            mention = synthetic_mention(i, cluster_key=key)
            mention = mention.model_copy(update={"text": f"ALPHA {mention.text}"})
            rows.append(
                (mention, synthetic_label(mention, "positive" if key == "k1" else "irrelevant"))
            )
        result = build_topics(rows, SameVectorBackend(directions(), answers=ANSWERS))
        (topic,) = result.topics
        assert (topic.n, topic.n_clusters) == (4, 2)
        assert topic.net is None
        assert result.abstentions[0].detail.startswith(
            "nubank-01: 3 labelled mentions over 1 cluster keys"
        )

    def test_cluster_without_breadth_is_not_a_topic(self) -> None:
        rows = [
            (m.model_copy(update={"cluster_key": "one_thread"}), label)
            for m, label in rows_in_direction(4, "ALPHA")
        ]
        result = build_topics(rows, SameVectorBackend(directions(), answers=ANSWERS))
        assert result.topics == []
        (row,) = result.abstentions
        assert row.reason == "below_minimum"
        assert "largest cluster 4" in row.detail
        assert result.assignments == {}

    def test_brand_with_too_few_relevant_mentions_abstains_without_embedding(self) -> None:
        rows = rows_in_direction(2, "ALPHA")
        rows.append(
            (
                synthetic_mention(9),
                synthetic_label(synthetic_mention(9), "irrelevant", about_brand=False),
            )
        )
        backend = SameVectorBackend(directions(), answers=ANSWERS)
        result = build_topics(rows, backend)
        assert result.topics == []
        (row,) = result.abstentions
        assert row.reason == "below_minimum" and row.detail.startswith("no topics: 2 relevant")
        assert backend.calls == {}

    def test_embedding_failure_abstains_the_brand_only(self) -> None:
        rows = rows_in_direction(4, "ALPHA")
        result = build_topics(rows, FailingEmbedBackend(answers=ANSWERS))
        assert result.topics == []
        (row,) = result.abstentions
        assert row.scope == "topics" and row.reason == "embedding_failed" and row.brand == "Nubank"
        assert row.detail == "LlmUnparseable: embeddings: transport failed after retries"
        assert result.usages == []

    def test_unknown_embedding_model_rate_abstains_not_raises(self) -> None:
        rows = rows_in_direction(4, "ALPHA")
        result = build_topics(rows, FakeBackend(answers=ANSWERS), embedding_model="no-such-model")
        (row,) = result.abstentions
        assert row.reason == "embedding_failed" and row.detail.startswith("LlmRateError")

    def test_naming_failure_uses_fallback_and_notes_it(self) -> None:
        rows = rows_in_direction(3, "ALPHA")
        backend = SameVectorBackend(directions(), answers={"TopicName": {"__refusal__": "policy"}})
        result = build_topics(rows, backend)
        (topic,) = result.topics
        assert topic.name == "Nubank topic 01"
        assert result.notes == ["topic naming fell back for nubank-01: LlmRefusal: policy"]
        assert result.llm_calls() == {"embed": 1, "name_topic": 0}

    def test_brands_are_independent_and_ordered_by_first_appearance(self) -> None:
        nubank = rows_in_direction(3, "ALPHA")
        inter: list[Row] = []
        for i in range(3):
            mention = synthetic_mention(20 + i, brand="Inter")
            mention = mention.model_copy(update={"text": f"BETA {mention.text}"})
            inter.append((mention, synthetic_label(mention, "negative")))
        result = build_topics(inter + nubank, SameVectorBackend(directions(), answers=ANSWERS))
        assert [t.topic_id for t in result.topics] == ["inter-01", "nubank-01"]
        assert result.topics[0].net == -1.0 and result.topics[1].net == 1.0
        assert result.llm_calls() == {"embed": 2, "name_topic": 2}

    def test_duplicate_mention_ids_count_once(self) -> None:
        rows = rows_in_direction(3, "ALPHA")
        result = build_topics(rows + rows, SameVectorBackend(directions(), answers=ANSWERS))
        (topic,) = result.topics
        assert topic.n == 3 and topic.share == 1.0

    def test_config_minimums_match_contracts(self) -> None:
        assert config.TOPIC_MIN_SIZE == 3 and config.TOPIC_MIN_BREADTH == 2
        assert config.TOPIC_LINKAGE == "average"
        assert config.THRESHOLD_INDEX["topic_distance_threshold"] == config.TOPIC_DISTANCE_THRESHOLD


# --------------------------------------------------------------------------- golden


class TestGolden:
    def test_sample_pool_has_two_brands(self) -> None:
        mentions = sample_mentions()
        brands = {m.brand for m in mentions}
        assert brands == {"Nubank", "Inter"}
        assert sum(m.brand == "Nubank" for m in mentions) >= 20

    def test_golden_matches_and_is_deterministic(self, tmp_path: Path) -> None:
        backend = golden_backend()
        rows = golden_rows(backend)
        cache_path = tmp_path / CACHE_FILENAME
        result = build_topics(rows, backend, cache_path=cache_path)
        payload = golden_payload(result)

        again = build_topics(rows, golden_backend(), cache_path=tmp_path / "again" / CACHE_FILENAME)
        assert golden_payload(again) == payload

        replay = build_topics(rows, golden_backend(), cache_path=cache_path)
        assert golden_payload(replay) == payload
        assert replay.embedding_cache_misses == 0 and replay.embedding_cache_hits > 0

        if os.environ.get("SONAR_UPDATE_GOLDEN") == "1":
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        assert GOLDEN.exists(), "golden missing: run with SONAR_UPDATE_GOLDEN=1"
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert golden == payload

    def test_golden_invariants(self) -> None:
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        assert golden["schema_rev"] == SCHEMA_REV
        assert golden["fake_dim"] == GOLDEN_DIM
        topics = [Topic.model_validate(t) for t in golden["topics"]]
        assert topics, "golden must hold at least one topic"
        brands = [t.brand for t in topics]
        assert brands == sorted(brands, key=brands.index)
        ns = [t.n for t in topics if t.brand == "Nubank"]
        assert ns == sorted(ns, reverse=True)
        assert [t.topic_id for t in topics if t.brand == "Nubank"] == [
            f"nubank-{i:02d}" for i in range(1, len(ns) + 1)
        ]
        for topic in topics:
            assert topic.n >= config.TOPIC_MIN_SIZE and topic.n_clusters >= config.TOPIC_MIN_BREADTH
            assert len(topic.name.split()) <= config.TOPIC_NAME_MAX_WORDS
            assert len(topic.exemplar_mention_ids) == config.TOPIC_EXEMPLARS
        assert any(t.has_null_estimate for t in topics), "golden should show a null estimate"
        assert any(not t.has_null_estimate for t in topics), "golden should show a full estimate"
        abstentions = golden["abstentions"]
        nulls = [t for t in topics if t.has_null_estimate]
        paired = [a for a in abstentions if any(a["detail"].startswith(t.topic_id) for t in nulls)]
        assert len(paired) == len(nulls)
        assert any(a["brand"] == "Inter" and a["reason"] == "below_minimum" for a in abstentions)
        assigned = {(a["brand"], a["mention_id"]) for a in golden["assignments"]}
        assert sum(t.n for t in topics) == len(assigned)
        assert golden["notes"] == []
