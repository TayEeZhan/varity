"""Profiles and users. Postgres when DATABASE_URL is set (Replit Database), else the SQLite file.

owner_key is "t:"+sha256(browser token) for anonymous use or "u:"+sub for a signed-in account.
The old SQLite table `profiles(token_hash, ...)` is read as a fallback and copied over on first read.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3

from trendsignal.config import Settings
from trendsignal.db import connect

TABLES = (
    "CREATE TABLE IF NOT EXISTS owner_profiles (owner_key TEXT PRIMARY KEY, profile_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS users (sub TEXT PRIMARY KEY, email TEXT, display_name TEXT, image_url TEXT, "
    "created_at TEXT NOT NULL, last_login_at TEXT NOT NULL)",
)
_ready: set[str] = set()


def token_owner(token: str | None) -> str | None:
    if not token or len(token) > 100:
        return None
    return "t:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def database_url() -> str | None:
    return os.environ.get("DATABASE_URL") or None


def to_postgres(sql: str) -> str:
    """The SQL below is written with ? placeholders; psycopg wants %s."""
    return sql.replace("?", "%s")


def _run(settings: Settings, sql: str, params: tuple = (), *, fetch: bool = False):
    """Run one statement; returns the first row (or None) when fetch, else the affected row count."""
    url = database_url()
    if url:
        import psycopg  # only needed on Replit

        with psycopg.connect(url) as conn:  # commits on exit
            if url not in _ready:
                for ddl in TABLES:
                    conn.execute(ddl)
                _ready.add(url)
            cur = conn.execute(to_postgres(sql), params)
            return cur.fetchone() if fetch else cur.rowcount
    with connect(settings.db_path) as conn:
        for ddl in TABLES:
            conn.execute(ddl)
        cur = conn.execute(sql, params)
        return cur.fetchone() if fetch else cur.rowcount


def _legacy_json(settings: Settings, owner_key: str) -> str | None:
    if database_url() or not owner_key.startswith("t:"):
        return None
    try:
        row = _run(settings, "SELECT profile_json FROM profiles WHERE token_hash = ?", (owner_key[2:],), fetch=True)
    except sqlite3.OperationalError:
        return None
    return row[0] if row else None


def get_profile_json(settings: Settings, owner_key: str) -> str | None:
    row = _run(settings, "SELECT profile_json FROM owner_profiles WHERE owner_key = ?", (owner_key,), fetch=True)
    if row:
        return row[0]
    return _legacy_json(settings, owner_key)


def put_profile_json(settings: Settings, owner_key: str, profile_json: str, updated_at: str) -> None:
    _run(settings, "INSERT INTO owner_profiles (owner_key, profile_json, updated_at) VALUES (?, ?, ?) "
         "ON CONFLICT(owner_key) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at",
         (owner_key, profile_json, updated_at))


def delete_profile_row(settings: Settings, owner_key: str) -> bool:
    deleted = _run(settings, "DELETE FROM owner_profiles WHERE owner_key = ?", (owner_key,)) > 0
    if not database_url() and owner_key.startswith("t:"):
        try:
            deleted |= _run(settings, "DELETE FROM profiles WHERE token_hash = ?", (owner_key[2:],)) > 0
        except sqlite3.OperationalError:
            pass
    return deleted


def move_profile(settings: Settings, src: str, dst: str) -> bool:
    """Give the anonymous profile to an account. Never overwrites: false when dst has one or src has none."""
    if get_profile_json(settings, dst) is not None:
        return False
    row = _run(settings, "SELECT profile_json, updated_at FROM owner_profiles WHERE owner_key = ?", (src,), fetch=True)
    if row is None:
        legacy = _legacy_json(settings, src)
        row = (legacy, "") if legacy else None
    if row is None:
        return False
    put_profile_json(settings, dst, row[0], row[1])
    delete_profile_row(settings, src)
    return True


def upsert_user(settings: Settings, sub: str, email: str | None, name: str | None, image: str | None, now: str) -> None:
    _run(settings, "INSERT INTO users (sub, email, display_name, image_url, created_at, last_login_at) VALUES (?, ?, ?, ?, ?, ?) "
         "ON CONFLICT(sub) DO UPDATE SET email = excluded.email, display_name = excluded.display_name, "
         "image_url = excluded.image_url, last_login_at = excluded.last_login_at",
         (sub, email, name, image, now, now))


def get_user(settings: Settings, sub: str) -> dict | None:
    row = _run(settings, "SELECT email, display_name, image_url FROM users WHERE sub = ?", (sub,), fetch=True)
    return {"email": row[0], "name": row[1], "imageUrl": row[2]} if row else None


def delete_user(settings: Settings, sub: str) -> None:
    _run(settings, "DELETE FROM users WHERE sub = ?", (sub,))
    _run(settings, "DELETE FROM owner_profiles WHERE owner_key = ?", ("u:" + sub,))
