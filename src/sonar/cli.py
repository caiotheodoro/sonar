"""``sonar`` command line: doctor, plan, run, reconcile, spend, record, render, verify.

Exit codes follow the design's error matrix: ``2`` for bad input (the ``Query``
validators run before any client exists; a missing key or an unreadable
session is bad input too), ``3`` when the Monid 402 breaker halted the session
or the plan's estimate exceeds ``--max-spend`` (nothing is submitted), ``4``
when the receipt is not ``RECONCILED`` after a live run or a ``reconcile``,
and ``0`` otherwise, including every abstention path. ``verify`` exits ``0``
only on ``RECONCILED``, ``1`` on ``PARTIAL`` or ``REPLAY`` and ``2`` on an
invalid card.

``run --fixtures`` is the offline path: the recorded run bodies under
``tests/fixtures`` are replayed through a mock transport and the seam is the
fake, so the whole pipeline runs without a key or a network; the receipt is a
``REPLAY``. ``render --from <dir>`` re-renders stored artifacts with the REPLAY
banner and the verdict ``REPLAY``.

``run --out DIR`` writes the session's artifacts directly into ``DIR``
(``DIR/receipt.json``); without ``--out`` they land under
``out/<session-id>/``. ``reconcile``, ``spend`` and ``doctor`` take ``--root``
(default ``out``) and find sessions as ``<root>/<session-id>/``;
``reconcile --session`` also accepts a session directory path.

Every entry point takes the client and seam factories as arguments so tests can
prove that bad input never constructs a client.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final, TextIO

import httpx
from pydantic import ValidationError

from sonar import config, pipeline
from sonar.chat import command as chat_command
from sonar.config import PROFILES
from sonar.llm.base import LlmBackend
from sonar.models import Query, Receipt
from sonar.monid import Ledger, MonidClient, MonidError, MonidHTTPError, load_api_key
from sonar.monid.client import DEFAULT_ENV_PATH, ENV_PATH_VAR, _parse_env_file
from sonar.report.markdown import REPLAY_BANNER, render_digest, render_receipt
from sonar.report.receipt import verify_receipt_file
from sonar.sentiment.cache import CACHE_DIR

EXIT_OK: Final[int] = pipeline.EXIT_OK
EXIT_USAGE: Final[int] = pipeline.EXIT_USAGE
EXIT_HALTED: Final[int] = pipeline.EXIT_HALTED
EXIT_PARTIAL: Final[int] = pipeline.EXIT_PARTIAL
EXIT_UNREACHABLE: Final[int] = 1
"""``doctor``: a key is present but its service did not answer."""

OPENAI_KEY_VAR: Final[str] = "OPENAI_API_KEY"
OPENAI_MODELS_URL: Final[str] = "https://api.openai.com/v1/models"
DEFAULT_ROOT: Final[Path] = Path("out")
"""Where sessions land without ``--out``: ``out/<session-id>/`` (README, CONTRACTS §Receipt)."""
DEFAULT_MAX_SPEND_USD: Final[float] = config.MONID_RUN_CAP_USD
RECORD_SCRIPT: Final[Path] = Path(__file__).resolve().parents[2] / "scripts" / "record_fixtures.py"

ClientFactory = Callable[[str], MonidClient]
LlmFactory = Callable[[str], LlmBackend]
Probe = Callable[[str], str | None]
"""``doctor`` reachability probe: returns ``None`` when the service answered, else the error."""


def default_client_factory(api_key: str) -> MonidClient:
    return MonidClient(api_key)


def default_llm_factory(api_key: str) -> LlmBackend:
    from sonar.llm.openai_backend import OpenAIBackend  # the only ``openai`` importer

    return OpenAIBackend(api_key)


def openai_probe(api_key: str) -> str | None:
    """``GET /v1/models`` with the key; the SDK is not imported here."""
    try:
        response = httpx.get(
            OPENAI_MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=20.0
        )
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    if response.status_code >= 400:
        return f"HTTP {response.status_code}: {response.text[:200]}"
    return None


def load_openai_key(env: Mapping[str, str] | None = None) -> str | None:
    """``OPENAI_API_KEY`` from the process env, else from ``$SONAR_ENV`` / ``~/.sonar/.env``."""
    source: Mapping[str, str] = os.environ if env is None else env
    direct = source.get(OPENAI_KEY_VAR, "").strip()
    if direct:
        return direct
    env_path = Path(source.get(ENV_PATH_VAR) or DEFAULT_ENV_PATH).expanduser()
    key = _parse_env_file(env_path).get(OPENAI_KEY_VAR, "").strip()
    return key or None


def load_elevenlabs_key(env: Mapping[str, str] | None = None) -> str | None:
    """``ELEVENLABS_API_KEY`` from the process env, else from ``$SONAR_ENV`` / ``~/.sonar/.env``."""
    source: Mapping[str, str] = os.environ if env is None else env
    direct = source.get(config.ENV_ELEVENLABS_KEY, "").strip()
    if direct:
        return direct
    env_path = Path(source.get(ENV_PATH_VAR) or DEFAULT_ENV_PATH).expanduser()
    key = _parse_env_file(env_path).get(config.ENV_ELEVENLABS_KEY, "").strip()
    return key or None


# --------------------------------------------------------------------------- parser


def _add_query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("brand", help="brand to listen for (2-64 chars)")
    parser.add_argument(
        "--vs",
        dest="competitors",
        nargs="+",
        action="extend",
        default=[],
        metavar="COMPETITOR",
        help="up to three competitors (one under --profile lite)",
    )
    parser.add_argument(
        "--alias", action="append", default=[], metavar="ALIAS", help="brand alias; repeatable"
    )
    parser.add_argument(
        "--brand-hint", default=None, help="context for the classifier (≤ 120 chars)"
    )
    parser.add_argument(
        "--profile", choices=sorted(PROFILES), default="full", help="smoke, lite or full"
    )
    parser.add_argument(
        "--max-spend",
        type=float,
        default=DEFAULT_MAX_SPEND_USD,
        metavar="USD",
        help=f"refuse when the plan estimate exceeds this (default {DEFAULT_MAX_SPEND_USD})",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sonar", description="Pay-per-call brand listening.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--trace", action="store_true", help="log every stage to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", parents=[common], help="check keys and reachability")
    doctor.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="sessions root for the wallet line"
    )

    plan = sub.add_parser("plan", parents=[common], help="validate the query and estimate")
    _add_query_args(plan)

    run = sub.add_parser("run", parents=[common], help="fetch, analyse, write the artifacts")
    _add_query_args(run)
    run.add_argument(
        "--out",
        type=Path,
        default=None,
        metavar="DIR",
        help=f"session directory for the artifacts (default {DEFAULT_ROOT}/<session-id>)",
    )
    run.add_argument(
        "--run-deadline",
        type=float,
        default=pipeline.DEFAULT_RUN_DEADLINE_S,
        metavar="SECONDS",
        help="per-run wait before a run abstains with reason deadline",
    )
    run.add_argument("--no-voice", action="store_true", help="skip narration and the voice run")
    run.add_argument(
        "--fixtures",
        nargs="?",
        const=pipeline.FIXTURES_DIR,
        default=None,
        type=Path,
        metavar="DIR",
        help="offline replay of the recorded fixtures with the fake seam (default tests/fixtures)",
    )
    run.add_argument(
        "--resamples", type=int, default=config.B, help=f"bootstrap resamples (default {config.B})"
    )
    run.add_argument("--session", default=None, help="session id to use instead of a fresh one")
    run.add_argument("--voice-id", default=None, help="ElevenLabs voice id")

    reconcile = sub.add_parser("reconcile", parents=[common], help="rejoin GET /v1/runs")
    reconcile.add_argument(
        "--session", required=True, help="session id under --root, or a session directory"
    )
    reconcile.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="sessions root")

    spend = sub.add_parser("spend", parents=[common], help="totals per session and running")
    spend.add_argument("--session", default=None, help="only this session id")
    spend.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="sessions root")

    record = sub.add_parser("record", parents=[common], help="record adapter fixtures (live)")
    record.add_argument("brand")
    record.add_argument("--profile", choices=sorted(PROFILES), default="smoke")
    record.add_argument("--alias", action="append", default=[])
    record.add_argument("--max-spend", type=float, default=None)
    record.add_argument("--fixtures-dir", type=Path, default=None)
    record.add_argument("--dry-run", action="store_true")
    record.add_argument("--task", default=None)

    render = sub.add_parser("render", parents=[common], help="re-render stored artifacts")
    render.add_argument("--from", dest="source_dir", type=Path, required=True, metavar="DIR")
    render.add_argument("--out", type=Path, default=None, help="write the Markdown here too")

    verify = sub.add_parser("verify", parents=[common], help="re-derive a receipt's verdict")
    verify.add_argument("receipt", type=Path)
    chat_command.register(sub, common, default_root=DEFAULT_ROOT)
    return parser


# --------------------------------------------------------------------------- helpers


def _configure_logging(trace: bool, err: TextIO) -> None:
    level = logging.INFO if trace else logging.WARNING
    logging.basicConfig(
        level=level,
        stream=err,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _query_from(args: argparse.Namespace, out: TextIO) -> Query | None:
    try:
        return Query(
            brand=args.brand,
            brand_aliases=list(args.alias),
            brand_hint=args.brand_hint,
            competitors=list(args.competitors),
            profile=args.profile,
        )
    except ValidationError as exc:
        print(f"invalid query: {exc}", file=out)
        return None


def _session_dir(session: str, root: Path) -> Path:
    """``--session`` as a session directory when it is one, else ``<root>/<session-id>``."""
    given = Path(session)
    if (given / pipeline.RECEIPT_JSON).is_file():
        return given
    return root / session


def _receipts_under(root: Path) -> list[tuple[Path, Receipt]]:
    """Every readable receipt at ``<root>/receipt.json`` or ``<root>/*/receipt.json``."""
    found: list[tuple[Path, Receipt]] = []
    if not root.is_dir():
        return found
    candidates = [root / pipeline.RECEIPT_JSON, *sorted(root.glob(f"*/{pipeline.RECEIPT_JSON}"))]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            found.append(
                (path.parent, Receipt.model_validate_json(path.read_text(encoding="utf-8")))
            )
        except (OSError, ValueError, ValidationError):
            continue
    return found


