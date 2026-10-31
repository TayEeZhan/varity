"""Project and Cert stations API (tasks/plan-projects-certs.md). Same envelope, owner key and rate limit as roles_api.

Flow: board a project -> submit a repo -> hard checks (code) -> live jury per criterion (3 models, cited lines)
-> passed: each criterion skill gets jury_pass evidence (Applied, full credit in the match score).
Certs: add to plan -> "I passed" with a Credly link -> badge_verified evidence (Certified) or self-reported.
A failed item whose skill is not on the route yields a re-plan offer: Keep adds the stop, Revert hides it.
Spend guard (no per-user cap, by decision): one review per project at a time, and a repeat review needs new
commits; the per-job budget cap in engine/llm_client.py stops all jury calls when the credit runs low.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, Header, Query, Request
from pydantic import BaseModel, Field

from advisor import planner, service
from advisor.mapping import LEARNED_CREDIT
from intake import ledger
from intake.models import Evidence
from proof import catalog, credly, jury, why
from proof import github as gh_mod
from trendsignal.jobs import AppContext
from trendsignal.web import accounts_store as store
from trendsignal.web.app import RateLimiter, envelope
from trendsignal.web.auth_api import owner_of
from trendsignal.web.cv_api import client_ip, load_profile, save_profile

PROOF_LIMIT_PER_MINUTE = 30
OPEN_STATUSES = ("on_board", "not_yet", "delayed", "hard_fail", "reviewing")
NEEDS_NEW_COMMITS = ("not_yet",)  # a repeat review of the same commit would only repeat the votes


class BoardIn(BaseModel):
    projectId: str = Field(min_length=1, max_length=60)
    roleId: str = Field(min_length=1, max_length=60)


class ProjectIn(BaseModel):
    projectId: str = Field(min_length=1, max_length=60)


class ConsentIn(BaseModel):
    privateJurors: Literal["all", "claude_gpt"] = "all"


class SubmitIn(BaseModel):
    projectId: str = Field(min_length=1, max_length=60)
    repo: str = Field(min_length=3, max_length=200)
    prUrl: str | None = Field(default=None, max_length=200)
    demoUrl: str | None = Field(default=None, max_length=300)


class DisputeIn(BaseModel):
    projectId: str = Field(min_length=1, max_length=60)
    item: int = Field(ge=0, le=20)
    note: str = Field(min_length=3, max_length=500)


class CertIn(BaseModel):
    certId: str = Field(min_length=1, max_length=60)
    roleId: str = Field(min_length=1, max_length=60)


class PassedIn(BaseModel):
    certId: str = Field(min_length=1, max_length=60)
    badgeUrl: str = Field(min_length=10, max_length=300)


class ReplanIn(BaseModel):
    roleId: str = Field(min_length=1, max_length=60)
    skill: str = Field(min_length=1, max_length=60)
    action: Literal["keep", "revert"]


@dataclass(frozen=True)
class ReviewJob:
    """Everything the background jury needs for one review (or one disputed item)."""
    owner: str
    project_id: str
    item: dict
    gh: gh_mod.Github
    repo_info: dict
    skip_deepseek: bool = False
    only: int | None = None
    note: str | None = None
    previous: tuple = ()


# ---- state (one JSON document per owner, moved and deleted with the profile)

def _now() -> str:
    return ledger.now_iso()


def is_account(owner: str | None) -> bool:
    return bool(owner) and owner.startswith("u:")


def load_state(settings, owner: str) -> dict:
    raw = store.get_proof(settings, owner)
    state = json.loads(raw) if raw else {}
    return {"consent": state.get("consent"), "projects": state.get("projects", []), "certs": state.get("certs", [])}


def save_state(settings, owner: str, state: dict) -> None:
    store.put_proof(settings, owner, json.dumps(state, separators=(",", ":")), _now())


def _find(items: list[dict], key: str) -> dict | None:
    return next((x for x in items if x["id"] == key), None)


@lru_cache(maxsize=1)
def juror_names() -> tuple[str, ...]:
    return tuple(j.name for j in jury.default_jurors())


def spawn(target, *args) -> None:
    """Run the jury off the request thread (tests replace this to run it inline)."""
    threading.Thread(target=target, args=args, daemon=True).start()


# ---- evidence and re-plan

def add_proof_evidence(profile, skills: list[str], source: str, method: str, context: str, note: str):
    for skill in skills:
        evidence = Evidence(source=source, method=method, context=context, added_at=_now(), added_by="varity", note=note[:200])
        profile = ledger.add_evidence(profile, service.task_slug(skill), skill, evidence, caller="proof")
    return profile


def replan_offers(role: dict, skills: list[str], plan_state) -> list[str]:
    """Skills a failed item or a cert needs that the route has no stop for: not held, not a gap, not added yet."""
    on_route = {s["skill"] for s in role["have"] + role["gap"]} | set(plan_state.pushed if plan_state else ())
    return [s for s in dict.fromkeys(skills) if s not in on_route]


def _role(profile, data, role_id: str) -> dict | None:
    out = service.match(profile, data, "moderate")
    return next((r for r in out["roles"] + out["low_match"] if r["role_id"] == role_id), None)


# ---- review (the jury runs in a background thread; the page polls GET /api/proof)

def _files_for(gh, repo_info: dict, paths: list[str], hints: list[str], cache: dict, skipped: list) -> dict[str, str]:
    files = {}
    for path in jury.pick_paths(paths, hints):
        if path not in cache:
            try:
                cache[path] = gh_mod.read_file(gh, repo_info["fullName"], path, repo_info["branch"])
            except gh_mod.GithubError as exc:
                cache[path] = None
                skipped.append(f"{path} ({exc.status or 'unreadable'})")
        if cache[path] is not None:
            files[path] = cache[path]
    return files


def run_jury(catalog_item: dict, gh, repo_info: dict, jurors: list, notes: dict | None = None,
             only: int | None = None, previous: list | None = None) -> tuple[list[dict], list[str]]:
    """(items, files that could not be read). Votes every criterion, or only one (a dispute)."""
    paths = gh_mod.list_paths(gh, repo_info["fullName"], repo_info["branch"])
    items, cache, skipped = list(previous or []), {}, []
    for i, crit in enumerate(catalog_item["criteria"]):
        if only is not None and i != only:
            continue
        files = _files_for(gh, repo_info, paths, crit["hints"], cache, skipped)
        row = {"criterion": crit["text"], "skill": crit["skill"],
               **jury.vote_item(crit["text"], files, jurors, (notes or {}).get(i)), "disputed": only is not None}
        if i < len(items):
            items[i] = row
        else:
            items.append(row)
    return items, sorted(set(skipped))


def review_outcome(hard: list[dict], items: list[dict]) -> str:
    if not all(h["ok"] for h in hard):
        return "hard_fail"
    return jury.outcome([i["result"] for i in items])


# ---- routes

def add_proof_routes(app: FastAPI, ctx: AppContext) -> None:
    settings = ctx.settings
    limiter = RateLimiter(PROOF_LIMIT_PER_MINUTE)

    def who(request: Request, token: str | None):
        """(owner, profile, error)."""
        if not limiter.allow(client_ip(request)):
            return None, None, envelope(error="too many requests, try again in a minute", status=429, meta={"code": "RATE_LIMITED"})
        owner = owner_of(request, token)
        profile = load_profile(settings, owner)
        if profile is None:
            return None, None, envelope(error="no saved profile: read and save a CV first", status=404,
                                        meta={"code": "PROFILE_NOT_FOUND"})
        return owner, profile, None

    def running(owner: str, project_id: str) -> bool:
        return store.review_running(settings, owner, project_id, time.time())

    def view(owner: str, profile, role_id: str | None) -> dict:
        state = load_state(settings, owner)
        role = _role(profile, service.load_data(), role_id) if role_id else None
        mine = []
        for p in state["projects"]:
            last = p["reviews"][-1] if p.get("reviews") else None
            is_running = running(owner, p["id"])
            if p["status"] == "reviewing" and not is_running:  # the server stopped mid-review: say so, never hang
                p = {**p, "status": "delayed"}
                if last:
                    last = {**last, "outcome": "delayed", "error": "The review stopped before it finished."}
                    p["reviews"] = p["reviews"][:-1] + [last]
            mine.append({**p, "running": is_running})
        return {
            "roleName": role["name"] if role else None,
            "projects": why.apply(catalog.rank_projects(role, catalog.projects()), role["name"]) if role else [],
            "certs": catalog.rank_certs(role, catalog.certs(), catalog.load("cert_demand.json", required=False)) if role else [],
            "mine": mine, "myCerts": state["certs"], "consent": state["consent"], "openStatuses": list(OPEN_STATUSES),
            "jurors": list(juror_names()), "learnedCredit": LEARNED_CREDIT}

    @app.get("/api/proof")
    def api_proof(request: Request, roleId: str | None = Query(default=None, max_length=60),
                  x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        return error or envelope(view(owner, profile, roleId))

    @app.post("/api/proof/consent")
    def api_consent(request: Request, payload: ConsentIn | None = None, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        payload = payload or ConsentIn()
        state = load_state(settings, owner)
        state["consent"] = {"at": _now(), "privateJurors": payload.privateJurors}
        save_state(settings, owner, state)
        return envelope({"consent": state["consent"]})

    @app.post("/api/proof/board")
    def api_board(payload: BoardIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        item = catalog.project_by_id(payload.projectId)
        if item is None:
            return envelope(error="unknown project", status=404, meta={"code": "NOT_FOUND"})
        state = load_state(settings, owner)
        if any(running(owner, p["id"]) for p in state["projects"]):
            return envelope(error="wait for the running review to finish", status=409, meta={"code": "REVIEW_RUNNING"})
        for p in state["projects"]:  # one project on board at a time: the old one is cancelled, kept visible
            if p["status"] in OPEN_STATUSES and p["id"] != payload.projectId:
                p.update(status="cancelled", cancelledAt=_now(), cancelReason=f"You boarded {item['title']} instead.")
        current = _find(state["projects"], payload.projectId)
        if current is None:
            state["projects"].append({"id": payload.projectId, "roleId": payload.roleId, "status": "on_board",
                                      "boardedAt": _now(), "reviews": [], "replan": []})
        elif current["status"] == "cancelled":
            current.update(status="on_board", cancelledAt=None, cancelReason=None, roleId=payload.roleId)
        save_state(settings, owner, state)
        return envelope(view(owner, profile, payload.roleId))

    @app.post("/api/proof/abandon")
    def api_abandon(payload: ProjectIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        state = load_state(settings, owner)
        p = _find(state["projects"], payload.projectId)
        if p is None or p["status"] not in OPEN_STATUSES or running(owner, p["id"]):
            return envelope(error="no open project to abandon", status=409, meta={"code": "NO_PROJECT"})
        p.update(status="cancelled", cancelledAt=_now(), cancelReason="You abandoned it.")
        save_state(settings, owner, state)
        return envelope(view(owner, profile, p["roleId"]))

    def start_review(owner: str, project_id: str, item: dict, note: dict | None = None, only: int | None = None):
        """Hard checks now; the jury in a background thread. Returns an error response, or None when done or started."""
        if not store.acquire_review(settings, owner, project_id, time.time()):
            return envelope(error="a review of this project is already running", status=409, meta={"code": "REVIEW_RUNNING"})
        started = False
        try:
            state = load_state(settings, owner)
            p = _find(state["projects"], project_id)
            gh = gh_mod.Github(gh_mod.server_token())
            try:
                hard, info = gh_mod.hard_checks(gh, p["repo"], None,
                                                p.get("prUrl") if item.get("needsPr") else None, p.get("demoUrl"))
            except gh_mod.GithubError as exc:
                return envelope(error=f"GitHub could not be read: {exc}", status=502, meta={"code": "GITHUB_ERROR"})
            last = p["reviews"][-1] if p["reviews"] else None
            missed = last and any(v["vote"] == "none" for i in last.get("items", []) for v in i.get("votes", []))
            if (only is None and last and last["outcome"] in NEEDS_NEW_COMMITS and info.get("head")
                    and info["head"] == last.get("head") and not missed):  # a juror that did not answer may vote again
                return envelope(error="push your fixes to GitHub first: this commit was already reviewed", status=409,
                                meta={"code": "NO_NEW_COMMITS"})
            p["unverified"] = True  # no GitHub sign-in: nothing proves the repo is the user's
            hard_ok = all(h["ok"] for h in hard)
            if only is not None:  # a dispute re-votes one item of the last review; hard rules still apply
                review = last
                review.update(hard=hard, outcome="reviewing", head=info.get("head"))
            else:
                review = {"id": f"r{len(p['reviews']) + 1}", "at": _now(), "hard": hard, "items": [],
                          "outcome": "reviewing", "head": info.get("head")}
                p["reviews"].append(review)
            if not hard_ok:  # no LLM call when a hard check fails, for a new review and for a dispute
                review["outcome"] = p["status"] = "hard_fail"
                save_state(settings, owner, state)
                return None
            p["status"] = "reviewing"
            save_state(settings, owner, state)
            consent = state["consent"] or {}
            job = ReviewJob(owner, project_id, item, gh, info,
                            skip_deepseek=info.get("private", False) and consent.get("privateJurors") == "claude_gpt",
                            only=only, note=(note or {}).get(only) if only is not None else None,
                            previous=tuple(last["items"]) if only is not None else ())
            spawn(finish_review, job)
            started = True
            return None
        finally:
            if not started:
                store.release_review(settings, owner, project_id)

    def finish_review(job: ReviewJob):
        try:
            notes = {job.only: job.note} if job.note else None
            try:
                jurors = jury.default_jurors(skip_deepseek=job.skip_deepseek)
                items, skipped = run_jury(job.item, job.gh, job.repo_info, jurors, notes, job.only, list(job.previous))
                failure = None
            except gh_mod.GithubError as exc:
                items, skipped, failure = list(job.previous), [], f"GitHub could not be read: {exc}"
            state = load_state(settings, job.owner)  # reload: the user may have acted meanwhile
            p = _find(state["projects"], job.project_id)
            if p is None or p["status"] == "cancelled":
                return
            review = p["reviews"][-1]
            review.update(items=items, skippedFiles=skipped)
            review["outcome"] = p["status"] = "delayed" if failure else review_outcome(review["hard"], items)
            if failure:
                review["error"] = failure
            profile = load_profile(settings, job.owner)
            if profile is not None and p["status"] == "passed":
                note_text = f"Project {job.item['title']} passed review {review['id']} ({p['repo']})"
                profile = add_proof_evidence(profile, sorted({c["skill"] for c in job.item["criteria"]}),
                                             "github", "jury_pass", "project", note_text)
                save_profile(settings, job.owner, profile)
            if profile is not None and p["status"] == "not_yet":
                role = _role(profile, service.load_data(), p["roleId"])
                failed = [i["skill"] for i in items if i["result"] == "fail"]
                p["replan"] = replan_offers(role, failed, profile.plan) if role else []
            save_state(settings, job.owner, state)
        finally:
            store.release_review(settings, job.owner, job.project_id)

    @app.post("/api/proof/submit")
    def api_submit(payload: SubmitIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        item = catalog.project_by_id(payload.projectId)
        repo = gh_mod.parse_repo(payload.repo)
        if item is None or repo is None:
            return envelope(error="give a GitHub repo as owner/name or its github.com link", status=422,
                            meta={"code": "VALIDATION_ERROR"})
        state = load_state(settings, owner)
        if not state["consent"]:
            return envelope(error="agree to the review terms first", status=409, meta={"code": "NEEDS_CONSENT"})
        p = _find(state["projects"], payload.projectId)
        if p is None or p["status"] not in OPEN_STATUSES or p["status"] == "reviewing":
            return envelope(error="board this project first", status=409, meta={"code": "NO_PROJECT"})
        p.update(repo=repo, prUrl=payload.prUrl, demoUrl=payload.demoUrl)
        save_state(settings, owner, state)
        error = start_review(owner, p["id"], item)
        return error or envelope(view(owner, profile, p["roleId"]))

    @app.post("/api/proof/recheck")
    def api_recheck(payload: ProjectIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        p = _find(load_state(settings, owner)["projects"], payload.projectId)
        item = catalog.project_by_id(payload.projectId)
        if p is None or item is None or not p.get("repo") or p["status"] not in OPEN_STATUSES:
            return envelope(error="nothing to re-check", status=409, meta={"code": "NO_PROJECT"})
        error = start_review(owner, p["id"], item)
        return error or envelope(view(owner, profile, p["roleId"]))

    @app.post("/api/proof/dispute")
    def api_dispute(payload: DisputeIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        p = _find(load_state(settings, owner)["projects"], payload.projectId)
        item = catalog.project_by_id(payload.projectId)
        last = p["reviews"][-1] if p and p.get("reviews") else None
        if item is None or not last or last["outcome"] != "not_yet" or payload.item >= len(last["items"]):
            return envelope(error="only a failed item of the last review can be disputed", status=409, meta={"code": "NO_DISPUTE"})
        row = last["items"][payload.item]
        if row["result"] != "fail" or row.get("disputed"):
            return envelope(error="this item was already re-checked once", status=409, meta={"code": "NO_DISPUTE"})
        error = start_review(owner, p["id"], item, {payload.item: payload.note}, payload.item)
        return error or envelope(view(owner, profile, p["roleId"]))

    @app.post("/api/proof/replan")
    def api_replan(payload: ReplanIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Keep adds the offered skill as a stop on the route (a pushed skill); Revert hides it for 30 days."""
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        state = load_state(settings, owner)
        offered = {s for x in state["projects"] + state["certs"] for s in x.get("replan", [])}
        if payload.skill not in offered or profile.plan is None or profile.plan.role_id != payload.roleId:
            return envelope(error="that stop is not on offer", status=409, meta={"code": "NO_OFFER"})
        today = service.today_myt().isoformat()
        plan_state = planner.answer_offer(profile.plan, payload.skill, payload.action == "keep", today, _now())
        profile = profile.model_copy(update={"plan": plan_state})
        save_profile(settings, owner, profile)
        for x in state["projects"] + state["certs"]:
            x["replan"] = [s for s in x.get("replan", []) if s != payload.skill]
        save_state(settings, owner, state)
        return envelope(view(owner, profile, payload.roleId))

    @app.post("/api/proof/certs/plan")
    def api_cert_plan(payload: CertIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        cert = catalog.cert_by_id(payload.certId)
        role = _role(profile, service.load_data(), payload.roleId)
        if cert is None or role is None:
            return envelope(error="unknown cert or role", status=404, meta={"code": "NOT_FOUND"})
        state = load_state(settings, owner)
        if _find(state["certs"], cert["id"]) is None:
            _, credit = catalog.role_weights(role)
            missing = [s for s in cert["syllabus"] if credit.get(s, 0.0) == 0.0]
            state["certs"].append({"id": cert["id"], "roleId": payload.roleId, "status": "planned", "at": _now(),
                                   "replan": replan_offers(role, missing, profile.plan)})
            save_state(settings, owner, state)
        return envelope(view(owner, profile, payload.roleId))

    @app.post("/api/proof/certs/passed")
    def api_cert_passed(payload: PassedIn, request: Request, x_profile_token: str | None = Header(default=None)):
        owner, profile, error = who(request, x_profile_token)
        if error:
            return error
        cert = catalog.cert_by_id(payload.certId)
        state = load_state(settings, owner)
        mine = _find(state["certs"], payload.certId)
        if cert is None or mine is None:
            return envelope(error="add this cert to your plan first", status=409, meta={"code": "NO_CERT"})
        user = store.get_user(settings, owner[2:]) if is_account(owner) else None
        result = credly.verify(payload.badgeUrl, cert, date.today(), earner=(user or {}).get("name"))
        mine.update(status=result["status"], detail=result["detail"], badgeUrl=payload.badgeUrl, at=_now(), replan=[])
        if result["status"] == "certified":
            profile = add_proof_evidence(profile, cert["syllabus"], "credly", "badge_verified", "certification",
                                         f"{cert['name']}: {payload.badgeUrl}")
            save_profile(settings, owner, profile)
        save_state(settings, owner, state)
        return envelope(view(owner, profile, mine["roleId"]))
