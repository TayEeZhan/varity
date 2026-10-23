"""SQLite connection and schema. Raw items are immutable; stories carry the latest score."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_state (
    source_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'ok',
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_run_at TEXT,
    last_ok_at TEXT,
    last_error TEXT,
    etag TEXT,
    last_modified TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    published_at TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    UNIQUE (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    anchor_item_id INTEGER,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unconfirmed',
    category TEXT,
    entities_json TEXT NOT NULL DEFAULT '[]',
    tldr TEXT,
    why_it_matters TEXT,
    audience_json TEXT NOT NULL DEFAULT '[]',
    is_breaking_change INTEGER NOT NULL DEFAULT 0,
    change_magnitude INTEGER,
    magnitude_reason TEXT,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    time_to_understand_min INTEGER,
    enriched_by TEXT,
    enriched_at TEXT,
    needs_enrichment INTEGER NOT NULL DEFAULT 1,
    importance REAL,
    rank_score REAL,
    tier TEXT,
    features_json TEXT,
    reasons_json TEXT,
    scored_at TEXT
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    raw_item_id INTEGER NOT NULL UNIQUE REFERENCES raw_items(id),
    source_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    linked_url TEXT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    author TEXT,
    published_at TEXT NOT NULL,
    engagement_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    story_id INTEGER REFERENCES stories(id)
);
CREATE INDEX IF NOT EXISTS idx_items_story ON items(story_id);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at);
CREATE INDEX IF NOT EXISTS idx_items_hash ON items(content_hash);
CREATE INDEX IF NOT EXISTS idx_items_url ON items(canonical_url);
CREATE INDEX IF NOT EXISTS idx_stories_first_seen ON stories(first_seen_at);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    computed_at TEXT NOT NULL,
    importance REAL NOT NULL,
    tier TEXT NOT NULL,
    features_json TEXT NOT NULL,
    weights_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'weekly')),
    digest_date TEXT NOT NULL,
    story_ids_json TEXT NOT NULL,
    body_md TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    verification_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (kind, digest_date)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    signal TEXT NOT NULL CHECK (signal IN ('useful', 'not_important', 'already_knew', 'wrong')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    items INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS x_users (
    username TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    followers INTEGER,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    computed_at TEXT NOT NULL,
    rank INTEGER NOT NULL,
    ranked_by TEXT NOT NULL CHECK (ranked_by IN ('jev', 'formula')),
    tier TEXT NOT NULL,
    final_score REAL NOT NULL,
    expected_impact REAL,
    confidence REAL,
    tier_probs_json TEXT,
    impact_probs_json TEXT,
    jev_model TEXT,
    jev_error TEXT,
    formula_score REAL NOT NULL,
    features_json TEXT NOT NULL,
    top_features_json TEXT NOT NULL,
    notes_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_rankings_run ON rankings(run_id, rank);

CREATE TABLE IF NOT EXISTS jev_cache (
    state_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    answers_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (state_hash, model)
);
"""

# Columns added after the first release; init_schema adds them to existing databases.
MIGRATIONS = (
    ("stories", "category_confidence", "REAL"),
    ("stories", "category_source", "TEXT"),
)


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a connection, commit on success, roll back on error, always close."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for table, column, kind in MIGRATIONS:
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
