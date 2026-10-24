"""Varity's CV page: read a CV with the intake (intake/), let the user confirm each skill, keep the profile.

Anonymous use: the browser holds a random profile token and sends it as X-Profile-Token. Only the
token's SHA-256 is stored, so a copied database does not give access to anyone's profile. A signed-in
account (auth_api.py) needs no token. The raw CV is never stored; only the skills, their quotes and the rules behind them.
"""

from __future__ import annotations

import base64
import binascii
import os
import secrets
import threading
import time
import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Header, Request
from pydantic import BaseModel, Field

from intake import ledger
from intake.keyword_pass import build_patterns
from intake.llm_extract import MODEL_LABEL, LlmUnavailable, extract_mentions, load_cached_run
from intake.models import MAX_YEARS, SKILL_ID_PATTERN, Evidence, Profile, Progress
from intake.pipeline import run_intake
from intake.readers import MAX_BYTES, MAX_CHARS, ReadError, read_upload
from intake.reconcile import Review, apply_review
from intake.skills import load_graph, slugify
from trendsignal.config import Settings
from trendsignal.web import accounts_store as store
from trendsignal.web.app import RateLimiter, envelope
from trendsignal.web.auth_api import owner_of

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "intake" / "samples"
SAMPLES = {"aina": "aina.txt", "daniel": "daniel.txt", "priya": "priya.txt"}
CACHED_RUNS = {"aina": "aina-extraction.json"}
EXAMPLES_FILE = Path(__file__).resolve().parents[4] / "data" / "example_profiles.json"
EXAMPLE_NOTE = "Synthetic example: no CV was read"
REVIEW_TTL_S = 30 * 60
MAX_REVIEWS = 200
CV_LIMIT_PER_MINUTE = 6
PROFILE_LIMIT_PER_MINUTE = 30


class CvIn(BaseModel):
    """Exactly one of text, file or sample."""

    text: str | None = Field(default=None, max_length=MAX_CHARS * 2)
    file_name: str | None = Field(default=None, max_length=200)
    file_b64: str | None = Field(default=None, max_length=MAX_BYTES * 4 // 3 + 8)
    sample: Literal["aina", "daniel", "priya"] | None = None
    use_ai: bool = True


class ApplyIn(BaseModel):
    review_id: str = Field(max_length=64)
    kept_ids: list[str] = Field(max_length=300)
    edited_years: dict[str, Annotated[float, Field(ge=0, le=MAX_YEARS)]] = Field(default_factory=dict, max_length=300)
    name: str | None = Field(default=None, max_length=80)
    target_role: str | None = Field(default=None, max_length=80)


class ExampleIn(BaseModel):
    id: str = Field(pattern=SKILL_ID_PATTERN)


def load_examples() -> list[dict]:
    try:
        return json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))["profiles"]
    except (OSError, ValueError, KeyError):
        return []


def example_profile(example: dict) -> Profile:
    """A profile of taxonomy skills at the evidence level 'synthetic example': no quotes, nothing from a CV."""
    profile = ledger.new_profile(name=example["name"])
    stamp = ledger.now_iso()
    for name in example["skills"]:
        evidence = Evidence(source="form", method="user_entry", context="user", note=EXAMPLE_NOTE,
                            added_at=stamp, added_by="user")
        profile = ledger.add_evidence(profile, slugify(name), name, evidence, caller="user", now=stamp)
    return profile


class ProgressIn(BaseModel):
    signature: str = Field(max_length=128)
    doneIds: list[Annotated[str, Field(max_length=64)]] = Field(max_length=500)


class RemoveIn(BaseModel):
    skill_id: str = Field(pattern=SKILL_ID_PATTERN)


class ReviewStore:
    """Reviews waiting for Save. In memory, so the browser cannot send back forged rows.

    shortcut: one process only and lost on restart (the user reads the CV again); move to SQLite if Replit runs more than one instance.
    """

    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Review]] = {}
        self._lock = threading.Lock()

    def put(self, review: Review) -> str:
        review_id = secrets.token_urlsafe(16)
        now = time.monotonic()
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if v[0] > now}
            while len(self._items) >= MAX_REVIEWS:
                self._items.pop(next(iter(self._items)))
            self._items[review_id] = (now + REVIEW_TTL_S, review)
        return review_id

    def pop(self, review_id: str) -> Review | None:
        with self._lock:
            item = self._items.pop(review_id, None)
        return item[1] if item and item[0] > time.monotonic() else None


