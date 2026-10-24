"""Every /api error uses the {success, data, error, meta} envelope with a plain-English message."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.web.app import create_app


@pytest.fixture
def frontend_client(settings, tmp_path):
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text("<title>Varity</title>", encoding="utf-8")
    (tmp_path / "frontend" / "landing.js").write_text("//js", encoding="utf-8")
    return TestClient(create_app(load_context(replace(settings, frontend_dir=tmp_path / "frontend"))))


def check(response, status, message=None):
    body = response.json()
    assert response.status_code == status
    assert set(body) == {"success", "data", "error", "meta"} and body["success"] is False and body["data"] is None
    assert "detail" not in body and "{" not in body["error"] and "pydantic" not in body["error"].lower()
    if message:
        assert body["error"] == message
    return body


def test_missing_field_is_plain_english(frontend_client):
    check(frontend_client.post("/api/profile/apply", json={"kept_ids": []}), 422, "Missing field: review_id")


def test_invalid_value_is_plain_english(frontend_client):
    check(frontend_client.post("/api/profile/apply", json={"review_id": "r", "kept_ids": "nope"}), 422, "Invalid value for kept_ids")


def test_unknown_api_path_is_a_404_envelope(frontend_client):
    check(frontend_client.get("/api/does-not-exist"), 404, "Not found.")


def test_wrong_method_is_a_405_envelope(frontend_client):
    check(frontend_client.get("/api/login/prepare"), 405, "Method not allowed.")


def test_http_exception_404_uses_the_envelope(frontend_client):
    check(frontend_client.post("/api/admin/run"), 404, "Not found.")  # raised as HTTPException when no admin token is set


def test_oversized_cv_upload_gets_the_too_large_message(frontend_client):
    response = frontend_client.post("/api/cv/extract", json={"file_name": "cv.pdf", "file_b64": "A" * 7_000_000})
    assert check(response, 422, "The file is larger than 5 MB.")["meta"]["code"] == "TOO_LARGE"


def test_admin_routes_do_not_leak_config(frontend_client, settings):
    for path in ("/api/admin/run", "/api/admin/digest/daily"):
        check(frontend_client.post(path), 404, "Not found.")
    object.__setattr__(settings, "admin_token", "s3cret")
    secured = TestClient(create_app(load_context(settings)))
    check(secured.post("/api/admin/run", headers={"X-Admin-Token": "wrong"}), 401, "Not allowed.")
    assert secured.post("/api/admin/run", headers={"X-Admin-Token": "s3cret"}).status_code == 202


def test_static_frontend_and_html_pages_are_unchanged(frontend_client):
    assert "Varity" in frontend_client.get("/").text
    assert frontend_client.get("/landing.js").status_code == 200
    assert frontend_client.get("/nope.html").status_code == 404
    assert "detail" in frontend_client.get("/story/99999").json()
