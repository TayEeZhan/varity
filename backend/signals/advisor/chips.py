"""Reason chips: every reason shown for a role or a pathway step, written by code from the data.

The LLM may only choose among these chips (advisor.llm); it never writes a number or a skill name itself.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from intake.skills import fold

HAVE_SHOWN = 3
SMALL_GAP_MAX = 3
CHIPS_SHOWN = 3
STRONG_FIT_FROM, GOOD_FIT_FROM = 0.5, 0.3


def chip(chip_id: str, kind: str, text: str, strength: float, source: str, as_of: str | None) -> dict:
    return {"id": chip_id, "type": kind, "text": text, "strength": round(max(0.0, min(strength, 1.0)), 3),
            "source": source, "asOf": as_of}


def watch_map(taxonomy: Iterable[Mapping], watch_skills: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """Taxonomy skill -> the watchlist skill whose terms name it (config/watchlist.yaml). No match: left out."""
    out = {}
    for t in taxonomy:
        names = {fold(n) for n in [t["skill"], *(t.get("synonyms") or ())]}
        hit = next((w for w, terms in watch_skills.items() if names & {fold(term) for term in terms}), None)
        if hit:
            out[t["skill"]] = hit
    return out


def rising_momentum(skills: Iterable[str], momentum: Mapping[str, Mapping], links: Mapping[str, str]) -> tuple[str, dict] | None:
    """(role skill, momentum row) of the role skill whose watchlist skill rose most this week; None if none rose."""
    best = None
    for skill in skills:
        row = momentum.get(links.get(skill, ""))
        if row and row["momentum"] > 0 and (best is None or row["momentum"] > best[1]["momentum"]):
            best = (skill, row)
    return best


def gap_weeks(gap: Sequence[Mapping], minutes_by_skill: Mapping[str, int], hours_per_week: float) -> int | None:
    minutes = [minutes_by_skill.get(g["skill"]) for g in gap]
    if not gap or None in minutes:
        return None
    return max(1, math.ceil(sum(minutes) / 60 / hours_per_week))


def role_chips(role: Mapping[str, Any], forecast: Mapping[str, Any] | None, momentum: Mapping[str, Mapping],
               links: Mapping[str, str], minutes_by_skill: Mapping[str, int], hours_per_week: float,
               as_of: Mapping[str, str | None]) -> list[dict]:
    """Every chip that is true for one match_roles result. `as_of`: profile, forecast, signals dates."""
    chips: list[dict] = []
    have, gap, n = role["have"], role["gap"], role["n_profile_skills"]
    if have:
        names = ", ".join(s["skill"] for s in have[:HAVE_SHOWN])
        names = names if len(have) <= HAVE_SHOWN else f"including {names}"
        chips.append(chip("skill_fit", "skill_fit", f"You already have {len(have)} of its {n} core skills, {names}",
                          role["match_score"], "profile", as_of["profile"]))
    weeks = gap_weeks(gap, minutes_by_skill, hours_per_week)
    if 0 < len(gap) <= SMALL_GAP_MAX:
        tail = f", about {weeks} week{'s' if weeks > 1 else ''} at {hours_per_week:g} h/week" if weeks else ""
        chips.append(chip("small_gap", "small_gap", f"Only {len(gap)} skill{'s' if len(gap) > 1 else ''} to learn{tail}",
                          1 - len(gap) / max(n, 1), "resources", as_of["profile"]))
    trend = (forecast or {}).get("trend") or {}
    label, now, before = trend.get("label"), trend.get("share_last12"), trend.get("share_prev12")
    # Observed shares (last 12 months vs the 12 before), not a forecast.
    shares = f": {before:.1%} → {now:.1%} of HN hiring posts, last 12 months vs the 12 before" if now is not None and before is not None else ""
    if label == "Rising":
        chips.append(chip("demand_rising", "demand_rising", f"Demand rising{shares}",
                          1 - (trend.get("p") or 0.5), "role_forecast", as_of["forecast"]))
    rise = rising_momentum([s["skill"] for s in have + gap], momentum, links)
    if rise:
        skill, row = rise
        chips.append(chip("ai_boost", "ai_boost",
                          f"{row['skill']} ({skill} in this role) is in {row['this_week']} AI stories this week, "
                          f"vs {row['weekly_average_before']:g} a week before",
                          min(row["momentum"] / 10, 1.0) * 0.7, "signals", as_of["signals"]))
    if label == "Falling":
        chips.append(chip("watch_falling", "watch_out", f"Demand falling{shares}", 1.0, "role_forecast", as_of["forecast"]))
    elif role.get("tier") == "rough":
        chips.append(chip("watch_rough", "watch_out",
                          f"Rough role profile: learned from only {role['n_single_role_posts']} job posts",
                          0.8, "role_profiles", as_of["profile"]))
    elif label is None:
        chips.append(chip("watch_no_trend", "watch_out", "Too few job posts to tell if demand is rising",
                          0.5, "role_forecast", as_of["forecast"]))
    return chips


def default_pick(chips: Sequence[Mapping]) -> tuple[list[dict], dict | None]:
    """(top reasons by strength, first watch-out): what the user sees when no LLM ranked the roles."""
    reasons = sorted((c for c in chips if c["type"] != "watch_out"), key=lambda c: -c["strength"])[:CHIPS_SHOWN]
    watch = next((c for c in chips if c["type"] == "watch_out"), None)
    return [dict(c) for c in reasons], dict(watch) if watch else None


def fit_label(match: float, trend_label: str | None) -> str:
    fit = "Strong fit" if match >= STRONG_FIT_FROM else "Good fit" if match >= GOOD_FIT_FROM else "Partial fit"
    demand = {"Rising": "rising demand", "Falling": "falling demand", "No clear change": "steady demand"}
    return f"{fit}, {demand.get(trend_label, 'demand not clear')}"


def step_chips(step: Mapping[str, Any], target_name: str, momentum: Mapping[str, Mapping],
               links: Mapping[str, str], as_of: Mapping[str, str | None]) -> list[dict]:
    """Chips for one pathway step (build_pathway output)."""
    chips = [chip("closes_gap", "closes_gap", f"Closes a gap for {target_name}: {step['skill']}",
                  float(step.get("weight") or 0), "role_profiles", as_of["profile"])]
    if step.get("trend_label") == "Rising":
        chips.append(chip("skill_rising", "skill_rising", f"{step['skill']} is rising in job posts",
                          0.8, "skill_scores", as_of["skills"]))
    rise = rising_momentum([step["skill"]], momentum, links)
    if rise:
        row = rise[1]
        chips.append(chip("ai_boost", "ai_boost",
                          f"{row['skill']} is in {row['this_week']} AI stories this week, vs {row['weekly_average_before']:g} a week before",
                          min(row["momentum"] / 10, 1.0) * 0.7, "signals", as_of["signals"]))
    if step.get("stage") == "no_regret":
        chips.append(chip("no_regret", "no_regret", "Needed by more than one of your best-fit roles",
                          0.9, "role_profiles", as_of["profile"]))
    return chips
