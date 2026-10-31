"""Replay of real data as of an older month (per request), and the rate-limited background refresh."""

import time

import pytest
from fastapi.testclient import TestClient

from advisor import service
from trendsignal.jobs import load_context
from trendsignal.web.app import create_app


@pytest.fixture
def client(settings):
    service._refresh_state["last_start"] = None
    yield TestClient(create_app(load_context(settings)))
    service._refresh_state["last_start"] = None


def routes(client, token, as_of=None):
    url = "/api/roles/suggestions" + (f"?asOf={as_of}" if as_of else "")
    body = client.get(url, headers={"X-Profile-Token": token}).json()
    return body["meta"], [(r["roleId"], r["matchPct"], r["trendLabel"]) for r in body["data"]["roles"]]


def test_two_viewers_see_different_months_at_once(client):
    token = client.post("/api/profile/example", json={"id": "aina"}).json()["data"]["token"]
    meta_old, old = routes(client, token, "2025-06")
    meta_now, latest = routes(client, token)
    assert meta_old["dataAsOf"] == "2025-06" and meta_old["dataMode"] == "replay"
    assert meta_now["dataAsOf"] != "2025-06" and meta_now["dataMode"] == "latest"
    assert old != latest
    assert routes(client, token) == (meta_now, latest)  # nothing stuck on the server
    assert client.get("/api/data/status?asOf=2025-06").json()["data"]["asOf"] == "2025-06"
    assert client.get("/api/data/status").json()["data"]["mode"] == "latest"
    assert client.get("/api/skills/radar?asOf=2025-06").json()["data"]["asOf"] == "2025-06"
    assert client.get("/api/skills/radar").json()["data"]["asOf"] != "2025-06"


def test_invalid_month_is_refused(client):
    token = client.post("/api/profile/example", json={"id": "aina"}).json()["data"]["token"]
    headers = {"X-Profile-Token": token}
    for path in ("/api/roles/suggestions", "/api/pathway", "/api/skills/radar", "/api/data/status"):
        assert client.get(f"{path}?asOf=2025-07", headers=headers).status_code == 422
    assert client.post("/api/data/asof", json={"asOf": "2025-06"}).status_code in (404, 405)


def test_refresh_runs_in_background_keeps_data_on_failure_and_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr("engine.refresh.refresh", lambda: {"ok": False, "error": "network down"})
    assert client.post("/api/data/refresh").status_code == 202
    for _ in range(50):
        status = client.get("/api/data/status").json()["data"]
        if status["mode"] != "refreshing":
            break
        time.sleep(0.1)
    assert status["mode"] == "latest" and status["error"] == "network down"
    second = client.post("/api/data/refresh")
    assert second.status_code == 429 and 0 < second.json()["meta"]["retryAfter"] <= 600
