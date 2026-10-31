"""Optional accounts: Replit Auth (mocked, no network), signed session, profile storage in SQLite and the Postgres SQL."""

import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from trendsignal.db import connect
from trendsignal.jobs import load_context
from trendsignal.web import accounts_store as store
from trendsignal.web import auth_api
from trendsignal.web.app import create_app

DOC = {"issuer": "https://replit.com/oidc", "authorization_endpoint": "https://replit.com/oidc/auth",
       "token_endpoint": "https://replit.com/oidc/token", "userinfo_endpoint": "https://replit.com/oidc/me",
       "end_session_endpoint": "https://replit.com/oidc/session/end"}
USER = {"sub": "42", "username": "ada", "first_name": "Ada", "last_name": "L", "email": "ada@example.com",
        "profile_image_url": "https://img/ada.png"}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("REPL_ID", "repl-123")
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    for name in ("DATABASE_URL", "PUBLIC_BASE_URL", "REPLIT_DOMAINS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(auth_api, "discovery", lambda: DOC)
    monkeypatch.setattr(auth_api, "exchange_code", lambda endpoint, form: {"access_token": "at"})
    monkeypatch.setattr(auth_api, "fetch_userinfo", lambda endpoint, token: USER)


@pytest.fixture
def client(settings, on):
    return TestClient(create_app(load_context(settings)), follow_redirects=False, base_url="http://localhost")


def start_login(client, **params):
    response = client.get("/api/login", params=params)
    return response, parse_qs(urlparse(response.headers["location"]).query)


def sign_in(client):
    _, query = start_login(client)
    return client.get("/api/callback", params={"code": "c", "state": query["state"][0]})


from tests.test_cv_api import MINI_CV  # noqa: E402


def anonymous_profile(client):
    review = client.post("/api/cv/extract", json={"text": MINI_CV, "use_ai": False}).json()["data"]
    return client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": ["python"]}).json()["data"]["token"]


def example_id(client):
    return client.get("/api/profile/examples").json()["data"]["examples"][0]["id"]


def test_disabled_without_env(settings, monkeypatch):
    monkeypatch.delenv("REPL_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    client = TestClient(create_app(load_context(settings)), follow_redirects=False, base_url="http://localhost")
    assert client.get("/api/me").json()["data"] == {"enabled": False, "signedIn": False, "user": None, "hasProfile": False,
                                                    "googleClientId": None}
    assert client.get("/api/login").status_code == 404
    assert client.post("/api/login/prepare").status_code == 404


def test_google_client_id_only_if_it_looks_like_one(settings, monkeypatch):
    client = TestClient(create_app(load_context(settings)), follow_redirects=False, base_url="http://localhost")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "GOCSPX-abcdefSECRET123")
    assert client.get("/api/me").json()["data"]["googleClientId"] is None
    assert "GOCSPX" not in client.get("/api/me").text
    good = "123456-abc9def.apps.googleusercontent.com"
    monkeypatch.setenv("GOOGLE_CLIENT_ID", good)
    assert client.get("/api/me").json()["data"]["googleClientId"] == good


def test_login_redirect_has_pkce_state_and_safe_return(client):
    response, query = start_login(client, returnTo="/#/pathway")
    assert response.status_code == 302 and response.headers["location"].startswith(DOC["authorization_endpoint"])
    assert query["code_challenge_method"] == ["S256"] and query["client_id"] == ["repl-123"]
    assert query["response_type"] == ["code"] and query["state"] and query["nonce"] and query["code_challenge"]
    assert query["redirect_uri"] == ["http://localhost/api/callback"]
    flow = auth_api.unsign(client.cookies.get("varity_oidc"))
    assert flow["r"] == "/#/pathway" and flow["s"] == query["state"][0]


@pytest.mark.parametrize("bad", ["https://evil.example/", "//evil.example", "/\\evil.example", "javascript:alert(1)", "x"])
def test_open_redirect_return_to_is_rejected(client, bad):
    start_login(client, returnTo=bad)
    assert auth_api.unsign(client.cookies.get("varity_oidc"))["r"] == auth_api.DEFAULT_RETURN


def test_redirect_uri_follows_proxy_headers_and_rejects_foreign_hosts(client, monkeypatch):
    monkeypatch.setenv("REPLIT_DOMAINS", "app.replit.app,other.replit.app")
    ok = client.get("/api/login", headers={"x-forwarded-proto": "https", "x-forwarded-host": "app.replit.app"})
    assert parse_qs(urlparse(ok.headers["location"]).query)["redirect_uri"] == ["https://app.replit.app/api/callback"]
    assert client.get("/api/login", headers={"x-forwarded-host": "evil.example"}).status_code == 400


def test_callback_signs_in_and_moves_the_anonymous_profile(client):
    token = anonymous_profile(client)
    client.cookies.clear()
    assert client.post("/api/login/prepare", headers={"X-Profile-Token": token}).json()["data"]["linked"] is True
    response = sign_in(client)
    assert response.status_code == 302 and response.headers["location"] == auth_api.DEFAULT_RETURN
    header = " ".join(response.headers.get_list("set-cookie")).lower()
    assert "varity_session=" in header and "httponly" in header and "samesite=lax" in header
    me = client.get("/api/me").json()["data"]
    assert me["signedIn"] and me["hasProfile"]
    assert me["user"] == {"name": "Ada L", "email": "ada@example.com", "imageUrl": "https://img/ada.png"}
    got = client.get("/api/profile").json()["data"]  # no token: the cookie is enough
    assert got["account"] is True and [s["skill_id"] for s in got["profile"]["skills"]] == ["python"]
    client.cookies.clear()
    assert client.get("/api/profile", headers={"X-Profile-Token": token}).status_code == 404  # moved, not copied


def test_bad_state_is_rejected(client):
    start_login(client)
    response = client.get("/api/callback", params={"code": "c", "state": "wrong"})
    assert response.headers["location"] == auth_api.FAILED
    assert "varity_session" not in response.headers.get("set-cookie", "")
    client.cookies.clear()
    assert client.get("/api/callback", params={"code": "c", "state": "s"}).headers["location"] == auth_api.FAILED


def test_failed_exchange_and_bad_id_token_redirect_to_failed(client, monkeypatch):
    def boom(endpoint, form):
        raise RuntimeError("down")

    monkeypatch.setattr(auth_api, "exchange_code", boom)
    assert sign_in(client).headers["location"] == auth_api.FAILED
    monkeypatch.setattr(auth_api, "exchange_code", lambda e, f: {"access_token": "at", "id_token": "a.e30.c"})
    assert sign_in(client).headers["location"] == auth_api.FAILED  # claims {} fail iss/aud


def test_tampered_or_unsigned_session_cookie_is_ignored(client):
    sign_in(client)
    good = client.cookies.get("varity_session")
    client.cookies.clear()
    forged_values = (good[:-2] + "xx", auth_api.sign({"sub": "42"}, 60).rsplit(".", 1)[0] + ".AAAA", "junk",
                     auth_api.sign({"sub": "42"}, -5))  # last one is expired
    for forged in forged_values:
        headers = {"Cookie": f"varity_session={forged}"}
        assert client.get("/api/me", headers=headers).json()["data"]["signedIn"] is False
        assert client.get("/api/profile", headers=headers).status_code == 404
    assert client.get("/api/me", headers={"Cookie": f"varity_session={good}"}).json()["data"]["signedIn"] is True


def test_signed_in_profile_routes_work_without_a_token(client):
    sign_in(client)
    saved = client.post("/api/profile/example", json={"id": example_id(client)})
    data = saved.json()["data"]
    assert saved.status_code == 200 and data["account"] is True and "token" not in data
    assert client.get("/api/profile").json()["data"]["account"] is True
    assert client.get("/api/skills/radar").status_code == 200


def test_progress_round_trip(client):
    token = anonymous_profile(client)
    headers = {"X-Profile-Token": token}
    put = client.put("/api/profile/progress", json={"signature": "sig", "doneIds": ["a", "b", "a"]}, headers=headers)
    assert put.status_code == 200
    got = client.get("/api/profile", headers=headers).json()["data"]
    assert got["progress"]["signature"] == "sig" and got["progress"]["doneIds"] == ["a", "b"] and got["progress"]["updatedAt"]
    assert client.put("/api/profile/progress", json={"signature": "s" * 129, "doneIds": []}, headers=headers).status_code == 422
    assert client.put("/api/profile/progress", json={"signature": "s", "doneIds": ["x" * 65]}, headers=headers).status_code == 422
    assert client.put("/api/profile/progress", json={"signature": "s", "doneIds": []}).status_code == 404


def test_logout_clears_the_session(client):
    sign_in(client)
    response = client.get("/api/logout")
    assert response.status_code == 302
    target = urlparse(response.headers["location"])
    assert target.path == "/oidc/session/end"
    assert parse_qs(target.query)["post_logout_redirect_uri"] == ["http://localhost/"]
    assert "varity_session=" in response.headers["set-cookie"] and "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/me").json()["data"]["signedIn"] is False


