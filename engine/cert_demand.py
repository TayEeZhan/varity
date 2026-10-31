"""How often HN hiring posts for each role name each cert (data/certs.json), over the last 12 months.

    python -m engine.cert_demand          writes data/cert_demand.json

A post counts for a role when the role's title pattern matches it (engine.roles), and for a cert when any of
the cert's hn_patterns appears in it (case-insensitive, word bounded). Counts only; no post text is written.
Needs the raw HN threads (python -m engine.backfill_hn).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping

from engine.demand import RAW_DIR, THREADS_CSV, _live_posts, _read_threads
from engine.roles import ROLES_JSON, compile_patterns, load_roles, matching_roles
from engine.tagging import clean_text

ROOT = Path(__file__).resolve().parent.parent
CERTS_JSON = ROOT / "data" / "certs.json"
OUT_JSON = ROOT / "data" / "cert_demand.json"
WINDOW_MONTHS = 12


def cert_patterns(certs: Iterable[Mapping]) -> dict[str, re.Pattern[str]]:
    return {c["id"]: re.compile(r"\b(?:" + "|".join(re.escape(p) for p in c["hn_patterns"]) + r")\b", re.I) for c in certs}


def count(posts_by_month: Mapping[str, list[str]], role_patterns, cert_pats, months: list[str]) -> dict:
    """{cert: {roles: {role: {mentions, posts}}}} over the given months."""
    posts: dict[str, int] = {}
    mentions: dict[str, dict[str, int]] = {c: {} for c in cert_pats}
    for month in months:
        for text in posts_by_month.get(month, []):
            roles = matching_roles(text, role_patterns)
            if not roles:
                continue
            clean = clean_text(text)
            hits = [c for c, pat in cert_pats.items() if pat.search(clean)]
            for role in roles:
                posts[role] = posts.get(role, 0) + 1
                for c in hits:
                    mentions[c][role] = mentions[c].get(role, 0) + 1
    return {c: {"roles": {r: {"mentions": mentions[c].get(r, 0), "posts": n} for r, n in sorted(posts.items())}}
            for c in cert_pats}


def build(threads_csv=THREADS_CSV, raw_dir=RAW_DIR, certs_json=CERTS_JSON, roles_json=ROLES_JSON,
          out_json: Path | None = OUT_JSON) -> dict:
    threads = _read_threads(Path(threads_csv))
    months = sorted(t["month"] for t in threads)[-WINDOW_MONTHS:]
    by_month = {}
    for t in threads:
        if t["month"] in months:
            item = json.loads((Path(raw_dir) / f"{t['thread_id']}.json").read_text(encoding="utf-8"))
            by_month[t["month"]] = list(_live_posts(item))
    certs = json.loads(Path(certs_json).read_text(encoding="utf-8"))["certs"]
    doc = {"as_of": months[-1] if months else None, "window_months": len(months),
           "certs": count(by_month, compile_patterns(load_roles(roles_json)), cert_patterns(certs), months)}
    if out_json:
        Path(out_json).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    return doc


if __name__ == "__main__":
    out = build()
    print(f"cert_demand.json: {len(out['certs'])} certs, months up to {out['as_of']}")
