"""Published-claims gate: every number and path the docs publish is sourced.

Each test here checks that something this repository says in prose is still
true of the artifact it claims to come from: a cited path opens, the incumbent
price is one number in every place it is printed, the frozen thresholds equal
the constants, every model id has a dated decision, and the demo receipt the
README points at verifies. ``make check-claims`` runs this file alone with
``-rs`` so the skipped gates print why they were skipped (demo artifacts land
in Wave 6, narration in Wave 7).

Ported from ``assay/tests/test_published_claims.py``; the gates that skip
until an artifact exists are listed in the module so a reader can see what is
deferred rather than discovering it from a green run.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from sonar import config
from sonar.report.incumbent import BRAND24_TEAM
from sonar.report.receipt import load_receipt, verify_receipt

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "sonar"
README = ROOT / "README.md"
DECISIONS = ROOT / "docs" / "DECISIONS.md"
PRE_REG = ROOT / "docs" / "PRE-REGISTRATION.md"
INCUMBENT_README = ROOT / "results" / "incumbent" / "README.md"
DEMO_RECEIPT = ROOT / "results" / "demo" / "receipt.json"
DEMO_STATS = ROOT / "results" / "demo" / "stats.json"
NARRATION = ROOT / "video" / "src" / "data" / "narration.json"

# Documents whose backticked paths are citations a judge is expected to open.
# ``docs/research/`` is the plan and the review transcripts: history, exempt.
DOCS_THAT_CITE_PATHS = (
    "README.md",
    "AGENTS.md",
    "llms.txt",
    *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "docs").glob("*.md")),
)

# Artifacts later waves produce. A citation under one of these is checked the
# moment the directory exists; until then the gate skips and says so.
DEFERRED_PREFIXES: dict[str, str] = {
    "results/demo/": "frozen demo run, W6.1",
    "results/demo-empty/": "zero-mention brand receipt, W6.1",
    "results/handcheck/": "blind hand check, W6.3",
    "results/rehearsal/": "rehearsal run, W8.2",
    "skill/": "Claude Code skill, W5.3",
    "video/": "video scaffold and narration, W7",
}

# Paths cited on purpose that belong to another repository.
EXTERNAL_CITATIONS: dict[str, str] = {
    "scripts/intervals.py": "assay's bootstrap script, ported per D010",
}

# A heading that retires its section: what follows is a record, not a claim.
HISTORICAL_HEADING = re.compile(
    r"^#{1,6}\s+(?:.*\b(?:historical|superseded|amendments?|prior)\b.*|\d{4}-\d{2}-\d{2}\b.*)$",
    flags=re.IGNORECASE,
)

_CITATION = re.compile(r"`([A-Za-z0-9_.][A-Za-z0-9_./-]*)(?::[0-9]+(?:-[0-9]+)?)?`")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _tracked() -> frozenset[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return frozenset(line for line in out.splitlines() if line)


def _is_tracked(path: str, tracked: frozenset[str]) -> bool:
    prefix = path.rstrip("/") + "/"
    return path in tracked or any(t.startswith(prefix) for t in tracked)


def _ignored_dir_prefixes() -> tuple[str, ...]:
    """Directory patterns from ``.gitignore``: runtime output, never a citation."""
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return tuple(line.strip() for line in lines if line.strip().endswith("/"))


def _endpoint_providers() -> frozenset[str]:
    """Monid provider ids; ``apify/<actor>`` is an endpoint, not a file."""
    providers = {plan.provider for plan in config.SOURCE_PLAN.values()}
    providers.add(config.ELEVENLABS_PROVIDER)
    return frozenset(providers)


def _resolve(cited: str) -> Path | None:
    """Repo path, ``src/sonar``-relative path, or module path without ``.py``."""
    for candidate in (ROOT / cited, PACKAGE / cited, PACKAGE / f"{cited}.py"):
        if candidate.exists():
            return candidate
    return None


def _live_lines(doc: Path) -> Iterator[str]:
    """Lines of ``doc`` outside sections retired by a historical heading."""
    retired = False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            retired = HISTORICAL_HEADING.match(line) is not None
        if not retired:
            yield line


def _citations() -> Iterator[tuple[str, str]]:
    ignored = _ignored_dir_prefixes()
    providers = _endpoint_providers()
    for doc in DOCS_THAT_CITE_PATHS:
        text = "\n".join(_live_lines(ROOT / doc))
        for cited in sorted(set(_CITATION.findall(text))):
            # A bare filename is a mention; only a path with a directory
            # component is a claim about this repository.
            if "/" not in cited:
                continue
            if cited.startswith(ignored) or cited.split("/", 1)[0] in providers:
                continue
            if cited in EXTERNAL_CITATIONS:
                continue
            yield doc, cited


def _deferred_reason(cited: str) -> str | None:
    for prefix, reason in DEFERRED_PREFIXES.items():
        if cited.startswith(prefix):
            return reason
    return None


# --------------------------------------------------------------------- paths


def test_every_cited_path_resolves_and_is_tracked() -> None:
    """A citation a judge cannot open is worse than no citation.

    The docs say "open the file"; one dead link and the reader may assume the
    rest are decorative. Every path also has to be in ``git ls-files``: a file
    that exists only on one machine is not published.
    """
    tracked = _tracked()
    broken: list[str] = []
    for doc, cited in _citations():
        if _deferred_reason(cited) is not None:
            continue
        resolved = _resolve(cited)
        if resolved is None:
            broken.append(f"{doc} cites {cited!r}, which does not exist")
            continue
        relative = resolved.relative_to(ROOT).as_posix()
        if not _is_tracked(relative, tracked):
            broken.append(f"{doc} cites {cited!r}, which is not in git ls-files")
    assert not broken, "dead citations:\n  " + "\n  ".join(broken)


def test_every_cited_demo_path_resolves_once_its_wave_lands() -> None:
    """Paths under the deferred prefixes are checked as soon as the prefix exists."""
    tracked = _tracked()
    pending: dict[str, str] = {}
    broken: list[str] = []
    for doc, cited in _citations():
        reason = _deferred_reason(cited)
        if reason is None:
            continue
        prefix = next(p for p in DEFERRED_PREFIXES if cited.startswith(p))
        if not (ROOT / prefix).exists():
            pending[prefix] = reason
            continue
        resolved = _resolve(cited)
        if resolved is None:
            broken.append(f"{doc} cites {cited!r}, which does not exist")
        elif not _is_tracked(resolved.relative_to(ROOT).as_posix(), tracked):
            broken.append(f"{doc} cites {cited!r}, which is not in git ls-files")
    assert not broken, "dead citations:\n  " + "\n  ".join(broken)
    if pending:
        waiting = "; ".join(f"{prefix} ({reason})" for prefix, reason in sorted(pending.items()))
        pytest.skip(f"not yet produced: {waiting}")


# --------------------------------------------------------------------- price


def test_the_incumbent_price_is_one_number_everywhere_it_is_printed() -> None:
    """``report/incumbent.py`` is the source; README and the evidence file agree."""
    price = BRAND24_TEAM.price_usd_month
    name = BRAND24_TEAM.name
    readme = README.read_text(encoding="utf-8")
    assert f"{name}, ${price} per month" in readme
    monthly = {int(m) for m in re.findall(r"\$(\d+) per month", readme)}
    assert monthly == {price}, (
        f"README prints monthly prices {sorted(monthly)}, source says {price}"
    )
    quoted = {int(m) for m in re.findall(r"`\$(\d+)`", readme)}
    assert quoted == {price}, f"README quotes {sorted(quoted)} as the price, source says {price}"

    evidence = INCUMBENT_README.read_text(encoding="utf-8")
    assert f"Team ${price}/mo" in evidence, "results/incumbent/README.md disagrees on the price"


def test_the_demo_receipt_carries_the_same_incumbent_block() -> None:
    if not DEMO_RECEIPT.exists():
        pytest.skip("results/demo/receipt.json not yet frozen (W6.1)")
    receipt = load_receipt(DEMO_RECEIPT)
    assert receipt.incumbent.name == BRAND24_TEAM.name
    assert receipt.incumbent.price_usd_month == BRAND24_TEAM.price_usd_month
    assert receipt.incumbent.url == BRAND24_TEAM.url
    assert receipt.incumbent.checked_at == BRAND24_TEAM.checked_at
    assert receipt.incumbent.mentions_quota == BRAND24_TEAM.mentions_quota


# ---------------------------------------------------------------- suite size


def test_the_suite_size_the_readme_advertises_is_the_suite_size_that_ran(
    request: pytest.FixtureRequest,
) -> None:
    """ "N tests" in the README is a present-tense claim about this collection."""
    readme = README.read_text(encoding="utf-8")
    advertised = {int(m) for m in re.findall(r"\b(\d{2,5}) (?:tests|passed)\b", readme)}
    if not advertised:
        pytest.skip("README advertises no suite size")
    collected = request.session.testscollected
    if collected < min(advertised) // 2:
        pytest.skip(f"partial run ({collected} collected); only meaningful on the full suite")
    assert advertised == {collected}, f"README advertises {sorted(advertised)}, ran {collected}"


# -------------------------------------------------------------- placeholders


def test_no_placeholder_markers_in_tracked_text() -> None:
    """No unresolved marker in anything published; open questions are named instead.

    The needles are assembled from fragments so this file does not trip itself.
    Word-bounded, so a Portuguese "TODOS" inside a recorded fixture is data.
    ``docs/research/`` is history and exempt, as in ``scripts/check_placeholders.py``.
    """
    needles = ("TB" + "D", "TO" + "DO")
    marker = re.compile(r"\b(?:" + "|".join(needles) + r")\b")
    offenders: list[str] = []
    for path in sorted(_tracked()):
        # The sibling shell gate names the markers by necessity, as this file
        # would if it did not build them from fragments.
        if path.startswith("docs/research/") or path == "scripts/check_placeholders.py":
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if marker.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()[:80]}")
    assert not offenders, "placeholders in tracked text:\n  " + "\n  ".join(offenders)


# ----------------------------------------------------------------- thresholds

# One pattern per THRESHOLD_INDEX key, against the bullet list under
# "## Threshold index". A key with no pattern, or a pattern with no match,
# fails: the index and the constants must name the same set of thresholds.
THRESHOLD_PATTERNS: dict[str, tuple[str, float]] = {
    "ci_level": (r"(\d+) %, B=", 0.01),
    "b_live": (r"B=(\d+) live", 1),
    "b_frozen_demo": (r"B=(\d+) frozen demo", 1),
    "seed": (r"seed (\d+)", 1),
    "holm_alpha": (r"α=([\d.]+) \(Holm\)", 1),
    "min_clusters_per_week": (r"n_clusters < (\d+)", 1),
    "min_mentions_per_week": (r"n < (\d+) in either period", 1),
    "event_min_count": (r"n_day ≥ max\((\d+), median", 1),
    "event_mad_multiplier": (r"median \+ (\d+)·MAD", 1),
    "event_min_clusters": (r"n_clusters_day ≥ (\d+)", 1),
    "event_baseline_days": (r"(\d+)-day baseline", 1),
    "tiebreak_confidence_threshold": (r"confidence < ([\d.]+)", 1),
    "tiebreak_cap_fraction": (r"cap (\d+) %", 0.01),
    "audit_sample_fraction": (r"audit (\d+) %", 0.01),
    "h1_max_total_usd": (r"H1: < \$([\d.]+)", 1),
    "h2_min_design_effect": (r"H2: ≥ ([\d.]+)", 1),
    "h3_min_agreement": (r"H3: ≥ ([\d.]+)", 1),
    "h4_min_total_usd_exclusive": (r"H4: > \$([\d.]+)", 1),
    "h5_min_agreement": (r"H5: ≥ ([\d.]+) on", 1),
    "h5_n_labels": (r"on (\d+) labels", 1),
    "topic_distance_threshold": (r"distance cut ([\d.]+)", 1),
    "topic_min_size": (r"min_size (\d+)", 1),
    "topic_min_breadth": (r"min_breadth (\d+)", 1),
}


def _threshold_index_bullets() -> list[str]:
    text = PRE_REG.read_text(encoding="utf-8")
    match = re.search(
        r"^## Threshold index\n(.*?)(?=^---$|^## )", text, flags=re.DOTALL | re.MULTILINE
    )
    assert match is not None, "PRE-REGISTRATION.md has no '## Threshold index' section"
    bullets: list[str] = []
    for line in match.group(1).splitlines():
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        elif line.startswith("  ") and bullets:
            bullets[-1] += " " + line.strip()
    assert bullets, "threshold index has no bullet list"
    return bullets


def test_every_threshold_in_the_index_equals_its_constant() -> None:
    index = " ; ".join(_threshold_index_bullets())
    assert set(THRESHOLD_PATTERNS) == set(config.THRESHOLD_INDEX), (
        "config.THRESHOLD_INDEX and the index patterns name different thresholds: "
        f"{sorted(set(THRESHOLD_PATTERNS) ^ set(config.THRESHOLD_INDEX))}"
    )
    wrong: list[str] = []
    for key, (pattern, scale) in THRESHOLD_PATTERNS.items():
        match = re.search(pattern, index)
        if match is None:
            wrong.append(f"{key}: pattern {pattern!r} not found in the threshold index")
            continue
        published = float(match.group(1)) * scale
        constant = config.THRESHOLD_INDEX[key]
        if published != pytest.approx(constant):
            wrong.append(f"{key}: index says {published}, config says {constant}")
    assert not wrong, "threshold index disagrees with config:\n  " + "\n  ".join(wrong)


def test_the_window_split_in_the_index_equals_its_constants() -> None:
    """The 14-day window and the 7-day split are frozen too, outside THRESHOLD_INDEX."""
    index = " ; ".join(_threshold_index_bullets())
    window = re.search(r"window_days = (\d+)", index)
    split = re.search(r"now − (\d+) d, now\)", index)
    assert window is not None and int(window.group(1)) == config.WINDOW_DAYS_DEFAULT
    assert split is not None and int(split.group(1)) == config.WOW_SPLIT_DAYS


# ------------------------------------------------------------------ model ids


def _decision_entries() -> list[tuple[str, str]]:
    """``(heading, body)`` per ``## Dnnn`` entry of docs/DECISIONS.md."""
    text = DECISIONS.read_text(encoding="utf-8")
    parts = re.split(r"^(## D\d{3}\b.*)$", text, flags=re.MULTILINE)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


