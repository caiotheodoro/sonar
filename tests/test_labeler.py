"""Batched labeler: batches of 20, exact tiebreak volume (cap and audit), cache hits.

The fake counts calls per model; the tiebreak model's classify count is the
number of tiebreak calls, so the 40 % cap and the 10 % audit sample are
asserted exactly, not approximately.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypeVar

import pytest
from pydantic import BaseModel

from sonar import config
from sonar.llm.base import (
    ClassifyBatch,
    ClassifyResult,
    EmbedResult,
    JsonResult,
    MentionText,
    Rate,
    Usage,
)
from sonar.llm.fake import FakeBackend, LabelFixtureEntry
from sonar.models import Label, Mention, Polarity, SentimentLabel, mention_id_for
from sonar.sentiment import rules
from sonar.sentiment.cache import CACHE_PATH, LabelCache
from sonar.sentiment.labeler import (
    BATCH_SIZE,
    Labeler,
    LabelRun,
    apportion,
    batches,
    label_mentions,
)
from sonar.sentiment.lexicon import load_lexicon
from sonar.sentiment.prompt import (
    CLASSIFIER_SYSTEM,
    PROMPT_REV,
    TIEBREAK_SYSTEM,
    prompt_digest,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
MODELS = config.LlmModels(
    classifier_model=config.CLASSIFIER_MODEL_DEFAULT,
    tiebreak_model=config.TIEBREAK_MODEL_DEFAULT,
    embedding_model=config.EMBEDDING_MODEL_DEFAULT,
)
HIGH = config.TIEBREAK_CONFIDENCE_THRESHOLD + 0.3
LOW = config.TIEBREAK_CONFIDENCE_THRESHOLD - 0.3

POSITIVE_TEXT = "Adorei o app do Nubank, atendimento excelente"
NEGATIVE_TEXT = "Não recomendo o Nubank, atendimento péssimo"
NEUTRAL_TEXT = "O Nubank publicou o relatório trimestral na terça"


# --------------------------------------------------------------------------- fakes


class RoutingFake:
    """Seam implementation that sends each model to its own ``FakeBackend``."""

    def __init__(self, classifier: FakeBackend, tiebreak: FakeBackend) -> None:
        self.classifier = classifier
        self.tiebreak = tiebreak

    @property
    def rates(self) -> Mapping[str, Rate]:
        return self.classifier.rates

    def _route(self, model: str) -> FakeBackend:
        if model == MODELS.classifier_model:
            return self.classifier
        if model == MODELS.tiebreak_model:
            return self.tiebreak
        raise AssertionError(f"unexpected model {model!r}")

    def classify(self, batch: ClassifyBatch, model: str) -> ClassifyResult:
        return self._route(model).classify(batch, model)

    def complete_json(
        self, system: str, user: str, schema: type[SchemaT], model: str
    ) -> JsonResult[SchemaT]:
        return self._route(model).complete_json(system, user, schema, model)

    def embed(self, texts: Sequence[str], model: str) -> EmbedResult:
        return self.classifier.embed(texts, model)

    @property
    def classify_calls(self) -> int:
        return self.classifier.calls[MODELS.classifier_model]

    @property
    def tiebreak_calls(self) -> int:
        return self.tiebreak.calls[MODELS.tiebreak_model]


def entry(
    label: SentimentLabel,
    confidence: float = HIGH,
    *,
    about_brand: bool = True,
    status: str = "ok",
) -> LabelFixtureEntry:
    if status != "ok":
        return LabelFixtureEntry.model_validate({"status": status, "rationale": "declined"})
    return LabelFixtureEntry(
        label=label, about_brand=about_brand, confidence=confidence, rationale="Because."
    )


def mention(
    key: str, text: str, brand: str = "Nubank", published_at: datetime | None = T0
) -> Mention:
    return Mention(
        mention_id=mention_id_for("reddit", key),
        brand=brand,
        source="reddit",
        run_id="run_01",
        native_id=key,
        url=None,
        author_hash=None,
        text=text,
        lang="pt",
        published_at=published_at,
        engagement={},
        rating=None,
        cluster_key="post-1",
        matched_terms=[brand.casefold()],
        raw_ref="1#0",
    )


class Scenario:
    """53 rows for one brand: 50 policy rows (20 confirmed, 20 triggered, 10 unsignalled) + 3 others."""

    def __init__(self) -> None:
        self.mentions: list[Mention] = []
        self.classifier: dict[str, LabelFixtureEntry] = {}
        self.tiebreak: dict[str, LabelFixtureEntry] = {}
        self.confirmed: set[str] = set()
        self.triggered: set[str] = set()
        self.unsignalled: set[str] = set()
        polarities: tuple[Polarity, ...] = ("positive", "negative")
        for i in range(20):  # classifier agrees with the lexicon
            text = POSITIVE_TEXT if i % 2 == 0 else NEGATIVE_TEXT
            m = mention(f"agree{i}", text, published_at=T0 + timedelta(minutes=i))
            self._add(m, entry(polarities[i % 2]), entry(polarities[(i + 1) % 2]))
            self.confirmed.add(m.mention_id)
        for i in range(20):  # classifier disagrees with the lexicon: trigger (a)
            text = POSITIVE_TEXT if i % 2 == 0 else NEGATIVE_TEXT
            m = mention(f"clash{i}", text, published_at=T0 + timedelta(hours=1, minutes=i))
            # tiebreak: agrees with the classifier on even rows, sides with the lexicon on odd rows
            classifier_label = polarities[(i + 1) % 2]
            tiebreak_label = classifier_label if i % 2 == 0 else polarities[i % 2]
            self._add(m, entry(classifier_label), entry(tiebreak_label))
            self.triggered.add(m.mention_id)
        for i in range(10):  # no lexicon hit, confident classifier: model_only, no trigger
            m = mention(f"plain{i}", NEUTRAL_TEXT, published_at=T0 + timedelta(hours=2, minutes=i))
            self._add(m, entry("neutral", HIGH), entry("positive"))
            self.unsignalled.add(m.mention_id)
        self.not_about = mention("homonym", "Nubank é uma cor bonita")
        self._add(self.not_about, entry("positive", about_brand=False), entry("positive"))
        self.irrelevant = mention("offtopic", NEUTRAL_TEXT)
        self._add(self.irrelevant, entry("irrelevant"), entry("positive"))
        self.refused = mention("refused", NEUTRAL_TEXT)
        self._add(self.refused, entry("neutral", status="refused"), entry("neutral"))

    def _add(self, m: Mention, classifier: LabelFixtureEntry, tiebreak: LabelFixtureEntry) -> None:
        self.mentions.append(m)
        self.classifier[m.mention_id] = classifier
        self.tiebreak[m.mention_id] = tiebreak

    @property
    def policy_ids(self) -> set[str]:
        return self.confirmed | self.triggered | self.unsignalled

    def backend(self) -> RoutingFake:
        return RoutingFake(FakeBackend(self.classifier), FakeBackend(self.tiebreak))


@pytest.fixture
def scenario() -> Scenario:
    return Scenario()


def labels_of(run: LabelRun, brand: str = "Nubank") -> dict[str, Label]:
    return {row.label.mention_id: row.label for row in run.labels if row.brand == brand}


# --------------------------------------------------------------------------- prompt


class TestPrompt:
    def test_prompt_rev_is_config_and_embedded(self) -> None:
        assert PROMPT_REV == config.PROMPT_REV
        assert PROMPT_REV in CLASSIFIER_SYSTEM and PROMPT_REV in TIEBREAK_SYSTEM
        assert str(config.RATIONALE_MAX_WORDS) in CLASSIFIER_SYSTEM

    def test_prompts_are_frozen_with_prompt_rev(self) -> None:
        # Editing a prompt without bumping config.PROMPT_REV would serve stale cached labels;
        # a digest change here means PROMPT_REV must move through a DECISIONS entry.
        assert (
            prompt_digest(CLASSIFIER_SYSTEM)
            == "a5548afe012ead989c46f3aafac59b9709b5799be9f688c6480914bcca8efb1b"
        )
        assert (
            prompt_digest(TIEBREAK_SYSTEM)
            == "169b2abe4527f3a800df7193cbea7e4e0f93fa7e325e931a1d5c8aa0130322b1"
        )
        assert (
            prompt_digest(CLASSIFIER_SYSTEM)
            == hashlib.sha256(CLASSIFIER_SYSTEM.encode()).hexdigest()
        )


# --------------------------------------------------------------------------- helpers


class TestHelpers:
    def test_batches_of_twenty(self) -> None:
        items = [MentionText(mention_id=f"{i:024x}", text="t") for i in range(53)]
        chunks = batches(items)
        assert BATCH_SIZE == 20
        assert [len(c) for c in chunks] == [20, 20, 13]
        assert [i for c in chunks for i in c] == items
        assert batches([]) == []
        with pytest.raises(ValueError):
            batches(items, 0)

    def test_apportion_sums_tokens_exactly(self) -> None:
        usage = Usage.price(
            MODELS.classifier_model,
            100,
            7,
            {MODELS.classifier_model: Rate(input_usd_per_mtok=1.0, output_usd_per_mtok=2.0)},
        )
        shares = apportion(usage, 4)
        assert sum(s.tokens for s in shares) == usage.tokens == 107
        assert [s.tokens for s in shares] == [27, 27, 27, 26]
        assert sum(s.cost_usd for s in shares) == pytest.approx(usage.cost_usd)
        with pytest.raises(ValueError):
            apportion(usage, 0)


# --------------------------------------------------------------------------- one brand, exact volumes


class TestVolumes:
    def test_classifier_batches_of_twenty(self, scenario: Scenario) -> None:
        backend = scenario.backend()
        label_mentions(scenario.mentions, backend, models=MODELS)
        sizes = [
            len(ids)
            for model, ids in backend.classifier.batches
            if model == MODELS.classifier_model
        ]
        assert sizes == [20, 20, 13]
        assert backend.classify_calls == 3
        assert all(len(ids) == 1 for model, ids in backend.tiebreak.batches)
        assert {model for model, _ in backend.tiebreak.batches} == {MODELS.tiebreak_model}

    def test_tiebreak_calls_equal_cap_and_audit_is_exact(self, scenario: Scenario) -> None:
        backend = scenario.backend()
        run = label_mentions(scenario.mentions, backend, models=MODELS)
        labels = labels_of(run)
        n = len(scenario.policy_ids)
        assert n == 50
        cap = rules.tiebreak_cap(n)
        audit = rules.audit_sample(scenario.policy_ids)
        assert cap == 20 and len(audit) == 5

        wanted = audit | scenario.triggered
        assert backend.tiebreak_calls == min(cap, len(wanted)) == 20
        assert run.audit.tiebreak_calls == 20
        assert run.audit.tiebreak_overflow == len(wanted) - cap == len(audit - scenario.triggered)
        assert run.spend["tiebreak"].calls == 20 and run.spend["classify"].calls == 3

        called = {mid for mid, lab in labels.items() if lab.signals.tiebreak is not None}
        assert len(called) == 20 and audit <= called
        overflowed = {mid for mid, lab in labels.items() if lab.signals.overflow}
        assert overflowed <= scenario.triggered - audit
        assert len(overflowed) == run.audit.tiebreak_overflow
        # overflow rows are the latest-published triggered rows outside the audit sample
        ordered = sorted(
            (mid for mid in scenario.triggered - audit),
            key=lambda mid: rules.published_order_key(
                next(m for m in scenario.mentions if m.mention_id == mid)
            ),
        )
        assert set(ordered[cap - len(audit) :]) == overflowed

        # audit block: every audit tiebreak returned ok; agreement counted against the classifier label
        assert run.audit.n_sample == 5
        agree = sum(
            1 for mid in audit if scenario.tiebreak[mid].label == scenario.classifier[mid].label
        )
        assert run.audit.n_agree == agree
        assert run.audit.agreement == pytest.approx(agree / 5)

        # Sample and cap denominators exclude the three non-policy rows
        assert scenario.not_about.mention_id not in audit
        assert labels[scenario.not_about.mention_id].corroboration == "irrelevant"
        assert labels[scenario.irrelevant.mention_id].corroboration == "irrelevant"
        assert scenario.refused.mention_id not in labels
        assert [(e.mention_id, e.reason) for e in run.excluded] == [
            (scenario.refused.mention_id, "refused")
        ]
        assert run.excluded_with_reason() == {
            "not_about_brand": 1,
            "irrelevant_label": 1,
            "refused": 1,
            "unparseable": 0,
            "error": 0,
        }

    def test_corroboration_follows_precedence(self, scenario: Scenario) -> None:
        run = label_mentions(scenario.mentions, scenario.backend(), models=MODELS)
        labels = labels_of(run)
        audit = rules.audit_sample(scenario.policy_ids)
        for mid in scenario.confirmed:
            lab = labels[mid]
            assert lab.corroboration == "confirmed" and lab.decided_by == "classifier"
            assert (lab.signals.tiebreak is not None) == (mid in audit)
        for mid in scenario.unsignalled:
            lab = labels[mid]
            assert lab.corroboration == "model_only" and lab.decided_by == "classifier"
            assert lab.signals.deterministic.kind == "none" and not lab.signals.overflow
            assert (lab.signals.tiebreak is not None) == (mid in audit)
        for mid in scenario.triggered:
            lab = labels[mid]
            if lab.signals.overflow:
                assert lab.corroboration == "model_only" and lab.signals.tiebreak is None
                assert lab.label == scenario.classifier[mid].label
                continue
            assert lab.signals.tiebreak is not None
            if scenario.tiebreak[mid].label == scenario.classifier[mid].label:
                assert lab.corroboration == "confirmed" and lab.decided_by == "classifier"
            else:
                assert lab.corroboration == "contested" and lab.decided_by == "tiebreak"
                assert lab.label == scenario.tiebreak[mid].label
                assert lab.confidence == scenario.tiebreak[mid].confidence
        assert any(lab.corroboration == "contested" for lab in labels.values())
        assert all(lab.prompt_rev == config.PROMPT_REV for lab in labels.values())
        assert all(lab.status == "ok" for lab in labels.values())

    def test_usage_sums_to_spend(self, scenario: Scenario) -> None:
        run = label_mentions(scenario.mentions, scenario.backend(), models=MODELS)
        tokens = sum(row.label.usage.tokens for row in run.labels)
        cost = sum(row.label.usage.cost_usd for row in run.labels)
        # the refused row's share of its batch is spent but has no Label
        spent_tokens = sum(s.tokens for s in run.spend.values())
        assert 0 < tokens < spent_tokens
        assert 0 < cost < run.llm_usd
        assert (
            run.spend["tiebreak"].cost_usd > run.spend["classify"].cost_usd
        )  # terra is dearer per row

    def test_failed_tiebreak_keeps_classifier_label(self, scenario: Scenario) -> None:
        for mid in scenario.triggered:
            scenario.tiebreak[mid] = entry("neutral", status="error")
        run = label_mentions(scenario.mentions, scenario.backend(), models=MODELS)
        labels = labels_of(run)
        called = [
            labels[mid] for mid in scenario.triggered if labels[mid].signals.tiebreak is not None
        ]
        assert called
        for lab in called:
            assert lab.corroboration == "model_only" and lab.decided_by == "classifier"
            assert lab.signals.tiebreak is not None and lab.signals.tiebreak.status == "error"
        audit = rules.audit_sample(scenario.policy_ids)
        assert run.audit.n_sample == len(audit - scenario.triggered)
        assert run.audit.tiebreak_calls == 20


# --------------------------------------------------------------------------- brands


class TestBrands:
    def test_mention_kept_for_two_brands_is_two_rows(
        self, scenario: Scenario, seen_batches: list[ClassifyBatch]
    ) -> None:
        second = [
            m.model_copy(update={"brand": "Inter", "matched_terms": ["inter"]})
            for m in scenario.mentions
        ]
        backend = scenario.backend()
        run = label_mentions(
            scenario.mentions + second,
            backend,
            models=MODELS,
            brand_hints={"Nubank": "Brazilian digital bank"},
        )
        assert len(labels_of(run, "Nubank")) == 52 and len(labels_of(run, "Inter")) == 52
        assert backend.classify_calls == 6 and backend.tiebreak_calls == 40
        assert run.audit.tiebreak_calls == 40 and run.audit.n_sample == 10
        hints = {batch.brand: batch.brand_hint for batch in seen_batches}
        assert hints == {"Nubank": "Brazilian digital bank", "Inter": None}

    def test_duplicate_rows_rejected(self, scenario: Scenario) -> None:
        with pytest.raises(ValueError):
            label_mentions(
                scenario.mentions + scenario.mentions[:1], scenario.backend(), models=MODELS
            )


@pytest.fixture
def seen_batches(monkeypatch: pytest.MonkeyPatch) -> list[ClassifyBatch]:
    """Every ``ClassifyBatch`` the fakes received, brand and hint included."""
    seen: list[ClassifyBatch] = []
    original = FakeBackend.classify

    def spy(self: FakeBackend, batch: ClassifyBatch, model: str) -> ClassifyResult:
        seen.append(batch)
        return original(self, batch, model)

    monkeypatch.setattr(FakeBackend, "classify", spy)
    return seen


# --------------------------------------------------------------------------- cache


class TestCache:
    def test_second_run_serves_classifier_from_cache(
        self, scenario: Scenario, tmp_path: Path
    ) -> None:
        path = tmp_path / CACHE_PATH
        first_backend = scenario.backend()
        first = Labeler(first_backend, models=MODELS, cache=LabelCache(path)).run(scenario.mentions)
        assert first_backend.classify_calls == 3 and first.cache_hits == 0
        assert path.exists()
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 52  # the refused observation is not cached
        assert {tuple(sorted(r)) for r in rows} == {
            ("brand", "mention_id", "model", "observation", "prompt_rev")
        }
        assert {r["prompt_rev"] for r in rows} == {PROMPT_REV}
        assert {r["model"] for r in rows} == {MODELS.classifier_model}

        second_backend = scenario.backend()
        cache = LabelCache(path)
        assert len(cache) == 52
        second = Labeler(second_backend, models=MODELS, cache=cache).run(scenario.mentions)
        assert second_backend.classify_calls == 1  # only the refused row is re-asked
        assert second.cache_hits == 52 and cache.hits == 52 and cache.misses == 1
        assert second_backend.tiebreak_calls == 20  # tiebreaks are never cached
        assert "classify" in second.spend and second.spend["classify"].calls == 1

        first_labels, second_labels = labels_of(first), labels_of(second)
        assert set(first_labels) == set(second_labels)
        for mid, lab in second_labels.items():
            assert lab.signals.classifier.status == "cached"
            if lab.signals.tiebreak is None:
                assert lab.status == "cached"
                assert lab.usage.model_dump() == {"tokens": 0, "cost_usd": 0.0}
            else:
                assert lab.status == "ok"
                assert lab.usage.tokens > 0
            assert lab.label == first_labels[mid].label
            assert lab.corroboration == first_labels[mid].corroboration
        assert second.audit == first.audit

    def test_cache_key_includes_prompt_rev_and_model(
        self, scenario: Scenario, tmp_path: Path
    ) -> None:
        path = tmp_path / "labels.jsonl"
        Labeler(scenario.backend(), models=MODELS, cache=LabelCache(path)).run(scenario.mentions)
        other_rev = scenario.backend()
        run = Labeler(
            other_rev, models=MODELS, cache=LabelCache(path), prompt_rev="classify-v0"
        ).run(scenario.mentions)
        assert other_rev.classify_calls == 3 and run.cache_hits == 0
        other_model = scenario.backend()
        models = config.LlmModels(
            classifier_model=MODELS.tiebreak_model,
            tiebreak_model=MODELS.tiebreak_model,
            embedding_model=MODELS.embedding_model,
        )
        run = Labeler(
            RoutingFake(other_model.tiebreak, other_model.tiebreak),
            models=models,
            cache=LabelCache(path),
        ).run(scenario.mentions)
        assert run.cache_hits == 0

    def test_cache_rejects_corrupt_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "labels.jsonl"
        path.write_text('{"mention_id": "x"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="labels.jsonl:1"):
            LabelCache(path)

    def test_default_path(self) -> None:
        assert CACHE_PATH == Path(".sonar/cache/labels.jsonl")
        assert LabelCache().path == CACHE_PATH


# --------------------------------------------------------------------------- lexicon in the loop


def test_lexicon_is_loaded_once() -> None:
    assert load_lexicon() is load_lexicon()
