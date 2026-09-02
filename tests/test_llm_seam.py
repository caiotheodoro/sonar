"""Contract tests for the LLM seam, run against the fake and the stubbed OpenAI backend.

The stub transport answers ``chat/completions`` from the same labels fixture
the fake replays, so both implementations are held to one contract:
ids round-trip in batch order, missing ids become ``unparseable``, invented
ids are dropped, refusals mark the whole batch, usage is priced from the rate
table, embeddings have one row per text, and only ``openai_backend`` imports
``openai``.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import numpy as np
import pytest
from pydantic import BaseModel, ValidationError

from sonar.llm import base
from sonar.llm.base import (
    ClassifyBatch,
    LabelObservation,
    LlmRateError,
    LlmRefusal,
    LlmUnparseable,
    MentionText,
    Rate,
    Usage,
    coerce_rates,
)
from sonar.llm.fake import FakeBackend, LabelFixtureEntry, load_labels_fixture
from sonar.llm.openai_backend import OpenAIBackend

FIXTURE = Path(__file__).parent / "fixtures" / "labels.json"
SRC = Path(__file__).resolve().parents[1] / "src" / "sonar" / "llm"

CLASSIFIER = "gpt-5.6-luna"
TIEBREAK = "gpt-5.6-terra"
EMBEDDING = "text-embedding-3-small"

RATES: dict[str, Rate] = {
    CLASSIFIER: Rate(input_usd_per_mtok=0.20, output_usd_per_mtok=1.20),
    TIEBREAK: Rate(input_usd_per_mtok=2.00, output_usd_per_mtok=12.00),
    EMBEDDING: Rate(input_usd_per_mtok=0.02, output_usd_per_mtok=0.0),
}

SYSTEM = "You label brand mentions. Answer only in the JSON schema."
IDS = [f"aaaaaaaaaaaaaaaaaaaaaaa{i}" for i in range(1, 6)]
TEXTS = {
    IDS[0]: "Onboarding no app foi rápido, adorei o Nubank.",
    IDS[1]: "Nubank blocked my card again, awful support.",
    IDS[2]: "Does Nubank charge fees on international transfers?",
    IDS[3]: "The nubank shade of purple is trending this season.",
    IDS[4]: "Content the model will refuse to label.",
}


class TopicName(BaseModel):
    name: str
    keywords: list[str]


@dataclass
class StubState:
    """Knobs the stubbed transport reads: which ids to drop, add, or refuse."""

    labels: dict[str, LabelFixtureEntry]
    drop_ids: set[str] = field(default_factory=set)
    extra_ids: list[str] = field(default_factory=list)
    refuse_batch: bool = False
    garbage_json: bool = False
    fail_http: int | None = None
    requests: list[httpx2.Request] = field(default_factory=list)
    calls: dict[str, int] = field(default_factory=dict)


def _chat_response(model: str, content: str | None, refusal: str | None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if refusal is not None:
        message["refusal"] = refusal
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160},
    }


def _answer_for(state: StubState, mention_id: str) -> dict[str, Any] | None:
    entry = state.labels.get(mention_id)
    if entry is None or entry.status != "ok":
        return None
    return {
        "mention_id": mention_id,
        "label": entry.label,
        "about_brand": entry.about_brand,
        "confidence": entry.confidence,
        "rationale": entry.rationale,
    }


def make_handler(state: StubState) -> Callable[[httpx2.Request], httpx2.Response]:
    def handler(request: httpx2.Request) -> httpx2.Response:
        state.requests.append(request)
        body = json.loads(request.content)
        model = body["model"]
        state.calls[model] = state.calls.get(model, 0) + 1
        if state.fail_http is not None:
            return httpx2.Response(state.fail_http, json={"error": {"message": "stub failure"}})
        if request.url.path.endswith("/embeddings"):
            texts = body["input"]
            data = [
                {"object": "embedding", "index": i, "embedding": [float(i + 1), 0.5, -0.25]}
                for i in range(len(texts))
            ]
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": data,
                    "model": model,
                    "usage": {"prompt_tokens": 7 * len(texts), "total_tokens": 7 * len(texts)},
                },
            )
        assert request.url.path.endswith("/chat/completions")
        assert body["response_format"]["type"] == "json_schema"
        schema_name = body["response_format"]["json_schema"]["name"]
        if state.refuse_batch:
            return httpx2.Response(200, json=_chat_response(model, None, "I cannot label this."))
        if state.garbage_json:
            return httpx2.Response(200, json=_chat_response(model, "{not json", None))
        if schema_name == "TopicName":
            content = json.dumps({"name": "Card blocks", "keywords": ["card", "blocked"]})
            return httpx2.Response(200, json=_chat_response(model, content, None))
        assert schema_name == "LabelAnswers"
        user = body["messages"][1]["content"]
        items = json.loads(user[user.index("[") :])
        labels: list[dict[str, Any]] = []
        for item in items:
            if item["mention_id"] in state.drop_ids:
                continue
            answer = _answer_for(state, item["mention_id"])
            if answer is not None:
                labels.append(answer)
        for extra in state.extra_ids:
            labels.append(
                {
                    "mention_id": extra,
                    "label": "positive",
                    "about_brand": True,
                    "confidence": 0.5,
                    "rationale": "invented",
                }
            )
        return httpx2.Response(
            200, json=_chat_response(model, json.dumps({"labels": labels}), None)
        )

    return handler


@dataclass
class Harness:
    """One seam implementation plus the knobs to make it misbehave in contract-visible ways."""

    name: str
    backend: FakeBackend | OpenAIBackend
    fake: FakeBackend | None
    stub: StubState | None

    def calls(self, model: str) -> int:
        if self.fake is not None:
            return self.fake.calls[model]
        assert self.stub is not None
        return self.stub.calls.get(model, 0)

    def drop_from_answers(self, mention_id: str) -> None:
        if self.fake is not None:
            self.fake._labels.pop(mention_id, None)
        else:
            assert self.stub is not None
            self.stub.drop_ids.add(mention_id)


def _fixture_labels() -> dict[str, LabelFixtureEntry]:
    return load_labels_fixture(FIXTURE)


@pytest.fixture(params=["fake", "openai-stub"])
def harness(request: pytest.FixtureRequest) -> Iterator[Harness]:
    labels = _fixture_labels()
    answers = {"TopicName": {"name": "Card blocks", "keywords": ["card", "blocked"]}}
    if request.param == "fake":
        fake = FakeBackend(labels, answers=answers, rates=RATES, dim=3)
        yield Harness("fake", fake, fake, None)
        return
    state = StubState(labels=labels)
    client = httpx2.Client(transport=httpx2.MockTransport(make_handler(state)))
    backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
    yield Harness("openai-stub", backend, None, state)
    client.close()


def batch_of(ids: list[str]) -> ClassifyBatch:
    return ClassifyBatch(
        system=SYSTEM,
        brand="Nubank",
        brand_hint="Brazilian digital bank",
        items=[MentionText(mention_id=i, text=TEXTS[i]) for i in ids],
    )


# --- classify -----------------------------------------------------------------


def test_classify_round_trips_ids_in_batch_order(harness: Harness) -> None:
    ids = IDS[:4]
    result = harness.backend.classify(batch_of(ids), CLASSIFIER)
    assert [o.mention_id for o in result.observations] == ids
    assert all(o.status == "ok" for o in result.observations)
    by_id = result.by_id()
    assert by_id[IDS[0]].label == "positive"
    assert by_id[IDS[1]].label == "negative"
    assert by_id[IDS[3]].label == "irrelevant"
    assert by_id[IDS[3]].about_brand is False
    assert by_id[IDS[2]].confidence == pytest.approx(0.55)


def test_classify_reversed_batch_keeps_batch_order(harness: Harness) -> None:
    ids = list(reversed(IDS[:4]))
    result = harness.backend.classify(batch_of(ids), CLASSIFIER)
    assert [o.mention_id for o in result.observations] == ids


def test_missing_ids_become_unparseable(harness: Harness) -> None:
    harness.drop_from_answers(IDS[1])
    result = harness.backend.classify(batch_of(IDS[:3]), CLASSIFIER)
    assert [o.mention_id for o in result.observations] == IDS[:3]
    statuses = {o.mention_id: o.status for o in result.observations}
    assert statuses == {IDS[0]: "ok", IDS[1]: "unparseable", IDS[2]: "ok"}
    missing = result.by_id()[IDS[1]]
    assert missing.label is None and missing.confidence is None and missing.about_brand is None
    assert result.usage.cost_usd > 0.0, "an unparseable id still cost tokens"


def test_id_not_in_fixture_is_unparseable_not_invented(harness: Harness) -> None:
    unknown = "ffffffffffffffffffffffff"
    batch = ClassifyBatch(
        system=SYSTEM,
        brand="Nubank",
        items=[MentionText(mention_id=unknown, text="never seen before")],
    )
    result = harness.backend.classify(batch, CLASSIFIER)
    assert result.observations == [
        LabelObservation(
            mention_id=unknown, status="unparseable", rationale="id missing from answer"
        )
    ]


def test_refused_entry_marks_only_that_id(harness: Harness) -> None:
    result = harness.backend.classify(batch_of([IDS[0], IDS[4]]), CLASSIFIER)
    statuses = [o.status for o in result.observations]
    # The fake replays the fixture's per-id refusal; the stub cannot express a per-id
    # refusal in structured output, so the id is simply absent → unparseable. Both are
    # non-ok, both keep the id in place.
    assert statuses[0] == "ok"
    assert statuses[1] in {"refused", "unparseable"}
    assert [o.mention_id for o in result.observations] == [IDS[0], IDS[4]]


def test_invented_ids_are_dropped() -> None:
    state = StubState(labels=_fixture_labels(), extra_ids=["bbbbbbbbbbbbbbbbbbbbbbbb"])
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        result = backend.classify(batch_of(IDS[:2]), CLASSIFIER)
    assert [o.mention_id for o in result.observations] == IDS[:2]


def test_whole_batch_refusal_marks_every_id_refused() -> None:
    state = StubState(labels=_fixture_labels(), refuse_batch=True)
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        result = backend.classify(batch_of(IDS[:3]), CLASSIFIER)
    assert [o.mention_id for o in result.observations] == IDS[:3]
    assert {o.status for o in result.observations} == {"refused"}
    assert result.usage.tokens == 160, "a refusal is still billed"


def test_garbage_json_marks_every_id_unparseable() -> None:
    state = StubState(labels=_fixture_labels(), garbage_json=True)
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        result = backend.classify(batch_of(IDS[:2]), CLASSIFIER)
    assert {o.status for o in result.observations} == {"unparseable"}
    assert [o.mention_id for o in result.observations] == IDS[:2]


def test_http_failure_after_retries_marks_every_id_error() -> None:
    state = StubState(labels=_fixture_labels(), fail_http=500)
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        result = backend.classify(batch_of(IDS[:2]), CLASSIFIER)
    assert {o.status for o in result.observations} == {"error"}
    assert [o.mention_id for o in result.observations] == IDS[:2]
    assert result.usage.cost_usd == 0.0


def test_backend_sends_structured_output_with_pydantic_schema() -> None:
    state = StubState(labels=_fixture_labels())
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        backend.classify(batch_of(IDS[:1]), CLASSIFIER)
    body = json.loads(state.requests[0].content)
    response_format = body["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "LabelAnswers"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["properties"]["labels"]["type"] == "array"
    assert body["messages"][0] == {"role": "system", "content": SYSTEM}
    assert "Brazilian digital bank" in body["messages"][1]["content"]


def test_batch_rejects_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        ClassifyBatch(
            system=SYSTEM,
            brand="Nubank",
            items=[
                MentionText(mention_id=IDS[0], text="a"),
                MentionText(mention_id=IDS[0], text="b"),
            ],
        )


def test_observation_status_and_fields_are_consistent() -> None:
    with pytest.raises(ValidationError):
        LabelObservation(mention_id=IDS[0], status="ok")
    with pytest.raises(ValidationError):
        LabelObservation(
            mention_id=IDS[0],
            status="unparseable",
            label="positive",
            about_brand=True,
            confidence=1.0,
        )


# --- usage and cost -------------------------------------------------------------


def test_classify_usage_is_priced_from_rates(harness: Harness) -> None:
    result = harness.backend.classify(batch_of(IDS[:3]), CLASSIFIER)
    usage = result.usage
    assert usage.model == CLASSIFIER
    assert usage.tokens == usage.input_tokens + usage.output_tokens > 0
    rate = RATES[CLASSIFIER]
    expected = (
        usage.input_tokens * rate.input_usd_per_mtok
        + usage.output_tokens * rate.output_usd_per_mtok
    ) / 1_000_000
    assert usage.cost_usd == pytest.approx(expected)
    assert usage.cost_usd > 0.0


def test_tiebreak_model_is_priced_higher_for_same_batch(harness: Harness) -> None:
    cheap = harness.backend.classify(batch_of(IDS[:3]), CLASSIFIER).usage
    dear = harness.backend.classify(batch_of(IDS[:3]), TIEBREAK).usage
    assert dear.model == TIEBREAK
    assert dear.cost_usd > cheap.cost_usd


def test_unknown_model_rate_raises_before_any_call(harness: Harness) -> None:
    with pytest.raises(LlmRateError):
        harness.backend.classify(batch_of(IDS[:1]), "gpt-unpriced")
    with pytest.raises(LlmRateError):
        harness.backend.embed(["x"], "embed-unpriced")
    with pytest.raises(LlmRateError):
        harness.backend.complete_json("s", "u", TopicName, "gpt-unpriced")
    assert harness.calls("gpt-unpriced") == 0
    assert harness.calls("embed-unpriced") == 0


def test_usage_price_arithmetic() -> None:
    usage = Usage.price(TIEBREAK, 1_000_000, 500_000, RATES)
    assert usage.cost_usd == pytest.approx(2.00 + 6.00)
    assert usage.tokens == 1_500_000


# --- complete_json ---------------------------------------------------------------


def test_complete_json_returns_schema_instance(harness: Harness) -> None:
    result = harness.backend.complete_json(
        "Name the topic in six words or fewer.",
        "medoids: card blocked, card blocked again",
        TopicName,
        TIEBREAK,
    )
    assert isinstance(result.value, TopicName)
    assert result.value.name == "Card blocks"
    assert result.value.keywords == ["card", "blocked"]
    assert result.usage.model == TIEBREAK
    assert result.usage.cost_usd > 0.0


def test_complete_json_refusal_raises() -> None:
    state = StubState(labels=_fixture_labels(), refuse_batch=True)
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        with pytest.raises(LlmRefusal):
            backend.complete_json("s", "u", TopicName, TIEBREAK)
    fake = FakeBackend(rates=RATES, answers={"TopicName": {"__refusal__": "no"}})
    with pytest.raises(LlmRefusal):
        fake.complete_json("s", "u", TopicName, TIEBREAK)


def test_complete_json_unparseable_raises() -> None:
    state = StubState(labels=_fixture_labels(), garbage_json=True)
    with httpx2.Client(transport=httpx2.MockTransport(make_handler(state))) as client:
        backend = OpenAIBackend("sk-stub", rates=RATES, http_client=client, max_retries=0)
        with pytest.raises(LlmUnparseable):
            backend.complete_json("s", "u", TopicName, TIEBREAK)
    fake = FakeBackend(rates=RATES, answers={"TopicName": {"name": 3}})
    with pytest.raises(LlmUnparseable):
        fake.complete_json("s", "u", TopicName, TIEBREAK)
    with pytest.raises(LlmUnparseable):
        FakeBackend(rates=RATES).complete_json("s", "u", TopicName, TIEBREAK)


# --- embed ------------------------------------------------------------------------


def test_embed_returns_one_row_per_text(harness: Harness) -> None:
    texts = [TEXTS[i] for i in IDS[:3]]
    result = harness.backend.embed(texts, EMBEDDING)
    assert isinstance(result.vectors, np.ndarray)
    assert result.vectors.dtype == np.float64
    assert result.vectors.shape == (3, 3)
    assert result.usage.model == EMBEDDING
    assert result.usage.output_tokens == 0
    assert result.usage.cost_usd == pytest.approx(result.usage.input_tokens * 0.02 / 1_000_000)
    assert result.usage.cost_usd > 0.0


def test_embed_empty_input_makes_no_call(harness: Harness) -> None:
    before = harness.calls(EMBEDDING)
    result = harness.backend.embed([], EMBEDDING)
    assert result.vectors.shape[0] == 0
    assert result.usage.tokens == 0
    if harness.stub is not None:
        assert harness.calls(EMBEDDING) == before


def test_fake_embeddings_are_deterministic_and_unit_length() -> None:
    a = FakeBackend(rates=RATES, dim=16).embed(["hello", "world"], EMBEDDING).vectors
    b = FakeBackend(rates=RATES, dim=16).embed(["hello", "world"], EMBEDDING).vectors
    np.testing.assert_array_equal(a, b)
    np.testing.assert_allclose(np.linalg.norm(a, axis=1), 1.0)
    assert not np.allclose(a[0], a[1])


# --- call counting (tiebreak volume) ------------------------------------------------


def test_calls_are_counted_per_model(harness: Harness) -> None:
    harness.backend.classify(batch_of(IDS[:4]), CLASSIFIER)
    harness.backend.classify(batch_of(IDS[:2]), TIEBREAK)
    harness.backend.classify(batch_of(IDS[2:4]), TIEBREAK)
    harness.backend.embed(["x"], EMBEDDING)
    assert harness.calls(CLASSIFIER) == 1
    assert harness.calls(TIEBREAK) == 2
    assert harness.calls(EMBEDDING) == 1


def test_fake_records_batches_and_kinds() -> None:
    fake = FakeBackend(
        _fixture_labels(), rates=RATES, answers={"TopicName": {"name": "n", "keywords": []}}
    )
    fake.classify(batch_of(IDS[:2]), CLASSIFIER)
    fake.classify(batch_of(IDS[:1]), TIEBREAK)
    fake.complete_json("s", "u", TopicName, TIEBREAK)
    assert fake.batches == [(CLASSIFIER, IDS[:2]), (TIEBREAK, IDS[:1])]
    assert fake.calls_by_kind[("classify", TIEBREAK)] == 1
    assert fake.calls_by_kind[("TopicName", TIEBREAK)] == 1
    assert fake.calls[TIEBREAK] == 2
    tiebreak_mentions = sum(len(ids) for model, ids in fake.batches if model == TIEBREAK)
    assert tiebreak_mentions == 1


def test_fake_from_fixture_loads_labels() -> None:
    fake = FakeBackend.from_fixture(FIXTURE, rates=RATES)
    result = fake.classify(batch_of(IDS[:1]), CLASSIFIER)
    assert result.observations[0].label == "positive"


# --- rates table and import discipline -------------------------------------------------


def test_coerce_rates_accepts_config_shapes() -> None:
    rates = coerce_rates(
        {
            "a": {"input": 1.0, "output": 2.0, "dated": "2026-09-02"},
            "b": {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 4.0},
            "c": (5.0, 6.0),
            "d": Rate(input_usd_per_mtok=7.0, output_usd_per_mtok=8.0),
        }
    )
    assert rates["a"].input_usd_per_mtok == 1.0 and rates["a"].output_usd_per_mtok == 2.0
    assert rates["b"].input_usd_per_mtok == 3.0
    assert rates["c"].output_usd_per_mtok == 6.0
    assert rates["d"].input_usd_per_mtok == 7.0
    with pytest.raises(LlmRateError):
        coerce_rates({"e": {"price": 1.0}})


def test_load_rates_prices_the_design_models() -> None:
    rates = base.load_rates()
    for model in (CLASSIFIER, TIEBREAK):
        assert model in rates, f"{model} must be priced (config.LLM_RATES or fallback)"
        assert rates[model].input_usd_per_mtok > 0.0


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_only_openai_backend_imports_openai() -> None:
    for name in ("__init__.py", "base.py", "fake.py"):
        assert "openai" not in _imported_modules(SRC / name), name
    assert "openai" in _imported_modules(SRC / "openai_backend.py")


def test_fake_and_backend_satisfy_protocol() -> None:
    assert isinstance(FakeBackend(rates=RATES), base.LlmBackend)
    with httpx2.Client(
        transport=httpx2.MockTransport(make_handler(StubState(labels={})))
    ) as client:
        assert isinstance(
            OpenAIBackend("sk-stub", rates=RATES, http_client=client), base.LlmBackend
        )
