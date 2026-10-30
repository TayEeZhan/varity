"""Role match (E7): learn what each role asks for from real job posts, then rank roles for a user.

Run: python -m engine.roles --raw-dir <folder with the raw HN thread JSON files>
It writes data/role_profiles.json, data/role_demand_monthly.csv and data/role_trends.json.

Three steps
1. Role profiles. A post belongs to a role if its text matches the role's `title_pattern`
   (data/roles.json). Rules, each one fixing a measured problem:
   - Title masking: before tagging skills in a role post, the matched title span is replaced by
     spaces, so the title cannot create its own skill ("AI engineer" does not tag Machine Learning).
   - Single-role posts only: a post that names 2 or more roles tells us little about either one,
     so profiles are learned only from posts that match exactly ONE role.
   For each role and skill (single-role posts only for the role side):
       p_role = share of the role's single-role posts that mention the skill
       p_all  = share of all posts in the window that mention the skill (no masking)
       lift   = p_role / p_all
   Keep skills with p_role >= 0.08, lift >= 1.1 and at least 10 single-role posts (MIN_SKILL_POSTS).
   Take the top 10 by p_role. weight = p_role divided by the sum of the kept p_role values.
   Confidence tier: "solid" = at least 150 single-role posts AND at least 5 skills; "rough" = at least 50 posts; else "not_ranked".
   Profiles are computed at fixed as_of points, each from the 24 months up to that point, so the
   app's As-of slider never uses a profile that saw later posts (see profile_for).
2. Role demand. Monthly share of posts that match each role (every post that matches, single or
   not), with the same Welch trend label as skills (engine.forecast.trend_label).
3. match_roles. For one user, per role
       match_score = weight of the role's skills the user has / total weight (0 to 1)
       future_score = 1.0 Rising, 0.5 No clear change or unknown, 0.0 Falling (moderate trend)
       rank_score = 0.7 * match_score + 0.3 * future_score         (both scenarios)
   A role with match_score < 0.20 is not ranked: it goes to "low_match" so it cannot rank on outlook alone.
   The 0.7 / 0.3 split is team judgement, not fitted. The Fast scenario never changes the rank.
   It adds fast_shift = -k * sum(weight * e_s): how much the role's demand moves, as a fraction,
   if skills lose demand in line with their AI exposure (the skill rule fast = moderate * (1 - k * e_s)
   applied to the role's weights).

Counting rules follow engine.demand: top-level HN posts with text, not deleted; a post counts at
most once per skill and once per role. Outputs hold aggregates and thread ids only. No post text
is ever written.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

if __package__ in (None, ""):  # allow "python engine/roles.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.demand import RAW_DIR, THREADS_CSV, _live_posts, _read_threads  # noqa: E402
from engine.forecast import logit, smoothed_share, trend_label  # noqa: E402
from engine.tagging import clean_text, load_taxonomy, tag_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ROLES_JSON = DATA_DIR / "roles.json"
PROFILES_JSON = DATA_DIR / "role_profiles.json"
ROLE_DEMAND_CSV = DATA_DIR / "role_demand_monthly.csv"
ROLE_TRENDS_JSON = DATA_DIR / "role_trends.json"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"

# Profile learning (set before looking at results).
PROFILE_MONTHS = 24
MIN_P_ROLE = 0.08
MIN_LIFT = 1.1
MIN_SKILL_POSTS = 10  # a skill must appear in at least this many single-role posts
TOP_K = 10
SOLID_FROM = 150  # n_single_role_posts >= this AND SOLID_MIN_SKILLS skills: "solid"
SOLID_MIN_SKILLS = 5  # a profile with fewer skills than this is at best "rough"
ROUGH_FROM = 50  # n_single_role_posts >= this: "rough"; below: "not_ranked"
LOW_MATCH_BELOW = 0.20  # match_score below this: the role is not ranked (team judgement)
PROFILE_AS_OF_POINTS = ("2023-12", "2024-06", "2024-12", "2025-06", "2025-12", "2026-10")
SCHEMA_VERSION = 2

# Ranking: team judgement, not fitted. Shown in the app next to the score.
MATCH_WEIGHT = 0.7
FUTURE_WEIGHT = 0.3
FUTURE_BY_TREND = {"Rising": 1.0, "No clear change": 0.5, "Falling": 0.0}
FUTURE_UNKNOWN = 0.5
SCENARIOS = ("moderate", "fast")
DEFAULT_K = 2  # same assumption as engine.scores.K; match_roles reads k from skill_scores

# Having the key skill counts as having the value skill (the combined taxonomy row).
SYNONYMS = {"TypeScript": "JavaScript / TypeScript"}

DEMAND_COLUMNS = ["month", "role_id", "mentions", "n_posts", "share"]
REASON_HAVE_SHOWN = 4
REASON_GAPS_SHOWN = 3
ROLE_KEYS = ("id", "name", "title_pattern", "description", "sdg")


# ---------------------------------------------------------------- roles and posts

def load_roles(path: str | Path = ROLES_JSON) -> list[dict[str, Any]]:
    """Read data/roles.json and check each role has the needed keys and a valid regex."""
    roles = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(roles, list):
        raise ValueError(f"roles file must be a JSON list: {path}")
    seen: set[str] = set()
    for role in roles:
        missing = [k for k in ROLE_KEYS if k not in role]
        if missing:
            raise ValueError(f"role {role.get('id')!r} is missing {missing}")
        if role["id"] in seen:
            raise ValueError(f"duplicate role id {role['id']!r}")
        seen.add(role["id"])
        re.compile(role["title_pattern"])  # fail early on a bad pattern
    return roles


def compile_patterns(roles: Iterable[Mapping[str, Any]]) -> dict[str, re.Pattern[str]]:
    """role id -> compiled, case-insensitive title pattern."""
    return {r["id"]: re.compile(r["title_pattern"], re.IGNORECASE) for r in roles}


def role_spans(clean: str, patterns: Mapping[str, re.Pattern[str]]) -> dict[str, list[tuple[int, int]]]:
    """role id -> spans of its title matches in already-cleaned text. Roles with no match are left out."""
    spans = {}
    for role_id, pat in patterns.items():
        found = [m.span() for m in pat.finditer(clean)]
        if found:
            spans[role_id] = found
    return spans


def mask_spans(clean: str, spans: Iterable[tuple[int, int]]) -> str:
    """Replace each span with spaces of the same length (the title cannot create its own skill)."""
    chars = list(clean)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def matching_roles(text: str, patterns: Mapping[str, re.Pattern[str]]) -> set[str]:
    """Ids of the roles whose title pattern matches the post text (HTML cleaned first)."""
    if not text:
        return set()
    return set(role_spans(clean_text(text), patterns))


def tag_role_post(text: str, patterns: Mapping[str, re.Pattern[str]], taxonomy: list[dict]) -> tuple[set[str], set[str]]:
    """(role ids, skills tagged after masking the title) for one post.

    The skills are tagged on the text with every matched title span blanked out.
    """
    clean = clean_text(text)
    spans = role_spans(clean, patterns)
    if not spans:
        return set(), set()
    masked = mask_spans(clean, [s for sp in spans.values() for s in sp])
    return set(spans), tag_text(masked, taxonomy)


def _read_item(raw_dir: Path, thread_id: str) -> dict:
    return json.loads((raw_dir / f"{thread_id}.json").read_text(encoding="utf-8"))


def tier_for(n_single: int, n_skills: int) -> str:
    """Confidence tier from the single-role posts behind a profile and its number of skills.

    solid: at least 150 posts AND at least 5 skills. rough: at least 50 posts (a short profile
    with many posts is rough too). not_ranked: fewer than 50 posts.
    """
    if n_single >= SOLID_FROM and n_skills >= SOLID_MIN_SKILLS:
        return "solid"
    if n_single >= ROUGH_FROM:
        return "rough"
    return "not_ranked"


# ---------------------------------------------------------------- scan (one pass over the posts)

def scan_threads(
    raw_dir: str | Path,
    threads: list[dict],
    roles: list[dict[str, Any]],
    taxonomy: list[dict[str, Any]] | None = None,
    labels: Mapping[str, set[str]] | None = None,
) -> list[dict]:
    """Count posts per thread. One entry per thread, in the order given.

    labels (post id -> role ids, from engine.llm_labels) replaces the title regex for role counts.
    Every post must have a label, so one series never mixes two labellers. Only with taxonomy=None.

    {"thread_id", "month", "n_posts", "all": {skill: posts}, "roles": {role_id: {"n", "single",
    "skills": {skill: single-role posts}}}}.
    "all" counts every post (no masking). "n" counts posts that match the role, "single" those that
    match only this role, and "skills" the masked skills of those single-role posts.
    With taxonomy=None no skills are tagged (enough for role demand, and much faster).
    """
    raw_dir = Path(raw_dir)
    patterns = compile_patterns(roles)
    if labels is not None:
        if taxonomy is not None:
            raise ValueError("labels count roles only; profiles are learned with the title regex")
        return [_scan_labelled(raw_dir, t, patterns, labels) for t in threads]
    out = []
    for thread in threads:
        all_counts: Counter = Counter()
        role_n: Counter = Counter()
        role_single: Counter = Counter()
        role_skills: dict[str, Counter] = {rid: Counter() for rid in patterns}
        n_posts = 0
        for text in _live_posts(_read_item(raw_dir, thread["thread_id"])):
            n_posts += 1
            if taxonomy is None:
                rids = matching_roles(text, patterns)
                skills: set[str] = set()
            else:
                all_counts.update(tag_text(text, taxonomy))
                rids, skills = tag_role_post(text, patterns, taxonomy)
            for rid in rids:
                role_n[rid] += 1
            if len(rids) == 1:
                (rid,) = rids
                role_single[rid] += 1
                role_skills[rid].update(skills)
        out.append(
            {
                "thread_id": thread["thread_id"],
                "month": thread["month"],
                "n_posts": n_posts,
                "all": dict(all_counts),
                "roles": {
                    rid: {"n": role_n[rid], "single": role_single[rid], "skills": dict(role_skills[rid])}
                    for rid in patterns
                },
            }
        )
    return out


def _scan_labelled(raw_dir: Path, thread: dict, patterns: Mapping[str, Any], labels: Mapping[str, set[str]]) -> dict:
    """scan_threads entry for one thread, with role ids from the labels instead of the regex."""
    role_n: Counter = Counter()
    role_single: Counter = Counter()
    n_posts = 0
    for child in _read_item(raw_dir, thread["thread_id"]).get("children") or []:
        if child.get("deleted") or not (child.get("text") or "").strip():
            continue
        n_posts += 1
        pid = str(child["id"])
        if pid not in labels:
            raise ValueError(f"post {pid} of thread {thread['thread_id']} has no label")
        rids = labels[pid] & set(patterns)
        role_n.update(rids)
        if len(rids) == 1:
            role_single.update(rids)
    return {"thread_id": thread["thread_id"], "month": thread["month"], "n_posts": n_posts, "all": {},
            "roles": {rid: {"n": role_n[rid], "single": role_single[rid], "skills": {}} for rid in patterns}}


# ---------------------------------------------------------------- 1. role profiles

def _window(scan: list[dict], months: int, as_of: str | None) -> list[dict]:
    """The last `months` scanned threads with month <= as_of (the scan is in month order)."""
    if months < 1:
        raise ValueError("months must be at least 1")
    if as_of is not None:
        scan = [s for s in scan if s["month"] <= as_of]
    return scan[-months:]


def profile_from_scan(
    scan: list[dict],
    roles: list[dict[str, Any]],
    skills: list[str],
    months: int = PROFILE_MONTHS,
    as_of: str | None = None,
) -> dict:
    """One role_profiles entry (the window is the last `months` months up to `as_of`)."""
    window = _window(scan, months, as_of)
    if not window:
        raise ValueError("no threads in the window")
    n_all = sum(s["n_posts"] for s in window)
    all_counts = Counter()
    for s in window:
        all_counts.update(s["all"])
    window_info = {"from": window[0]["month"], "to": window[-1]["month"], "months": len(window)}

    role_docs = []
    for role in roles:
        rid = role["id"]
        n_role = sum(s["roles"][rid]["n"] for s in window)
        n_single = sum(s["roles"][rid]["single"] for s in window)
        counts: Counter = Counter()
        for s in window:
            counts.update(s["roles"][rid]["skills"])
        threads_used = sorted((s["thread_id"] for s in window if s["roles"][rid]["single"]), key=int)

        kept = []
        for skill in skills:
            c = counts[skill]
            if not c or c < MIN_SKILL_POSTS:
                continue
            p_role = c / n_single
            p_all = all_counts[skill] / n_all
            # p_all can be 0 only if masking made a skill appear in role posts that the unmasked
            # tagger did not see; it cannot happen, but guard the division.
            lift = p_role / p_all if p_all > 0 else float("inf")
            if p_role >= MIN_P_ROLE - 1e-12 and lift >= MIN_LIFT - 1e-12:
                kept.append({"skill": skill, "count": c, "p_role": p_role, "p_all": p_all, "lift": lift})
        kept.sort(key=lambda s: (-s["p_role"], s["skill"]))
        kept = kept[:TOP_K]
        total = sum(s["p_role"] for s in kept)
        skill_docs = [
            {
                "skill": s["skill"],
                "weight": round(s["p_role"] / total, 6),
                "p_role": round(s["p_role"], 6),
                "p_all": round(s["p_all"], 6),
                "lift": round(min(s["lift"], 1e6), 4),
                "single_role_posts": s["count"],
            }
            for s in kept
        ]
        tier = tier_for(n_single, len(skill_docs))
        ranked = bool(role.get("ranked", True))
        if not ranked:
            note = role.get("note") or "Not ranked."
        elif tier == "not_ranked":
            note = f"Not ranked: only {n_single} single-role posts (fewer than {ROUGH_FROM}) to learn a profile."
        elif tier == "rough" and n_single >= SOLID_FROM:
            k_found = len(skill_docs)
            note = (f"Rough profile: only {k_found} skill{'s' if k_found != 1 else ''} passed the filters "
                    f"(at least {SOLID_MIN_SKILLS} are needed). Treat the weights as approximate.")
        elif tier == "rough":
            note = (f"Rough profile: learned from {n_single} single-role posts "
                    f"(fewer than {SOLID_FROM}). Treat the weights as approximate.")
        else:
            note = None
        role_docs.append(
            {
                "role_id": rid,
                "name": role["name"],
                "description": role["description"],
                "sdg": list(role["sdg"]),
                "n_role_posts": n_role,
                "n_single_role_posts": n_single,
                "window": dict(window_info),
                "tier": tier,
                "ranked": ranked and tier != "not_ranked",
                "note": note,
                "skills": skill_docs,
                "thread_ids": threads_used,
            }
        )

    return {
        "as_of": window[-1]["month"],
        "window": window_info,
        "n_posts_all": n_all,
        "thread_ids": [s["thread_id"] for s in window],
        "roles": role_docs,
    }


def _profile_params() -> dict:
    return {
        "months": PROFILE_MONTHS,
        "min_p_role": MIN_P_ROLE,
        "min_lift": MIN_LIFT,
        "min_skill_posts": MIN_SKILL_POSTS,
        "top_k": TOP_K,
        "tiers": {"solid": f">= {SOLID_FROM} single-role posts and >= {SOLID_MIN_SKILLS} skills",
                  "rough": f">= {ROUGH_FROM} single-role posts (and not solid)",
                  "not_ranked": f"< {ROUGH_FROM} single-role posts"},
        "weight": "p_role / sum of kept p_role",
        "posts_used": "single-role posts only, title span masked before tagging skills",
    }


def learn_role_profiles(
    raw_dir: str | Path,
    threads_csv: str | Path,
    taxonomy: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    months: int = PROFILE_MONTHS,
    as_of: str | None = None,
) -> dict:
    """Learn each role's skill weights from the posts of the last `months` months up to `as_of`.

    Returns one profile (the caller writes it). It holds counts, shares and thread ids only.
    """
    threads = _read_threads(Path(threads_csv))
    window = _window(threads, months, as_of)
    if not window:
        raise ValueError("no threads in the window")
    scan = scan_threads(raw_dir, window, roles, taxonomy)
    return profile_from_scan(scan, roles, [e["skill"] for e in taxonomy], months, as_of)


def learn_profile_set(
    raw_dir: str | Path,
    threads_csv: str | Path,
    taxonomy: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    as_of_points: Iterable[str] = PROFILE_AS_OF_POINTS,
    months: int = PROFILE_MONTHS,
    scan: list[dict] | None = None,
) -> dict:
    """The role_profiles.json document: one profile per as_of point, keyed by as_of.

    Each profile uses the 24 months up to its own point. The posts are scanned once.
    Pass `scan` (from scan_threads with a taxonomy) to reuse a scan.
    """
    points = sorted(as_of_points)
    threads = [t for t in _read_threads(Path(threads_csv)) if t["month"] <= points[-1]]
    if scan is None:
        scan = scan_threads(raw_dir, threads, roles, taxonomy)
    skills = [e["skill"] for e in taxonomy]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "params": _profile_params(),
        "as_of_points": points,
        "profiles": {p: profile_from_scan(scan, roles, skills, months, p) for p in points},
    }


def profile_for(as_of: str, profiles_doc: Mapping[str, Any]) -> dict:
    """The latest profile whose as_of point is <= as_of (so it never saw later posts).

    Returns a copy of that profile with "requested_as_of" added. Its own "as_of" and "window"
    say which window it used. Raises ValueError if as_of is before the first point.
    """
    points = sorted(profiles_doc["profiles"])
    usable = [p for p in points if p <= as_of]
    if not usable:
        raise ValueError(f"no role profile on or before {as_of}; the first one is for {points[0]}")
    return {**profiles_doc["profiles"][usable[-1]], "requested_as_of": as_of}


# ---------------------------------------------------------------- 2. role demand and trend

def role_demand(
    raw_dir: str | Path,
    threads_csv: str | Path,
    roles: list[dict[str, Any]],
    out_csv: str | Path | None = None,
    scan: list[dict] | None = None,
) -> list[dict]:
    """Monthly share of posts that match each role, for every month in threads_csv.

    Columns: month, role_id, mentions, n_posts, share. mentions = posts in that month that match
    the role (single-role or not; a post counts once per role). n_posts is counted as in
    engine.demand. Writes the CSV when out_csv is given, and returns the rows.
    """
    if scan is None:
        scan = scan_threads(raw_dir, _read_threads(Path(threads_csv)), roles)
    rows: list[dict] = []
    for s in scan:
        for role in roles:
            n = s["roles"][role["id"]]["n"]
            rows.append(
                {
                    "month": s["month"],
                    "role_id": role["id"],
                    "mentions": n,
                    "n_posts": s["n_posts"],
                    "share": n / s["n_posts"] if s["n_posts"] else 0.0,
                }
            )
    if out_csv is not None:
        out = Path(out_csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=DEMAND_COLUMNS)
            writer.writeheader()
            for r in rows:
                writer.writerow({**r, "share": f"{r['share']:.6f}"})
    return rows


def read_demand_rows(path: str | Path = ROLE_DEMAND_CSV) -> list[dict]:
    """Read role_demand_monthly.csv back as rows with int counts."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return [
            {"month": r["month"], "role_id": r["role_id"], "mentions": int(r["mentions"]),
             "n_posts": int(r["n_posts"]), "share": float(r["share"])}
            for r in csv.DictReader(fh)
        ]


