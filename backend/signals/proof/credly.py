"""Cert check: a Credly badge link, read from Credly only (allowed domain), compared with the catalog cert.

Passes when the badge's issuer contains the cert's credly_issuer, its title matches the cert name, and it is
accepted and not expired. Any failure to read it gives "self_reported", never a block.
When the badge names its earner and the user is signed in, the names must roughly match (a flag, not proof:
Credly hides the earner's email, so code cannot prove the badge is the user's own).
"""

from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher
from typing import Any, Callable, Mapping

import httpx

BADGE_RE = re.compile(r"^https://(?:www\.)?credly\.com/badges/([0-9a-fA-F-]{36})(?:/[\w-]*)?/?$")
TITLE_MATCH = 0.6  # similarity of badge title to cert name (team judgement)
NAME_MATCH = 0.8   # similarity of badge earner to account name when the words differ (team judgement)


def badge_id(url: str) -> str | None:
    m = BADGE_RE.match((url or "").strip())
    return m.group(1).lower() if m else None


def _fetch(badge: str) -> Any:
    r = httpx.get(f"https://www.credly.com/badges/{badge}.json", timeout=10, follow_redirects=False)
    r.raise_for_status()
    return r.json()


def _first(doc: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(doc, Mapping):
            return None
        doc = doc.get(key)
    return doc


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _name_matches(a: str, b: str) -> bool:
    """Fuzzy: every word of the shorter name appears in the longer one, or the two are close. Flags, never proves."""
    wa, wb = set(_slug(a).split()), set(_slug(b).split())
    small, big = sorted((wa, wb), key=len)
    return bool(small) and (small <= big or SequenceMatcher(None, _slug(a), _slug(b)).ratio() >= NAME_MATCH)


def verify(url: str, cert: Mapping, today: date, fetch: Callable[[str], Any] = _fetch, earner: str | None = None) -> dict:
    """{'status': 'certified' | 'self_reported', 'detail': str}. earner: the user's account name, when known."""
    badge = badge_id(url)
    if badge is None:
        return {"status": "self_reported", "detail": "Not a Credly badge link (https://www.credly.com/badges/…)."}
    try:
        doc = fetch(badge)
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "self_reported", "detail": f"Could not read the badge from Credly ({type(exc).__name__})."}
    doc = doc.get("data", doc) if isinstance(doc, Mapping) else {}
    title = str(_first(doc, "badge_template", "name") or doc.get("name") or "")
    entities = _first(doc, "issuer", "entities") or []
    issuer = " ".join(str(_first(e, "entity", "name") or "") for e in entities).strip() \
        or str(_first(doc, "issuer", "name") or "")
    state, expires = doc.get("state"), doc.get("expires_at")
    if cert["credly_issuer"].lower() not in issuer.lower():
        return {"status": "self_reported", "detail": f"Badge issuer is {issuer or 'unknown'}, not {cert['credly_issuer']}."}
    if SequenceMatcher(None, _slug(title), _slug(cert["name"])).ratio() < TITLE_MATCH:
        return {"status": "self_reported", "detail": f"Badge is \"{title}\", not {cert['name']}."}
    if state and state != "accepted":
        return {"status": "self_reported", "detail": f"Badge state is {state}."}
    if expires and str(expires)[:10] < today.isoformat():
        return {"status": "self_reported", "detail": f"Badge expired on {str(expires)[:10]}."}
    issued_to = str(doc.get("issued_to") or _first(doc, "user", "name") or "")
    if earner and issued_to and not _name_matches(earner, issued_to):
        return {"status": "self_reported", "detail": f"Badge was issued to {issued_to}, not to your account name."}
    return {"status": "certified", "detail": f"Verified on Credly: {title}, issued by {issuer}."}
