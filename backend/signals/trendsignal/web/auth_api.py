"""Optional accounts with Replit Auth (OpenID Connect, authorization code + PKCE, public client).

Login is on only when REPL_ID and SESSION_SECRET are set. The session is a signed cookie (HMAC-SHA256);
tokens from Replit are used once in the callback and never stored or logged. owner_of() is the one place
that turns a request into the key a profile is stored under.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import FastAPI, Header, Request
from fastapi.responses import RedirectResponse, Response

from intake import ledger
from trendsignal.config import Settings
from trendsignal.web import accounts_store as store
from trendsignal.web.app import RateLimiter, envelope

log = logging.getLogger("trendsignal.auth")

SESSION_COOKIE, OIDC_COOKIE, LINK_COOKIE = "varity_session", "varity_oidc", "varity_link"
SESSION_TTL_S = 30 * 24 * 3600
FLOW_TTL_S = 600
DEFAULT_RETURN = "/#/profile"
FAILED = "/#/profile?login=failed"
LIMIT_PER_MINUTE = 30
GOOGLE_ID_RE = re.compile(r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$", re.IGNORECASE)
_warned_google_id = False
_discovery_cache: dict = {}
_discovery_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get("REPL_ID") and os.environ.get("SESSION_SECRET"))


def _issuer() -> str:
    return os.environ.get("OIDC_ISSUER", "https://replit.com/oidc").rstrip("/")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str) -> str:
    return _b64(hmac.new(os.environ["SESSION_SECRET"].encode(), body.encode(), hashlib.sha256).digest())


def sign(payload: dict, ttl: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode())
    return f"{body}.{_mac(body)}"


def unsign(value: str | None) -> dict | None:
    """The payload when the signature and expiry are good, else None."""
    if not value or "." not in value or not enabled():
        return None
    body, _, mac = value.partition(".")
    if not hmac.compare_digest(mac, _mac(body)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("exp", 0) > time.time() else None


def session_sub(request: Request) -> str | None:
    payload = unsign(request.cookies.get(SESSION_COOKIE))
    sub = payload.get("sub") if payload else None
    return sub if isinstance(sub, str) and sub else None


def owner_of(request: Request, token: str | None) -> str | None:
    """Signed-in account first, else the anonymous browser token."""
    sub = session_sub(request)
    return "u:" + sub if sub else store.token_owner(token)


# ---- Replit side (these three are the only network calls; tests replace them)

def discovery() -> dict:
    issuer = _issuer()
    with _discovery_lock:
        cached = _discovery_cache.get(issuer)
        if cached and cached[0] > time.time():
            return cached[1]
    doc = httpx.get(issuer + "/.well-known/openid-configuration", timeout=10).raise_for_status().json()
    with _discovery_lock:
        _discovery_cache[issuer] = (time.time() + 3600, doc)
    return doc


def exchange_code(token_endpoint: str, form: dict) -> dict:
    return httpx.post(token_endpoint, data=form, timeout=10).raise_for_status().json()


def fetch_userinfo(userinfo_endpoint: str, access_token: str) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    return httpx.get(userinfo_endpoint, headers=headers, timeout=10).raise_for_status().json()


# ---- request helpers

def base_url(request: Request) -> str | None:
    """Public origin of this app, or None when the host is not one we serve (host-header injection)."""
    fixed = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if fixed:
        return fixed
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.headers.get("host", "")
    allowed = {d.strip() for d in os.environ.get("REPLIT_DOMAINS", "").split(",") if d.strip()}
    if allowed and host not in allowed:
        return None
    return f"{proto}://{host}" if host else None


def safe_return(value: str | None) -> str:
    """Same-origin path only: starts with a single "/", no backslash or control characters."""
    ok = (value and len(value) <= 200 and value[0] == "/" and not value.startswith("//")
          and "\\" not in value and value.isprintable())
    return value if ok else DEFAULT_RETURN


def _cookie(response: Response, request: Request, name: str, value: str, max_age: int, path: str = "/") -> None:
    local_http = urlparse(base_url(request) or "").scheme == "http" and request.url.hostname in ("localhost", "127.0.0.1")
    response.set_cookie(name, value, max_age=max_age, path=path, httponly=True, secure=not local_http, samesite="lax")


def _failed() -> RedirectResponse:
    response = RedirectResponse(FAILED, status_code=302)
    response.delete_cookie(OIDC_COOKIE, path="/api")
    response.delete_cookie(LINK_COOKIE, path="/api")
    return response


def _check_id_token(id_token: str, issuer: str, client_id: str, nonce: str) -> str | None:
    """Claims come over TLS straight from the token endpoint, so the signature is not re-checked. Returns sub."""
    claims = json.loads(_unb64(id_token.split(".")[1]))
    aud = claims.get("aud")
    if str(claims.get("iss", "")).rstrip("/") != issuer or client_id not in (aud if isinstance(aud, list) else [aud]):
        raise ValueError("id_token iss/aud")
    if float(claims.get("exp", 0)) <= time.time() or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("id_token exp/nonce")
    return claims.get("sub")


def add_auth_routes(app: FastAPI, settings: Settings) -> None:
    limiter = RateLimiter(LIMIT_PER_MINUTE)

    def limited(request: Request) -> bool:
        from trendsignal.web.cv_api import client_ip  # here: cv_api imports this module

        return not limiter.allow(client_ip(request))

    def off():
        return envelope(error="accounts are not enabled on this server (needs REPL_ID and SESSION_SECRET)", status=404,
                        meta={"code": "LOGIN_DISABLED"})

    @app.post("/api/login/prepare")
    def api_login_prepare(request: Request, x_profile_token: str | None = Header(default=None)):
        """Remember which anonymous profile to carry into the account: the callback has no X-Profile-Token header."""
        if not enabled():
            return off()
        if limited(request):
            return envelope(error="too many requests, try again in a minute", status=429)
        owner = store.token_owner(x_profile_token)
        response = envelope({"linked": owner is not None})
        if owner:
            _cookie(response, request, LINK_COOKIE, sign({"owner": owner}, FLOW_TTL_S), FLOW_TTL_S, "/api")
        return response

    @app.get("/api/login")
    def api_login(request: Request, returnTo: str | None = None):
        if not enabled():
            return off()
        if limited(request):
            return envelope(error="too many requests, try again in a minute", status=429)
        base = base_url(request)
        if base is None:
            return envelope(error="unknown host", status=400)
        try:
            endpoint = discovery()["authorization_endpoint"]
        except (httpx.HTTPError, KeyError, ValueError):
            return envelope(error="sign-in is unavailable right now", status=502)
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        query = urlencode({
            "response_type": "code", "client_id": os.environ["REPL_ID"], "redirect_uri": base + "/api/callback",
            "scope": "openid profile email", "state": state, "nonce": nonce, "prompt": "login consent",
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256",
        })
        response = RedirectResponse(f"{endpoint}?{query}", status_code=302)
        flow = {"s": state, "n": nonce, "v": verifier, "r": safe_return(returnTo)}
        _cookie(response, request, OIDC_COOKIE, sign(flow, FLOW_TTL_S), FLOW_TTL_S, "/api")
        return response

    @app.get("/api/callback")
    def api_callback(request: Request, code: str | None = None, state: str | None = None):
        if not enabled() or limited(request):
            return _failed()
        flow = unsign(request.cookies.get(OIDC_COOKIE))
        base = base_url(request)
        if not (flow and code and state and base) or not hmac.compare_digest(state, str(flow.get("s", ""))):
            return _failed()
        try:
            client_id = os.environ["REPL_ID"]
            doc = discovery()
            tokens = exchange_code(doc["token_endpoint"], {
                "grant_type": "authorization_code", "code": code, "redirect_uri": base + "/api/callback",
                "client_id": client_id, "code_verifier": flow["v"]})
            id_sub = None
            if tokens.get("id_token"):
                id_sub = _check_id_token(tokens["id_token"], _issuer(), client_id, flow["n"])
            info = fetch_userinfo(doc["userinfo_endpoint"], tokens["access_token"])
            sub = str(info.get("sub") or "")
            if not sub or (id_sub and str(id_sub) != sub):
                raise ValueError("missing or mismatched sub")
            name = " ".join(p for p in (info.get("first_name"), info.get("last_name")) if p) or info.get("username")
            store.upsert_user(settings, sub, info.get("email"), name, info.get("profile_image_url"), ledger.now_iso())
            link = unsign(request.cookies.get(LINK_COOKIE))
            if link and isinstance(link.get("owner"), str):
                store.move_profile(settings, link["owner"], "u:" + sub)
        except Exception as exc:  # any failure sends the user back; log the type only (no tokens, codes or cookies)
            log.warning("login failed: %s", type(exc).__name__)
            return _failed()
        response = RedirectResponse(safe_return(flow.get("r")), status_code=302)
        _cookie(response, request, SESSION_COOKIE, sign({"sub": sub, "iat": int(time.time())}, SESSION_TTL_S), SESSION_TTL_S)
        response.delete_cookie(OIDC_COOKIE, path="/api")
        response.delete_cookie(LINK_COOKIE, path="/api")
        return response

    @app.get("/api/me")
    def api_me(request: Request, x_profile_token: str | None = Header(default=None)):
        if limited(request):
            return envelope(error="too many requests, try again in a minute", status=429)
        # A public OAuth client id: the browser asks Google for a Tasks token itself (see app.js).
        # Never echo anything else (a pasted client secret would be published to every visitor).
        global _warned_google_id
        raw = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
        valid = bool(GOOGLE_ID_RE.match(raw))
        if raw and not valid and not _warned_google_id:
            _warned_google_id = True
            log.warning("GOOGLE_CLIENT_ID is not a Google OAuth client id; Google Tasks is hidden")
        google = {"googleClientId": raw if valid else None}
        if not enabled():
            return envelope({"enabled": False, "signedIn": False, "user": None, "hasProfile": False, **google})
        sub = session_sub(request)
        user = store.get_user(settings, sub) if sub else None
        owner = "u:" + sub if user else store.token_owner(x_profile_token)
        has = bool(owner and store.get_profile_json(settings, owner) is not None)
        return envelope({"enabled": True, "signedIn": user is not None, "user": user, "hasProfile": has, **google})

    @app.get("/api/logout")
    def api_logout(request: Request):
        target = "/"
        base = base_url(request)
        if enabled() and base:
            try:
                query = urlencode({"client_id": os.environ["REPL_ID"], "post_logout_redirect_uri": base + "/"})
                target = f"{discovery()['end_session_endpoint']}?{query}"
            except (httpx.HTTPError, KeyError, ValueError):
                pass
        response = RedirectResponse(target, status_code=302)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.delete("/api/me")
    def api_me_delete(request: Request):
        sub = session_sub(request)
        if sub is None:
            return envelope(error="not signed in", status=401)
        if limited(request):
            return envelope(error="too many requests, try again in a minute", status=429)
        store.delete_user(settings, sub)
        response = envelope({"deleted": True})
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response
