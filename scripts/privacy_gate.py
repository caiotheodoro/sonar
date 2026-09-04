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


SHOTS_PREFIX = "video/public/shots/"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def check_shots(tracked: list[str]) -> list[str]:
    """Every tracked screenshot needs a reviewed sidecar; app captures need redactions.

    If ``tesseract`` is on PATH the PNG is OCR'd and the key and email
    patterns run over the text; otherwise that step is reported as skipped.
    """
    import json
    import shutil

    problems: list[str] = []
    pngs = [p for p in tracked if p.startswith(SHOTS_PREFIX) and p.endswith(".png")]
    ocr = shutil.which("tesseract")
    if pngs and not ocr:
        print(f"privacy-gate: tesseract not on PATH; {len(pngs)} screenshot(s) not OCR-scanned")
    for png in pngs:
        sidecar = png[:-4] + ".json"
        if sidecar not in tracked:
            problems.append(f"{png}: sidecar {sidecar} is not tracked")
            continue
        with open(sidecar, encoding="utf-8") as fh:
            meta = json.load(fh)
        if meta.get("pii_reviewed") is not True:
            problems.append(f"{png}: sidecar pii_reviewed is not true")
        host = str(meta.get("url", "")).split("/")[2] if "//" in str(meta.get("url", "")) else ""
        if host.startswith("app.") and not meta.get("redactions"):
            problems.append(f"{png}: a logged-in app capture with no redactions")
        if ocr:
            text = subprocess.run(
                [ocr, png, "-", "--psm", "6"], capture_output=True, text=True, check=False
            ).stdout
            for pat in API_KEY_PATTERNS:
                if pat.search(text):
                    problems.append(f"{png}: OCR text matches API key pattern {pat.pattern}")
            if EMAIL.search(text):
                problems.append(f"{png}: OCR text contains an email address")
    return problems


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    )
    return [f for f in result.stdout.splitlines() if f.strip()]


def main() -> int:
    violations: list[str] = []
    tracked = tracked_files()
    violations.extend(check_shots(tracked))
    for path in tracked:
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