def _spend_lines(receipts: Sequence[tuple[Path, Receipt]]) -> list[str]:
    header = f"{'session':<40} {'verdict':<11} {'monid':>9} {'openai':>9} {'total':>9}"
    lines = [header, "-" * len(header)]
    monid = llm = total = 0.0
    for _, receipt in receipts:
        t = receipt.totals
        lines.append(
            f"{receipt.session_id:<40} {receipt.verdict:<11} {t.monid_usd:>9.4f} "
            f"{t.llm_usd:>9.4f} {t.total_usd:>9.4f}"
        )
        if not receipt.replay:
            monid += t.monid_usd
            llm += t.llm_usd
            total += t.total_usd
    lines.append("-" * len(header))
    lines.append(
        f"{'running total (live sessions)':<40} {'':<11} {monid:>9.4f} {llm:>9.4f} {total:>9.4f}"
    )
    return lines


# --------------------------------------------------------------------------- commands


def cmd_doctor(
    args: argparse.Namespace,
    *,
    out: TextIO,
    env: Mapping[str, str] | None,
    client_factory: ClientFactory,
    probe: Probe,
) -> int:
    code = EXIT_OK
    try:
        monid_key: str | None = load_api_key(dict(env) if env is not None else None)
        print("monid key: present", file=out)
    except MonidError as exc:
        monid_key = None
        print(f"monid key: MISSING ({exc})", file=out)
        code = EXIT_USAGE
    openai_key = load_openai_key(env)
    print(f"openai key: {'present' if openai_key else 'MISSING (OPENAI_API_KEY)'}", file=out)
    if openai_key is None:
        code = EXIT_USAGE
    if monid_key is not None:
        client = client_factory(monid_key)
        try:
            listed = client.list_runs(limit=1)
            print(f"monid api: reachable (GET /v1/runs returned {len(listed)} item(s))", file=out)
        except (MonidError, MonidHTTPError) as exc:
            print(f"monid api: UNREACHABLE ({exc})", file=out)
            code = code or EXIT_UNREACHABLE
        finally:
            client.close()
    if openai_key is not None:
        problem = probe(openai_key)
        if problem is None:
            print("openai api: reachable (GET /v1/models)", file=out)
        else:
            print(f"openai api: UNREACHABLE ({problem})", file=out)
            code = code or EXIT_UNREACHABLE
    receipts = _receipts_under(args.root)
    live = [r for _, r in receipts if not r.replay]
    spent = sum(r.totals.monid_usd for r in live)
    print(
        f"wallet: {len(live)} live session(s) under {args.root} spent ${spent:.4f} on Monid; "
        f"budget cap ${config.MONID_BUDGET_CAP_USD:.2f}, reserve ${config.MONID_RESERVE_USD:.2f} "
        "(balance is on the Monid dashboard or `monid whoami`)",
        file=out,
    )
    print("doctor: ok" if code == EXIT_OK else f"doctor: problems (exit {code})", file=out)
    return code


