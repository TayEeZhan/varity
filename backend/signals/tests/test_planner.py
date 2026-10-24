"""Plan memory (advisor/planner.py): stable plans, learned skills, re-plan Keep / Revert, trend-gated offers."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from advisor import planner, service
from intake.models import PlanState
from trendsignal.jobs import load_context
from trendsignal.web.accounts_store import token_owner
from trendsignal.web.app import create_app
from trendsignal.web.cv_api import load_profile, save_profile

TODAY = "2026-10-26"


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


@pytest.fixture
def token(client):
    review = client.post("/api/cv/extract", json={"sample": "aina"}).json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    token = client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept}).json()["data"]["token"]
    roles = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()["data"]["roles"]
    client.post("/api/profile/target-role", json={"roleId": roles[0]["roleId"]}, headers={"X-Profile-Token": token})
    return token


def news(this_week, before, weekly, skill="w"):
    return {"skill": skill, "this_week": this_week, "weekly_average_before": before,
            "momentum": (this_week - before) / max(before, 1), "weekly_counts": weekly}


def state(**kw):
    return PlanState(role_id="r", start_date=TODAY, accepted_at=f"{TODAY}T00:00:00Z", **kw)


# ── pure rules ────────────────────────────────────────────────────

def test_news_must_be_big_enough_and_hold_for_three_weeks():
    assert planner.news_rising(news(6, 2, [6, 4, 3, 1, 1]))
    assert not planner.news_rising(news(6, 2, [6, 1, 3, 1, 1]))   # dipped last week: a spike, not a trend
    assert not planner.news_rising(news(2, 0.5, [2, 1, 1, 0, 0]))  # too few stories
    assert not planner.news_rising(news(5, 4, [5, 4, 4, 4, 4]))    # not enough rise
    assert not planner.news_rising(None)


def test_diff_hides_skills_the_user_learned():
    steps = [{"skill": "RAG", "reason": "r"}, {"skill": "Go", "reason": "g"}]
    old = state(skills=("RAG", "Docker", "Python"))
    change = planner.diff(old, steps, held={"Python"}, scores={"Docker": {"trend_label": "Falling"}})
    assert change == {"added": [{"skill": "Go", "reason": "g"}],
                      "removed": [{"skill": "Docker", "reason": "Job posts asking for Docker are now falling."}]}
    assert planner.diff(state(skills=("RAG", "Go", "Python")), steps, {"Python"}, {}) is None
    assert planner.diff(None, steps, set(), {}) is None


def offer(st, scores, rows, held=(), planned=(), resources=frozenset({"Rust", "Terraform"})):
    gaps = [[{"skill": "Rust"}, {"skill": "Terraform"}]]
    links = {"Rust": "rust-w", "Terraform": "tf-w"}
    return planner.trend_offer(st, TODAY, held, planned, gaps, scores, rows, links, set(resources), "2026-09")


def test_offer_needs_news_and_job_posts_to_agree():
    rising = {"Rust": {"trend_label": "Rising"}, "Terraform": {"trend_label": "Rising"}}
    rows = {"rust-w": news(9, 2, [9, 5, 3], "rust-w"), "tf-w": news(5, 2, [5, 4, 4], "tf-w")}
    got = offer(state(), rising, rows)
    assert got["skill"] == "Rust" and "9 AI stories" in got["news"] and "rising" in got["jobs"]
    assert offer(state(), {"Rust": {"trend_label": "No clear change"}}, rows) is None           # news only
    assert offer(state(), rising, {"rust-w": news(1, 1, [1, 1, 1])}) is None                    # job posts only
    assert offer(state(), rising, rows, held={"Rust"})["skill"] == "Terraform"                  # already known
    assert offer(state(), rising, rows, resources={"Terraform"})["skill"] == "Terraform"        # no checked resource
    assert offer(state(offers="off"), rising, rows) is None
    assert offer(None, rising, rows) is None


def test_offer_budget_and_not_now():
    rising = {"Rust": {"trend_label": "Rising"}}
    rows = {"rust-w": news(9, 2, [9, 5, 3])}
    asked = planner.answer_offer(state(), "Rust", add=False, today=TODAY, now=f"{TODAY}T09:00:00Z")
    assert offer(asked, rising, rows) is None                                                   # once a week
    later = asked.model_copy(update={"last_offer_at": "2026-10-01T00:00:00Z"})
    assert offer(later, rising, rows) is None                                                   # "Not now" lasts 30 days
    assert offer(later.model_copy(update={"declined": ()}), rising, rows)["skill"] == "Rust"
    added = planner.answer_offer(state(), "Rust", add=True, today=TODAY, now=TODAY)
    assert added.pushed == ("Rust",)
    assert planner.pushed_gap(added, held=set(), gap_skills=[], scores=rising)[0]["skill"] == "Rust"
    assert planner.pushed_gap(added, set(), [], {"Rust": {"trend_label": "Falling"}}) == []      # dropped when it falls


# ── service and API ───────────────────────────────────────────────

def _profile(settings, token):
    return load_profile(settings, token_owner(token))


def test_dates_stay_fixed_after_the_plan_is_accepted(settings, token):
    profile, data = _profile(settings, token), service.load_data()
    role = profile.target_role
    first = service.pathway(profile, role, [], None, settings.db_path, use_llm=False, data=data, start_date=date(2026, 10, 26))
    assert first["planState"].start_date == "2026-10-26" and first["change"] is None
    kept = profile.model_copy(update={"plan": first["planState"]})
    tue = service.pathway(kept, role, [], None, settings.db_path, use_llm=False, data=data, start_date=date(2026, 10, 27))
    assert [(t["id"], t["date"]) for t in tue["tasks"]] == [(t["id"], t["date"]) for t in first["tasks"]]
    assert tue["planState"] is None  # nothing to save: same plan


def test_learned_skill_leaves_the_plan_without_a_banner(client, token):
    headers = {"X-Profile-Token": token}
    plan = client.get("/api/pathway", headers=headers).json()["data"]
    skill = plan["steps"][0]["skill"]
    saved = client.post("/api/profile/learned", json={"skill": skill}, headers=headers).json()["data"]["profile"]
    learned = next(s for s in saved["skills"] if s["name"] == skill)
    assert learned["basis"] == "self_reported" and learned["evidence"][0]["source"] == "pathway"
    after = client.get("/api/pathway", headers=headers).json()["data"]
    assert skill not in [s["skill"] for s in after["steps"]]
    assert after["change"] is None and after["matchPct"] >= plan["matchPct"]
    assert client.post("/api/profile/learned", json={"skill": "Cobol"}, headers=headers).status_code == 422


def _pretend_old_plan(settings, token, skills):
    profile = _profile(settings, token)
    save_profile(settings, token_owner(token), profile.model_copy(update={"plan": profile.plan.model_copy(update={"skills": skills})}))


def test_changed_plan_can_be_kept_or_reverted(settings, client, token):
    headers = {"X-Profile-Token": token}
    plan = client.get("/api/pathway", headers=headers).json()["data"]
    skills = [s["skill"] for s in plan["steps"]]
    new_skill = skills[-1]
    _pretend_old_plan(settings, token, tuple(skills[:-1]) + ("Perl",))  # old plan: no new_skill, had Perl

    changed = client.get("/api/pathway", headers=headers).json()["data"]
    assert [a["skill"] for a in changed["change"]["added"]] == [new_skill]
    assert [r["skill"] for r in changed["change"]["removed"]] == ["Perl"]

    body = {"roleId": plan["roleId"], "action": "revert"}
    reverted = client.post("/api/pathway/decision", json=body, headers=headers).json()["data"]
    assert new_skill not in [s["skill"] for s in reverted["steps"]] and reverted["change"] is None
    assert _profile(settings, token).plan.declined[0].skill == new_skill
    assert client.post("/api/pathway/decision", json=body, headers=headers).json()["meta"]["code"] == "NO_CHANGE"

    _pretend_old_plan(settings, token, tuple(skills[1:-1]))  # now the first skill looks new
    kept = client.post("/api/pathway/decision", json={"roleId": plan["roleId"], "action": "keep"}, headers=headers).json()["data"]
    assert skills[0] in [s["skill"] for s in kept["steps"]] and kept["change"] is None


def test_offer_answers_need_a_live_offer(client, token):
    headers = {"X-Profile-Token": token}
    plan = client.get("/api/pathway", headers=headers).json()["data"]
    assert plan["offer"] is None  # the test database has no trend stories
    body = {"roleId": plan["roleId"], "action": "add", "skill": "Rust"}
    assert client.post("/api/pathway/decision", json=body, headers=headers).json()["meta"]["code"] == "NO_OFFER"
