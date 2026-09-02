"""Pydantic v2 encoding of every record in CONTRACTS.md (`schema_rev` 1.0.0).

Every model is frozen with ``extra="forbid"``; field names are the wire names.
Closed enums are ``Literal`` aliases so an unknown value is a validation error.
Rules that CONTRACTS states in prose (cluster_key per source, Query validator
order, receipt verdict, canonical JSON digests) are validators or helpers here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import UTC, date, datetime
from itertools import pairwise
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
    model_validator,
)

SCHEMA_REV = "1.0.0"

# --------------------------------------------------------------------------- enums

Source = Literal[
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
Profile = Literal["smoke", "lite", "full"]
Lang = Literal["pt", "en", "other", "unknown"]
SentimentLabel = Literal["positive", "negative", "neutral", "irrelevant"]
Polarity = Literal["positive", "negative", "neutral"]
Corroboration = Literal["confirmed", "model_only", "contested", "irrelevant"]
DecidedBy = Literal["classifier", "tiebreak"]
LabelStatus = Literal["ok", "refused", "unparseable", "error", "cached"]
SignalKind = Literal["rating", "lexicon", "none"]
CostSource = Literal["/v1/runs", "unreconciled"]
Verdict = Literal["RECONCILED", "PARTIAL", "REPLAY"]
WowVerdict = Literal["SIGNIFICANT", "SUGGESTIVE", "NO_CHANGE_DETECTED", "ABSTAIN"]
AnswerStatus = Literal["ok", "unverified", "refused"]
LlmKind = Literal["classify", "tiebreak", "embed", "name_topic", "narrate", "ask"]
AbstainReason = Literal[
    "empty",
    "provider_failed",
    "rate_limited",
    "deadline",
    "unavailable",
    "schema_drift",
    "no_timestamps",
    "below_minimum",
    "halted",
    "embedding_failed",
]
AbstainScope = Literal["source", "brand", "topics", "voice", "session"]

SOURCES: tuple[Source, ...] = get_args(Source)
REVIEW_SOURCES: frozenset[Source] = frozenset({"google_maps", "facebook", "trustpilot", "g2"})
COMMENT_SOURCES: frozenset[Source] = frozenset({"reddit", "youtube_comment", "tiktok", "instagram"})
AUTHOR_CLUSTER_SOURCES: frozenset[Source] = frozenset({"tiktok", "instagram"})
MENTION_ID_CLUSTER_SOURCES: frozenset[Source] = frozenset(
    {"youtube", "google_maps", "facebook", "trustpilot", "g2", "news"}
)
ENGAGEMENT_KEYS: frozenset[str] = frozenset(
    {"upvotes", "likes", "comments", "shares", "views", "replies", "votes"}
)
EXCLUSION_REASONS: frozenset[str] = frozenset(
    {"not_about_brand", "no_matched_terms", "refused", "unparseable", "error"}
)

# Default `Query.sources` per profile. CONTRACTS names `config.SOURCE_PLAN` (W2.2)
# as the cap table; the profile source lists there must equal these
# (design: `smoke` = reddit + maps; `lite` halves caps over the full list).
PROFILE_SOURCES: dict[Profile, tuple[Source, ...]] = {
    "smoke": ("reddit", "google_maps"),
    "lite": SOURCES,
    "full": SOURCES,
}

# --------------------------------------------------------------------------- scalars

_HEX24 = re.compile(r"^[0-9a-f]{24}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")
_RAW_REF = re.compile(r"^[1-9][0-9]*#(0|[1-9][0-9]*)$")
_TOPIC_ID = re.compile(r"^\S+-[0-9]{2}$")
_SESSION_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-\S+-[0-9a-f]{6}$")
_LOCAL_STATUS = re.compile(r"^LOCAL_(REJECTED_[0-9]{3}|BACKOFF_EXHAUSTED|DEADLINE)$")
_WS = re.compile(r"\s+")


def _utc_seconds(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware (UTC)")
    return value.astimezone(UTC).replace(microsecond=0)


def _iso_z(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[
    datetime,
    AfterValidator(_utc_seconds),
    PlainSerializer(_iso_z, return_type=str, when_used="json"),
]


def _ordered_interval(value: tuple[float, float]) -> tuple[float, float]:
    lo, hi = value
    if math.isnan(lo) or math.isnan(hi):
        raise ValueError("CI95 bounds must not be NaN")
    if lo > hi:
        raise ValueError(f"CI95 lower bound {lo} exceeds upper bound {hi}")
    return value


CI95 = Annotated[tuple[float, float], AfterValidator(_ordered_interval)]
Hex24 = Annotated[str, Field(pattern=_HEX24.pattern)]
Hex16 = Annotated[str, Field(pattern=_HEX16.pattern)]
Money = Annotated[float, Field(ge=0.0)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]
NetScore = Annotated[float, Field(ge=-1.0, le=1.0)]


def _word_count(text: str) -> int:
    return len(text.split())


def normalize_term(term: str) -> str:
    """Term-level normalization used for distinctness (NFKC, casefold, collapsed whitespace)."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", term).casefold()).strip()


