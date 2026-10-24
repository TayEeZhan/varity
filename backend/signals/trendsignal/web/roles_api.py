"""Varity's CV & routes, Pathway and Today pages: role suggestions, the chosen route and its pathway.

Same envelope, profile token and rate limiting as cv_api. An LLM failure is never an HTTP error: the answer
says rankedBy / personalisedBy "formula" and why in llmStatus.
"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, Header, Query, Request
from pydantic import BaseModel, Field

from advisor import service
from advisor.llm import LlmUnavailable, call_model
from intake import ledger
from trendsignal.jobs import AppContext
from trendsignal.output import latest_run_id
from trendsignal.queries import skill_momentum
from trendsignal.web.app import RateLimiter, envelope
from trendsignal.web.cv_api import client_ip, load_profile, save_profile

ROLES_LIMIT_PER_MINUTE = 30
MIN_HOURS, MAX_HOURS = 1, 40
MODEL_CALLS_PER_MINUTE = 4  # per IP: counted only when a paid model call really starts, never for a cached answer


class TargetRoleIn(BaseModel):
    roleId: str = Field(min_length=1, max_length=60)


def add_role_routes(app: FastAPI, ctx: AppContext) -> None:
    settings = ctx.settings
    limiter = RateLimiter(ROLES_LIMIT_PER_MINUTE)
    model_limiter = RateLimiter(MODEL_CALLS_PER_MINUTE)

    def model_call(request: Request):
        """The model call for this client: the per-IP limit is spent here, after the cache lookup."""
        def call(*args, **kwargs):
            if not model_limiter.allow(client_ip(request)):
                raise LlmUnavailable("RATE_LIMITED")
            return call_model(*args, **kwargs)
        return call

    def signals() -> tuple[list[dict], str | None]:
        rows = [{**row, "terms": ctx.watchlist.skills.get(row["skill"], [])}
                for row in skill_momentum(settings, ctx.watchlist)]
        return rows, latest_run_id(settings)

    def engine_data():
        try:
            return service.load_data(), None
        except (OSError, ValueError):
            return None, envelope(error="role data is missing: run the engine (engine/roles.py)", status=500,
                                  meta={"code": "ROLE_DATA_MISSING"})

    def checks(request: Request, token: str | None):
        """(profile, data, error response)."""
        if not limiter.allow(client_ip(request)):
            return None, None, envelope(error="too many requests, try again in a minute", status=429,
                                        meta={"code": "RATE_LIMITED"})
        profile = load_profile(settings, token)
        if profile is None:
            return None, None, envelope(error="no saved profile: read and save a CV first", status=404,
                                        meta={"code": "PROFILE_NOT_FOUND"})
        data, error = engine_data()
        return profile, data, error

    @app.get("/api/roles/suggestions")
    def api_role_suggestions(request: Request, scenario: Literal["moderate", "fast"] = "moderate",
                             hoursPerWeek: int = Query(default=5, ge=MIN_HOURS, le=MAX_HOURS),
                             x_profile_token: str | None = Header(default=None)):
        """Roles ranked for the saved profile, each with reason chips built from the profile, forecast and signals."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        rows, run_id = signals()
        return envelope(service.suggestions(profile, rows, run_id, settings.db_path, scenario=scenario,
                                            hours_per_week=hoursPerWeek, use_llm=settings.llm_mode != "off",
                                            call=model_call(request), data=data))

    @app.post("/api/profile/target-role")
    def api_target_role(payload: TargetRoleIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Save the route the user picked. Setting the same role again changes nothing."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        if payload.roleId not in service.pathway_role_ids(profile, data):
            return envelope(error="unknown role", status=422, meta={"code": "VALIDATION_ERROR"})
        if profile.target_role != payload.roleId:
            profile = ledger.set_details(profile, name=profile.name, target_role=payload.roleId)
            save_profile(settings, x_profile_token, profile)
        return envelope({"profile": profile.model_dump(mode="json")})

    @app.get("/api/pathway")
    def api_pathway(request: Request, roleId: str | None = Query(default=None, max_length=60),
                    hoursPerWeek: int = Query(default=5, ge=MIN_HOURS, le=MAX_HOURS),
                    scenario: Literal["moderate", "fast"] = "moderate",
                    x_profile_token: str | None = Header(default=None)):
        """The pathway to roleId, or to the saved route. Its dated tasks feed the Today page."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        role_id = roleId or profile.target_role
        if not role_id:
            return envelope(error="pick a route first", status=409, meta={"code": "NO_TARGET_ROLE"})
        rows, run_id = signals()
        try:
            plan = service.pathway(profile, role_id, rows, run_id, settings.db_path, scenario=scenario,
                                   hours_per_week=hoursPerWeek, use_llm=settings.llm_mode != "off",
                                   call=model_call(request), data=data)
        except service.RoleNotFound:
            return envelope(error="no pathway for this role: unknown, or too few job posts to learn it", status=422,
                            meta={"code": "VALIDATION_ERROR"})
        return envelope(plan)
