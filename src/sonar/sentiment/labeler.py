"""Batched labeler over the LLM seam with the label cache and the two-signal policy.

``label_mentions`` takes deduplicated Mention rows (any mix of brands),
classifies the uncached ones in batches of ``BATCH_SIZE`` per brand, applies
``rules`` per brand (audit sample, cap, precedence) with one tiebreak call per
planned row, and returns every ``Label`` plus what the Receipt needs: the
audit block, the exclusions with their reason, and the LLM spend by kind.

Deterministic edges, model in nodes: the backend only ever answers
``ClassifyBatch`` requests; every decision is made here or in ``rules``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal

from sonar import config
from sonar.llm.base import ClassifyBatch, LabelObservation, LlmBackend, MentionText
from sonar.llm.base import Usage as SeamUsage
from sonar.models import Audit, Label, LlmKind, Mention, Usage
from sonar.sentiment import rules
from sonar.sentiment.cache import LabelCache
from sonar.sentiment.lexicon import Lexicon, load_lexicon
from sonar.sentiment.prompt import CLASSIFIER_SYSTEM, PROMPT_REV, TIEBREAK_SYSTEM

BATCH_SIZE: Final[int] = 20
"""Mentions per classifier call (design §W4.1: batches of 20)."""

ExclusionReason = Literal["refused", "unparseable", "error"]
IRRELEVANT_REASONS: Final[tuple[str, ...]] = ("not_about_brand", "irrelevant_label")
FAILURE_REASONS: Final[tuple[ExclusionReason, ...]] = ("refused", "unparseable", "error")


@dataclass(frozen=True)
class LabeledRow:
    """A ``Label`` joined with the brand of its Mention row (key ``(mention_id, brand)``)."""

    brand: str
    label: Label


@dataclass(frozen=True)
class Exclusion:
    """A row with no Label: the classifier call ended ``refused``, ``unparseable`` or ``error``."""

    mention_id: str
    brand: str
    reason: ExclusionReason
    detail: str


@dataclass
class Spend:
    """Calls, tokens and cost of one ``LlmKind``; cached labels are not calls."""

    calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0

    def add(self, usage: SeamUsage) -> None:
        self.calls += 1
        self.tokens += usage.tokens
        self.cost_usd += usage.cost_usd


@dataclass
class LabelRun:
    labels: list[LabeledRow] = field(default_factory=list)
    excluded: list[Exclusion] = field(default_factory=list)
    spend: dict[LlmKind, Spend] = field(default_factory=dict)
    audit: Audit = field(
        default_factory=lambda: Audit(
            n_sample=0, n_agree=0, agreement=None, tiebreak_calls=0, tiebreak_overflow=0
        )
    )
    cache_hits: int = 0

    def by_key(self) -> dict[tuple[str, str], Label]:
        return {(row.brand, row.label.mention_id): row.label for row in self.labels}

    def excluded_with_reason(self) -> dict[str, int]:
        """The five label-side keys of ``MentionCounts.excluded_with_reason``."""
        counts = dict.fromkeys(IRRELEVANT_REASONS + FAILURE_REASONS, 0)
        for row in self.labels:
            if row.label.corroboration != "irrelevant":
                continue
            if not row.label.about_brand:
                counts["not_about_brand"] += 1
            else:
                counts["irrelevant_label"] += 1
        for exclusion in self.excluded:
            counts[exclusion.reason] += 1
        return counts

    @property
    def llm_usd(self) -> float:
        return sum(spend.cost_usd for spend in self.spend.values())


# --------------------------------------------------------------------------- helpers


def apportion(usage: SeamUsage, n_items: int) -> list[Usage]:
    """Split one batch call's usage over its items; tokens sum exactly, cost splits evenly."""
    if n_items <= 0:
        raise ValueError("cannot apportion usage over zero items")
    base, remainder = divmod(usage.tokens, n_items)
    per_item = usage.cost_usd / n_items
    return [
        Usage(tokens=base + (1 if index < remainder else 0), cost_usd=per_item)
        for index in range(n_items)
    ]


def add_usage(first: Usage, second: Usage) -> Usage:
    return Usage(tokens=first.tokens + second.tokens, cost_usd=first.cost_usd + second.cost_usd)


