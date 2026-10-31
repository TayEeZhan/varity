"""Data-driven SDG links: which sectors hire for each role and skill.

Run: python -m engine.sdg --raw-dir <folder with the raw HN thread JSON files>
It writes data/role_sdg.json and data/skill_sdg.json (aggregates and thread URLs only).

Idea. The same role can serve very different goals, depending on what the employer does. An HN job
post says what the company does. We tag each post with the sectors it describes (data/sdg_sectors.json,
word-boundary regex patterns, tuned for precision), then measure, per role and per skill:
    share = posts in the sector / posts of the role (or posts that mention the skill)
for the last `months` months and the `months` before, against the same share over all posts
(the baseline). A user who picks a goal, such as "climate", sees which roles actually hire for it.

Rules (same counting rules as engine.roles):
- Posts are top-level HN posts with text, not deleted. A post counts once per sector and once per role.
- Role posts are SINGLE-ROLE posts only (a post that names 2 or more roles tells little about either).
  The role title patterns come from data/roles.json (engine.roles).
- Skill posts are all posts that mention the skill (engine.tagging, no masking).
- Perks and legal lines are removed before sector patterns run: a "Benefits: healthcare, dental" line
  or an equal-opportunity statement must not tag a post as health or accessibility.
- Outputs hold counts, shares and thread URLs only. No post text, no company names, no post links.

Hooks for the UI (no app code here):
    rerank_for_goal(match_roles_output, role_sdg, goal_sector) -> dict
    plan_sdg_summary(plan, role, role_sdg, goal_sector=None) -> {"lines": [...], "numbers": {...}}
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):  # allow "python engine/sdg.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.demand import RAW_DIR, THREADS_CSV, _live_posts, _read_threads  # noqa: E402
from engine.roles import (  # noqa: E402
    ROLES_JSON,
    _read_item,
    _window,
    build_role_trends,
    compile_patterns,
    load_roles,
    role_spans,
)
from engine.tagging import clean_text, load_taxonomy, tag_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SECTORS_JSON = DATA_DIR / "sdg_sectors.json"
ROLE_SDG_JSON = DATA_DIR / "role_sdg.json"
SKILL_SDG_JSON = DATA_DIR / "skill_sdg.json"
SCHEMA_VERSION = 1

# Measurement (set before looking at results).
WINDOW_MONTHS = 12
MIN_N = 30  # a role or skill needs at least this many posts in the window for its shares to count
MIN_EMPLOYERS = 3  # and at least this many different employers tagged in the sector (HN posts repeat monthly)
MIN_SECTOR_POSTS = 10  # team judgement: and at least this many posts of the role in the sector, or the lift is rough
EXAMPLE_THREADS = 2

# Goal fit (team judgement, not fitted). goal_fit_score = rank_score * (1 + GOAL_WEIGHT * excess),
# excess = min(max(lift - 1, 0), MAX_EXCESS), lift = role share / baseline share.
# Only a reliable over-representation raises the score (reliable: MIN_N role posts, MIN_EMPLOYERS employers and
# MIN_SECTOR_POSTS posts in the sector; the last one is checked here, in goal_numbers). Nothing is lowered and no role is hidden.
GOAL_WEIGHT = 0.15
MAX_EXCESS = 3.0


# ---------------------------------------------------------------- sectors and text

def load_sectors(path: str | Path = SECTORS_JSON) -> dict[str, Any]:
    """Read data/sdg_sectors.json and check it. Fails early on a bad regex or a duplicate id."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = doc.get("text_rules")
    sectors = doc.get("sectors")
    if not isinstance(rules, dict) or not isinstance(sectors, list) or not sectors:
        raise ValueError(f"sectors file needs 'text_rules' and a non-empty 'sectors' list: {path}")
    for key in ("drop_line", "benefits_header", "benefits_inline"):
        re.compile(rules[key], re.IGNORECASE)
    seen: set[str] = set()
    for sector in sectors:
        missing = [k for k in ("id", "name", "sdg", "patterns") if k not in sector]
        if missing:
            raise ValueError(f"sector {sector.get('id')!r} is missing {missing}")
        if sector["id"] in seen:
            raise ValueError(f"duplicate sector id {sector['id']!r}")
        seen.add(sector["id"])
        for pattern in sector["patterns"]:
            re.compile(pattern, re.IGNORECASE)
    return doc


@lru_cache(maxsize=1)
def _default_sectors() -> dict[str, Any]:
    return load_sectors()


@lru_cache(maxsize=None)
def _rules(drop_line: str, header: str, inline: str) -> tuple[re.Pattern, re.Pattern, re.Pattern]:
    flags = re.IGNORECASE
    return re.compile(drop_line, flags), re.compile(header, flags), re.compile(inline, flags)


