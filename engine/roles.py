"""Role match (E7): learn what each role asks for from real job posts, then rank roles for a user.

Run: python -m engine.roles --raw-dir <folder with the raw HN thread JSON files>
It writes data/role_profiles.json, data/role_demand_monthly.csv and data/role_trends.json.

Three steps
1. learn_role_profiles: a post belongs to a role if its text matches the role's `title_pattern`
   (data/roles.json). For each role and skill:
       p_role = share of the role's posts that mention the skill
       p_all  = share of all posts in the window that mention it
       lift   = p_role / p_all
   Keep skills with p_role >= 0.08 and lift >= 1.2, take the top 10 by p_role, and set
   weight = p_role divided by the sum of the kept p_role values. Weights come from the posts.
   A role with fewer than 30 posts is marked "thin".
2. role_demand + build_role_trends: monthly share of posts that match each role, and the same
   Welch trend label used for skills (engine.forecast.trend_label): last 12 months against the
   12 before, p < 0.05, at least 30 mentions.
3. match_roles: for one user, per role
       match_score  = weight of the role's skills the user has / total weight (0 to 1)
       future_score = 1.0 Rising, 0.5 No clear change or unknown, 0.0 Falling
                      (fast scenario: +0.1 if most weight is on AI-complement skills,
                       -0.1 if most is on AI-substitutable skills; clipped to [0, 1])
       rank_score   = 0.7 * match_score + 0.3 * future_score
   The 0.7 / 0.3 split and the 0.1 adjustment are team judgement, not fitted. The output says so.

Counting rules follow engine.demand: top-level HN posts with text, not deleted, a post counts
at most once per skill and once per role. A post can match more than one role.
Outputs hold aggregates and thread ids only. No post text is ever written.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
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
SKILL_SCORES_JSON = DATA_DIR / "skill_scores.json"

# Profile learning (set before looking at results).
PROFILE_MONTHS = 24
MIN_P_ROLE = 0.08
MIN_LIFT = 1.2
TOP_K = 10
THIN_BELOW = 30  # fewer role posts than this -> "thin"

# Ranking: team judgement, not fitted. Shown in the app next to the score.
MATCH_WEIGHT = 0.7
FUTURE_WEIGHT = 0.3
FAST_ADJUSTMENT = 0.1
FUTURE_BY_TREND = {"Rising": 1.0, "No clear change": 0.5, "Falling": 0.0}
FUTURE_UNKNOWN = 0.5
SCENARIOS = ("moderate", "fast")

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


def matching_roles(text: str, patterns: Mapping[str, re.Pattern[str]]) -> set[str]:
    """Ids of the roles whose title pattern matches the post text (HTML cleaned first)."""
    if not text:
        return set()
    clean = clean_text(text)
    return {role_id for role_id, pat in patterns.items() if pat.search(clean)}


def _read_item(raw_dir: Path, thread_id: str) -> dict:
    return json.loads((raw_dir / f"{thread_id}.json").read_text(encoding="utf-8"))


def _window_threads(threads: list[dict], months: int, as_of: str | None) -> list[dict]:
    """The last `months` threads with month <= as_of (threads are sorted by month)."""
    if months < 1:
        raise ValueError("months must be at least 1")
    if as_of is not None:
        threads = [t for t in threads if t["month"] <= as_of]
    return threads[-months:]


# ---------------------------------------------------------------- 1. role profiles

def learn_role_profiles(
    raw_dir: str | Path,
    threads_csv: str | Path,
    taxonomy: list[dict[str, Any]],
    roles: list[dict[str, Any]],
    months: int = PROFILE_MONTHS,
    as_of: str | None = None,
) -> dict:
    """Learn each role's skill weights from the posts of the last `months` months up to `as_of`.

    Returns the role_profiles document (the caller writes it). It holds counts, shares and
    thread ids only.
    """
    raw_dir = Path(raw_dir)
    patterns = compile_patterns(roles)
    skills = [e["skill"] for e in taxonomy]
    window = _window_threads(_read_threads(Path(threads_csv)), months, as_of)
    if not window:
        raise ValueError("no threads in the window")

    n_all = 0
    all_counts = dict.fromkeys(skills, 0)
    n_role = dict.fromkeys(patterns, 0)
    role_counts = {rid: dict.fromkeys(skills, 0) for rid in patterns}
    role_threads: dict[str, set[str]] = {rid: set() for rid in patterns}

    for thread in window:
        for text in _live_posts(_read_item(raw_dir, thread["thread_id"])):
            tags = tag_text(text, taxonomy)
            n_all += 1
            for skill in tags:
                all_counts[skill] += 1
            for rid in matching_roles(text, patterns):
                n_role[rid] += 1
                role_threads[rid].add(thread["thread_id"])
                for skill in tags:
                    role_counts[rid][skill] += 1

    window_info = {"from": window[0]["month"], "to": window[-1]["month"], "months": len(window)}
    role_docs = []
    for role in roles:
        rid = role["id"]
        n = n_role[rid]
        kept = []
        for skill in skills:
            c = role_counts[rid][skill]
            if not c:
                continue
            p_role = c / n
            p_all = all_counts[skill] / n_all  # >= p_role * n / n_all > 0 because the role posts are in all posts
            lift = p_role / p_all
            if p_role >= MIN_P_ROLE - 1e-12 and lift >= MIN_LIFT - 1e-12:
                kept.append({"skill": skill, "p_role": p_role, "p_all": p_all, "lift": lift})
        kept.sort(key=lambda s: (-s["p_role"], s["skill"]))
        kept = kept[:TOP_K]
        total = sum(s["p_role"] for s in kept)
        skill_docs = [
            {
                "skill": s["skill"],
                "weight": round(s["p_role"] / total, 6),
                "p_role": round(s["p_role"], 6),
                "p_all": round(s["p_all"], 6),
                "lift": round(s["lift"], 4),
            }
            for s in kept
        ]
        thin = n < THIN_BELOW
        role_docs.append(
            {
                "role_id": rid,
                "name": role["name"],
                "description": role["description"],
                "sdg": list(role["sdg"]),
                "n_role_posts": n,
                "window": dict(window_info),
                "profile_status": "thin" if thin else "ok",
                "note": (
                    f"Thin profile: only {n} posts name this role in the window "
                    f"(fewer than {THIN_BELOW}). Treat the weights as rough."
                    if thin else None
                ),
                "skills": skill_docs,
                "thread_ids": sorted(role_threads[rid], key=int),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": window[-1]["month"],
        "window": window_info,
        "params": {
            "min_p_role": MIN_P_ROLE,
            "min_lift": MIN_LIFT,
            "top_k": TOP_K,
            "thin_below_posts": THIN_BELOW,
            "weight": "p_role / sum of kept p_role",
        },
        "n_posts_all": n_all,
        "thread_ids": [t["thread_id"] for t in window],
        "roles": role_docs,
    }


# ---------------------------------------------------------------- 2. role demand and trend

def role_demand(
    raw_dir: str | Path,
    threads_csv: str | Path,
    roles: list[dict[str, Any]],
    out_csv: str | Path | None = None,
) -> list[dict]:
    """Monthly share of posts that match each role, for every month in threads_csv.

    Columns: month, role_id, mentions, n_posts, share. mentions = posts that match the role
    (a post counts once per role). n_posts is counted as in engine.demand. Writes the CSV when
    out_csv is given, and returns the rows.
    """
    raw_dir = Path(raw_dir)
    patterns = compile_patterns(roles)
    rows: list[dict] = []
    for thread in _read_threads(Path(threads_csv)):
        counts = dict.fromkeys(patterns, 0)
        n_posts = 0
        for text in _live_posts(_read_item(raw_dir, thread["thread_id"])):
            n_posts += 1
            for rid in matching_roles(text, patterns):
                counts[rid] += 1
        for role in roles:
            rid = role["id"]
            rows.append(
                {
                    "month": thread["month"],
                    "role_id": rid,
                    "mentions": counts[rid],
                    "n_posts": n_posts,
                    "share": counts[rid] / n_posts if n_posts else 0.0,
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


def build_role_trends(
    demand_rows: list[dict],
    roles: list[dict[str, Any]],
    as_of: str | None = None,
    today: datetime | None = None,
) -> dict:
    """Welch trend label per role: the skill rule from engine.forecast.trend_label.

    Last 12 months against the 12 before, on the logit of the smoothed monthly share.
    Label is None when there are fewer than 24 months or fewer than 30 mentions in them.
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


