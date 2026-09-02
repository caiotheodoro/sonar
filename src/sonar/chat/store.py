"""The session store ``sonar ask`` reads: one session directory, loaded read-only.

``mentions.jsonl`` (one ``Mention`` per line), ``labels.jsonl`` (``{"brand",
"label"}`` per line, the pipeline's shape), ``stats.json`` (``StatsFile``) and
``topics.json`` (``list[Topic]``) come from the same directory ``sonar run``
wrote; ``embeddings.npy`` in that directory is the retrieval cache in the
topics layer's format and is written by :mod:`sonar.chat.retrieve` the first
time a question is embedded. A missing artifact is an empty store, not an
error; a directory with none of them and no receipt is not a session.

The session id is the receipt's when ``receipt.json`` is present, else the
directory name, which must then be a CONTRACTS session id.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

from sonar.models import Label, Mention, Receipt, StatsFile, Topic
from sonar.pipeline import LABELS_JSONL, MENTIONS_JSONL, RECEIPT_JSON, STATS_JSON, TOPICS_JSON
from sonar.topics import CACHE_FILENAME, Row, is_relevant

ANSWERS_JSONL: Final[str] = "answers.jsonl"
"""One ``Answer`` per line, appended by every ``sonar ask`` (CONTRACTS §Answer)."""
EMBEDDINGS_NPY: Final[str] = CACHE_FILENAME
"""The retrieval cache next to the other artifacts (``embeddings.npy``)."""

_SESSION_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-\S+-[0-9a-f]{6}$")
_TOPICS_ADAPTER: TypeAdapter[list[Topic]] = TypeAdapter(list[Topic])


class StoreError(ValueError):
    """The directory is not a session, or one of its artifacts does not parse."""


def brand_key(brand: str) -> str:
    """Brands compare case-insensitively after whitespace collapse."""
    return " ".join(brand.split()).casefold()


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _session_id_for(session_dir: Path) -> str:
    receipt_path = session_dir / RECEIPT_JSON
    if receipt_path.is_file():
        try:
            return Receipt.model_validate_json(receipt_path.read_text(encoding="utf-8")).session_id
        except ValidationError as exc:
            raise StoreError(f"{receipt_path} is not a receipt: {exc}") from exc
    name = session_dir.name
    if not _SESSION_ID_RE.match(name):
        raise StoreError(
            f"{session_dir} has no receipt.json and its name is not a session id: {name!r}"
        )
    return name


@dataclass(frozen=True)
class SessionStore:
    """Everything one session wrote that a question may draw on."""

    session_dir: Path
    session_id: str
    mentions: tuple[Mention, ...]
    labels: Mapping[tuple[str, str], Label]
    stats: StatsFile | None
    topics: tuple[Topic, ...]

    @classmethod
    def load(cls, session_dir: Path) -> SessionStore:
        if not session_dir.is_dir():
            raise StoreError(f"session directory not found: {session_dir}")
        present = [
            name
            for name in (RECEIPT_JSON, MENTIONS_JSONL, LABELS_JSONL, STATS_JSON, TOPICS_JSON)
            if (session_dir / name).is_file()
        ]
        if not present:
            raise StoreError(f"{session_dir} holds no session artifacts")
        session_id = _session_id_for(session_dir)
        try:
            mentions = tuple(
                Mention.model_validate_json(line)
                for line in _read_lines(session_dir / MENTIONS_JSONL)
            )
            labels: dict[tuple[str, str], Label] = {}
            for line in _read_lines(session_dir / LABELS_JSONL):
                row = json.loads(line)
                if not isinstance(row, dict) or "brand" not in row or "label" not in row:
                    raise StoreError(f"{LABELS_JSONL}: a line is not {{brand, label}}")
                label = Label.model_validate(row["label"])
                labels[(brand_key(str(row["brand"])), label.mention_id)] = label
            stats_path = session_dir / STATS_JSON
            stats = (
                StatsFile.model_validate_json(stats_path.read_text(encoding="utf-8"))
                if stats_path.is_file()
                else None
            )
            topics_path = session_dir / TOPICS_JSON
            topics = (
                tuple(_TOPICS_ADAPTER.validate_json(topics_path.read_text(encoding="utf-8")))
                if topics_path.is_file()
                else ()
            )
        except (ValidationError, ValueError) as exc:
            raise StoreError(f"{session_dir}: {exc}") from exc
        return cls(
            session_dir=session_dir,
            session_id=session_id,
            mentions=mentions,
            labels=labels,
            stats=stats,
            topics=topics,
        )

    @property
    def mention_ids(self) -> frozenset[str]:
        """Every ``mention_id`` in the store, the set a citation must belong to."""
        return frozenset(m.mention_id for m in self.mentions)

    @property
    def brands(self) -> tuple[str, ...]:
        """Brands with at least one mention, in first-seen order."""
        seen: dict[str, str] = {}
        for m in self.mentions:
            seen.setdefault(brand_key(m.brand), m.brand)
        return tuple(seen.values())

    def by_id(self, mention_id: str) -> Mention | None:
        for m in self.mentions:
            if m.mention_id == mention_id:
                return m
        return None

    def rows(self, brand: str) -> list[Row]:
        """The relevant ``(Mention, Label)`` rows of *brand*, one per mention id."""
        key = brand_key(brand)
        out: list[Row] = []
        seen: set[str] = set()
        for m in self.mentions:
            if brand_key(m.brand) != key or m.mention_id in seen:
                continue
            label = self.labels.get((key, m.mention_id))
            if label is None:
                continue
            row: Row = (m, label)
            if is_relevant(row):
                seen.add(m.mention_id)
                out.append(row)
        return out


__all__ = [
    "ANSWERS_JSONL",
    "EMBEDDINGS_NPY",
    "SessionStore",
    "StoreError",
    "brand_key",
]