@lru_cache(maxsize=None)
def _sector_regex(patterns: tuple[str, ...]) -> re.Pattern:
    """One compiled alternation per sector: the text is scanned once, not once per pattern."""
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


def strip_perks(clean: str, rules: Mapping[str, Any]) -> str:
    """Remove the lines that say what the employer OFFERS or must say by law, from cleaned text.

    Removed: equal-opportunity and discrimination lines; a line that starts with Benefits, Perks,
    "We offer" and similar; the bullet lines and short plain lines after a short header such as "Benefits:"
    (until a long line, a sentence that ends with a full stop, or a new header); and inline "Benefits: ..." / "Perks include ..." / "we offer ..." parts.
    """
    drop, header, inline = _rules(rules["drop_line"], rules["benefits_header"], rules["benefits_inline"])
    max_header = int(rules.get("section_max_header_chars", 60))
    max_item = int(rules.get("section_max_item_chars", 120))
    max_plain = int(rules.get("section_max_plain_chars", 80))
    kept: list[str] = []
    in_section = False
    for line in clean.split("\n"):
        text = line.strip()
        if not text:
            continue
        if drop.search(text):
            continue
        if header.match(text):
            in_section = len(text) <= max_header
            continue
        if in_section:
            bullet = text[0] in "*-•–—+>"
            if (bullet and len(text) <= max_item) or (len(text) <= max_plain and not text.endswith((".", ":"))):
                continue
            in_section = False
        kept.append(inline.sub(" ", text))
    return "\n".join(kept)


def sector_tags_clean(clean: str, sectors: Mapping[str, Any] | None = None) -> set[str]:
    """Sector ids for text that is already cleaned (see sector_tags)."""
    doc = sectors or _default_sectors()
    text = strip_perks(clean, doc["text_rules"])
    if not text:
        return set()
    return {
        s["id"] for s in doc["sectors"]
        if _has_real_match(_sector_regex(tuple(s["patterns"])), text)
    }


# A sector word inside a list is usually a customer list or a tag list ("serving pharma, energy and
# retail", "rockets, medical devices, robotics"), not what the employer does. Three shapes of list:
_LEAD_IN = re.compile(r"(?:\blike|such as|including|e\.g\.?|ranging from|across|spanning)\s*:?\s*$", re.IGNORECASE)
_ITEM_THEN_COMMA = re.compile(r"[\w/&+.-]+(?:\s[\w/&+.-]+)?\s*[,/]\s*(?:(?:and|or)\s+)?$")
_ITEM_THEN_END = re.compile(r"\s*(?:[,/.;]|\band\b|\bor\b|$)", re.IGNORECASE)
_TWO_MORE_ITEMS = re.compile(r"\s*,\s*[\w/&+.-]+(?:\s[\w/&+.-]+)?\s*,")
_NEIGHBOUR_CHARS = 60


def _in_list(text: str, match: re.Match) -> bool:
    """True when the match is an item of a list: after "like"/"such as", between short items, or first of 3+."""
    left = text[max(0, match.start() - 50):match.start()]
    right = text[match.end():match.end() + 50]
    if _LEAD_IN.search(left):
        return True
    if _ITEM_THEN_COMMA.search(left) and _ITEM_THEN_END.match(right):
        return True
    return bool(_TWO_MORE_ITEMS.match(right))


def _has_real_match(rx: re.Pattern, text: str) -> bool:
    """A match counts unless it sits in a list. A list of terms of the SAME sector ("hospitals,
    clinics and labs") counts: another match of this sector within a few words saves it."""
    matches = list(rx.finditer(text))
    for m in matches:
        if not _in_list(text, m):
            return True
        if any(o is not m and max(o.start() - m.end(), m.start() - o.end()) < _NEIGHBOUR_CHARS for o in matches):
            return True
    return False


def sector_tags(text: str, sectors: Mapping[str, Any] | None = None) -> set[str]:
    """The set of sector ids a job post describes. `text` is raw HN comment HTML or plain text.

    sectors: the load_sectors() document; the default is data/sdg_sectors.json.
    """
    if not text:
        return set()
    return sector_tags_clean(clean_text(text), sectors)


# ---------------------------------------------------------------- scan (one pass over the posts)