def future_score(trend: str | None, weights_by_stance: Mapping[str, float], scenario: str) -> tuple[float, float]:
    """Return (future_score, scenario_adjustment).

    Base: Rising 1.0, No clear change 0.5, Falling 0.0, unknown 0.5. In the fast scenario,
    +0.1 if more than half of the role's weight is on AI-complement skills, -0.1 if more than
    half is on AI-substitutable skills. The result is clipped to [0, 1].
    """
    base = FUTURE_BY_TREND.get(trend, FUTURE_UNKNOWN) if trend else FUTURE_UNKNOWN
    adjustment = 0.0
    if scenario == "fast":
        if weights_by_stance.get("AI-complement", 0.0) > 0.5:
            adjustment = FAST_ADJUSTMENT
        elif weights_by_stance.get("AI-substitutable", 0.0) > 0.5:
            adjustment = -FAST_ADJUSTMENT
    return float(np.clip(base + adjustment, 0.0, 1.0)), adjustment


def _reason(name: str, have: list[dict], gap: list[dict], n_skills: int, trend: Mapping | None, status: str,
            n_posts: int) -> str:
    if n_skills == 0:
        return f"No skill profile for {name}: only {n_posts} matching posts."
    if have:
        shown = ", ".join(s["skill"] for s in have[:REASON_HAVE_SHOWN])
        text = f"You have {len(have)} of its top {n_skills} skills ({shown})."
    else:
        text = f"You have none of its top {n_skills} skills."
    if gap:
        text += " Biggest gaps: " + ", ".join(s["skill"] for s in gap[:REASON_GAPS_SHOWN]) + "."
    else:
        text += " No gaps among its top skills."
    label = trend.get("trend_label") if trend else None
    if label:
        text += f" Role demand: {label} ({trend['mentions_last12']} vs {trend['mentions_prev12']} posts)."
    else:
        text += " Role demand: too few posts to label a trend."
    if status == "thin":
        text += f" Thin profile: built from only {n_posts} posts."
    return text


