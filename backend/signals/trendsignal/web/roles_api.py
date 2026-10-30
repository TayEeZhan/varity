"""Varity's CV & routes, Pathway and Today pages: role suggestions, the chosen route and its pathway.

Same envelope, profile token and rate limiting as cv_api. An LLM failure is never an HTTP error: the answer
says rankedBy / personalisedBy "formula" and why in llmStatus.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Query, Request
from pydantic import BaseModel, Field

from advisor import cv_agent, cv_writer, planner, service
from advisor.cv_writer import CvDraft
from advisor.llm import LlmUnavailable, call_model
from intake import ledger
from intake.models import Evidence
from trendsignal.jobs import AppContext
from trendsignal.output import latest_run_id
from trendsignal.queries import skill_momentum
from trendsignal.web import accounts_store
from trendsignal.web.app import RateLimiter, envelope
from trendsignal.web.auth_api import owner_of
from trendsignal.web.cv_api import client_ip, example_profile, load_profile, profile_out, save_profile

ROLES_LIMIT_PER_MINUTE = 30
MIN_HOURS, MAX_HOURS = 1, 40
MODEL_CALLS_PER_MINUTE = 4  # per IP: counted only when a paid model call really starts, never for a cached answer


class TargetRoleIn(BaseModel):
    roleId: str = Field(min_length=1, max_length=60)


class DecisionIn(BaseModel):
    roleId: str = Field(min_length=1, max_length=60)
    action: Literal["keep", "revert", "add", "later"]
    skill: str | None = Field(default=None, max_length=60)  # for add / later
    scenario: Literal["moderate", "fast"] = "moderate"
    hoursPerWeek: int = Field(default=5, ge=MIN_HOURS, le=MAX_HOURS)


class TeamPerson(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    skills: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(max_length=40)


class TeamIn(BaseModel):
    profiles: list[TeamPerson] = Field(min_length=2, max_length=50)
    roleId: str = Field(min_length=1, max_length=60)
    scenario: Literal["moderate", "fast"] = "moderate"


class LearnedIn(BaseModel):
    skill: str = Field(min_length=1, max_length=60)  # a taxonomy skill name, as the pathway shows it


MAX_FACTS = 40


class GenerateIn(BaseModel):
    roleId: str | None = Field(default=None, max_length=60)  # None: the saved target role
    jobAd: str = Field(default="", max_length=8000)


class DraftIn(BaseModel):
    draft: CvDraft
    facts: list[Annotated[str, Field(max_length=2000)]] = Field(default_factory=list, max_length=200)
    addedByYou: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=100)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class AgentIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=40)
    selection: str = Field(default="", max_length=40)
    justDoIt: bool = False


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
        profile = load_profile(settings, owner_of(request, token))
        if profile is None:
            return None, None, envelope(error="no saved profile: read and save a CV first", status=404,
                                        meta={"code": "PROFILE_NOT_FOUND"})
        data, error = engine_data()
        return profile, data, error

    @app.get("/api/roles/suggestions")
    def api_role_suggestions(request: Request, scenario: Literal["moderate", "fast"] = "moderate",
                             hoursPerWeek: int = Query(default=5, ge=MIN_HOURS, le=MAX_HOURS),
                             goal: str | None = Query(default=None, max_length=40),
                             x_profile_token: str | None = Header(default=None)):
        """Roles ranked for the saved profile, each with reason chips built from the profile, forecast and signals."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        if bad_goal(goal, data):
            return envelope(error="unknown goal sector", status=422, meta={"code": "VALIDATION_ERROR"})
        rows, run_id = signals()
        return envelope(service.suggestions(profile, rows, run_id, settings.db_path, scenario=scenario,
                                            hours_per_week=hoursPerWeek, use_llm=settings.llm_mode != "off",
                                            call=model_call(request), data=data, goal=goal),
                        meta=service.data_meta())

    @app.post("/api/team")
    def api_team(payload: TeamIn, request: Request):
        """G2: match each synthetic profile to one role; count who misses each skill. Nothing is stored."""
        if not limiter.allow(client_ip(request)):
            return envelope(error="too many requests, try again in a minute", status=429, meta={"code": "RATE_LIMITED"})
        data, error = engine_data()
        if error:
            return error
        rows, unmapped, role, gaps = [], {}, None, {}
        for person in payload.profiles:
            profile = example_profile({"name": person.label, "skills": person.skills})
            out, _, miss = service._match(profile, data, payload.scenario)
            role = next((r for r in out["roles"] + out["low_match"] if r["role_id"] == payload.roleId), None)
            if role is None:
                return envelope(error="unknown role", status=422, meta={"code": "VALIDATION_ERROR"})
            rows.append({"label": person.label, "matchPct": round(role["match_score"] * 100),
                         "have": [s["skill"] for s in role["have"]], "gap": [s["skill"] for s in role["gap"]]})
            unmapped[person.label] = miss
            for s in role["gap"]:
                g = gaps.setdefault(s["skill"], {"skill": s["skill"], "missing": 0, "trendLabel": s["trend_label"], "weight": s["weight"]})
                g["missing"] += 1
        skills = sorted(role["have"] + role["gap"], key=lambda s: (-s["weight"], s["skill"]))
        team_gaps = sorted(gaps.values(), key=lambda g: (-g["missing"], -g["weight"], g["skill"]))
        return envelope({"role": role["name"], "skills": [s["skill"] for s in skills], "rows": rows,
                         "teamGaps": team_gaps, "unmapped": unmapped}, meta=service.data_meta())

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
            save_profile(settings, owner_of(request, x_profile_token), profile)
        return envelope(profile_out(profile, owner_of(request, x_profile_token)))

    @app.get("/api/pathway")
    def api_pathway(request: Request, roleId: str | None = Query(default=None, max_length=60),
                    hoursPerWeek: int = Query(default=5, ge=MIN_HOURS, le=MAX_HOURS),
                    scenario: Literal["moderate", "fast"] = "moderate",
                    goal: str | None = Query(default=None, max_length=40),
                    x_profile_token: str | None = Header(default=None)):
        """The pathway to roleId, or to the saved route. Its dated tasks feed the Today page."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        if bad_goal(goal, data):
            return envelope(error="unknown goal sector", status=422, meta={"code": "VALIDATION_ERROR"})
        role_id = roleId or profile.target_role
        if not role_id:
            return envelope(error="pick a route first", status=409, meta={"code": "NO_TARGET_ROLE"})
        plan, error = build_plan(request, x_profile_token, profile, data, role_id, scenario, hoursPerWeek, goal)
        return error or envelope(plan, meta=service.data_meta())

    def bad_goal(goal: str | None, data) -> bool:
        return goal is not None and goal not in {x["id"] for x in (data.get("role_sdg") or {}).get("sectors", [])}

    def build_plan(request: Request, token: str | None, profile, data, role_id: str, scenario: str, hours: int,
                   goal: str | None = None):
        """(pathway, error). Saves the plan state when the service says it changed without needing a question."""
        rows, run_id = signals()
        try:
            plan = service.pathway(profile, role_id, rows, run_id, settings.db_path, scenario=scenario,
                                   hours_per_week=hours, use_llm=settings.llm_mode != "off",
                                   call=model_call(request), data=data, goal=goal)
        except service.RoleNotFound:
            return None, envelope(error="no pathway for this role: unknown, or too few job posts to learn it", status=422,
                                  meta={"code": "VALIDATION_ERROR"})
        state = plan.pop("planState")
        if state is not None:
            save_profile(settings, owner_of(request, token), profile.model_copy(update={"plan": state}))
        return plan, None

    @app.post("/api/pathway/decision")
    def api_pathway_decision(payload: DecisionIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Keep / Revert a changed plan, or Add / Not now a trend skill. Returns the pathway after the decision."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        plan, error = build_plan(request, x_profile_token, profile, data, payload.roleId, payload.scenario, payload.hoursPerWeek)
        if error:
            return error
        profile = load_profile(settings, owner_of(request, x_profile_token))  # build_plan may have saved a new state
        state, today, now = profile.plan, service.pathway_mod.today_myt().isoformat(), ledger.now_iso()
        if payload.action in ("keep", "revert"):
            if not plan["change"] or state is None:
                return envelope(error="nothing changed in this plan", status=409, meta={"code": "NO_CHANGE"})
            state = (planner.accept(state, payload.roleId, [s["skill"] for s in plan["steps"]], today, now)
                     if payload.action == "keep" else planner.revert(state, plan["change"], today, now))
        else:
            if not plan["offer"] or plan["offer"]["skill"] != payload.skill or state is None:
                return envelope(error="that skill is not on offer", status=409, meta={"code": "NO_OFFER"})
            state = planner.answer_offer(state, payload.skill, payload.action == "add", today, now)
        profile = profile.model_copy(update={"plan": state})
        save_profile(settings, owner_of(request, x_profile_token), profile)
        plan, error = build_plan(request, x_profile_token, profile, data, payload.roleId, payload.scenario, payload.hoursPerWeek)
        return error or envelope(plan)

    @app.post("/api/profile/learned")
    def api_profile_learned(payload: LearnedIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """The user finished a skill's pathway tasks: add it to the profile (source pathway, self-reported)."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        if payload.skill not in {t["skill"] for t in data["taxonomy"]}:
            return envelope(error="unknown skill", status=422, meta={"code": "VALIDATION_ERROR"})
        evidence = Evidence(source="pathway", method="task_done", context="user", added_at=ledger.now_iso(),
                            added_by="user", note=f"Finished every pathway task for {payload.skill}")
        try:
            profile = ledger.add_evidence(profile, service.pathway_mod.task_slug(payload.skill), payload.skill,
                                          evidence, caller="pathway")
        except ledger.LedgerError as exc:
            return envelope(error=str(exc), status=422)
        save_profile(settings, owner_of(request, x_profile_token), profile)
        return envelope(profile_out(profile, owner_of(request, x_profile_token)))

    def saved_draft(owner: str | None) -> dict | None:
        raw = accounts_store.get_cv_draft(settings, owner) if owner else None
        return json.loads(raw) if raw else None

    def draft_out(saved: dict, profile) -> dict:
        draft = CvDraft.model_validate(saved["draft"])
        return {**saved, "markdown": cv_writer.render(draft, saved["role"], cv_writer.learned(profile))}

    def notes_of(owner: str | None) -> list[str]:
        raw = accounts_store.get_cv_notes(settings, owner) if owner else None
        return json.loads(raw) if raw else []

    @app.post("/api/cv/generate")
    def api_cv_generate(request: Request, payload: GenerateIn | None = None,
                        x_profile_token: str | None = Header(default=None)):
        """A new CV for roleId (default: the saved target role), from the saved CV text and every current skill.

        Choosing another role here changes only this CV, never the pathway. A structured draft is saved for the
        CV builder; the .md is in the answer either way.
        """
        payload = payload or GenerateIn()
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        role_id = payload.roleId or profile.target_role
        if not role_id:
            return envelope(error="pick a role for this CV", status=422, meta={"code": "NO_TARGET_ROLE"})
        if role_id not in service.pathway_role_ids(profile, data):
            return envelope(error="no pathway for this role: unknown, or too few job posts to learn it", status=422,
                            meta={"code": "VALIDATION_ERROR"})
        owner = owner_of(request, x_profile_token)
        cv_text = accounts_store.get_cv_text(settings, owner)
        momentum, _ = signals()
        try:
            out = cv_writer.generate(profile, role_id, cv_text, data, model_call(request), job_ad=payload.jobAd,
                                     momentum=momentum)
        except service.RoleNotFound:
            return envelope(error="no pathway for this role: unknown, or too few job posts to learn it", status=422,
                            meta={"code": "VALIDATION_ERROR"})
        if out["draft"] and owner:
            saved = {"roleId": role_id, "role": out["role"], "jobAd": payload.jobAd, "draft": out["draft"],
                     "facts": [], "addedByYou": []}
            accounts_store.put_cv_draft(settings, owner, json.dumps(saved), ledger.now_iso())
        return envelope(out)

    @app.get("/api/cv/draft")
    def api_cv_draft(request: Request, x_profile_token: str | None = Header(default=None)):
        """The saved CV builder draft and the user's CV notes."""
        profile, _, error = checks(request, x_profile_token)
        if error:
            return error
        owner = owner_of(request, x_profile_token)
        saved = saved_draft(owner)
        if saved is None:
            return envelope(error="no CV draft yet: generate one", status=404, meta={"code": "NO_DRAFT"})
        return envelope({**draft_out(saved, profile), "notes": notes_of(owner)})

    @app.put("/api/cv/draft")
    def api_cv_draft_put(payload: DraftIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Save the draft after a direct edit or an accepted agent edit. The user's own words need no checker."""
        profile, _, error = checks(request, x_profile_token)
        if error:
            return error
        owner = owner_of(request, x_profile_token)
        saved = saved_draft(owner)
        if saved is None:
            return envelope(error="no CV draft yet: generate one", status=404, meta={"code": "NO_DRAFT"})
        saved = {**saved, "draft": payload.draft.model_dump(), "facts": payload.facts[-MAX_FACTS:],
                 "addedByYou": payload.addedByYou}
        accounts_store.put_cv_draft(settings, owner, json.dumps(saved), ledger.now_iso())
        return envelope(draft_out(saved, profile))

    @app.post("/api/cv/agent")
    def api_cv_agent(payload: AgentIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """One message to the CV agent → ask / plan / edit / say. An edit is only a proposal until the user accepts."""
        profile, data, error = checks(request, x_profile_token)
        if error:
            return error
        owner = owner_of(request, x_profile_token)
        saved, cv_text = saved_draft(owner), accounts_store.get_cv_text(settings, owner)
        if saved is None or not cv_text:
            return envelope(error="generate the CV first", status=409, meta={"code": "NO_DRAFT"})
        momentum, _ = signals()
        try:
            role_row = cv_writer._role(profile, saved["roleId"], data)
            _, skills = cv_writer.role_skills(profile, saved["roleId"], data,
                                              [r["skill"] for r in momentum if r["momentum"] > 0])
        except service.RoleNotFound:
            return envelope(error="this CV's role has no pathway any more: generate it again", status=409,
                            meta={"code": "NO_DRAFT"})
        said = [h.text for h in payload.history if h.role == "user"] + [payload.message]
        ctx = cv_agent.Context(
            role=saved["role"], role_row=role_row, skills=skills, learned=cv_writer.learned(profile), cv_text=cv_text,
            draft=saved["draft"], job_ad=saved.get("jobAd", ""), notes=notes_of(owner),
            trends=cv_writer.trend_rows(momentum, skills, [s["skill"] for s in role_row["have"] + role_row["gap"]]),
            facts=[*saved.get("facts", []), *said], selection=payload.selection,
            save_note=lambda notes: accounts_store.put_cv_notes(settings, owner, json.dumps(notes), ledger.now_iso()))
        if not model_limiter.allow(client_ip(request)):
            return envelope({"type": "off", "code": "RATE_LIMITED"})
        try:
            out = cv_agent.run(ctx, [h.model_dump() for h in payload.history], payload.message,
                               just_do_it=payload.justDoIt)
        except LlmUnavailable as exc:
            return envelope({"type": "off", "code": exc.code})
        return envelope({**out, "facts": said if out["type"] == "edit" and out.get("addedByYou") else []})
