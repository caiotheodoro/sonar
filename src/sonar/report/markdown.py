"""Markdown rendering of the receipt card and the digest.

This is the only layer that formats money: CONTRACTS keeps ``float`` USD at
upstream precision in every record, and the tables here print it with
``USD_DECIMALS`` places. The receipt table prints every ledger row, including
``run_id=null`` rows, ``n_results=0`` rows and ``$0`` rows: an empty return
that was billed is the point of the card (H4), and a row that cost nothing is
still a call that was made.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from sonar.models import (
    CI95,
    Abstention,
    BySourceEntry,
    Digest,
    Receipt,
    RunRecord,
    SentimentEntry,
    SovEntry,
    Totals,
)

USD_DECIMALS: Final[int] = 4
USD_QUANTUM: Final[Decimal] = Decimal(1).scaleb(-USD_DECIMALS)
SHARE_DECIMALS: Final[int] = 3
REPLAY_BANNER: Final[str] = (
    "> **REPLAY** — rendered from stored artifacts with `sonar render --from`, "
    "not a live run. This receipt never passes `sonar verify`."
)
PARTIAL_BANNER: Final[str] = (
    "> **PARTIAL** — at least one run is not reconciled against `GET /v1/runs` "
    "or a remote run has no ledger row; unreconciled rows contribute $0. "
    "Run `sonar reconcile --session <id>`."
)
RECONCILED_BANNER: Final[str] = (
    "> **RECONCILED** — every run with an id is priced from `GET /v1/runs` "
    "and no remote run is unmatched."
)
UNRECONCILED_CELL: Final[str] = "unreconciled"
NULL_CELL: Final[str] = "—"


# --------------------------------------------------------------------------- cells


def usd(value: float | None) -> str:
    """``$0.0000`` for zero, ``unreconciled`` for a cost the listing has not priced.

    Rounds the decimal the ledger carries (``repr`` of the float), half up, not the
    binary double: ``0.03375`` prints ``$0.0338`` and ``0.31405`` prints ``$0.3141``,
    so the printed ``billed`` cells sum to the printed ``Monid billed`` line.
    """
    if value is None:
        return UNRECONCILED_CELL
    amount = Decimal(repr(value)).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)
    return f"${amount:f}"


def ratio_cell(value: float | None) -> str:
    return NULL_CELL if value is None else f"{value:,.1f}×"


def share_cell(value: float | None) -> str:
    return NULL_CELL if value is None else f"{value:.{SHARE_DECIMALS}f}"


def ci_cell(ci: CI95 | None) -> str:
    if ci is None:
        return NULL_CELL
    lo, hi = ci
    return f"[{lo:.{SHARE_DECIMALS}f}, {hi:.{SHARE_DECIMALS}f}]"


def int_cell(value: int | None) -> str:
    return NULL_CELL if value is None else str(value)


def text_cell(value: str | None) -> str:
    if value is None:
        return NULL_CELL
    return value.replace("|", "\\|").replace("\n", " ")


def stamp(value: datetime | date | None) -> str:
    if value is None:
        return NULL_CELL
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.isoformat()


def table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def verdict_banner(receipt: Receipt) -> str:
    if receipt.verdict == "REPLAY":
        return REPLAY_BANNER
    if receipt.verdict == "PARTIAL":
        return PARTIAL_BANNER
    return RECONCILED_BANNER


# --------------------------------------------------------------------------- receipt


def runs_table(runs: Sequence[RunRecord]) -> str:
    """Every ledger row in ``local_seq`` order; zero results and zero cost are printed."""
    rows = [
        (
            str(r.local_seq),
            text_cell(r.run_id),
            text_cell(f"{r.provider} {r.endpoint}"),
            text_cell(r.brand),
            text_cell(r.source),
            text_cell(r.status),
            int_cell(r.n_results),
            usd(r.estimate_usd),
            usd(r.cost_usd),
            r.cost_source,
        )
        for r in runs
    ]
    return table(
        (
            "seq",
            "run id",
            "endpoint",
            "brand",
            "source",
            "status",
            "results",
            "estimate",
            "billed",
            "cost source",
        ),
        rows,
    )


def totals_table(totals: Totals) -> str:
    calls = ", ".join(f"{kind} {count}" for kind, count in totals.llm_calls.items() if count)
    rows = [
        ("Monid billed", usd(totals.monid_usd)),
        ("Monid runs", str(totals.monid_runs)),
        ("Monid runs billed", str(totals.monid_runs_billed)),
        ("Monid runs with zero results", str(totals.monid_runs_zero_results)),
        ("Monid runs failed", str(totals.monid_runs_failed)),
        ("ElevenLabs (breakout of Monid)", usd(totals.elevenlabs_usd)),
        ("OpenAI", usd(totals.llm_usd)),
        ("OpenAI calls", calls or "0"),
        ("OpenAI tokens", str(totals.llm_tokens)),
        ("**Total**", f"**{usd(totals.total_usd)}**"),
    ]
    return table(("Line", "Value"), rows)


def comparison_table(receipt: Receipt) -> str:
    inc, cmp = receipt.incumbent, receipt.comparison
    rows = [
        (
            "Price",
            f"${inc.price_usd_month} per month",
            f"{usd(receipt.totals.total_usd)} this brief",
        ),
        (
            "Monthly equivalent",
            f"${inc.price_usd_month}",
            f"{usd(cmp.sonar_usd_month_equiv)} at {cmp.briefs_per_month_assumed} briefs",
        ),
        ("Mentions", f"{inc.mentions_quota:,} quota", f"{cmp.mentions_this_brief} this brief"),
        ("Ratio", "1×", ratio_cell(cmp.ratio)),
        ("Price checked", stamp(inc.checked_at), stamp(receipt.timestamps.finished_at)),
    ]
    return table(("", inc.name, "sonar"), rows)


def abstentions_table(rows: Sequence[Abstention]) -> str:
    if not rows:
        return "None."
    return table(
        ("scope", "brand", "source", "reason", "detail"),
        [
            (a.scope, text_cell(a.brand), text_cell(a.source), a.reason, text_cell(a.detail))
            for a in rows
        ],
    )


def bullet_list(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "None."


def render_receipt(receipt: Receipt) -> str:
    """The receipt card as Markdown."""
    q = receipt.query
    rec = receipt.reconciliation
    counts = receipt.mentions
    audit = receipt.audit
    excluded = ", ".join(f"{k} {v}" for k, v in sorted(counts.excluded_with_reason.items()))
    by_source = ", ".join(f"{k} {v}" for k, v in counts.by_source.items()) or "none"
    by_brand = ", ".join(f"{k} {v}" for k, v in counts.by_brand.items()) or "none"
    competitors = ", ".join(q.competitors) if q.competitors else "none"
    sections = [
        f"# sonar receipt — {q.brand}",
        "",
        verdict_banner(receipt),
        "",
        table(
            ("Field", "Value"),
            [
                ("Session", receipt.session_id),
                ("Verdict", f"**{receipt.verdict}**"),
                ("Profile", q.profile),
                ("Competitors", competitors),
                ("Sources", ", ".join(q.sources)),
                ("Started", stamp(receipt.timestamps.started_at)),
                ("Finished", stamp(receipt.timestamps.finished_at)),
                ("Reconciled", stamp(receipt.timestamps.reconciled_at)),
                ("schema_rev", receipt.schema_rev),
                ("sonar_rev", receipt.sonar_rev),
            ],
        ),
        "",
        "## Price side by side",
        "",
        comparison_table(receipt),
        "",
        "## Totals",
        "",
        totals_table(receipt.totals),
        "",
        "## Runs",
        "",
        (
            "Every Monid call of the session, including calls that returned no id, "
            "runs that returned zero results and runs that cost nothing."
        ),
        "",
        runs_table(receipt.runs),
        "",
        "## Reconciliation",
        "",
        table(
            ("Field", "Value"),
            [
                ("Fetched `GET /v1/runs`", stamp(rec.fetched_at)),
                ("Listed in window", str(rec.n_listed_in_window)),
                (
                    "Unmatched remote run ids",
                    ", ".join(rec.unmatched_remote_run_ids) or "none",
                ),
                (
                    "Unreconciled local_seq",
                    ", ".join(str(s) for s in rec.unreconciled_local_seqs) or "none",
                ),
            ],
        ),
        "",
        "## Mentions",
        "",
        table(
            ("Field", "Value"),
            [
                ("Fetched", str(counts.fetched)),
                ("After dedup (rows, one per brand)", str(counts.deduped)),
                ("Labelled", str(counts.labelled)),
                ("Excluded", excluded),
                ("By source", by_source),
                ("By brand", by_brand),
            ],
        ),
        "",
        "## Audit (classifier vs tiebreak, fixed 10 % sample)",
        "",
        table(
            ("Field", "Value"),
            [
                ("Sample size", str(audit.n_sample)),
                ("Agree", str(audit.n_agree)),
                ("Agreement", share_cell(audit.agreement)),
                ("Tiebreak calls", str(audit.tiebreak_calls)),
                ("Tiebreak overflow (40 % cap)", str(audit.tiebreak_overflow)),
            ],
        ),
        "",
        "## Abstentions",
        "",
        abstentions_table(receipt.abstentions),
        "",
        "## What could not be checked",
        "",
        bullet_list(receipt.what_could_not_be_checked),
        "",
        f"content_digest: `{receipt.content_digest}`",
        "",
    ]
    return "\n".join(sections)


# --------------------------------------------------------------------------- digest


def sov_table(rows: Sequence[SovEntry]) -> str:
    return table(
        ("brand", "n", "clusters", "share", "95 % CI", "WoW Δ", "WoW CI", "verdict", "basis"),
        [
            (
                s.brand,
                str(s.n),
                str(s.n_clusters),
                share_cell(s.share),
                ci_cell(s.ci95),
                share_cell(s.wow.delta),
                ci_cell(s.wow.ci95),
                s.wow.verdict,
                ", ".join(s.basis_sources) or NULL_CELL,
            )
            for s in rows
        ],
    )


def sentiment_table(rows: Sequence[SentimentEntry]) -> str:
    return table(
        (
            "brand",
            "n",
            "confirmed",
            "pos",
            "neg",
            "neu",
            "net",
            "95 % CI",
            "iid CI",
            "design effect",
            "WoW Δ",
            "WoW CI",
            "confirmed-only CI",
            "verdict",
        ),
        [
            (
                s.brand,
                str(s.n),
                str(s.n_confirmed),
                str(s.pos),
                str(s.neg),
                str(s.neu),
                share_cell(s.net),
                ci_cell(s.ci95),
                ci_cell(s.ci95_iid),
                share_cell(s.design_effect),
                share_cell(s.wow.delta),
                ci_cell(s.wow.ci95),
                ci_cell(s.wow.ci95_confirmed_only),
                s.wow.verdict,
            )
            for s in rows
        ],
    )


def by_source_table(rows: Sequence[BySourceEntry]) -> str:
    return table(
        ("brand", "source", "n", "clusters", "net", "95 % CI", "design effect", "WoW scope"),
        [
            (
                r.brand,
                r.source,
                str(r.n),
                str(r.n_clusters),
                share_cell(r.net),
                ci_cell(r.ci95),
                share_cell(r.design_effect),
                "yes" if r.wow_scope else "no (no timestamps)",
            )
            for r in rows
        ],
    )


def render_digest(digest: Digest) -> str:
    """The digest as Markdown, cost quoted from the receipt."""
    w = digest.window
    competitors = ", ".join(digest.competitors) if digest.competitors else "none"
    topics = (
        table(
            ("topic", "brand", "name", "n", "clusters", "share", "net", "95 % CI"),
            [
                (
                    t.topic_id,
                    t.brand,
                    text_cell(t.name),
                    str(t.n),
                    str(t.n_clusters),
                    share_cell(t.share),
                    share_cell(t.net),
                    ci_cell(t.ci95),
                )
                for t in digest.topics
            ],
        )
        if digest.topics
        else "None."
    )
    events = (
        table(
            ("brand", "date", "n", "clusters", "median", "MAD", "threshold", "label", "exhibit"),
            [
                (
                    e.brand,
                    stamp(e.date),
                    str(e.n),
                    str(e.n_clusters),
                    f"{e.baseline_median:.1f}",
                    f"{e.baseline_mad:.1f}",
                    f"{e.threshold:.1f}",
                    text_cell(e.label),
                    text_cell(e.exhibit_url),
                )
                for e in digest.events
            ],
        )
        if digest.events
        else "None."
    )
    top = (
        table(
            ("brand", "source", "label", "lang", "engagement", "published", "quote", "url"),
            [
                (
                    t.brand,
                    t.source,
                    t.label,
                    t.lang,
                    str(t.engagement_score),
                    stamp(t.published_at),
                    text_cell(t.quote),
                    text_cell(t.url),
                )
                for t in digest.top_mentions
            ],
        )
        if digest.top_mentions
        else "None."
    )
    gaps = table(
        ("source", "reason", "note"),
        [(g.source, g.reason, text_cell(g.note)) for g in digest.coverage_gaps],
    )
    n = digest.narration
    narration = (
        f"{n.text}\n\n({n.chars} chars; numbers verified: {'yes' if n.numbers_verified else 'no'}"
        + (f"; mp3 `{n.mp3_path}`, ledger row {n.local_seq}" if n.mp3_path else "")
        + ")"
        if n.text is not None
        else "No narration for this run."
    )
    sections = [
        f"# sonar digest — {digest.brand}",
        "",
        (
            f"Competitors: {competitors}. Window: current {stamp(w.current.start)} to "
            f"{stamp(w.current.end)}, previous {stamp(w.previous.start)} to "
            f"{stamp(w.previous.end)}."
        ),
        "",
        (
            f"Cost verdict **{digest.cost.verdict}**, total {usd(digest.cost.totals.total_usd)} "
            f"(Monid {usd(digest.cost.totals.monid_usd)}, "
            f"OpenAI {usd(digest.cost.totals.llm_usd)})."
        ),
        "",
        "## Share of voice",
        "",
        "Share counts mention–brand pairs over the sources that returned for every brand.",
        "",
        sov_table(digest.share_of_voice),
        "",
        "## Sentiment",
        "",
        sentiment_table(digest.sentiment),
        "",
        "## By source",
        "",
        by_source_table(digest.by_source),
        "",
        "## Topics",
        "",
        topics,
        "",
        "## Events",
        "",
        events,
        "",
        "## Top mentions",
        "",
        top,
        "",
        "## Abstentions",
        "",
        abstentions_table(digest.abstentions),
        "",
        "## Coverage gaps",
        "",
        gaps,
        "",
        "## Narration",
        "",
        narration,
        "",
    ]
    return "\n".join(sections)


__all__ = [
    "NULL_CELL",
    "PARTIAL_BANNER",
    "RECONCILED_BANNER",
    "REPLAY_BANNER",
    "UNRECONCILED_CELL",
    "USD_DECIMALS",
    "USD_QUANTUM",
    "abstentions_table",
    "comparison_table",
    "render_digest",
    "render_receipt",
    "runs_table",
    "table",
    "totals_table",
    "usd",
    "verdict_banner",
]
