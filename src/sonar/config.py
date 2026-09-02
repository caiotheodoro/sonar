"""Configuration layer: source plan, profiles, LLM ids and rates, thresholds.

Every number the published-claims gate checks lives here as a named constant:
the threshold index of ``docs/PRE-REGISTRATION.md`` (v1.1.2, frozen
2026-09-02, amended same day by D012 A1/A2, D013 A3 and D014 A4; later
amendments bump the patch version there, never the values here without a
``DECISIONS.md`` entry), the
endpoint reference table of the design document (Monid ids
and prices verified 2026-09-02) and the OpenAI prices of ``docs/DECISIONS.md``
D003. Changing a frozen value after that date is a ``docs/DECISIONS.md``
entry, never a silent edit here.

Nothing in this module imports ``sonar.models``; the enums below are the
CONTRACTS ``Source`` and ``Profile`` values spelled as ``Literal`` so that
``models.py`` can depend on this module and not the other way round.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final, Literal

SourceName = Literal[
    "reddit",
    "youtube",
    "youtube_comment",
    "tiktok",
    "instagram",
    "google_maps",
    "facebook",
    "trustpilot",
    "g2",
    "news",
]
ProfileName = Literal["smoke", "lite", "full"]
ClusterRule = Literal["post_id", "video_id", "author_hash", "mention_id"]
CapUnit = Literal["results", "calls", "pages"]

SOURCES: Final[tuple[SourceName, ...]] = (
    "reddit",
    "youtube",
    "youtube_comment",
    "tiktok",
    "instagram",
    "google_maps",
    "facebook",
    "trustpilot",
    "g2",
    "news",
)
REVIEW_SOURCES: Final[frozenset[SourceName]] = frozenset(
    {"google_maps", "facebook", "trustpilot", "g2"}
)
COMMENT_SOURCES: Final[frozenset[SourceName]] = frozenset(
    {"reddit", "youtube_comment", "tiktok", "instagram"}
)

# ---------------------------------------------------------------------------
# Randomness and bootstrap
# ---------------------------------------------------------------------------

SEED: Final[int] = 777
B_LIVE: Final[int] = 2000
B_FROZEN_DEMO: Final[int] = 10000
B: Final[int] = B_LIVE
CI_LEVEL: Final[float] = 0.95
HOLM_ALPHA: Final[float] = 0.05

# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

WINDOW_DAYS_DEFAULT: Final[int] = 14
WINDOW_DAYS_MIN: Final[int] = 1
WINDOW_DAYS_MAX: Final[int] = 31
WOW_SPLIT_DAYS: Final[int] = 7

# ---------------------------------------------------------------------------
# Abstention minimums (brand level, in either week)
# ---------------------------------------------------------------------------

MIN_CLUSTERS_PER_WEEK: Final[int] = 5
MIN_MENTIONS_PER_WEEK: Final[int] = 20

# ---------------------------------------------------------------------------
# Event rule: n_day >= max(EVENT_MIN_COUNT, median + EVENT_MAD_MULTIPLIER * MAD)
# and n_clusters_day >= EVENT_MIN_CLUSTERS, baseline over EVENT_BASELINE_DAYS
# ---------------------------------------------------------------------------

EVENT_MIN_COUNT: Final[int] = 5
EVENT_MAD_MULTIPLIER: Final[float] = 3.0
EVENT_MIN_CLUSTERS: Final[int] = 3
EVENT_BASELINE_DAYS: Final[int] = 14

# ---------------------------------------------------------------------------
# Two-signal labelling policy
# ---------------------------------------------------------------------------

TIEBREAK_CONFIDENCE_THRESHOLD: Final[float] = 0.6
TIEBREAK_CAP_FRACTION: Final[float] = 0.40
AUDIT_SAMPLE_FRACTION: Final[float] = 0.10
RATING_NEGATIVE_MAX: Final[int] = 2
RATING_POSITIVE_MIN: Final[int] = 4
RATIONALE_MAX_WORDS: Final[int] = 20
RATIONALE_MAX_CHARS: Final[int] = 200
PROMPT_REV: Final[str] = "classify-v1-2026-09-02"

# ---------------------------------------------------------------------------
# Hypotheses H1-H5
# ---------------------------------------------------------------------------

H1_MAX_TOTAL_USD: Final[float] = 5.0
H2_MIN_DESIGN_EFFECT: Final[float] = 1.5
H3_MIN_AGREEMENT: Final[float] = 0.85
H4_MIN_TOTAL_USD_EXCLUSIVE: Final[float] = 0.0
H5_MIN_AGREEMENT: Final[float] = 0.85
H5_N_LABELS: Final[int] = 50

# ---------------------------------------------------------------------------
# Topics (CONTRACTS Topic.method; cut, min_size and min_breadth are frozen in
# the PRE-REGISTRATION threshold index per D012 F16)
# ---------------------------------------------------------------------------

TOPIC_MIN_SIZE: Final[int] = 3
TOPIC_MIN_BREADTH: Final[int] = 2
TOPIC_LINKAGE: Final[str] = "average"
TOPIC_DISTANCE_THRESHOLD: Final[float] = 0.35
TOPIC_EXEMPLARS: Final[int] = 3
TOPIC_NAME_MAX_WORDS: Final[int] = 6

# ---------------------------------------------------------------------------
# Digest, chat, voice
# ---------------------------------------------------------------------------

TOP_MENTIONS_PER_BRAND: Final[int] = 10
QUOTE_MAX_CHARS: Final[int] = 240
CHAT_TOP_K: Final[int] = 20
NARRATION_MAX_CHARS: Final[int] = 900
BRIEFS_PER_MONTH_ASSUMED: Final[int] = 4

# ---------------------------------------------------------------------------
# Monid transport and budget (design "How to run this graph" and Error matrix)
# ---------------------------------------------------------------------------

MONID_API_BASE: Final[str] = "https://api.monid.ai/v1"
MONID_BACKOFF_SECONDS: Final[tuple[int, ...]] = (2, 4, 8, 16)
MONID_RUNS_PAGE_LIMIT: Final[int] = 100
MONID_BUDGET_CAP_USD: Final[float] = 10.0
MONID_RUN_CAP_USD: Final[float] = 3.5
MONID_RESERVE_USD: Final[float] = 1.5
OPENAI_MAX_RETRIES: Final[int] = 4

# ---------------------------------------------------------------------------
# ElevenLabs voice run (a Monid run, not a source)
# ---------------------------------------------------------------------------

ELEVENLABS_PROVIDER: Final[str] = "elevenlabs"
ELEVENLABS_ENDPOINT: Final[str] = "/text-to-speech"
ELEVENLABS_VOICES_ENDPOINT: Final[str] = "/voices"
ELEVENLABS_MODEL_ID: Final[str] = "eleven_flash_v2_5"
ELEVENLABS_USD_PER_1K_CHARS: Final[float] = 0.05

# Direct-to-ElevenLabs voice path (D016). Default is the Monid proxy above;
# with SONAR_TTS_DIRECT set and a key present the run goes straight to
# ElevenLabs and the ledger row carries the Monid-equivalent price as its
# theoretical `estimate_usd` (no Monid spend).
ELEVENLABS_DIRECT_BASE_URL: Final[str] = "https://api.elevenlabs.io"
ELEVENLABS_DIRECT_OUTPUT_FORMAT: Final[str] = "mp3_44100_128"
ENV_TTS_DIRECT: Final[str] = "SONAR_TTS_DIRECT"
ENV_ELEVENLABS_KEY: Final[str] = "ELEVENLABS_API_KEY"

_TRUTHY_ENV: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class TtsMode:
    """Where the voice run spends: Monid proxy (default) or ElevenLabs direct (D016)."""

    direct: bool
    api_key: str | None

    @property
    def usable_direct(self) -> bool:
        """``direct`` was asked for and a key is available to honour it."""
        return self.direct and bool(self.api_key)


def resolve_tts(env: Mapping[str, str] | None = None) -> TtsMode:
    """The direct-TTS toggle and ElevenLabs key from ``env`` (default ``os.environ``).

    ``SONAR_TTS_DIRECT`` in {1, true, yes, on} routes the voice run straight to
    ElevenLabs; the theoretical Monid ``/text-to-speech`` cost is still recorded
    on the ledger row's ``estimate_usd`` (D016). With the toggle off, or no key,
    the run goes through Monid as before.
    """
    source = os.environ if env is None else env
    direct = source.get(ENV_TTS_DIRECT, "").strip().lower() in _TRUTHY_ENV
    api_key = source.get(ENV_ELEVENLABS_KEY, "").strip() or None
    return TtsMode(direct=direct, api_key=api_key)

# ---------------------------------------------------------------------------
# Source plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourcePlan:
    """One Monid endpoint per source with its caps and price.

    ``caps`` is the per-brand cap in ``cap_unit`` for each profile; ``0`` means
    the source is not fetched in that profile. ``per_result_usd`` is charged per
    billed result, ``per_call_usd`` once per call. Sources capped in ``calls``
    or ``pages`` make ``cap`` calls; sources capped in ``results`` make one.
    ``lookup_endpoint`` is the id-resolution call some providers need first
    (Trustpilot company search, G2 software search), billed at ``lookup_usd``.
    ``max_posts`` and ``max_comments_per_post`` split a ``results`` cap between
    posts and the comments fetched under each post (reddit, D014); ``None``
    means the source has no such split and the cap alone applies.
    """

    source: SourceName
    provider: str
    endpoint: str
    caps: Mapping[ProfileName, int]
    cap_unit: CapUnit
    per_result_usd: float
    per_call_usd: float
    cluster_rule: ClusterRule
    has_rating: bool
    has_timestamps: bool = True
    lookup_endpoint: str | None = None
    lookup_usd: float = 0.0
    max_posts: int | None = None
    max_comments_per_post: int | None = None

    def n_calls(self, profile: ProfileName) -> int:
        cap = self.caps[profile]
        if cap == 0:
            return 0
        return 1 if self.cap_unit == "results" else cap

    def estimate_usd(self, profile: ProfileName) -> float:
        """Estimated per-brand cost for one profile, lookup included."""
        cap = self.caps[profile]
        if cap == 0:
            return 0.0
        results = cap if self.cap_unit == "results" else 0
        lookup = self.lookup_usd if self.lookup_endpoint is not None else 0.0
        return self.n_calls(profile) * self.per_call_usd + results * self.per_result_usd + lookup


def _caps(smoke: int, lite: int, full: int) -> Mapping[ProfileName, int]:
    return {"smoke": smoke, "lite": lite, "full": full}


SOURCE_PLAN: Final[Mapping[SourceName, SourcePlan]] = {
    "reddit": SourcePlan(
        source="reddit",
        provider="apify",
        endpoint="/trudax/reddit-scraper-lite",
        caps=_caps(40, 20, 40),
        cap_unit="results",
        per_result_usd=0.0057,
        per_call_usd=0.02,
        cluster_rule="post_id",
        has_rating=False,
        max_posts=15,
        max_comments_per_post=2,
    ),
    "youtube": SourcePlan(
        source="youtube",
        provider="apify",
        endpoint="/streamers/youtube-scraper",
        caps=_caps(0, 5, 10),
        cap_unit="results",
        per_result_usd=0.0045,
        per_call_usd=0.0,
        cluster_rule="mention_id",
        has_rating=False,
    ),
    "youtube_comment": SourcePlan(
        source="youtube_comment",
        provider="apify",
        endpoint="/streamers/youtube-comments-scraper",
        caps=_caps(0, 30, 60),
        cap_unit="results",
        per_result_usd=0.00225,
        per_call_usd=0.0,
        cluster_rule="video_id",
        has_rating=False,
        has_timestamps=False,
    ),
    "tiktok": SourcePlan(
        source="tiktok",
        provider="apify",
        endpoint="/apidojo/tiktok-scraper",
        caps=_caps(0, 20, 40),
        cap_unit="results",
        per_result_usd=0.00045,
        per_call_usd=0.0,
        cluster_rule="author_hash",
        has_rating=False,
    ),
    "instagram": SourcePlan(
        source="instagram",
        provider="apify",
        endpoint="/apify/instagram-hashtag-scraper",
        caps=_caps(0, 15, 30),
        cap_unit="results",
        per_result_usd=0.0,
        per_call_usd=0.00345,
        cluster_rule="author_hash",
        has_rating=False,
        has_timestamps=False,
    ),
    "google_maps": SourcePlan(
        source="google_maps",
        provider="apify",
        endpoint="/compass/google-maps-reviews-scraper",
        caps=_caps(50, 25, 50),
        cap_unit="results",
        per_result_usd=0.000675,
        per_call_usd=0.0,
        cluster_rule="mention_id",
        has_rating=True,
    ),
    "facebook": SourcePlan(
        source="facebook",
        provider="apify",
        endpoint="/apify/facebook-reviews-scraper",
        caps=_caps(0, 15, 30),
        cap_unit="results",
        per_result_usd=0.003,
        per_call_usd=0.001,
        cluster_rule="mention_id",
        has_rating=True,
    ),
    "trustpilot": SourcePlan(
        source="trustpilot",
        provider="trustpilot",
        endpoint="/get_company_reviews",
        caps=_caps(0, 1, 1),
        cap_unit="calls",
        per_result_usd=0.0,
        per_call_usd=0.03,
        cluster_rule="mention_id",
        has_rating=True,
        lookup_endpoint="/search_companies",
        lookup_usd=0.03,
    ),
    "g2": SourcePlan(
        source="g2",
        provider="g2",
        endpoint="/get_product_reviews",
        caps=_caps(0, 1, 1),
        cap_unit="calls",
        per_result_usd=0.0,
        per_call_usd=0.05,
        cluster_rule="mention_id",
        has_rating=True,
        lookup_endpoint="/search_software",
        lookup_usd=0.02,
    ),
    "news": SourcePlan(
        source="news",
        provider="tinyfish",
        endpoint="/search",
        caps=_caps(0, 2, 3),
        cap_unit="pages",
        per_result_usd=0.0,
        per_call_usd=0.0,
        cluster_rule="mention_id",
        has_rating=False,
    ),
}

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Profile:
    """Which sources a profile fetches, how many competitors it allows, and B."""

    name: ProfileName
    sources: tuple[SourceName, ...]
    max_competitors: int
    resamples: int

    def estimate_usd_per_brand(self) -> float:
        return sum(SOURCE_PLAN[s].estimate_usd(self.name) for s in self.sources)

    def estimate_usd(self, n_brands: int) -> float:
        """Monid estimate for a brief over ``n_brands`` (brand plus competitors)."""
        return self.estimate_usd_per_brand() * n_brands


PROFILES: Final[Mapping[ProfileName, Profile]] = {
    "smoke": Profile(
        name="smoke",
        sources=("reddit", "google_maps"),
        max_competitors=0,
        resamples=B_LIVE,
    ),
    "lite": Profile(name="lite", sources=SOURCES, max_competitors=1, resamples=B_LIVE),
    "full": Profile(name="full", sources=SOURCES, max_competitors=3, resamples=B_LIVE),
}
MAX_COMPETITORS: Final[int] = PROFILES["full"].max_competitors

# ---------------------------------------------------------------------------
# LLM models, env overrides and rates (docs/DECISIONS.md D003, dated 2026-09-02)
# ---------------------------------------------------------------------------

CLASSIFIER_MODEL_DEFAULT: Final[str] = "gpt-5.6-luna"
TIEBREAK_MODEL_DEFAULT: Final[str] = "gpt-5.6-terra"
EMBEDDING_MODEL_DEFAULT: Final[str] = "text-embedding-3-small"
ENV_CLASSIFIER_MODEL: Final[str] = "SONAR_CLASSIFIER_MODEL"
ENV_TIEBREAK_MODEL: Final[str] = "SONAR_TIEBREAK_MODEL"
ENV_EMBEDDING_MODEL: Final[str] = "SONAR_EMBEDDING_MODEL"

LlmRole = Literal["classifier_model", "tiebreak_model", "embedding_model"]


@dataclass(frozen=True, slots=True)
class LlmModels:
    """Model ids by role; ``LLM["classifier_model"]`` and ``LLM.classifier_model`` both work."""

    classifier_model: str
    tiebreak_model: str
    embedding_model: str

    def __getitem__(self, role: LlmRole) -> str:
        value: str = getattr(self, role)
        return value


def resolve_llm(env: Mapping[str, str] | None = None) -> LlmModels:
    """Model ids after applying the ``SONAR_*_MODEL`` overrides from ``env``.

    An override set to the empty string is ignored, so an exported-but-empty
    variable cannot silently send requests to model id ``""``.
    """
    source = os.environ if env is None else env

    def pick(var: str, default: str) -> str:
        value = source.get(var, "").strip()
        return value or default

    return LlmModels(
        classifier_model=pick(ENV_CLASSIFIER_MODEL, CLASSIFIER_MODEL_DEFAULT),
        tiebreak_model=pick(ENV_TIEBREAK_MODEL, TIEBREAK_MODEL_DEFAULT),
        embedding_model=pick(ENV_EMBEDDING_MODEL, EMBEDDING_MODEL_DEFAULT),
    )


LLM: Final[LlmModels] = resolve_llm()


@dataclass(frozen=True, slots=True)
class LlmRate:
    """OpenAI list price in USD per million tokens."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float