def test_delete_me_removes_user_and_profile(client, settings):
    sign_in(client)
    client.post("/api/profile/example", json={"id": example_id(client)})
    assert client.delete("/api/me").json()["data"]["deleted"] is True
    assert store.get_user(settings, "42") is None and store.get_profile_json(settings, "u:42") is None
    assert client.get("/api/me").json()["data"]["signedIn"] is False
    assert client.delete("/api/me").status_code == 401


def test_anonymous_flow_and_legacy_rows_still_work(client, settings):
    token = anonymous_profile(client)
    assert client.get("/api/profile", headers={"X-Profile-Token": token}).json()["data"]["account"] is False
    # a row written by the old code (profiles.token_hash) is found and can be moved
    with connect(settings.db_path) as conn:
        conn.execute("INSERT INTO profiles (token_hash, profile_json, updated_at) VALUES ('abc', '{\"x\":1}', 't')")
    assert store.get_profile_json(settings, "t:abc") == '{"x":1}'
    assert store.move_profile(settings, "t:abc", "u:9") and store.get_profile_json(settings, "u:9") == '{"x":1}'


def test_postgres_sql_uses_percent_placeholders():
    assert store.to_postgres("SELECT 1 FROM t WHERE a = ? AND b = ?") == "SELECT 1 FROM t WHERE a = %s AND b = %s"
    assert all("?" not in ddl for ddl in store.TABLES)


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL for a real Postgres run")
def test_postgres_round_trip(settings, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    store.put_profile_json(settings, "u:pgtest", "{}", "t")
    assert store.get_profile_json(settings, "u:pgtest") == "{}"
    assert store.delete_profile_row(settings, "u:pgtest")


def test_delete_stale_users_keeps_fresh_accounts(settings, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    store.upsert_user(settings, "old", "o@example.com", "Old", None, "2024-01-01T00:00:00Z")
    store.put_profile_json(settings, "u:old", "{}", "2024-01-01T00:00:00Z")
    store.upsert_user(settings, "new", "n@example.com", "New", None, "2026-10-30T00:00:00Z")
    now = datetime(2026, 10, 31, tzinfo=timezone.utc)
    assert store.delete_stale_users(settings, now) == 1
    assert store.get_user(settings, "old") is None and store.get_profile_json(settings, "u:old") is None
    assert store.get_user(settings, "new") is not None
