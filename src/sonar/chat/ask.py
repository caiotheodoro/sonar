"""``sonar ask``: one question against one session's store, answered through the seam and gated.

Flow (design Pipeline rules, CONTRACTS §Answer):

1. The relevant rows of the brand. None: ``refused`` with ``retrieved=[]`` and
   no seam call.
2. Retrieval: top-20 by cosine (lexical fallback, stated) plus the stats
   summary and the topic table as context.
3. ``complete_json`` against :class:`AnswerSchema`. A refusal is ``refused``.
4. Gates in code: every citation must be a ``mention_id`` in the store, every
   number must occur in stats, topics or a retrieved mention. A miss on either
   re-asks once with the offending ids and numbers listed; a second miss
   strips the unknown citations and sets ``status=unverified``. Output that
   does not fit the schema is re-asked once the same way; a second such
   failure is ``unverified`` with an empty answer.
5. The ``Answer`` line is appended to ``answers.jsonl`` with the usage of every
   seam call (embedding included) so ``reconcile`` can fold it into ``llm_usd``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from sonar import config
from sonar.chat.gates import available_numbers, citations_gate, numbers_gate, strip_citations
from sonar.chat.retrieve import Retrieval, retrieve
from sonar.chat.store import ANSWERS_JSONL, SessionStore
from sonar.llm.base import LlmBackend, LlmRefusal, LlmUnparseable
from sonar.llm.base import Usage as SeamUsage
from sonar.models import Answer, AnswerStatus, Mention, StatsFile, Topic, Usage
from sonar.report.markdown import (
    by_source_table,
    ci_cell,
    sentiment_table,
    share_cell,
    sov_table,
    table,
    text_cell,
)

MAX_ATTEMPTS: Final[int] = 2
"""One answer plus one re-ask when a gate or the schema rejects it."""

ANSWER_MAX_WORDS: Final[int] = 150

SYSTEM_PROMPT: Final[str] = f"""\
You answer questions about one brand from a brand-listening session.
Use only the context you are given: the stats summary, the topic table and the retrieved \
mentions. Answer in English, plain prose, at most {ANSWER_MAX_WORDS} words.
Cite mentions by writing their mention_id in square brackets inside the answer, like \
[<mention_id>], and list every cited mention_id in `citations`. Cite only ids that appear in \
the retrieved mentions; never invent an id.
Every number you write must be copied from the context as written (stats, topics or a \
mention), with at most two decimals; never compute, convert, estimate or invent a number. \
A share written as 0.6 may be written as 60%. Do not write dates as digits.
If the context does not answer the question, say so in one sentence and cite nothing.\
"""


class AnswerSchema(BaseModel):
    """Structured output of the ask call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class AskResult:
    """The record written, what was retrieved, and how many seam answers it took."""

    answer: Answer
    retrieval: Retrieval
    attempts: int
    note: str | None = None

    @property
    def cited(self) -> list[Mention]:
        return [m for m in self.retrieval.mentions if m.mention_id in self.answer.citations]


def _sum_usage(usages: Sequence[SeamUsage]) -> Usage:
    return Usage(tokens=sum(u.tokens for u in usages), cost_usd=sum(u.cost_usd for u in usages))


def stats_summary(stats: StatsFile | None) -> str:
    """The stats file as the digest's tables, without narration or quotes."""
    if stats is None:
        return "Stats: none (the session wrote no stats.json)."
    w = stats.window
    lines = [
        (
            f"Window: current {w.current.start.isoformat()} to {w.current.end.isoformat()}; "
            f"previous {w.previous.start.isoformat()} to {w.previous.end.isoformat()}."
        ),
        "Share of voice:",
        sov_table(stats.share_of_voice),
        "Sentiment:",
        sentiment_table(stats.sentiment),
        "By source:",
        by_source_table(stats.by_source),
        f"Events: {len(stats.events)}",
    ]
    return "\n".join(lines)


