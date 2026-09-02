"""Topics layer (W4.2): embed through the seam, cluster in code, name through the model.

``build_topics`` is the entry point; the pipeline joins ``Mention`` and
``Label`` rows per brand, passes them in, and writes ``assignments`` back into
``Label.topic_id`` with ``assign_topic_ids``.
"""

from sonar.topics.build import (
    Row,
    TopicsResult,
    assign_topic_ids,
    brand_slug,
    build_topics,
    is_relevant,
    topic_id_for,
)
from sonar.topics.cluster import average_linkage, cosine_distances, medoid_indices
from sonar.topics.embed import (
    CACHE_FILENAME,
    EmbeddingBatch,
    EmbeddingCache,
    embed_texts,
    embedding_key,
)
from sonar.topics.estimate import PolarCounts, net_ci95, net_of, share_of
from sonar.topics.name import NAMING_SYSTEM, TopicName, cap_words, fallback_name, name_topic

__all__ = [
    "CACHE_FILENAME",
    "NAMING_SYSTEM",
    "EmbeddingBatch",
    "EmbeddingCache",
    "PolarCounts",
    "Row",
    "TopicName",
    "TopicsResult",
    "assign_topic_ids",
    "average_linkage",
    "brand_slug",
    "build_topics",
    "cap_words",
    "cosine_distances",
    "embed_texts",
    "embedding_key",
    "fallback_name",
    "is_relevant",
    "medoid_indices",
    "name_topic",
    "net_ci95",
    "net_of",
    "share_of",
    "topic_id_for",
]
