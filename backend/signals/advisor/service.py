"""Join the three inputs: the saved skill profile, the AI signals and the role forecast.

Code computes every number (engine.roles.match_roles, engine.pathway.build_pathway) and writes every reason
(advisor.chips). The LLM steps (advisor.llm) only re-rank within limits and choose among those reasons.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from advisor import chips as chip_mod
from advisor import planner
from advisor.llm import LlmUnavailable, advise, call_model, coach, verify_advice, verify_coaching
from advisor.mapping import map_profile, skill_credit, skill_levels, taxonomy_index
from intake.ledger import now_iso as ledger_now
from intake.models import Profile

VERITY_ROOT = Path(__file__).resolve().parents[3]
if str(VERITY_ROOT) not in sys.path:
    sys.path.insert(0, str(VERITY_ROOT))  # engine/ lives at the verity root, as app.py does it

from engine import ledger as ledger_mod
from engine import live as live_mod  # noqa: E402
from engine import my_dosm  # noqa: E402
from engine import pathway as pathway_mod  # noqa: E402
from engine import roles as roles_mod  # noqa: E402
from engine import sdg as sdg_mod  # noqa: E402

DATA_DIR = VERITY_ROOT / "data"
SCENARIOS = roles_mod.SCENARIOS
STEP_REASONS_SHOWN = 2
FILES = {"profiles": "role_profiles.json", "scores": "skill_scores.json", "trends": "role_trends.json",
         "forecast": "role_forecast.json", "resources": "resources.json", "taxonomy": "taxonomy.json",
         "exposure": "exposure.csv"}
# Left out of the answer (not an error) when missing, as app.py does.
OPTIONAL_FILES = {"role_sdg": "role_sdg.json", "mycol": "mycol.json", "mycol_map": "mycol_role_map.json"}
SCENARIO_LABELS = {"moderate": "Expected (estimate)", "fast": "If AI speeds up (estimate)"}
# Short names for the SDG targets that data/ uses (plain paraphrase of the UN target text).
SDG_LABELS = {
    "1.4": "Access to basic services", "2.3": "Small food producers' income", "2.4": "Sustainable food production",
    "3.8": "Universal health coverage", "3.b": "Health research", "3.d": "Health risk early warning",
    "4.3": "Technical and tertiary education", "4.4": "Skills for employment", "7.2": "Renewable energy",
    "7.3": "Energy efficiency", "8.2": "Productivity through technology", "8.5": "Productive employment",
    "8.10": "Access to financial services", "9.5": "Research and innovation", "9.c": "ICT access",
    "10.2": "Inclusion of all", "11.1": "Adequate housing", "11.2": "Sustainable transport",
    "13.2": "Climate policy", "16.6": "Effective institutions", "16.7": "Inclusive decision-making",
}
MYCOL_LABEL = "TalentCorp MyCOL"


class RoleNotFound(ValueError):
    """The role id is not one the engine can plan for (unknown, or too few posts to learn a profile)."""


@lru_cache(maxsize=32)
def _read(path: str, mtime: float) -> Any:
    """`mtime` only keys the cache, so an engine refresh is picked up."""
    if path.endswith(".csv"):
        with open(path, encoding="utf-8", newline="") as fh:
            return {r["skill"]: float(r["e_s"]) for r in csv.DictReader(fh)}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


LIVE_CHECK_SECONDS = 600
_live = {"checked": float("-inf"), "dir": None}


def current_data_dir() -> Path:
    """The newest stored snapshot (engine.live, written by the daily refresh), else the committed data/.

    The store is asked at most every 10 minutes; any store problem means the committed data.
    """
    now = time.monotonic()
    if now - _live["checked"] > LIVE_CHECK_SECONDS:
        _live.update(checked=now, dir=live_mod.start_dir(DATA_DIR))
    return Path(_live["dir"]) if _live["dir"] else DATA_DIR


REFRESH_GAP_SECONDS = 600
_replay = {"cache": {}}
_refresh_state = {"running": False, "error": None, "fetched_at": None, "last_start": None}


def replay_months() -> list[str]:
    """The months a replay may use: the as-of points of the role profiles."""
    return sorted(_read(str(DATA_DIR / FILES["profiles"]), (DATA_DIR / FILES["profiles"]).stat().st_mtime)["profiles"])


def check_as_of(as_of: str | None) -> None:
    """Raise ValueError for a month that is not a replay month. None (latest) is fine."""
    if as_of is not None and as_of not in replay_months():
        raise ValueError(f"asOf must be one of {replay_months()}")


def _replayed(as_of: str) -> dict[str, Any]:
    """Skill scores and role trends cut at as_of from the committed demand files (no look-ahead). Cached per month."""
    if as_of not in _replay["cache"]:
        from engine import scores as scores_mod
        roles = roles_mod.load_roles(DATA_DIR / "roles.json")
        rows = roles_mod.read_demand_rows(DATA_DIR / "role_demand_monthly.csv")
        _replay["cache"][as_of] = {"scores": scores_mod.build_scores(as_of=as_of, data_dir=DATA_DIR),
                                   "trends": roles_mod.build_role_trends(rows, roles, as_of=as_of)}
    return _replay["cache"][as_of]


def malaysia_meta() -> dict | None:
    """DOSM online-vacancy check (data/my_vacancies_quarterly.csv, committed). None when the file is missing."""
    path = DATA_DIR / "my_vacancies_quarterly.csv"
    try:
        return _malaysia(str(path), path.stat().st_mtime)
    except OSError:
        return None


@lru_cache(maxsize=2)
def _malaysia(path: str, mtime: float) -> dict | None:
    return my_dosm.summary(my_dosm.read_csv(Path(path)))


def data_meta(as_of: str | None = None) -> dict[str, Any]:
    """What the UI shows in the 'Trend data' banner. as_of is the viewer's replay month (already checked)."""
    snap = live_mod.folder_meta(current_data_dir())
    scores_as_of = as_of or _read(str(current_data_dir() / FILES["scores"]), (current_data_dir() / FILES["scores"]).stat().st_mtime).get("as_of")
    mode = "refreshing" if _refresh_state["running"] else "replay" if as_of else "latest"
    return {"mode": mode, "asOf": scores_as_of, "dataAsOf": scores_as_of, "dataMode": "replay" if as_of else "latest",
            "fetchedAt": (snap or {}).get("fetched_at") or _refresh_state["fetched_at"],
            "source": "HN Who is hiring", "error": _refresh_state["error"], "replayMonths": replay_months()}


