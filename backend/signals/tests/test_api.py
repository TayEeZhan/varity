from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.pipeline.process import run_process
from trendsignal.web.app import create_app, render_brief_html
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


def test_home_page_renders_tiers(client):
    page = client.get("/feed")
    assert page.status_code == 200
    assert "Must-know" in page.text and "Introducing GPT-6 for developers" in page.text


def test_feed_filters_reject_unknown_values_quietly(client):
    assert client.get("/feed?category=nonsense&audience=<script>").status_code == 200


def test_api_stories_uses_the_envelope(client):
    body = client.get("/api/stories?limit=5").json()
    assert body["success"] is True and body["error"] is None
    assert body["meta"]["limit"] == 5 and body["data"][0]["title"].startswith("Introducing GPT-6")


def test_api_rejects_unknown_tier(client):
    response = client.get("/api/stories?tier=bogus")
    assert response.status_code == 422 and response.json()["success"] is False


def test_api_story_detail_and_not_found(client):
    story_id = client.get("/api/stories").json()["data"][0]["id"]
    detail = client.get(f"/api/stories/{story_id}").json()["data"]
    assert detail["reports"][0]["source"] == OPENAI.name
    assert client.get("/api/stories/99999").status_code == 404
    assert client.get(f"/story/{story_id}").status_code == 200


def test_feedback_is_saved_validated_and_rate_limited(client):
    story_id = client.get("/api/stories").json()["data"][0]["id"]
    assert client.post("/api/feedback", json={"story_id": story_id, "signal": "useful"}).status_code == 200
    assert client.post("/api/feedback", json={"story_id": story_id, "signal": "hate"}).status_code == 422
    assert client.post("/api/feedback", json={"story_id": 424242, "signal": "useful"}).status_code == 404
    statuses = [client.post("/api/feedback", json={"story_id": story_id, "signal": "useful"}).status_code
                for _ in range(40)]
    assert 429 in statuses


def test_admin_endpoints_are_off_without_a_token_and_need_the_right_one(client, settings, monkeypatch):
    assert client.post("/api/admin/run").status_code == 404
    object.__setattr__(settings, "admin_token", "s3cret")
    ctx = load_context(settings)
    secured = TestClient(create_app(ctx))
    assert secured.post("/api/admin/run", headers={"X-Admin-Token": "wrong"}).status_code == 401


def test_brief_pages_and_digest_api_before_any_brief(client):
    assert client.get("/brief/daily").status_code == 200
    assert client.get("/api/digest/daily/latest").status_code == 404


def test_rss_health_trends_and_skills(client):
    rss = client.get("/rss.xml")
    assert rss.headers["content-type"].startswith("application/rss+xml") and "<rss" in rss.text
    assert client.get("/api/health").json()["success"] is True
    assert client.get("/api/trends").status_code == 200
    skills = client.get("/api/skills/momentum").json()
    assert "momentum" in skills["meta"]["definition"]
    assert client.get("/sources").status_code == 200


def test_brief_html_escapes_markup_from_the_model():
    rendered = render_brief_html("# Brief\n<script>alert(1)</script> line [S5]")
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert '<a class="cite" href="/story/5">S5</a>' in rendered


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


def test_root_serves_the_frontend_and_the_feed_moves(settings, client, tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text("<title>Varity</title>", encoding="utf-8")
    ctx = load_context(replace(settings, frontend_dir=tmp_path / "frontend"))
    app_client = TestClient(create_app(ctx))
    assert "Varity" in app_client.get("/").text
    assert app_client.get("/feed").status_code == 200 and app_client.get("/api/signals").status_code == 200


def test_root_falls_back_to_the_feed_without_a_frontend(settings, tmp_path):
    app_client = TestClient(create_app(load_context(replace(settings, frontend_dir=tmp_path / "missing"))))
    assert app_client.get("/").url.path == "/feed"


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