def cmd_plan(args: argparse.Namespace, *, out: TextIO) -> int:
    query = _query_from(args, out)
    if query is None:
        return EXIT_USAGE
    plan = pipeline.build_plan(query)
    print(json.dumps(query.model_dump(mode="json"), ensure_ascii=False), file=out)
    for line in pipeline.plan_lines(plan):
        print(line, file=out)
    if plan.estimate_usd > args.max_spend:
        print(
            f"WARNING: estimate ${plan.estimate_usd:.4f} exceeds --max-spend "
            f"${args.max_spend:.2f}; `sonar run` would refuse",
            file=out,
        )
    return EXIT_OK


def cmd_run(
    args: argparse.Namespace,
    *,
    out: TextIO,
    env: Mapping[str, str] | None,
    client_factory: ClientFactory,
    llm_factory: LlmFactory,
    now: datetime | None,
) -> int:
    query = _query_from(args, out)
    if query is None:
        return EXIT_USAGE
    plan = pipeline.build_plan(query)
    for line in pipeline.plan_lines(plan):
        print(line, file=out)
    fixtures: Path | None = args.fixtures
    if fixtures is None and plan.estimate_usd > args.max_spend:
        print(
            f"REFUSED: estimate ${plan.estimate_usd:.4f} exceeds --max-spend "
            f"${args.max_spend:.2f}; nothing submitted",
            file=out,
        )
        return EXIT_HALTED

    if fixtures is not None:
        if not fixtures.is_dir():
            print(f"fixtures directory not found: {fixtures}", file=out)
            return EXIT_USAGE
        client = pipeline.fixtures_client(fixtures)
        llm: LlmBackend = pipeline.fixture_llm(fixtures / "labels.json")
        cache_dir: Path | None = None
        replay = True
        tts_direct = False
        tts_api_key: str | None = None
    else:
        try:
            monid_key = load_api_key(dict(env) if env is not None else None)
        except MonidError as exc:
            print(f"no Monid key: {exc}", file=out)
            return EXIT_USAGE
        openai_key = load_openai_key(env)
        if openai_key is None:
            print(f"no OpenAI key: set {OPENAI_KEY_VAR} or add it to ~/.sonar/.env", file=out)
            return EXIT_USAGE
        client = client_factory(monid_key)
        llm = llm_factory(openai_key)
        cache_dir = CACHE_DIR
        replay = False
        tts_direct = config.resolve_tts(dict(env) if env is not None else None).direct
        tts_api_key = load_elevenlabs_key(env)
        if tts_direct and tts_api_key is None:
            print(
                f"{config.ENV_TTS_DIRECT} set but no {config.ENV_ELEVENLABS_KEY}; "
                "voicing through Monid",
                file=out,
            )
        elif tts_direct:
            print("voice: direct to ElevenLabs (D016); Monid-equivalent cost estimated", file=out)

    session_id = args.session or pipeline.new_session_id(query.brand, now)
    session_dir: Path = args.out if args.out is not None else DEFAULT_ROOT / session_id
    ledger = Ledger(session_dir / pipeline.RUNS_JSONL)
    options = pipeline.RunOptions(
        voice=not args.no_voice,
        replay=replay,
        run_deadline_s=args.run_deadline,
        resamples=args.resamples,
        cache_dir=cache_dir,
        voice_id=args.voice_id,
        tts_direct=tts_direct,
        tts_api_key=tts_api_key,
        bounded_reconcile=not replay,
    )
    print(f"session {session_id} -> {session_dir}{' (offline replay)' if replay else ''}", file=out)
    try:
        result = pipeline.run(
            query, client, ledger, llm, session_dir, session_id=session_id, now=now, options=options
        )
    finally:
        client.close()
    _print_run_summary(result, out)
    return result.exit_code