def scan_sdg(
    raw_dir: str | Path,
    threads: list[dict],
    roles: list[dict[str, Any]] | None,
    taxonomy: list[dict[str, Any]] | None,
    sectors: Mapping[str, Any],
) -> list[dict]:
    """Count sector tags per thread. One entry per thread, in the order given.

    {"thread_id", "month", "url", "n_posts", "sectors": {sector: posts}, "employers": {sector: {key}},
     "roles": {role_id: {"n": posts matching the role, "single": single-role posts,
                         "sectors": {sector: single-role posts}, "employers": {sector: {key}}}},
     "skills": {skill: {"n": posts mentioning it, "sectors": {sector: posts}, "employers": {sector: {key}}}}}
    roles=None skips the role part; taxonomy=None skips the skill part (much faster).
    "employers" holds an in-memory key per post (see employer_key). It is only counted, never written.
    """
    raw_dir = Path(raw_dir)
    patterns = compile_patterns(roles) if roles else {}
    out = []
    for thread in threads:
        n_posts = 0
        all_sectors: Counter = Counter()
        all_emp: dict[str, set] = {}
        role_n: Counter = Counter()
        role_single: Counter = Counter()
        role_sectors: dict[str, Counter] = {rid: Counter() for rid in patterns}
        role_emp: dict[str, dict[str, set]] = {rid: {} for rid in patterns}
        skill_n: Counter = Counter()
        skill_sectors: dict[str, Counter] = {}
        skill_emp: dict[str, dict[str, set]] = {}
        for text in _live_posts(_read_item(raw_dir, thread["thread_id"])):
            n_posts += 1
            clean = clean_text(text)
            tags = sector_tags_clean(clean, sectors)
            key = employer_key(clean) if tags else ""
            all_sectors.update(tags)
            _add_key(all_emp, tags, key)
            if patterns:
                rids = set(role_spans(clean, patterns))
                role_n.update(rids)
                if len(rids) == 1:
                    (rid,) = rids
                    role_single[rid] += 1
                    role_sectors[rid].update(tags)
                    _add_key(role_emp[rid], tags, key)
            if taxonomy is not None:
                for skill in tag_text(text, taxonomy):
                    skill_n[skill] += 1
                    skill_sectors.setdefault(skill, Counter()).update(tags)
                    _add_key(skill_emp.setdefault(skill, {}), tags, key)
        out.append({
            "thread_id": thread["thread_id"],
            "month": thread["month"],
            "url": thread["url"],
            "n_posts": n_posts,
            "sectors": dict(all_sectors),
            "employers": all_emp,
            "roles": {rid: {"n": role_n[rid], "single": role_single[rid], "sectors": dict(role_sectors[rid]),
                            "employers": role_emp[rid]}
                      for rid in patterns},
            "skills": {s: {"n": skill_n[s], "sectors": dict(skill_sectors[s]), "employers": skill_emp[s]}
                       for s in skill_n},
        })
    return out


_FIRST_SEGMENT = re.compile(r"\s*[|–—]\s*|\s+-\s+")


def employer_key(clean: str) -> str:
    """A rough key for who posted: the first segment of the first line, lowercased ("Acme | Remote" -> "acme").

    HN posters repeat their post every month, so one employer can fill many posts. The key is only
    used to COUNT distinct employers in memory. It is never written to any file.
    """
    for line in clean.split("\n"):
        if line.strip():
            return re.sub(r"[^a-z0-9]+", " ", _FIRST_SEGMENT.split(line.strip())[0].lower()).strip()[:40]
    return ""


def _add_key(target: dict[str, set], tags: Iterable[str], key: str) -> None:
    for sid in tags:
        target.setdefault(sid, set()).add(key)


def _employer_counts(parts: Iterable[Mapping[str, set]]) -> dict[str, int]:
    """sector -> number of different employer keys over several scan entries."""
    union: dict[str, set] = {}
    for part in parts:
        for sid, keys in part.items():
            union.setdefault(sid, set()).update(keys)
    return {sid: len(keys) for sid, keys in union.items()}


# ---------------------------------------------------------------- aggregation