def match_roles(
    user_skills: Iterable[str] | Mapping[str, Any],
    role_profiles: Any,
    skill_scores: Any,
    role_trends: Any,
    scenario: str = "moderate",
) -> dict:
    """Rank roles for one user. Nothing is written.

    user_skills: set of canonical skill names, or a dict skill -> years (years are only echoed).
    role_profiles: the role_profiles.json document (or its "roles" list).
    skill_scores: the skill_scores.json document (or its "skills" list).
    role_trends: the role_trends.json document (or its "roles" mapping).

    Returns {"scenario", "formula", "roles"}. "roles" is sorted by rank_score (ties: higher
    match_score, then name). Every role carries all parts of its score so the UI can explain it.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, got {scenario!r}")
    years = dict(user_skills) if isinstance(user_skills, Mapping) else {}
    have_set = set(user_skills)
    scores = {s["skill"]: s for s in _as_list(skill_scores, "skills")}
    trends = _trend_map(role_trends)

    results = []
    for prof in _as_list(role_profiles, "roles"):
        skills = sorted(prof["skills"], key=lambda s: (-s["weight"], s["skill"]))
        total = sum(s["weight"] for s in skills)

        def info(s: Mapping) -> dict:
            rec = scores.get(s["skill"]) or {}
            return {
                "skill": s["skill"],
                "weight": s["weight"],
                "status": rec.get("status"),
                "trend_label": rec.get("trend_label"),
                "stance": rec.get("stance"),
            }

        have = [{**info(s), "years": years.get(s["skill"])} for s in skills if s["skill"] in have_set]
        gap = [info(s) for s in skills if s["skill"] not in have_set]
        match = sum(s["weight"] for s in have) / total if total > 0 else 0.0

        by_stance: dict[str, float] = {}
        for s in skills:
            stance = (scores.get(s["skill"]) or {}).get("stance")
            if stance and total > 0:
                by_stance[stance] = by_stance.get(stance, 0.0) + s["weight"] / total
        trend = trends.get(prof["role_id"])
        fut, adjustment = future_score(trend.get("trend_label") if trend else None, by_stance, scenario)
        rank = MATCH_WEIGHT * match + FUTURE_WEIGHT * fut

        results.append(
            {
                "role_id": prof["role_id"],
                "name": prof["name"],
                "description": prof.get("description"),
                "sdg": prof.get("sdg", []),
                "profile_status": prof.get("profile_status"),
                "n_role_posts": prof.get("n_role_posts"),
                "match_score": match,
                "future_score": fut,
                "rank_score": rank,
                "scenario_adjustment": adjustment,
                "ai_stance_weights": {k: by_stance.get(k, 0.0) for k in ("AI-complement", "neutral", "AI-substitutable")},
                "outlook": {
                    "trend_label": trend.get("trend_label") if trend else None,
                    "trend_p": trend.get("trend_p") if trend else None,
                    "mentions_last12": trend.get("mentions_last12") if trend else None,
                    "mentions_prev12": trend.get("mentions_prev12") if trend else None,
                },
                "n_profile_skills": len(skills),
                "have": have,
                "gap": gap,
                "reason": _reason(prof["name"], have, gap, len(skills), trend, prof.get("profile_status", "ok"),
                                  prof.get("n_role_posts", 0)),
            }
        )

    results.sort(key=lambda r: (-r["rank_score"], -r["match_score"], r["name"]))
    for i, r in enumerate(results, start=1):
        r["rank"] = i
    return {
        "scenario": scenario,
        "formula": {
            "rank_score": f"{MATCH_WEIGHT} * match_score + {FUTURE_WEIGHT} * future_score",
            "match_weight": MATCH_WEIGHT,
            "future_weight": FUTURE_WEIGHT,
            "fast_adjustment": FAST_ADJUSTMENT,
            "future_by_trend": dict(FUTURE_BY_TREND, unknown=FUTURE_UNKNOWN),
            "basis": "team judgement: these constants are chosen by the team, not fitted to data",
        },
        "roles": results,
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
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    roles = load_roles(data_dir / ROLES_JSON.name)
    taxonomy = load_taxonomy(data_dir / "taxonomy.json")

    profiles = learn_role_profiles(args.raw_dir, args.threads_csv, taxonomy, roles, months=args.months)
    _write_json(data_dir / PROFILES_JSON.name, profiles)

    rows = role_demand(args.raw_dir, args.threads_csv, roles, out_csv=data_dir / ROLE_DEMAND_CSV.name)
    trends = build_role_trends(rows, roles)
    _write_json(data_dir / ROLE_TRENDS_JSON.name, trends)

    print(f"Profiles: {profiles['window']['from']}..{profiles['window']['to']}, {profiles['n_posts_all']} posts")
    for prof in profiles["roles"]:
        t = trends["roles"][prof["role_id"]]
        top = ", ".join(f"{s['skill']} {s['weight']:.2f}" for s in prof["skills"][:5])
        print(f"{prof['name']:<28} n={prof['n_role_posts']:<4} {prof['profile_status']:<5} "
              f"{str(t['trend_label']):<16} {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