def build_role_trends(
    demand_rows: list[dict],
    roles: list[dict[str, Any]],
    as_of: str | None = None,
    today: datetime | None = None,
) -> dict:
    """Welch trend label per role: the skill rule from engine.forecast.trend_label.

    Last 12 months against the 12 before, on the logit of the smoothed monthly share. Only rows with
    month <= as_of are used, so a past as_of never sees later data. Label is None when there are
    fewer than 24 months or fewer than 30 mentions in them.
    """
    today = today or datetime.now(timezone.utc)
    months = sorted({r["month"] for r in demand_rows if as_of is None or r["month"] <= as_of})
    if not months:
        raise ValueError("no demand rows on or before as_of")
    month_set = set(months)
    by_role: dict[str, dict[str, tuple[int, int]]] = {}
    for r in demand_rows:
        if r["month"] in month_set:
            by_role.setdefault(r["role_id"], {})[r["month"]] = (int(r["mentions"]), int(r["n_posts"]))

    out: dict[str, dict] = {}
    for role in roles:
        series = by_role.get(role["id"], {})
        m = np.array([series[mo][0] for mo in months if mo in series], dtype=float)
        p = np.array([series[mo][1] for mo in months if mo in series], dtype=float)
        y = logit(smoothed_share(m, p)) if m.size else np.array([])
        label, pval = trend_label(y, m)
        out[role["id"]] = {
            "trend_label": label,
            "trend_p": None if pval is None else float(pval),
            "mentions_last12": int(m[-12:].sum()),
            "posts_last12": int(p[-12:].sum()),
            "mentions_prev12": int(m[-24:-12].sum()),
            "posts_prev12": int(p[-24:-12].sum()),
        }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": months[-1],
        "partial_month": months[-1] == today.strftime("%Y-%m"),
        "method": "Welch t-test on the monthly logit share, last 12 months against the 12 before; "
                  "p < 0.05 and at least 30 mentions in the 24 months, as for skills.",
        "roles": out,
    }


