"""Example profiles, SDG and MyCOL fields, no-profile answers and the model-call guards."""

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.web.app import create_app


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


def use_example(client, example_id="aina", token=None):
    headers = {"X-Profile-Token": token} if token else {}
    return client.post("/api/profile/example", json={"id": example_id}, headers=headers).json()


def test_example_profile_saves_with_no_key_and_no_quotes(client):
    body = use_example(client)
    assert body["success"] and body["data"]["token"]
    profile = body["data"]["profile"]
    assert profile["name"] == "Aina (synthetic)"
    assert [s["name"] for s in profile["skills"]] == ["Python", "SQL", "PostgreSQL", "Docker", "AWS"]
    assert all(s["evidence_quote"] is None and "Synthetic example" in s["evidence"][0]["note"] for s in profile["skills"])
    saved = client.get("/api/profile", headers={"X-Profile-Token": body["data"]["token"]}).json()
    assert saved["success"]


def test_unknown_example_is_refused(client):
    assert client.post("/api/profile/example", json={"id": "nobody"}).status_code == 404
    assert [e["id"] for e in client.get("/api/profile/examples").json()["data"]["examples"]] == ["aina", "ben", "chloe"]


def test_suggestions_carry_sdg_and_mycol(client):
    token = use_example(client, "ben")["data"]["token"]
    data = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()["data"]
    assert data["roles"] and data["scenarioLabel"] == "Expected (estimate)"
    assert data["formulaWeights"]["match"] + data["formulaWeights"]["future"] == pytest.approx(1.0)
    for role in data["roles"]:
        b = role["breakdown"]
        assert b["rank"] == pytest.approx(b["matchWeight"] * b["match"] + b["outlookWeight"] * b["outlook"])
        assert len(b["raise"]) <= 3 and all(x["newRank"] > b["rank"] for x in b["raise"])
        for tag in role["sdg"]["tags"]:
            assert tag["target"] and tag["label"] and tag["source"] == "data/roles.json"
        for sector in role["sdg"]["sectors"]:
            assert sector["lift"] > 1 and sector["tags"][0]["source"] == "data/role_sdg.json"
        strengths = [m["strength"] for m in role["mycol"]]
        assert strengths == sorted(strengths, key=lambda s: s != "direct")
        assert all(m["label"] == "TalentCorp MyCOL" and m["year"] for m in role["mycol"])
    assert any(r["mycol"] for r in data["roles"]) and any(r["sdg"]["tags"] for r in data["roles"])


def test_pathway_carries_sdg_tags_and_summary(client):
    token = use_example(client, "aina")["data"]["token"]
    headers = {"X-Profile-Token": token}
    role = client.get("/api/roles/suggestions", headers=headers).json()["data"]["roles"][0]["roleId"]
    plan = client.get(f"/api/pathway?roleId={role}&scenario=fast", headers=headers).json()["data"]
    assert plan["scenarioLabel"].endswith("(estimate)")
    assert plan["sdgSummary"]["line"] and plan["sdgSummary"]["lines"]
    for step in plan["steps"]:
        assert [t["target"] for t in step["sdgTags"]] == step["sdg"]


def test_no_profile_answers_404_for_every_screen(client):
    for path in ("/api/roles/suggestions", "/api/pathway"):
        body = client.get(path).json()
        assert not body["success"] and body["meta"]["code"] == "PROFILE_NOT_FOUND"


def test_target_role_must_have_a_pathway(client):
    token = use_example(client)["data"]["token"]
    headers = {"X-Profile-Token": token}
    assert client.post("/api/profile/target-role", json={"roleId": "analytics_engineer"}, headers=headers).status_code == 422
    assert client.post("/api/profile/target-role", json={"roleId": "nope"}, headers=headers).status_code == 422


def test_hours_per_week_is_a_bounded_int(client):
    token = use_example(client)["data"]["token"]
    for bad in ("0", "41", "2.5"):
        assert client.get(f"/api/roles/suggestions?hoursPerWeek={bad}", headers={"X-Profile-Token": token}).status_code == 422


