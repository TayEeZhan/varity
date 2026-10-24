from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.pipeline.process import run_process
from trendsignal.web.app import create_app
from tests.conftest import raw, seed, source

OPENAI = source("openai_news", "A")


@pytest.fixture
def client(settings, weights, watchlist):
    seed(settings, OPENAI, [raw("openai_news", "o1", "Introducing GPT-6 for developers", url="https://openai.com/gpt-6",
                                text="GPT-6 is now available in the API.")])
    run_process(settings, (OPENAI,), weights, watchlist)
    ctx = load_context(settings)
    ctx.source_map["openai_news"] = OPENAI
    return TestClient(create_app(ctx))


def test_admin_endpoints_are_off_without_a_token_and_need_the_right_one(client, settings, monkeypatch):
    assert client.post("/api/admin/run").status_code == 404
    object.__setattr__(settings, "admin_token", "s3cret")
    ctx = load_context(settings)
    secured = TestClient(create_app(ctx))
    assert secured.post("/api/admin/run", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_health_works_and_the_old_trendsignal_pages_are_gone(client):
    assert client.get("/api/health").json()["success"] is True
    for path in ("/feed", "/sources", "/rss.xml", "/api/stories", "/api/trends", "/api/skills/momentum",
                 "/api/digest/daily/latest"):
        assert client.get(path).status_code == 404, path
    assert client.post("/api/feedback", json={"story_id": 1, "signal": "useful"}).status_code in (404, 405)


def test_api_signals_matches_the_varity_page_shape(client):
    body = client.get("/api/signals").json()
    assert body["success"] is True
    run, stories, skills = body["data"]["run"], body["data"]["stories"], body["data"]["skills"]
    assert run["runId"] and run["storyCount"] == 1 and run["rankedBy"] == "deterministic formula"
    story = stories[0]
    assert set(story) == {"rank", "score", "tier", "category", "date", "title", "url", "sources", "why"}
    assert story["title"].startswith("Introducing GPT-6") and story["sources"] == [OPENAI.name]
    assert story["tier"] in ("Must-know", "Worth a look", "Minor") and story["category"] == "Model release"
    assert all(len(s["weekly"]) == 5 and {"skill", "avgBefore", "momentum"} <= set(s) for s in skills)


def test_signals_page_categories_match_its_filter_labels():
    from trendsignal.models import CATEGORIES
    from trendsignal.web.app import UI_CATEGORIES

    assert set(UI_CATEGORIES) == set(CATEGORIES)
    # frontend/screens-explore.js FILTERS match these exact labels
    assert {UI_CATEGORIES[c] for c in ("security_incident", "research", "product_feature", "model_release")} == {
        "Security incident", "Research", "Product feature", "Model release"}
    assert "API" in UI_CATEGORIES["api_pricing_change"] and "Policy" in UI_CATEGORIES["policy_regulation"]


def test_root_serves_the_frontend(settings, client, tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text("<title>Varity</title>", encoding="utf-8")
    ctx = load_context(replace(settings, frontend_dir=tmp_path / "frontend"))
    app_client = TestClient(create_app(ctx))
    assert "Varity" in app_client.get("/").text
    assert app_client.get("/api/signals").status_code == 200


def test_root_is_404_without_a_frontend(settings, tmp_path):
    app_client = TestClient(create_app(load_context(replace(settings, frontend_dir=tmp_path / "missing"))))
    assert app_client.get("/").status_code == 404


def test_role_forecast_serves_the_engine_file(settings, tmp_path):
    path = tmp_path / "role_forecast.json"
    path.write_text('{"as_of": "2026-10", "roles": {"data_engineer": {"name": "Data Engineer", "status": "ok"}}}',
                    encoding="utf-8")
    app_client = TestClient(create_app(load_context(replace(settings, role_forecast_path=path))))
    body = app_client.get("/api/roles/forecast").json()
    assert body["success"] and body["data"]["as_of"] == "2026-10"
    assert body["data"]["roles"]["data_engineer"]["name"] == "Data Engineer"


def test_role_forecast_is_404_when_the_file_is_missing(settings, tmp_path):
    missing = replace(settings, role_forecast_path=tmp_path / "missing.json")
    response = TestClient(create_app(load_context(missing))).get("/api/roles/forecast")
    assert response.status_code == 404 and response.json()["error"]


def test_role_forecast_is_500_when_the_file_is_broken(settings, tmp_path):
    path = tmp_path / "role_forecast.json"
    path.write_text("{not json", encoding="utf-8")
    response = TestClient(create_app(load_context(replace(settings, role_forecast_path=path)))).get("/api/roles/forecast")
    assert response.status_code == 500 and not response.json()["success"]
