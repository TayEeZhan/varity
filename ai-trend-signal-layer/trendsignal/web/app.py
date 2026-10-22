"""FastAPI app: web feed, briefs, JSON API (success/data/error/meta envelope), RSS, feedback."""

from __future__ import annotations

import hmac
import html
import re
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from xml.sax.saxutils import escape

import markdown as md
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from trendsignal.agents.template import CATEGORY_LABELS
from trendsignal.jobs import AppContext, load_context, make_digest, run_pipeline_if_idle
from trendsignal.models import AUDIENCES, CATEGORIES
from trendsignal.queries import (feed, get_story, last_run, latest_digest, record_feedback, skill_momentum,
                                 source_health, story_reports, trend_counts)

WEB_DIR = Path(__file__).parent
TIER_ORDER = ("must_know", "worth_a_look", "emerging", "minor")
TIER_LABELS = {"must_know": "Must-know", "worth_a_look": "Worth a look", "emerging": "Emerging", "minor": "Minor"}
MINOR_SHOWN = 60
FEEDBACK_LIMIT_PER_MINUTE = 30
ADMIN_LIMIT_PER_MINUTE = 10


class FeedbackIn(BaseModel):
    story_id: int
    signal: Literal["useful", "not_important", "already_knew", "wrong"]


def envelope(data=None, *, error: str | None = None, meta: dict | None = None, status: int = 200) -> JSONResponse:
    return JSONResponse({"success": error is None, "data": data, "error": error, "meta": meta or {}}, status_code=status)


