"""Reskilling pathway engine (task E8).

Turns the skill gap for a target role into an ordered pathway, a dated daily to-do list,
progress tracking and exports (Markdown, iCalendar).

Rules that matter (see docs/pathway.md):
  * The order is set by code from dated data. No language model touches it.
  * A resource comes only from data/resources.json, and only if its link was checked
    (HTTP 200). A skill with no such resource gets the placeholder PLACEHOLDER_RESOURCE.
    The engine never makes up a course, a link or an HRD Corp claim.
  * All times are estimates. Scenario "fast" is an assumption, not a forecast.

The role-match engine (another branch) supplies `gap`: a list of
{skill, weight, status, trend_label, stance}, ordered by weight. This module only reads
those keys, so it does not import the roles module.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SCENARIOS = ("moderate", "fast")
MAX_TASK_MINUTES = 45
MIN_FRAGMENT_MINUTES = 10
WORK_DAYS_PER_WEEK = 5
NO_REGRET_MIN_ROLES = 2
MYT = timezone(timedelta(hours=8))  # Malaysia time, UTC+8, no daylight saving
PLACEHOLDER_RESOURCE = "No verified free resource yet"

HRD_CORP_NOTE = ("HRD Corp-claimable status not verified for these resources; "
                 "check https://hrdcorp.gov.my before claiming.")
ESTIMATE_NOTE = ("All times are estimates by the Verity team. The Fast scenario changes only "
                 "the order of the stages. It is an assumption, not a forecast.")

STAGE_LABELS = {
    "no_regret": "Stage 1: no-regret (needed by 2 or more of your roles, not falling, not AI-substitutable)",
    "near_term": "Stage 2: near-term demand (highest share of job posts among your gap skills)",
    "other": "Also in the gap (no strong trend or demand signal)",
    "future_bet": "Stage 3: future bet (rising, or AI-complement)",
}
STAGE_ORDER = {
    "moderate": ("no_regret", "near_term", "other", "future_bet"),
    "fast": ("no_regret", "future_bet", "near_term", "other"),
}


# ---------------------------------------------------------------- loading helpers

def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_resources(path: Path | str | None = None) -> dict[str, Any]:
    """Load data/resources.json (an object with a "resources" list)."""
    return _load_json(Path(path) if path else DATA_DIR / "resources.json")


def load_taxonomy(path: Path | str | None = None) -> list[dict[str, Any]]:
    return _load_json(Path(path) if path else DATA_DIR / "taxonomy.json")


def load_skill_scores(path: Path | str | None = None) -> dict[str, Any]:
    return _load_json(Path(path) if path else DATA_DIR / "skill_scores.json")


def _skill_index(skill_scores: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, dict]:
    records = skill_scores.get("skills", []) if isinstance(skill_scores, Mapping) else skill_scores
    return {r["skill"]: dict(r) for r in records}


def _resource_index(resources: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, list[dict]]:
    """Group usable resources by skill. A usable resource has an https URL and check_status 200."""
    records = resources.get("resources", []) if isinstance(resources, Mapping) else resources
    index: dict[str, list[dict]] = {}
    for rec in records:
        url = str(rec.get("url", ""))
        if not url.startswith("https://") or rec.get("check_status") != 200:
            continue
        if not isinstance(rec.get("minutes"), int) or rec["minutes"] <= 0:
            continue
        index.setdefault(rec["skill"], []).append(dict(rec))
    return index


def today_myt() -> date:
    """Today's date in Malaysia (UTC+8). Early morning in Malaysia is still yesterday in UTC."""
    return datetime.now(MYT).date()


def tasks_signature(tasks: Iterable[Mapping[str, Any]]) -> str:
    """Short hash of a task list (id, title and date of every task).

    Two plans share a signature only when all their tasks are the same, so it is safe as a key
    for ticks and as part of a calendar UID.
    """
    text = "\n".join(f"{t['id']}|{t['title']}|{t['date']}" for t in tasks)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _as_date(value: date | datetime | str | None) -> date:
    if value is None:
        return today_myt()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _next_workday(day: date) -> date:
    while day.weekday() >= WORK_DAYS_PER_WEEK:
        day += timedelta(days=1)
    return day


