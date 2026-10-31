"""Role suggestions and pathway: mapping, chips, verifiers, the formula fallback and the three routes."""

import pytest
from fastapi.testclient import TestClient

from advisor import service
from advisor.llm import Advice, Coaching, LlmUnavailable, RoleAdvice, StepAdvice, text_ok, verified_order
from advisor.mapping import map_profile, taxonomy_index
from intake import ledger
from intake.models import Evidence, SkillEntry
from trendsignal.jobs import load_context
from trendsignal.web.app import create_app
from trendsignal.web.accounts_store import token_owner
from trendsignal.web.cv_api import load_profile

TAXONOMY = [{"skill": "TypeScript", "synonyms": []}, {"skill": "JavaScript / TypeScript", "synonyms": ["TypeScript", "JS"]},
            {"skill": "Python", "synonyms": ["Python3"]}]


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


@pytest.fixture
def token(client):
    review = client.post("/api/cv/extract", json={"sample": "aina"}).json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    return client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept}).json()["data"]["token"]


def entry(skill_id, name, years=None):
    ev = Evidence(source="form", method="user_entry", added_at="2026-10-24", added_by="user", years=years)
    return SkillEntry(skill_id=skill_id, name=name, basis="self_reported", years=years, evidence=(ev,))


def test_mapping_prefers_exact_names_and_never_guesses():
    profile = ledger.new_profile().model_copy(update={"skills": (entry("typescript", "TypeScript"),
                                                                  entry("python", "Python", 2.0),
                                                                  entry("obsidian", "Obsidian"))})
    held, unmapped = map_profile(profile, taxonomy_index(TAXONOMY))
    assert held == {"TypeScript": None, "Python": 2.0}
    assert unmapped == ["Obsidian"]


def test_text_rules_drop_numbers_money_and_unknown_skills():
    skills = ["Python", "Go", "Kubernetes"]
    assert text_ok("Closest to your Python work, and demand is growing.", "You already have Python", skills)
    assert not text_ok("You have 3 of its skills.", "You already have Python", skills)
    assert not text_ok("This role pays more.", "You already have Python", skills)
    assert not text_ok("Learn Kubernetes next.", "You already have Python", skills)
    for claim in ("Demand has doubled.", "Three of its five skills match.", "One of the fastest-growing roles.", "A top pick."):
        assert not text_ok(claim, "You already have Python", skills)


def test_rank_limit_is_two_places():
    formula = ["a", "b", "c", "d", "e"]
    assert verified_order(["c", "a", "b", "d", "e"], formula) == ["c", "a", "b", "d", "e"]
    assert verified_order(["d", "a", "b", "c", "e"], formula) is None  # d moved 3 places
    assert verified_order(["a", "b", "c", "d"], formula) is None  # a role dropped
    assert verified_order(["a", "a", "c", "d", "e"], formula) is None


def test_routes_need_a_saved_profile(client):
    body = client.get("/api/roles/suggestions").json()
    assert body["success"] is False and body["meta"]["code"] == "PROFILE_NOT_FOUND"


def test_suggestions_fall_back_to_the_formula_without_a_key(client, token):
    data = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()["data"]
    assert data["rankedBy"] == "formula" and data["llmStatus"].startswith("off:")
    ranks = [r["formulaRank"] for r in data["roles"]]
    assert ranks == sorted(ranks) and [r["rank"] for r in data["roles"]] == list(range(1, len(ranks) + 1))
    for role in data["roles"]:
        assert 1 <= len(role["reasons"]) <= 3 and role["salary"] is None and role["summary"] is None
        assert all(c["type"] != "watch_out" for c in role["reasons"])
    assert all(r["matchPct"] < 20 for r in data["lowMatch"])


def test_route_switch_changes_the_pathway(client, token):
    headers = {"X-Profile-Token": token}
    assert client.get("/api/pathway", headers=headers).json()["meta"]["code"] == "NO_TARGET_ROLE"
    assert client.post("/api/profile/target-role", json={"roleId": "nope"}, headers=headers).status_code == 422
    roles = client.get("/api/roles/suggestions", headers=headers).json()["data"]["roles"]
    for role in roles[:2]:
        saved = client.post("/api/profile/target-role", json={"roleId": role["roleId"]}, headers=headers).json()["data"]
        assert saved["profile"]["target_role"] == role["roleId"]
        plan = client.get("/api/pathway", headers=headers).json()["data"]
        assert plan["roleId"] == role["roleId"] and plan["targetRole"] == role["name"]
        assert {s["skill"] for s in plan["steps"]} == set(role["gap"])
        assert plan["tasks"] and all(t["resourceUrl"].startswith("http") for t in plan["tasks"])
    assert client.get("/api/pathway?roleId=analytics_engineer", headers=headers).status_code == 422


