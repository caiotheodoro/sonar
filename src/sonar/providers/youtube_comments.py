"""YouTube comments adapter: Apify ``streamers/youtube-comments-scraper``.

Endpoint reference (design appendix, verified 2026-09-02):

* input ``startUrls[]``, ``maxComments``, ``sortCommentsBy``;
* output items ``comment, author, videoId, voteCount, replyCount`` and no
  timestamp;
* price 0.00225 USD per result (``config.SOURCE_PLAN["youtube_comment"]``).

``startUrls`` come from the videos the :mod:`sonar.providers.youtube` adapter
returned for the same brand. ``maxComments`` is the profile cap divided over
the start URLs so the billed total stays at or under the cap whether the
actor applies the number per video or per run.

A comment becomes one :class:`~sonar.models.Mention` with
``published_at = null`` (the endpoint carries no timestamp, so the source is
``wow_scope=false`` per CONTRACTS §AbstainReason) and ``cluster_key`` the
``videoId`` it belongs to (CONTRACTS §cluster_key rules).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sonar.config import SOURCE_PLAN, SourcePlan
from sonar.models import Mention, author_hash_for, mention_id_for
from sonar.providers.base import AdapterSchemaError
from sonar.providers.registry import PROVIDERS
from sonar.providers.youtube import (
    engagement_of,
    items_of,
    optional_str,
    require,
)
from sonar.text import detect_lang, match_terms, text_key

PLAN: SourcePlan = SOURCE_PLAN["youtube_comment"]
SORT_COMMENTS_BY = "newest"


def video_urls_of(videos: Sequence[Any]) -> list[str]:
    """Distinct video URLs, in order, from the Mention rows of the video adapter.

    Rows without a URL are skipped; strings are accepted as-is so a caller can
    also pass URLs directly.
    """
    seen: set[str] = set()
    urls: list[str] = []
    for video in videos:
        url = video if isinstance(video, str) else getattr(video, "url", None)
        if isinstance(url, str) and url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


class YouTubeCommentsProvider:
    """Apify ``streamers/youtube-comments-scraper`` adapter (source ``youtube_comment``)."""

    _ENGAGEMENT: tuple[tuple[str, str], ...] = (
        ("voteCount", "likes"),
        ("replyCount", "replies"),
    )

    @property
    def source(self) -> str:
        return PLAN.source

    @property
    def provider(self) -> str:
        return PLAN.provider

    @property
    def endpoint(self) -> str:
        return PLAN.endpoint

    @property
    def available(self) -> bool:
        return True

    @property
    def unavailable_reason(self) -> str | None:
        return None

    def build_input(self, query: Any, videos: Sequence[Any] = ()) -> dict[str, Any]:
        """Actor input for ``POST /v1/run`` (passed to Apify unchanged).

        *videos* are the Mention rows (or URLs) the video adapter returned.
        With no videos there is nothing to fetch and ``ValueError`` is raised
        so no run is submitted; a profile that does not fetch comments raises
        too. ``maxComments`` is never ``0``.
        """
        cap = PLAN.caps[query.profile]
        if cap <= 0:
            raise ValueError(f"youtube_comment is not fetched under profile {query.profile!r}")
        urls = video_urls_of(videos)
        if not urls:
            raise ValueError("youtube_comment needs at least one video URL")
        return {
            "startUrls": [{"url": url} for url in urls],
            "maxComments": max(1, cap // len(urls)),
            "sortCommentsBy": SORT_COMMENTS_BY,
        }

    def parse(
        self,
        raw: Any,
        run_id: str | None,
        brand: str,
        *,
        local_seq: int = 1,
        terms: Sequence[str] | None = None,
    ) -> list[Mention]:
        """Turn the provider response into Mention rows for *brand*.

        ``local_seq`` is the ledger row that saved *raw* (``raw_ref`` is
        ``"{local_seq}#{index}"``); the pipeline passes it and the default
        only satisfies the Provider protocol. ``terms`` are the brand terms
        to match (default: the brand alone); comments without a match are
        not emitted. ``published_at`` is always ``null``.
        """
        source = PLAN.source
        match_on = list(terms) if terms else [brand]
        mentions: list[Mention] = []
        for index, item in enumerate(items_of(raw, self.provider, self.endpoint)):
            text = require(item, "comment", index, self.provider, self.endpoint)
            video_id = require(item, "videoId", index, self.provider, self.endpoint)
            matched = match_terms(text, match_on)
            if not matched:
                continue
            native_id = optional_str(item, "cid") or optional_str(item, "id")
            author = optional_str(item, "author")
            key = native_id if native_id is not None else text_key(text)
            if not key:
                raise AdapterSchemaError(
                    self.provider, self.endpoint, f"item {index} has no id and no text key"
                )
            record: dict[str, Any] = {
                "mention_id": mention_id_for(source, key),
                "brand": brand,
                "source": source,
                "run_id": run_id,
                "native_id": native_id,
                "url": None,
                "author_hash": author_hash_for(source, author) if author else None,
                "text": text,
                "lang": detect_lang(text),
                "published_at": None,
                "engagement": engagement_of(item, self._ENGAGEMENT),
                "rating": None,
                "cluster_key": video_id,
                "matched_terms": matched,
                "raw_ref": f"{local_seq}#{index}",
            }
            mentions.append(Mention.model_validate(record))
        return mentions

    def unit_cost(self, n_results: int) -> float:
        """Estimated USD for *n_results* billed results plus the per-call price."""
        return PLAN.per_call_usd + n_results * PLAN.per_result_usd

    def cluster_key(self, item: Mention) -> str:
        """CONTRACTS §cluster_key rules: the video the comment belongs to."""
        return item.cluster_key


PROVIDER = YouTubeCommentsProvider()
PROVIDERS[PROVIDER.source] = PROVIDER

__all__ = ["PLAN", "PROVIDER", "YouTubeCommentsProvider", "video_urls_of"]