# ---------------------------------------------------------------- staging

def _gap_list(item: Any) -> list[dict]:
    """Accept a gap list, or a role result that has a "gap" key."""
    if isinstance(item, Mapping):
        item = item.get("gap", [])
    return list(item)


def _dedupe_gap(gap: Iterable[Mapping[str, Any]]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for g in gap:
        if g["skill"] not in seen:
            seen.add(g["skill"])
            out.append(dict(g))
    return out


def _role_counts(gap_skills: Iterable[str], role_gaps: Any) -> tuple[dict[str, int], int]:
    """How many of the given roles have each skill in their gap. Every given role is counted."""
    if isinstance(role_gaps, Mapping):
        role_gaps = list(role_gaps.values())
    roles = [{g["skill"] for g in _gap_list(item)} for item in list(role_gaps or [])]
    return {s: sum(s in r for r in roles) for s in gap_skills}, len(roles)


def classify(gap: Sequence[Mapping[str, Any]], role_gaps: Any,
             skill_scores: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, dict]:
    """Assign each gap skill to a stage. Returns {skill: {"stage", "roles_needing", "roles_total"}}.

    `role_gaps` holds the gap of the target role and of every ranked role (one list per role, the
    target counted once). A skill is no-regret when it is in the gap of 2 or more of them, its trend is
    not "Falling" and its stance is not "AI-substitutable". Near-term is relative: the top half of
    the gap skills by share now.

    Precedence when a skill fits several stages: no_regret, then near_term, then future_bet.
    A skill that fits none is "other".
    """
    gap = _dedupe_gap(gap)
    scores = _skill_index(skill_scores)
    counts, n_roles = _role_counts([g["skill"] for g in gap], role_gaps)

    # Near-term: status ok and share-now in the top half of the gap skills (by share).
    def share(skill: str) -> float:
        value = scores.get(skill, {}).get("demand_share_latest")
        return float(value) if value is not None else -1.0

    ranked = sorted(gap, key=lambda g: -share(g["skill"]))  # stable: ties keep gap order
    top_half = {g["skill"] for g in ranked[:math.ceil(len(ranked) / 2)]}

    out: dict[str, dict] = {}
    for g in gap:
        skill = g["skill"]
        trend = g.get("trend_label")
        if (counts[skill] >= NO_REGRET_MIN_ROLES and trend != "Falling"
                and g.get("stance") != "AI-substitutable"):
            stage = "no_regret"
        elif g.get("status") == "ok" and skill in top_half and share(skill) >= 0:
            stage = "near_term"
        elif trend == "Rising" or g.get("stance") == "AI-complement":
            stage = "future_bet"
        else:
            stage = "other"
        out[skill] = {"stage": stage, "roles_needing": counts[skill], "roles_total": n_roles}
    return out


def _share_pair(rec: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        return (rec["mentions_last12"] / rec["posts_last12"],
                rec["mentions_prev12"] / rec["posts_prev12"])
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def _reason(stage: str, g: Mapping[str, Any], rec: Mapping[str, Any], info: Mapping[str, Any],
            role: str) -> str:
    skill = g["skill"]
    trend = g.get("trend_label")
    if stage == "no_regret":
        return (f"Needed by {info['roles_needing']} of the {info['roles_total']} roles counted "
                f"(your target and your ranked roles); trend: {trend or 'not enough data'}, "
                f"so it is not Falling.")
    if stage == "near_term":
        share = rec.get("demand_share_latest")
        return (f"Demand now: {100 * share:.1f}% of recent job posts mention it, in the top half "
                f"of your gap skills (relative to your gap, not a fixed level).")
    if stage == "future_bet":
        pair = _share_pair(rec)
        if trend == "Rising" and pair:
            return f"Rising: {100 * pair[0]:.1f}% of posts vs {100 * pair[1]:.1f}% in the 12 months before."
        if trend == "Rising":
            return "Rising (tested trend over the last 12 months)."
        exposure = rec.get("ai_exposure")
        extra = f" (AI exposure {100 * exposure:.0f}%)" if exposure is not None else ""
        return f"AI-complement stance{extra}: a skill that works with AI tools."
    status = g.get("status") or rec.get("status")
    why = {"low_volume": "Too few posts to forecast", "rare": "Very few posts"}.get(
        status, "No rising trend, not in the top half by current demand")
    return f"In the {role} gap (weight {g.get('weight', 0):.2f}). {why}."


def _source_line(rec: Mapping[str, Any], as_of: str | None) -> tuple[str, list[dict]]:
    sources = list(rec.get("sources") or [])
    if not sources:
        return "No dated source in skill_scores.json for this skill.", []
    parts = [f"{s['name']} ({s['date']})" for s in sources if "name" in s and "date" in s]
    prefix = f"data/skill_scores.json as of {as_of}: " if as_of else "data/skill_scores.json: "
    return prefix + "; ".join(parts), sources


def _pick_resource(options: Sequence[Mapping[str, Any]]) -> tuple[dict | None, list[dict]]:
    """Prefer a verified HRD Corp course, then a beginner resource, then the first listed.

    Returns (chosen, alternatives).
    """
    if not options:
        return None, []
    ordered = sorted(options, key=lambda r: (0 if r.get("hrd_corp") is True else 1,
                                             0 if r.get("level") == "beginner" else 1))  # stable
    return dict(ordered[0]), [dict(r) for r in ordered[1:]]


# ---------------------------------------------------------------- daily tasks

def schedule_tasks(steps: Sequence[dict], hours_per_week: float, start_date: date) -> list[dict]:
    """Split steps into daily tasks of at most MAX_TASK_MINUTES and give each a date.

    Daily budget = hours_per_week * 60 / 5 minutes, on Monday to Friday. A task never exceeds
    the budget or 45 minutes. `deadline` is the end of the task's planned day.
    """
    budget = hours_per_week * 60 / WORK_DAYS_PER_WEEK
    day = _next_workday(start_date)
    left_today = budget
    tasks: list[dict] = []

    for step in steps:
        remaining = step["minutes"]
        if not remaining or not step.get("resource"):
            step["task_ids"], step["start_date"], step["deadline"] = [], None, None
            continue
        pieces: list[tuple[date, int]] = []
        while remaining > 0:
            if left_today < MIN_FRAGMENT_MINUTES:
                day = _next_workday(day + timedelta(days=1))
                left_today = budget
            chunk = int(min(MAX_TASK_MINUTES, left_today, remaining))
            if chunk <= 0:  # budget below one minute per day: still make progress
                chunk = min(MAX_TASK_MINUTES, remaining)
            pieces.append((day, chunk))
            remaining -= chunk
            left_today -= chunk
        step_deadline = pieces[-1][0].isoformat()
        ids = []
        for i, (d, chunk) in enumerate(pieces, start=1):
            tid = f"T{len(tasks) + 1:03d}"
            ids.append(tid)
            res = step["resource"]
            tasks.append({
                "id": tid, "step": step["order"], "skill": step["skill"], "stage": step["stage"],
                "title": f"{step['skill']}: {res['title']} (part {i} of {len(pieces)})",
                "minutes": chunk, "part": i, "parts": len(pieces),
                "date": d.isoformat(), "deadline": d.isoformat(), "step_deadline": step_deadline,
                "resource_title": res["title"], "resource_url": res["url"],
                "reason": step["reason"], "sdg": list(step["sdg"]),
            })
        step["task_ids"] = ids
        step["start_date"] = pieces[0][0].isoformat()
        step["deadline"] = step_deadline
    return tasks


# ---------------------------------------------------------------- SDG summary

def _target_key(target: str) -> tuple:
    """Sort SDG targets numerically: 7.3 before 16.6, and 9.5 before 9.c."""
    major, _, minor = target.partition(".")
    return (int(major) if major.isdigit() else 99,
            (0, int(minor)) if minor.isdigit() else (1, minor))


def sdg_summary(steps: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count steps per SDG target and build a one-line contribution from the sdg_reason texts."""
    counts: dict[str, int] = {}
    skills_by_target: dict[str, list[str]] = {}
    first_reason: dict[str, str] = {}
    for step in steps:
        for target in step.get("sdg", []):
            counts[target] = counts.get(target, 0) + 1
            skills_by_target.setdefault(target, []).append(step["skill"])
            if step.get("sdg_reason"):
                first_reason.setdefault(target, step["sdg_reason"])
    ordered = dict(sorted(counts.items(), key=lambda kv: (-kv[1], _target_key(kv[0]))))
    reasons: list[str] = []
    for target in list(ordered)[:3]:
        text = first_reason.get(target)
        if text and text not in reasons:
            reasons.append(text)
    if ordered:
        targets = ", ".join(f"SDG {t} ({n})" for t, n in ordered.items())
        line = f"How this plan contributes: {targets}. " + " ".join(reasons)
    else:
        line = "How this plan contributes: no SDG tags for the skills in this plan."
    return {"counts": ordered, "skills_by_target": skills_by_target, "line": line.strip()}


def _outlook_text(outlook: Mapping[str, Any] | None) -> str:
    """Role demand in words, from the role's own trend numbers only."""
    outlook = outlook or {}
    label = outlook.get("trend_label")
    last, prev = outlook.get("share_last12"), outlook.get("share_prev12")
    if label and last is not None and prev is not None:
        return (f"{label}, {100 * last:.1f}% of posts in the last 12 months vs {100 * prev:.1f}% "
                f"the 12 months before")
    return "no trend label: too few posts"


def sdg_headline(pathway: Mapping[str, Any], outlook: Mapping[str, Any] | None = None) -> list[str]:
    """Two plan-level SDG sentences. Every number comes from the plan or the role's outlook.

    SDG 4.4 uses indicator 4.4.1 (ICT skills for employment). The cost reads "RM0 ... free resources"
    only when every chosen resource has cost "free"; otherwise "mostly free".
    """
    chosen = [s["resource"] for s in pathway["steps"] if s["resource"]]
    all_free = bool(chosen) and all(str(r.get("cost", "")).strip().lower() == "free" for r in chosen)
    cost = "at RM0 cost using free resources" if all_free else "using mostly free resources"
    hours = pathway["totals"]["hours"]
    return [
        f"SDG 4.4 (indicator 4.4.1, ICT skills for employment): this plan adds {len(chosen)} job-listed "
        f"skills in {hours} hours (estimate) {cost}.",
        f"SDG 8.5 (full and productive employment): moves you toward {pathway['target_role']} "
        f"(role demand: {_outlook_text(outlook)}).",
    ]


# ---------------------------------------------------------------- main entry

def build_pathway(target_role: str,
                  gap: Sequence[Mapping[str, Any]],
                  role_gaps: Any,
                  skill_scores: Mapping[str, Any] | Sequence[Mapping[str, Any]],
                  resources: Mapping[str, Any] | Sequence[Mapping[str, Any]],
                  scenario: str = "moderate",
                  hours_per_week: float = 5,
                  start_date: date | datetime | str | None = None,
                  taxonomy: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Build the pathway for `target_role`.

    gap             [{skill, weight, status, trend_label, stance}, ...] ordered by weight.
    role_gaps       gap lists of the roles to count for the no-regret stage: the target role and
                    every ranked role, each once. Items may also be role results with a "gap" key.
    skill_scores    data/skill_scores.json (dict) or its "skills" list.
    resources       data/resources.json (dict) or its "resources" list.
    taxonomy        data/taxonomy.json list; loaded from disk when None (for SDG reasons).
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}, got {scenario!r}")
    if not hours_per_week or hours_per_week <= 0:
        raise ValueError("hours_per_week must be positive")

    start = _next_workday(_as_date(start_date))
    gap = _dedupe_gap(gap)
    scores = _skill_index(skill_scores)
    res_index = _resource_index(resources)
    tax = {t["skill"]: t for t in (taxonomy if taxonomy is not None else load_taxonomy())}
    as_of = skill_scores.get("as_of") if isinstance(skill_scores, Mapping) else None

    staged = classify(gap, role_gaps, skill_scores)
    gap_pos = {g["skill"]: i for i, g in enumerate(gap)}
    by_stage: dict[str, list[dict]] = {name: [] for name in STAGE_LABELS}
    for g in gap:
        by_stage[staged[g["skill"]]["stage"]].append(g)
    for members in by_stage.values():  # within a stage: role weight, high first; ties keep gap order
        members.sort(key=lambda g: (-float(g.get("weight", 0)), gap_pos[g["skill"]]))

    steps: list[dict] = []
    for stage in STAGE_ORDER[scenario]:
        for g in by_stage[stage]:
            skill = g["skill"]
            rec = scores.get(skill, {})
            chosen, alternatives = _pick_resource(res_index.get(skill, []))
            source, sources = _source_line(rec, as_of)
            tx = tax.get(skill, {})
            steps.append({
                "order": len(steps) + 1,
                "skill": skill,
                "stage": stage,
                "stage_label": STAGE_LABELS[stage],
                "weight": g.get("weight"),
                "reason": _reason(stage, g, rec, staged[skill], target_role),
                "status": g.get("status") or rec.get("status"),
                "trend_label": g.get("trend_label"),
                "stance": g.get("stance"),
                "resource": chosen,
                "resource_note": None if chosen else PLACEHOLDER_RESOURCE,
                "alternatives": alternatives,
                "minutes": chosen["minutes"] if chosen else 0,
                "minutes_is_estimate": True,
                "sdg": list(tx.get("sdg") or rec.get("sdg") or []),
                "sdg_reason": tx.get("sdg_reason"),
                "source": source,
                "sources": sources,
            })

    tasks = schedule_tasks(steps, hours_per_week, start)
    stages = [{"name": s, "label": STAGE_LABELS[s],
               "skills": [st["skill"] for st in steps if st["stage"] == s]}
              for s in STAGE_ORDER[scenario]]
    total_minutes = sum(t["minutes"] for t in tasks)
    return {
        "target_role": target_role,
        "scenario": scenario,
        "scenario_label": ("Fast AI disruption (estimate)" if scenario == "fast"
                           else "Moderate (estimate)"),
        "hours_per_week": hours_per_week,
        "start_date": start.isoformat(),
        "finish_date": tasks[-1]["deadline"] if tasks else None,
        "skill_scores_as_of": as_of,
        "stages": stages,
        "steps": steps,
        "tasks": tasks,
        "unresolved": [s["skill"] for s in steps if not s["resource"]],
        "totals": {"steps": len(steps), "tasks": len(tasks), "minutes": total_minutes,
                   "hours": round(total_minutes / 60, 1)},
        "sdg_summary": sdg_summary(steps),
        "notes": [ESTIMATE_NOTE, HRD_CORP_NOTE],
    }


# ---------------------------------------------------------------- progress

def progress(tasks: Sequence[Mapping[str, Any]], done_ids: Iterable[str],
             as_of: date | datetime | str | None = None) -> dict[str, Any]:
    """Progress of a task list.

    percent_done is weighted by minutes. A task is overdue when it is not done and its
    deadline is before `as_of` (today when None). Ids in done_ids that match no task are
    returned in `unknown_ids` and otherwise ignored.
    """
    today = _as_date(as_of)
    done = set(done_ids)
    known = {t["id"] for t in tasks}
    total = sum(t["minutes"] for t in tasks)
    done_minutes = sum(t["minutes"] for t in tasks if t["id"] in done)
    overdue = [dict(t) for t in tasks
               if t["id"] not in done and date.fromisoformat(t["deadline"]) < today]
    next_task = next((dict(t) for t in tasks if t["id"] not in done), None)

    completed: list[str] = []
    for skill in dict.fromkeys(t["skill"] for t in tasks):
        if all(t["id"] in done for t in tasks if t["skill"] == skill):
            completed.append(skill)
    return {
        "percent_done": round(100 * done_minutes / total, 1) if total else 0.0,
        "tasks_done": sum(1 for t in tasks if t["id"] in done),
        "tasks_total": len(tasks),
        "minutes_done": done_minutes,
        "minutes_total": total,
        "overdue": overdue,
        "next_task": next_task,
        "completed_skills": completed,
        "unknown_ids": sorted(done - known),
        "as_of": today.isoformat(),
    }


# ---------------------------------------------------------------- exports

def to_markdown(pathway: Mapping[str, Any]) -> str:
    """Render the pathway as Markdown."""
    p = pathway
    totals = p["totals"]
    lines = [
        f"# Reskilling pathway: {p['target_role']}",
        "",
        f"- Scenario: {p['scenario_label']}",
        f"- Pace: {p['hours_per_week']} hours a week, Monday to Friday",
        f"- Plan: {totals['steps']} skills, {totals['tasks']} daily tasks, about {totals['hours']} hours (estimate)",
        f"- Dates: {p['start_date']} to {p['finish_date'] or 'n/a'}",
        f"- Skill data as of: {p.get('skill_scores_as_of') or 'n/a'}",
        "",
        "## Order of skills",
        "",
    ]
    for stage in p["stages"]:
        lines += [f"### {stage['label']}", ""]
        steps = [s for s in p["steps"] if s["stage"] == stage["name"]]
        if not steps:
            lines += ["None.", ""]
            continue
        for s in steps:
            res = s["resource"]
            lines.append(f"{s['order']}. **{s['skill']}** (about {s['minutes']} min, estimate)")
            lines.append(f"   - Why: {s['reason']}")
            if res:
                cost = res["cost"] + (", HRD Corp-claimable" if res.get("hrd_corp") else "")
                lines.append(f"   - Resource: [{res['title']}]({res['url']}) ({res['provider']}, {cost}, "
                             f"{res['level']}; link checked {res['checked']})")
            else:
                lines.append(f"   - Resource: {s['resource_note']}")
            if s["sdg"]:
                lines.append(f"   - SDG: {', '.join(s['sdg'])}. {s['sdg_reason'] or ''}".rstrip())
            lines.append(f"   - Source: {s['source']}")
        lines.append("")
    lines += ["## Daily tasks", "", "| Id | Date | Min | Task | Link |", "|---|---|---|---|---|"]
    for t in p["tasks"]:
        lines.append(f"| {t['id']} | {t['date']} | {t['minutes']} | {t['title']} | {t['resource_url']} |")
    lines += ["", "## SDG links", ""]
    for target, n in p["sdg_summary"]["counts"].items():
        lines.append(f"- SDG {target}: {n} step{'s' if n != 1 else ''} ({', '.join(p['sdg_summary']['skills_by_target'][target])})")
    lines += ["", p["sdg_summary"]["line"], "", "## Notes", ""]
    lines += [f"- {n}" for n in p["notes"]]
    if p["unresolved"]:
        lines.append(f"- {PLACEHOLDER_RESOURCE}: {', '.join(p['unresolved'])}.")
    return "\n".join(lines) + "\n"


def _ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def _ics_fold(line: str) -> str:
    """Fold a content line at 75 octets (RFC 5545 section 3.1), never inside a UTF-8 character."""
    out, current, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 75:
            out.append(current)
            current, size = " " + ch, 1 + n
        else:
            current += ch
            size += n
    out.append(current)
    return "\r\n".join(out)


def to_ics(tasks: Sequence[Mapping[str, Any]], calendar_name: str = "Verity reskilling plan",
           now: datetime | None = None) -> str:
    """Write the tasks as an RFC 5545 calendar: one all-day VEVENT per task, CRLF line ends.

    The UID holds a short hash of the plan (`tasks_signature`), so two plans never share a UID.
    """
    plan_id = tasks_signature(tasks)
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Verity//Pathway E8//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_escape(calendar_name)}"]
    for t in tasks:
        day = date.fromisoformat(t["date"])
        desc = (f"{t['minutes']} min (estimate). Resource: {t['resource_title']} {t['resource_url']} "
                f"Why: {t['reason']} Finish by {t['deadline']}.")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{plan_id}-{t['id']}-{t['date']}@verity.pathway",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(t['title'])}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            f"URL:{t['resource_url']}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(line) for line in lines) + "\r\n"
