"""G2 team view: POST /api/team."""

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.web.app import create_app


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


def examples(client):
    return [{"label": e["name"], "skills": e["skills"]} for e in client.get("/api/profile/examples").json()["data"]["examples"]]


def test_team_rows_and_sorted_gaps(client):
    people = examples(client)
    r = client.post("/api/team", json={"profiles": people, "roleId": "backend_engineer"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert len(d["rows"]) == len(people) == 3
    assert set(d["rows"][0]["have"]) | set(d["rows"][0]["gap"]) == set(d["skills"])
    keys = [(-g["missing"], -g["weight"], g["skill"]) for g in d["teamGaps"]]
    assert keys == sorted(keys) and d["teamGaps"][0]["missing"] >= 1
    assert set(d["unmapped"]) == {p["label"] for p in people}


def test_team_validation(client):
    people = examples(client)
    assert client.post("/api/team", json={"profiles": people[:1], "roleId": "backend_engineer"}).status_code == 422
    assert client.post("/api/team", json={"profiles": people, "roleId": "no_such_role"}).status_code == 422