def _print_run_summary(result: pipeline.RunResult, out: TextIO) -> None:
    receipt = result.receipt
    t = receipt.totals
    m = receipt.mentions
    print(
        f"verdict {receipt.verdict}; mentions fetched {m.fetched} deduped {m.deduped} "
        f"labelled {m.labelled}; runs {t.monid_runs} (failed {t.monid_runs_failed}); "
        f"cost Monid ${t.monid_usd:.4f} + OpenAI ${t.llm_usd:.4f} = ${t.total_usd:.4f}; "
        f"abstentions {len(receipt.abstentions)}",
        file=out,
    )
    for path in result.written:
        print(f"wrote {path}", file=out)
    if result.halted:
        print("HALTED: Monid 402 tripped the breaker; stats are on what was fetched", file=out)
    elif result.exit_code == EXIT_PARTIAL:
        print(
            f"PARTIAL: run `sonar reconcile --session {result.out_dir}` after billing settles",
            file=out,
        )


def cmd_reconcile(
    args: argparse.Namespace,
    *,
    out: TextIO,
    env: Mapping[str, str] | None,
    client_factory: ClientFactory,
    now: datetime | None,
) -> int:
    session_dir = _session_dir(args.session, args.root)
    if not (session_dir / pipeline.RECEIPT_JSON).is_file():
        print(f"no receipt under {session_dir}", file=out)
        return EXIT_USAGE
    try:
        monid_key = load_api_key(dict(env) if env is not None else None)
    except MonidError as exc:
        print(f"no Monid key: {exc}", file=out)
        return EXIT_USAGE
    client = client_factory(monid_key)
    try:
        receipt, _digest, code = pipeline.reconcile_session(session_dir, client, now=now)
    finally:
        client.close()
    rec = receipt.reconciliation
    print(
        f"verdict {receipt.verdict}; listed in window {rec.n_listed_in_window}; "
        f"unmatched remote {rec.unmatched_remote_run_ids or 'none'}; "
        f"unreconciled local_seq {rec.unreconciled_local_seqs or 'none'}; "
        f"Monid ${receipt.totals.monid_usd:.4f} total ${receipt.totals.total_usd:.4f}",
        file=out,
    )
    return code