def load_profile(settings: Settings, owner: str | None) -> Profile | None:
    """owner is an owner_key ("t:..." or "u:..."), from auth_api.owner_of or accounts_store.token_owner."""
    raw = store.get_profile_json(settings, owner) if owner else None
    return Profile.model_validate_json(raw) if raw else None


def save_profile(settings: Settings, owner: str, profile: Profile) -> None:
    store.put_profile_json(settings, owner, profile.model_dump_json(), profile.updated_at)


def delete_profile(settings: Settings, owner: str | None) -> bool:
    return bool(owner) and store.delete_profile_row(settings, owner)


def _read_cv(payload: CvIn) -> str:
    given = [payload.text is not None, payload.file_b64 is not None, payload.sample is not None]
    if sum(given) != 1:
        raise ReadError("EMPTY")
    if payload.sample:
        return (SAMPLES_DIR / SAMPLES[payload.sample]).read_text(encoding="utf-8")
    if payload.file_b64 is not None:
        try:
            data = base64.b64decode(payload.file_b64, validate=True)
        except (binascii.Error, ValueError):
            raise ReadError("UNREADABLE") from None
        return read_upload(payload.file_name or "", data)
    return payload.text or ""


def _choose_extractor(payload: CvIn, settings: Settings):
    """Live model when a key exists; the cached run for the Aina sample; otherwise keyword pass only."""
    if not payload.use_ai:
        return None, "llm", "SWITCHED_OFF"
    if settings.llm_mode != "off" and os.environ.get("ANTHROPIC_API_KEY"):
        return (lambda text, codes: extract_mentions(text, retry_codes=codes)), "llm", ""
    if payload.sample in CACHED_RUNS:
        path = SAMPLES_DIR / CACHED_RUNS[payload.sample]

        def cached(text: str, _codes: tuple[str, ...]):
            extraction = load_cached_run(path, text)
            if extraction is None:
                raise LlmUnavailable("NO_KEY")
            return extraction

        return cached, "cached", ""
    return None, "llm", "NO_KEY"


def _has_pathway(profile: Profile, role_id: str) -> bool:
    from advisor import service  # here: advisor needs trendsignal.web at import time

    try:
        return role_id in service.pathway_role_ids(profile, service.load_data())
    except (OSError, ValueError):
        return False


def profile_out(profile: Profile, owner: str | None, token: str | None = None) -> dict:
    account = bool(owner and owner.startswith("u:"))
    dump = profile.model_dump(mode="json")
    data = {"profile": {**dump, "account": account}, "account": account, "progress": dump["progress"]}
    if token:
        data["token"] = token
    return data


def save_target(owner: str | None, header_token: str | None, has_profile: bool) -> tuple[str, str | None]:
    """(owner key to save under, new token to hand back). Accounts need no token; a browser keeps its own or gets one."""
    if owner and owner.startswith("u:"):
        return owner, None
    token = header_token if has_profile else secrets.token_urlsafe(32)
    return store.token_owner(token), token