class RateLimiter:
    """Small in-memory sliding window per client IP. Enough for one instance on Replit."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self._limit, self._window = limit, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True


HREF_RE = re.compile(r'href="([^"]*)"')
IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


def _safe_href(match: re.Match[str]) -> str:
    target = html.unescape(match.group(1)).strip()
    if re.match(r"https?://", target, re.IGNORECASE) or (target.startswith("/") and not target.startswith("//")):
        return match.group(0)
    return 'href="#"'


def render_brief_html(body_md: str) -> str:
    """Escape first (the brief may come from an LLM that read untrusted pages), render Markdown, then
    keep only http(s) and same-site links and drop images. The claim verifier is the first gate; this is the second."""
    escaped = html.escape(body_md, quote=False)
    rendered = md.markdown(escaped, extensions=["sane_lists", "nl2br"])
    rendered = IMG_RE.sub("", HREF_RE.sub(_safe_href, rendered))
    return re.sub(r"\[S(\d+)\]", r'<a class="cite" href="/story/\1">S\1</a>', rendered)


def _check_admin(ctx: AppContext, token: str | None) -> None:
    expected = ctx.settings.admin_token
    if not expected:
        raise HTTPException(status_code=404, detail="admin endpoints are disabled (set ADMIN_TOKEN)")
    if not token or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=403, detail="invalid admin token")


def create_app(ctx: AppContext | None = None) -> FastAPI:
    ctx = ctx or load_context()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler = None
        if ctx.settings.scheduler_enabled:
            from trendsignal.scheduler import build_scheduler

            scheduler = build_scheduler(ctx)
            scheduler.start()
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="AI Trend Signal Layer", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=WEB_DIR / "templates")
    templates.env.globals.update(category_labels=CATEGORY_LABELS, tier_labels=TIER_LABELS,
                                 categories=CATEGORIES, audiences=AUDIENCES)
    feedback_limiter = RateLimiter(FEEDBACK_LIMIT_PER_MINUTE)
    admin_limiter = RateLimiter(ADMIN_LIMIT_PER_MINUTE)

    def guard_admin(request: Request, token: str | None) -> None:
        if not admin_limiter.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(status_code=429, detail="too many admin requests")
        _check_admin(ctx, token)

    def page_status() -> dict:
        health = source_health(ctx.settings, ctx.sources)
        return {"last_run": last_run(ctx.settings, "process"),
                "stale": [h["name"] for h in health if h["status"] == "stale"]}

    # ------------------------------------------------------------------ HTML pages

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, category: str | None = None, audience: str | None = None,
             hours: int = Query(72, ge=6, le=24 * 14)):
        category = category if category in CATEGORIES else None
        audience = audience if audience in AUDIENCES else None
        views = feed(ctx.settings, ctx.source_map, category=category, audience=audience, since_hours=hours)
        groups = {tier: [v for v in views if v.tier == tier] for tier in TIER_ORDER}
        context = {"groups": groups, "minor_total": len(groups["minor"]), "category": category,
                   "audience": audience, "hours": hours, **page_status()}
        groups["minor"] = groups["minor"][:MINOR_SHOWN]
        return templates.TemplateResponse(request, "feed.html", context)

    @app.get("/brief/{kind}", response_class=HTMLResponse)
    def brief_page(request: Request, kind: Literal["daily", "weekly"]):
        digest = latest_digest(ctx.settings, kind)
        body = render_brief_html(digest["body_md"]) if digest else None
        trends = trend_counts(ctx.settings) if kind == "weekly" else []
        return templates.TemplateResponse(request, "digest.html",
                                          {"kind": kind, "digest": digest, "body": body, "trends": trends,
                                           **page_status()})

    @app.get("/story/{story_id}", response_class=HTMLResponse)
    def story_page(request: Request, story_id: int):
        view = get_story(ctx.settings, ctx.source_map, story_id)
        if view is None:
            raise HTTPException(status_code=404, detail="story not found")
        reports = story_reports(ctx.settings, ctx.source_map, story_id)
        return templates.TemplateResponse(request, "story.html", {"story": view, "reports": reports, **page_status()})

    @app.get("/sources", response_class=HTMLResponse)
    def sources_page(request: Request):
        return templates.TemplateResponse(request, "sources.html",
                                          {"health": source_health(ctx.settings, ctx.sources), **page_status()})

    # ------------------------------------------------------------------ JSON API

    @app.get("/api/stories")
    def api_stories(tier: str | None = None, category: str | None = None, audience: str | None = None,
                    hours: int = Query(72, ge=1, le=24 * 30), limit: int = Query(50, ge=1, le=200),
                    offset: int = Query(0, ge=0)):
        if tier and tier not in TIER_ORDER:
            return envelope(error=f"tier must be one of {list(TIER_ORDER)}", status=422)
        if category and category not in CATEGORIES:
            return envelope(error="unknown category", status=422)
        views = feed(ctx.settings, ctx.source_map, tier=tier, category=category, audience=audience, since_hours=hours)
        page = views[offset:offset + limit]
        return envelope([v.as_dict() for v in page], meta={"total": len(views), "limit": limit, "offset": offset})

    @app.get("/api/stories/{story_id}")
    def api_story(story_id: int):
        view = get_story(ctx.settings, ctx.source_map, story_id)
        if view is None:
            return envelope(error="story not found", status=404)
        return envelope({**view.as_dict(), "reports": story_reports(ctx.settings, ctx.source_map, story_id)})

    @app.get("/api/digest/{kind}/latest")
    def api_digest(kind: Literal["daily", "weekly"]):
        digest = latest_digest(ctx.settings, kind)
        return envelope(digest) if digest else envelope(error="no brief generated yet", status=404)

    @app.get("/api/trends")
    def api_trends():
        return envelope(trend_counts(ctx.settings))

    @app.get("/api/skills/momentum")
    def api_skill_momentum():
        """For SKidea: weekly story counts per skill = the 'adoption momentum' signal."""
        return envelope(skill_momentum(ctx.settings, ctx.watchlist),
                        meta={"definition": "momentum = (this week - avg of previous 4 weeks) / max(avg, 1)"})

    @app.get("/api/health")
    def api_health():
        return envelope(source_health(ctx.settings, ctx.sources), meta=page_status())

    @app.post("/api/feedback")
    def api_feedback(payload: FeedbackIn, request: Request):
        client = request.client.host if request.client else "unknown"
        if not feedback_limiter.allow(client):
            return envelope(error="too many feedback requests, try again in a minute", status=429)
        if not record_feedback(ctx.settings, payload.story_id, payload.signal):
            return envelope(error="story not found", status=404)
        return envelope({"story_id": payload.story_id, "signal": payload.signal})

    @app.post("/api/admin/run", status_code=202)
    def api_admin_run(request: Request, background: BackgroundTasks, x_admin_token: str | None = Header(default=None)):
        guard_admin(request, x_admin_token)
        background.add_task(run_pipeline_if_idle, ctx)
        return envelope({"started": "pipeline"}, status=202)

    @app.post("/api/admin/digest/{kind}", status_code=202)
    def api_admin_digest(kind: Literal["daily", "weekly"], request: Request, background: BackgroundTasks,
                         x_admin_token: str | None = Header(default=None)):
        guard_admin(request, x_admin_token)
        background.add_task(make_digest, ctx, kind)
        return envelope({"started": f"{kind} digest"}, status=202)

    # ------------------------------------------------------------------ RSS

    @app.get("/rss.xml")
    def rss(request: Request):
        views = [v for v in feed(ctx.settings, ctx.source_map, since_hours=72) if v.tier in ("must_know", "worth_a_look")]
        base = str(request.base_url).rstrip("/")
        items = "".join(
            f"<item><title>{escape(f'[{TIER_LABELS[v.tier]}] {v.title}')}</title>"
            f"<link>{escape(v.url)}</link><guid isPermaLink=\"false\">trendsignal-{v.id}</guid>"
            f"<description>{escape(f'{v.tldr} Why it matters: {v.why_it_matters}')}</description>"
            f"<pubDate>{v.first_seen_at.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
            for v in views[:40]
        )
        body = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
                f"<title>AI Trend Signal: Must-know and Worth a look</title><link>{escape(base)}/</link>"
                f"<description>Ranked AI and tech updates for CS students and developers</description>{items}"
                f"</channel></rss>")
        return Response(body, media_type="application/rss+xml")

    return app