@pytest.mark.xfail(
    strict=True,
    reason="D003 names only the two chat models; the embedding id is deferred to "
    "config.py without being spelled out. One dated DECISIONS line naming "
    "text-embedding-3-small turns this into a pass and this marker must then go.",
)
def test_every_model_id_in_config_has_a_dated_decision() -> None:
    """A model id that can change price or behaviour needs a decision with a date."""
    entries = _decision_entries()
    assert entries, "docs/DECISIONS.md has no '## Dnnn' entries"
    missing: list[str] = []
    for role in ("classifier_model", "tiebreak_model", "embedding_model"):
        model = config.LLM[role]
        dated = [
            heading
            for heading, body in entries
            if f"`{model}`" in body and _DATE.search(body) is not None
        ]
        if not dated:
            missing.append(f"{role} = {model!r} has no dated docs/DECISIONS.md entry naming it")
    assert not missing, "\n  ".join(["undocumented model ids:", *missing])


# ------------------------------------------------------------------ narration


def _numbers_in(value: object) -> set[str]:
    """Every number token in a JSON value, as normalised strings."""
    found: set[str] = set()
    if isinstance(value, bool):
        return found
    if isinstance(value, int | float):
        found.add(_normalise_number(repr(value)))
    elif isinstance(value, str):
        found.update(_normalise_number(m) for m in _NUMBER.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            found.update(_numbers_in(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_numbers_in(item))
    return found


def _normalise_number(token: str) -> str:
    cleaned = token.replace(",", "")
    try:
        number = float(cleaned)
    except ValueError:
        return cleaned
    return str(int(number)) if number.is_integer() else repr(number)


def test_every_number_in_the_narration_exists_in_the_demo_results() -> None:
    """The voice brief may not say a number the receipt or stats do not contain."""
    if not NARRATION.exists():
        pytest.skip("video/src/data/narration.json not yet written (W7.2)")
    sources = [p for p in (DEMO_RECEIPT, DEMO_STATS) if p.exists()]
    if not sources:
        pytest.skip("results/demo/receipt.json and stats.json not yet frozen (W6.1)")
    narrated = _numbers_in(json.loads(NARRATION.read_text(encoding="utf-8")))
    published: set[str] = set()
    for source in sources:
        published.update(_numbers_in(json.loads(source.read_text(encoding="utf-8"))))
    unsourced = sorted(narrated - published)
    assert not unsourced, f"narration numbers absent from the demo results: {unsourced}"


# -------------------------------------------------------------------- receipt


def test_the_demo_receipt_verifies_as_reconciled() -> None:
    if not DEMO_RECEIPT.exists():
        pytest.skip("results/demo/receipt.json not yet frozen (W6.1)")
    receipt = load_receipt(DEMO_RECEIPT)
    result = verify_receipt(receipt)
    assert receipt.verdict == "RECONCILED", f"stored verdict {receipt.verdict}"
    assert result.ok, f"sonar verify would exit {result.exit_code}: {'; '.join(result.problems)}"
