import base64

import pytest
from fastapi.testclient import TestClient

from trendsignal.db import connect
from trendsignal.jobs import load_context
from trendsignal.web.app import create_app


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


def extract(client, token=None, **body):
    headers = {"X-Profile-Token": token} if token else {}
    return client.post("/api/cv/extract", json=body, headers=headers)


def rows_by_id(body):
    return {row["skill_id"]: row for row in body["data"]["rows"]}


def test_sample_cv_uses_the_cached_run_without_a_key(client):
    body = extract(client, sample="aina").json()
    assert body["success"] and body["data"]["llm_status"] == "cached"
    rows = rows_by_id(body)
    assert rows["python"]["years"] == 2.8 and rows["python"]["basis"] == "stated"
    assert rows["quantitative-finance"]["basis"] == "implied"
    assert [d["phrase"] for d in body["data"]["dropped"]] == ["Kubernetes"]
    assert [i["skill_id"] for i in body["data"]["interests"]] == ["rust"]


def test_pasted_text_without_ai_uses_the_keyword_pass(client):
    body = extract(client, text="Built REST APIs in Python with Flask.", use_ai=False).json()
    assert body["data"]["llm_status"] == "off:SWITCHED_OFF"
    assert {"python", "flask", "rest-apis"} <= set(rows_by_id(body))


def test_text_file_upload(client):
    data = base64.b64encode(b"Wrote SQL queries on PostgreSQL.").decode()
    body = extract(client, file_name="cv.txt", file_b64=data).json()
    assert body["data"]["llm_status"] == "off:NO_KEY"
    assert {"sql", "postgresql"} <= set(rows_by_id(body))


@pytest.mark.parametrize("body", [
    {"file_name": "cv.txt", "file_b64": "not base64!"},
    {"text": "Python", "sample": "aina"},
    {},
    {"file_name": "cv.docx", "file_b64": base64.b64encode(b"x").decode()},
], ids=["bad-base64", "two-inputs", "nothing", "docx"])
def test_bad_input_is_refused_with_a_message(client, body):
    response = client.post("/api/cv/extract", json=body)
    assert response.status_code == 422 and response.json()["error"]


def test_save_load_remove_delete_round_trip(client, settings):
    review = extract(client, sample="aina").json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    saved = client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept,
                                                     "target_role": "data_engineer"}).json()["data"]
    token = saved["token"]
    assert saved["profile"]["target_role"] == "data_engineer"
    assert len(saved["profile"]["skills"]) == len(kept)

    headers = {"X-Profile-Token": token}
    assert client.get("/api/profile", headers=headers).json()["data"]["profile"] == saved["profile"]
    assert client.get("/api/profile").status_code == 404
    assert client.get("/api/profile", headers={"X-Profile-Token": "guess"}).status_code == 404

    removed = client.post("/api/profile/remove", json={"skill_id": "excel"}, headers=headers).json()["data"]["profile"]
    assert "excel" not in {s["skill_id"] for s in removed["skills"]}
    again = rows_by_id(extract(client, token=token, sample="aina").json())
    assert again["excel"]["default_keep"] is False and again["excel"]["note"]

    with connect(settings.db_path) as conn:
        stored = [row["token_hash"] for row in conn.execute("SELECT token_hash FROM profiles")]
    assert stored and token not in stored  # only the hash is kept

    assert client.delete("/api/profile", headers=headers).json()["data"]["deleted"] is True
    assert client.get("/api/profile", headers=headers).status_code == 404


def test_second_apply_adds_to_the_same_profile(client):
    first = extract(client, text="Built REST APIs in Python.", use_ai=False).json()["data"]
    token = client.post("/api/profile/apply", json={"review_id": first["review_id"], "kept_ids": ["python"]}).json()["data"]["token"]
    second = extract(client, token=token, text="Wrote SQL queries.", use_ai=False).json()["data"]
    saved = client.post("/api/profile/apply", json={"review_id": second["review_id"], "kept_ids": ["sql"]},
                        headers={"X-Profile-Token": token}).json()["data"]
    assert saved["token"] == token
    assert {s["skill_id"] for s in saved["profile"]["skills"]} == {"python", "sql"}


def test_a_review_can_be_saved_once_and_cannot_be_forged(client):
    review = extract(client, text="Python", use_ai=False).json()["data"]
    body = {"review_id": review["review_id"], "kept_ids": ["python"]}
    assert client.post("/api/profile/apply", json=body).status_code == 200
    assert client.post("/api/profile/apply", json=body).status_code == 410
    assert client.post("/api/profile/apply", json={"review_id": "made-up", "kept_ids": ["kubernetes"]}).status_code == 410


@pytest.mark.parametrize("years", [-1, 41, "NaN"])
def test_typed_years_out_of_range_are_refused(client, years):
    review = extract(client, text="Python", use_ai=False).json()["data"]
    body = {"review_id": review["review_id"], "kept_ids": ["python"], "edited_years": {"python": years}}
    assert client.post("/api/profile/apply", json=body).status_code == 422


def test_rate_limit_uses_the_forwarded_address(client):
    for _ in range(6):
        extract(client, text="Python", use_ai=False)
    other = client.post("/api/cv/extract", json={"text": "Python", "use_ai": False},
                        headers={"X-Forwarded-For": "203.0.113.9"})
    assert other.status_code == 200


def test_cv_reading_is_rate_limited(client):
    statuses = [extract(client, text="Python", use_ai=False).status_code for _ in range(7)]
    assert statuses[:6] == [200] * 6 and statuses[6] == 429
