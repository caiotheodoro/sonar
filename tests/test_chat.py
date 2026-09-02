"""Chat layer tests (W5.2): store, retrieval, gates, ``ask``, ``answers.jsonl``, CLI and REPL.

Uses the fake llm seam; the CLI tests also drive ``sonar ask`` on the offline
fixture session. No network, no real model.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sonar import cli, config
from sonar.chat import (
    ANSWERS_JSONL,
    EMBEDDINGS_NPY,
    MAX_ATTEMPTS,
    AnswerSchema,
    SessionStore,
    StoreError,
    append_answer,
    ask,
    available_numbers,
    citations_gate,
    clean_for_numbers,
    extract_numbers,
    numbers_gate,
    read_answers,
    render_answer,
    retrieve,
    strip_citations,
)
from sonar.chat.command import cmd_ask, newest_session
from sonar.llm.base import EmbedResult, JsonResult, LlmError
from sonar.llm.fake import FakeBackend
from sonar.models import (
    Answer,
    BySourceEntry,
    DateRange,
    Label,
    Mention,
    SentimentEntry,
    SovEntry,
    StatsFile,
    Topic,
    TopicMethod,
    Window,
    WowNet,
    WowShare,
    mention_id_for,
)

NOW = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)
SESSION_ID = "20260902T120000Z-nubank-c0ffee"
BRAND = "Nubank"
FAKE_ID = "f" * 24


# -- factories ---------------------------------------------------------------------


def mention(key: str, *, brand: str = BRAND, **overrides: Any) -> Mention:
    base: dict[str, Any] = {
        "mention_id": mention_id_for("reddit", key),
        "brand": brand,
        "source": "reddit",
        "run_id": "01RUN1",
        "native_id": key,
        "url": f"https://reddit.com/r/x/comments/{key}",
        "author_hash": None,
        "text": f"{brand} card limit went up after the {key} update",
        "lang": "en",
        "published_at": NOW - timedelta(days=1),
        "engagement": {"upvotes": 3},
        "rating": None,
        "cluster_key": key,
        "matched_terms": [brand.lower()],
        "raw_ref": "1#0",
    }
    base.update(overrides)
    return Mention.model_validate(base)


def label(mid: str, **overrides: Any) -> Label:
    base: dict[str, Any] = {
        "mention_id": mid,
        "label": "positive",
        "about_brand": True,
        "confidence": 0.9,
        "rationale": "praises the card",
        "topic_id": None,
        "signals": {
            "classifier": {
                "model": config.LLM.classifier_model,
                "label": "positive",
                "confidence": 0.9,
                "status": "ok",
            },
            "tiebreak": None,
            "deterministic": {"kind": "lexicon", "label": "positive"},
            "overflow": False,
        },
        "corroboration": "confirmed",
        "decided_by": "classifier",
        "prompt_rev": config.PROMPT_REV,
        "status": "ok",
        "usage": {"tokens": 100, "cost_usd": 0.0001},
    }
    base.update(overrides)
    return Label.model_validate(base)


def make_stats(brand: str = BRAND) -> StatsFile:
    start = NOW - timedelta(days=7)
    return StatsFile(
        share_of_voice=[
            SovEntry(
                brand=brand,
                n=30,
                n_clusters=10,
                share=0.6,
                ci95=(0.5, 0.7),
                basis_sources=["reddit"],
                wow=WowShare(
                    delta=0.05, ci95=(0.01, 0.09), verdict="SUGGESTIVE", p_raw=0.03, p_holm=0.06
                ),
            )
        ],
        sentiment=[
            SentimentEntry(
                brand=brand,
                n=30,
                n_confirmed=20,
                pos=15,
                neg=5,
                neu=10,
                net=0.5,
                ci95=(0.2, 0.8),
                ci95_iid=(0.25, 0.75),
                design_effect=1.44,
                wow=WowNet(
                    delta=0.1,
                    ci95=(-0.05, 0.25),
                    ci95_confirmed_only=(-0.03, 0.2),
                    verdict="NO_CHANGE_DETECTED",
                    p_raw=0.15,
                    p_holm=0.3,
                ),
            )
        ],
        by_source=[
            BySourceEntry(
                brand=brand,
                source="reddit",
                n=20,
                n_clusters=8,
                pos=10,
                neg=3,
                neu=7,
                net=0.43,
                ci95=(0.1, 0.7),
                ci95_iid=(0.1, 0.7),
                design_effect=1.0,
                wow_scope=True,
            )
        ],
        events=[],
        window=Window(
            current=DateRange(start=start, end=NOW),
            previous=DateRange(start=start - timedelta(days=7), end=start),
        ),
    )


def make_topic(ids: Sequence[str], brand: str = BRAND) -> Topic:
    return Topic(
        topic_id="nubank-00",
        brand=brand,
        name="Card limit changes",
        n=15,
        n_clusters=6,
        share=0.5,
        net=0.3,
        ci95=(0.0, 0.6),
        exemplar_mention_ids=list(ids[:3]),
        method=TopicMethod(
            embedding_model=config.LLM.embedding_model,
            linkage="average",
            threshold=config.TOPIC_DISTANCE_THRESHOLD,
            min_size=3,
            min_breadth=2,
        ),
    )


def write_session(
    root: Path,
    mentions: Sequence[Mention],
    *,
    stats: StatsFile | None = None,
    topics: Sequence[Topic] = (),
    session_id: str = SESSION_ID,
) -> Path:
    session_dir = root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "mentions.jsonl").write_text(
        "".join(m.model_dump_json() + "\n" for m in mentions), encoding="utf-8"
    )
    (session_dir / "labels.jsonl").write_text(
        "".join(
            json.dumps({"brand": m.brand, "label": label(m.mention_id).model_dump(mode="json")})
            + "\n"
            for m in mentions
        ),
        encoding="utf-8",
    )
    if stats is not None:
        (session_dir / "stats.json").write_text(stats.model_dump_json(), encoding="utf-8")
    if topics:
        (session_dir / "topics.json").write_text(
            json.dumps([t.model_dump(mode="json") for t in topics]), encoding="utf-8"
        )
    return session_dir


class ScriptedFake(FakeBackend):
    """``FakeBackend`` whose ``complete_json`` answers come from a list, in order."""

    def __init__(self, answers: Sequence[Mapping[str, Any]]) -> None:
        super().__init__()
        self._script = list(answers)
        self.users: list[str] = []

    def complete_json(
        self, system: str, user: str, schema: type[Any], model: str
    ) -> JsonResult[Any]:
        self.users.append(user)
        if self._script:
            self._answers[schema.__name__] = self._script.pop(0)
        result: JsonResult[Any] = super().complete_json(system, user, schema, model)
        return result


class NoEmbedFake(ScriptedFake):
    def embed(self, texts: Sequence[str], model: str) -> EmbedResult:
        raise LlmError("embedding endpoint down")


@pytest.fixture
def session(tmp_path: Path) -> tuple[Path, list[Mention]]:
    mentions = [
        mention(f"p{i}", text=f"Nubank {'limit' if i % 2 else 'app'} post {i}") for i in range(6)
    ]
    mentions.append(mention("q0", brand="Inter", text="Inter post", matched_terms=["inter"]))
    ids = [m.mention_id for m in mentions]
    session_dir = write_session(tmp_path, mentions, stats=make_stats(), topics=[make_topic(ids)])
    return session_dir, mentions


def total_calls(fake: FakeBackend) -> int:
    return sum(fake.calls.values())


# -- store -----------------------------------------------------------------------------


class TestStore:
    def test_loads_every_artifact_and_relevant_rows_per_brand(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        assert store.session_id == SESSION_ID
        assert store.brands == (BRAND, "Inter")
        assert len(store.rows(BRAND)) == 6 and len(store.rows("inter")) == 1
        assert store.rows("Avenza") == []
        assert store.stats is not None and len(store.topics) == 1
        assert store.mention_ids == {m.mention_id for m in mentions}

    def test_not_a_session_or_bad_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StoreError):
            SessionStore.load(tmp_path / "missing")
        (tmp_path / "plain").mkdir()
        with pytest.raises(StoreError):
            SessionStore.load(tmp_path / "plain")
        odd = tmp_path / "not-a-session-id"
        odd.mkdir()
        (odd / "mentions.jsonl").write_text("", encoding="utf-8")
        with pytest.raises(StoreError, match="not a session id"):
            SessionStore.load(odd)


# -- gates -----------------------------------------------------------------------------


class TestGates:
    def test_extract_numbers_skips_ids_dates_and_word_digits(self) -> None:
        text = f"Share 0.6 [{FAKE_ID}] on 2026-09-02, 60% of v2 users, -0.27 net, $1,234.50"
        values = [t.value for t in extract_numbers(clean_for_numbers(text))]
        assert Decimal("0.6") in values and Decimal(60) in values
        assert Decimal("-0.27") in values and Decimal("1234.5") in values
        assert Decimal(2026) not in values and Decimal(2) not in values
        gate = numbers_gate(text, frozenset({Decimal("0.6"), Decimal("-0.27"), Decimal("1234.5")}))
        assert gate.verified == ("0.6", "60%", "-0.27", "$1,234.50") and gate.passed

    def test_rounded_match_half_up_and_bare_integer_exact(self) -> None:
        available = frozenset({Decimal("0.336"), Decimal("29.6")})
        assert numbers_gate("34% of posts", available).passed
        assert numbers_gate("0.34 share", available).passed
        assert not numbers_gate("30 posts", available).passed
        assert numbers_gate("30 posts", frozenset({Decimal(30)})).passed

    def test_available_numbers_come_from_stats_topics_and_mentions(self) -> None:
        stats, topic = make_stats(), make_topic(["a" * 24, "b" * 24, "c" * 24])
        m = mention("z9", text="Limit rose to 5000 reais", engagement={"upvotes": 17})
        available = available_numbers(stats, [topic], [m])
        assert {
            Decimal("0.6"),
            Decimal("1.44"),
            Decimal(15),
            Decimal(5000),
            Decimal(17),
        } <= available
        assert Decimal(2026) not in available

    def test_citations_gate_and_strip(self) -> None:
        real = "a" * 24
        gate = citations_gate([real, FAKE_ID, real, " "], {real})
        assert gate.kept == (real,) and gate.unknown == (FAKE_ID,)
        stripped = strip_citations(
            f"Fees rose [{real}] and [{FAKE_ID}] , see {FAKE_ID}.", [FAKE_ID]
        )
        assert stripped == f"Fees rose [{real}] and, see."


# -- retrieval ---------------------------------------------------------------------------


class TestRetrieval:
    def test_top_k_by_cosine_writes_the_session_cache(self, tmp_path: Path) -> None:
        mentions = [mention(f"m{i}", text=f"Nubank note {i}") for i in range(25)]
        store = SessionStore.load(write_session(tmp_path, mentions))
        fake = FakeBackend()
        result = retrieve(store, mentions, "what about notes?", fake, top_k=20)
        assert result.method == "cosine" and len(result.mentions) == 20
        assert result.candidates == 25 and result.usage and result.note is None
        assert (store.session_dir / EMBEDDINGS_NPY).is_file()
        assert fake.calls_by_kind[("embed", config.LLM.embedding_model)] == 1

    def test_lexical_fallback_is_stated_when_embedding_fails(self, tmp_path: Path) -> None:
        mentions = [mention("m0", text="Nubank fees doubled"), mention("m1", text="Nubank app")]
        store = SessionStore.load(write_session(tmp_path, mentions))
        result = retrieve(store, mentions, "why did fees double?", NoEmbedFake([]))
        assert result.method == "lexical" and result.note is not None
        assert "lexical fallback" in result.note and "LlmError" in result.note
        assert result.mentions[0].text == "Nubank fees doubled" and not result.usage


# -- ask -------------------------------------------------------------------------------


class TestAsk:
    def test_fabricated_id_is_stripped_and_marked_unverified(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        real = mentions[0].mention_id
        canned = {
            "answer": f"Limits rose [{real}] and fees too [{FAKE_ID}].",
            "citations": [real, FAKE_ID],
        }
        fake = ScriptedFake([canned, canned])
        result = ask(store, BRAND, "what changed?", fake)
        answer = result.answer
        assert answer.status == "unverified"
        assert answer.citations == [real] and FAKE_ID not in answer.answer
        assert answer.answer == f"Limits rose [{real}] and fees too."
        assert result.attempts == MAX_ATTEMPTS
        assert fake.calls_by_kind[("AnswerSchema", config.LLM.classifier_model)] == 2
        assert FAKE_ID in fake.users[1] and "not in the session" in fake.users[1]
        assert len(answer.retrieved) == 6 and answer.usage.tokens > 0

    def test_clean_second_answer_after_one_miss_is_ok(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        real = mentions[1].mention_id
        fake = ScriptedFake(
            [
                {"answer": f"Bad [{FAKE_ID}].", "citations": [FAKE_ID]},
                {"answer": f"Share of voice is 0.6 [{real}].", "citations": [real]},
            ]
        )
        result = ask(store, BRAND, "share?", fake)
        assert result.answer.status == "ok" and result.attempts == 2
        assert result.answer.citations == [real] and result.answer.verified_numbers == ["0.6"]

    def test_number_absent_from_stats_fails_the_gate(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        real = mentions[0].mention_id
        canned = {"answer": f"Share is 0.91 with 15 positives [{real}].", "citations": [real]}
        fake = ScriptedFake([canned, canned])
        result = ask(store, BRAND, "share?", fake)
        assert result.answer.status == "unverified"
        assert result.answer.verified_numbers == ["15"]
        assert result.note is not None and "0.91" in result.note
        assert "0.91" in fake.users[1] and "not in the context" in fake.users[1]

    def test_numbers_from_stats_topics_and_mentions_pass(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        real = mentions[2].mention_id
        fake = ScriptedFake(
            [{"answer": f"60% share, net 0.5, topic n 15, post 2 [{real}].", "citations": [real]}]
        )
        result = ask(store, BRAND, "numbers?", fake)
        assert result.answer.status == "ok"
        assert result.answer.verified_numbers == ["60%", "0.5", "15", "2"]

    def test_empty_store_makes_no_llm_call(self, tmp_path: Path) -> None:
        store = SessionStore.load(write_session(tmp_path, []))
        fake = FakeBackend()
        result = ask(store, BRAND, "anything?", fake)
        assert result.answer.status == "refused" and result.answer.answer == ""
        assert result.answer.retrieved == [] and result.answer.usage.tokens == 0
        assert total_calls(fake) == 0 and result.attempts == 0
        assert ask(store, BRAND, "again?", None).answer.status == "refused"

    def test_brand_without_rows_is_an_empty_store(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, _ = session
        fake = FakeBackend()
        result = ask(SessionStore.load(session_dir), "Avenza", "anything?", fake)
        assert result.answer.status == "refused" and total_calls(fake) == 0

    def test_refusal_maps_to_refused(self, session: tuple[Path, list[Mention]]) -> None:
        session_dir, _ = session
        fake = ScriptedFake([{"__refusal__": "cannot help"}])
        result = ask(SessionStore.load(session_dir), BRAND, "q?", fake)
        assert result.answer.status == "refused" and result.answer.answer == ""
        assert result.answer.citations == [] and len(result.answer.retrieved) == 6
        assert result.note is not None and "refused" in result.note

    def test_unparseable_twice_is_unverified_with_empty_answer(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, _ = session
        fake = ScriptedFake([{"answer": ""}, {"nope": 1}])
        result = ask(SessionStore.load(session_dir), BRAND, "q?", fake)
        assert result.answer.status == "unverified" and result.answer.answer == ""
        assert result.attempts == 2 and "did not fit the schema" in (result.note or "")

    def test_answers_jsonl_appends_a_line_with_usage(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        real = mentions[0].mention_id
        fake = ScriptedFake(
            [
                {"answer": f"One [{real}].", "citations": [real]},
                {"answer": "Two.", "citations": []},
            ]
        )
        for question in ("one?", "two?"):
            append_answer(session_dir, ask(store, BRAND, question, fake).answer)
        lines = (session_dir / ANSWERS_JSONL).read_text().splitlines()
        assert len(lines) == 2
        answers = [Answer.model_validate_json(line) for line in lines]
        assert answers == read_answers(session_dir)
        assert answers[0].usage.tokens > 0 and answers[0].usage.cost_usd > 0
        assert answers[0].session_id == SESSION_ID and answers[1].question == "two?"

    def test_answer_schema_is_answer_and_citations(self) -> None:
        assert set(AnswerSchema.model_fields) == {"answer", "citations"}
        assert issubclass(AnswerSchema, BaseModel)


# -- rendering ---------------------------------------------------------------------------


class TestRender:
    def test_citations_render_as_footnotes_with_source_and_url(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        store = SessionStore.load(session_dir)
        a, b = mentions[0].mention_id, mentions[3].mention_id
        fake = ScriptedFake(
            [{"answer": f"Limits rose [{a}]; the app changed [{b}].", "citations": [a, b]}]
        )
        result = ask(store, BRAND, "what?", fake)
        text = render_answer(result, store)
        assert "Limits rose [1]; the app changed [2]." in text
        assert f"[1] reddit: {mentions[0].url}" in text
        assert f"[2] reddit: {mentions[3].url}" in text
        assert "retrieval: cosine over 6 relevant mention(s), top 6" in text
        assert "status ok; citations 2" in text

    def test_empty_store_renders_a_reason(self, tmp_path: Path) -> None:
        store = SessionStore.load(write_session(tmp_path, []))
        text = render_answer(ask(store, BRAND, "q?", None), store)
        assert "No relevant mentions for Nubank" in text and "status refused" in text


# -- CLI -------------------------------------------------------------------------------


def invoke(argv: Sequence[str], **kwargs: Any) -> tuple[int, str]:
    out = io.StringIO()
    kwargs.setdefault("client_factory", _refuse_client)
    kwargs.setdefault("llm_factory", _refuse_llm)
    kwargs.setdefault("env", {"SONAR_ENV": "/nonexistent/.env"})
    code = cli.main(list(argv), out=out, err=io.StringIO(), **kwargs)
    return code, out.getvalue()


def _refuse_client(_key: str) -> Any:
    raise AssertionError("a Monid client was constructed by `ask`")


def _refuse_llm(_key: str) -> Any:
    raise AssertionError("a seam backend was constructed for an empty store")


ENV = {"OPENAI_API_KEY": "sk-test-0123456789"}


class TestCli:
    def test_ask_prints_footnotes_and_appends_answers_jsonl(
        self, session: tuple[Path, list[Mention]]
    ) -> None:
        session_dir, mentions = session
        real = mentions[0].mention_id
        fake = ScriptedFake([{"answer": f"Limits rose [{real}].", "citations": [real]}])
        code, text = invoke(
            ["ask", BRAND, "what changed?", "--session", str(session_dir)],
            llm_factory=lambda _key: fake,
            env=ENV,
        )
        assert code == 0, text
        assert "Limits rose [1]." in text and f"[1] reddit: {mentions[0].url}" in text
        assert f"wrote {session_dir / ANSWERS_JSONL}" in text
        assert read_answers(session_dir)[0].question == "what changed?"

    def test_empty_store_needs_no_key_and_no_backend(self, tmp_path: Path) -> None:
        session_dir = write_session(tmp_path, [])
        code, text = invoke(["ask", BRAND, "anything?", "--session", str(session_dir)])
        assert code == 0, text
        assert "status refused" in text and read_answers(session_dir)[0].status == "refused"

    def test_missing_key_with_rows_exits_2(self, session: tuple[Path, list[Mention]]) -> None:
        session_dir, _ = session
        code, text = invoke(["ask", BRAND, "q?", "--session", str(session_dir)])
        assert code == 2 and "no OpenAI key" in text

    def test_missing_session_exits_2(self, tmp_path: Path) -> None:
        code, text = invoke(["ask", BRAND, "q?", "--session", str(tmp_path / "nope")])
        assert code == 2 and "cannot load session" in text
        code, text = invoke(["ask", BRAND, "q?", "--root", str(tmp_path / "empty")])
        assert code == 2 and "no session under" in text

    def test_repl_answers_until_exit(self, session: tuple[Path, list[Mention]]) -> None:
        session_dir, mentions = session
        real = mentions[0].mention_id
        fake = ScriptedFake(
            [
                {"answer": f"One [{real}].", "citations": [real]},
                {"answer": "Two.", "citations": []},
            ]
        )
        args = cli.build_parser().parse_args(["ask", BRAND, "--session", str(session_dir)])
        assert args.question is None
        out = io.StringIO()
        code = cmd_ask(
            args,
            out=out,
            openai_key="sk-test",
            llm_factory=lambda _key: fake,
            inp=io.StringIO("one?\ntwo?\nexit\nnever asked\n"),
        )
        assert code == 0
        text = out.getvalue()
        assert text.count("sonar ask> ") == 3 and "One [1]." in text and "Two." in text
        assert [a.question for a in read_answers(session_dir)] == ["one?", "two?"]

    def test_newest_session_under_root(self, tmp_path: Path) -> None:
        assert newest_session(tmp_path / "none") is None
        for name in ("20260901T000000Z-a-000001", "20260902T000000Z-b-000002"):
            d = tmp_path / name
            d.mkdir()
            (d / "receipt.json").write_text("{}", encoding="utf-8")
        (tmp_path / "20260903T000000Z-c-000003").mkdir()
        found = newest_session(tmp_path)
        assert found is not None and found.name == "20260902T000000Z-b-000002"