def canonical_json(data: Any) -> bytes:
    """Canonical JSON: sorted keys, ``,``/``:`` separators, UTF-8 (CONTRACTS §RunRecord)."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def mention_id_for(source: Source, key: str) -> str:
    """CONTRACTS §mention_id rule: sha256 over ``"{source}\\n{key}"``, first 24 hex."""
    return hashlib.sha256(f"{source}\n{key}".encode()).hexdigest()[:24]


def author_hash_for(source: Source, handle: str) -> str:
    """CONTRACTS §Mention.author_hash: sha256 over ``"{source}\\n{handle}"``, first 16 hex."""
    return hashlib.sha256(f"{source}\n{handle}".encode()).hexdigest()[:16]


def input_digest_for(request_input: Any) -> str:
    """CONTRACTS §RunRecord.input_digest: first 24 hex of sha256 over canonical JSON."""
    return hashlib.sha256(canonical_json(request_input)).hexdigest()[:24]


# --------------------------------------------------------------------------- base


class SonarModel(BaseModel):
    """Frozen, extra-forbidding base for every wire record."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=False)


# --------------------------------------------------------------------------- Query


def _check_term(term: str, what: str) -> str:
    stripped = term.strip()
    if not 2 <= len(stripped) <= 64:
        raise ValueError(f"{what} must be 2-64 characters after trim, got {len(stripped)}")
    if not any(ch.isalnum() for ch in stripped):
        raise ValueError(f"{what} must not be punctuation-only: {stripped!r}")
    return stripped


class Query(SonarModel):
    """Input record; validated before any client exists (CONTRACTS §Query)."""

    brand: str
    brand_aliases: list[str] = Field(default_factory=list)
    brand_hint: str | None = Field(default=None, max_length=120)
    competitors: list[str] = Field(default_factory=list)
    window_days: int = Field(default=14, ge=1, le=31)
    profile: Profile = "full"
    sources: list[Source] = Field(default_factory=lambda: list(PROFILE_SOURCES["full"]))

    @model_validator(mode="before")
    @classmethod
    def _ordered_checks(cls, data: Any) -> Any:
        """Run the CONTRACTS validator order so the first failure is the one reported.

        Order: length and punctuation per term; distinctness across brand, aliases and
        competitors; competitor count; sources membership, distinctness and profile rule.
        Non-string inputs are left for the field type checks.
        """
        if not isinstance(data, dict):
            return data
        out: dict[str, Any] = dict(data)
        brand = out.get("brand")
        aliases = out.get("brand_aliases", [])
        competitors = out.get("competitors", [])
        if (
            isinstance(brand, str)
            and isinstance(aliases, list)
            and isinstance(competitors, list)
            and all(isinstance(a, str) for a in aliases)
            and all(isinstance(c, str) for c in competitors)
        ):
            out["brand"] = _check_term(brand, "brand")
            out["brand_aliases"] = [_check_term(a, "brand_aliases entry") for a in aliases]
            out["competitors"] = [_check_term(c, "competitors entry") for c in competitors]
            seen: dict[str, str] = {}
            for what, term in (
                [("brand", out["brand"])]
                + [("brand_aliases", a) for a in out["brand_aliases"]]
                + [("competitors", c) for c in out["competitors"]]
            ):
                key = normalize_term(term)
                if key in seen:
                    raise ValueError(f"{what} entry {term!r} duplicates {seen[key]} term")
                seen[key] = what
            if len(out["competitors"]) > 3:
                raise ValueError(f"competitors must have at most 3 entries, got {len(competitors)}")
        profile = out.get("profile", "full")
        sources = out.get("sources")
        if sources is None and profile in PROFILE_SOURCES:
            out["sources"] = list(PROFILE_SOURCES[profile])
        elif isinstance(sources, list) and all(isinstance(s, str) for s in sources):
            unknown = [s for s in sources if s not in SOURCES]
            if unknown:
                raise ValueError(f"sources contains non-members: {unknown}")
            if len(set(sources)) != len(sources):
                raise ValueError("sources must be distinct")
            if profile == "smoke":
                disallowed = [s for s in sources if s not in PROFILE_SOURCES["smoke"]]
                if disallowed:
                    raise ValueError(
                        f"profile smoke allows only reddit and google_maps, got {disallowed}"
                    )
        return out


