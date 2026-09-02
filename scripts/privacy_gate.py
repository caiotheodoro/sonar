#!/usr/bin/env python3
"""Fail if any tracked file contains an API key pattern or a raw social handle field."""
from __future__ import annotations

import re
import subprocess
import sys

# Patterns that look like leaked secrets
API_KEY_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),           # OpenAI
    re.compile(r"monid_live_[A-Za-z0-9]{20,}"),    # Monid
    re.compile(r"ghp_[A-Za-z0-9]{36}"),            # GitHub PAT
    re.compile(r"xoxb-[0-9]{10,}-[A-Za-z0-9]{24,}"),  # Slack bot
    re.compile(r"AKIA[A-Z0-9]{16}"),               # AWS access key
]

# Raw social handle fields that should never appear as plaintext values
HANDLE_FIELDS = [
    re.compile(r'"twitter_handle"\s*:\s*"[^"]*"'),
    re.compile(r'"x_handle"\s*:\s*"[^"]*"'),
    re.compile(r'"instagram_handle"\s*:\s*"[^"]*"'),
    re.compile(r'"email"\s*:\s*"[^"]*@[a-z]"'),
]


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [f for f in result.stdout.splitlines() if f.strip()]


def main() -> int:
    violations: list[str] = []
    for path in tracked_files():
        try:
            with open(path, errors="ignore") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for pat in API_KEY_PATTERNS:
            if pat.search(text):
                violations.append(f"{path}: matches API key pattern {pat.pattern}")
        for pat in HANDLE_FIELDS:
            if pat.search(text):
                violations.append(f"{path}: matches raw handle field {pat.pattern}")

    if violations:
        print("privacy-gate FAILED — possible secrets or raw handles:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("privacy-gate OK — no secrets or raw handles found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