ZERO_USAGE: Final[Usage] = Usage(tokens=0, cost_usd=0.0)


def batches(items: Sequence[MentionText], size: int = BATCH_SIZE) -> list[list[MentionText]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


@dataclass(frozen=True)
class _Observed:
    observation: LabelObservation
    cached: bool
    usage: Usage


class Labeler:
    """Holds the backend, models, cache and lexicon; ``run`` labels one session's rows."""

    def __init__(
        self,
        backend: LlmBackend,
        *,
        models: config.LlmModels = config.LLM,
        cache: LabelCache | None = None,
        lexicon: Lexicon | None = None,
        prompt_rev: str = PROMPT_REV,
        seed: int = config.SEED,
        batch_size: int = BATCH_SIZE,
    ) -> None:
        self._backend = backend
        self._models = models
        self._cache = cache
        self._lexicon = lexicon if lexicon is not None else load_lexicon()
        self._prompt_rev = prompt_rev
        self._seed = seed
        self._batch_size = batch_size

    # ----------------------------------------------------------------- classifier

    def _classify_brand(
        self, brand: str, brand_hint: str | None, mentions: Sequence[Mention], run: LabelRun
    ) -> dict[str, _Observed]:
        observed: dict[str, _Observed] = {}
        pending: list[MentionText] = []
        model = self._models.classifier_model
        for mention in mentions:
            cached = (
                None
                if self._cache is None
                else self._cache.get(mention.mention_id, self._prompt_rev, model)
            )
            if cached is not None:
                observed[mention.mention_id] = _Observed(cached, cached=True, usage=ZERO_USAGE)
                run.cache_hits += 1
            else:
                pending.append(MentionText(mention_id=mention.mention_id, text=mention.text))
        for batch_items in batches(pending, self._batch_size):
            batch = ClassifyBatch(
                system=CLASSIFIER_SYSTEM, brand=brand, brand_hint=brand_hint, items=batch_items
            )
            result = self._backend.classify(batch, model)
            run.spend.setdefault("classify", Spend()).add(result.usage)
            shares = apportion(result.usage, len(batch_items))
            for observation, share in zip(result.observations, shares, strict=True):
                observed[observation.mention_id] = _Observed(observation, cached=False, usage=share)
                if self._cache is not None:
                    self._cache.put(
                        observation.mention_id, self._prompt_rev, model, brand, observation
                    )
        return observed

    # ----------------------------------------------------------------- tiebreak

    def _tiebreak(
        self, brand: str, brand_hint: str | None, mention: Mention, run: LabelRun
    ) -> tuple[LabelObservation, Usage]:
        batch = ClassifyBatch(
            system=TIEBREAK_SYSTEM,
            brand=brand,
            brand_hint=brand_hint,
            items=[MentionText(mention_id=mention.mention_id, text=mention.text)],
        )
        result = self._backend.classify(batch, self._models.tiebreak_model)
        run.spend.setdefault("tiebreak", Spend()).add(result.usage)
        observation = result.observations[0]
        return observation, Usage(tokens=result.usage.tokens, cost_usd=result.usage.cost_usd)

    # ----------------------------------------------------------------- one brand

    def _label_brand(
        self, brand: str, brand_hint: str | None, mentions: Sequence[Mention], run: LabelRun
    ) -> tuple[int, int, int, int, int]:
        """Returns (tiebreak_calls, n_sample, n_agree, overflow, n_rows) for the audit block."""
        observed = self._classify_brand(brand, brand_hint, mentions, run)
        classifier_model = self._models.classifier_model
        tiebreak_model = self._models.tiebreak_model
        policy_rows: dict[str, rules.PolicyRow] = {}
        deterministic = {
            m.mention_id: rules.deterministic_signal(m, self._lexicon) for m in mentions
        }
        for mention in mentions:
            seen = observed[mention.mention_id]
            if seen.observation.status != "ok":
                status = seen.observation.status
                assert status in FAILURE_REASONS
                run.excluded.append(
                    Exclusion(
                        mention_id=mention.mention_id,
                        brand=brand,
                        reason=status,
                        detail=seen.observation.rationale or "",
                    )
                )
                continue
            if rules.is_policy_row(mention, seen.observation):
                policy_rows[mention.mention_id] = rules.PolicyRow(
                    mention, seen.observation, deterministic[mention.mention_id]
                )
        plan = rules.plan_tiebreaks(list(policy_rows.values()), self._seed)
        tiebreaks: dict[str, tuple[LabelObservation, Usage]] = {}
        for mention_id in plan.call:
            planned = policy_rows[mention_id]
            tiebreaks[mention_id] = self._tiebreak(brand, brand_hint, planned.mention, run)

        n_sample = 0
        n_agree = 0
        for mention_id in plan.audit:
            observation, _ = tiebreaks[mention_id]
            if observation.status != "ok":
                continue
            n_sample += 1
            if observation.label == policy_rows[mention_id].classifier.label:
                n_agree += 1

        for mention in mentions:
            seen = observed[mention.mention_id]
            if seen.observation.status != "ok":
                continue
            row = policy_rows.get(mention.mention_id)
            if row is None:
                label = rules.irrelevant_label(
                    mention,
                    seen.observation,
                    deterministic[mention.mention_id],
                    classifier_model=classifier_model,
                    classifier_cached=seen.cached,
                    usage=seen.usage,
                    prompt_rev=self._prompt_rev,
                )
            else:
                called = tiebreaks.get(mention.mention_id)
                tiebreak = None if called is None else called[0]
                usage = seen.usage if called is None else add_usage(seen.usage, called[1])
                label = rules.build_label(
                    row,
                    tiebreak,
                    audited=mention.mention_id in plan.audit,
                    classifier_model=classifier_model,
                    tiebreak_model=tiebreak_model,
                    classifier_cached=seen.cached,
                    usage=usage,
                    prompt_rev=self._prompt_rev,
                )
            run.labels.append(LabeledRow(brand=brand, label=label))
        return len(plan.call), n_sample, n_agree, len(plan.overflow), plan.n_rows

    # ----------------------------------------------------------------- session

    def run(
        self, mentions: Sequence[Mention], *, brand_hints: Mapping[str, str | None] | None = None
    ) -> LabelRun:
        """Label every ``(mention_id, brand)`` row; rows are grouped by brand in first-seen order."""
        keys = [(m.mention_id, m.brand) for m in mentions]
        if len(set(keys)) != len(keys):
            raise ValueError("mentions must be deduplicated: (mention_id, brand) repeats")
        hints = dict(brand_hints or {})
        by_brand: dict[str, list[Mention]] = defaultdict(list)
        for mention in mentions:
            by_brand[mention.brand].append(mention)
        run = LabelRun()
        calls = sample = agree = overflow = 0
        for brand, rows in by_brand.items():
            b_calls, b_sample, b_agree, b_overflow, _ = self._label_brand(
                brand, hints.get(brand), rows, run
            )
            calls += b_calls
            sample += b_sample
            agree += b_agree
            overflow += b_overflow
        run.audit = Audit(
            n_sample=sample,
            n_agree=agree,
            agreement=None if sample == 0 else agree / sample,
            tiebreak_calls=calls,
            tiebreak_overflow=overflow,
        )
        return run


def label_mentions(
    mentions: Sequence[Mention],
    backend: LlmBackend,
    *,
    brand_hints: Mapping[str, str | None] | None = None,
    models: config.LlmModels = config.LLM,
    cache: LabelCache | None = None,
    lexicon: Lexicon | None = None,
    seed: int = config.SEED,
) -> LabelRun:
    """One-shot entry point: build a ``Labeler`` and run it over the session's rows."""
    labeler = Labeler(backend, models=models, cache=cache, lexicon=lexicon, seed=seed)
    return labeler.run(mentions, brand_hints=brand_hints)


__all__ = [
    "BATCH_SIZE",
    "FAILURE_REASONS",
    "IRRELEVANT_REASONS",
    "ZERO_USAGE",
    "Exclusion",
    "ExclusionReason",
    "LabelRun",
    "LabeledRow",
    "Labeler",
    "Spend",
    "add_usage",
    "apportion",
    "batches",
    "label_mentions",
]