# --------------------------------------------------------------------------- Mention


class Mention(SonarModel):
    """One fetched item attributed to one brand; key ``(mention_id, brand)``."""

    mention_id: Hex24
    brand: str = Field(min_length=1)
    source: Source
    run_id: str = Field(min_length=1)
    native_id: str | None
    url: str | None
    author_hash: Hex16 | None
    text: str
    lang: Lang
    published_at: UtcDatetime | None
    engagement: dict[str, int]
    rating: int | None
    cluster_key: str = Field(min_length=1)
    matched_terms: list[str] = Field(min_length=1)
    raw_ref: str = Field(pattern=_RAW_REF.pattern)

    @field_validator("text")
    @classmethod
    def _text_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must have at least one non-whitespace character")
        return value

    @field_validator("native_id", "url")
    @classmethod
    def _optional_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must be null when absent, not an empty string")
        return value

    @field_validator("engagement")
    @classmethod
    def _engagement_keys(cls, value: dict[str, int]) -> dict[str, int]:
        bad = sorted(set(value) - ENGAGEMENT_KEYS)
        if bad:
            raise ValueError(f"engagement keys not allowed: {bad}")
        return value

    @field_validator("matched_terms")
    @classmethod
    def _matched_terms_nonblank(cls, value: list[str]) -> list[str]:
        if any(not t.strip() for t in value):
            raise ValueError("matched_terms entries must be non-empty")
        return value

    @model_validator(mode="after")
    def _source_rules(self) -> Self:
        if self.source in REVIEW_SOURCES:
            if self.rating is not None and not 1 <= self.rating <= 5:
                raise ValueError(f"rating must be 1-5 for review source {self.source}")
        elif self.rating is not None:
            raise ValueError(f"rating must be null for non-review source {self.source}")
        expected = expected_cluster_key(self.source, self.mention_id, self.author_hash)
        if expected is not None and self.cluster_key != expected:
            raise ValueError(
                f"cluster_key for {self.source} must be {expected!r}, got {self.cluster_key!r}"
            )
        return self


def expected_cluster_key(source: Source, mention_id: str, author_hash: str | None) -> str | None:
    """CONTRACTS §cluster_key rules where the key is derivable from the row itself.

    Returns ``mention_id`` for video, review and news sources; ``author_hash`` (or the
    ``mention_id`` fallback when it is null) for tiktok and instagram; ``None`` for reddit
    and youtube_comment, whose key (post id, video id) comes from the payload.
    """
    if source in MENTION_ID_CLUSTER_SOURCES:
        return mention_id
    if source in AUTHOR_CLUSTER_SOURCES:
        return author_hash if author_hash is not None else mention_id
    return None


# --------------------------------------------------------------------------- Label


class Usage(SonarModel):
    tokens: int = Field(ge=0)
    cost_usd: Money


class ModelSignal(SonarModel):
    model: str = Field(min_length=1)
    label: SentimentLabel
    confidence: UnitInterval
    status: LabelStatus


