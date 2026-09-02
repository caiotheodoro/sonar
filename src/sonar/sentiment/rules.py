"""The two-signal labelling policy, exactly as PRE-REGISTRATION v1.1.1 and CONTRACTS §Label state it.

Pure functions over model observations; no model is called here. The model
supplies observations (``LabelObservation``), code decides. In order:

1. Relevance gate: ``about_brand`` (classifier) and ``matched_terms`` non-empty
   (regex, carried on the Mention). A row that fails it is ``irrelevant``.
   A row whose classifier label is ``irrelevant`` while ``about_brand`` is
   true is also ``irrelevant`` (exclusion reason ``irrelevant_label``); the
   deterministic signal is a polarity and can never confirm it, so such a row
   is not a policy row and never spends a tiebreak.
2. Deterministic signal: rating bucket for review sources (``≤ 2`` negative,
   ``3`` neutral, ``≥ 4`` positive), lexicon sign otherwise; a review row
   without a rating falls back to the lexicon like any other row.
3. Tiebreak trigger: (a) classifier disagrees with a non-null deterministic
   label, or (b) null deterministic label and classifier confidence below
   ``config.TIEBREAK_CONFIDENCE_THRESHOLD``; plus (c) the fixed audit sample.
4. Audit sample: ``floor(AUDIT_SAMPLE_FRACTION · n)`` of the brand's policy
   rows, drawn with ``config.SEED`` from the rows sorted by ``mention_id``.
5. Cap: at most ``floor(TIEBREAK_CAP_FRACTION · n)`` rows per brand get a
   tiebreak; audit rows first, then triggered rows in ``published_at`` order
   (null last, ties by ``mention_id``). Triggered rows beyond the cap keep the
   classifier label with ``overflow=true``.
6. Precedence 1–4 of CONTRACTS §Two-signal policy in ``corroborate``.

Denominator for the sample and the cap: relevant mention–brand rows after
dedup, per brand, per session (a mention kept for two brands is two rows).

One case the frozen text does not name: a tiebreak answer that is not a
polarity (label ``irrelevant`` or ``about_brand=false``) cannot be adopted,
because CONTRACTS makes ``label=irrelevant`` imply ``corroboration=irrelevant``
and ``decided_by=tiebreak`` imply ``contested``. Such an answer is recorded
in ``signals.tiebreak`` and counted in the audit as a disagreement, and the
row keeps the classifier label as ``model_only`` (N5: no tiebreak adopted and
not confirmed), the same treatment as a failed tiebreak call.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, get_args

import numpy as np

from sonar import config
from sonar.llm.base import LabelObservation, clip_rationale
from sonar.models import (
    Corroboration,
    DecidedBy,
    DeterministicSignal,
    Label,
    LabelStatus,
    Mention,
    ModelSignal,
    Polarity,
    SentimentLabel,
    Signals,
    Usage,
)
from sonar.sentiment.lexicon import Lexicon

POLARITIES: Final[frozenset[str]] = frozenset(get_args(Polarity))
FAILED_TIEBREAK_CONFIDENCE: Final[float] = 0.0
"""Confidence recorded on a tiebreak ``ModelSignal`` whose call did not return ``ok``."""


# --------------------------------------------------------------------------- gates and signals


def is_relevant(mention: Mention, classifier: LabelObservation) -> bool:
    """Relevance = ``about_brand`` (model) and ``matched_terms`` non-empty (regex)."""
    return bool(classifier.about_brand) and len(mention.matched_terms) > 0


def is_policy_row(mention: Mention, classifier: LabelObservation) -> bool:
    """A relevant row with an ``ok`` classifier observation carrying a polarity label."""
    return (
        classifier.status == "ok"
        and is_relevant(mention, classifier)
        and classifier.label in POLARITIES
    )


def rating_bucket(rating: int) -> Polarity:
    if rating <= config.RATING_NEGATIVE_MAX:
        return "negative"
    if rating >= config.RATING_POSITIVE_MIN:
        return "positive"
    return "neutral"


def deterministic_signal(mention: Mention, lexicon: Lexicon) -> DeterministicSignal:
    """Rating bucket for review sources with a rating; lexicon sign otherwise."""
    if mention.source in config.REVIEW_SOURCES and mention.rating is not None:
        return DeterministicSignal(kind="rating", label=rating_bucket(mention.rating))
    score = lexicon.score(mention.text)
    if score.n_hits == 0:
        return DeterministicSignal(kind="none", label=None)
    return DeterministicSignal(kind="lexicon", label=score.sign)


def tiebreak_trigger(
    classifier_label: SentimentLabel, classifier_confidence: float, deterministic: Polarity | None
) -> bool:
    """Trigger (a): disagreement with a non-null signal; (b): null signal and low confidence."""
    if deterministic is not None:
        return classifier_label != deterministic
    return classifier_confidence < config.TIEBREAK_CONFIDENCE_THRESHOLD


# --------------------------------------------------------------------------- sample and cap


def audit_sample_size(n_rows: int) -> int:
    return math.floor(config.AUDIT_SAMPLE_FRACTION * n_rows)


def tiebreak_cap(n_rows: int) -> int:
    return math.floor(config.TIEBREAK_CAP_FRACTION * n_rows)


def audit_sample(mention_ids: Iterable[str], seed: int = config.SEED) -> frozenset[str]:
    """The fixed audit sample of one brand's policy rows: sorted ids, ``seed``, no replacement."""
    ordered = sorted(set(mention_ids))
    k = audit_sample_size(len(ordered))
    if k == 0:
        return frozenset()
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(ordered), size=k, replace=False)
    return frozenset(ordered[int(i)] for i in picked)


