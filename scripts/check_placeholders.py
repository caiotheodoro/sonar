#!/usr/bin/env python3
"""Fail if any tracked text file contains the standalone markers TBD or TODO.

Word-bounded, like the claims gate: a Portuguese "TODOS" or a fixture id is
data, not a placeholder. Recorded provider payloads (fixtures and the frozen
demo's mention/label files) are third-party text and are exempt outright.
"""
from __future__ import annotations

import re
import subprocess
import sys

_MARKER = re.compile(r"\b(?:TBD|TODO)\b")


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [f for f in result.stdout.splitlines() if f.strip()]


def main() -> int:
    self_path = "scripts/check_placeholders.py"
    # Recorded provider payloads are third-party text, and the claims gate
    # must spell the needles it searches for; neither is a placeholder.
    exclude_prefixes = ("docs/research/", "tests/fixtures/", "tests/test_published_claims.py")
    exclude_suffixes = ("/mentions.jsonl", "/labels.jsonl")
    violations: list[str] = []
    for path in tracked_files():
        if path == self_path or any(path.startswith(p) for p in exclude_prefixes):
            continue
        if path.startswith("results/") and path.endswith(exclude_suffixes):
            continue
        try:
            with open(path, errors="ignore") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        found = {m.group(0) for m in _MARKER.finditer(text)}
        for needle in sorted(found):
            violations.append(f"{path}: contains {needle}")

    if violations:
        print("check-placeholders FAILED — found placeholders:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("check-placeholders OK — no standalone TBD or TODO found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