class DeterministicSignal(SonarModel):
    kind: SignalKind
    label: Polarity | None

    @model_validator(mode="after")
    def _kind_label(self) -> Self:
        if self.kind == "none" and self.label is not None:
            raise ValueError("deterministic signal of kind none must have label null")
        if self.kind == "rating" and self.label is None:
            raise ValueError("deterministic signal of kind rating always yields a label")
        return self


class Signals(SonarModel):
    classifier: ModelSignal
    tiebreak: ModelSignal | None
    deterministic: DeterministicSignal


class Label(SonarModel):
    """One sentiment decision per Mention row (CONTRACTS §Label)."""

    mention_id: Hex24
    label: SentimentLabel
    about_brand: bool
    confidence: UnitInterval
    rationale: str
    topic_id: str | None
    signals: Signals
    corroboration: Corroboration
    decided_by: DecidedBy
    prompt_rev: str = Field(min_length=1)
    status: LabelStatus
    usage: Usage

    @field_validator("rationale")
    @classmethod
    def _rationale_words(cls, value: str) -> str:
        if _word_count(value) > 20:
            raise ValueError("rationale must be at most 20 words")
        return value

    @field_validator("topic_id")
    @classmethod
    def _topic_id(cls, value: str | None) -> str | None:
        if value is not None and not _TOPIC_ID.match(value):
            raise ValueError("topic_id must be '{brand slug}-{index:02d}'")
        return value

    @model_validator(mode="after")
    def _policy_consistency(self) -> Self:
        if self.decided_by == "tiebreak" and self.signals.tiebreak is None:
            raise ValueError("decided_by=tiebreak requires a tiebreak signal")
        irrelevant = (not self.about_brand) or self.label == "irrelevant"
        if irrelevant != (self.corroboration == "irrelevant"):
            raise ValueError(
                "corroboration is irrelevant iff about_brand is false or label is irrelevant"
            )
        if self.status == "cached" and (self.usage.tokens != 0 or self.usage.cost_usd != 0.0):
            raise ValueError("cached labels carry usage {tokens: 0, cost_usd: 0.0}")
        return self


# --------------------------------------------------------------------------- RunRecord


class RunRecord(SonarModel):
    """One ledger row, written before ``POST /v1/run`` (CONTRACTS §RunRecord)."""

    local_seq: int = Field(ge=1)
    run_id: str | None
    provider: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)
    brand: str | None
    source: Source | None
    input_digest: Hex24
    submitted_at: UtcDatetime
    completed_at: UtcDatetime | None
    status: str = Field(min_length=1)
    provider_http_status: int | None
    n_results: int | None = Field(ge=0)
    estimate_usd: Money
    cost_usd: Money | None
    billed_units: int | None = Field(ge=0)
    cost_source: CostSource
    attempts: int = Field(ge=1)
    error: str | None = Field(max_length=500)

    @property
    def is_local_status(self) -> bool:
        return self.status.startswith("LOCAL_")

    @model_validator(mode="after")
    def _ledger_rules(self) -> Self:
        if self.is_local_status:
            if not _LOCAL_STATUS.match(self.status):
                raise ValueError(
                    "local status must be LOCAL_REJECTED_<http>, LOCAL_BACKOFF_EXHAUSTED "
                    f"or LOCAL_DEADLINE, got {self.status!r}"
                )
            if self.status != "LOCAL_DEADLINE" and self.run_id is not None:
                raise ValueError(f"{self.status} rows must have run_id null")
        if self.cost_source == "/v1/runs" and self.cost_usd is None:
            raise ValueError("cost_source=/v1/runs requires cost_usd filled from the listing")
        if self.cost_source == "unreconciled" and self.cost_usd is not None:
            raise ValueError("cost_usd is null until reconciled from /v1/runs")
        if self.run_id is not None and not self.run_id.strip():
            raise ValueError("run_id must be null when absent, not an empty string")
        return self


# --------------------------------------------------------------------------- Topic


class TopicMethod(SonarModel):
    embedding_model: str = Field(min_length=1)
    linkage: Literal["average"] = "average"
    threshold: float
    min_size: Literal[3] = 3
    min_breadth: Literal[2] = 2