def topic_table(topics: Sequence[Topic]) -> str:
    if not topics:
        return "Topics: none."
    return table(
        ("topic", "brand", "name", "n", "clusters", "share", "net", "95 % CI"),
        [
            (
                t.topic_id,
                t.brand,
                text_cell(t.name),
                str(t.n),
                str(t.n_clusters),
                share_cell(t.share),
                share_cell(t.net),
                ci_cell(t.ci95),
            )
            for t in topics
        ],
    )


def mentions_context(mentions: Sequence[Mention]) -> str:
    rows = [
        {
            "mention_id": m.mention_id,
            "source": m.source,
            "published_at": None if m.published_at is None else m.published_at.isoformat(),
            "rating": m.rating,
            "text": m.text,
        }
        for m in mentions
    ]
    return json.dumps(rows, ensure_ascii=False)


def _user_message(
    brand: str,
    question: str,
    context: str,
    *,
    unknown: Sequence[str],
    foreign: Sequence[str],
    unparseable: bool,
) -> str:
    parts = [f"Brand: {brand}", context, f"Question: {question}"]
    if unknown:
        parts.append(
            "Your previous answer cited ids that are not in the session: "
            + ", ".join(unknown)
            + ". Cite only ids from the retrieved mentions."
        )
    if foreign:
        parts.append(
            "Your previous answer used numbers that are not in the context: "
            + ", ".join(foreign)
            + ". Remove them or replace them with numbers copied from the context."
        )
    if unparseable:
        parts.append(
            "Your previous answer did not fit the schema; return `answer` and `citations`."
        )
    return "\n\n".join(parts)


def _record(
    store: SessionStore,
    brand: str,
    question: str,
    *,
    model: str,
    text: str,
    citations: Sequence[str],
    verified: Sequence[str],
    retrieved: Sequence[str],
    usages: Sequence[SeamUsage],
    status: AnswerStatus,
) -> Answer:
    return Answer(
        session_id=store.session_id,
        brand=brand,
        question=question,
        answer=text,
        citations=list(citations),
        verified_numbers=list(verified),
        retrieved=list(retrieved),
        model=model,
        usage=_sum_usage(usages),
        status=status,
    )


