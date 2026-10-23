"""Read-side queries shared by the web app, the digest job and the Editor agent's tools."""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from trendsignal.config import Settings, SourceConfig, Watchlist
from trendsignal.db import connect, loads
from trendsignal.models import FEEDBACK_SIGNALS
from trendsignal.timeutil import now_utc, parse_iso, to_iso

TIER_SORT = {"must_know": 0, "worth_a_look": 1, "emerging": 2, "minor": 3}


@dataclass(frozen=True)
class SourceLink:
    name: str
    tier: str
    url: str


@dataclass(frozen=True)
class StoryView:
    id: int
    title: str
    tier: str
    importance: float
    rank_score: float
    category: str
    status: str
    tldr: str
    why_it_matters: str
    audience: tuple[str, ...]
    entities: tuple[str, ...]
    time_to_understand_min: int
    is_breaking_change: bool
    first_seen_at: datetime
    reasons: tuple[str, ...]
    features: dict[str, float]
    url: str
    sources: tuple[SourceLink, ...]
    enriched_by: str

    def as_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "tier": self.tier, "importance": self.importance,
            "rank_score": self.rank_score, "category": self.category, "status": self.status, "tldr": self.tldr,
            "why_it_matters": self.why_it_matters, "audience": list(self.audience), "entities": list(self.entities),
            "time_to_understand_min": self.time_to_understand_min, "is_breaking_change": self.is_breaking_change,
            "first_seen_at": to_iso(self.first_seen_at), "reasons": list(self.reasons), "features": self.features,
            "url": self.url, "sources": [s.__dict__ for s in self.sources], "enriched_by": self.enriched_by,
        }


def _views(conn: sqlite3.Connection, rows: list[sqlite3.Row], sources: dict[str, SourceConfig]) -> list[StoryView]:
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in ids)
    links: dict[int, list[tuple[int, SourceLink]]] = {}
    anchors: dict[int, str] = {}
    for item in conn.execute(f"SELECT id, story_id, source_id, tier, canonical_url FROM items WHERE story_id IN ({placeholders})", ids):
        source = sources.get(item["source_id"])
        link = SourceLink(source.name if source else item["source_id"], item["tier"], item["canonical_url"])
        links.setdefault(item["story_id"], []).append((item["id"], link))
    for row in rows:
        anchors[row["id"]] = next((l.url for i, l in links.get(row["id"], []) if i == row["anchor_item_id"]), "")
    views = []
    for row in rows:
        story_links = sorted((l for _, l in links.get(row["id"], [])), key=lambda l: (l.tier, l.name))
        views.append(StoryView(
            id=row["id"], title=row["title"], tier=row["tier"] or "minor", importance=row["importance"] or 0.0,
            rank_score=row["rank_score"] or 0.0, category=row["category"] or "opinion", status=row["status"],
            tldr=row["tldr"] or "", why_it_matters=row["why_it_matters"] or "",
            audience=tuple(loads(row["audience_json"], [])),
            entities=tuple(e["name"] for e in loads(row["entities_json"], [])),
            time_to_understand_min=int(row["time_to_understand_min"] or 2),
            is_breaking_change=bool(row["is_breaking_change"]), first_seen_at=parse_iso(row["first_seen_at"]),
            reasons=tuple(loads(row["reasons_json"], [])), features=loads(row["features_json"], {}),
            url=anchors[row["id"]] or (story_links[0].url if story_links else ""),
            sources=tuple(story_links), enriched_by=row["enriched_by"] or "",
        ))
    return views


def feed(settings: Settings, sources: dict[str, SourceConfig], *, tier: str | None = None,
         category: str | None = None, audience: str | None = None, since_hours: int = 72,
         limit: int = 300, now: datetime | None = None) -> list[StoryView]:
    now = now or now_utc()
    clauses = ["tier IS NOT NULL", "first_seen_at >= ?"]
    params: list = [to_iso(now - timedelta(hours=since_hours))]
    if tier:
        clauses.append("tier = ?")
        params.append(tier)
    if category:
        clauses.append("category = ?")
        params.append(category)
    if audience and re.fullmatch(r"[a-z_]+", audience):
        clauses.append("audience_json LIKE ?")
        params.append(f'%"{audience}"%')
    query = f"SELECT * FROM stories WHERE {' AND '.join(clauses)} ORDER BY importance DESC LIMIT ?"
    with connect(settings.db_path) as conn:
        views = _views(conn, conn.execute(query, (*params, limit)).fetchall(), sources)
    return sorted(views, key=lambda v: (TIER_SORT.get(v.tier, 9),
                                        -(v.importance if v.tier == "must_know" else v.rank_score)))


