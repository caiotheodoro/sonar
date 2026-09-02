"""Build and verify the receipt card (CONTRACTS §Receipt) from the ledger.

``build_receipt`` takes what the pipeline already has (ledger rows, the
reconcile result, LLM usage, mention counts, audit counts, abstentions) and
produces the ``Receipt`` record; every number in it is derived here, never
copied from an estimate. ``verify_receipt`` re-derives the verdict and the
content digest of a stored receipt and reports the exit code ``sonar verify``
must use: ``0`` only on ``RECONCILED``.

Money rules (CONTRACTS §RunRecord, §Totals, D013 N6):

* ``monid_usd`` sums ``cost_usd`` over rows with ``cost_source="/v1/runs"``
  only. An ``unreconciled`` row contributes ``0.0`` and is listed under
  ``reconciliation.unreconciled_local_seqs``; a ``local`` row carries ``0.0``.
* a row is failed iff its status is a Monid failure state or starts with
  ``LOCAL_``; a succeeded ``run_id=null`` sync run is not failed.
* ``elevenlabs_usd`` is the reconciled cost of the ElevenLabs rows, a breakout
  of ``monid_usd``; ``total_usd = monid_usd + llm_usd``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, get_args

from pydantic import ValidationError

from sonar import __version__, config
from sonar.llm.base import Usage as LlmCallUsage
from sonar.models import (
    SCHEMA_REV,
    Abstention,
    Audit,
    Comparison,
    Incumbent,
    Label,
    LlmKind,
    Mention,
    MentionCounts,
    Query,
    Receipt,
    Reconciliation,
    RunRecord,
    Source,
    Timestamps,
    Totals,
    Verdict,
    derive_verdict,
)
from sonar.monid.ledger import ReconcileResult, is_failed
from sonar.report.incumbent import BRAND24_TEAM
from sonar.report.incumbent import Incumbent as IncumbentConstant

LLM_KINDS: Final[tuple[LlmKind, ...]] = get_args(LlmKind)

X_NOT_CHECKED: Final[str] = "X/Twitter: no Monid endpoint"
"""Always present in ``what_could_not_be_checked`` (CONTRACTS §Receipt example)."""

VERIFY_OK: Final[int] = 0
VERIFY_NOT_RECONCILED: Final[int] = 1
VERIFY_INVALID: Final[int] = 2
"""``sonar verify`` exit codes: ``0`` only on ``RECONCILED``; ``1`` for ``PARTIAL`` or
``REPLAY``; ``2`` when the file is unreadable, fails validation, or its stored verdict
or ``content_digest`` disagree with what the receipt re-derives (design §Error matrix:
bad input exits 2)."""

VerifyStatus = Literal["ok", "not_reconciled", "invalid"]


# --------------------------------------------------------------------------- LLM usage


@dataclass
class LlmUsageTotals:
    """Running totals of every OpenAI call in a session, by ``LlmKind``.

    ``record`` takes the seam's ``Usage`` (one call). ``add`` takes a token and cost
    pair for calls already summed elsewhere, such as ``Label.usage`` for a mention whose
    classifier call was made in a batch: pass ``calls=0`` so the batch is not counted
    twice. Cached labels carry ``{0, 0.0}`` and are not calls (CONTRACTS §Totals).
    """

    usd: float = 0.0
    tokens: int = 0
    calls: dict[LlmKind, int] = field(default_factory=lambda: dict.fromkeys(LLM_KINDS, 0))

    def record(self, kind: LlmKind, usage: LlmCallUsage) -> None:
        self.add(kind, tokens=usage.tokens, cost_usd=usage.cost_usd, calls=1)

    def add(self, kind: LlmKind, *, tokens: int, cost_usd: float, calls: int = 1) -> None:
        if kind not in self.calls:
            raise ValueError(f"unknown LlmKind {kind!r}; expected one of {LLM_KINDS}")
        if tokens < 0 or cost_usd < 0.0 or calls < 0:
            raise ValueError("tokens, cost_usd and calls must be non-negative")
        self.usd += cost_usd
        self.tokens += tokens
        self.calls[kind] += calls

    def merge(self, other: LlmUsageTotals) -> None:
        for kind, count in other.calls.items():
            self.calls[kind] = self.calls.get(kind, 0) + count
        self.usd += other.usd
        self.tokens += other.tokens

    @classmethod
    def from_labels(
        cls, labels: Iterable[Label], *, batch_calls: int, tiebreak_calls: int
    ) -> LlmUsageTotals:
        """Sum ``Label.usage`` (classifier plus tiebreak cost per mention) with the call
        counts the labeler made: classifier batches and tiebreak calls are counted by the
        caller, not per label, because one batch call labels many mentions."""
        totals = cls()
        for label in labels:
            totals.add(
                "classify", tokens=label.usage.tokens, cost_usd=label.usage.cost_usd, calls=0
            )
        totals.calls["classify"] += batch_calls
        totals.calls["tiebreak"] += tiebreak_calls
        return totals


# --------------------------------------------------------------------------- inputs


def _reconciliation(
    rec: ReconcileResult | Reconciliation, runs: Sequence[RunRecord]
) -> Reconciliation:
    unreconciled = sorted(r.local_seq for r in runs if r.cost_source == "unreconciled")
    return Reconciliation(
        fetched_at=rec.fetched_at,
        n_listed_in_window=rec.n_listed_in_window,
        unmatched_remote_run_ids=list(rec.unmatched_remote_run_ids),
        unreconciled_local_seqs=unreconciled,
    )


def _incumbent(constant: IncumbentConstant) -> Incumbent:
    return Incumbent.model_validate(constant.to_record())


def resolve_sonar_rev(repo_root: Path | None = None) -> str:
    """``{package version}+{short git sha}`` read from ``.git`` without a subprocess.

    Falls back to ``+nogit`` when no repository is found, so a receipt built from an
    installed wheel still carries the package version.
    """
    root = repo_root if repo_root is not None else Path(__file__).resolve().parents[3]
    git_dir = root / ".git"
    sha = _git_head_sha(git_dir)
    return f"{__version__}+{sha[:7] if sha else 'nogit'}"


def _git_head_sha(git_dir: Path) -> str | None:
    head = git_dir / "HEAD"
    if git_dir.is_file():
        # Worktree: ``.git`` is a file pointing at the real git dir.
        pointer = git_dir.read_text(encoding="utf-8").strip()
        if pointer.startswith("gitdir:"):
            git_dir = (git_dir.parent / pointer.split(":", 1)[1].strip()).resolve()
            head = git_dir / "HEAD"
    if not head.is_file():
        return None
    content = head.read_text(encoding="utf-8").strip()
    if not content.startswith("ref:"):
        return content or None
    ref = content.split(":", 1)[1].strip()
    ref_file = git_dir / ref
    if ref_file.is_file():
        return ref_file.read_text(encoding="utf-8").strip() or None
    # Worktrees keep HEAD in their own dir but refs in the common dir.
    common = git_dir / "commondir"
    if common.is_file():
        common_dir = (git_dir / common.read_text(encoding="utf-8").strip()).resolve()
        ref_file = common_dir / ref
        if ref_file.is_file():
            return ref_file.read_text(encoding="utf-8").strip() or None
        git_dir = common_dir
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    return None


# --------------------------------------------------------------------------- totals


def elevenlabs_usd(runs: Iterable[RunRecord]) -> float:
    """Reconciled cost of the ElevenLabs rows: a breakout of ``monid_usd``."""
    return sum(
        r.cost_usd or 0.0
        for r in runs
        if r.provider == config.ELEVENLABS_PROVIDER and r.cost_source == "/v1/runs"
    )


def build_totals(runs: Sequence[RunRecord], llm: LlmUsageTotals) -> Totals:
    """CONTRACTS §Totals from the ledger rows and the LLM usage totals."""
    monid_usd = sum(r.cost_usd or 0.0 for r in runs if r.cost_source == "/v1/runs")
    return Totals(
        monid_usd=monid_usd,
        monid_runs=len(runs),
        monid_runs_billed=sum(1 for r in runs if r.cost_usd is not None and r.cost_usd > 0),
        monid_runs_zero_results=sum(1 for r in runs if r.n_results == 0),
        monid_runs_failed=sum(1 for r in runs if is_failed(r)),
        llm_usd=llm.usd,
        llm_calls={kind: llm.calls.get(kind, 0) for kind in LLM_KINDS},
        llm_tokens=llm.tokens,
        elevenlabs_usd=elevenlabs_usd(runs),
        total_usd=monid_usd + llm.usd,
    )


def build_comparison(totals: Totals, incumbent: Incumbent, mentions_this_brief: int) -> Comparison:
    """CONTRACTS §Comparison: monthly equivalent at the assumed brief cadence, and the ratio."""
    equiv = totals.total_usd * config.BRIEFS_PER_MONTH_ASSUMED
    ratio = incumbent.price_usd_month / equiv if equiv > 0.0 else None
    return Comparison(
        sonar_usd_month_equiv=equiv,
        ratio=ratio,
        mentions_this_brief=mentions_this_brief,
    )


# --------------------------------------------------------------------------- mentions block


def count_mentions(
    *,
    fetched: int,
    kept: Sequence[Mention],
    labels: Mapping[tuple[str, str], Label],
    dedup_dropped: Mapping[str, int],
) -> MentionCounts:
    """CONTRACTS §MentionCounts with every one of the eight exclusion keys present.

    ``kept`` is the rows after §Dedup precedence (``deduped`` counts them);
    ``labels`` is keyed by ``(mention_id, brand)``; ``dedup_dropped`` carries the
    ``dedup_*`` counts from ``text.dedup``. ``labelled`` counts rows whose Label has
    status ``ok`` or ``cached``; ``refused``, ``unparseable`` and ``error`` rows are
    excluded with that reason; a labelled row is excluded as ``not_about_brand`` when
    ``about_brand`` is false and as ``irrelevant_label`` when the label is ``irrelevant``.
    """
    reasons: dict[str, int] = {
        "not_about_brand": 0,
        "irrelevant_label": 0,
        "refused": 0,
        "unparseable": 0,
        "error": 0,
        "dedup_native_id": 0,
        "dedup_url": 0,
        "dedup_text": 0,
    }
    for key, count in dedup_dropped.items():
        if key not in reasons:
            raise ValueError(f"dedup_dropped key {key!r} is not an excluded_with_reason key")
        reasons[key] += count
    by_source: dict[Source, int] = {}
    by_brand: dict[str, int] = {}
    labelled = 0
    for row in kept:
        by_source[row.source] = by_source.get(row.source, 0) + 1
        by_brand[row.brand] = by_brand.get(row.brand, 0) + 1
        label = labels.get((row.mention_id, row.brand))
        if label is None:
            continue
        if label.status in ("refused", "unparseable", "error"):
            reasons[label.status] += 1
            continue
        labelled += 1
        if not label.about_brand:
            reasons["not_about_brand"] += 1
        elif label.label == "irrelevant":
            reasons["irrelevant_label"] += 1
    return MentionCounts(
        fetched=fetched,
        deduped=len(kept),
        labelled=labelled,
        excluded_with_reason=reasons,
        by_source=by_source,
        by_brand=by_brand,
    )


def build_audit(
    rows: Iterable[tuple[str, str, Label]], *, audit_sample: Iterable[tuple[str, str]]
) -> Audit:
    """CONTRACTS §Receipt.audit from the joined ``(mention_id, brand, label)`` rows.

    ``audit_sample`` lists the ``(mention_id, brand)`` rows the labeler drew as the fixed
    10 % sample; a row is in ``n_sample`` when its tiebreak call returned ``ok`` and in
    ``n_agree`` when the tiebreak label equals the classifier label. ``tiebreak_calls``
    counts every non-null tiebreak signal; ``tiebreak_overflow`` counts rows with
    ``signals.overflow=true``.
    """
    sample = set(audit_sample)
    n_sample = n_agree = tiebreak_calls = overflow = 0
    for mention_id, brand, label in rows:
        tiebreak = label.signals.tiebreak
        if label.signals.overflow:
            overflow += 1
        if tiebreak is None:
            continue
        tiebreak_calls += 1
        if (mention_id, brand) in sample and tiebreak.status == "ok":
            n_sample += 1
            if tiebreak.label == label.signals.classifier.label:
                n_agree += 1
    return Audit(
        n_sample=n_sample,
        n_agree=n_agree,
        agreement=(n_agree / n_sample) if n_sample else None,
        tiebreak_calls=tiebreak_calls,
        tiebreak_overflow=overflow,
    )


# --------------------------------------------------------------------------- receipt


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def build_receipt(
    *,
    session_id: str,
    query: Query,
    runs: Sequence[RunRecord],
    reconciliation: ReconcileResult | Reconciliation,
    llm: LlmUsageTotals,
    mentions: MentionCounts,
    audit: Audit,
    abstentions: Sequence[Abstention],
    what_could_not_be_checked: Sequence[str],
    started_at: datetime,
    finished_at: datetime,
    replay: bool = False,
    sonar_rev: str | None = None,
    incumbent: IncumbentConstant = BRAND24_TEAM,
) -> Receipt:
    """The card. Every total is derived from ``runs`` and ``llm`` here.

    ``runs`` are sorted by ``local_seq`` and all of them are kept, including
    ``run_id=null`` rows and ``n_results=0`` rows. The verdict follows
    :func:`sonar.models.derive_verdict`; ``content_digest`` is filled last.
    """
    ordered = sorted(runs, key=lambda r: r.local_seq)
    rec = _reconciliation(reconciliation, ordered)
    totals = build_totals(ordered, llm)
    incumbent_record = _incumbent(incumbent)
    verdict: Verdict = derive_verdict(replay, ordered, rec)
    receipt = Receipt(
        schema_rev=SCHEMA_REV,
        sonar_rev=sonar_rev if sonar_rev is not None else resolve_sonar_rev(),
        session_id=session_id,
        timestamps=Timestamps(
            started_at=started_at, finished_at=finished_at, reconciled_at=rec.fetched_at
        ),
        replay=replay,
        verdict=verdict,
        query=query,
        runs=ordered,
        totals=totals,
        reconciliation=rec,
        incumbent=incumbent_record,
        comparison=build_comparison(totals, incumbent_record, mentions.deduped),
        mentions=mentions,
        audit=audit,
        abstentions=list(abstentions),
        what_could_not_be_checked=_dedupe_keep_order([X_NOT_CHECKED, *what_could_not_be_checked]),
        content_digest="",
    )
    return receipt.with_content_digest()


def receipt_json(receipt: Receipt) -> str:
    """The on-disk form of ``receipt.json``: wire names, indented, UTF-8, trailing newline."""
    return json.dumps(receipt.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_receipt(receipt: Receipt, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(receipt_json(receipt), encoding="utf-8")
    return path


def load_receipt(path: Path) -> Receipt:
    return Receipt.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- verify


@dataclass(frozen=True)
class VerifyResult:
    """What ``sonar verify`` found; ``exit_code`` is the process exit status."""

    status: VerifyStatus
    exit_code: int
    stored_verdict: Verdict | None
    derived_verdict: Verdict | None
    digest_matches: bool
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.exit_code == VERIFY_OK


def verify_receipt(receipt: Receipt) -> VerifyResult:
    """Re-derive the verdict and ``content_digest``; ``ok`` only on ``RECONCILED``.

    A receipt whose stored verdict or digest disagrees with what its own rows imply is
    ``invalid`` (exit 2) even when the re-derived verdict would be ``RECONCILED``: the
    card was edited after it was written.
    """
    problems: list[str] = []
    derived = receipt.derived_verdict
    digest_ok = receipt.content_digest == receipt.compute_content_digest()
    if not digest_ok:
        problems.append("content_digest does not match the receipt body")
    if receipt.verdict != derived:
        problems.append(f"stored verdict {receipt.verdict} but rows derive {derived}")
    if problems:
        return VerifyResult(
            "invalid", VERIFY_INVALID, receipt.verdict, derived, digest_ok, tuple(problems)
        )
    if derived != "RECONCILED":
        if derived == "REPLAY":
            problems.append("replay receipt: rendered from stored artifacts, not a live run")
        if receipt.reconciliation.unreconciled_local_seqs:
            seqs = ", ".join(str(s) for s in receipt.reconciliation.unreconciled_local_seqs)
            problems.append(f"unreconciled local_seq: {seqs}")
        if receipt.reconciliation.unmatched_remote_run_ids:
            ids = ", ".join(receipt.reconciliation.unmatched_remote_run_ids)
            problems.append(f"remote runs with no ledger row: {ids}")
        if receipt.reconciliation.fetched_at is None and not receipt.replay:
            problems.append("GET /v1/runs was never fetched; run `sonar reconcile --session`")
        return VerifyResult(
            "not_reconciled", VERIFY_NOT_RECONCILED, receipt.verdict, derived, True, tuple(problems)
        )
    return VerifyResult("ok", VERIFY_OK, receipt.verdict, derived, True, ())


def verify_receipt_file(path: Path) -> VerifyResult:
    """``sonar verify <path>``: read, validate, re-derive; unreadable input is ``invalid``."""
    try:
        receipt = load_receipt(path)
    except (OSError, ValueError, ValidationError) as exc:
        return VerifyResult("invalid", VERIFY_INVALID, None, None, False, (f"{path}: {exc}",))
    return verify_receipt(receipt)


__all__ = [
    "LLM_KINDS",
    "VERIFY_INVALID",
    "VERIFY_NOT_RECONCILED",
    "VERIFY_OK",
    "X_NOT_CHECKED",
    "LlmUsageTotals",
    "VerifyResult",
    "VerifyStatus",
    "build_audit",
    "build_comparison",
    "build_receipt",
    "build_totals",
    "count_mentions",
    "elevenlabs_usd",
    "load_receipt",
    "receipt_json",
    "resolve_sonar_rev",
    "verify_receipt",
    "verify_receipt_file",
    "write_receipt",
]
