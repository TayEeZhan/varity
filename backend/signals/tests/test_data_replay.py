"""Replay of real data as of an older month, the admin guard and the background refresh."""

import time

import pytest
from fastapi.testclient import TestClient

from advisor import service
from trendsignal.jobs import load_context
from trendsignal.web.app import create_app

ADMIN = {"X-Admin-Token": "secret"}


@pytest.fixture
def client(settings, monkeypatch):
    monkeypatch.setenv("VERITY_ADMIN_TOKEN", "secret")
    yield TestClient(create_app(load_context(settings)))
    service.set_replay(None)


def aina_routes(client):
    token = client.post("/api/profile/example", json={"id": "aina"}).json()["data"]["token"]
    body = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()
    return body["meta"], [(r["roleId"], r["matchPct"], r["trendLabel"]) for r in body["data"]["roles"]]


def test_write_routes_need_the_token(client, monkeypatch):
    assert client.post("/api/data/asof", json={"asOf": "2025-06"}).status_code == 403
    assert client.post("/api/data/asof", json={"asOf": "2025-06"}, headers={"X-Admin-Token": "no"}).status_code == 403
    assert client.delete("/api/data/asof").status_code == 403
    assert client.post("/api/admin/refresh").status_code == 403
    monkeypatch.delenv("VERITY_ADMIN_TOKEN")
    r = client.post("/api/data/asof", json={"asOf": "2025-06"}, headers=ADMIN)
    assert r.status_code == 403 and "VERITY_ADMIN_TOKEN" in r.json()["error"]


def test_replay_changes_the_routes_and_delete_restores(client):
    meta0, latest = aina_routes(client)
    assert meta0["dataMode"] == "latest"
    assert client.post("/api/data/asof", json={"asOf": "2025-06"}, headers=ADMIN).json()["data"]["mode"] == "replay"
    meta1, old = aina_routes(client)
    assert meta1["dataAsOf"] == "2025-06" and meta1["dataMode"] == "replay"
    assert old != latest
    print("LATEST", latest[:3], "REPLAY", old[:3])
    assert client.get("/api/data/status").json()["data"]["asOf"] == "2025-06"
    assert client.delete("/api/data/asof", headers=ADMIN).json()["data"]["mode"] == "latest"
    assert aina_routes(client) == (meta0, latest)


def test_invalid_month_is_refused(client):
    r = client.post("/api/data/asof", json={"asOf": "2025-07"}, headers=ADMIN)
    assert r.status_code == 422
    assert client.get("/api/data/status").json()["data"]["mode"] == "latest"


def test_refresh_runs_in_background_and_keeps_data_on_failure(client, monkeypatch):
    monkeypatch.setattr("engine.refresh.refresh", lambda: {"ok": False, "error": "network down"})
    assert client.post("/api/admin/refresh", headers=ADMIN).status_code == 202
    for _ in range(50):
        status = client.get("/api/data/status").json()["data"]
        if status["mode"] != "refreshing":
            break
        time.sleep(0.1)
    assert status["mode"] == "latest" and status["error"] == "network down"