def refresh_in_background() -> tuple[bool, int]:
    """Start engine.refresh.refresh in a thread. (False, seconds to wait) when one runs or started under 10 minutes ago.

    A failure keeps the last good data. The gap is server-wide and in memory (it resets on restart)."""
    import threading
    wait = REFRESH_GAP_SECONDS - (time.monotonic() - (_refresh_state["last_start"] or float("-inf")))
    if _refresh_state["running"] or wait > 0:
        return False, max(1, int(wait)) if wait > 0 else REFRESH_GAP_SECONDS
    _refresh_state.update(running=True, error=None, last_start=time.monotonic())

    def run() -> None:
        try:
            from engine import refresh as refresh_mod
            result = refresh_mod.refresh()
            if not result.get("ok"):
                _refresh_state["error"] = result.get("error") or "refresh failed"
                return
            live_mod.publish(result)
            _refresh_state["fetched_at"] = result.get("fetched_at")
            _live.update(checked=float("-inf"), dir=None)  # ask the store again
        except Exception as exc:  # noqa: BLE001 - the last good data stays in use
            _refresh_state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            _refresh_state["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return True, 0


def load_data(data_dir: Path | None = None, as_of: str | None = None) -> dict[str, Any]:
    """The engine files. Raises FileNotFoundError when one is missing. as_of (a replay month) is checked by the caller."""
    replay = data_dir is None and as_of
    data_dir = data_dir or current_data_dir()
    data = {key: _read(str(data_dir / name), (data_dir / name).stat().st_mtime) for key, name in FILES.items()}
    for key, name in OPTIONAL_FILES.items():
        try:
            data[key] = _read(str(data_dir / name), (data_dir / name).stat().st_mtime)
        except (OSError, ValueError):
            data[key] = None
    try:  # employer-funded options (HRD Corp): always from the repo data folder; missing file = none
        data["hrd"] = _read(str(DATA_DIR / "hrd_programmes.json"), (DATA_DIR / "hrd_programmes.json").stat().st_mtime)
    except (OSError, ValueError):
        data["hrd"] = {"programmes": []}
    doc = data["role_sdg"]
    if doc is not None and not (isinstance(doc, dict) and isinstance(doc.get("roles"), dict)
                                and isinstance(doc.get("sectors"), list)):
        data["role_sdg"] = None  # malformed: treat like a missing optional file
    if replay:
        data = {**data, **_replayed(replay)}
    return data


def role_ids(data: Mapping[str, Any]) -> set[str]:
    return set(data["trends"]["roles"])


def pathway_role_ids(profile: Profile, data: Mapping[str, Any]) -> set[str]:
    """Roles a pathway can be built for: the ranked ones and the low-match ones (not the unranked)."""
    out = _match(profile, data, "moderate")[0]
    return {r["role_id"] for r in out["roles"] + out["low_match"]}


def sdg_tags(targets: Sequence[str], source: str) -> list[dict]:
    return [{"target": t, "label": SDG_LABELS.get(t, f"SDG {t}"), "source": source} for t in targets]


def _role_sdg(role: Mapping[str, Any], data: Mapping[str, Any]) -> dict:
    """SDG targets of the role (data/roles.json) and the sectors where its posts are over-represented (data/role_sdg.json)."""
    doc = data.get("role_sdg") or {}
    names = {x["id"]: x for x in doc.get("sectors", [])}
    sectors = []
    for sid in (doc.get("roles", {}).get(role["role_id"]) or {}).get("sectors", {}):
        nums = sdg_mod.goal_numbers(doc, role["role_id"], sid)
        if nums and nums["reliable"] and nums["lift"] and nums["lift"] > 1 and sid in names:
            sectors.append({"sector": sid, "name": names[sid]["name"], "tags": sdg_tags(names[sid]["sdg"], "data/role_sdg.json"),
                            "sharePct": round(nums["share"] * 100, 1), "baselinePct": round(nums["baseline_share"] * 100, 1),
                            "lift": round(nums["lift"], 1), "count": nums["count"], "posts": nums["n"],
                            "months": nums["months"], "asOf": doc.get("as_of")})
    sectors.sort(key=lambda x: -x["lift"])
    return {"tags": sdg_tags(role.get("sdg") or [], "data/roles.json"), "sectors": sectors[:2]}


def mycol_by_role(data: Mapping[str, Any]) -> dict[str, list[dict]]:
    """{role_id: MyCOL occupations}, direct matches first (port of app.py mycol_by_role). {} when a file is missing."""
    mycol, mapping = data.get("mycol"), data.get("mycol_map")
    if not mycol or not mapping or not isinstance(mycol.get("occupations"), list) or not isinstance(mapping.get("mappings"), list):
        return {}
    source = mycol.get("source") if isinstance(mycol.get("source"), dict) else {}
    by_code = {o.get("masco_code"): o for o in mycol["occupations"] if isinstance(o, dict)}
    found: dict[str, list[dict]] = {}
    for m in mapping["mappings"]:
        occ = by_code.get(m.get("masco_code")) if isinstance(m, dict) else None
        if occ is None or not m.get("role_id") or m.get("strength") not in ("direct", "partial"):
            continue
        url = occ.get("source_url") or source.get("pdf_url") or source.get("landing_page") or ""
        found.setdefault(m["role_id"], []).append({
            "label": MYCOL_LABEL, "occupation": occ.get("occupation") or m.get("occupation"), "mascoCode": m["masco_code"],
            "strength": m["strength"], "year": occ.get("year") or source.get("year") or "",
            "url": url if str(url).startswith(("http://", "https://")) else ""})
    for items in found.values():
        items.sort(key=lambda i: i["strength"] != "direct")
    return found


def _match(profile: Profile, data: Mapping[str, Any], scenario: str) -> tuple[dict, dict, list[str]]:
    index = taxonomy_index(data["taxonomy"])
    held, unmapped = map_profile(profile, index)
    role_profile = roles_mod.profile_for(data["scores"]["as_of"], data["profiles"])
    out = roles_mod.match_roles(held, role_profile, data["scores"], data["trends"], scenario, exposure=data["exposure"],
                                credit=skill_credit(profile, index))
    return out, held, unmapped


def match(profile: Profile, data: Mapping[str, Any], scenario: str) -> dict:
    """match_roles for a saved profile (the proof API ranks projects and certs from it)."""
    return _match(profile, data, scenario)[0]


task_slug = pathway_mod.task_slug
today_myt = pathway_mod.today_myt


def _tag(as_of: Mapping[str, str | None], scenario: str | None = None) -> str:
    """Cache tag: data dates, plus the scenario only where the prompt depends on it (the coach)."""
    return json.dumps([as_of, scenario], sort_keys=True)


def _momentum(rows: Sequence[Mapping]) -> dict[str, Mapping]:
    return {r["skill"]: r for r in rows}


def _watch_terms(momentum_rows: Sequence[Mapping]) -> dict[str, list[str]]:
    return {r["skill"]: list(r.get("terms") or []) for r in momentum_rows}


def _minutes_by_skill(resources: Mapping[str, Any]) -> dict[str, int]:
    by_skill: dict[str, list[dict]] = {}
    for r in resources["resources"]:
        by_skill.setdefault(r["skill"], []).append(r)
    picked = {skill: pathway_mod._pick_resource(options)[0] for skill, options in by_skill.items()}  # same pick as build_pathway
    return {skill: r["minutes"] for skill, r in picked.items() if r and r.get("minutes")}


def _outlook(forecast: Mapping[str, Any] | None, as_of: str | None) -> dict | None:
    if not forecast:
        return None
    band = forecast.get("forecast_moderate") or {}
    return {"label": (forecast.get("trend") or {}).get("label"), "shareNow": (forecast.get("share_now") or {}).get("value"),
            "low": band.get("low"), "high": band.get("high"), "asOf": as_of}


def _as_of(profile: Profile, data: Mapping[str, Any], run_id: str | None) -> dict[str, str | None]:
    return {"profile": profile.updated_at[:10], "forecast": data["forecast"].get("as_of"),
            "signals": run_id, "skills": data["scores"].get("as_of")}


def suggestions(profile: Profile, momentum_rows: Sequence[Mapping], run_id: str | None, db_path: Path, *,
                scenario: str = "moderate", hours_per_week: float = 5, use_llm: bool = True,
                call: Callable = call_model, data: Mapping[str, Any] | None = None, goal: str | None = None) -> dict:
    """GET /api/roles/suggestions: ranked roles with reason chips (docs/role-suggestion-pathway-architecture.md §4.1)."""
    data = data or load_data()
    out, held, unmapped = _match(profile, data, scenario)
    levels = skill_levels(profile, taxonomy_index(data["taxonomy"]))
    as_of = _as_of(profile, data, run_id)
    momentum, links = _momentum(momentum_rows), chip_mod.watch_map(data["taxonomy"], _watch_terms(momentum_rows))
    minutes, forecasts = _minutes_by_skill(data["resources"]), data["forecast"]["roles"]
    mycol = mycol_by_role(data)
    options: dict[str, list[dict]] = {}
    for res in data["resources"]["resources"]:
        options.setdefault(res["skill"], []).append(res)

    def breakdown(r: Mapping[str, Any]) -> dict:
        b = roles_mod.score_breakdown(r)
        b["levels"] = [{"skill": s["skill"], "level": levels.get(s["skill"], "CV"), "credit": s.get("credit", 1.0)}
                       for s in r["have"]]
        for item in b["raise"]:
            pick = pathway_mod._pick_resource(options.get(item["skill"], []))[0]
            item["resource"] = {"title": pick["title"], "url": pick["url"]} if pick else None
        return b

    def role_row(r: Mapping[str, Any]) -> dict:
        chips = chip_mod.role_chips(r, forecasts.get(r["role_id"]), momentum, links, minutes, hours_per_week, as_of)
        return {"roleId": r["role_id"], "name": r["name"], "formulaRank": r["rank"],
                "matchPct": round(r["match_score"] * 100), "trendLabel": r["outlook"]["trend_label"],
                "outlook": _outlook(forecasts.get(r["role_id"]), as_of["forecast"]), "tier": r["tier"],
                "have": [s["skill"] for s in r["have"]],
                "learnedOnly": [s["skill"] for s in r["have"] if s.get("credit", 1.0) < 1.0], "gap": [s["skill"] for s in r["gap"]], "chips": chips,
                "breakdown": breakdown(r), "fastShift": r["fast_shift"], "sdg": _role_sdg(r, data), "mycol": mycol.get(r["role_id"], []),
                "sdgReason": sdg_mod.role_reason(data.get("role_sdg") or {}, r["role_id"])}

    roles = [role_row(r) for r in out["roles"]]

    status, checked = "off:NO_ROLES", {"order": None, "roles": {}}
    if roles and use_llm:
        try:
            advice, status = advise(db_path, sorted(held), roles, call, _tag(as_of))
            checked = verify_advice(advice, roles, [t["skill"] for t in data["taxonomy"]])
        except LlmUnavailable as exc:
            status = f"off:{exc.code}"
    elif not use_llm:
        status = "off:SWITCHED_OFF"

    pathway_ids = {r["role_id"] for r in out["roles"] + out["low_match"]}
    by_id = {r["roleId"]: r for r in roles}
    order = checked["order"] or [r["roleId"] for r in roles]
    ranked = []
    for rank, role_id in enumerate(order, start=1):
        role, llm = by_id[role_id], checked["roles"].get(role_id, {})
        reasons, watch = chip_mod.default_pick(role["chips"])
        ranked.append({**{k: v for k, v in role.items() if k != "chips"}, "rank": rank,
                       "fitLabel": chip_mod.fit_label(role["matchPct"] / 100, role["trendLabel"]),
                       "summary": llm.get("summary"), "reasons": llm.get("reasons") or reasons,
                       "watchOut": llm.get("watchOut") or watch, "salary": None})
    # A low-match destination is not ranked, but the planner pins it, so it needs the same fields as a ranked row.
    low_target = next((r for r in out["low_match"] if r["role_id"] == profile.target_role), None)
    destination = None
    if low_target:
        row = role_row(low_target)
        reasons, watch = chip_mod.default_pick(row["chips"])
        destination = {**{k: v for k, v in row.items() if k != "chips"}, "rank": None,
                       "fitLabel": chip_mod.fit_label(row["matchPct"] / 100, row["trendLabel"]),
                       "summary": None, "reasons": reasons, "watchOut": watch, "salary": None}
    goal_out = {}
    if goal:
        doc = data.get("role_sdg") or {}
        rr = sdg_mod.rerank_for_goal(out, doc, goal)
        fit = {x["role_id"]: x for x in rr["by_goal_fit"]}
        for row in ranked + ([destination] if destination else []):
            g = next((r for r in rr["roles"] + rr["low_match"] if r["role_id"] == row["roleId"]), None)["sdg_goal"]
            row["goal"] = {"share": g["share"], "baselineShare": g["baseline_share"], "count": g["count"], "n": g["n"],
                           "reliable": g["reliable"], "goalRank": fit.get(row["roleId"], {}).get("goal_rank")}
        goal_out = {"goal": goal, "goalName": rr["sector_name"], "goalOrder": [x["role_id"] for x in rr["by_goal_fit"]]}
        if not any(r["goal"]["reliable"] for r in ranked):
            goal_out["goalNote"] = f"Too few posts from {rr['sector_name']} employers to re-rank; the order is unchanged."
    return {
        **goal_out,
        "lowMatchTarget": destination,
        "rankedBy": "llm" if checked["order"] else "formula", "llmStatus": status, "scenario": scenario,
        "inputs": {"profileUpdatedAt": profile.updated_at, "signalsRunId": run_id,
                   "forecastAsOf": as_of["forecast"], "skillsAsOf": as_of["skills"]},
        "targetRoleId": profile.target_role if profile.target_role in pathway_ids else None, "roles": ranked,
        "scenarioLabel": SCENARIO_LABELS[scenario],
        "lowMatch": [{"roleId": r["role_id"], "name": r["name"], "matchPct": round(r["match_score"] * 100)}
                     for r in out["low_match"]],
        "notRanked": [{"roleId": r["role_id"], "name": r["name"], "note": r.get("note")} for r in out["not_ranked"]],
        "unmappedSkills": unmapped, "formula": out["formula"]["rank_score"],
        "formulaWeights": {"match": out["formula"]["match_weight"], "future": out["formula"]["future_weight"]},
    }


def _apply_coaching(steps: list[dict], checked: Mapping[str, Any]) -> list[dict]:
    """New step list: LLM order (within stages) and the chosen verified resource; the rest stays as code built it."""
    by_skill = {s["skill"]: s for s in steps}
    order = checked["order"] or [s["skill"] for s in steps]
    result = []
    for skill in order:
        step, llm = dict(by_skill[skill]), checked["steps"].get(skill, {})
        chosen = llm.get("resource")
        if chosen and step["resource"] and chosen["url"] != step["resource"]["url"]:
            options = [step["resource"], *step["alternatives"]]
            step["resource"] = dict(chosen)
            step["alternatives"] = [o for o in options if o["url"] != chosen["url"]]
            step["minutes"] = chosen["minutes"]
        step["reasons"] = llm.get("reasons") or step["reasons"]
        step["whyForYou"] = llm.get("whyForYou")
        result.append(step)
    for i, step in enumerate(result, start=1):
        step["order"] = i
    return result


def _task_out(t: Mapping[str, Any]) -> dict:
    return {"id": t["id"], "step": t["step"], "skill": t["skill"], "stage": t["stage"], "title": t["title"],
            "minutes": t["minutes"], "date": t["date"], "resourceTitle": t["resource_title"],
            "resourceUrl": t["resource_url"], "reason": t["reason"], "sdg": t["sdg"]}


def _employer_funded(skill: str, hrd: Mapping[str, Any] | None) -> dict | None:
    hrd = hrd or {}
    p = next((p for p in hrd.get("programmes") or [] if p.get("skill") == skill), None)
    if p is None:
        return None
    return {"title": p["title"], "provider": p["provider"], "url": p["url"], "days": p["days"], "feeMyr": p["fee_myr"],
            "hrdStatus": p["hrd_status"], "checkedOn": hrd.get("checked_on")}


def _step_out(s: Mapping[str, Any]) -> dict:
    return {"order": s["order"], "skill": s["skill"], "stage": s["stage"], "stageLabel": s["stage_label"],
            "reason": s["reason"], "reasons": s["reasons"], "whyForYou": s.get("whyForYou"), "resource": s["resource"],
            "resourceNote": s["resource_note"], "alternatives": s["alternatives"], "minutes": s["minutes"],
            "trendLabel": s["trend_label"], "sdg": s["sdg"], "sdgTags": sdg_tags(s["sdg"], "data/taxonomy.json"),
            "sdgReason": s.get("sdg_reason"), "startDate": s.get("start_date"),
            "deadline": s.get("deadline"), "taskIds": s.get("task_ids", []), "source": s["source"]}


def pathway(profile: Profile, role_id: str, momentum_rows: Sequence[Mapping], run_id: str | None, db_path: Path, *,
            scenario: str = "moderate", hours_per_week: float = 5, start_date: date | None = None,
            use_llm: bool = True, call: Callable = call_model, data: Mapping[str, Any] | None = None,
            goal: str | None = None) -> dict:
    """GET /api/pathway: the reskilling pathway to one role, with dated tasks (§4.3). Raises RoleNotFound."""
    data = data or load_data()
    out, held, _ = _match(profile, data, scenario)
    role = next((r for r in out["roles"] + out["low_match"] if r["role_id"] == role_id), None)
    if role is None:
        raise RoleNotFound(role_id)
    today = (start_date or pathway_mod.today_myt()).isoformat()
    state = profile.plan if profile.plan and profile.plan.role_id == role_id else None
    scores = pathway_mod._skill_index(data["scores"])
    declined = planner.active_declined(profile.plan, today)
    gap = [g for g in role["gap"] if g["skill"] not in declined]
    gap += planner.pushed_gap(state, held, [g["skill"] for g in gap], scores)
    other_gaps = [r["gap"] for r in out["roles"] if r["role_id"] != role_id]
    plan = pathway_mod.build_pathway(role["name"], gap, [gap] + other_gaps, data["scores"], data["resources"],
                                     scenario=scenario, hours_per_week=hours_per_week,
                                     start_date=state.start_date if state else today, taxonomy=data["taxonomy"])
    as_of = _as_of(profile, data, run_id)
    momentum, links = _momentum(momentum_rows), chip_mod.watch_map(data["taxonomy"], _watch_terms(momentum_rows))
    steps = []
    for s in plan["steps"]:
        chips = chip_mod.step_chips(s, role["name"], momentum, links, as_of)
        steps.append({**s, "chips": chips,
                      "reasons": sorted(chips, key=lambda c: -c["strength"])[:STEP_REASONS_SHOWN]})

    status, checked = "off:NO_STEPS", {"order": None, "steps": {}}
    if steps and use_llm:
        try:
            coaching, status = coach(db_path, sorted(held), role["name"], steps, call, _tag(as_of, scenario))
            checked = verify_coaching(coaching, steps, held, [t["skill"] for t in data["taxonomy"]])
        except LlmUnavailable as exc:
            status = f"off:{exc.code}"
    elif not use_llm:
        status = "off:SWITCHED_OFF"
    kept = checked["order"] or any(any(v.values()) for v in checked["steps"].values())
    personalised = status in ("llm", "cached") and bool(kept)  # only claim AI if the verifier kept something
    if personalised:
        steps = _apply_coaching(steps, checked)
    linked = sdg_mod.goal_skills(data["taxonomy"], data.get("role_sdg") or {}, goal) if goal else set()
    if goal:  # order inside a stage only; the scheduler below re-dates the steps
        steps = sdg_mod.goal_first(steps, linked)
    tasks = pathway_mod.schedule_tasks(steps, hours_per_week, date.fromisoformat(plan["start_date"]))
    minutes = sum(t["minutes"] for t in tasks)
    planned = [s["skill"] for s in steps]
    change = planner.diff(state, steps, held, scores)
    offer = None if change else planner.trend_offer(
        profile.plan if state else None, today, held, planned + [g["skill"] for g in role["gap"]], other_gaps, scores,
        momentum, links, {r["skill"] for r in data["resources"]["resources"]}, plan["skill_scores_as_of"])
    # Saved by the API without asking: the first plan for a role, or a plan that only lost skills the user now holds.
    silent = state is None or (change is None and set(state.skills) != set(planned))
    pushed = set(state.pushed) if state else set()
    sdg_lines = sdg_mod.plan_sdg_summary(plan, role, data.get("role_sdg") or {}, goal)["lines"]
    if goal and not linked & set(planned):
        meta = sdg_mod._sector_meta(data["role_sdg"], goal)
        sdg_lines.append(f"None of your gap skills link to {meta['name']} (SDG {' / '.join(meta['sdg'])}).")
    return {
        "planId": role_id, "change": change, "offer": offer,
        "outlookChange": planner.outlook_change(state, role_id, ledger_mod.read(current_data_dir())),
        "planState": planner.accept(profile.plan, role_id, planned, today, ledger_now()) if silent else None,
        "roleId": role_id, "targetRole": role["name"], "matchPct": round(role["match_score"] * 100),
        "scenario": scenario, "scenarioLabel": plan["scenario_label"], "hoursPerWeek": hours_per_week,
        "startDate": plan["start_date"], "finishDate": tasks[-1]["deadline"] if tasks else None,
        "skillsAsOf": plan["skill_scores_as_of"], "signalsRunId": run_id,
        "personalisedBy": "llm" if personalised else "formula", "llmStatus": status,
        "stages": [{"name": st["name"], "label": st["label"],
                    "skills": [s["skill"] for s in steps if s["stage"] == st["name"]]} for st in plan["stages"]],
        "steps": [{**_step_out(s), "employerFunded": _employer_funded(s["skill"], data.get("hrd")), "pushed": s["skill"] in pushed, "goalLinked": bool(s.get("goalLinked"))} for s in steps], "tasks": [_task_out(t) for t in tasks],
        "unresolved": [s["skill"] for s in steps if not s["resource"]],
        "totals": {"steps": len(steps), "tasks": len(tasks), "minutes": minutes, "hours": round(minutes / 60, 1)},
        "notes": plan["notes"],
        "sdgSummary": {**plan["sdg_summary"], "lines": sdg_lines},
        "roleSdg": _role_sdg(role, data), "mycol": mycol_by_role(data).get(role_id, []),
    }