LLM_RATES_CHECKED_AT: Final[date] = date(2026, 9, 2)
LLM_RATES: Final[Mapping[str, LlmRate]] = {
    CLASSIFIER_MODEL_DEFAULT: LlmRate(input_usd_per_mtok=0.20, output_usd_per_mtok=1.20),
    TIEBREAK_MODEL_DEFAULT: LlmRate(input_usd_per_mtok=2.00, output_usd_per_mtok=12.00),
    EMBEDDING_MODEL_DEFAULT: LlmRate(input_usd_per_mtok=0.02, output_usd_per_mtok=0.0),
}


def llm_cost_usd(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Cost of one call from token usage. Unknown model ids raise, never cost 0."""
    if model not in LLM_RATES:
        known = ", ".join(sorted(LLM_RATES))
        raise KeyError(f"no LLM_RATES entry for {model!r}; known: {known}")
    rate = LLM_RATES[model]
    return (
        input_tokens * rate.input_usd_per_mtok + output_tokens * rate.output_usd_per_mtok
    ) / 1_000_000


# ---------------------------------------------------------------------------
# Threshold index: PRE-REGISTRATION name -> constant, for the claims gate
# ---------------------------------------------------------------------------

THRESHOLD_INDEX: Final[Mapping[str, float | int]] = {
    "ci_level": CI_LEVEL,
    "b_live": B_LIVE,
    "b_frozen_demo": B_FROZEN_DEMO,
    "seed": SEED,
    "holm_alpha": HOLM_ALPHA,
    "min_clusters_per_week": MIN_CLUSTERS_PER_WEEK,
    "min_mentions_per_week": MIN_MENTIONS_PER_WEEK,
    "event_min_count": EVENT_MIN_COUNT,
    "event_mad_multiplier": EVENT_MAD_MULTIPLIER,
    "event_min_clusters": EVENT_MIN_CLUSTERS,
    "event_baseline_days": EVENT_BASELINE_DAYS,
    "tiebreak_confidence_threshold": TIEBREAK_CONFIDENCE_THRESHOLD,
    "tiebreak_cap_fraction": TIEBREAK_CAP_FRACTION,
    "audit_sample_fraction": AUDIT_SAMPLE_FRACTION,
    "h1_max_total_usd": H1_MAX_TOTAL_USD,
    "h2_min_design_effect": H2_MIN_DESIGN_EFFECT,
    "h3_min_agreement": H3_MIN_AGREEMENT,
    "h4_min_total_usd_exclusive": H4_MIN_TOTAL_USD_EXCLUSIVE,
    "h5_min_agreement": H5_MIN_AGREEMENT,
    "h5_n_labels": H5_N_LABELS,
    "topic_distance_threshold": TOPIC_DISTANCE_THRESHOLD,
    "topic_min_size": TOPIC_MIN_SIZE,
    "topic_min_breadth": TOPIC_MIN_BREADTH,
}
