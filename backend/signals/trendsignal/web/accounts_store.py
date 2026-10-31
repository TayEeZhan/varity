"""Profiles and users. Postgres when DATABASE_URL is set (Replit Database), else the SQLite file.

owner_key is "t:"+sha256(browser token) for anonymous use or "u:"+sub for a signed-in account.
The old SQLite table `profiles(token_hash, ...)` is read as a fallback and copied over on first read.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from trendsignal.config import Settings
from trendsignal.db import connect

TABLES = (
    "CREATE TABLE IF NOT EXISTS owner_profiles (owner_key TEXT PRIMARY KEY, profile_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS users (sub TEXT PRIMARY KEY, email TEXT, display_name TEXT, image_url TEXT, "
    "created_at TEXT NOT NULL, last_login_at TEXT NOT NULL)",
    # The cleaned CV (contacts already [email]/[phone]), kept apart so profile responses never carry it.
    "CREATE TABLE IF NOT EXISTS owner_cvs (owner_key TEXT PRIMARY KEY, cv_text TEXT NOT NULL, updated_at TEXT NOT NULL)",
    # The CV builder: the accepted draft (CvDraft + facts the user added) and the user's saved CV notes.
    "CREATE TABLE IF NOT EXISTS owner_cv_drafts (owner_key TEXT PRIMARY KEY, draft_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS owner_cv_notes (owner_key TEXT PRIMARY KEY, notes_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
    # Project and cert stations (proof/): boarded projects, reviews with jury votes, certs.
    "CREATE TABLE IF NOT EXISTS owner_proof (owner_key TEXT PRIMARY KEY, proof_json TEXT NOT NULL, updated_at TEXT NOT NULL)",
    # One running review per project, shared by every server copy. A lock older than REVIEW_LOCK_SECONDS is stale.
    "CREATE TABLE IF NOT EXISTS proof_review_locks (owner_key TEXT NOT NULL, project_id TEXT NOT NULL, "
    "started_at DOUBLE PRECISION NOT NULL, PRIMARY KEY (owner_key, project_id))",
)
REVIEW_LOCK_SECONDS = 600
# Owner-keyed text tables that go with the profile: deleted and moved with it. (table, column)
OWNED = (("owner_cvs", "cv_text"), ("owner_cv_drafts", "draft_json"), ("owner_cv_notes", "notes_json"),
         ("owner_proof", "proof_json"))
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


def _get_owned(settings: Settings, table: str, column: str, owner_key: str) -> str | None:
    row = _run(settings, f"SELECT {column} FROM {table} WHERE owner_key = ?", (owner_key,), fetch=True)
    return row[0] if row else None


def _put_owned(settings: Settings, table: str, column: str, owner_key: str, value: str, updated_at: str) -> None:
    _run(settings, f"INSERT INTO {table} (owner_key, {column}, updated_at) VALUES (?, ?, ?) "
         f"ON CONFLICT(owner_key) DO UPDATE SET {column} = excluded.{column}, updated_at = excluded.updated_at",
         (owner_key, value, updated_at))


def get_cv_text(settings: Settings, owner_key: str) -> str | None:
    return _get_owned(settings, "owner_cvs", "cv_text", owner_key)


def put_cv_text(settings: Settings, owner_key: str, cv_text: str, updated_at: str) -> None:
    _put_owned(settings, "owner_cvs", "cv_text", owner_key, cv_text, updated_at)


def get_cv_draft(settings: Settings, owner_key: str) -> str | None:
    return _get_owned(settings, "owner_cv_drafts", "draft_json", owner_key)


def put_cv_draft(settings: Settings, owner_key: str, draft_json: str, updated_at: str) -> None:
    _put_owned(settings, "owner_cv_drafts", "draft_json", owner_key, draft_json, updated_at)


def get_cv_notes(settings: Settings, owner_key: str) -> str | None:
    return _get_owned(settings, "owner_cv_notes", "notes_json", owner_key)


def put_cv_notes(settings: Settings, owner_key: str, notes_json: str, updated_at: str) -> None:
    _put_owned(settings, "owner_cv_notes", "notes_json", owner_key, notes_json, updated_at)


def get_proof(settings: Settings, owner_key: str) -> str | None:
    return _get_owned(settings, "owner_proof", "proof_json", owner_key)


def put_proof(settings: Settings, owner_key: str, proof_json: str, updated_at: str) -> None:
    _put_owned(settings, "owner_proof", "proof_json", owner_key, proof_json, updated_at)


def acquire_review(settings: Settings, owner_key: str, project_id: str, now: float) -> bool:
    """Take the review lock in one statement: true only for the caller that inserted the row."""
    _run(settings, "DELETE FROM proof_review_locks WHERE owner_key = ? AND project_id = ? AND started_at < ?",
         (owner_key, project_id, now - REVIEW_LOCK_SECONDS))
    return _run(settings, "INSERT INTO proof_review_locks (owner_key, project_id, started_at) VALUES (?, ?, ?) "
                "ON CONFLICT (owner_key, project_id) DO NOTHING", (owner_key, project_id, now)) == 1


def release_review(settings: Settings, owner_key: str, project_id: str) -> None:
    _run(settings, "DELETE FROM proof_review_locks WHERE owner_key = ? AND project_id = ?", (owner_key, project_id))


def review_running(settings: Settings, owner_key: str, project_id: str, now: float) -> bool:
    row = _run(settings, "SELECT started_at FROM proof_review_locks WHERE owner_key = ? AND project_id = ?",
               (owner_key, project_id), fetch=True)
    return bool(row) and row[0] >= now - REVIEW_LOCK_SECONDS


def delete_profile_row(settings: Settings, owner_key: str) -> bool:
    for table, _ in OWNED:
        _run(settings, f"DELETE FROM {table} WHERE owner_key = ?", (owner_key,))
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
    for table, column in OWNED:
        value = _get_owned(settings, table, column, src)
        if value is not None:
            _put_owned(settings, table, column, dst, value, row[1])
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
    delete_profile_row(settings, "u:" + sub)


RETENTION_DAYS = 365


def delete_stale_users(settings: Settings, now: datetime | None = None) -> int:
    """PDPA retention: delete accounts (and their profiles) with no login for 365 days. Returns how many."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)).replace(microsecond=0)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")  # same format as last_login_at, so text order is time order
    count = 0
    while row := _run(settings, "SELECT sub FROM users WHERE last_login_at < ? LIMIT 1", (cutoff_iso,), fetch=True):
        delete_user(settings, row[0])
        count += 1
    return count