class Topic(SonarModel):
    """One embedding cluster of relevant mentions for one brand (CONTRACTS §Topic)."""

    topic_id: str = Field(pattern=_TOPIC_ID.pattern)
    brand: str = Field(min_length=1)
    name: str = Field(min_length=1)
    n: int = Field(ge=1)
    n_clusters: int = Field(ge=1)
    share: UnitInterval
    net: NetScore
    ci95: CI95
    exemplar_mention_ids: list[Hex24] = Field(min_length=3, max_length=3)
    method: TopicMethod

    @field_validator("name")
    @classmethod
    def _name_words(cls, value: str) -> str:
        if _word_count(value) > 6:
            raise ValueError("topic name must be at most 6 words")
        return value

    @model_validator(mode="after")
    def _minimums(self) -> Self:
        if self.n < self.method.min_size:
            raise ValueError(f"n={self.n} below method.min_size={self.method.min_size}")
        if self.n_clusters < self.method.min_breadth:
            raise ValueError(
                f"n_clusters={self.n_clusters} below method.min_breadth={self.method.min_breadth}"
            )
        if self.n_clusters > self.n:
            raise ValueError("n_clusters cannot exceed n")
        return self


# --------------------------------------------------------------------------- Receipt


class Timestamps(SonarModel):
    started_at: UtcDatetime
    finished_at: UtcDatetime
    reconciled_at: UtcDatetime | None

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        return self


class Totals(SonarModel):
    monid_usd: Money
    monid_runs: int = Field(ge=0)
    monid_runs_billed: int = Field(ge=0)
    monid_runs_zero_results: int = Field(ge=0)
    monid_runs_failed: int = Field(ge=0)
    llm_usd: Money
    llm_calls: dict[LlmKind, int]
    llm_tokens: int = Field(ge=0)
    elevenlabs_usd: Money
    total_usd: Money

    @field_validator("llm_calls")
    @classmethod
    def _call_counts(cls, value: dict[LlmKind, int]) -> dict[LlmKind, int]:
        negative = sorted(k for k, v in value.items() if v < 0)
        if negative:
            raise ValueError(f"llm_calls counts must be >= 0: {negative}")
        return value

    @model_validator(mode="after")
    def _sums(self) -> Self:
        if not math.isclose(self.total_usd, self.monid_usd + self.llm_usd, abs_tol=1e-9):
            raise ValueError("total_usd must equal monid_usd + llm_usd")
        if self.elevenlabs_usd > self.monid_usd + 1e-9:
            raise ValueError("elevenlabs_usd is a breakout of monid_usd and cannot exceed it")
        for name in ("monid_runs_billed", "monid_runs_zero_results", "monid_runs_failed"):
            if getattr(self, name) > self.monid_runs:
                raise ValueError(f"{name} cannot exceed monid_runs")
        return self


class Reconciliation(SonarModel):
    fetched_at: UtcDatetime | None
    n_listed_in_window: int = Field(ge=0)
    unmatched_remote_run_ids: list[str]
    unreconciled_local_seqs: list[int]


class Incumbent(SonarModel):
    name: Literal["Brand24 Team"] = "Brand24 Team"
    price_usd_month: Literal[349] = 349
    url: str = Field(min_length=1)
    checked_at: date
    mentions_quota: Literal[10000] = 10000


class Comparison(SonarModel):
    briefs_per_month_assumed: Literal[4] = 4
    sonar_usd_month_equiv: Money
    ratio: float | None
    mentions_this_brief: int = Field(ge=0)

    @model_validator(mode="after")
    def _ratio_rule(self) -> Self:
        if self.sonar_usd_month_equiv == 0.0 and self.ratio is not None:
            raise ValueError("ratio must be null when sonar_usd_month_equiv is 0")
        if self.sonar_usd_month_equiv > 0.0 and self.ratio is None:
            raise ValueError("ratio must be set when sonar_usd_month_equiv is positive")
        return self


