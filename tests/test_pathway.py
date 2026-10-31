"""Tests for engine/pathway.py. Fixtures only: no network."""

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine import pathway as pw

DATA = Path(__file__).resolve().parent.parent / "data"
MONDAY = "2026-10-26"
FIXED_NOW = datetime(2026, 10, 22, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- fixtures

def score(skill, share, status="ok", trend="No clear change", stance="neutral",
          last12=None, prev12=None, sdg=("8.2",)):
    """One skill_scores.json record with only the keys the engine reads."""
    m12, p12 = last12 or (100, 1000)
    m_prev, p_prev = prev12 or (100, 1000)
    return {
        "skill": skill, "sdg": list(sdg), "demand_share_latest": share, "status": status,
        "trend_label": trend, "stance": stance, "ai_exposure": 0.5,
        "mentions_last12": m12, "posts_last12": p12, "mentions_prev12": m_prev, "posts_prev12": p_prev,
        "sources": [{"name": f"Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=1",
                     "date": "2026-10-01"}],
    }


def gap_item(skill, weight, status="ok", trend="No clear change", stance="neutral"):
    return {"skill": skill, "weight": weight, "status": status, "trend_label": trend, "stance": stance}


def res(skill, minutes=90, title=None, url=None, hrd=False, status=200, **extra):
    rec = {"skill": skill, "title": title or f"{skill} course", "url": url or f"https://example.org/{skill}",
           "provider": "Example", "cost": "free", "format": "tutorial", "minutes": minutes,
           "level": "beginner", "hrd_corp": hrd, "checked": "2026-10-22", "check_status": status}
    rec.update(extra)
    return rec


@pytest.fixture
def taxonomy():
    return [
        {"skill": "Go", "sdg": ["8.2"], "sdg_reason": "Go reason (8.2)."},
        {"skill": "Kubernetes", "sdg": ["8.2", "7.3"], "sdg_reason": "K8s reason (8.2, 7.3)."},
        {"skill": "Docker", "sdg": ["4.4"], "sdg_reason": "Docker reason (4.4)."},
        {"skill": "RAG", "sdg": ["4.4", "16.6"], "sdg_reason": "RAG reason (4.4, 16.6)."},
        {"skill": "Perl", "sdg": ["8.5"], "sdg_reason": "Perl reason (8.5)."},
        {"skill": "SQL", "sdg": ["4.4"], "sdg_reason": "SQL reason (4.4)."},
        {"skill": "Kafka", "sdg": ["8.2"], "sdg_reason": "Kafka reason (8.2)."},
    ]


@pytest.fixture
def scores():
    """Six gap skills with shares 0.30, 0.20, 0.10, 0.05, 0.02 and 0.01."""
    return {"as_of": "2026-10", "skills": [
        score("Docker", 0.30),
        score("SQL", 0.20),
        score("Go", 0.10, last12=(81, 1000), prev12=(68, 1000), trend="Rising"),
        score("Kubernetes", 0.05),
        score("RAG", 0.02, trend="Rising", stance="AI-complement", last12=(25, 1000), prev12=(13, 1000)),
        score("Kafka", 0.01, status="low_volume"),
        score("Perl", 0.0, status="rare", trend=None),
    ]}


@pytest.fixture
def resources():
    return {"resources": [res("Go", 180), res("Kubernetes", 90), res("Docker", 90), res("RAG", 90),
                          res("SQL", 60), res("Kafka", 45), res("Perl", 30)]}


@pytest.fixture
def staging_case(scores):
    """Role gap for the target role, and the gaps of the roles counted (target first).

    Docker: in all 3 roles (no-regret). Go: in 2 roles, Rising, not Falling (no-regret).
    Kubernetes: 1 role only, ok, share rank 4 of 5.
    """
    docker = gap_item("Docker", 0.9)
    go = gap_item("Go", 0.8, trend="Rising")
    sql = gap_item("SQL", 0.7)
    k8s = gap_item("Kubernetes", 0.6)
    rag = gap_item("RAG", 0.5, trend="Rising", stance="AI-complement")
    kafka = gap_item("Kafka", 0.4, status="low_volume")
    gap = [docker, go, sql, k8s, rag, kafka]
    top = [gap, [docker, go], [docker]]
    return gap, top


def stages_of(path):
    return {s["skill"]: s["stage"] for s in path["steps"]}


def build(gap, top, scores, resources, taxonomy, **kw):
    kw.setdefault("start_date", MONDAY)
    return pw.build_pathway("Backend Engineer", gap, top, scores, resources, taxonomy=taxonomy, **kw)


# ---------------------------------------------------------------- stage rules

def test_no_regret_needs_two_of_top_three_roles_and_not_falling(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    st = stages_of(build(gap, top, scores, resources, taxonomy))
    assert st["Docker"] == "no_regret"          # 3 roles
    assert st["Go"] == "no_regret"              # 2 roles, Rising
    assert st["Kubernetes"] != "no_regret"      # 1 role


def test_falling_skill_is_never_no_regret(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    gap = [dict(g, trend_label="Falling") if g["skill"] == "Docker" else g for g in gap]
    top = [[dict(g, trend_label="Falling") if g["skill"] == "Docker" else g for g in t] for t in top]
    st = stages_of(build(gap, top, scores, resources, taxonomy))
    assert st["Docker"] == "near_term"   # still high demand now, so stage 2, not 1


def test_every_given_role_is_counted_not_only_three(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    kafka_in_roles = [[gap_item("Kafka", 1.0)], [], [], [gap_item("Kafka", 1.0)], [gap_item("Kafka", 1.0)]]
    classified = pw.classify(gap, kafka_in_roles, scores)
    assert classified["Kafka"]["stage"] == "no_regret"   # 3 of 5 roles
    assert classified["Kafka"]["roles_needing"] == 3
    assert classified["Kafka"]["roles_total"] == 5


def test_ai_substitutable_skill_is_never_no_regret(scores):
    gap = [gap_item("Docker", 0.9, stance="AI-substitutable"), gap_item("SQL", 0.8)]
    c = pw.classify(gap, [gap, gap, gap], scores)
    assert c["SQL"]["stage"] == "no_regret"
    assert c["Docker"]["stage"] != "no_regret"
    assert c["Docker"]["stage"] == "near_term"   # still a high share now


def test_near_term_is_status_ok_and_top_half_of_gap_by_share(scores, resources, taxonomy):
    gap = [gap_item(s, 0.5) for s in ("Docker", "SQL", "Go", "Kubernetes", "Kafka")]
    gap.insert(4, gap_item("RAG", 0.5, trend="Rising", stance="AI-complement"))
    c = pw.classify(gap, [gap], scores)  # one role only: nothing is no-regret
    # shares: Docker .30, SQL .20, Go .10 are the top half (3 of 6)
    assert c["Docker"]["stage"] == "near_term"
    assert c["SQL"]["stage"] == "near_term"
    assert c["Go"]["stage"] == "near_term"      # Rising, but near-term has precedence
    assert c["Kubernetes"]["stage"] == "other"  # share rank 4, no trend
    assert c["RAG"]["stage"] == "future_bet"
    assert c["Kafka"]["stage"] == "other"


def test_low_volume_skill_is_not_near_term_even_with_a_high_share(scores):
    sc = {"skills": [score("Docker", 0.30, status="low_volume"), score("SQL", 0.01)]}
    gap = [gap_item("Docker", 0.5, status="low_volume"), gap_item("SQL", 0.4)]
    c = pw.classify(gap, [gap], sc)
    assert c["Docker"]["stage"] == "other"


def test_future_bet_is_rising_or_ai_complement(scores):
    sc = {"skills": [score("Go", 0.001, trend="Rising"), score("RAG", 0.001, stance="AI-complement"),
                     score("Perl", 0.2), score("SQL", 0.3)]}
    gap = [gap_item("SQL", 1.0), gap_item("Perl", 0.9), gap_item("Go", 0.5, trend="Rising"),
           gap_item("RAG", 0.4, stance="AI-complement")]
    c = pw.classify(gap, [gap], sc)
    assert c["Go"]["stage"] == "future_bet"
    assert c["RAG"]["stage"] == "future_bet"


def test_skill_that_fits_no_stage_goes_after_stage_2_and_before_stage_3(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    path = build(gap, top, scores, resources, taxonomy)
    order = [s["stage"] for s in path["steps"]]
    assert order.index("other") > max(i for i, s in enumerate(order) if s == "near_term")
    assert order.index("other") < order.index("future_bet")
    assert [s["name"] for s in path["stages"]] == ["no_regret", "near_term", "other", "future_bet"]


def test_within_a_stage_skills_are_sorted_by_role_weight(scores, resources, taxonomy):
    gap = [gap_item("Docker", 0.2), gap_item("SQL", 0.9), gap_item("Go", 0.5)]
    top = [gap, gap, gap]
    path = build(gap, top, scores, resources, taxonomy)
    assert [s["skill"] for s in path["steps"]] == ["SQL", "Go", "Docker"]


def test_fast_scenario_moves_future_bets_to_second_place(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    moderate = build(gap, top, scores, resources, taxonomy, scenario="moderate")
    fast = build(gap, top, scores, resources, taxonomy, scenario="fast")
    assert [s["name"] for s in moderate["stages"]] == ["no_regret", "near_term", "other", "future_bet"]
    assert [s["name"] for s in fast["stages"]] == ["no_regret", "future_bet", "near_term", "other"]
    fast_skills = [s["skill"] for s in fast["steps"]]
    assert fast_skills.index("RAG") < fast_skills.index("SQL")
    assert fast_skills.index("RAG") > fast_skills.index("Docker")
    assert sorted(fast_skills) == sorted(s["skill"] for s in moderate["steps"])
    assert "speeds up" in fast["scenario_label"] and "estimate" in fast["scenario_label"]


def test_reasons_use_the_numbers(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    steps = {s["skill"]: s for s in build(gap, top, scores, resources, taxonomy)["steps"]}
    assert steps["Docker"]["reason"].startswith("Needed by 3 of the 3 roles counted")
    assert steps["Go"]["reason"].startswith("Needed by 2 of the 3 roles counted")
    assert steps["RAG"]["reason"] == "Rising: 2.5% of posts vs 1.3% in the 12 months before."
    assert "20.0%" in steps["SQL"]["reason"] and "top half" in steps["SQL"]["reason"]
    assert "Too few posts to forecast" in steps["Kafka"]["reason"]


def test_rising_reason_matches_the_data_contract_example():
    sc = {"skills": [score("Go", 0.001, trend="Rising", last12=(81, 1000), prev12=(68, 1000)),
                     score("SQL", 0.3), score("Docker", 0.2)]}
    gap = [gap_item("Go", 1.0, trend="Rising"), gap_item("SQL", 0.5), gap_item("Docker", 0.4)]
    path = pw.build_pathway("X", gap, [gap], sc, {"resources": []}, taxonomy=[], start_date=MONDAY)
    go = next(s for s in path["steps"] if s["skill"] == "Go")
    assert go["reason"] == "Rising: 8.1% of posts vs 6.8% in the 12 months before."


def test_step_carries_source_line_and_sdg_with_reason(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    steps = {s["skill"]: s for s in build(gap, top, scores, resources, taxonomy)["steps"]}
    k8s = steps["Kubernetes"]
    assert k8s["sdg"] == ["8.2", "7.3"]
    assert k8s["sdg_reason"] == "K8s reason (8.2, 7.3)."
    assert "Ask HN: Who is hiring? (October 2026) (2026-10-01)" in k8s["source"]
    assert "as of 2026-10" in k8s["source"]


def test_skill_without_a_source_says_so(resources, taxonomy):
    sc = {"skills": [score("Perl", 0.0, status="rare", trend=None)]}
    sc["skills"][0]["sources"] = []
    gap = [gap_item("Perl", 1.0, status="rare", trend=None)]
    step = build(gap, [gap], sc, resources, taxonomy)["steps"][0]
    assert step["source"] == "No dated source in skill_scores.json for this skill."


def test_duplicate_gap_skills_and_unknown_skills_do_not_crash(resources, taxonomy):
    gap = [gap_item("Go", 0.9), gap_item("Go", 0.1), gap_item("Unknown thing", 0.2)]
    path = pw.build_pathway("X", gap, [gap], {"skills": []}, resources, taxonomy=taxonomy, start_date=MONDAY)
    assert [s["skill"] for s in path["steps"]] == ["Go", "Unknown thing"]
    unknown = path["steps"][1]
    assert unknown["resource"] is None and unknown["sdg"] == []


def test_top_roles_may_be_role_results_with_a_gap_key(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    wrapped = [{"role": f"R{i}", "gap": g} for i, g in enumerate(top)]
    assert stages_of(build(gap, wrapped, scores, resources, taxonomy)) == stages_of(
        build(gap, top, scores, resources, taxonomy))


def test_empty_gap_gives_an_empty_pathway(scores, resources, taxonomy):
    path = build([], [], scores, resources, taxonomy)
    assert path["steps"] == [] and path["tasks"] == [] and path["finish_date"] is None
    assert path["sdg_summary"]["counts"] == {}
    assert "no SDG tags" in path["sdg_summary"]["line"]


def test_bad_arguments_raise(scores, resources, taxonomy):
    with pytest.raises(ValueError, match="scenario"):
        build([], [], scores, resources, taxonomy, scenario="slow")
    with pytest.raises(ValueError, match="hours_per_week"):
        build([], [], scores, resources, taxonomy, hours_per_week=0)


# ---------------------------------------------------------------- resources: never invented

def test_skill_without_a_resource_gets_the_placeholder_and_no_tasks(scores, taxonomy):
    gap = [gap_item("Docker", 0.9), gap_item("Go", 0.8)]
    only_docker = {"resources": [res("Docker", 60)]}
    path = build(gap, [gap], scores, only_docker, taxonomy)
    go = next(s for s in path["steps"] if s["skill"] == "Go")
    assert go["resource"] is None
    assert go["resource_note"] == "No verified free resource yet"
    assert go["minutes"] == 0 and go["task_ids"] == []
    assert path["unresolved"] == ["Go"]
    assert {t["skill"] for t in path["tasks"]} == {"Docker"}
    assert "No verified free resource yet" in pw.to_markdown(path)


def test_unchecked_or_non_https_resources_are_ignored(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    bad = {"resources": [res("Docker", 60, status=404), res("Docker", 60, url="http://example.org/d"),
                         res("Docker", 0)]}
    step = build(gap, [gap], scores, bad, taxonomy)["steps"][0]
    assert step["resource"] is None


def test_chosen_resource_comes_from_resources_json_only(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    known_urls = {r["url"] for r in resources["resources"]}
    for step in build(gap, top, scores, resources, taxonomy)["steps"]:
        assert step["resource"]["url"] in known_urls


def test_verified_hrd_corp_resource_is_preferred_and_others_are_kept_as_alternatives(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    rs = {"resources": [res("Docker", 90, title="Free docs", url="https://example.org/a"),
                        res("Docker", 120, title="HRD course", url="https://example.org/b", hrd=True)]}
    step = build(gap, [gap], scores, rs, taxonomy)["steps"][0]
    assert step["resource"]["title"] == "HRD course"
    assert [a["title"] for a in step["alternatives"]] == ["Free docs"]
    assert step["minutes"] == 120


def test_resources_may_be_a_plain_list(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    step = build(gap, [gap], scores, [res("Docker", 60)], taxonomy)["steps"][0]
    assert step["resource"]["minutes"] == 60


# ---------------------------------------------------------------- daily tasks

@pytest.mark.parametrize("minutes", [30, 45, 46, 90, 100, 600])
@pytest.mark.parametrize("hours", [2.5, 5, 10])
def test_tasks_never_exceed_45_minutes_and_add_up(scores, taxonomy, minutes, hours):
    gap = [gap_item("Docker", 0.9)]
    path = build(gap, [gap], scores, {"resources": [res("Docker", minutes)]}, taxonomy, hours_per_week=hours)
    mins = [t["minutes"] for t in path["tasks"]]
    assert max(mins) <= 45 and min(mins) > 0
    assert sum(mins) == minutes
    assert path["totals"]["minutes"] == minutes
    assert [t["part"] for t in path["tasks"]] == list(range(1, len(mins) + 1))
    assert all(t["parts"] == len(mins) for t in path["tasks"])


def test_task_ids_are_unique_and_ordered(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    tasks = build(gap, top, scores, resources, taxonomy)["tasks"]
    ids = [t["id"] for t in tasks]
    assert len(set(ids)) == len(ids)
    assert ids == [f"{pw.task_slug(t['skill'])}-{t['part']}" for t in tasks]


def test_task_ids_survive_an_added_skill(scores, resources, taxonomy):
    docker = [gap_item("Docker", 0.9)]
    both = [gap_item("Go", 0.95), gap_item("Docker", 0.9)]
    before = {t["id"] for t in build(docker, [docker], scores, resources, taxonomy)["tasks"]}
    after = {t["id"] for t in build(both, [both], scores, resources, taxonomy)["tasks"]}
    assert before and before <= after  # ticks keyed by id still match after the plan grows
    assert pw.task_slug("JavaScript / TypeScript") == "javascript-typescript"


def test_dates_follow_start_date_on_weekdays_with_a_daily_budget(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    # 5 h a week = 60 min a day. 300 min: 45+15 each day, five days = one week.
    path = build(gap, [gap], scores, {"resources": [res("Docker", 300)]}, taxonomy, hours_per_week=5)
    by_day = {}
    for t in path["tasks"]:
        by_day.setdefault(t["date"], 0)
        by_day[t["date"]] += t["minutes"]
    assert list(by_day) == ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    assert all(v == 60 for v in by_day.values())
    assert path["start_date"] == "2026-10-26"
    assert path["finish_date"] == "2026-10-30"


def test_weekends_are_skipped(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    path = build(gap, [gap], scores, {"resources": [res("Docker", 450)]}, taxonomy, hours_per_week=5)
    days = {date.fromisoformat(t["date"]) for t in path["tasks"]}
    assert len(days) == 8 and all(d.weekday() < 5 for d in days)
    assert "2026-10-31" not in {t["date"] for t in path["tasks"]}  # Saturday
    assert path["finish_date"] == "2026-11-04"


def test_a_weekend_start_date_rolls_to_monday(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    path = build(gap, [gap], scores, {"resources": [res("Docker", 30)]}, taxonomy, start_date="2026-10-24")
    assert path["start_date"] == "2026-10-26"
    assert path["tasks"][0]["date"] == "2026-10-26"


def test_start_date_accepts_date_and_datetime_objects(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    for sd in (date(2026, 10, 26), datetime(2026, 10, 26, 8, 0)):
        path = build(gap, [gap], scores, {"resources": [res("Docker", 30)]}, taxonomy, start_date=sd)
        assert path["start_date"] == "2026-10-26"


def test_deadline_is_the_planned_day_and_step_deadline_is_the_last_task_of_the_step(scores, taxonomy):
    gap = [gap_item("Docker", 0.9), gap_item("SQL", 0.8)]
    rs = {"resources": [res("Docker", 120), res("SQL", 60)]}
    path = build(gap, [gap, gap, gap], scores, rs, taxonomy, hours_per_week=5)
    for t in path["tasks"]:
        assert t["deadline"] == t["date"]
    docker = [t for t in path["tasks"] if t["skill"] == "Docker"]
    assert {t["step_deadline"] for t in docker} == {docker[-1]["date"]}
    step = next(s for s in path["steps"] if s["skill"] == "Docker")
    assert step["start_date"] == docker[0]["date"] and step["deadline"] == docker[-1]["date"]
    assert step["task_ids"] == [t["id"] for t in docker]


def test_weekly_time_does_not_exceed_hours_per_week(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    path = build(gap, [gap], scores, {"resources": [res("Docker", 900)]}, taxonomy, hours_per_week=3)
    weeks = {}
    for t in path["tasks"]:
        monday = date.fromisoformat(t["date"]).isocalendar()[:2]
        weeks[monday] = weeks.get(monday, 0) + t["minutes"]
    assert max(weeks.values()) <= 3 * 60


def test_task_links_back_to_its_resource(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    path = build(gap, top, scores, resources, taxonomy)
    for t in path["tasks"]:
        step = path["steps"][t["step"] - 1]
        assert t["skill"] == step["skill"] and t["resource_url"] == step["resource"]["url"]
        assert t["title"].startswith(f"{t['skill']}: ")


# ---------------------------------------------------------------- progress

@pytest.fixture
def plan(scores, taxonomy):
    gap = [gap_item("Docker", 0.9), gap_item("SQL", 0.8)]
    rs = {"resources": [res("Docker", 90), res("SQL", 45)]}
    return build(gap, [gap, gap, gap], scores, rs, taxonomy, hours_per_week=5)


def test_progress_percent_is_weighted_by_minutes(plan):
    tasks = plan["tasks"]  # Docker 90 min then SQL 45 min, 60 min a day
    done = [tasks[0]["id"]]
    p = pw.progress(tasks, done, MONDAY)
    expected = round(100 * tasks[0]["minutes"] / sum(t["minutes"] for t in tasks), 1)
    assert p["percent_done"] == expected
    assert p["tasks_done"] == 1 and p["tasks_total"] == len(tasks)


def test_progress_with_nothing_or_everything_done(plan):
    ids = [t["id"] for t in plan["tasks"]]
    none = pw.progress(plan["tasks"], [], MONDAY)
    assert none["percent_done"] == 0.0 and none["next_task"]["id"] == ids[0] and none["completed_skills"] == []
    full = pw.progress(plan["tasks"], ids, "2027-01-01")
    assert full["percent_done"] == 100.0 and full["next_task"] is None
    assert full["overdue"] == [] and full["completed_skills"] == ["Docker", "SQL"]


def test_progress_with_no_tasks():
    p = pw.progress([], [], MONDAY)
    assert p["percent_done"] == 0.0 and p["next_task"] is None and p["overdue"] == []


def test_overdue_means_not_done_and_deadline_before_as_of(plan):
    tasks = plan["tasks"]
    first, second = tasks[0], tasks[1]
    assert first["deadline"] == "2026-10-26" and second["deadline"] == "2026-10-26"
    same_day = pw.progress(tasks, [], "2026-10-26")
    assert same_day["overdue"] == []                       # due today is not overdue yet
    next_day = pw.progress(tasks, [], "2026-10-27")
    assert [t["id"] for t in next_day["overdue"]] == [t["id"] for t in tasks if t["deadline"] < "2026-10-27"]
    cleared = pw.progress(tasks, [t["id"] for t in next_day["overdue"]], "2026-10-27")
    assert cleared["overdue"] == []


def test_next_task_is_the_first_not_done_task_in_plan_order(plan):
    tasks = plan["tasks"]
    p = pw.progress(tasks, [tasks[0]["id"], tasks[2]["id"]], MONDAY)
    assert p["next_task"]["id"] == tasks[1]["id"]


def test_skill_is_completed_only_when_all_its_tasks_are_done(plan):
    tasks = plan["tasks"]
    docker = [t["id"] for t in tasks if t["skill"] == "Docker"]
    assert len(docker) > 1
    assert pw.progress(tasks, docker[:-1], MONDAY)["completed_skills"] == []
    assert pw.progress(tasks, docker, MONDAY)["completed_skills"] == ["Docker"]


def test_unknown_done_ids_are_reported_not_counted(plan):
    p = pw.progress(plan["tasks"], ["T999", plan["tasks"][0]["id"]], MONDAY)
    assert p["unknown_ids"] == ["T999"] and p["tasks_done"] == 1


# ---------------------------------------------------------------- ICS

def unfold(text):
    return re.sub(r"\r\n[ \t]", "", text)


@pytest.fixture
def ics(plan):
    return pw.to_ics(plan["tasks"], now=FIXED_NOW)


def test_ics_has_valid_structure(ics, plan):
    lines = unfold(ics).split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and lines[-1] == ""
    assert "VERSION:2.0" in lines and any(l.startswith("PRODID:") for l in lines)
    assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == len(plan["tasks"])


def test_ics_uses_crlf_only(ics):
    assert "\n" not in ics.replace("\r\n", "")
    assert "\r" not in ics.replace("\r\n", "")
    assert ics.endswith("\r\n")


def test_ics_lines_are_folded_at_75_octets(ics):
    assert all(len(l.encode("utf-8")) <= 75 for l in ics.split("\r\n"))


def test_ics_events_carry_date_summary_description_and_url(ics, plan):
    flat = unfold(ics)
    events = re.findall(r"BEGIN:VEVENT\r\n(.*?)\r\nEND:VEVENT", flat, re.S)
    assert len(events) == len(plan["tasks"])
    for ev, task in zip(events, plan["tasks"]):
        props = dict(l.split(":", 1) for l in ev.split("\r\n"))
        day = task["date"].replace("-", "")
        assert props["DTSTART;VALUE=DATE"] == day
        assert props["DTSTAMP"] == "20261022T090000Z"
        assert props["UID"] == f"{pw.tasks_signature(plan['tasks'])}-{task['id']}-{task['date']}@verity.pathway"
        assert props["SUMMARY"].replace("\\,", ",") == task["title"]
        assert task["resource_url"] in props["DESCRIPTION"]
        assert props["URL"] == task["resource_url"]
    uids = re.findall(r"UID:(\S+)", flat)
    assert len(set(uids)) == len(uids)


def test_ics_escapes_special_characters_and_folds_utf8_safely():
    task = {"id": "T001", "date": "2026-10-26", "deadline": "2026-10-26", "minutes": 30,
            "title": "Go; Rust, C\\C++\nline", "resource_title": "Café " * 30,
            "resource_url": "https://example.org/x", "reason": "r"}
    out = pw.to_ics([task], now=FIXED_NOW)
    flat = unfold(out)
    assert "SUMMARY:Go\\; Rust\\, C\\\\C++\\nline" in flat
    assert all(len(l.encode("utf-8")) <= 75 for l in out.split("\r\n"))
    out.encode("utf-8").decode("utf-8")
    assert "Café Café" in flat


def test_ics_of_no_tasks_is_still_a_calendar():
    out = pw.to_ics([], now=FIXED_NOW)
    assert out.startswith("BEGIN:VCALENDAR\r\n") and out.endswith("END:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" not in out


# ---------------------------------------------------------------- Markdown

def test_markdown_export(scores, taxonomy):
    gap = [gap_item("Docker", 0.9), gap_item("Go", 0.8)]
    rs = {"resources": [res("Docker", 90, title="Docker docs", url="https://example.org/docker")]}
    path = build(gap, [gap, gap], scores, rs, taxonomy, scenario="fast")
    md = pw.to_markdown(path)
    assert md.startswith("# Reskilling pathway: Backend Engineer\n")
    assert "If AI speeds up (estimate)" in md
    assert "[Docker docs](https://example.org/docker)" in md
    assert "Needed by 2 of the 2 roles counted" in md
    assert "No verified free resource yet" in md          # Go has no resource
    assert "| docker-1 | 2026-10-26 | 45 |" in md
    assert "SDG 4.4: 1 step (Docker)" in md
    assert "HRD Corp-claimable status not verified" in md
    assert "estimate" in md.lower()
    assert "Source: data/skill_scores.json as of 2026-10" in md
    assert md.endswith("\n")


def test_markdown_marks_a_verified_hrd_corp_resource(scores, taxonomy):
    gap = [gap_item("Docker", 0.9)]
    rs = {"resources": [res("Docker", 90, hrd=True)]}
    assert "HRD Corp-claimable" in pw.to_markdown(build(gap, [gap], scores, rs, taxonomy)).split("## Daily tasks")[0]


# ---------------------------------------------------------------- SDG summary

def test_sdg_summary_counts_steps_per_target(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    summary = build(gap, top, scores, resources, taxonomy)["sdg_summary"]
    # Docker 4.4 | Go 8.2 | SQL 4.4 | Kubernetes 8.2, 7.3 | RAG 4.4, 16.6 | Kafka 8.2
    assert summary["counts"] == {"4.4": 3, "8.2": 3, "7.3": 1, "16.6": 1}
    assert list(summary["counts"]) == ["4.4", "8.2", "7.3", "16.6"]   # most steps first, then target
    assert summary["skills_by_target"]["7.3"] == ["Kubernetes"]


def test_sdg_line_is_built_only_from_sdg_reason_texts(scores, resources, taxonomy, staging_case):
    gap, top = staging_case
    summary = build(gap, top, scores, resources, taxonomy)["sdg_summary"]
    line = summary["line"]
    assert line.startswith("How this plan contributes: ")
    allowed = [t["sdg_reason"] for t in taxonomy]
    leftover = line.removeprefix("How this plan contributes: ")
    leftover = re.sub(r"SDG [\d.a-z]+ \(\d+\)[,.]?", "", leftover)
    for reason in allowed:
        leftover = leftover.replace(reason, "")
    assert leftover.strip() == ""
    assert any(r in line for r in allowed)


# ---------------------------------------------------------------- real data files

REQUIRED = {"skill", "title", "url", "provider", "cost", "format", "minutes", "level",
            "hrd_corp", "checked", "check_status"}


@pytest.fixture(scope="module")
def real_resources():
    return json.loads((DATA / "resources.json").read_text(encoding="utf-8"))


def test_real_resources_have_the_hrd_corp_note(real_resources):
    assert real_resources["hrd_corp_note"] == pw.HRD_CORP_NOTE
    assert "estimate" in real_resources["minutes_note"]


def test_every_real_resource_has_required_fields_https_and_status_200(real_resources):
    assert real_resources["resources"]
    for r in real_resources["resources"]:
        assert REQUIRED <= set(r), r
        assert r["url"].startswith("https://"), r["url"]
        assert r["check_status"] == 200, r["url"]
        assert isinstance(r["minutes"], int) and r["minutes"] > 0
        assert r["minutes_is_estimate"] is True
        assert isinstance(r["hrd_corp"], bool)
        assert r["cost"] in {"free", "free trial", "free audit", "low-cost"}
        assert r["level"] in {"beginner", "intermediate", "advanced"}
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["checked"])


def test_real_resources_cover_taxonomy_skills_only_and_have_no_duplicate_urls(real_resources):
    taxonomy = {t["skill"] for t in json.loads((DATA / "taxonomy.json").read_text(encoding="utf-8"))}
    skills = [r["skill"] for r in real_resources["resources"]]
    assert set(skills) <= taxonomy
    per_skill = {s: skills.count(s) for s in set(skills)}
    assert max(per_skill.values()) <= 2
    urls = [r["url"] for r in real_resources["resources"]]
    assert len(urls) == len(set(urls))


def test_no_real_resource_claims_hrd_corp_without_evidence(real_resources):
    # No official HRD Corp page listing a course was found, so nothing may claim it.
    for r in real_resources["resources"]:
        if r["hrd_corp"]:
            assert r.get("hrd_corp_source", "").startswith("https://hrdcorp.gov.my"), r["url"]


def test_pathway_on_the_real_data_files():
    scores = pw.load_skill_scores()
    by = {s["skill"]: s for s in scores["skills"]}
    names = ["Go", "Kubernetes", "Terraform", "PostgreSQL", "Docker", "Kafka"]
    gap = [gap_item(n, 1 - i / 10, by[n]["status"], by[n]["trend_label"], by[n]["stance"])
           for i, n in enumerate(names)]
    path = pw.build_pathway("Backend Engineer", gap, [gap, gap[:3], gap[:2]], scores,
                            pw.load_resources(), start_date=MONDAY)
    assert path["unresolved"] == []
    assert len(path["steps"]) == len(names)
    assert all(t["minutes"] <= 45 for t in path["tasks"])
    assert all(s["sdg"] and s["sdg_reason"] for s in path["steps"])
    assert pw.to_ics(path["tasks"]).count("BEGIN:VEVENT") == len(path["tasks"])


# ---------------------------------------------------------------- review fixes: time, UID, picking, SDG

class _FixedClock(datetime):
    """datetime whose now() is 01:00 on Monday 2026-10-26 in the zone asked for (UTC+8 here)."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 26, 1, 0, tzinfo=tz)


def test_today_myt_is_the_malaysia_date_not_the_utc_date(monkeypatch):
    utc_clock = datetime(2026, 10, 26, 1, 0, tzinfo=pw.MYT).astimezone(timezone.utc)
    assert utc_clock.date() == date(2026, 10, 25)          # still Sunday in UTC
    monkeypatch.setattr(pw, "datetime", _FixedClock)
    assert pw.today_myt() == date(2026, 10, 26)            # already Monday in Malaysia
    assert pw._as_date(None) == date(2026, 10, 26)


def test_default_start_date_uses_malaysia_today(monkeypatch, scores, resources, taxonomy):
    monkeypatch.setattr(pw, "datetime", _FixedClock)
    gap = [gap_item("Docker", 0.9)]
    path = pw.build_pathway("Backend Engineer", gap, [gap], scores, resources, taxonomy=taxonomy)
    assert path["start_date"] == "2026-10-26"               # a Monday: not rolled back to Sunday's date


def test_ics_uids_are_unique_across_two_plans(scores, resources, taxonomy):
    one = build([gap_item("Docker", 0.9)], [[gap_item("Docker", 0.9)]], scores, resources, taxonomy)
    two = build([gap_item("Go", 0.9)], [[gap_item("Go", 0.9)]], scores, resources, taxonomy)
    assert one["tasks"][0]["date"] == two["tasks"][0]["date"]   # same date: the UID must still differ
    uids = re.findall(r"UID:(\S+)", unfold(pw.to_ics(one["tasks"], now=FIXED_NOW) + pw.to_ics(two["tasks"], now=FIXED_NOW)))
    assert len(uids) == len(one["tasks"]) + len(two["tasks"]) and len(set(uids)) == len(uids)


def test_tasks_signature_changes_with_any_task_and_ignores_nothing_else():
    a = [{"id": "T001", "title": "Go: A (part 1 of 1)", "date": "2026-10-26"}]
    assert pw.tasks_signature(a) == pw.tasks_signature([dict(a[0])])
    assert pw.tasks_signature(a) != pw.tasks_signature([dict(a[0], title="Kubernetes: B (part 1 of 1)")])
    assert pw.tasks_signature(a) != pw.tasks_signature([dict(a[0], date="2026-10-27")])
    assert pw.tasks_signature(a) != pw.tasks_signature([dict(a[0], id="T002")])


def test_pick_resource_prefers_hrd_then_beginner_then_first_listed():
    inter = res("X", 60, title="Intermediate first", url="https://example.org/i", level="intermediate")
    begin = res("X", 60, title="Beginner second", url="https://example.org/b")
    chosen, alts = pw._pick_resource([inter, begin])
    assert chosen["title"] == "Beginner second" and [a["title"] for a in alts] == ["Intermediate first"]
    first, second = (res("X", 60, title="First", url="https://example.org/1", level="intermediate"),
                     res("X", 60, title="Second", url="https://example.org/2", level="intermediate"))
    assert pw._pick_resource([first, second])[0]["title"] == "First"
    hrd = res("X", 60, title="HRD", url="https://example.org/h", level="intermediate", hrd=True)
    assert pw._pick_resource([begin, hrd])[0]["title"] == "HRD"


def test_real_resources_pick_simple_rag_and_a_beginner_resource_where_one_exists(real_resources):
    index = pw._resource_index(real_resources)
    assert pw._pick_resource(index["RAG"])[0]["title"].startswith("Simple RAG")
    for skill, options in index.items():
        if any(o["level"] == "beginner" for o in options):
            assert pw._pick_resource(options)[0]["level"] == "beginner", skill


def test_real_resources_have_no_catalog_pages_for_mongodb_snowflake_and_gcp(real_resources):
    urls = {r["url"] for r in real_resources["resources"]}
    assert "https://learn.mongodb.com/" not in urls
    assert "https://www.snowflake.com/en/developers/guides/" not in urls
    assert "https://www.skills.google/" not in urls
    assert not [r for r in real_resources["resources"] if r["cost"] == "free audit"]
    minutes = {r["title"]: r["minutes"] for r in real_resources["resources"]}
    assert minutes["Scientific Computing with Python"] > 600 and minutes["Learn C++"] > 1200
    assert minutes["The Rust Programming Language (the Book)"] > 900 and minutes["React Quick Start"] < 300


def test_sdg_headline_uses_only_plan_numbers_and_says_rm0_only_when_all_free(scores, resources, taxonomy):
    gap = [gap_item("Docker", 0.9), gap_item("Go", 0.8), gap_item("Kafka", 0.5)]
    rs = {"resources": [res("Docker", 90), res("Go", 150)]}          # Kafka has no resource
    path = build(gap, [gap], scores, rs, taxonomy)
    outlook = {"trend_label": "Rising", "share_last12": 0.102, "share_prev12": 0.081}
    first, second = pw.sdg_headline(path, outlook)
    assert first == ("SDG 4.4 (indicator 4.4.1, ICT skills for employment): this plan adds 2 job-listed skills "
                     "in 4.0 hours (estimate) at RM0 cost using free resources.")
    assert second == ("SDG 8.5 (full and productive employment): moves you toward Backend Engineer "
                      "(role demand: Rising, 10.2% of posts in the last 12 months vs 8.1% the 12 months before).")
    paid = {"resources": [res("Docker", 90, cost="low-cost"), res("Go", 150)]}
    mostly = pw.sdg_headline(build(gap, [gap], scores, paid, taxonomy), None)
    assert "mostly free resources" in mostly[0] and "RM0" not in mostly[0]
    assert "no trend label: too few posts" in mostly[1]
