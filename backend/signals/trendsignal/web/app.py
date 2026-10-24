"""FastAPI app: Varity's JSON API (success/data/error/meta envelope) and its static frontend."""

from __future__ import annotations

import hmac
import json
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from http import HTTPStatus
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from intake.readers import MESSAGES

from trendsignal.jobs import AppContext, load_context, run_pipeline_if_idle
from trendsignal.output import latest_run_id, ranking_rows
from trendsignal.queries import last_run, skill_momentum, source_health
from trendsignal.timeutil import parse_iso

BODY_PARTS = {"body", "query", "path", "header", "cookie"}  # leading entries of a pydantic error "loc"
TIER_LABELS = {"must_know": "Must-know", "worth_a_look": "Worth a look", "emerging": "Emerging", "minor": "Minor"}
ADMIN_LIMIT_PER_MINUTE = 10
SIGNALS_TOP = 10
# Labels the Varity Signals page shows; its filter buttons (frontend/screens-explore.js) match on them.
UI_CATEGORIES = {
    "model_release": "Model release", "research": "Research", "product_feature": "Product feature",
    "dev_tool_release": "Tool release", "api_pricing_change": "API / pricing change",
    "security_incident": "Security incident", "policy_regulation": "Policy / regulation",
    "funding_business": "Business", "benchmark": "Benchmark", "opinion": "Opinion",
}
RANKED_BY_LABELS = {"formula": "deterministic formula", "jev": "Jev",
                    "mixed": "Jev, with the formula where Jev had no answer"}


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


def _check_admin(ctx: AppContext, token: str | None) -> None:
    expected = ctx.settings.admin_token
    if not expected:
        raise HTTPException(status_code=404, detail="Not found.")  # generic: don't reveal the admin routes exist
    if not token or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Not allowed.")


def _local(iso: str, tz: ZoneInfo) -> datetime:
    return parse_iso(iso).astimezone(tz)


def signals_payload(ctx: AppContext) -> dict:
    """Data for Varity's Signals page, in the same shape as frontend/data.js (SIGNAL_RUN, STORIES, SKILLS)."""
    tz = ZoneInfo(ctx.settings.timezone)
    run_id = latest_run_id(ctx.settings)
    rows = ranking_rows(ctx.settings, ctx.source_map, run_id)
    finished = last_run(ctx.settings, "process")
    run = None
    if rows:
        rankers = {row["ranked_by"] for row in rows}
        ranked_by = rankers.pop() if len(rankers) == 1 else "mixed"
        at = _local(finished, tz) if finished else None
        run = {"runId": run_id, "storyCount": len(rows), "rankedBy": RANKED_BY_LABELS[ranked_by],
               "generatedAt": f"{at:%d %b %Y, %H:%M}" if at else None,
               "generatedIso": at.isoformat(timespec="minutes") if at else None}
    stories = []
    for row in rows[:SIGNALS_TOP]:
        seen = _local(row["first_seen_at"], tz)
        stories.append({"rank": row["rank"], "score": row["final_score"], "tier": TIER_LABELS[row["tier"]],
                        "category": UI_CATEGORIES.get(row["category"], row["category"]),
                        "date": f"{seen.day} {seen:%b}", "title": row["title"], "url": row["url"],
                        "sources": row["sources"], "why": row["top_features"]})
    skills = [{"skill": s["skill"], "weekly": s["weekly_counts"][::-1], "avgBefore": s["weekly_average_before"],
               "momentum": s["momentum"]} for s in skill_momentum(ctx.settings, ctx.watchlist)]
    return {"run": run, "stories": stories, "skills": skills}


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

    app = FastAPI(title="Varity", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if not request.url.path.startswith("/api/"):
            return await request_validation_exception_handler(request, exc)
        err = exc.errors()[0]
        field = next((str(p) for p in reversed(err["loc"]) if isinstance(p, str) and p not in BODY_PARTS), None)
        if err["type"] == "string_too_long" and field == "file_b64":
            return envelope(error=MESSAGES["TOO_LARGE"], status=422, meta={"code": "TOO_LARGE"})
        if err["type"] == "missing":
            message = f"Missing field: {field}" if field else "Missing request body."
        else:
            message = f"Invalid value for {field}" if field else "Invalid request."
        return envelope(error=message, status=422, meta={"code": "INVALID_REQUEST"})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if not request.url.path.startswith("/api/"):
            return await http_exception_handler(request, exc)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if message == HTTPStatus(exc.status_code).phrase:  # Starlette's default text, e.g. "Method Not Allowed"
            message = message.capitalize() + "."
        return envelope(error=message, status=exc.status_code, meta={"code": HTTPStatus(exc.status_code).name})

    admin_limiter = RateLimiter(ADMIN_LIMIT_PER_MINUTE)

    def guard_admin(request: Request, token: str | None) -> None:
        if not admin_limiter.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(status_code=429, detail="too many admin requests")
        _check_admin(ctx, token)

    def page_status() -> dict:
        health = source_health(ctx.settings, ctx.sources)
        return {"last_run": last_run(ctx.settings, "process"),
                "stale": [h["name"] for h in health if h["status"] == "stale"]}

    # ------------------------------------------------------------------ JSON API

    @app.get("/api/signals")
    def api_signals():
        """Varity's Signals page: run summary, top 10 stories and skill momentum (weekly: oldest -> this week)."""
        return envelope(signals_payload(ctx))

    @app.get("/api/roles/forecast")
    def api_role_forecast():
        """Varity's Job forecast page: data/role_forecast.json as the engine wrote it (read only, never recomputed)."""
        path = ctx.settings.role_forecast_path
        if not path or not path.is_file():
            return envelope(error="no role forecast yet: run engine/role_forecast.py", status=404)
        try:
            return envelope(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return envelope(error="role forecast file could not be read", status=500)

    @app.get("/api/health")
    def api_health():
        return envelope(source_health(ctx.settings, ctx.sources), meta=page_status())

    @app.post("/api/admin/run", status_code=202)
    def api_admin_run(request: Request, background: BackgroundTasks, x_admin_token: str | None = Header(default=None)):
        guard_admin(request, x_admin_token)
        background.add_task(run_pipeline_if_idle, ctx)
        return envelope({"started": "pipeline"}, status=202)

    from trendsignal.web.cv_api import add_cv_routes  # imported here: cv_api uses envelope and RateLimiter from this module
    add_cv_routes(app, ctx.settings)
    from trendsignal.web.auth_api import add_auth_routes  # same reason as cv_api
    add_auth_routes(app, ctx.settings)
    from trendsignal.web.roles_api import add_role_routes  # same reason as cv_api
    add_role_routes(app, ctx)
    from trendsignal.web.evidence_api import add_evidence_routes  # same reason as cv_api
    add_evidence_routes(app, ctx.settings)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_unknown(request: Request, path: str):
        # Only reached when no real route matched fully; without this the "/" static mount would turn a 405 into a 404.
        if any(r.matches(request.scope)[0] == Match.PARTIAL for r in app.routes if r.path != "/api/{path:path}"):
            raise HTTPException(status_code=405)
        raise HTTPException(status_code=404)

    # Mounted last so every route above wins over the static files.
    frontend = ctx.settings.frontend_dir
    if frontend and (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return app