def wilson_interval(count: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a share. None when n is 0."""
    if n <= 0:
        return None
    p = count / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _scan_threads(threads_csv: str | Path, months: int, as_of: str | None) -> list[dict]:
    """The threads a profile needs: the last 2 * months months up to as_of."""
    return _window(_read_threads(Path(threads_csv)), 2 * months, as_of)


def _split(scan: list[dict], months: int, as_of: str | None) -> tuple[list[dict], list[dict]]:
    """(recent, previous): the last `months` scanned months up to as_of, and the `months` before."""
    window = _window(scan, 2 * months, as_of)
    if not window:
        raise ValueError("no threads in the window")
    recent = window[-months:]
    return recent, window[: len(window) - len(recent)]


def _window_info(part: list[dict]) -> dict | None:
    if not part:
        return None
    return {"from": part[0]["month"], "to": part[-1]["month"], "months": len(part),
            "n_posts": sum(s["n_posts"] for s in part)}


def _share(count: int, n: int) -> float | None:
    return round(count / n, 6) if n else None


def _entity_doc(
    sector_ids: list[str],
    recent_counts: Mapping[str, int],
    prev_counts: Mapping[str, int],
    n_recent: int,
    n_prev: int,
    baseline: Mapping[str, Any] | None,
    examples: Mapping[str, list[str]] | None,
    employers: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Sector block for one role, one skill or the baseline.

    employers: sector -> number of different employers behind the recent posts (see employer_key).
    """
    sectors: dict[str, dict] = {}
    for sid in sector_ids:
        c_now, c_prev = recent_counts.get(sid, 0), prev_counts.get(sid, 0)
        share_now = _share(c_now, n_recent)
        n_emp = (employers or {}).get(sid, 0)
        entry: dict[str, Any] = {
            "count_recent": c_now,
            "employers_recent": n_emp,
            "share_recent": share_now,
            "count_prev": c_prev,
            "share_prev": _share(c_prev, n_prev),
        }
        ci = wilson_interval(c_now, n_recent)
        entry["ci95_recent"] = None if ci is None else [round(ci[0], 6), round(ci[1], 6)]
        if baseline is not None:
            base = baseline["sectors"][sid]["share_recent"]
            entry["lift"] = round(share_now / base, 4) if share_now is not None and base else None
            entry["reliable"] = n_recent >= MIN_N and n_emp >= MIN_EMPLOYERS
            entry["example_threads"] = list((examples or {}).get(sid, []))
        sectors[sid] = entry
    return {"n_recent": n_recent, "n_prev": n_prev, "sectors": sectors}


def _example_urls(recent: list[dict], counts_of) -> dict[str, list[str]]:
    """sector -> thread URLs (newest first, at most EXAMPLE_THREADS) where the entity has a tagged post."""
    found: dict[str, list[str]] = {}
    for s in reversed(recent):
        for sid, c in counts_of(s).items():
            if c and len(found.setdefault(sid, [])) < EXAMPLE_THREADS:
                found[sid].append(s["url"])
    return found


def _baseline(sector_ids: list[str], recent: list[dict], prev: list[dict]) -> dict:
    now, before = Counter(), Counter()
    for s in recent:
        now.update(s["sectors"])
    for s in prev:
        before.update(s["sectors"])
    return _entity_doc(sector_ids, now, before, sum(s["n_posts"] for s in recent),
                       sum(s["n_posts"] for s in prev), None, None,
                       _employer_counts(s["employers"] for s in recent))


def _meta(sectors: Mapping[str, Any], months: int, recent: list[dict], prev: list[dict], what: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": recent[-1]["month"],
        "months": months,
        "window": {"recent": _window_info(recent), "previous": _window_info(prev)},
        "sectors": [{"id": s["id"], "name": s["name"], "sdg": list(s["sdg"])} for s in sectors["sectors"]],
        "method": (f"Share of {what} in each sector, last {months} months against the {months} before. "
                   "Sector = regex patterns over post text (data/sdg_sectors.json), perks and legal lines "
                   "removed first. Baseline = all posts. lift = share / baseline share. "
                   f"reliable = at least {MIN_N} posts and {MIN_EMPLOYERS} different employers tagged in the sector. "
                   "employers_recent = distinct employers (first line of the post) behind the tagged posts; "
                   "ci95 = Wilson interval. Counts, shares and thread URLs only."),
    }


def role_sdg_profile(
    raw_dir: str | Path,
    threads_csv: str | Path,
    roles: list[dict[str, Any]],
    sectors: Mapping[str, Any],
    months: int = WINDOW_MONTHS,
    as_of: str | None = None,
    scan: list[dict] | None = None,
) -> dict:
    """The role_sdg.json document: per role, the share of its single-role posts in each sector.

    Windows: the last `months` months up to `as_of` (default: the latest thread), and the `months`
    before. Pass `scan` (from scan_sdg) to reuse a scan. Role "outlook" is the same trend as role_trends.json.
    {"as_of", "months", "window", "sectors": [{id, name, sdg}], "method", "baseline": {n_recent, n_prev,
     "sectors": {id: {...}}}, "roles": {role_id: {"name", "ranked", "n_recent", "n_prev", "n_role_posts_recent",
     "outlook", "sectors": {id: {count_recent, share_recent, count_prev, share_prev, ci95_recent, lift,
     reliable, example_threads}}}}}
    """
    if scan is None:
        scan = scan_sdg(raw_dir, _scan_threads(threads_csv, months, as_of), roles, None, sectors)
    recent, prev = _split(scan, months, as_of)
    ids = [s["id"] for s in sectors["sectors"]]
    baseline = _baseline(ids, recent, prev)
    demand_rows = [
        {"month": s["month"], "role_id": role["id"], "mentions": s["roles"][role["id"]]["n"],
         "n_posts": s["n_posts"]}
        for s in scan if as_of is None or s["month"] <= as_of
        for role in roles
    ]
    trends = build_role_trends(demand_rows, roles, as_of=as_of)["roles"]

    role_docs = {}
    for role in roles:
        rid = role["id"]
        now, before = Counter(), Counter()
        for s in recent:
            now.update(s["roles"][rid]["sectors"])
        for s in prev:
            before.update(s["roles"][rid]["sectors"])
        n_now = sum(s["roles"][rid]["single"] for s in recent)
        n_before = sum(s["roles"][rid]["single"] for s in prev)
        examples = _example_urls(recent, lambda s, rid=rid: s["roles"][rid]["sectors"])
        doc = _entity_doc(ids, now, before, n_now, n_before, baseline, examples,
                          _employer_counts(s["roles"][rid]["employers"] for s in recent))
        doc.update({
            "name": role["name"],
            "ranked": bool(role.get("ranked", True)),
            "n_role_posts_recent": sum(s["roles"][rid]["n"] for s in recent),
            "outlook": _outlook(trends[rid]),
        })
        role_docs[rid] = doc
    return {**_meta(sectors, months, recent, prev, "single-role posts"), "baseline": baseline, "roles": role_docs}


def _outlook(trend: Mapping[str, Any]) -> dict:
    """The keys of match_roles' role outlook, from one role_trends entry."""
    def share(m: Any, p: Any) -> float | None:
        return m / p if p else None

    return {
        "trend_label": trend.get("trend_label"),
        "mentions_last12": trend.get("mentions_last12"),
        "posts_last12": trend.get("posts_last12"),
        "mentions_prev12": trend.get("mentions_prev12"),
        "posts_prev12": trend.get("posts_prev12"),
        "share_last12": share(trend.get("mentions_last12"), trend.get("posts_last12")),
        "share_prev12": share(trend.get("mentions_prev12"), trend.get("posts_prev12")),
    }


def skill_sdg_profile(
    raw_dir: str | Path,
    threads_csv: str | Path,
    taxonomy: list[dict[str, Any]],
    sectors: Mapping[str, Any],
    months: int = WINDOW_MONTHS,
    as_of: str | None = None,
    scan: list[dict] | None = None,
) -> dict:
    """The skill_sdg.json document: per skill, the share of the posts that mention it in each sector.

    Same windows, baseline and fields as role_sdg_profile, with "skills" in place of "roles"
    (each skill has "n_recent", "n_prev" and "sectors"). No outlook.
    """
    if scan is None:
        scan = scan_sdg(raw_dir, _scan_threads(threads_csv, months, as_of), None, taxonomy, sectors)
    recent, prev = _split(scan, months, as_of)
    ids = [s["id"] for s in sectors["sectors"]]
    baseline = _baseline(ids, recent, prev)
    skill_docs = {}
    for entry in taxonomy:
        skill = entry["skill"]
        now, before = Counter(), Counter()
        n_now = n_before = 0
        for s in recent:
            rec = s["skills"].get(skill)
            if rec:
                n_now += rec["n"]
                now.update(rec["sectors"])
        for s in prev:
            rec = s["skills"].get(skill)
            if rec:
                n_before += rec["n"]
                before.update(rec["sectors"])
        examples = _example_urls(recent, lambda s, sk=skill: (s["skills"].get(sk) or {}).get("sectors", {}))
        employers = _employer_counts((s["skills"].get(skill) or {}).get("employers", {}) for s in recent)
        skill_docs[skill] = _entity_doc(ids, now, before, n_now, n_before, baseline, examples, employers)
    return {**_meta(sectors, months, recent, prev, "posts that mention the skill"),
            "baseline": baseline, "skills": skill_docs}


# ---------------------------------------------------------------- UI hooks

def _pct(x: float) -> str:
    return f"{100 * x:.0f}%" if x >= 0.095 else f"{100 * x:.1f}%"


def _sector_meta(role_sdg: Mapping[str, Any], goal_sector: str) -> dict:
    for s in role_sdg.get("sectors", []):
        if s["id"] == goal_sector:
            return s
    known = ", ".join(s["id"] for s in role_sdg.get("sectors", []))
    raise ValueError(f"unknown goal sector {goal_sector!r}; known: {known}")


def _role_entry(role_sdg: Mapping[str, Any], role: str) -> tuple[str, Mapping[str, Any]] | None:
    """(role_id, entry) for a role id or name (case-insensitive), else None."""
    roles = role_sdg.get("roles", {})
    if role in roles:
        return role, roles[role]
    wanted = role.strip().lower()
    for rid, entry in roles.items():
        if entry.get("name", "").lower() == wanted:
            return rid, entry
    return None


def goal_numbers(role_sdg: Mapping[str, Any], role_id: str, goal_sector: str) -> dict[str, Any] | None:
    """The numbers for one role and one goal sector, or None when the role has no entry.

    {"share", "baseline_share", "lift", "count", "employers", "n", "reliable", "months"}; share and lift can be None.
    """
    entry = role_sdg.get("roles", {}).get(role_id)
    if entry is None:
        return None
    sec = entry["sectors"][goal_sector]
    return {
        "share": sec["share_recent"],
        "baseline_share": role_sdg["baseline"]["sectors"][goal_sector]["share_recent"],
        "lift": sec["lift"],
        "count": sec["count_recent"],
        "employers": sec.get("employers_recent"),
        "n": entry["n_recent"],
        "reliable": bool(sec["reliable"]) and sec["count_recent"] >= MIN_SECTOR_POSTS,
        "months": role_sdg["months"],
    }


def _why_rough(nums: Mapping[str, Any]) -> str:
    """The real reason a cell is not a signal: only N role posts, only N posts in the sector, only N employers."""
    reasons = []
    if nums["n"] is not None and nums["n"] < MIN_N:
        reasons.append(f"only {nums['n']} role posts")
    if nums["count"] is not None and nums["count"] < MIN_SECTOR_POSTS:
        reasons.append(f"only {nums['count']} posts in the sector")
    if nums.get("employers") is not None and nums["employers"] < MIN_EMPLOYERS:
        reasons.append(f"only {nums['employers']} employers")
    return ", ".join(reasons) or "the cell is marked not reliable in role_sdg.json"


def _goal_sentence(nums: Mapping[str, Any] | None, sector_name: str) -> str:
    if nums is None or nums["share"] is None:
        return f"No {sector_name} data for this role: too few posts to measure."
    text = (f"{_pct(nums['share'])} of its posts are in {sector_name} "
            f"(baseline {_pct(nums['baseline_share'])})")
    if nums["lift"] is not None:
        text += f", {nums['lift']:.1f}x the baseline"
    text += f" ({nums['count']} of {nums['n']} posts)."
    if not nums["reliable"]:
        text += f" Too few to count as a signal: {_why_rough(nums)}."
    return text


def goal_multiplier(nums: Mapping[str, Any] | None) -> float:
    """1 + GOAL_WEIGHT * min(max(lift - 1, 0), MAX_EXCESS). It is 1.0 when there is no reliable lift."""
    if nums is None or not nums["reliable"] or nums["lift"] is None:
        return 1.0
    return 1.0 + GOAL_WEIGHT * min(max(nums["lift"] - 1.0, 0.0), MAX_EXCESS)


def rerank_for_goal(match_roles_output: Mapping[str, Any], role_sdg: Mapping[str, Any], goal_sector: str) -> dict:
    """Add a goal view to the match_roles result, and give an alternative order. Nothing is hidden.

    match_roles_output: the dict from engine.roles.match_roles (uses "roles" and "low_match").
    role_sdg: the role_sdg.json document. goal_sector: a sector id (see role_sdg["sectors"]).
    Raises ValueError for an unknown goal_sector.

    Returns {"goal_sector", "sector_name", "sdg", "formula",
      "roles":     match_roles "roles" in the ORIGINAL order, each a copy plus "sdg_goal",
      "low_match": match_roles "low_match", same order, each plus "sdg_goal",
      "by_goal_fit": [{"role_id", "name", "original_rank", "goal_rank", "rank_score",
                       "multiplier", "goal_fit_score"}]}   (ranked roles only, best first)
    "sdg_goal" = {"share", "baseline_share", "lift", "count", "n", "reliable", "months", "multiplier",
      "sentence"} (the sentence reads "X% of its posts are in <sector> (baseline Y%), Zx the baseline").
    A role with no entry in role_sdg keeps multiplier 1.0 and a "no data" sentence.
    The weight is team judgement, not fitted. Ties in goal_fit_score keep the original rank.
    """
    meta = _sector_meta(role_sdg, goal_sector)

    def annotate(role: Mapping[str, Any]) -> dict:
        nums = goal_numbers(role_sdg, role["role_id"], goal_sector)
        mult = goal_multiplier(nums)
        sdg_goal = dict(nums) if nums else {"share": None, "baseline_share": None, "lift": None,
                                            "count": None, "n": None, "reliable": False,
                                            "months": role_sdg.get("months")}
        sdg_goal.update({"multiplier": mult, "sentence": _goal_sentence(nums, meta["name"])})
        return {**role, "sdg_goal": sdg_goal}

    ranked = [annotate(r) for r in match_roles_output.get("roles", [])]
    low = [annotate(r) for r in match_roles_output.get("low_match", [])]
    order = sorted(
        ranked,
        key=lambda r: (-r["rank_score"] * r["sdg_goal"]["multiplier"], r.get("rank") or 0),
    )
    by_fit = [
        {
            "role_id": r["role_id"],
            "name": r["name"],
            "original_rank": r.get("rank"),
            "goal_rank": i,
            "rank_score": r["rank_score"],
            "multiplier": r["sdg_goal"]["multiplier"],
            "goal_fit_score": r["rank_score"] * r["sdg_goal"]["multiplier"],
        }
        for i, r in enumerate(order, start=1)
    ]
    return {
        "goal_sector": goal_sector,
        "sector_name": meta["name"],
        "sdg": list(meta["sdg"]),
        "formula": {
            "goal_fit_score": f"rank_score * (1 + {GOAL_WEIGHT} * min(max(lift - 1, 0), {MAX_EXCESS:g}))",
            "goal_weight": GOAL_WEIGHT,
            "max_excess": MAX_EXCESS,
            "lift": "share of the role's single-role posts in the sector / share of all posts in the sector",
            "reliable_only": f"lift counts only with at least {MIN_N} role posts, {MIN_SECTOR_POSTS} role posts in the sector "
                             f"and {MIN_EMPLOYERS} employers in the sector; "
                             "otherwise the multiplier is 1",
            "basis": "team judgement, not fitted: the weight and the cap are chosen by the team. "
                     "The original order and every role stay visible.",
        },
        "roles": ranked,
        "low_match": low,
        "by_goal_fit": by_fit,
    }


def role_reason(role_sdg: Mapping[str, Any], role_id: str) -> str | None:
    """One sentence on the role's most-linked sector, from role_sdg numbers only. None when there is no data."""
    entry = (role_sdg.get("roles") or {}).get(role_id)
    base = (role_sdg.get("baseline") or {}).get("sectors")
    if not entry or not base:
        return None
    names = {x["id"]: x for x in role_sdg.get("sectors", [])}
    cells = [(sid, c) for sid, c in entry["sectors"].items() if c.get("share_recent") is not None and sid in names]
    pool = [x for x in cells if x[1]["reliable"] and x[1]["count_recent"] >= MIN_SECTOR_POSTS] or cells
    if not pool:
        return None
    # Rank by share against all posts, so a sector that is big everywhere (health) does not win every role.
    sid, c = max(pool, key=lambda x: x[1]["share_recent"] / (base[x[0]]["share_recent"] or 1))
    rough = "" if c["reliable"] and c["count_recent"] >= MIN_SECTOR_POSTS else f" (few posts, n={c['count_recent']})"
    goals = " / ".join(names[sid]["sdg"])
    label = "Most over-represented sector" if c["share_recent"] > base[sid]["share_recent"] else "Main SDG-linked sector"
    return (f"{label}: {names[sid]['name']}, {_pct(c['share_recent'])} of posts in the last "
            f"{role_sdg.get('months', WINDOW_MONTHS)} months (SDG {goals}), against "
            f"{_pct(base[sid]['share_recent'])} of all posts{rough}.")


def goal_skills(taxonomy: Sequence[Mapping[str, Any]], role_sdg: Mapping[str, Any], goal_sector: str) -> set[str]:
    """Skills whose taxonomy SDG targets share a goal number (the part before the dot) with the sector."""
    goals = {t.split(".")[0] for t in _sector_meta(role_sdg, goal_sector)["sdg"]}
    return {t["skill"] for t in taxonomy if goals & {x.split(".")[0] for x in t.get("sdg", [])}}


def goal_first(steps: Sequence[Mapping[str, Any]], linked: set[str]) -> list[dict]:
    """Marks goalLinked and moves linked steps first inside each stage. Stages and their order stay as they are."""
    rank = {}
    for s in steps:
        rank.setdefault(s["stage"], len(rank))
    out = [{**s, "goalLinked": s["skill"] in linked} for s in steps]
    return sorted(out, key=lambda s: (rank[s["stage"]], not s["goalLinked"]))


def plan_sdg_summary(
    plan: Mapping[str, Any],
    role: str | Mapping[str, Any],
    role_sdg: Mapping[str, Any],
    goal_sector: str | None = None,
) -> dict:
    """Plan-level SDG sentences. Every number comes from the plan or from role_sdg.

    plan: an engine.pathway.build_pathway result. role: the role id or name, or a match_roles role
    result (its "outlook" is then used for the SDG 8.5 line). goal_sector: a sector id, or None.
    Returns {"lines": [str, ...], "numbers": {...}}.
    Lines: SDG 4.4 (skills added, hours); SDG 8.5 (role demand trend); and, with a goal sector,
    "N% of <role> posts in the last 12 months came from <sector> employers (SDG x.y), against Z% of all posts."
    """
    from engine.pathway import sdg_headline  # local import: pathway does not need this module

    role_id = role_name = None
    outlook = None
    if isinstance(role, Mapping):
        role_id, role_name, outlook = role.get("role_id"), role.get("name"), role.get("outlook")
    else:
        found = _role_entry(role_sdg, role)
        role_id = found[0] if found else None
        role_name = found[1].get("name") if found else role
    entry = role_sdg.get("roles", {}).get(role_id) if role_id else None
    if outlook is None and entry is not None:
        outlook = entry.get("outlook")
    role_name = role_name or plan.get("target_role")

    lines = sdg_headline(plan, outlook)
    numbers: dict[str, Any] = {
        "skills_added": sum(1 for s in plan["steps"] if s["resource"]),
        "hours": plan["totals"]["hours"],
        "role_demand": dict(outlook) if outlook else None,
        "goal": None,
    }
    if goal_sector is not None:
        meta = _sector_meta(role_sdg, goal_sector)
        nums = goal_numbers(role_sdg, role_id, goal_sector) if role_id else None
        targets = " / ".join(meta["sdg"])
        if nums is None or nums["share"] is None:
            lines.append(f"{meta['name']} (SDG {targets}): too few {role_name} posts in the last "
                         f"{role_sdg.get('months', WINDOW_MONTHS)} months to measure the sector share.")
        else:
            line = (f"{_pct(nums['share'])} of {role_name} posts in the last {nums['months']} months came from "
                    f"{meta['name']} employers (SDG {targets}), against {_pct(nums['baseline_share'])} "
                    f"of all posts ({nums['count']} of {nums['n']} posts).")
            if not nums["reliable"]:
                line += f" Rough, not a signal ({_why_rough(nums)}): treat it with care."
            lines.append(line)
        numbers["goal"] = nums
    return {"lines": lines, "numbers": numbers}


# ---------------------------------------------------------------- main

def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _print_table(doc: Mapping[str, Any], key: str, top: int = 3) -> None:
    base = doc["baseline"]["sectors"]
    names = {s["id"]: s["name"] for s in doc["sectors"]}
    print(f"baseline n={doc['baseline']['n_recent']} (last {doc['months']} months to {doc['as_of']})")
    for name, entry in doc[key].items():
        ranked = sorted(entry["sectors"].items(), key=lambda kv: -(kv[1]["share_recent"] or 0))[:top]
        parts = ", ".join(
            f"{names[sid]} {100 * (v['share_recent'] or 0):.1f}% (base {100 * (base[sid]['share_recent'] or 0):.1f}%)"
            for sid, v in ranked
        )
        print(f"{entry.get('name', name):<28} n={entry['n_recent']:<4} {parts}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build role_sdg.json and skill_sdg.json (sector shares).")
    ap.add_argument("--raw-dir", default=str(RAW_DIR), help="folder with <thread_id>.json files (local only)")
    ap.add_argument("--threads-csv", default=str(THREADS_CSV))
    ap.add_argument("--data-dir", default=str(DATA_DIR), help="where roles.json, taxonomy.json and the outputs live")
    ap.add_argument("--months", type=int, default=WINDOW_MONTHS)
    ap.add_argument("--as-of", default=None, help="last month to use, YYYY-MM (default: the latest thread)")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    sectors = load_sectors(data_dir / SECTORS_JSON.name)
    roles = load_roles(data_dir / ROLES_JSON.name)
    taxonomy = load_taxonomy(data_dir / "taxonomy.json")
    scan = scan_sdg(args.raw_dir, _scan_threads(args.threads_csv, args.months, args.as_of), roles, taxonomy, sectors)

    role_doc = role_sdg_profile(args.raw_dir, args.threads_csv, roles, sectors, args.months, args.as_of, scan=scan)
    skill_doc = skill_sdg_profile(args.raw_dir, args.threads_csv, taxonomy, sectors, args.months, args.as_of, scan=scan)
    _write_json(data_dir / ROLE_SDG_JSON.name, role_doc)
    _write_json(data_dir / SKILL_SDG_JSON.name, skill_doc)
    print("ROLES"); _print_table(role_doc, "roles")
    print("SKILLS"); _print_table(skill_doc, "skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
