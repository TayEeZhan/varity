"""Jobs the CLI, the scheduler and the admin endpoint run: pipeline, digest."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anthropic

from trendsignal.agents.editor import build_tools, write_brief
from trendsignal.agents.template import render_brief, story_facts
from trendsignal.agents.verifier import verify_brief
from trendsignal.collectors.runner import CollectSummary, collect_due
from trendsignal.config import (Settings, SourceConfig, Watchlist, Weights, load_settings, load_sources,
                                load_watchlist, load_weights)
from trendsignal.db import connect, dumps, init_schema
from trendsignal.decision.jev import JevClient, make_jev_client
from trendsignal.delivery import send_telegram
from trendsignal.llm import LlmGate, llm_spent_since, make_client
from trendsignal.output import latest_run_id, ranking_document, ranking_rows, write_ranking
from trendsignal.pipeline.process import ProcessSummary, run_process
from trendsignal.queries import digest_stories, skill_momentum, story_reports, trend_counts
from trendsignal.timeutil import local_date, local_day_start, now_utc, to_iso

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    sources: tuple[SourceConfig, ...]
    weights: Weights
    watchlist: Watchlist
    source_map: dict[str, SourceConfig] = field(default_factory=dict)


def load_context(settings: Settings | None = None) -> AppContext:
    settings = settings or load_settings()
    init_schema(settings.db_path)
    sources = load_sources(settings.config_dir)
    return AppContext(settings, sources, load_weights(settings.config_dir), load_watchlist(settings.config_dir),
                      {s.id: s for s in sources})


class PipelineBusy(RuntimeError):
    """Another pipeline run is in progress in this process."""


# Two overlapping runs would both cluster the same unassigned items into duplicate stories.
# This guards the scheduler and the admin endpoint, which share the web process.
_PIPELINE_LOCK = threading.Lock()


def run_pipeline(ctx: AppContext, *, force: bool = False, only: set[str] | None = None, collect: bool = True,
                 client_factory: Callable[[], anthropic.Anthropic] = make_client,
                 jev_factory: Callable[[Settings], JevClient | None] = make_jev_client,
                 ) -> tuple[CollectSummary, ProcessSummary]:
    """Collect (unless collect=False), then cluster, extract features, decide and rank."""
    if not _PIPELINE_LOCK.acquire(blocking=False):
        raise PipelineBusy("a pipeline run is already in progress")
    try:
        collected = collect_due(ctx.settings, ctx.sources, force=force, only=only) if collect else CollectSummary(())
        processed = run_process(ctx.settings, ctx.sources, ctx.weights, ctx.watchlist,
                                jev=jev_factory(ctx.settings), client_factory=client_factory)
    finally:
        _PIPELINE_LOCK.release()
    log.info("pipeline: %d new items, %d errors, %d stories ranked (%d by Jev)",
             collected.new_items, collected.errors, processed.scored, processed.ranked_by_jev)
    return collected, processed


def output_dir(settings: Settings) -> Path:
    return settings.db_path.parent / "ranked"


def write_ranking_outputs(ctx: AppContext, out_dir: Path | None = None, *, hours: int = 72,
                          limit: int | None = None) -> tuple[dict, dict[str, Path]]:
    """Write the latest ranking as JSON and CSV, plus skills.json for SKidea's matching."""
    run_id = latest_run_id(ctx.settings)
    rows = ranking_rows(ctx.settings, ctx.source_map, run_id, hours=hours, limit=limit)
    document = ranking_document(ctx.settings, rows, run_id)
    paths = write_ranking(document, out_dir or output_dir(ctx.settings),
                          {"skills": skill_momentum(ctx.settings, ctx.watchlist)})
    return document, paths


def run_pipeline_if_idle(ctx: AppContext) -> None:
    """For background callers: skip quietly when a run is already going."""
    try:
        run_pipeline(ctx)
    except PipelineBusy:
        log.info("pipeline already running; skipped this trigger")
        return
    write_ranking_outputs(ctx)


