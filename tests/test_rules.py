"""Two-signal policy (PRE-REGISTRATION v1.1.1, CONTRACTS §Label): the exhaustive matrix.

Every ``corroborate`` outcome is checked twice: against the expectation
written here from the frozen text, and by assembling the CONTRACTS ``Label``
through ``build_label`` so ``models.Label``'s own validators (an independent
encoding of the same rules) accept it.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, get_args

import pytest

from sonar import config
from sonar.llm.base import LabelObservation
from sonar.models import (
    Corroboration,
    DecidedBy,
    DeterministicSignal,
    Label,
    Mention,
    Polarity,
    SentimentLabel,
    Source,
    Usage,
    mention_id_for,
)
from sonar.sentiment import rules
from sonar.sentiment.lexicon import (
    Lexicon,
    LexiconError,
    load_lexicon,
    load_lexicon_file,
    parse_lexicon_lines,
)

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
CLASSIFIER = config.CLASSIFIER_MODEL_DEFAULT
TIEBREAK = config.TIEBREAK_MODEL_DEFAULT
POLARITIES: tuple[Polarity, ...] = get_args(Polarity)
LOW = config.TIEBREAK_CONFIDENCE_THRESHOLD - 0.3
HIGH = config.TIEBREAK_CONFIDENCE_THRESHOLD + 0.3
AT_THRESHOLD = config.TIEBREAK_CONFIDENCE_THRESHOLD
USAGE = Usage(tokens=30, cost_usd=0.00001)


# --------------------------------------------------------------------------- builders


def mention(
    key: str,
    text: str = "Comentário sobre o Nubank",
    *,
    source: Source = "reddit",
    rating: int | None = None,
    published_at: datetime | None = T0,
    matched_terms: list[str] | None = None,
) -> Mention:
    mid = mention_id_for(source, key)
    cluster_key = "post-1" if source == "reddit" else mid
    return Mention(
        mention_id=mid,
        brand="Nubank",
        source=source,
        run_id="run_01",
        native_id=key,
        url=None,
        author_hash=None,
        text=text,
        lang="pt",
        published_at=published_at,
        engagement={},
        rating=rating,
        cluster_key=cluster_key,
        matched_terms=["nubank"] if matched_terms is None else matched_terms,
        raw_ref="1#0",
    )


def obs(
    mention_id: str,
    label: SentimentLabel = "positive",
    confidence: float = HIGH,
    *,
    about_brand: bool = True,
    status: Literal["ok", "refused", "unparseable", "error"] = "ok",
    rationale: str = "Says so.",
) -> LabelObservation:
    if status != "ok":
        return LabelObservation.failed(mention_id, status, rationale)
    return LabelObservation(
        mention_id=mention_id,
        status="ok",
        label=label,
        about_brand=about_brand,
        confidence=confidence,
        rationale=rationale,
    )


@pytest.fixture(scope="module")
def lexicon() -> Lexicon:
    return load_lexicon()


# --------------------------------------------------------------------------- lexicon


class TestLexicon:
    def test_files_parse_and_disjoint_polarities(self) -> None:
        pt = load_lexicon_file("pt")
        en = load_lexicon_file("en")
        assert pt and en
        for table in (pt, en):
            assert set(table.values()) <= {1, -1}
        shared = set(pt) & set(en)
        assert all(pt[t] == en[t] for t in shared)

    @pytest.mark.parametrize(
        ("text", "sign"),
        [
            ("Adorei o app, atendimento excelente", "positive"),
            ("Não recomendo, atendimento péssimo", "negative"),
            ("I love it, works great", "positive"),
            ("Not recommended, the app is broken", "negative"),
            ("NÃO RECOMENDO!!!", "negative"),
        ],
    )
    def test_sign(self, lexicon: Lexicon, text: str, sign: Polarity) -> None:
        assert lexicon.sign(text) == sign

    def test_negated_phrase_wins_over_its_subword(self, lexicon: Lexicon) -> None:
        score = lexicon.score("eu não recomendo")
        assert [h.term for h in score.hits] == ["não recomendo"]
        assert score.score == -1

    def test_zero_score_with_hits_is_lexicon_null(self, lexicon: Lexicon) -> None:
        score = lexicon.score("bom mas ruim")
        assert score.n_hits == 2 and score.score == 0 and score.sign is None

    def test_no_hits(self, lexicon: Lexicon) -> None:
        score = lexicon.score("Relatório trimestral publicado na terça")
        assert score.n_hits == 0 and score.sign is None

    def test_word_boundaries(self) -> None:
        lex = Lexicon({"bom": 1})
        assert lex.score("bombeiro").n_hits == 0
        assert lex.score("muito bom!").n_hits == 1

    def test_parse_rejects_bad_lines(self) -> None:
        with pytest.raises(LexiconError):
            parse_lexicon_lines(["bom"])
        with pytest.raises(LexiconError):
            parse_lexicon_lines(["*\tbom"])
        with pytest.raises(LexiconError):
            parse_lexicon_lines(["+\tbom", "-\tBom"])
        assert parse_lexicon_lines(["# c", "", "+\tBom  Dia"]) == {"bom dia": 1}

    def test_empty_lexicon_rejected(self) -> None:
        with pytest.raises(LexiconError):
            Lexicon({})


# --------------------------------------------------------------------------- deterministic signal


class TestDeterministicSignal:
    @pytest.mark.parametrize(
        ("rating", "label"),
        [(1, "negative"), (2, "negative"), (3, "neutral"), (4, "positive"), (5, "positive")],
    )
    def test_rating_bucket(self, lexicon: Lexicon, rating: int, label: Polarity) -> None:
        m = mention(f"r{rating}", "texto sem sinal", source="google_maps", rating=rating)
        signal = rules.deterministic_signal(m, lexicon)
        assert signal.kind == "rating" and signal.label == label
        assert rules.rating_bucket(rating) == label

    def test_rating_thresholds_are_config(self) -> None:
        assert rules.rating_bucket(config.RATING_NEGATIVE_MAX) == "negative"
        assert rules.rating_bucket(config.RATING_NEGATIVE_MAX + 1) == "neutral"
        assert rules.rating_bucket(config.RATING_POSITIVE_MIN) == "positive"

    def test_rating_beats_lexicon_on_review_sources(self, lexicon: Lexicon) -> None:
        m = mention("r", "péssimo, horrível", source="trustpilot", rating=5)
        assert rules.deterministic_signal(m, lexicon).label == "positive"

    def test_review_source_without_rating_uses_lexicon(self, lexicon: Lexicon) -> None:
        m = mention("nr", "péssimo atendimento", source="facebook", rating=None)
        signal = rules.deterministic_signal(m, lexicon)
        assert signal.kind == "lexicon" and signal.label == "negative"

    def test_lexicon_kinds(self, lexicon: Lexicon) -> None:
        assert rules.deterministic_signal(mention("a", "adorei"), lexicon).model_dump() == {
            "kind": "lexicon",
            "label": "positive",
        }
        assert rules.deterministic_signal(mention("b", "bom mas ruim"), lexicon).model_dump() == {
            "kind": "lexicon",
            "label": None,
        }
        assert rules.deterministic_signal(mention("c", "relatório"), lexicon).model_dump() == {
            "kind": "none",
            "label": None,
        }


# --------------------------------------------------------------------------- gates and trigger


class TestGates:
    def test_relevance_requires_both_signals(self) -> None:
        m = mention("g")
        assert rules.is_relevant(m, obs(m.mention_id, about_brand=True))
        assert not rules.is_relevant(m, obs(m.mention_id, about_brand=False))
        bare = m.model_copy(update={"matched_terms": ["nubank"]})
        assert rules.is_relevant(bare, obs(m.mention_id))

    def test_policy_row_excludes_irrelevant_label_and_failures(self) -> None:
        m = mention("p")
        assert rules.is_policy_row(m, obs(m.mention_id, "neutral"))
        assert not rules.is_policy_row(m, obs(m.mention_id, "irrelevant"))
        assert not rules.is_policy_row(m, obs(m.mention_id, about_brand=False))
        assert not rules.is_policy_row(m, obs(m.mention_id, status="refused"))

    @pytest.mark.parametrize(
        ("label", "confidence", "deterministic", "expected"),
        [
            ("positive", HIGH, "positive", False),
            ("positive", LOW, "positive", False),
            ("positive", HIGH, "negative", True),
            ("neutral", LOW, "positive", True),
            ("positive", LOW, None, True),
            ("positive", HIGH, None, False),
            ("positive", AT_THRESHOLD, None, False),
        ],
    )
    def test_trigger(
        self,
        label: SentimentLabel,
        confidence: float,
        deterministic: Polarity | None,
        expected: bool,
    ) -> None:
        assert rules.tiebreak_trigger(label, confidence, deterministic) is expected


# --------------------------------------------------------------------------- sample and cap


class TestSampleAndCap:
    def test_sizes_are_floor_of_config_fractions(self) -> None:
        for n in (0, 1, 9, 10, 19, 20, 25, 50, 101):
            assert rules.audit_sample_size(n) == int(config.AUDIT_SAMPLE_FRACTION * n // 1)
            assert rules.tiebreak_cap(n) == int(config.TIEBREAK_CAP_FRACTION * n // 1)
            assert rules.audit_sample_size(n) <= rules.tiebreak_cap(n)

    def test_audit_sample_is_fixed_by_seed_and_ids(self) -> None:
        ids = [mention_id_for("reddit", f"s{i}") for i in range(40)]
        first = rules.audit_sample(ids)
        assert len(first) == rules.audit_sample_size(40) == 4
        assert first <= set(ids)
        assert rules.audit_sample(list(reversed(ids))) == first
        assert rules.audit_sample(ids, seed=config.SEED) == first
        assert rules.audit_sample(ids, seed=config.SEED + 1) != first
        assert rules.audit_sample(ids[:9]) == frozenset()

    def test_plan_audit_first_then_published_order_then_overflow(self, lexicon: Lexicon) -> None:
        rows: list[rules.PolicyRow] = []
        for i in range(30):
            when = T0 + timedelta(minutes=30 - i) if i % 7 else None
            m = mention(f"c{i}", "adorei o app", published_at=when)
            # every classifier disagrees with the positive lexicon signal: all rows trigger
            rows.append(
                rules.PolicyRow(
                    m, obs(m.mention_id, "negative"), rules.deterministic_signal(m, lexicon)
                )
            )
        plan = rules.plan_tiebreaks(rows)
        assert plan.n_rows == 30 and plan.cap == 12 and len(plan.audit) == 3
        assert len(plan.call) == 12
        assert set(plan.call[:3]) == plan.audit
        assert len(plan.overflow) == 18
        assert plan.audit.isdisjoint(plan.overflow)
        by_id = {row.mention_id: row for row in rows}
        ordered = sorted(
            (row for row in rows if row.mention_id not in plan.audit),
            key=lambda row: rules.published_order_key(row.mention),
        )
        assert list(plan.call[3:]) == [row.mention_id for row in ordered[:9]]
        assert plan.overflow == {row.mention_id for row in ordered[9:]}
        # null published_at sorts last
        nulls = [row.mention_id for row in ordered if row.mention.published_at is None]
        assert nulls and all(by_id[n].mention.published_at is None for n in nulls)
        assert ordered[-len(nulls) :] == [by_id[n] for n in nulls]

    def test_plan_untriggered_rows_only_called_when_audited(self, lexicon: Lexicon) -> None:
        rows = []
        for i in range(20):
            m = mention(f"u{i}", "adorei o app")
            rows.append(
                rules.PolicyRow(
                    m, obs(m.mention_id, "positive"), rules.deterministic_signal(m, lexicon)
                )
            )
        plan = rules.plan_tiebreaks(rows)
        assert set(plan.call) == plan.audit and len(plan.audit) == 2
        assert plan.overflow == frozenset()

    def test_plan_rejects_duplicate_ids(self, lexicon: Lexicon) -> None:
        m = mention("d")
        row = rules.PolicyRow(m, obs(m.mention_id), rules.deterministic_signal(m, lexicon))
        with pytest.raises(ValueError):
            rules.plan_tiebreaks([row, row])


# --------------------------------------------------------------------------- exhaustive matrix

TiebreakCase = Literal["none", "agree", "disagree", "failed", "irrelevant", "not_about_brand"]
TIEBREAK_CASES: tuple[TiebreakCase, ...] = get_args(TiebreakCase)


def tiebreak_for(
    case: TiebreakCase, classifier_label: Polarity, mention_id: str
) -> LabelObservation | None:
    other = next(p for p in POLARITIES if p != classifier_label)
    match case:
        case "none":
            return None
        case "agree":
            return obs(mention_id, classifier_label, 0.77, rationale="Second reader agrees.")
        case "disagree":
            return obs(mention_id, other, 0.66, rationale="Second reader disagrees.")
        case "failed":
            return obs(mention_id, status="refused", rationale="refused")
        case "irrelevant":
            return obs(mention_id, "irrelevant", 0.9)
        case "not_about_brand":
            return obs(mention_id, other, 0.9, about_brand=False)


def expected_outcome(
    deterministic: Polarity | None,
    classifier_label: Polarity,
    confidence: float,
    tiebreak: LabelObservation | None,
) -> tuple[Corroboration, DecidedBy, SentimentLabel, bool]:
    """PRE-REGISTRATION v1.1.1 §Two-signal labelling policy, precedence 1-4, restated."""
    disagrees = deterministic is not None and classifier_label != deterministic
    low = deterministic is None and confidence < config.TIEBREAK_CONFIDENCE_THRESHOLD
    if deterministic is not None and not disagrees:
        return ("confirmed", "classifier", classifier_label, False)  # rule 1
    if disagrees or low:
        if tiebreak is None:
            return ("model_only", "classifier", classifier_label, True)  # rule 3
        adopted = tiebreak.status == "ok" and tiebreak.about_brand and tiebreak.label in POLARITIES
        if not adopted:
            return ("model_only", "classifier", classifier_label, False)  # N5 failed call
        assert tiebreak.label is not None
        if tiebreak.label == classifier_label:
            return ("confirmed", "classifier", classifier_label, False)  # rule 2, agrees
        return ("contested", "tiebreak", tiebreak.label, False)  # rule 2, wins
    return ("model_only", "classifier", classifier_label, False)  # N5 / rule 4


MATRIX = list(
    itertools.product(
        (None, *POLARITIES),  # deterministic label
        POLARITIES,  # classifier label
        (LOW, HIGH),  # classifier confidence
        (False, True),  # in the audit sample
        TIEBREAK_CASES,
    )
)


def possible(
    deterministic: Polarity | None, label: Polarity, conf: float, audited: bool, case: TiebreakCase
) -> bool:
    triggered = rules.tiebreak_trigger(label, conf, deterministic)
    if audited:
        return case != "none"  # an audited row always gets a call
    if not triggered:
        return case == "none"  # nothing sends it
    return True


@pytest.mark.parametrize(("deterministic", "label", "conf", "audited", "case"), MATRIX)
def test_policy_matrix(
    deterministic: Polarity | None, label: Polarity, conf: float, audited: bool, case: TiebreakCase
) -> None:
    m = mention("mx")
    classifier = obs(m.mention_id, label, conf)
    tiebreak = tiebreak_for(case, label, m.mention_id)
    if not possible(deterministic, label, conf, audited, case):
        with pytest.raises(ValueError):
            rules.corroborate(classifier, deterministic, tiebreak, audited=audited)
        return
    decision = rules.corroborate(classifier, deterministic, tiebreak, audited=audited)
    corroboration, decided_by, final, overflow = expected_outcome(
        deterministic, label, conf, tiebreak
    )
    assert (decision.corroboration, decision.decided_by, decision.label, decision.overflow) == (
        corroboration,
        decided_by,
        final,
        overflow,
    )
    if decided_by == "tiebreak":
        assert tiebreak is not None and tiebreak.confidence is not None
        assert decision.confidence == tiebreak.confidence
        assert decision.rationale == "Second reader disagrees."
    else:
        assert decision.confidence == conf and decision.rationale == "Says so."

    # Independent oracle: the CONTRACTS Label validators in models.py accept the row.
    kind: Literal["lexicon", "none"] = "none" if deterministic is None else "lexicon"
    row = rules.PolicyRow(m, classifier, DeterministicSignal(kind=kind, label=deterministic))
    built = rules.build_label(
        row,
        tiebreak,
        audited=audited,
        classifier_model=CLASSIFIER,
        tiebreak_model=TIEBREAK,
        classifier_cached=False,
        usage=USAGE,
    )
    assert isinstance(built, Label)
    assert (built.corroboration, built.decided_by, built.label, built.signals.overflow) == (
        corroboration,
        decided_by,
        final,
        overflow,
    )
    assert (
        built.about_brand is True and built.status == "ok" and built.prompt_rev == config.PROMPT_REV
    )
    assert built.signals.classifier.model_dump() == {
        "model": CLASSIFIER,
        "label": label,
        "confidence": conf,
        "status": "ok",
    }
    if tiebreak is None:
        assert built.signals.tiebreak is None
    elif tiebreak.status == "ok":
        assert built.signals.tiebreak is not None
        assert built.signals.tiebreak.model == TIEBREAK and built.signals.tiebreak.status == "ok"
        assert built.signals.tiebreak.label == tiebreak.label
    else:
        assert built.signals.tiebreak is not None
        assert built.signals.tiebreak.status == tiebreak.status
        assert built.signals.tiebreak.confidence == rules.FAILED_TIEBREAK_CONFIDENCE
    assert built.signals.deterministic.label == deterministic


def test_matrix_covers_every_corroboration_and_both_deciders() -> None:
    seen: set[tuple[Any, ...]] = set()
    for deterministic, label, conf, audited, case in MATRIX:
        if not possible(deterministic, label, conf, audited, case):
            continue
        seen.add(
            expected_outcome(deterministic, label, conf, tiebreak_for(case, label, "x" * 24))[:2]
        )
    assert seen == {
        ("confirmed", "classifier"),
        ("contested", "tiebreak"),
        ("model_only", "classifier"),
    }


# --------------------------------------------------------------------------- named cases from the frozen text


class TestNamedCases:
    def test_rule_1_audit_tiebreak_never_overrides_confirmed(self) -> None:
        m = mention("n1")
        decision = rules.corroborate(
            obs(m.mention_id, "positive", HIGH),
            "positive",
            obs(m.mention_id, "negative", 0.99),
            audited=True,
        )
        assert (decision.corroboration, decision.decided_by, decision.label) == (
            "confirmed",
            "classifier",
            "positive",
        )

    def test_rule_4_audit_only_tiebreak_never_adopted(self) -> None:
        m = mention("n4")
        for tb_label in ("positive", "negative"):
            decision = rules.corroborate(
                obs(m.mention_id, "positive", HIGH), None, obs(m.mention_id, tb_label), audited=True
            )
            assert (decision.corroboration, decision.decided_by, decision.label) == (
                "model_only",
                "classifier",
                "positive",
            )

    def test_rule_3_overflow_keeps_classifier_label(self) -> None:
        m = mention("n3")
        decision = rules.corroborate(
            obs(m.mention_id, "negative", HIGH), "positive", None, audited=False
        )
        assert (
            decision.overflow
            and decision.corroboration == "model_only"
            and decision.label == "negative"
        )

    def test_corroborate_rejects_non_policy_rows(self) -> None:
        m = mention("np")
        with pytest.raises(ValueError):
            rules.corroborate(obs(m.mention_id, "irrelevant"), None, None, audited=False)
        with pytest.raises(ValueError):
            rules.corroborate(obs(m.mention_id, status="error"), None, None, audited=False)

    def test_irrelevant_label_record(self, lexicon: Lexicon) -> None:
        m = mention("ir", "adorei")
        for observation in (
            obs(m.mention_id, "positive", about_brand=False),
            obs(m.mention_id, "irrelevant"),
        ):
            label = rules.irrelevant_label(
                m,
                observation,
                rules.deterministic_signal(m, lexicon),
                classifier_model=CLASSIFIER,
                classifier_cached=True,
                usage=Usage(tokens=0, cost_usd=0.0),
            )
            assert label.label == "irrelevant" and label.corroboration == "irrelevant"
            assert label.decided_by == "classifier" and label.signals.tiebreak is None
            assert label.status == "cached" and label.signals.classifier.status == "cached"
            assert label.about_brand is bool(observation.about_brand)

    def test_cached_status_only_without_tiebreak(self) -> None:
        m = mention("cs")
        row = rules.PolicyRow(
            m,
            obs(m.mention_id, "positive"),
            DeterministicSignal(kind="lexicon", label="positive"),
        )
        zero = Usage(tokens=0, cost_usd=0.0)
        cached = rules.build_label(
            row,
            None,
            audited=False,
            classifier_model=CLASSIFIER,
            tiebreak_model=TIEBREAK,
            classifier_cached=True,
            usage=zero,
        )
        assert cached.status == "cached" and cached.signals.classifier.status == "cached"
        live = rules.build_label(
            row,
            obs(m.mention_id, "negative"),
            audited=True,
            classifier_model=CLASSIFIER,
            tiebreak_model=TIEBREAK,
            classifier_cached=True,
            usage=USAGE,
        )
        assert live.status == "ok" and live.signals.classifier.status == "cached"
        assert live.usage == USAGE
