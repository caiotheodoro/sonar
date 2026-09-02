"""Label cache: ``.sonar/cache/labels.jsonl`` keyed by ``(mention_id, prompt_rev, model)``.

CONTRACTS §Label: ``status=cached`` when served from the label cache keyed by
``(mention_id, prompt_rev, classifier model)``. Only ``ok`` classifier
observations are stored, so a refusal or an error is retried on the next run.
Tiebreak observations are never cached: ``Receipt.audit.tiebreak_calls`` counts
calls made, and ``n_sample`` (audit rows with an ``ok`` tiebreak) may not exceed
it, which a cached tiebreak would break.

The key carries no brand, as CONTRACTS states it: a mention kept for two
brands reuses the first brand's observation (``about_brand`` included) for the
second. ``brand`` is stored on the row for audit so that a later DECISIONS
entry can key by it without a format change.

One JSON object per line; the file is append-only and the last row for a key
wins on load. A row that does not parse raises with its line number: a cache
that lies is worse than no cache.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

from sonar.llm.base import LabelObservation

CACHE_DIR: Final[Path] = Path(".sonar") / "cache"
CACHE_PATH: Final[Path] = CACHE_DIR / "labels.jsonl"

CacheKey = tuple[str, str, str]


class CacheRow(BaseModel):
    """One line of ``labels.jsonl``; ``brand`` is carried for audit, not part of the key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mention_id: str
    prompt_rev: str
    model: str
    brand: str
    observation: LabelObservation

    @property
    def key(self) -> CacheKey:
        return (self.mention_id, self.prompt_rev, self.model)


class LabelCache:
    """In-memory view of the JSONL file with append-through writes."""

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self._path = path
        self._rows: dict[CacheKey, CacheRow] = {}
        self.hits = 0
        self.misses = 0
        if path.exists():
            self._load()

    @property
    def path(self) -> Path:
        return self._path

    def __len__(self) -> int:
        return len(self._rows)

    def _load(self) -> None:
        with self._path.open(encoding="utf-8") as handle:
            for lineno, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = CacheRow.model_validate_json(line)
                except ValidationError as exc:
                    raise ValueError(f"{self._path}:{lineno}: bad cache row: {exc}") from exc
                if row.observation.status != "ok":
                    raise ValueError(f"{self._path}:{lineno}: cache holds a non-ok observation")
                self._rows[row.key] = row

    def get(self, mention_id: str, prompt_rev: str, model: str) -> LabelObservation | None:
        row = self._rows.get((mention_id, prompt_rev, model))
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return row.observation

    def put(
        self,
        mention_id: str,
        prompt_rev: str,
        model: str,
        brand: str,
        observation: LabelObservation,
    ) -> None:
        if observation.status != "ok":
            return
        if observation.mention_id != mention_id:
            raise ValueError("observation.mention_id must match the cache key")
        row = CacheRow(
            mention_id=mention_id,
            prompt_rev=prompt_rev,
            model=model,
            brand=brand,
            observation=observation,
        )
        self._rows[row.key] = row
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False) + "\n")


__all__ = ["CACHE_DIR", "CACHE_PATH", "CacheKey", "CacheRow", "LabelCache"]