def test_auto_mode_without_a_key_says_no_key(settings, monkeypatch):
    monkeypatch.setenv("TRENDSIGNAL_LLM", "auto")
    from trendsignal.config import load_settings
    from trendsignal.db import init_schema
    auto = load_settings()
    init_schema(auto.db_path)
    client = TestClient(create_app(load_context(auto)))
    headers = {"X-Profile-Token": use_example(client)["data"]["token"]}
    suggestions = client.get("/api/roles/suggestions", headers=headers).json()["data"]
    assert suggestions["llmStatus"] == "off:NO_KEY"
    plan = client.get(f"/api/pathway?roleId={suggestions['roles'][0]['roleId']}", headers=headers).json()["data"]
    assert plan["llmStatus"] == "off:NO_KEY"


def test_cached_advisor_answer_is_served_after_the_ip_limit_is_spent(llm_settings, monkeypatch):
    from advisor.llm import Advice
    from trendsignal.web import roles_api
    calls = []
    monkeypatch.setattr(roles_api, "call_model", lambda *a, **k: calls.append(1) or Advice(order=[], roles=[]))
    monkeypatch.setattr(roles_api, "MODEL_CALLS_PER_MINUTE", 1)
    client = TestClient(create_app(load_context(llm_settings)))
    headers = {"X-Profile-Token": use_example(client)["data"]["token"]}
    assert client.get("/api/roles/suggestions", headers=headers).json()["data"]["llmStatus"] == "llm"
    assert client.get("/api/roles/suggestions", headers=headers).json()["data"]["llmStatus"] == "cached"
    assert client.get("/api/roles/suggestions?scenario=fast", headers=headers).json()["data"]["llmStatus"] == "cached"
    assert client.get("/api/roles/suggestions?hoursPerWeek=20", headers=headers).json()["data"]["llmStatus"] == "off:RATE_LIMITED"
    assert len(calls) == 1


def test_malformed_role_sdg_is_treated_as_missing(tmp_path):
    import shutil
    from advisor import service
    for name in [*service.FILES.values(), *service.OPTIONAL_FILES.values()]:
        shutil.copy(service.DATA_DIR / name, tmp_path / name)
    (tmp_path / "role_sdg.json").write_text('{"roles": [], "sectors": {}}', encoding="utf-8")
    assert service.load_data(tmp_path)["role_sdg"] is None


def test_goal_adds_reason_and_keeps_pathway_shape(client):
    token = use_example(client)["data"]["token"]
    headers = {"X-Profile-Token": token}
    data = client.get("/api/roles/suggestions?goal=health", headers=headers).json()["data"]
    assert data["goalOrder"] and all("sdgReason" in r and "goalRank" in r["goal"] for r in data["roles"])
    assert client.get("/api/roles/suggestions?goal=bogus", headers=headers).status_code == 422
    assert client.get("/api/pathway?goal=bogus", headers=headers).status_code == 422
    role = data["roles"][0]["roleId"]
    plain = client.get(f"/api/pathway?roleId={role}", headers=headers).json()["data"]
    goal = client.get(f"/api/pathway?roleId={role}&goal=health", headers=headers).json()["data"]
    assert [s["name"] for s in goal["stages"]] == [s["name"] for s in plain["stages"]]
    assert {s["skill"] for s in goal["steps"]} == {s["skill"] for s in plain["steps"]}
    assert goal["totals"]["minutes"] == plain["totals"]["minutes"]


def test_python_gap_step_carries_an_employer_funded_option(client):
    token = use_example(client, "ben")["data"]["token"]
    headers = {"X-Profile-Token": token}
    sug = client.get("/api/roles/suggestions", headers=headers).json()["data"]
    steps = []
    for role in sug["roles"] + sug["lowMatch"]:
        client.post("/api/profile/target-role", json={"roleId": role["roleId"]}, headers=headers)
        steps += client.get("/api/pathway", headers=headers).json()["data"]["steps"]
    funded = [s for s in steps if s["employerFunded"]]
    assert any(s["skill"] == "Python" for s in funded)
    py = next(s for s in funded if s["skill"] == "Python")["employerFunded"]
    assert py["url"].startswith("https://") and py["days"] > 0 and py["feeMyr"] > 0 and py["checkedOn"]
    assert all(s["skill"] in {"Python", "AWS", "GCP"} for s in funded)
    assert any(s["employerFunded"] is None for s in steps)