def cmd_spend(args: argparse.Namespace, *, out: TextIO) -> int:
    receipts = _receipts_under(args.root)
    if args.session is not None:
        receipts = [(d, r) for d, r in receipts if r.session_id == args.session]
        if not receipts:
            print(f"no session {args.session} under {args.root}", file=out)
            return EXIT_USAGE
    if not receipts:
        print(f"no receipts under {args.root}", file=out)
    for line in _spend_lines(receipts):
        print(line, file=out)
    return EXIT_OK


def cmd_record(args: argparse.Namespace, *, out: TextIO) -> int:
    if not RECORD_SCRIPT.is_file():
        print(f"recorder script not found: {RECORD_SCRIPT}", file=out)
        return EXIT_USAGE
    spec = importlib.util.spec_from_file_location("sonar_record_fixtures", RECORD_SCRIPT)
    if spec is None or spec.loader is None:
        print(f"cannot load {RECORD_SCRIPT}", file=out)
        return EXIT_USAGE
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    argv: list[str] = ["--brand", args.brand, "--profile", args.profile]
    for alias in args.alias:
        argv.extend(["--alias", alias])
    if args.max_spend is not None:
        argv.extend(["--max-spend", str(args.max_spend)])
    if args.fixtures_dir is not None:
        argv.extend(["--fixtures-dir", str(args.fixtures_dir)])
    if args.task is not None:
        argv.extend(["--task", args.task])
    if args.dry_run:
        argv.append("--dry-run")
    main: Callable[..., int] = module.main
    return int(main(argv, out=out))