# ---------------------------------------------------------------- 3. match

def _as_list(doc: Any, key: str) -> list:
    return doc[key] if isinstance(doc, Mapping) else list(doc)


def _trend_map(role_trends: Any) -> Mapping[str, Mapping]:
    """Accept the role_trends.json document or just its "roles" mapping."""
    if isinstance(role_trends, Mapping) and isinstance(role_trends.get("roles"), Mapping):
        return role_trends["roles"]
    return role_trends or {}


def load_exposure(path: str | Path = EXPOSURE_CSV) -> dict[str, float]:
    """skill -> e_s (AI exposure minus the mean over the taxonomy) from exposure.csv."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return {r["skill"]: float(r["e_s"]) for r in csv.DictReader(fh)}


def _user_set(user_skills: Any) -> tuple[set[str], dict[str, Any]]:
    """(skill names, years by skill). A plain string is a mistake: iterating it gives letters."""
    if isinstance(user_skills, (str, bytes)):
        raise TypeError("user_skills must be a set of skill names or a dict skill -> years, not a string")
    if isinstance(user_skills, Mapping):
        return set(user_skills), dict(user_skills)
    return set(user_skills), {}


def merge_synonyms(skills: list[Mapping]) -> list[dict]:
    """Merge a synonym row into its combined row when a profile has both (weights add up)."""
    by_name = {s["skill"]: dict(s) for s in skills}
    for child, parent in SYNONYMS.items():
        if child in by_name and parent in by_name:
            by_name[parent]["weight"] = by_name[parent]["weight"] + by_name[child]["weight"]
            by_name[parent]["merged_from"] = [child]
            del by_name[child]
    return list(by_name.values())


def future_score(trend: str | None) -> float:
    """Rising 1.0, No clear change 0.5, Falling 0.0, unknown 0.5. Same in both scenarios."""
    return FUTURE_BY_TREND.get(trend, FUTURE_UNKNOWN) if trend else FUTURE_UNKNOWN


def score_breakdown(r: Mapping, top: int = 3) -> dict:
    """The parts of one match_roles result, and what each of the top gap skills would add. Pure arithmetic."""
    total = sum(s["weight"] for s in r["have"]) + sum(s["weight"] for s in r["gap"])  # merge_synonyms already applied
    fut = r["future_score"]
    gaps = sorted(r["gap"], key=lambda s: (-s["weight"], s["skill"]))[:top]
    raise_ = [{"skill": s["skill"], "addMatch": add, "newRank": MATCH_WEIGHT * (r["match_score"] + add) + FUTURE_WEIGHT * fut}
              for s in gaps for add in [s["weight"] / total if total > 0 else 0.0]]
    return {"match": r["match_score"], "outlook": fut, "matchWeight": MATCH_WEIGHT, "outlookWeight": FUTURE_WEIGHT,
            "rank": r["rank_score"], "raise": raise_}


def _share(mentions: Any, posts: Any) -> float | None:
    if isinstance(mentions, (int, float)) and isinstance(posts, (int, float)) and posts:
        return mentions / posts
    return None


def _reason(name: str, have: list[dict], gap: list[dict], n_skills: int, outlook: Mapping, tier: str | None,
            n_single: int) -> str:
    if n_skills == 0:
        return f"No skill profile for {name}: only {n_single} single-role posts."
    if have:
        shown = ", ".join(s["skill"] for s in have[:REASON_HAVE_SHOWN])
        text = f"You have {len(have)} of its top {n_skills} skills ({shown})."
    else:
        text = f"You have none of its top {n_skills} skills."
    if gap:
        text += " Biggest gaps: " + ", ".join(s["skill"] for s in gap[:REASON_GAPS_SHOWN]) + "."
    else:
        text += " No gaps among its top skills."
    label = outlook.get("trend_label")
    now, before = outlook.get("share_last12"), outlook.get("share_prev12")
    if label and now is not None and before is not None:
        text += f" Role demand: {label} ({now:.1%} of posts vs {before:.1%} the year before)."
    elif label:
        text += f" Role demand: {label}."
    else:
        text += " Role demand: too few posts to label a trend."
    if tier == "rough":
        text += f" Rough profile: learned from {n_single} single-role posts."
    return text


def match_roles(
    user_skills: Iterable[str] | Mapping[str, Any],
    role_profiles: Any,
    skill_scores: Any,
    role_trends: Any,
    scenario: str = "moderate",
    exposure: Mapping[str, float] | None = None,
    k: float | None = None,
    low_match_below: float = LOW_MATCH_BELOW,
) -> dict:
    """Rank roles for one user. Nothing is written.

    user_skills: set (or list) of canonical skill names, or a dict skill -> years. A plain string
        raises TypeError. Having "TypeScript" counts as having "JavaScript / TypeScript".
    role_profiles: ONE profile (from profile_for, or a role_profiles entry) or its "roles" list.
    skill_scores: the skill_scores.json document (or its "skills" list).
    role_trends: the role_trends.json document (or its "roles" mapping), cut at the right as_of.
    scenario: "moderate" or "fast". Both give the same rank. The Fast scenario only changes the
        fast_shift the UI shows.
    exposure: skill -> e_s (use load_exposure). Default: ai_exposure in skill_scores minus its mean,
        which is how exposure.csv defines e_s.
    k: Fast strength. Default: skill_scores["scenario_params"]["k"], else 2.

    low_match_below: a role whose match_score is below this goes to "low_match" and is NOT ranked, so a
        role cannot rank on its outlook alone. Default 0.20 (team judgement). Use 0 to rank every role.

    Returns {"scenario", "formula", "roles", "low_match", "not_ranked", "unmatched"}. "roles" holds the
    roles with match_score >= low_match_below, sorted by rank_score (ties: higher match_score, then
    name), each with a "rank". "low_match" holds the others, sorted by match_score (highest first),
    with rank None. Every role carries all parts of its score. "roles" may be empty.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, got {scenario!r}")
    names, years = _user_set(user_skills)
    score_list = _as_list(skill_scores, "skills")
    scores = {s["skill"]: s for s in score_list}
    have_set = set(names)
    for child, parent in SYNONYMS.items():
        if child in have_set:
            have_set.add(parent)
    unmatched = sorted(n for n in names if n not in scores)

    if k is None:
        params = skill_scores.get("scenario_params") if isinstance(skill_scores, Mapping) else None
        k = (params or {}).get("k", DEFAULT_K)
    if exposure is None:
        exps = {s["skill"]: s.get("ai_exposure") for s in score_list if s.get("ai_exposure") is not None}
        mean = sum(exps.values()) / len(exps) if exps else 0.0
        exposure = {name: value - mean for name, value in exps.items()}
    trends = _trend_map(role_trends)

    profiles = role_profiles["roles"] if isinstance(role_profiles, Mapping) else list(role_profiles)
    results, not_ranked = [], []
    for prof in profiles:
        if prof.get("ranked") is False or prof.get("tier") == "not_ranked":
            not_ranked.append({"role_id": prof["role_id"], "name": prof["name"], "tier": prof.get("tier"),
                               "n_single_role_posts": prof.get("n_single_role_posts"), "note": prof.get("note")})
            continue
        skills = sorted(merge_synonyms(prof["skills"]), key=lambda s: (-s["weight"], s["skill"]))
        total = sum(s["weight"] for s in skills)

        def info(s: Mapping) -> dict:
            rec = scores.get(s["skill"]) or {}
            return {"skill": s["skill"], "weight": s["weight"], "status": rec.get("status"),
                    "trend_label": rec.get("trend_label"), "stance": rec.get("stance")}

        have = [{**info(s), "years": years.get(s["skill"])} for s in skills if s["skill"] in have_set]
        gap = [info(s) for s in skills if s["skill"] not in have_set]
        match = sum(s["weight"] for s in have) / total if total > 0 else 0.0

        by_stance: dict[str, float] = {}
        for s in skills:
            stance = (scores.get(s["skill"]) or {}).get("stance")
            if stance and total > 0:
                by_stance[stance] = by_stance.get(stance, 0.0) + s["weight"] / total
        fast_shift = (-k * sum(s["weight"] / total * exposure.get(s["skill"], 0.0) for s in skills)
                      if total > 0 else 0.0)

        trend = trends.get(prof["role_id"]) or {}
        label = trend.get("trend_label")
        outlook = {
            "trend_label": label,
            "trend_p": trend.get("trend_p"),
            "mentions_last12": trend.get("mentions_last12"),
            "mentions_prev12": trend.get("mentions_prev12"),
            "posts_last12": trend.get("posts_last12"),
            "posts_prev12": trend.get("posts_prev12"),
            "share_last12": _share(trend.get("mentions_last12"), trend.get("posts_last12")),
            "share_prev12": _share(trend.get("mentions_prev12"), trend.get("posts_prev12")),
        }
        fut = future_score(label)
        rank = MATCH_WEIGHT * match + FUTURE_WEIGHT * fut
        n_single = prof.get("n_single_role_posts", 0)
        tier = prof.get("tier")
        results.append(
            {
                "role_id": prof["role_id"],
                "name": prof["name"],
                "description": prof.get("description"),
                "sdg": prof.get("sdg", []),
                "tier": tier,
                "tier_note": prof.get("note"),
                "n_role_posts": prof.get("n_role_posts"),
                "n_single_role_posts": n_single,
                "match_score": match,
                "future_score": fut,
                "rank_score": rank,
                "fast_shift": fast_shift,
                "ai_stance_weights": {s: by_stance.get(s, 0.0) for s in ("AI-complement", "neutral", "AI-substitutable")},
                "outlook": outlook,
                "n_profile_skills": len(skills),
                "have": have,
                "gap": gap,
                "reason": _reason(prof["name"], have, gap, len(skills), outlook, tier, n_single),
            }
        )

    low_match = sorted((r for r in results if r["match_score"] < low_match_below),
                       key=lambda r: (-r["match_score"], r["name"]))
    for r in low_match:
        r["rank"] = None
    results = [r for r in results if r["match_score"] >= low_match_below]
    results.sort(key=lambda r: (-r["rank_score"], -r["match_score"], r["name"]))
    for i, r in enumerate(results, start=1):
        r["rank"] = i
    return {
        "scenario": scenario,
        "formula": {
            "rank_score": f"{MATCH_WEIGHT} * match_score + {FUTURE_WEIGHT} * future_score",
            "match_weight": MATCH_WEIGHT,
            "future_weight": FUTURE_WEIGHT,
            "future_by_trend": dict(FUTURE_BY_TREND, unknown=FUTURE_UNKNOWN),
            "fast_shift": "-k * sum(weight * e_s) over the role's skills, as a fraction of role demand; "
                          "shown for the Fast scenario only and never used in rank_score",
            "k": k,
            "low_match_below": low_match_below,
            "low_match": "a role with match_score below low_match_below is listed in low_match and not ranked, "
                         "so it cannot rank on its outlook alone",
            "basis": "team judgement: 0.7 / 0.3, the trend scores and the 0.20 low-match limit are chosen by "
                     "the team, not fitted to data",
        },
        "roles": results,
        "low_match": low_match,
        "not_ranked": not_ranked,
        "unmatched": unmatched,
    }


