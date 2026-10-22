"""Run due collectors, store what they return, and keep a per-source circuit breaker."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from trendsignal.collectors import ADAPTERS
from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, make_http_client
from trendsignal.config import Settings, SourceConfig
from trendsignal.db import connect, dumps
from trendsignal.models import RawItemIn
from trendsignal.pipeline.normalise import normalise
from trendsignal.timeutil import local_day_start, now_utc, parse_iso, to_iso

log = logging.getLogger(__name__)

STALE_AFTER_FAILURES = 3
STALE_RETRY_MINUTES = 360
FAILURE_RETRY_MINUTES = 30
MAX_FUTURE_SKEW = timedelta(days=1)  # feeds sometimes mis-date entries; far-future dates would win "fresh"
MAX_RAW_TEXT_CHARS = 20000
MAX_ITEM_AGE_DAYS = 30  # older entries in a feed (e.g. old GitHub releases) are history, not news


@dataclass(frozen=True)
class SourceOutcome:
    source_id: str
    status: str  # ok | not_modified | error | skipped
    new_items: int = 0
    updated_items: int = 0
    cost_usd: float = 0.0
    message: str | None = None


@dataclass(frozen=True)
class CollectSummary:
    outcomes: tuple[SourceOutcome, ...]

    @property
    def new_items(self) -> int:
        return sum(o.new_items for o in self.outcomes)

    @property
    def errors(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "error")

    @property
    def cost_usd(self) -> float:
        return round(sum(o.cost_usd for o in self.outcomes), 4)


def _state(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_state WHERE source_id = ?", (source_id,)).fetchone()


def is_due(source: SourceConfig, state: sqlite3.Row | None, now: datetime) -> bool:
    if state is None or not state["last_run_at"]:
        return True
    interval = source.poll_every_minutes
    if state["status"] == "stale":
        interval = max(interval, STALE_RETRY_MINUTES)
    elif state["consecutive_failures"]:
        interval = min(interval, FAILURE_RETRY_MINUTES)  # a daily source that just failed retries soon
    return now - parse_iso(state["last_run_at"]) >= timedelta(minutes=interval)


def spent_today(conn: sqlite3.Connection, job: str, since_iso: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM runs WHERE job = ? AND started_at >= ?",
        (job, since_iso),
    ).fetchone()
    return float(row["spent"])


def store_items(conn: sqlite3.Connection, source: SourceConfig, items: tuple[RawItemIn, ...], retrieved_at: str) -> tuple[int, int]:
    """Insert new raw items and their normalised rows. For known items, refresh engagement only."""
    new, updated = 0, 0
    retrieved = parse_iso(retrieved_at)
    oldest_allowed, newest_allowed = retrieved - timedelta(days=MAX_ITEM_AGE_DAYS), retrieved + MAX_FUTURE_SKEW
    for raw in items:
        if not (oldest_allowed <= raw.published_at <= newest_allowed) or not raw.url.startswith(("http://", "https://")):
            continue
        payload = {
            "title": raw.title,
            "text": raw.text[:MAX_RAW_TEXT_CHARS],
            "author": raw.author,
            "engagement": raw.engagement,
            **raw.payload,
        }
        cursor = conn.execute(
            "INSERT OR IGNORE INTO raw_items (source_id, external_id, url, payload_json, published_at, retrieved_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (source.id, raw.external_id, raw.url, dumps(payload), to_iso(raw.published_at), retrieved_at),
        )
        if cursor.rowcount == 1:
            norm = normalise(raw)
            conn.execute(
                "INSERT INTO items (raw_item_id, source_id, tier, canonical_url, linked_url, title, text, author,"
                " published_at, engagement_json, content_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (cursor.lastrowid, source.id, source.tier, norm.canonical_url, norm.linked_url, norm.title,
                 norm.text, raw.author, to_iso(raw.published_at), dumps(raw.engagement), norm.content_hash),
            )
            new += 1
        elif raw.engagement:
            conn.execute(
                "UPDATE items SET engagement_json = ? WHERE raw_item_id ="
                " (SELECT id FROM raw_items WHERE source_id = ? AND external_id = ?)",
                (dumps(raw.engagement), source.id, raw.external_id),
            )
            updated += 1
    return new, updated


def _save_state(conn: sqlite3.Connection, source_id: str, *, ok: bool, now_iso: str,
                error: str | None, result: CollectResult | None) -> None:
    previous = _state(conn, source_id)
    failures = 0 if ok else (int(previous["consecutive_failures"]) if previous else 0) + 1
    status = "ok" if ok else ("stale" if failures >= STALE_AFTER_FAILURES else "ok")
    etag = result.etag if result else (previous["etag"] if previous else None)
    last_modified = result.last_modified if result else (previous["last_modified"] if previous else None)
    last_ok = now_iso if ok else (previous["last_ok_at"] if previous else None)
    conn.execute(
        "INSERT OR REPLACE INTO source_state (source_id, status, consecutive_failures, last_run_at, last_ok_at,"
        " last_error, etag, last_modified) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source_id, status, failures, now_iso, last_ok, error, etag, last_modified),
    )


def collect_source(settings: Settings, source: SourceConfig, ctx: CollectContext) -> SourceOutcome:
    started = now_utc()
    job = f"collect:{source.id}"
    try:
        result = ADAPTERS[source.adapter](source, ctx)
    except Exception as exc:  # one broken source must not stop the others; it is recorded and retried
        message = f"{exc.__class__.__name__}: {exc}"
        if isinstance(exc, CollectError):
            log.warning("collect %s failed: %s", source.id, message)
        else:
            log.exception("collect %s failed unexpectedly", source.id)
        with connect(settings.db_path) as conn:
            _save_state(conn, source.id, ok=False, now_iso=to_iso(started), error=message, result=None)
            conn.execute(
                "INSERT INTO runs (job, started_at, finished_at, errors, detail) VALUES (?, ?, ?, 1, ?)",
                (job, to_iso(started), to_iso(now_utc()), message),
            )
        return SourceOutcome(source.id, "error", message=message)

    with connect(settings.db_path) as conn:
        new, updated = store_items(conn, source, result.items, to_iso(started))
        _save_state(conn, source.id, ok=True, now_iso=to_iso(started), error=None, result=result)
        conn.execute(
            "INSERT INTO runs (job, started_at, finished_at, items, cost_usd, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (job, to_iso(started), to_iso(now_utc()), new, result.cost_usd, result.note),
        )
    status = "not_modified" if result.not_modified else "ok"
    return SourceOutcome(source.id, status, new, updated, result.cost_usd, result.note)


def collect_due(settings: Settings, sources: tuple[SourceConfig, ...], *, force: bool = False,
                only: set[str] | None = None) -> CollectSummary:
    now = now_utc()
    outcomes: list[SourceOutcome] = []
    with make_http_client(settings) as http:
        for source in sources:
            if only and source.id not in only:
                continue
            if not source.enabled:
                outcomes.append(SourceOutcome(source.id, "skipped", message="disabled in sources.yaml"))
                continue
            with connect(settings.db_path) as conn:
                state = _state(conn, source.id)
                budget = None
                if source.daily_budget_usd is not None:
                    spent = spent_today(conn, f"collect:{source.id}", to_iso(local_day_start(now, settings.timezone)))
                    budget = max(0.0, source.daily_budget_usd - spent)
            if not force and not is_due(source, state, now):
                continue
            ctx = CollectContext(
                settings=settings,
                http=http,
                etag=state["etag"] if state else None,
                last_modified=state["last_modified"] if state else None,
                budget_remaining_usd=budget,
            )
            outcomes.append(collect_source(settings, source, ctx))
    return CollectSummary(tuple(outcomes))