class MentionCounts(SonarModel):
    fetched: int = Field(ge=0)
    deduped: int = Field(ge=0)
    labelled: int = Field(ge=0)
    excluded_with_reason: dict[str, int]
    by_source: dict[Source, int]
    by_brand: dict[str, int]

    @field_validator("excluded_with_reason")
    @classmethod
    def _reasons(cls, value: dict[str, int]) -> dict[str, int]:
        bad = sorted(set(value) - EXCLUSION_REASONS)
        if bad:
            raise ValueError(f"excluded_with_reason keys not allowed: {bad}")
        return value

    @field_validator("excluded_with_reason", "by_source", "by_brand")
    @classmethod
    def _non_negative(cls, value: dict[Any, int]) -> dict[Any, int]:
        negative = sorted(str(k) for k, v in value.items() if v < 0)
        if negative:
            raise ValueError(f"counts must be >= 0: {negative}")
        return value


class Abstention(SonarModel):
    scope: AbstainScope
    brand: str | None
    source: Source | None
    reason: AbstainReason
    detail: str


def derive_verdict(replay: bool, runs: list[RunRecord], reconciliation: Reconciliation) -> Verdict:
    """CONTRACTS §Receipt verdict rule, re-derived by ``sonar verify``."""
    if replay:
        return "REPLAY"
    if (
        all(r.cost_source == "/v1/runs" for r in runs)
        and reconciliation.unmatched_remote_run_ids == []
    ):
        return "RECONCILED"
    return "PARTIAL"