def cmd_render(args: argparse.Namespace, *, out: TextIO) -> int:
    source: Path = args.source_dir
    missing = [
        name
        for name in (pipeline.RECEIPT_JSON, pipeline.DIGEST_JSON)
        if not (source / name).is_file()
    ]
    if missing:
        print(f"cannot render {source}: missing {', '.join(missing)}", file=out)
        return EXIT_USAGE
    try:
        receipt, digest = pipeline.replay_artifacts(source)
    except (ValueError, ValidationError) as exc:
        print(f"cannot render {source}: {exc}", file=out)
        return EXIT_USAGE
    markdown = render_digest(digest) + "\n" + render_receipt(receipt) + "\n"
    print(REPLAY_BANNER, file=out)
    print(f"verdict {receipt.verdict}", file=out)
    print(markdown, file=out)
    if args.out is not None:
        target: Path = args.out
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(REPLAY_BANNER + "\n\n" + markdown, encoding="utf-8")
        print(f"wrote {target}", file=out)
    return EXIT_OK


def cmd_verify(args: argparse.Namespace, *, out: TextIO) -> int:
    result = verify_receipt_file(args.receipt)
    stored = result.stored_verdict or "unreadable"
    derived = result.derived_verdict or "unreadable"
    print(f"verdict {stored} (re-derived {derived}); status {result.status}", file=out)
    for problem in result.problems:
        print(f"- {problem}", file=out)
    return result.exit_code


# --------------------------------------------------------------------------- entry point


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: ClientFactory = default_client_factory,
    llm_factory: LlmFactory = default_llm_factory,
    probe: Probe = openai_probe,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(bool(getattr(args, "trace", False)), err)
    handlers: dict[str, Callable[[], int]] = {
        "doctor": lambda: cmd_doctor(
            args, out=out, env=env, client_factory=client_factory, probe=probe
        ),
        "plan": lambda: cmd_plan(args, out=out),
        "run": lambda: cmd_run(
            args,
            out=out,
            env=env,
            client_factory=client_factory,
            llm_factory=llm_factory,
            now=now,
        ),
        "reconcile": lambda: cmd_reconcile(
            args, out=out, env=env, client_factory=client_factory, now=now
        ),
        "spend": lambda: cmd_spend(args, out=out),
        "record": lambda: cmd_record(args, out=out),
        "render": lambda: cmd_render(args, out=out),
        "verify": lambda: cmd_verify(args, out=out),
        "ask": lambda: chat_command.cmd_ask(
            args, out=out, openai_key=load_openai_key(env), llm_factory=llm_factory
        ),
    }
    command: str = args.command
    return handlers[command]()


if __name__ == "__main__":
    sys.exit(main())