def test_low_match_destination_gets_a_full_row(client, token):
    headers = {"X-Profile-Token": token}
    data = client.get("/api/roles/suggestions", headers=headers).json()["data"]
    assert data["lowMatchTarget"] is None
    low = data["lowMatch"][0]  # aina's sample CV leaves at least one role under the match floor
    assert client.post("/api/profile/target-role", json={"roleId": low["roleId"]}, headers=headers).status_code == 200
    data = client.get("/api/roles/suggestions", headers=headers).json()["data"]
    row = data["lowMatchTarget"]
    assert data["targetRoleId"] == low["roleId"] == row["roleId"]
    assert row["rank"] is None and row["matchPct"] == low["matchPct"] and row["gap"]
    assert 1 <= len(row["reasons"]) <= 3 and "chips" not in row
    assert low["roleId"] not in [r["roleId"] for r in data["roles"]]  # pinning is display only: the ranking is unchanged


def _profile(settings, token):
    return load_profile(settings, token_owner(token))


def test_llm_order_reasons_and_cache(settings, token):
    profile, data = _profile(settings, token), service.load_data()
    base = service.suggestions(profile, [], None, settings.db_path, use_llm=False, data=data)["roles"]
    first, second = base[0]["roleId"], base[1]["roleId"]
    calls = []

    def fake(model, system, user, output, max_tokens):
        calls.append(model)
        roles = [RoleAdvice(role_id=second, chip_ids=["skill_fit", "made_up"],
                            summary="Closest to what you already do."),
                 RoleAdvice(role_id=first, chip_ids=[], summary="It pays 2x more.")]
        return Advice(order=[second, first, *[r["roleId"] for r in base[2:]]], roles=roles)

    out = service.suggestions(profile, [], None, settings.db_path, call=fake, data=data)
    assert out["rankedBy"] == "llm" and out["llmStatus"] == "llm"
    top, runner_up = out["roles"][0], out["roles"][1]
    assert top["roleId"] == second and top["summary"] == "Closest to what you already do."
    assert [c["id"] for c in top["reasons"]] == ["skill_fit"]  # the made-up chip is dropped
    assert runner_up["summary"] is None and "1" not in runner_up["fitLabel"]  # bad text dropped; the label is always code's
    again = service.suggestions(profile, [], None, settings.db_path, call=fake, data=data)
    assert again["llmStatus"] == "cached" and len(calls) == 1


def test_llm_rank_jump_and_failure_keep_the_formula(settings, token):
    profile, data = _profile(settings, token), service.load_data()
    base = [r["roleId"] for r in service.suggestions(profile, [], None, settings.db_path, use_llm=False, data=data)["roles"]]

    def jump(*_args):
        return Advice(order=[base[3], *base[:3], *base[4:]], roles=[])

    def broken(*_args):
        raise LlmUnavailable("TIMEOUT")

    assert [r["roleId"] for r in service.suggestions(profile, [], None, settings.db_path, call=jump, data=data)["roles"]] == base
    failed = service.suggestions(profile, [], "run-1", settings.db_path, call=broken, data=data)
    assert failed["rankedBy"] == "formula" and failed["llmStatus"] == "off:TIMEOUT"


def test_coach_stays_within_stages_and_verified_resources(settings, token):
    profile, data = _profile(settings, token), service.load_data()
    role_id = service.suggestions(profile, [], None, settings.db_path, use_llm=False, data=data)["roles"][0]["roleId"]
    base = service.pathway(profile, role_id, [], None, settings.db_path, use_llm=False, data=data)
    skills = [s["skill"] for s in base["steps"]]

    def fake(*_args):
        steps = [StepAdvice(skill=s, resource_url="https://evil.example/", chip_ids=["closes_gap"],
                            why_for_you=f"Builds on your Python for {s}.") for s in skills]
        return Coaching(order=list(reversed(skills)), steps=steps)

    out = service.pathway(profile, role_id, [], None, settings.db_path, call=fake, data=data)
    assert out["personalisedBy"] == "llm"
    by_stage = [s["stage"] for s in out["steps"]]
    assert by_stage == [s["stage"] for s in base["steps"]]  # stages never reorder
    assert all(s["resource"] is None or s["resource"]["url"] != "https://evil.example/" for s in out["steps"])
    assert [t["minutes"] for t in out["tasks"]] and out["totals"]["minutes"] == base["totals"]["minutes"]


def test_cut_off_json_is_truncated_not_invalid():
    from advisor.llm import call_model
    from intake.llm_extract import SpendGate

    class Cut:
        def __init__(self):
            self.messages = self

        def parse(self, **_kw):
            Advice.model_validate_json('{"order":["a"],"roles":[{"role_id":"a","summary":"Python is')  # raises

    with pytest.raises(LlmUnavailable, match="TRUNCATED"):
        call_model("m", "s", "u", Advice, 10, client=Cut(), gate=SpendGate(1.0))


def test_suggestions_meta_carries_the_dosm_check(client, token):
    meta = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()["meta"]
    m = meta["malaysia"]
    assert m["note"].startswith("DOSM does not split by job title") and m["sourceUrl"].startswith("https://www.dosm.gov.my/")
    ict = m["ict"]
    assert ict["label"] == "Information and communication" and ict["quarter"] == m["latestQuarter"]
    if ict["previous"]:
        assert ict["vsPreviousQuarterPct"] == round((ict["vacancies"] / ict["previous"] - 1) * 100, 1)
    assert "malaysia" in client.get("/api/skills/radar").json()["data"]