class Receipt(SonarModel):
    """The card (CONTRACTS §Receipt); ``results/<session>/receipt.json``."""

    schema_rev: str = Field(min_length=1)
    sonar_rev: str = Field(min_length=1)
    session_id: str = Field(pattern=_SESSION_ID.pattern)
    timestamps: Timestamps
    replay: bool
    verdict: Verdict
    query: Query
    runs: list[RunRecord]
    totals: Totals
    reconciliation: Reconciliation
    incumbent: Incumbent
    comparison: Comparison
    mentions: MentionCounts
    abstentions: list[Abstention]
    what_could_not_be_checked: list[str]
    content_digest: str = Field(pattern=r"^([0-9a-f]{64})?$")

    @model_validator(mode="after")
    def _ledger_consistency(self) -> Self:
        seqs = [r.local_seq for r in self.runs]
        if any(b <= a for a, b in pairwise(seqs)):
            raise ValueError("runs must be ordered by strictly increasing local_seq")
        if self.totals.monid_runs != len(self.runs):
            raise ValueError("totals.monid_runs must equal len(runs)")
        billed = sum(1 for r in self.runs if r.cost_usd is not None and r.cost_usd > 0)
        if self.totals.monid_runs_billed != billed:
            raise ValueError("totals.monid_runs_billed must count runs with cost_usd > 0")
        zero = sum(1 for r in self.runs if r.n_results == 0)
        if self.totals.monid_runs_zero_results != zero:
            raise ValueError("totals.monid_runs_zero_results must count runs with n_results = 0")
        unreconciled = [r.local_seq for r in self.runs if r.cost_source == "unreconciled"]
        if sorted(self.reconciliation.unreconciled_local_seqs) != unreconciled:
            raise ValueError(
                "reconciliation.unreconciled_local_seqs must list every unreconciled run"
            )
        equiv = self.totals.total_usd * self.comparison.briefs_per_month_assumed
        if not math.isclose(
            self.comparison.sonar_usd_month_equiv, equiv, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError(
                "comparison.sonar_usd_month_equiv must equal totals.total_usd x briefs_per_month"
            )
        if self.comparison.ratio is not None and not math.isclose(
            self.comparison.ratio,
            self.incumbent.price_usd_month / self.comparison.sonar_usd_month_equiv,
            rel_tol=1e-9,
        ):
            raise ValueError("comparison.ratio must equal incumbent price / sonar_usd_month_equiv")
        return self

    @property
    def derived_verdict(self) -> Verdict:
        return derive_verdict(self.replay, self.runs, self.reconciliation)

    def compute_content_digest(self) -> str:
        """sha256 hex over canonical JSON of this receipt with ``content_digest`` set to ``""``."""
        payload = self.model_dump(mode="json")
        payload["content_digest"] = ""
        return hashlib.sha256(canonical_json(payload)).hexdigest()

    def with_content_digest(self) -> Receipt:
        return self.model_copy(update={"content_digest": self.compute_content_digest()})


# --------------------------------------------------------------------------- Digest


class DateRange(SonarModel):
    start: UtcDatetime
    end: UtcDatetime

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            raise ValueError("end precedes start")
        return self


class Window(SonarModel):
    current: DateRange
    previous: DateRange


def _p_values_rule(verdict: WowVerdict, p_raw: float | None, p_holm: float | None) -> None:
    if verdict == "ABSTAIN":
        if p_raw is not None or p_holm is not None:
            raise ValueError("p_raw and p_holm must be null on ABSTAIN")
    elif p_raw is None or p_holm is None:
        raise ValueError("p_raw and p_holm are reported unless the verdict is ABSTAIN")


class WowNet(SonarModel):
    delta: float
    ci95: CI95
    ci95_confirmed_only: CI95
    verdict: WowVerdict
    p_raw: UnitInterval | None
    p_holm: UnitInterval | None

    @model_validator(mode="after")
    def _p_values(self) -> Self:
        _p_values_rule(self.verdict, self.p_raw, self.p_holm)
        return self


class WowShare(SonarModel):
    delta: float
    ci95: CI95
    verdict: WowVerdict
    p_raw: UnitInterval | None
    p_holm: UnitInterval | None

    @model_validator(mode="after")
    def _p_values(self) -> Self:
        if self.verdict == "SIGNIFICANT":
            raise ValueError("share of voice has no confirmed-only interval; report SUGGESTIVE")
        _p_values_rule(self.verdict, self.p_raw, self.p_holm)
        return self


class SovEntry(SonarModel):
    brand: str = Field(min_length=1)
    n: int = Field(ge=0)
    n_clusters: int = Field(ge=0)
    share: UnitInterval
    ci95: CI95
    basis_sources: list[Source]
    wow: WowShare


class SentimentEntry(SonarModel):
    brand: str = Field(min_length=1)
    n: int = Field(ge=0)
    n_confirmed: int = Field(ge=0)
    pos: int = Field(ge=0)
    neg: int = Field(ge=0)
    neu: int = Field(ge=0)
    net: NetScore
    ci95: CI95
    ci95_iid: CI95
    design_effect: float = Field(ge=0.0)
    wow: WowNet

    @model_validator(mode="after")
    def _counts(self) -> Self:
        if self.n_confirmed > self.n:
            raise ValueError("n_confirmed cannot exceed n")
        return self


class BySourceEntry(SonarModel):
    brand: str = Field(min_length=1)
    source: Source
    n: int = Field(ge=0)
    n_clusters: int = Field(ge=0)
    pos: int = Field(ge=0)
    neg: int = Field(ge=0)
    neu: int = Field(ge=0)
    net: NetScore | None

    @model_validator(mode="after")
    def _net_null_when_empty(self) -> Self:
        if self.n == 0 and self.net is not None:
            raise ValueError("net must be null when n is 0")
        return self


class Event(SonarModel):
    brand: str = Field(min_length=1)
    date: date
    n: int = Field(ge=5)
    n_clusters: int = Field(ge=3)
    baseline_median: float = Field(ge=0.0)
    label: str = Field(min_length=1)
    exhibit_url: str | None

    @field_validator("label")
    @classmethod
    def _label_words(cls, value: str) -> str:
        if _word_count(value) > 6:
            raise ValueError("event label must be at most 6 words")
        return value


class TopMention(SonarModel):
    mention_id: Hex24
    brand: str = Field(min_length=1)
    source: Source
    url: str | None
    quote: str = Field(min_length=1, max_length=240)
    lang: Lang
    label: SentimentLabel
    published_at: UtcDatetime | None


class CoverageGap(SonarModel):
    source: str = Field(min_length=1)
    reason: AbstainReason
    note: str


class CostQuote(SonarModel):
    verdict: Verdict
    totals: Totals


class Narration(SonarModel):
    text: str | None = Field(max_length=900)
    chars: int = Field(ge=0)
    numbers_verified: bool
    mp3_path: str | None
    local_seq: int | None = Field(ge=1)

    @model_validator(mode="after")
    def _chars(self) -> Self:
        if self.chars != len(self.text or ""):
            raise ValueError("chars must equal len(text)")
        if self.text is None and self.mp3_path is not None:
            raise ValueError("mp3_path requires narration text")
        return self


class Digest(SonarModel):
    """The analysis output (CONTRACTS §Digest); ``digest.json``."""

    brand: str = Field(min_length=1)
    competitors: list[str] = Field(max_length=3)
    window: Window
    share_of_voice: list[SovEntry]
    sentiment: list[SentimentEntry]
    by_source: list[BySourceEntry]
    topics: list[Topic]
    events: list[Event]
    top_mentions: list[TopMention]
    abstentions: list[Abstention]
    coverage_gaps: list[CoverageGap]
    cost: CostQuote
    narration: Narration

    @model_validator(mode="after")
    def _gaps_and_topics(self) -> Self:
        if not any(g.source == "x" and g.reason == "unavailable" for g in self.coverage_gaps):
            raise ValueError("coverage_gaps must always contain {source: x, reason: unavailable}")
        keys = [(t.brand, t.topic_id) for t in self.topics]
        if keys != sorted(keys):
            raise ValueError("topics must be ordered by brand then topic_id")
        per_brand = Counter(t.brand for t in self.top_mentions)
        over = sorted(b for b, c in per_brand.items() if c > 10)
        if over:
            raise ValueError(f"top_mentions allows at most 10 per brand, exceeded for {over}")
        return self


# --------------------------------------------------------------------------- Answer


class Answer(SonarModel):
    """One line of ``answers.jsonl`` per ``sonar ask`` (CONTRACTS §Answer)."""

    session_id: str = Field(pattern=_SESSION_ID.pattern)
    brand: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str
    citations: list[Hex24]
    numbers_verified: list[str]
    retrieved: list[Hex24] = Field(max_length=20)
    model: str
    usage: Usage
    status: AnswerStatus

    @model_validator(mode="after")
    def _status_rules(self) -> Self:
        if self.status == "refused" and self.answer != "":
            raise ValueError("a refused answer carries an empty answer string")
        return self


RECORDS: dict[str, type[SonarModel]] = {
    "Query": Query,
    "Mention": Mention,
    "Label": Label,
    "RunRecord": RunRecord,
    "Topic": Topic,
    "Receipt": Receipt,
    "Digest": Digest,
    "Answer": Answer,
}
"""Every top-level CONTRACTS record by its contract name."""

__all__ = [
    "AUTHOR_CLUSTER_SOURCES",
    "CI95",
    "COMMENT_SOURCES",
    "ENGAGEMENT_KEYS",
    "EXCLUSION_REASONS",
    "MENTION_ID_CLUSTER_SOURCES",
    "PROFILE_SOURCES",
    "RECORDS",
    "REVIEW_SOURCES",
    "SCHEMA_REV",
    "SOURCES",
    "AbstainReason",
    "AbstainScope",
    "Abstention",
    "Answer",
    "AnswerStatus",
    "BySourceEntry",
    "Comparison",
    "Corroboration",
    "CostQuote",
    "CostSource",
    "CoverageGap",
    "DateRange",
    "DecidedBy",
    "DeterministicSignal",
    "Digest",
    "Event",
    "Incumbent",
    "Label",
    "LabelStatus",
    "Lang",
    "LlmKind",
    "Mention",
    "MentionCounts",
    "ModelSignal",
    "Narration",
    "Polarity",
    "Profile",
    "Query",
    "Receipt",
    "Reconciliation",
    "RunRecord",
    "SentimentEntry",
    "SentimentLabel",
    "SignalKind",
    "Signals",
    "SonarModel",
    "Source",
    "SovEntry",
    "Timestamps",
    "TopMention",
    "Topic",
    "TopicMethod",
    "Totals",
    "Usage",
    "UtcDatetime",
    "Verdict",
    "Window",
    "WowNet",
    "WowShare",
    "WowVerdict",
    "author_hash_for",
    "canonical_json",
    "derive_verdict",
    "expected_cluster_key",
    "input_digest_for",
    "mention_id_for",
    "normalize_term",
]
