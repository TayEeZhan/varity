"""Turn a raw collected record into clean, comparable fields."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from trendsignal.models import RawItemIn

MAX_TEXT_CHARS = 6000
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "igshid", "si", "s"}
ARXIV_RE = re.compile(r"^(?:www\.)?arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?$")
HF_PAPER_RE = re.compile(r"^huggingface\.co/papers/(\d{4}\.\d{4,5})$")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
WORDS_PER_MINUTE = 230


@dataclass(frozen=True)
class NormalisedItem:
    canonical_url: str
    linked_url: str | None
    title: str
    text: str
    content_hash: str


def canonical_url(url: str) -> str:
    """Lowercase host, drop www/tracking params/fragments; map arXiv and HF paper URLs to one form."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    paper = ARXIV_RE.match(f"{host}{path}") or HF_PAPER_RE.match(f"{host}{path}")
    if paper:
        return f"https://arxiv.org/abs/{paper.group(1)}"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


def clean_text(raw: str, limit: int = MAX_TEXT_CHARS) -> str:
    without_code = SCRIPT_RE.sub(" ", raw or "")
    without_tags = TAG_RE.sub(" ", without_code)
    collapsed = " ".join(html.unescape(without_tags).split())
    return collapsed[:limit]


def content_hash(title: str, text: str) -> str:
    basis = re.sub(r"[^a-z0-9]+", " ", f"{title} {text[:500]}".lower()).strip()
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def reading_minutes(text: str, category: str | None) -> int:
    """Rough time to understand the primary source. Papers take longer than their abstract suggests."""
    words = len(text.split())
    minutes = max(1, round(words / WORDS_PER_MINUTE))
    if category == "research":
        return max(30, minutes)
    if category in ("model_release", "security_incident", "api_pricing_change"):
        return max(5, minutes)
    return max(2, minutes)


def normalise(raw: RawItemIn) -> NormalisedItem:
    title = clean_text(raw.title, limit=300)
    text = clean_text(raw.text)
    linked = raw.payload.get("linked_url") if isinstance(raw.payload, dict) else None
    return NormalisedItem(
        canonical_url=canonical_url(raw.url),
        linked_url=canonical_url(linked) if linked else None,
        title=title,
        text=text,
        content_hash=content_hash(title, text),
    )
