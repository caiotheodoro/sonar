"""Step ``doctor``: ``sonar doctor`` as JSON. Keys present, services reachable, wallet line.

    python skill/sonar/scripts/doctor.py --workspace DIR [--root out]

Writes ``<workspace>/doctor.json`` and prints the same object. Exit ``0`` when the CLI
said ``doctor: ok``, ``2`` when a key is missing, ``1`` when a key is present but its
service did not answer. The script never reads a key itself.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import DOCTOR_JSON, call_sonar, emit, utcnow_iso, workspace_parser, write_json


def _status(lines: list[str], prefix: str) -> str | None:
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def main(argv: list[str] | None = None) -> int:
    parser = workspace_parser("sonar doctor as JSON")
    parser.add_argument("--root", type=Path, default=None, help="sessions root for the wallet line")
    args = parser.parse_args(argv)
    workspace: Path = args.workspace
    cli_args = ["doctor"]
    if args.root is not None:
        cli_args.extend(["--root", str(args.root)])
    result = call_sonar(cli_args)
    lines = result.lines
    report: dict[str, Any] = {
        "step": "doctor",
        "checked_at": utcnow_iso(),
        "ok": result.exit_code == 0,
        "exit_code": result.exit_code,
        "monid_key": _status(lines, "monid key:"),
        "openai_key": _status(lines, "openai key:"),
        "monid_api": _status(lines, "monid api:"),
        "openai_api": _status(lines, "openai api:"),
        "wallet": _status(lines, "wallet:"),
        "lines": lines,
        "stderr": result.stderr.strip(),
    }
    write_json(workspace / DOCTOR_JSON, report)
    return emit(report, result.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