@dataclass(frozen=True)
class PolicyRow:
    """One relevant mention–brand row with its classifier observation and deterministic signal."""

    mention: Mention
    classifier: LabelObservation
    deterministic: DeterministicSignal

    @property
    def mention_id(self) -> str:
        return self.mention.mention_id

    @property
    def triggered(self) -> bool:
        assert self.classifier.label is not None and self.classifier.confidence is not None
        return tiebreak_trigger(
            self.classifier.label, self.classifier.confidence, self.deterministic.label
        )


def published_order_key(mention: Mention) -> tuple[int, datetime | None, str]:
    """``published_at`` ascending, null last, then ``mention_id``."""
    published = mention.published_at
    if published is None:
        return (1, None, mention.mention_id)
    return (0, published, mention.mention_id)


def _published_sort_key(row: PolicyRow) -> tuple[int, float, str]:
    null_last, published, mention_id = published_order_key(row.mention)
    return (null_last, 0.0 if published is None else published.timestamp(), mention_id)


@dataclass(frozen=True)
class TiebreakPlan:
    """Which of one brand's policy rows get a tiebreak call, and which overflowed the cap."""

    n_rows: int
    cap: int
    audit: frozenset[str]
    call: tuple[str, ...]
    overflow: frozenset[str]

    def __post_init__(self) -> None:
        if len(self.call) > self.cap:
            raise ValueError(f"plan calls {len(self.call)} rows over a cap of {self.cap}")
        if not self.audit <= set(self.call):
            raise ValueError("every audit row must receive a tiebreak call")
        if self.overflow & set(self.call):
            raise ValueError("a row cannot be both called and overflowed")


