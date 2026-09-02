"""Text and URL normalisation for dedup and mention_id derivation."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
})

_HANDLE_RE = re.compile(r"@\w+")
_URL_RE = re.compile(r"https?://\S+")
_WHITESPACE_RE = re.compile(r"\s+")

TEXT_KEY_LEN = 200


def normalize_url(url: str) -> str:
    """Lower scheme, strip tracking params, remove trailing slash."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    qs = parse_qs(parsed.query, keep_blank_values=True)
    cleaned = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
    fragment = ""
    return urlunparse((scheme, netloc, path, parsed.params, urlencode(cleaned, doseq=True), fragment))


def normalize(text: str) -> str:
    """NFKC, casefold, collapse whitespace, strip URLs and @handles."""
    t = unicodedata.normalize("NFKC", text)
    t = t.casefold()
    t = _URL_RE.sub("", t)
    t = _HANDLE_RE.sub("", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def text_key(text: str) -> str:
    """First 200 chars of normalised text (the mention_id fallback key)."""
    return normalize(text)[:TEXT_KEY_LEN]
