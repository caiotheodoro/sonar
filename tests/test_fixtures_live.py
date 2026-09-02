"""Adapters against the recorded W3.7 smoke fixtures (D014, relevance by context).

The fixtures are the raw Monid run objects saved by ``sonar record``; the
provider items sit under the run's ``output`` key. These tests prove the
D014 rules on real payloads: a Google Maps run yields one Mention per
review with ``match_kind = "entity"`` although no review text names the
brand, and a Reddit run keeps the comments under matched posts as
``inherited`` instead of dropping everything that does not repeat the
brand string.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sonar.models import Mention
from sonar.providers import google_maps, reddit
from sonar.text import match_terms

FIXTURES = Path(__file__).parent / "fixtures"
REDDIT_RUN = "apify_reddit-scraper-lite_nubank_2026-09-02T091816Z.json"
GOOGLE_MAPS_RUN = "apify_google-maps-reviews-scraper_nubank_2026-09-02T092007Z.json"
BRAND = "Nubank"


def _run(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data["output"], list)
    return data


class TestGoogleMapsLiveRun:
    def test_every_review_is_an_entity_match(self) -> None:
        run = _run(GOOGLE_MAPS_RUN)
        mentions = google_maps.PROVIDER.parse(run["output"], run["runId"], BRAND, local_seq=2)
        assert len(mentions) == 4
        assert len(run["output"]) == 4
        assert all(isinstance(m, Mention) for m in mentions)
        assert {m.match_kind for m in mentions} == {"entity"}
        assert all(m.matched_terms == ["nubank"] for m in mentions)
        assert all(m.run_id == run["runId"] and m.source == "google_maps" for m in mentions)
        assert all(m.rating is not None and 1 <= m.rating <= 5 for m in mentions)
        # the point of D014: no review text names the brand
        assert all(not match_terms(m.text, [BRAND]) for m in mentions)


class TestRedditLiveRun:
    def test_comments_inherit_the_matched_post(self) -> None:
        run = _run(REDDIT_RUN)
        report = reddit.PROVIDER.parse_with_report(
            run["output"], run["runId"], BRAND, local_seq=1, terms=["Nu"]
        )
        mentions = report.mentions
        items = run["output"]
        posts = {i["id"] for i in items if i["dataType"] == "post"}
        assert len(items) == 40
        assert len(posts) == 3
        text_hits = sum(1 for m in mentions if m.match_kind == "text")
        assert text_hits <= 11 + len(posts)
        assert len(mentions) > 11
        assert all(isinstance(m, Mention) for m in mentions)
        by_native = {m.native_id: m for m in mentions}
        assert all(by_native[p].match_kind == "text" for p in posts)
        inherited = [m for m in mentions if m.match_kind == "inherited"]
        assert inherited
        assert all(m.native_id is not None and m.native_id.startswith("t1_") for m in inherited)
        assert {m.native_id for m in inherited} == set(report.inherited_from)
        for m in inherited:
            assert m.native_id is not None
            parent = report.inherited_from[m.native_id]
            assert parent in posts
            assert m.cluster_key == parent
            assert m.matched_terms == by_native[parent].matched_terms
            assert not match_terms(m.text, [BRAND, "Nu"])
        assert report.cluster_key_fallbacks == 0
        assert report.skipped_no_match == len(items) - len(mentions)
