"""Build ``Topic`` records per brand from labelled mentions (CONTRACTS §Topic).

Deterministic edges, model in nodes: the model supplies embeddings and a
proposed name; every other decision is made here.

Per brand, in order:

1. Relevant rows: ``label.about_brand`` with a usable label status (``ok`` or
   ``cached``) and non-empty ``matched_terms``; one row per ``mention_id``,
   ordered by ``mention_id``.
2. Embeddings through the seam, cached to ``embeddings.npy``. Any failure
   abstains the brand's topics with reason ``embedding_failed``.
3. Average-linkage clusters on cosine distance at ``config.TOPIC_DISTANCE_THRESHOLD``;
   a cluster is a topic iff it has at least ``config.TOPIC_MIN_SIZE`` mentions and
   at least ``config.TOPIC_MIN_BREADTH`` distinct ``cluster_key`` values.
4. ``topic_id = "{brand slug}-{index:02d}"``, index by descending ``n``, ties by
   descending ``n_clusters`` then smallest ``mention_id``.
5. ``share = n / relevant`` and ``net = (pos - neg) / (pos + neg + neu)`` with a
   cluster bootstrap ``ci95`` on net. Both are left null, with one
   ``below_minimum`` abstention naming the topic, when the topic's polar labels
   (positive, negative, neutral) number fewer than ``TOPIC_MIN_SIZE`` or span
   fewer than ``TOPIC_MIN_BREADTH`` cluster keys; ``share`` is also null when
   the brand has no relevant rows, which cannot happen once a topic exists.
6. ``config.TOPIC_EXEMPLARS`` medoids, closest to the centroid first, are the
   exemplars and the naming model's input; the name is capped at
   ``config.TOPIC_NAME_MAX_WORDS`` words.

A brand with no topic gets one ``below_minimum`` abstention saying why. The
result also carries the ``(brand, mention_id) -> topic_id`` assignments for the
pipeline to write into ``Label.topic_id``, every seam ``Usage`` with its
``LlmKind``, and notes for ``Receipt.what_could_not_be_checked``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sonar import config
from sonar.llm.base import LlmBackend, Usage
from sonar.models import Abstention, Label, LlmKind, Mention, Topic, TopicMethod
from sonar.topics.cluster import average_linkage, cosine_distances, medoid_indices
from sonar.topics.embed import EmbeddingCache, embed_texts
from sonar.topics.estimate import PolarCounts, net_ci95, net_of, share_of
from sonar.topics.name import name_topic

USABLE_LABEL_STATUSES: frozenset[str] = frozenset({"ok", "cached"})
_NON_SLUG = re.compile(r"[^0-9a-z]+")
_DETAIL_MAX_CHARS = 500

Row = tuple[Mention, Label]


def brand_slug(brand: str) -> str:
    """Lowercase ASCII slug: NFKD, accents dropped, non-alphanumerics collapsed to ``-``."""
    decomposed = unicodedata.normalize("NFKD", brand)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").casefold()
    slug = _NON_SLUG.sub("-", ascii_only).strip("-")
    return slug or "brand"


def topic_id_for(brand: str, index: int) -> str:
    return f"{brand_slug(brand)}-{index:02d}"


def is_relevant(row: Row) -> bool:
    """CONTRACTS relevance: ``about_brand`` and a matched term, with a usable label."""
    mention, label = row
    return (
        label.about_brand
        and label.status in USABLE_LABEL_STATUSES
        and len(mention.matched_terms) > 0
        and label.mention_id == mention.mention_id
    )


@dataclass(frozen=True)
class TopicsResult:
    topics: list[Topic]
    assignments: dict[tuple[str, str], str]
    abstentions: list[Abstention]
    usages: list[tuple[LlmKind, Usage]]
    notes: list[str] = field(default_factory=list)
    embedding_cache_hits: int = 0
    embedding_cache_misses: int = 0

    @property
    def llm_usd(self) -> float:
        return sum(usage.cost_usd for _, usage in self.usages)

    def llm_calls(self) -> dict[LlmKind, int]:
        counts: dict[LlmKind, int] = {"embed": 0, "name_topic": 0}
        for kind, _ in self.usages:
            counts[kind] = counts.get(kind, 0) + 1
        return counts


@dataclass(frozen=True)
class _Cluster:
    rows: list[Row]

    @property
    def n(self) -> int:
        return len(self.rows)

    @property
    def n_clusters(self) -> int:
        return len({mention.cluster_key for mention, _ in self.rows})

    @property
    def first_mention_id(self) -> str:
        return min(mention.mention_id for mention, _ in self.rows)


def _abstain(brand: str, reason: str, detail: str) -> Abstention:
    return Abstention(
        scope="topics",
        brand=brand,
        source=None,
        reason=reason,  # type: ignore[arg-type]
        detail=detail[:_DETAIL_MAX_CHARS],
    )


def _brand_order(rows: Iterable[Row]) -> list[str]:
    seen: dict[str, None] = {}
    for mention, _ in rows:
        seen.setdefault(mention.brand, None)
    return list(seen)


def _relevant_rows(rows: Iterable[Row], brand: str) -> list[Row]:
    by_id: dict[str, Row] = {}
    for row in rows:
        mention, _ = row
        if mention.brand != brand or not is_relevant(row):
            continue
        by_id.setdefault(mention.mention_id, row)
    return [by_id[key] for key in sorted(by_id)]


def _polar_units(rows: Sequence[Row]) -> tuple[PolarCounts, list[PolarCounts], int]:
    """Cluster-wide polar counts, per-``cluster_key`` units, and the polar breadth."""
    per_unit: dict[str, PolarCounts] = {}
    polar_keys: set[str] = set()
    total = PolarCounts()
    for mention, label in rows:
        unit = per_unit.get(mention.cluster_key, PolarCounts())
        updated = unit.add(label.label)
        per_unit[mention.cluster_key] = updated
        total = total.add(label.label)
        if updated.total > unit.total:
            polar_keys.add(mention.cluster_key)
    units = [per_unit[key] for key in sorted(per_unit)]
    return total, units, len(polar_keys)


def build_topics(
    rows: Sequence[Row],
    backend: LlmBackend,
    *,
    embedding_model: str = config.LLM.embedding_model,
    naming_model: str = config.LLM.classifier_model,
    cache_path: Path | None = None,
    resamples: int = config.B,
    seed: int = config.SEED,
) -> TopicsResult:
    """Topics for every brand present in ``rows``; see the module docstring for the rules."""
    method = TopicMethod(embedding_model=embedding_model, threshold=config.TOPIC_DISTANCE_THRESHOLD)
    if (
        method.linkage != config.TOPIC_LINKAGE
        or method.min_size != config.TOPIC_MIN_SIZE
        or method.min_breadth != config.TOPIC_MIN_BREADTH
    ):
        raise ValueError(
            "config topic minimums disagree with CONTRACTS TopicMethod: "
            f"{config.TOPIC_LINKAGE!r}/{config.TOPIC_MIN_SIZE}/{config.TOPIC_MIN_BREADTH} "
            f"vs {method.linkage!r}/{method.min_size}/{method.min_breadth}"
        )
    cache = EmbeddingCache(cache_path)
    topics: list[Topic] = []
    assignments: dict[tuple[str, str], str] = {}
    abstentions: list[Abstention] = []
    usages: list[tuple[LlmKind, Usage]] = []
    notes: list[str] = []
    hits = 0
    misses = 0

    for brand in _brand_order(rows):
        relevant = _relevant_rows(rows, brand)
        if len(relevant) < method.min_size:
            abstentions.append(
                _abstain(
                    brand,
                    "below_minimum",
                    f"no topics: {len(relevant)} relevant mentions, min_size {method.min_size}",
                )
            )
            continue
        try:
            batch = embed_texts(backend, [m.text for m, _ in relevant], embedding_model, cache)
        except Exception as exc:  # noqa: BLE001 - the error matrix: embedding failure abstains
            abstentions.append(_abstain(brand, "embedding_failed", f"{type(exc).__name__}: {exc}"))
            continue
        usages.extend(("embed", usage) for usage in batch.usages)
        hits += batch.cache_hits
        misses += batch.cache_misses

        distances = cosine_distances(batch.vectors)
        candidates = [
            _Cluster([relevant[i] for i in members])
            for members in average_linkage(distances, method.threshold)
        ]
        kept = [
            c for c in candidates if c.n >= method.min_size and c.n_clusters >= method.min_breadth
        ]
        if not kept:
            largest = max((c.n for c in candidates), default=0)
            abstentions.append(
                _abstain(
                    brand,
                    "below_minimum",
                    f"no cluster met min_size {method.min_size} and min_breadth "
                    f"{method.min_breadth} over {len(relevant)} relevant mentions "
                    f"(largest cluster {largest})",
                )
            )
            continue
        kept.sort(key=lambda c: (-c.n, -c.n_clusters, c.first_mention_id))

        for index, cluster in enumerate(kept, start=1):
            topic_id = topic_id_for(brand, index)
            member_rows = {id(row): pos for pos, row in enumerate(relevant)}
            positions = [member_rows[id(row)] for row in cluster.rows]
            medoids = medoid_indices(batch.vectors, positions, config.TOPIC_EXEMPLARS)
            exemplar_rows = [relevant[i] for i in medoids]
            counts, units, polar_breadth = _polar_units(cluster.rows)

            share: float | None
            net: float | None
            ci95: tuple[float, float] | None
            if counts.total < method.min_size or polar_breadth < method.min_breadth:
                share, net, ci95 = None, None, None
                abstentions.append(
                    _abstain(
                        brand,
                        "below_minimum",
                        f"{topic_id}: {counts.total} labelled mentions over {polar_breadth} "
                        f"cluster keys; needs at least {method.min_size} over "
                        f"{method.min_breadth}",
                    )
                )
            else:
                share = share_of(cluster.n, len(relevant))
                net = net_of(counts)
                ci95 = net_ci95(units, resamples=resamples, seed=seed)
                if share is None or net is None or ci95 is None:
                    share, net, ci95 = None, None, None
                    abstentions.append(
                        _abstain(brand, "below_minimum", f"{topic_id}: estimate undefined")
                    )

            outcome = name_topic(
                backend,
                naming_model,
                brand=brand,
                index=index,
                n=cluster.n,
                exemplars=[m.text for m, _ in exemplar_rows],
            )
            if outcome.usage is not None:
                usages.append(("name_topic", outcome.usage))
            if outcome.failure is not None:
                notes.append(f"topic naming fell back for {topic_id}: {outcome.failure}")

            topics.append(
                Topic(
                    topic_id=topic_id,
                    brand=brand,
                    name=outcome.name,
                    n=cluster.n,
                    n_clusters=cluster.n_clusters,
                    share=share,
                    net=net,
                    ci95=ci95,
                    exemplar_mention_ids=[m.mention_id for m, _ in exemplar_rows],
                    method=method,
                )
            )
            for mention, _ in cluster.rows:
                assignments[(brand, mention.mention_id)] = topic_id

    return TopicsResult(
        topics=topics,
        assignments=assignments,
        abstentions=abstentions,
        usages=usages,
        notes=notes,
        embedding_cache_hits=hits,
        embedding_cache_misses=misses,
    )


def assign_topic_ids(rows: Sequence[Row], assignments: Mapping[tuple[str, str], str]) -> list[Row]:
    """Rows with ``Label.topic_id`` set from ``assignments``; unassigned labels get ``None``."""
    out: list[Row] = []
    for mention, label in rows:
        topic_id = assignments.get((mention.brand, mention.mention_id))
        out.append((mention, label.model_copy(update={"topic_id": topic_id})))
    return out


__all__ = [
    "USABLE_LABEL_STATUSES",
    "Row",
    "TopicsResult",
    "assign_topic_ids",
    "brand_slug",
    "build_topics",
    "is_relevant",
    "topic_id_for",
]