def get_story(settings: Settings, sources: dict[str, SourceConfig], story_id: int) -> StoryView | None:
    with connect(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchall()
        views = _views(conn, rows, sources)
    return views[0] if views else None


def story_reports(settings: Settings, sources: dict[str, SourceConfig], story_id: int) -> list[dict]:
    """Every source report in a story, for the Editor's get_story tool."""
    with connect(settings.db_path) as conn:
        rows = conn.execute("SELECT * FROM items WHERE story_id = ? ORDER BY tier, published_at", (story_id,)).fetchall()
    return [{
        "source": sources[r["source_id"]].name if r["source_id"] in sources else r["source_id"],
        "tier": r["tier"], "title": r["title"], "url": r["canonical_url"], "published_at": r["published_at"],
        "excerpt": r["text"][:600], "engagement": loads(r["engagement_json"], {}),
    } for r in rows]


def digest_stories(settings: Settings, sources: dict[str, SourceConfig], kind: str, now: datetime) -> dict[str, list[StoryView]]:
    """Daily: stories first seen in the last 36 h. Weekly: the 10 most important of the last 7 days."""
    if kind == "weekly":
        week = [v for v in feed(settings, sources, since_hours=7 * 24, now=now) if v.tier in ("must_know", "worth_a_look")]
        top = sorted(week, key=lambda v: -v.importance)[:10]
        return {"must_know": top, "worth_a_look": [], "emerging": [], "minor": []}
    views = feed(settings, sources, since_hours=36, now=now)
    grouped: dict[str, list[StoryView]] = {"must_know": [], "worth_a_look": [], "emerging": [], "minor": []}
    for view in views:
        grouped.setdefault(view.tier, []).append(view)
    grouped["worth_a_look"] = grouped["worth_a_look"][:8]
    grouped["emerging"] = grouped["emerging"][:3]
    return grouped


def _story_terms(row: sqlite3.Row) -> set[str]:
    return {e["name"].lower() for e in loads(row["entities_json"], [])}


def trend_counts(settings: Settings, now: datetime | None = None, weeks: int = 4, top: int = 10) -> list[dict]:
    """Entities mentioned in more stories this week than their average over the previous `weeks` weeks."""
    now = now or now_utc()
    this_week_start = now - timedelta(days=7)
    with connect(settings.db_path) as conn:
        rows = conn.execute("SELECT first_seen_at, entities_json FROM stories WHERE first_seen_at >= ?",
                            (to_iso(now - timedelta(days=7 * (weeks + 1))),)).fetchall()
    current, previous = Counter(), Counter()
    for row in rows:
        bucket = current if parse_iso(row["first_seen_at"]) >= this_week_start else previous
        bucket.update(_story_terms(row))
    rising = []
    for term, count in current.items():
        baseline = previous.get(term, 0) / weeks
        if count >= 2 and count > baseline:
            rising.append({"topic": term, "this_week": count, "weekly_average_before": round(baseline, 2),
                           "change": round(count - baseline, 2)})
    return sorted(rising, key=lambda r: (-r["change"], r["topic"]))[:top]


def skill_momentum(settings: Settings, watchlist: Watchlist, now: datetime | None = None, weeks: int = 4) -> list[dict]:
    """Per-skill weekly story counts for SKidea's skill scoring ("adoption momentum")."""
    now = now or now_utc()
    with connect(settings.db_path) as conn:
        rows = conn.execute("SELECT first_seen_at, title, tldr, entities_json FROM stories WHERE first_seen_at >= ?",
                            (to_iso(now - timedelta(days=7 * (weeks + 1))),)).fetchall()
    patterns = {skill: [re.compile(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])") for t in terms]
                for skill, terms in watchlist.skills.items()}
    result = []
    for skill, skill_patterns in patterns.items():
        weekly = [0] * (weeks + 1)  # index 0 = this week
        for row in rows:
            text = " ".join([row["title"], row["tldr"] or "", *_story_terms(row)]).lower()
            if any(p.search(text) for p in skill_patterns):
                age_weeks = int((now - parse_iso(row["first_seen_at"])).days // 7)
                if age_weeks <= weeks:
                    weekly[age_weeks] += 1
        baseline = sum(weekly[1:]) / weeks
        momentum = (weekly[0] - baseline) / max(baseline, 1.0)
        result.append({"skill": skill, "this_week": weekly[0], "weekly_average_before": round(baseline, 2),
                       "momentum": round(momentum, 3), "weekly_counts": weekly})
    return sorted(result, key=lambda r: -r["momentum"])


def source_health(settings: Settings, sources: tuple[SourceConfig, ...]) -> list[dict]:
    with connect(settings.db_path) as conn:
        states = {r["source_id"]: r for r in conn.execute("SELECT * FROM source_state").fetchall()}
    health = []
    for source in sources:
        state = states.get(source.id)
        health.append({
            "id": source.id, "name": source.name, "tier": source.tier, "adapter": source.adapter,
            "enabled": source.enabled, "status": (state["status"] if state else "never run") if source.enabled else "disabled",
            "last_ok_at": state["last_ok_at"] if state else None, "last_error": state["last_error"] if state else None,
            "consecutive_failures": state["consecutive_failures"] if state else 0,
        })
    return health


def latest_digest(settings: Settings, kind: str) -> dict | None:
    with connect(settings.db_path) as conn:
        row = conn.execute("SELECT * FROM digests WHERE kind = ? ORDER BY digest_date DESC LIMIT 1", (kind,)).fetchone()
    if row is None:
        return None
    return {"kind": row["kind"], "date": row["digest_date"], "body_md": row["body_md"],
            "generated_by": row["generated_by"], "verification": loads(row["verification_json"], {}),
            "created_at": row["created_at"]}


def record_feedback(settings: Settings, story_id: int, signal: str) -> bool:
    if signal not in FEEDBACK_SIGNALS:
        raise ValueError(f"signal must be one of {FEEDBACK_SIGNALS}")
    with connect(settings.db_path) as conn:
        if conn.execute("SELECT 1 FROM stories WHERE id = ?", (story_id,)).fetchone() is None:
            return False
        conn.execute("INSERT INTO feedback (story_id, signal, created_at) VALUES (?, ?, ?)",
                     (story_id, signal, to_iso(now_utc())))
    return True


def last_run(settings: Settings, job_prefix: str) -> str | None:
    with connect(settings.db_path) as conn:
        row = conn.execute("SELECT MAX(finished_at) AS at FROM runs WHERE job LIKE ?", (f"{job_prefix}%",)).fetchone()
    return row["at"] if row else None
