"""``sonar ask <brand> ["question"] [--session DIR]``: the CLI face of the brand assistant.

With a question, one answer is printed and appended to the session's
``answers.jsonl``; without one, a REPL reads questions from stdin until EOF,
an empty line, ``exit`` or ``quit``. Without ``--session`` the newest session
under ``--root`` (the ``out/<session-id>/`` layout) is used.

The seam backend is built only when a question needs a model call, so an
empty store answers with no key and no client (the same rule as ``plan``).
Exit codes: ``2`` for a missing session, a store that does not parse, or a
missing OpenAI key when a call is needed; ``0`` otherwise, whatever the
answer's status.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final, TextIO

from sonar.chat.ask import append_answer, ask, render_answer
from sonar.chat.store import SessionStore, StoreError, brand_key
from sonar.llm.base import LlmBackend
from sonar.pipeline import EXIT_OK, EXIT_USAGE, RECEIPT_JSON

REPL_PROMPT: Final[str] = "sonar ask> "
REPL_EXIT_WORDS: Final[frozenset[str]] = frozenset({"exit", "quit"})
LlmFactory = Callable[[str], LlmBackend]


def register(
    sub: argparse._SubParsersAction[argparse.ArgumentParser],
    common: argparse.ArgumentParser,
    *,
    default_root: Path,
) -> None:
    """Add the ``ask`` subcommand to the CLI's subparsers."""
    parser = sub.add_parser("ask", parents=[common], help="ask the session's brand assistant")
    parser.add_argument("brand", help="brand the session was run for")
    parser.add_argument(
        "question", nargs="?", default=None, help="the question; omit for a REPL on stdin"
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=None,
        metavar="DIR",
        help="session directory (default: the newest under --root)",
    )
    parser.add_argument("--root", type=Path, default=default_root, help="sessions root")


def newest_session(root: Path) -> Path | None:
    """The last session directory under *root* by name (session ids sort by timestamp)."""
    if not root.is_dir():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir() and (p / RECEIPT_JSON).is_file())
    return candidates[-1] if candidates else None


class _LazyBackend:
    """Builds the seam once, the first time a question needs it; ``None`` without a key."""

    def __init__(self, openai_key: str | None, factory: LlmFactory) -> None:
        self._key = openai_key
        self._factory = factory
        self._backend: LlmBackend | None = None

    def get(self) -> LlmBackend | None:
        if self._backend is None and self._key is not None:
            self._backend = self._factory(self._key)
        return self._backend


def _answer_one(
    store: SessionStore,
    brand: str,
    question: str,
    backend: _LazyBackend,
    *,
    out: TextIO,
) -> int:
    seam: LlmBackend | None = None
    if store.rows(brand):
        seam = backend.get()
        if seam is None:
            print("no OpenAI key: set OPENAI_API_KEY or add it to ~/.sonar/.env", file=out)
            return EXIT_USAGE
    result = ask(store, brand, question, seam)
    print(render_answer(result, store), file=out)
    path = append_answer(store.session_dir, result.answer)
    print(f"wrote {path}", file=out)
    return EXIT_OK


def cmd_ask(
    args: argparse.Namespace,
    *,
    out: TextIO,
    openai_key: str | None,
    llm_factory: LlmFactory,
    inp: TextIO | None = None,
) -> int:
    session_dir: Path | None = args.session
    if session_dir is None:
        session_dir = newest_session(args.root)
        if session_dir is None:
            print(f"no session under {args.root}; pass --session DIR", file=out)
            return EXIT_USAGE
    try:
        store = SessionStore.load(session_dir)
    except StoreError as exc:
        print(f"cannot load session: {exc}", file=out)
        return EXIT_USAGE
    brand: str = args.brand
    if store.brands and brand_key(brand) not in {brand_key(b) for b in store.brands}:
        print(
            f"note: {brand} has no mentions in {store.session_id}; brands here: "
            + ", ".join(store.brands),
            file=out,
        )
    backend = _LazyBackend(openai_key, llm_factory)
    question: str | None = args.question
    if question is not None and question.strip():
        return _answer_one(store, brand, question.strip(), backend, out=out)

    stream = inp if inp is not None else sys.stdin
    print(f"session {store.session_id}; brand {brand}; empty line, exit or quit ends", file=out)
    while True:
        print(REPL_PROMPT, end="", file=out, flush=True)
        line = stream.readline()
        if not line:
            break
        question = line.strip()
        if not question or question.casefold() in REPL_EXIT_WORDS:
            break
        code = _answer_one(store, brand, question, backend, out=out)
        if code != EXIT_OK:
            return code
    print(file=out)
    return EXIT_OK


__all__ = ["REPL_EXIT_WORDS", "REPL_PROMPT", "cmd_ask", "newest_session", "register"]