def bootstrap_if_empty(ctx: AppContext) -> threading.Thread | None:
    """Fresh deploy (no ranked run yet): fill the database in a background thread. Never blocks startup."""
    if latest_run_id(ctx.settings) is not None:
        return None

    def work() -> None:
        try:
            run_pipeline_if_idle(ctx)
        except Exception:  # noqa: BLE001 - a failed first run must not take the server down
            log.exception("first pipeline run failed; the page keeps its offline snapshot")

    thread = threading.Thread(target=work, name="first-run", daemon=True)
    thread.start()
    return thread


@dataclass(frozen=True)
class DigestResult:
    kind: str
    digest_date: str
    generated_by: str
    body: str
    verification: dict
    cost_usd: float
    note: str | None
    delivered: bool


def _title(kind: str, now: datetime, tz: str) -> str:
    day = local_date(now, tz)
    if kind == "weekly":
        return f"AI & Tech Weekly · week ending {day:%a %d %b %Y}"
    return f"AI & Tech Brief · {day:%a %d %b %Y}"


def make_digest(ctx: AppContext, kind: str = "daily", *, now: datetime | None = None, use_llm: bool = True,
                deliver: bool = True, client_factory: Callable[[], anthropic.Anthropic] = make_client) -> DigestResult:
    if kind not in ("daily", "weekly"):
        raise ValueError("kind must be 'daily' or 'weekly'")
    settings = ctx.settings
    now = now or now_utc()
    started = to_iso(now_utc())
    title = _title(kind, now, settings.timezone)
    groups = digest_stories(settings, ctx.source_map, kind, now)
    views = [view for group in groups.values() for view in group]
    facts = {view.id: story_facts(view) for view in views}

    required = [view.id for view in groups.get("must_know", [])]
    template_check = verify_brief(render_brief(title, kind, groups), facts, title=title, required_ids=required)
    body, generated_by, verification = template_check.body, "template", template_check
    cost, note = 0.0, None

    gate = LlmGate(settings, llm_spent_since(settings, to_iso(local_day_start(now, settings.timezone))), now)
    if not views:
        note = "no ranked stories in this window yet"
    elif not use_llm:
        note = "LLM disabled for this run"
    elif not gate.open:
        note = gate.reason
    else:
        tools = build_tools(groups, lambda story_id: story_reports(settings, ctx.source_map, story_id),
                            lambda: trend_counts(settings, now))
        result = write_brief(client_factory(), settings.editor_model, title, kind, tools)
        cost = result.cost_usd
        if result.markdown is None:
            note = f"Editor unavailable ({result.error}); used the template"
        else:
            check = verify_brief(result.markdown, facts, title=title, required_ids=required)
            if check.passed():
                body, generated_by, verification = check.body, settings.editor_model, check
            else:
                missing = f", missing Must-know {list(check.missing_required)}" if check.missing_required else ""
                note = (f"Editor draft failed verification ({check.failed_lines}/{check.checked_lines} lines"
                        f"{missing}); used the template")

    digest_date = local_date(now, settings.timezone).isoformat()
    with connect(settings.db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO digests (kind, digest_date, story_ids_json, body_md, generated_by,"
            " verification_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, digest_date, dumps([v.id for v in views]), body, generated_by,
             dumps({**verification.as_dict(), "note": note}), to_iso(now_utc())),
        )
        conn.execute(
            "INSERT INTO runs (job, started_at, finished_at, items, cost_usd, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (f"digest:{kind}", started, to_iso(now_utc()), len(views), round(cost, 5), note),
        )
    delivered = False
    if deliver and views:
        delivered, delivery_note = send_telegram(settings, body)
        if delivery_note and delivery_note != "Telegram not configured":
            note = f"{note}; {delivery_note}" if note else delivery_note
    return DigestResult(kind, digest_date, generated_by, body, verification.as_dict(), round(cost, 5), note, delivered)
