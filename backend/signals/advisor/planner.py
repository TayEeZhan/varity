"""Plan memory: what changed since the user last accepted the pathway, and which new trend skill to offer.

Pure functions; advisor/service.py calls them and roles_api.py stores the PlanState they return.
No LLM decides anything here. Rules (docs/Refining personalized planner and tasks assigner.md, section E):
- A skill dropped because the user now holds it is not a "change": it is accepted silently.
- A new skill is offered only when the news signal AND job posts both say it is rising, it is in the gap of
  another ranked role, it has a checked resource, and the user has not held, planned or declined it.
- At most one offer every OFFER_EVERY_DAYS; "Not now" hides a skill for DECLINE_DAYS.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping, Sequence

from intake.models import Declined, PlanState

OFFER_EVERY_DAYS = 7
DECLINE_DAYS = 30
MIN_NEWS_MOMENTUM = 0.5  # this week vs the 4 weeks before: +50% or more
MIN_STORIES_THIS_WEEK = 3  # one viral post is not a trend
RISING_WEEKS = 3  # this week >= last week >= the week before


def active_declined(state: PlanState | None, today: str) -> set[str]:
    return {d.skill for d in state.declined if d.until > today} if state else set()


def news_rising(row: Mapping[str, Any] | None) -> bool:
    """The trend-layer test: enough stories, a clear rise, and no drop over the last RISING_WEEKS weeks."""
    if not row:
        return False
    weekly = list(row.get("weekly_counts") or [])[:RISING_WEEKS]  # index 0 = this week
    held_up = len(weekly) == RISING_WEEKS and all(weekly[i] >= weekly[i + 1] for i in range(RISING_WEEKS - 1))
    return row.get("this_week", 0) >= MIN_STORIES_THIS_WEEK and row.get("momentum", 0) >= MIN_NEWS_MOMENTUM and held_up


def _removed_reason(skill: str, scores: Mapping[str, Mapping]) -> str:
    if (scores.get(skill) or {}).get("trend_label") == "Falling":
        return f"Job posts asking for {skill} are now falling."
    return f"{skill} is no longer in this role's job-post profile."


def diff(state: PlanState | None, steps: Sequence[Mapping[str, Any]], held: Iterable[str],
         scores: Mapping[str, Mapping]) -> dict | None:
    """{added, removed} against the accepted plan, each [{skill, reason}]; None when nothing worth telling changed."""
    if state is None:
        return None
    held, old = set(held), set(state.skills)
    new = [s["skill"] for s in steps]
    added = [{"skill": s["skill"], "reason": s["reason"]} for s in steps if s["skill"] not in old]
    removed = [{"skill": k, "reason": _removed_reason(k, scores)} for k in state.skills if k not in new and k not in held]
    return {"added": added, "removed": removed} if added or removed else None


MOVE_PP = 1.0  # a share move this big (percentage points) is worth telling, even with the same label (team judgement)


def outlook_change(state: PlanState | None, role_id: str, ledger_rows: Sequence[Mapping[str, str]]) -> dict | None:
    """The target role's outlook on the day the plan was accepted (forecast ledger) against today's.

    None when there is no accepted plan, no ledger row from that day or before, or nothing worth telling
    (same trend label and a share move under MOVE_PP).
    """
    if state is None:
        return None
    mine = [r for r in ledger_rows if r["role_id"] == role_id]
    then = [r for r in mine if r["run_date"] <= state.accepted_at[:10]]
    if not then:
        return None
    old, new = then[-1], mine[-1]
    moved = (float(new["share_now"]) - float(old["share_now"])) * 100
    if old["label"] == new["label"] and abs(moved) < MOVE_PP:
        return None
    return {"since": old["run_date"], "date": new["run_date"], "labelThen": old["label"] or None,
            "labelNow": new["label"] or None, "shareThen": float(old["share_now"]), "shareNow": float(new["share_now"]),
            "movedPp": round(moved, 2), "source": "Verity forecast ledger (daily HN refresh)"}


def trend_offer(state: PlanState | None, today: str, held: Iterable[str], planned: Iterable[str],
                other_gaps: Iterable[Iterable[Mapping[str, Any]]], scores: Mapping[str, Mapping],
                momentum: Mapping[str, Mapping], links: Mapping[str, str], with_resource: set[str],
                scores_as_of: str | None = None) -> dict | None:
    """The one new skill worth adding this week, with the evidence for it; None if none passes every gate."""
    if state is None or state.offers == "off":
        return None
    if state.last_offer_at and date.fromisoformat(state.last_offer_at[:10]) > date.fromisoformat(today) - timedelta(days=OFFER_EVERY_DAYS):
        return None
    skip = set(held) | set(planned) | active_declined(state, today)
    best = None
    for gap in other_gaps:
        for g in gap:
            skill = g["skill"]
            score, news = scores.get(skill) or {}, momentum.get(links.get(skill, ""))
            if skill in skip or skill not in with_resource or score.get("trend_label") != "Rising" or not news_rising(news):
                continue
            if best is None or news["momentum"] > best[1]["momentum"]:
                best = (skill, news)
    if best is None:
        return None
    skill, news = best
    return {"skill": skill,
            "news": f"{news['skill']} is in {news['this_week']} AI stories this week, vs {news['weekly_average_before']:g} a week before",
            "jobs": f"Job posts asking for {skill} are rising (skill data as of {scores_as_of or 'the latest run'})",
            "momentum": news["momentum"]}


def pushed_gap(state: PlanState | None, held: Iterable[str], gap_skills: Iterable[str],
               scores: Mapping[str, Mapping]) -> list[dict]:
    """Gap items for trend skills the user added: kept while not held, not already in the gap, and not falling."""
    if state is None:
        return []
    skip = set(held) | set(gap_skills)
    out = []
    for skill in state.pushed:
        row = scores.get(skill) or {}
        if skill in skip or row.get("trend_label") == "Falling":
            continue
        out.append({"skill": skill, "weight": 0.0, "status": row.get("status", "ok"),
                    "trend_label": row.get("trend_label"), "stance": row.get("stance")})
    return out


def accept(state: PlanState | None, role_id: str, skills: Sequence[str], today: str, now: str) -> PlanState:
    """Store this plan as the accepted one. A new role starts a new plan today; declines and offer timing carry over."""
    if state is None:
        return PlanState(role_id=role_id, start_date=today, skills=tuple(skills), accepted_at=now)
    if state.role_id != role_id:
        return state.model_copy(update={"role_id": role_id, "start_date": today, "skills": tuple(skills),
                                        "accepted_at": now, "pushed": ()})
    return state.model_copy(update={"skills": tuple(skills), "accepted_at": now})


def revert(state: PlanState, change: Mapping[str, Any], today: str, now: str) -> PlanState:
    """Keep the old plan: hide the added skills for DECLINE_DAYS. Removed skills are gone from the data, so they stay gone."""
    added = [a["skill"] for a in change.get("added", [])]
    gone = {r["skill"] for r in change.get("removed", [])}
    return state.model_copy(update={
        "skills": tuple(s for s in state.skills if s not in gone),
        "pushed": tuple(s for s in state.pushed if s not in added and s not in gone),
        "declined": _decline(state.declined, added, today), "accepted_at": now})


def answer_offer(state: PlanState, skill: str, add: bool, today: str, now: str) -> PlanState:
    update: dict[str, Any] = {"last_offer_at": now}
    if add:
        update["pushed"] = tuple(dict.fromkeys(state.pushed + (skill,)))
    else:
        update["declined"] = _decline(state.declined, [skill], today)
    return state.model_copy(update=update)


def _decline(current: Sequence[Declined], skills: Iterable[str], today: str) -> tuple[Declined, ...]:
    until = (date.fromisoformat(today) + timedelta(days=DECLINE_DAYS)).isoformat()
    skills = set(skills)
    kept = tuple(d for d in current if d.skill not in skills and d.until > today)
    return kept + tuple(Declined(skill=s, until=until) for s in sorted(skills))