# ---------------------------------------------------------------- main

def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build role profiles, role demand and role trends.")
    ap.add_argument("--raw-dir", default=str(RAW_DIR), help="folder with <thread_id>.json files (local only)")
    ap.add_argument("--threads-csv", default=str(THREADS_CSV))
    ap.add_argument("--data-dir", default=str(DATA_DIR), help="where roles.json and the outputs live")
    ap.add_argument("--months", type=int, default=PROFILE_MONTHS)
    ap.add_argument("--as-of", action="append", help="profile as_of point (repeatable); default: the 6 standard points")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    roles = load_roles(data_dir / ROLES_JSON.name)
    taxonomy = load_taxonomy(data_dir / "taxonomy.json")
    threads = _read_threads(Path(args.threads_csv))

    points = args.as_of or list(PROFILE_AS_OF_POINTS)
    scan = scan_threads(args.raw_dir, threads, roles, taxonomy)  # one pass: profiles and demand
    profiles = learn_profile_set(args.raw_dir, args.threads_csv, taxonomy, roles, points, args.months,
                                 scan=[s for s in scan if s["month"] <= max(points)])
    _write_json(data_dir / PROFILES_JSON.name, profiles)

    rows = role_demand(args.raw_dir, args.threads_csv, roles, out_csv=data_dir / ROLE_DEMAND_CSV.name, scan=scan)
    trends = build_role_trends(rows, roles)
    _write_json(data_dir / ROLE_TRENDS_JSON.name, trends)

    latest = profiles["profiles"][profiles["as_of_points"][-1]]
    print(f"Profiles at {', '.join(profiles['as_of_points'])}. Latest window "
          f"{latest['window']['from']}..{latest['window']['to']}, {latest['n_posts_all']} posts")
    for prof in latest["roles"]:
        t = trends["roles"][prof["role_id"]]
        top = ", ".join(f"{s['skill']} {s['weight']:.2f}" for s in prof["skills"][:5])
        print(f"{prof['name']:<28} all={prof['n_role_posts']:<4} single={prof['n_single_role_posts']:<4} "
              f"{prof['tier']:<10} {str(t['trend_label']):<16} {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