def ask(
    store: SessionStore,
    brand: str,
    question: str,
    backend: LlmBackend | None,
    *,
    model: str | None = None,
    embedding_model: str | None = None,
    top_k: int = config.CHAT_TOP_K,
) -> AskResult:
    """Answer *question* about *brand* from *store*; see the module docstring for the flow.

    *backend* may be ``None`` only when the store holds no relevant row for the
    brand: that answer is ``refused`` without a seam call. A store with rows
    and no backend is a caller error.
    """
    model = model or config.LLM.classifier_model
    rows = store.rows(brand)
    mentions = [m for m, _ in rows]
    if not mentions:
        empty = Retrieval(mentions=(), method="lexical", usage=(), note=None, candidates=0)
        answer = _record(
            store,
            brand,
            question,
            model=model,
            text="",
            citations=(),
            verified=(),
            retrieved=(),
            usages=(),
            status="refused",
        )
        return AskResult(
            answer=answer, retrieval=empty, attempts=0, note="empty store: no seam call"
        )

    if backend is None:
        raise ValueError(f"{len(mentions)} relevant mention(s) for {brand!r} but no backend")
    retrieval = retrieve(store, mentions, question, backend, model=embedding_model, top_k=top_k)
    context = "\n\n".join(
        [
            stats_summary(store.stats),
            "Topics:",
            topic_table(store.topics),
            "Retrieved mentions (JSON):",
            mentions_context(retrieval.mentions),
        ]
    )
    available = available_numbers(store.stats, store.topics, retrieval.mentions)
    known = store.mention_ids
    usages: list[SeamUsage] = list(retrieval.usage)

    text = ""
    kept: tuple[str, ...] = ()
    verified: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    foreign: tuple[str, ...] = ()
    unparseable = False
    status: AnswerStatus = "unverified"
    note: str | None = None
    attempts = 0
    while attempts < MAX_ATTEMPTS:
        attempts += 1
        user = _user_message(
            brand, question, context, unknown=unknown, foreign=foreign, unparseable=unparseable
        )
        try:
            result = backend.complete_json(SYSTEM_PROMPT, user, AnswerSchema, model)
        except LlmRefusal as exc:
            text, kept, verified = "", (), ()
            status = "refused"
            note = f"model refused: {str(exc)[:120]}"
            break
        except LlmUnparseable as exc:
            unparseable = True
            text, kept, verified = "", (), ()
            note = f"model output did not fit the schema: {str(exc)[:120]}"
            continue
        usages.append(result.usage)
        unparseable = False
        note = None
        cites = citations_gate(result.value.citations, known)
        numbers = numbers_gate(result.value.answer, available)
        text = strip_citations(result.value.answer, cites.unknown)
        kept, unknown = cites.kept, cites.unknown
        verified, foreign = numbers.verified, numbers.foreign
        if cites.passed and numbers.passed:
            status = "ok"
            break
        status = "unverified"
        note = "gate: " + "; ".join(
            part
            for part in (
                f"unknown citations {list(unknown)}" if unknown else "",
                f"unverifiable numbers {list(foreign)}" if foreign else "",
            )
            if part
        )
    answer = _record(
        store,
        brand,
        question,
        model=model,
        text=text,
        citations=kept,
        verified=verified,
        retrieved=retrieval.ids,
        usages=usages,
        status=status,
    )
    return AskResult(answer=answer, retrieval=retrieval, attempts=attempts, note=note)


def append_answer(session_dir: Path, answer: Answer) -> Path:
    """Append one ``Answer`` line to the session's ``answers.jsonl``."""
    path = session_dir / ANSWERS_JSONL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(answer.model_dump_json() + "\n")
    return path


def read_answers(session_dir: Path) -> list[Answer]:
    path = session_dir / ANSWERS_JSONL
    if not path.is_file():
        return []
    return [
        Answer.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def render_answer(result: AskResult, store: SessionStore) -> str:
    """The answer with ``[n]`` markers and one footnote per citation: source and url."""
    answer = result.answer
    if answer.status == "refused":
        body = (
            f"No relevant mentions for {answer.brand} in session {answer.session_id}; "
            "nothing to answer from."
            if result.attempts == 0
            else "The model declined to answer."
        )
    elif not answer.answer:
        body = "No answer: the model's output did not fit the schema twice."
    else:
        body = answer.answer
        for index, cited in enumerate(answer.citations, start=1):
            body = body.replace(f"[{cited}]", f"[{index}]")
    lines = [body]
    if answer.citations:
        lines.append("")
        for index, cited in enumerate(answer.citations, start=1):
            mention = store.by_id(cited)
            source = mention.source if mention is not None else "unknown"
            url = mention.url if mention is not None and mention.url else "no url"
            lines.append(f"[{index}] {source}: {url}")
    lines.append("")
    lines.append(result.retrieval.describe())
    status_line = (
        f"status {answer.status}; citations {len(answer.citations)}; "
        f"numbers verified {len(answer.verified_numbers)}; model {answer.model}; "
        f"usage {answer.usage.tokens} tokens ${answer.usage.cost_usd:.4f}"
    )
    if result.note:
        status_line += f"; {result.note}"
    lines.append(status_line)
    return "\n".join(lines)


__all__ = [
    "ANSWER_MAX_WORDS",
    "MAX_ATTEMPTS",
    "SYSTEM_PROMPT",
    "AnswerSchema",
    "AskResult",
    "append_answer",
    "ask",
    "mentions_context",
    "read_answers",
    "render_answer",
    "stats_summary",
    "topic_table",
]