def client_ip(request: Request) -> str:
    # Behind Replit's proxy request.client is the proxy; the proxy appends the real address last.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def add_cv_routes(app: FastAPI, settings: Settings) -> None:
    graph = load_graph()
    patterns = build_patterns(graph)
    reviews = ReviewStore()
    cv_limiter = RateLimiter(CV_LIMIT_PER_MINUTE)
    profile_limiter = RateLimiter(PROFILE_LIMIT_PER_MINUTE)

    client = client_ip

    @app.post("/api/cv/extract")
    def api_cv_extract(payload: CvIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Read a CV and return review rows. Nothing is saved until /api/profile/apply."""
        if not cv_limiter.allow(client(request)):
            return envelope(error="too many CVs read from here, try again in a minute", status=429)
        existing = load_profile(settings, owner_of(request, x_profile_token))
        removed = frozenset(item.skill_id for item in existing.removed) if existing else frozenset()
        extractor, label, off_reason = _choose_extractor(payload, settings)
        try:
            result = run_intake(_read_cv(payload), graph=graph, patterns=patterns, extractor=extractor,
                                llm_label=label, off_reason=off_reason, removed_ids=removed)
        except ReadError as exc:
            return envelope(error=exc.message, status=422, meta={"code": exc.code})
        return envelope({
            "review_id": reviews.put(result.review),
            "llm_status": result.llm_status,
            "model": MODEL_LABEL,
            "injection_hint": result.injection_hint,
            "redactions": result.redactions,
            "rows": [asdict(row) for row in result.review.rows],
            "interests": [asdict(item) for item in result.review.interests],
            "dropped": [asdict(item) for item in result.dropped],
        })

    @app.post("/api/profile/apply")
    def api_profile_apply(payload: ApplyIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Save the rows the user kept. Returns the profile and the token to keep for next time."""
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        review = reviews.pop(payload.review_id)
        if review is None:
            return envelope(error="this review has expired, read the CV again", status=410)
        profile = load_profile(settings, owner_of(request, x_profile_token))
        owner, token = save_target(owner_of(request, x_profile_token), x_profile_token, profile is not None)
        profile = profile or ledger.new_profile()
        try:
            profile = apply_review(profile, review, payload.kept_ids, edited_years=payload.edited_years)
            if payload.name is not None or payload.target_role is not None:
                profile = ledger.set_details(profile, name=payload.name if payload.name is not None else profile.name,
                                             target_role=payload.target_role if payload.target_role is not None
                                             else profile.target_role)
        except ledger.LedgerError as exc:
            return envelope(error=str(exc), status=422)
        if payload.target_role and not _has_pathway(profile, payload.target_role):
            return envelope(error="unknown route: pick a role from the suggestions", status=422,
                            meta={"code": "VALIDATION_ERROR"})
        save_profile(settings, owner, profile)
        return envelope(profile_out(profile, owner, token))

    @app.get("/api/profile/examples")
    def api_profile_examples():
        """The synthetic example profiles (data/example_profiles.json), for the Try an example buttons."""
        return envelope({"examples": [{"id": e["id"], "name": e["name"], "headline": e["headline"], "skills": e["skills"]}
                                      for e in load_examples()]})

    @app.post("/api/profile/example")
    def api_profile_example(payload: ExampleIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Save a synthetic example as the profile (replaces the one for this token). Needs no CV and no LLM key."""
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        example = next((e for e in load_examples() if e["id"] == payload.id), None)
        if example is None:
            return envelope(error="unknown example profile", status=404)
        current = owner_of(request, x_profile_token)
        owner, token = save_target(current, x_profile_token, load_profile(settings, current) is not None)
        profile = example_profile(example)
        save_profile(settings, owner, profile)
        return envelope(profile_out(profile, owner, token))

    @app.get("/api/profile")
    def api_profile(request: Request, x_profile_token: str | None = Header(default=None)):
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        owner = owner_of(request, x_profile_token)
        profile = load_profile(settings, owner)
        return envelope(profile_out(profile, owner)) if profile else envelope(error="no saved profile", status=404)

    @app.post("/api/profile/remove")
    def api_profile_remove(payload: RemoveIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Remove one skill. It stays removed when the next CV is read."""
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        owner = owner_of(request, x_profile_token)
        profile = load_profile(settings, owner)
        if profile is None:
            return envelope(error="no saved profile", status=404)
        try:
            profile = ledger.remove_skill(profile, payload.skill_id)
        except ledger.LedgerError as exc:
            return envelope(error=str(exc), status=422)
        save_profile(settings, owner, profile)
        return envelope(profile_out(profile, owner))

    @app.put("/api/profile/progress")
    def api_profile_progress(payload: ProgressIn, request: Request, x_profile_token: str | None = Header(default=None)):
        """Remember which pathway tasks are ticked, for the pathway named by signature."""
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        owner = owner_of(request, x_profile_token)
        profile = load_profile(settings, owner)
        if profile is None:
            return envelope(error="no saved profile", status=404)
        progress = Progress(signature=payload.signature, doneIds=tuple(dict.fromkeys(payload.doneIds)), updatedAt=ledger.now_iso())
        profile = profile.model_copy(update={"progress": progress})
        save_profile(settings, owner, profile)
        return envelope(profile_out(profile, owner))

    @app.delete("/api/profile")
    def api_profile_delete(request: Request, x_profile_token: str | None = Header(default=None)):
        if not profile_limiter.allow(client(request)):
            return envelope(error="too many requests, try again in a minute", status=429)
        if not delete_profile(settings, owner_of(request, x_profile_token)):
            return envelope(error="no saved profile", status=404)
        return envelope({"deleted": True})