def plan_tiebreaks(rows: Sequence[PolicyRow], seed: int = config.SEED) -> TiebreakPlan:
    """Audit sample first, then triggered rows in ``published_at`` order, up to the cap."""
    ids = [row.mention_id for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("policy rows of one brand must have distinct mention_ids")
    n = len(rows)
    cap = tiebreak_cap(n)
    audit = audit_sample(ids, seed)
    call: list[str] = sorted(audit)
    overflow: set[str] = set()
    triggered = sorted((row for row in rows if row.triggered), key=_published_sort_key)
    for row in triggered:
        if row.mention_id in audit:
            continue
        if len(call) < cap:
            call.append(row.mention_id)
        else:
            overflow.add(row.mention_id)
    return TiebreakPlan(
        n_rows=n, cap=cap, audit=audit, call=tuple(call), overflow=frozenset(overflow)
    )


# --------------------------------------------------------------------------- precedence


@dataclass(frozen=True)
class Decision:
    label: SentimentLabel
    corroboration: Corroboration
    decided_by: DecidedBy
    confidence: float
    rationale: str
    overflow: bool


def _adoptable(tiebreak: LabelObservation) -> bool:
    return tiebreak.status == "ok" and bool(tiebreak.about_brand) and tiebreak.label in POLARITIES


def corroborate(
    classifier: LabelObservation,
    deterministic: Polarity | None,
    tiebreak: LabelObservation | None,
    *,
    audited: bool,
) -> Decision:
    """CONTRACTS §Two-signal policy precedence 1–4 for one policy row.

    ``tiebreak`` is ``None`` when no call was made: for a triggered row that
    means the cap was hit (``overflow``); for an untriggered, unaudited row it
    is the normal case. An audited row always has a call, so ``tiebreak`` must
    not be ``None`` when ``audited``.
    """
    if classifier.status != "ok" or classifier.label not in POLARITIES:
        raise ValueError(
            "corroborate takes a policy row: an ok classifier observation with a polarity label"
        )
    assert classifier.label is not None and classifier.confidence is not None
    if audited and tiebreak is None:
        raise ValueError("an audited row always receives a tiebreak call")
    label = classifier.label
    confidence = classifier.confidence
    rationale = clip_rationale(classifier.rationale or "")
    triggered = tiebreak_trigger(label, confidence, deterministic)
    if not triggered and not audited and tiebreak is not None:
        raise ValueError("a tiebreak was called on a row the policy never sends")

    # Rule 1: agreement with a non-null deterministic signal is confirmed; nothing overrides it.
    if deterministic is not None and label == deterministic:
        return Decision(label, "confirmed", "classifier", confidence, rationale, overflow=False)

    if triggered:
        # Rule 3: met (a) or (b) but the cap was already reached.
        if tiebreak is None:
            return Decision(label, "model_only", "classifier", confidence, rationale, overflow=True)
        # Rule 2: the tiebreak wins when it disagrees and confirms when it agrees.
        if not _adoptable(tiebreak):
            return Decision(
                label, "model_only", "classifier", confidence, rationale, overflow=False
            )
        assert tiebreak.label is not None and tiebreak.confidence is not None
        if tiebreak.label == label:
            return Decision(label, "confirmed", "classifier", confidence, rationale, overflow=False)
        return Decision(
            tiebreak.label,
            "contested",
            "tiebreak",
            tiebreak.confidence,
            clip_rationale(tiebreak.rationale or ""),
            overflow=False,
        )

    # Not triggered and not confirmed: null deterministic signal with confidence at or
    # above the threshold. Rule 4: an audit-only tiebreak is never adopted (D013 A2).
    return Decision(label, "model_only", "classifier", confidence, rationale, overflow=False)


# --------------------------------------------------------------------------- Label assembly


def model_signal(observation: LabelObservation, model: str, *, cached: bool = False) -> ModelSignal:
    """The ``ModelSignal`` for an ``ok`` observation; ``cached`` marks a cache-served classifier."""
    assert observation.label is not None and observation.confidence is not None
    status: LabelStatus = "cached" if cached else "ok"
    return ModelSignal(
        model=model, label=observation.label, confidence=observation.confidence, status=status
    )


def failed_tiebreak_signal(
    classifier: LabelObservation, tiebreak: LabelObservation, model: str
) -> ModelSignal:
    """A tiebreak call that did not return ``ok``: the classifier's label with confidence 0."""
    assert classifier.label is not None
    if tiebreak.status == "ok":
        raise ValueError("failed_tiebreak_signal takes a non-ok observation")
    return ModelSignal(
        model=model,
        label=classifier.label,
        confidence=FAILED_TIEBREAK_CONFIDENCE,
        status=tiebreak.status,
    )


def tiebreak_signal(
    classifier: LabelObservation, tiebreak: LabelObservation | None, model: str
) -> ModelSignal | None:
    if tiebreak is None:
        return None
    if tiebreak.status == "ok":
        return model_signal(tiebreak, model)
    return failed_tiebreak_signal(classifier, tiebreak, model)


def irrelevant_label(
    mention: Mention,
    classifier: LabelObservation,
    deterministic: DeterministicSignal,
    *,
    classifier_model: str,
    classifier_cached: bool,
    usage: Usage,
    prompt_rev: str = config.PROMPT_REV,
) -> Label:
    """A row outside the relevance gate or labelled ``irrelevant``: corroboration ``irrelevant``."""
    assert classifier.label is not None and classifier.confidence is not None
    return Label(
        mention_id=mention.mention_id,
        label="irrelevant",
        about_brand=bool(classifier.about_brand),
        confidence=classifier.confidence,
        rationale=clip_rationale(classifier.rationale or ""),
        topic_id=None,
        signals=Signals(
            classifier=model_signal(classifier, classifier_model, cached=classifier_cached),
            tiebreak=None,
            deterministic=deterministic,
            overflow=False,
        ),
        corroboration="irrelevant",
        decided_by="classifier",
        prompt_rev=prompt_rev,
        status="cached" if classifier_cached else "ok",
        usage=usage,
    )


def build_label(
    row: PolicyRow,
    tiebreak: LabelObservation | None,
    *,
    audited: bool,
    classifier_model: str,
    tiebreak_model: str,
    classifier_cached: bool,
    usage: Usage,
    prompt_rev: str = config.PROMPT_REV,
) -> Label:
    """Apply the precedence to one policy row and assemble the CONTRACTS ``Label``."""
    decision = corroborate(row.classifier, row.deterministic.label, tiebreak, audited=audited)
    cached = classifier_cached and tiebreak is None
    return Label(
        mention_id=row.mention_id,
        label=decision.label,
        about_brand=True,
        confidence=decision.confidence,
        rationale=decision.rationale,
        topic_id=None,
        signals=Signals(
            classifier=model_signal(row.classifier, classifier_model, cached=classifier_cached),
            tiebreak=tiebreak_signal(row.classifier, tiebreak, tiebreak_model),
            deterministic=row.deterministic,
            overflow=decision.overflow,
        ),
        corroboration=decision.corroboration,
        decided_by=decision.decided_by,
        prompt_rev=prompt_rev,
        status="cached" if cached else "ok",
        usage=usage,
    )


__all__ = [
    "FAILED_TIEBREAK_CONFIDENCE",
    "POLARITIES",
    "Decision",
    "PolicyRow",
    "TiebreakPlan",
    "audit_sample",
    "audit_sample_size",
    "build_label",
    "corroborate",
    "deterministic_signal",
    "failed_tiebreak_signal",
    "irrelevant_label",
    "is_policy_row",
    "is_relevant",
    "model_signal",
    "plan_tiebreaks",
    "published_order_key",
    "rating_bucket",
    "tiebreak_cap",
    "tiebreak_signal",
    "tiebreak_trigger",
]
