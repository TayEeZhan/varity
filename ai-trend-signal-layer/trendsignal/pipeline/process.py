"""Core path after collection (ARCHITECTURE_JEV_RANKER.md section 3):

    cluster -> rules enrichment (+ optional Haiku for unsure categories) -> feature vector
            -> formula score and, when configured, Jev's probabilities -> ranker -> SQLite

"Code extracts, Jev decides, code ranks." Jev ranks only when TRENDSIGNAL_RANKER=jev; otherwise
its answers are stored as a second opinion beside the formula's ranking.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

import anthropic

from trendsignal.config import Settings, SourceConfig, Watchlist, Weights
from trendsignal.db import connect, dumps, loads
from trendsignal.decision.jev import JevClient, JevDecision, JevError
from trendsignal.decision.ranker import RankedStory, RankEntry, rank_stories
from trendsignal.llm import LlmGate, llm_spent_since, make_client
from trendsignal.pipeline.cluster import ClusterItem, assign_clusters
from trendsignal.pipeline.enrich import EnrichItem, EnrichOutcome, enrich_story
from trendsignal.pipeline.features import BuiltFeatures, FeatureInputs, build_features
from trendsignal.pipeline.heuristics import classify_with_confidence, heuristic_enrichment
from trendsignal.pipeline.normalise import reading_minutes
from trendsignal.pipeline.score import ScoredItem, ScoreInputs, engagement_rate, freshness, score_story
from trendsignal.pipeline.similarity import TfidfIndex, cosine, doc_text
from trendsignal.timeutil import hours_between, local_date, local_day_start, now_utc, parse_iso, to_iso

log = logging.getLogger(__name__)

TIER_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}
SOCIAL_ADAPTERS = frozenset({"bluesky", "x_api", "threads"})
MULTI_AUTHOR_ADAPTERS = frozenset({"hn", "bluesky", "x_api", "threads"})
SCORE_WINDOW_DAYS = 7
BASELINE_DAYS = 14
ENRICH_BATCH_LIMIT = 300
ENRICH_WORKERS = 4
JEV_WORKERS = 4
HISTORY_MIN_DELTA = 1.0
HAIKU_THRESHOLD = 0.5  # rule confidence below this asks Haiku for the category (when enabled)
HAIKU_CATEGORY_CONFIDENCE = 0.9  # a validated Haiku label
DEFAULT_CATEGORY_CONFIDENCE = 0.5  # stories enriched before confidence was recorded
LLM_RETRY_BATCH_LIMIT = 100
LLM_RETRY_EVERY_HOURS = 6
LLM_RETRY_MAX_AGE_DAYS = 3


@dataclass(frozen=True)
class ProcessSummary:
    clustered_items: int
    new_stories: int
    enriched: int
    llm_enriched: int
    fallback_reason: str | None
    scored: int
    cost_usd: float
    run_id: str = ""
    ranked_by_jev: int = 0
    ranked_by_formula: int = 0
    jev_answers: int = 0  # stories with a Jev answer (ranking or second opinion)
    jev_note: str | None = None
    jev_cost_usd: float = 0.0


# ---------------------------------------------------------------- clustering

def _cluster_item(row: sqlite3.Row) -> ClusterItem:
    return ClusterItem(
        id=row["id"], source_id=row["source_id"], author=row["author"], title=row["title"], text=row["text"],
        canonical_url=row["canonical_url"], linked_url=row["linked_url"], content_hash=row["content_hash"],
        published_at=parse_iso(row["published_at"]), story_id=row["story_id"],
    )


def refresh_story(conn: sqlite3.Connection, story_id: int, now_iso: str) -> None:
    """Re-pick the anchor (best tier, then earliest). A new anchor means the story needs re-enrichment."""
    rows = conn.execute("SELECT id, tier, title, published_at FROM items WHERE story_id = ?", (story_id,)).fetchall()
    anchor = min(rows, key=lambda r: (TIER_ORDER[r["tier"]], r["published_at"]))
    story = conn.execute("SELECT anchor_item_id, enriched_at FROM stories WHERE id = ?", (story_id,)).fetchone()
    reenrich = story["anchor_item_id"] != anchor["id"] or story["enriched_at"] is None
    conn.execute(
        "UPDATE stories SET title = ?, anchor_item_id = ?, first_seen_at = ?, last_updated_at = ?,"
        " needs_enrichment = CASE WHEN ? THEN 1 ELSE needs_enrichment END WHERE id = ?",
        (anchor["title"], anchor["id"], min(r["published_at"] for r in rows), now_iso, int(reenrich), story_id),
    )


def jev_same_story_judge(jev: JevClient, sources: dict[str, SourceConfig]):
    """Adapter from the clusterer's borderline pairs to Jev's same_story question."""

    def describe(item: ClusterItem) -> dict:
        source = sources.get(item.source_id)
        return {"title": item.title, "source": source.name if source else item.source_id,
                "source_tier": source.tier if source else "?"}

    def judge(item: ClusterItem, other: ClusterItem, similarity: float, shared: list[str]) -> float | None:
        if not jev.open:
            return None
        state = {"item_a": describe(item), "item_b": describe(other),
                 "hours_apart": round(hours_between(min(item.published_at, other.published_at),
                                                    max(item.published_at, other.published_at)), 1),
                 "text_similarity": round(similarity, 2), "shared_distinctive_names": shared}
        try:
            return jev.same_story(state)
        except JevError as exc:
            log.info("same_story unanswered, keeping the items apart: %s", exc)
            return None

    return judge


def cluster_new_items(conn: sqlite3.Connection, weights: Weights, sources: dict[str, SourceConfig],
                      now: datetime, jev: JevClient | None = None) -> tuple[int, int]:
    new_items = [_cluster_item(r) for r in conn.execute("SELECT * FROM items WHERE story_id IS NULL").fetchall()]
    if not new_items:
        return 0, 0
    window_start = min(i.published_at for i in new_items) - timedelta(hours=weights.cluster_window_hours)
    existing = [
        _cluster_item(r)
        for r in conn.execute("SELECT * FROM items WHERE story_id IS NOT NULL AND published_at >= ?",
                              (to_iso(window_start),)).fetchall()
    ]
    index = TfidfIndex(doc_text(i.title, i.text) for i in [*existing, *new_items])
    multi_author = frozenset(s.id for s in sources.values() if s.adapter in MULTI_AUTHOR_ADAPTERS)
    judge = jev_same_story_judge(jev, sources) if jev is not None else None
    assignments = assign_clusters(new_items, existing, index, weights, multi_author, judge)

    now_iso = to_iso(now)
    group_story: dict[int, int] = {}
    touched: set[int] = set()
    for item in sorted(new_items, key=lambda i: i.published_at):
        target = assignments[item.id]
        story_id = target.story_id if target.story_id is not None else group_story.get(target.new_group)
        if story_id is None:
            cursor = conn.execute(
                "INSERT INTO stories (title, anchor_item_id, first_seen_at, last_updated_at) VALUES (?, ?, ?, ?)",
                (item.title, item.id, to_iso(item.published_at), now_iso),
            )
            story_id = cursor.lastrowid
            group_story[target.new_group] = story_id
        conn.execute("UPDATE items SET story_id = ? WHERE id = ?", (story_id, item.id))
        touched.add(story_id)
    for story_id in touched:
        refresh_story(conn, story_id, now_iso)
    return len(new_items), len(group_story)


# ---------------------------------------------------------------- enrichment (rules, optional Haiku)

def _enrich_items(conn: sqlite3.Connection, story_id: int, sources: dict[str, SourceConfig]) -> list[EnrichItem]:
    rows = conn.execute("SELECT * FROM items WHERE story_id = ?", (story_id,)).fetchall()
    rows = sorted(rows, key=lambda r: (TIER_ORDER[r["tier"]], r["published_at"]))
    items = []
    for row in rows:
        source = sources.get(row["source_id"])
        engagement = loads(row["engagement_json"], {})
        items.append(EnrichItem(
            source_name=source.name if source else row["source_id"], tier=row["tier"], title=row["title"],
            text=row["text"], url=row["canonical_url"], published_at=parse_iso(row["published_at"]),
            upvotes=float(engagement.get("upvotes", 0.0)),
            is_release_feed=bool(source and source.params.get("title_prefix")),
        ))
    return items


@dataclass(frozen=True)
class _Enriched:
    story_id: int
    items: list[EnrichItem]
    outcome: EnrichOutcome
    category_confidence: float
    category_source: str  # "rules" or "haiku"


def enrich_one(story_id: int, items: list[EnrichItem], client: anthropic.Anthropic | None, model: str,
               gate: LlmGate, dev_terms: tuple[str, ...]) -> _Enriched:
    """Rules always run. Haiku is asked only when a client is given and the rules are unsure."""
    anchor = items[0]
    combined = " ".join(item.text for item in items[:4])
    _category, confidence = classify_with_confidence(anchor.title, combined, anchor.tier, anchor.is_release_feed)
    if client is not None and confidence < HAIKU_THRESHOLD:
        outcome = enrich_story(items, client, model, gate, dev_terms)
        if outcome.fallback_reason is None:
            return _Enriched(story_id, items, outcome, HAIKU_CATEGORY_CONFIDENCE, "haiku")
        return _Enriched(story_id, items, outcome, confidence, "rules")
    enrichment = heuristic_enrichment(anchor.title, combined, anchor.tier, anchor.is_release_feed,
                                      max(item.upvotes for item in items), dev_terms)
    return _Enriched(story_id, items, EnrichOutcome(enrichment, 0.0, None), confidence, "rules")


def _save_enrichment(conn: sqlite3.Connection, result: _Enriched, now_iso: str) -> None:
    e = result.outcome.enrichment
    conn.execute(
        "UPDATE stories SET category = ?, entities_json = ?, change_magnitude = ?, magnitude_reason = ?,"
        " audience_json = ?, is_breaking_change = ?, tldr = ?, why_it_matters = ?, evidence_json = ?,"
        " time_to_understand_min = ?, enriched_by = ?, enriched_at = ?, needs_enrichment = 0,"
        " category_confidence = ?, category_source = ? WHERE id = ?",
        (e.category, dumps([{"name": x.name, "type": x.type} for x in e.entities]), e.change_magnitude,
         e.magnitude_reason, dumps(list(e.audience)), int(e.is_breaking_change), e.tldr, e.why_it_matters,
         dumps(list(e.evidence_quotes)), reading_minutes(result.items[0].text, e.category), e.enriched_by, now_iso,
         round(result.category_confidence, 2), result.category_source, result.story_id),
    )


def _stories_to_enrich(conn: sqlite3.Connection, llm_available: bool, now: datetime) -> list[int]:
    """New or changed stories first. When Haiku is available, also retry recent unsure stories that
    fell back to rules (budget hit, rate limit, API error), at most once every few hours."""
    pending = [r["id"] for r in conn.execute(
        "SELECT id FROM stories s WHERE needs_enrichment = 1 AND EXISTS (SELECT 1 FROM items WHERE story_id = s.id)"
        " ORDER BY first_seen_at DESC LIMIT ?", (ENRICH_BATCH_LIMIT,)).fetchall()]
    room = min(LLM_RETRY_BATCH_LIMIT, ENRICH_BATCH_LIMIT - len(pending))
    if not llm_available or room <= 0:
        return pending
    retry = [r["id"] for r in conn.execute(
        "SELECT id FROM stories WHERE needs_enrichment = 0 AND COALESCE(category_source, 'rules') = 'rules'"
        " AND COALESCE(category_confidence, 0) < ? AND first_seen_at >= ? AND enriched_at <= ?"
        " ORDER BY first_seen_at DESC LIMIT ?",
        (HAIKU_THRESHOLD, to_iso(now - timedelta(days=LLM_RETRY_MAX_AGE_DAYS)),
         to_iso(now - timedelta(hours=LLM_RETRY_EVERY_HOURS)), room)).fetchall()]
    return pending + retry


def enrich_pending(settings: Settings, sources: dict[str, SourceConfig], watchlist: Watchlist, gate: LlmGate,
                   client: anthropic.Anthropic | None, now: datetime | None = None) -> tuple[int, int, str | None]:
    llm_available = client is not None and gate.open
    with connect(settings.db_path) as conn:
        story_ids = _stories_to_enrich(conn, llm_available, now or now_utc())
        jobs = [(story_id, _enrich_items(conn, story_id, sources)) for story_id in story_ids]
    jobs = [(story_id, items) for story_id, items in jobs if items]
    if not jobs:
        return 0, 0, None

    def run(job: tuple[int, list[EnrichItem]]) -> _Enriched:
        return enrich_one(job[0], job[1], client, settings.enrich_model, gate, watchlist.dev_terms)

    with ThreadPoolExecutor(max_workers=ENRICH_WORKERS if llm_available else 1) as pool:
        results = list(pool.map(run, jobs))

    now_iso = to_iso(now_utc())
    with connect(settings.db_path) as conn:
        for result in results:
            _save_enrichment(conn, result, now_iso)
    haiku_count = sum(1 for r in results if r.category_source == "haiku")
    fallback = next((r.outcome.fallback_reason for r in results if r.outcome.fallback_reason), None)
    return len(results), haiku_count, fallback


# ---------------------------------------------------------------- features, decision, ranking

def _scored_item(row: sqlite3.Row, sources: dict[str, SourceConfig]) -> ScoredItem:
    source = sources.get(row["source_id"])
    return ScoredItem(
        source_id=row["source_id"], source_name=source.name if source else row["source_id"], tier=row["tier"],
        is_social=bool(source and source.adapter in SOCIAL_ADAPTERS), author=row["author"],
        published_at=parse_iso(row["published_at"]), engagement=loads(row["engagement_json"], {}),
    )


def _baselines(conn: sqlite3.Connection, sources: dict[str, SourceConfig], now: datetime) -> dict[str, list[float]]:
    since = to_iso(now - timedelta(days=BASELINE_DAYS))
    baselines: dict[str, list[float]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM items WHERE published_at >= ? AND engagement_json != '{}'", (since,)):
        rate = engagement_rate(_scored_item(row, sources), now)
        if rate is not None:
            baselines[row["source_id"]].append(rate)
    return dict(baselines)


def _novelty(stories: list[sqlite3.Row], vectors: list[dict[str, float]], lookback: timedelta) -> list[float]:
    """1 - highest similarity to any earlier story within the lookback window (stories sorted by first_seen)."""
    starts = [parse_iso(s["first_seen_at"]) for s in stories]
    scores = []
    for i, start in enumerate(starts):
        best = 0.0
        for j in range(i - 1, -1, -1):
            if starts[j] < start - lookback:
                break
            best = max(best, cosine(vectors[i], vectors[j]))
        scores.append(1.0 - best)
    return scores


def _superseded_releases(conn: sqlite3.Connection, stories: list[sqlite3.Row], window_start: datetime) -> set[int]:
    """Release stories from the same feed: only the newest in the window keeps its tier."""
    release_ids = [s["id"] for s in stories if s["category"] == "dev_tool_release"
                   and parse_iso(s["first_seen_at"]) >= window_start]
    if not release_ids:
        return set()
    placeholders = ",".join("?" for _ in release_ids)
    rows = conn.execute(
        f"SELECT s.id, s.first_seen_at, i.source_id FROM stories s JOIN items i ON i.id = s.anchor_item_id"
        f" WHERE s.id IN ({placeholders}) ORDER BY s.first_seen_at DESC", release_ids).fetchall()
    newest_seen: set[str] = set()
    superseded = set()
    for row in rows:
        if row["source_id"] in newest_seen:
            superseded.add(row["id"])
        newest_seen.add(row["source_id"])
    return superseded


@dataclass(frozen=True)
class _StoryRecord:
    story: sqlite3.Row
    first_seen: datetime
    formula_features: dict[str, float]
    status: str


def _with_jev(entry: RankEntry, decision: JevDecision | None, error: str | None) -> RankEntry:
    return RankEntry(entry.story_id, entry.day, entry.built, entry.formula_score, entry.change_magnitude,
                     entry.confirmed, decision, error)


def _decide_all(jev: JevClient | None, entries: list[RankEntry]) -> list[RankEntry]:
    """Ask Jev about every story in parallel. A failed or skipped story keeps jev=None and its error."""
    if jev is None:
        return entries

    def decide(entry: RankEntry) -> RankEntry:
        if not jev.open:
            return _with_jev(entry, None, jev.reason)
        try:
            return _with_jev(entry, jev.decide(entry.built.features), None)
        except JevError as exc:
            return _with_jev(entry, None, str(exc))

    with ThreadPoolExecutor(max_workers=JEV_WORKERS) as pool:
        return list(pool.map(decide, entries))


def _reasons(ranked: RankedStory) -> list[str]:
    reasons = list(ranked.top_features) + list(ranked.notes)
    if ranked.tier_probs:
        prefix = "ranked by Jev" if ranked.ranked_by == "jev" else "Jev second opinion"
        reasons.append(f"{prefix}: P(must-know) {ranked.tier_probs['must_know']:.2f}")
    return reasons


def _store(conn: sqlite3.Connection, ranked: list[RankedStory], records: dict[int, _StoryRecord],
           weights: Weights, run_id: str, now: datetime) -> None:
    now_iso = to_iso(now)
    tau = weights.freshness_tau_hours["daily"]
    for r in ranked:
        record = records[r.story_id]
        story = record.story
        rank_score = round(r.final_score * freshness(hours_between(record.first_seen, now), tau), 2)
        conn.execute(
            "UPDATE stories SET importance = ?, rank_score = ?, tier = ?, features_json = ?, reasons_json = ?,"
            " status = ?, scored_at = ? WHERE id = ?",
            (r.final_score, rank_score, r.tier, dumps(record.formula_features), dumps(_reasons(r)),
             record.status, now_iso, r.story_id),
        )
        previous = story["importance"]
        if story["tier"] != r.tier or previous is None or abs(previous - r.final_score) >= HISTORY_MIN_DELTA:
            conn.execute(
                "INSERT INTO scores (story_id, computed_at, importance, tier, features_json, weights_version)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (r.story_id, now_iso, r.final_score, r.tier, dumps(r.built.features.as_dict()),
                 f"{weights.version}+{r.ranked_by}"),
            )
        conn.execute(
            "INSERT INTO rankings (run_id, story_id, computed_at, rank, ranked_by, tier, final_score, expected_impact,"
            " confidence, tier_probs_json, impact_probs_json, jev_model, jev_error, formula_score, features_json,"
            " top_features_json, notes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, r.story_id, now_iso, r.rank, r.ranked_by, r.tier, r.final_score, r.expected_impact,
             r.confidence, dumps(r.tier_probs) if r.tier_probs else None,
             dumps({str(k): v for k, v in r.impact_probs.items()}) if r.impact_probs else None,
             r.jev_model, r.jev_error, r.formula_score, dumps(r.built.features.as_dict()),
             dumps(list(r.top_features)), dumps(list(r.notes))),
        )


def rank_recent(conn: sqlite3.Connection, settings: Settings, weights: Weights, watchlist: Watchlist,
                sources: dict[str, SourceConfig], now: datetime, jev: JevClient | None = None,
                run_id: str = "") -> list[RankedStory]:
    lookback = timedelta(days=weights.novelty_lookback_days)
    window_start = now - timedelta(days=SCORE_WINDOW_DAYS)
    stories = conn.execute(
        "SELECT * FROM stories WHERE first_seen_at >= ? AND needs_enrichment = 0 ORDER BY first_seen_at",
        (to_iso(window_start - lookback),)).fetchall()
    if not stories:
        return []
    items_by_story: dict[int, list[ScoredItem]] = defaultdict(list)
    text_by_item: dict[int, str] = {}
    for row in conn.execute("SELECT * FROM items WHERE story_id IN (SELECT id FROM stories WHERE first_seen_at >= ?)",
                            (to_iso(window_start - lookback),)):
        items_by_story[row["story_id"]].append(_scored_item(row, sources))
        text_by_item[row["id"]] = row["text"]

    texts = [doc_text(s["title"], s["tldr"] or "") for s in stories]
    index = TfidfIndex(texts)
    novelty = _novelty(stories, [index.vector(t) for t in texts], lookback)
    baselines = _baselines(conn, sources, now)
    superseded = _superseded_releases(conn, stories, window_start)

    entries: list[RankEntry] = []
    records: dict[int, _StoryRecord] = {}
    for story, story_novelty in zip(stories, novelty):
        first_seen = parse_iso(story["first_seen_at"])
        items = tuple(items_by_story.get(story["id"], ()))
        if first_seen < window_start or not items:
            continue
        category = story["category"] or "opinion"
        formula = score_story(ScoreInputs(
            title=story["title"], category=category, change_magnitude=int(story["change_magnitude"] or 1),
            entity_names=tuple(e["name"] for e in loads(story["entities_json"], [])),
            tldr=story["tldr"] or "", is_breaking_change=bool(story["is_breaking_change"]),
            items=items, novelty=story_novelty,
        ), weights, baselines, watchlist.dev_terms, now)
        confidence = story["category_confidence"]
        built: BuiltFeatures = build_features(FeatureInputs(
            title=story["title"], text=text_by_item.get(story["anchor_item_id"], ""), category=category,
            category_confidence=DEFAULT_CATEGORY_CONFIDENCE if confidence is None else confidence,
            items=items, novelty=story_novelty, superseded=story["id"] in superseded, first_seen_at=first_seen,
        ), weights, baselines, watchlist.dev_terms, now)
        entries.append(RankEntry(story["id"], local_date(first_seen, settings.timezone), built,
                                 formula.importance, int(story["change_magnitude"] or 1), formula.confirmed))
        status = "unconfirmed" if formula.social_only else ("confirmed" if formula.confirmed else "community")
        records[story["id"]] = _StoryRecord(story, first_seen, formula.features, status)

    ranked = rank_stories(_decide_all(jev, entries), settings.ranker, weights)
    _store(conn, ranked, records, weights, run_id, now)
    return ranked


# ---------------------------------------------------------------- orchestration

def run_process(settings: Settings, sources: tuple[SourceConfig, ...], weights: Weights, watchlist: Watchlist,
                *, now: datetime | None = None, jev: JevClient | None = None,
                client_factory: Callable[[], anthropic.Anthropic] = make_client) -> ProcessSummary:
    now = now or now_utc()
    started = to_iso(now_utc())
    run_id = f"{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    source_map = {s.id: s for s in sources}
    with connect(settings.db_path) as conn:
        clustered, new_stories = cluster_new_items(conn, weights, source_map, now, jev)

    gate = LlmGate(settings, llm_spent_since(settings, to_iso(local_day_start(now, settings.timezone))), now)
    client = client_factory() if settings.haiku_fallback and gate.open else None
    enriched, haiku_count, fallback = 0, 0, None
    try:
        enriched, haiku_count, fallback = enrich_pending(settings, source_map, watchlist, gate, client, now)
    finally:
        # Record any Haiku spend right away, even if enrichment failed part-way, so the budget stays honest.
        with connect(settings.db_path) as conn:
            conn.execute(
                "INSERT INTO runs (job, started_at, finished_at, items, cost_usd, detail) VALUES ('enrich', ?, ?, ?, ?, ?)",
                (started, to_iso(now_utc()), enriched, round(gate.run_cost, 5), fallback),
            )
    if settings.haiku_fallback and client is None:
        fallback = gate.reason

    try:
        with connect(settings.db_path) as conn:
            ranked = rank_recent(conn, settings, weights, watchlist, source_map, now, jev, run_id)
    finally:
        if jev is not None:
            with connect(settings.db_path) as conn:
                conn.execute(
                    "INSERT INTO runs (job, started_at, finished_at, items, cost_usd, detail) VALUES ('jev', ?, ?, ?, ?, ?)",
                    (started, to_iso(now_utc()), jev.calls, jev.cost_usd, jev.reason),
                )

    by_jev = sum(1 for r in ranked if r.ranked_by == "jev")
    with connect(settings.db_path) as conn:
        conn.execute(
            "INSERT INTO runs (job, started_at, finished_at, items, detail) VALUES ('process', ?, ?, ?, ?)",
            (started, to_iso(now_utc()), clustered,
             f"run={run_id} new_stories={new_stories} ranked={len(ranked)} by_jev={by_jev}"),
        )
    return ProcessSummary(
        clustered_items=clustered, new_stories=new_stories, enriched=enriched, llm_enriched=haiku_count,
        fallback_reason=fallback, scored=len(ranked), cost_usd=round(gate.run_cost, 5), run_id=run_id,
        ranked_by_jev=by_jev, ranked_by_formula=len(ranked) - by_jev,
        jev_answers=sum(1 for r in ranked if r.tier_probs is not None),
        jev_note=jev.reason if jev is not None else
        "Jev not configured (set TYPESAFE_API_KEY, or enable Replit AI Integrations for OpenRouter)",
        jev_cost_usd=jev.cost_usd if jev is not None else 0.0,
    )
