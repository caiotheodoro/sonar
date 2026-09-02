#!/usr/bin/env python3
"""Fail if any tracked text file contains the strings TBD or TODO."""
from __future__ import annotations

import subprocess
import sys


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
    violations: list[str] = []
    for path in tracked_files():
        if path == self_path or any(path.startswith(p) for p in exclude_prefixes):
            continue
        try:
            with open(path, errors="ignore") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for needle in ("TBD", "TODO"):
            if needle in text:
                violations.append(f"{path}: contains {needle}")

    if violations:
        print("check-placeholders FAILED — found placeholders:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("check-placeholders OK — no TBD or TODO found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
