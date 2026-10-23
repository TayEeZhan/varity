"""The skill ledger write API (doc section 6).

Every function takes a Profile and returns a new one; nothing is changed in place. Later
systems (the user adding a skill, pathway completions, a GitHub import) all write through
add_evidence(), so the rules below hold for every writer:
- only the intake may write CV evidence, and CV evidence must carry a quote;
- adding the same evidence twice changes nothing (ids are hashes of the content);
- a removed skill stays removed until the user restores it.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from intake.models import (
    BASIS_ORDER, MAX_EVIDENCE_PER_SKILL, MAX_SKILLS, SKILL_ID_PATTERN,
    Basis, Evidence, Interest, Profile, Removed, SkillEntry,
)
from intake.normalise import norm

CV_WRITERS = frozenset({"intake"})
MAX_IMPORT_BYTES = 256 * 1024


class LedgerError(ValueError):
    """A write the ledger refuses. The message is safe to show to the user."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_profile(profile_id: str = "my-profile", name: str = "", now: str | None = None) -> Profile:
    return Profile(profile_id=profile_id, name=name, updated_at=now or now_iso())


def evidence_id(evidence: Evidence, skill_id: str) -> str:
    """Same content, same id. Form entries with no text are told apart by their years."""
    text = evidence.quote or evidence.rule or evidence.note or f"years={evidence.years}"
    digest = hashlib.sha1(f"{evidence.source}|{skill_id}|{norm(text)}".encode("utf-8")).hexdigest()
    return "sha1:" + digest[:16]


def basis_of(evidence: Evidence) -> Basis:
    if evidence.source == "cv":
        return "stated"
    if evidence.source == "inferred":
        return "suggested" if evidence.method == "graph:often_uses" else "implied"
    return "self_reported"


def _derive(skill_id: str, name: str, category: str | None, evidence: tuple[Evidence, ...], as_of: str) -> SkillEntry:
    """Basis, best quote and years come from the evidence, never from the caller."""
    basis = min((basis_of(item) for item in evidence), key=BASIS_ORDER.index)
    quotes = [item.quote for item in evidence if item.source == "cv" and item.quote]
    cv_years = [item.years for item in evidence if item.source == "cv" and item.years is not None]
    other_years = [item.years for item in evidence if item.source != "cv" and item.years is not None]
    years = max(cv_years) if cv_years else (max(other_years) if other_years else None)
    return SkillEntry(
        skill_id=skill_id,
        name=name,
        category=category,
        basis=basis,
        evidence_quote=quotes[0] if quotes else None,
        years=years,
        years_as_of=as_of if years is not None else None,
        evidence=evidence,
    )


def _check_skill_id(skill_id: str) -> None:
    if not re.fullmatch(SKILL_ID_PATTERN, skill_id):
        raise LedgerError(f"Not a valid skill id: {skill_id!r}")


def add_evidence(
    profile: Profile,
    skill_id: str,
    name: str,
    evidence: Evidence,
    *,
    caller: str,
    category: str | None = None,
    now: str | None = None,
    as_of: str | None = None,
) -> Profile:
    """The one way to add a skill or more evidence for it."""
    _check_skill_id(skill_id)
    if evidence.source == "cv" and caller not in CV_WRITERS:
        raise LedgerError("Only the CV intake can add evidence from a CV.")
    if evidence.source == "cv" and not evidence.quote:
        raise LedgerError("CV evidence needs a quote from the CV.")
    stamp = now or now_iso()
    as_of = as_of or date.today().isoformat()
    item = evidence.model_copy(update={"id": evidence_id(evidence, skill_id)})

    for index, removed in enumerate(profile.removed):
        if removed.skill_id == skill_id:
            # Sticky removal: keep the evidence aside, do not bring the skill back.
            if any(held.id == item.id for held in removed.held_evidence):
                return profile
            if len(removed.held_evidence) >= MAX_EVIDENCE_PER_SKILL:
                raise LedgerError(f"Too much evidence for {name}.")
            held = removed.model_copy(update={"held_evidence": removed.held_evidence + (item,)})
            return profile.model_copy(update={"removed": _replace(profile.removed, index, held), "updated_at": stamp})

    for index, entry in enumerate(profile.skills):
        if entry.skill_id == skill_id:
            if any(old.id == item.id for old in entry.evidence):
                return profile
            if len(entry.evidence) >= MAX_EVIDENCE_PER_SKILL:
                raise LedgerError(f"Too much evidence for {entry.name}.")
            updated = _derive(skill_id, entry.name, entry.category, entry.evidence + (item,), as_of)
            return _with_skills(profile, _replace(profile.skills, index, updated), stamp)

    if len(profile.skills) >= MAX_SKILLS:
        raise LedgerError(f"A profile can hold at most {MAX_SKILLS} skills.")
    created = _derive(skill_id, name, category, (item,), as_of)
    return _with_skills(profile, profile.skills + (created,), stamp)


def _replace(items: tuple, index: int, value) -> tuple:
    return items[:index] + (value,) + items[index + 1:]


def _with_skills(profile: Profile, skills: tuple[SkillEntry, ...], stamp: str) -> Profile:
    """A skill the person has is no longer only an interest."""
    have = {entry.skill_id for entry in skills}
    interests = tuple(item for item in profile.interests if item.skill_id not in have)
    return profile.model_copy(update={"skills": skills, "interests": interests, "updated_at": stamp})


def remove_skill(profile: Profile, skill_id: str, now: str | None = None) -> Profile:
    """User only. The skill and its evidence move to removed[]."""
    entry = next((item for item in profile.skills if item.skill_id == skill_id), None)
    if entry is None:
        raise LedgerError("That skill is not in the profile.")
    removed = Removed(
        skill_id=entry.skill_id,
        name=entry.name,
        category=entry.category,
        removed_at=now or now_iso(),
        held_evidence=entry.evidence,
    )
    skills = tuple(item for item in profile.skills if item.skill_id != skill_id)
    return profile.model_copy(update={"skills": skills, "removed": profile.removed + (removed,), "updated_at": removed.removed_at})


def restore_skill(profile: Profile, skill_id: str, now: str | None = None, as_of: str | None = None) -> Profile:
    """User only. Brings a removed skill back with the evidence held for it."""
    removed = next((item for item in profile.removed if item.skill_id == skill_id), None)
    if removed is None:
        raise LedgerError("That skill was not removed.")
    remaining = tuple(item for item in profile.removed if item.skill_id != skill_id)
    if not removed.held_evidence:
        return profile.model_copy(update={"removed": remaining, "updated_at": now or now_iso()})
    entry = _derive(skill_id, removed.name, removed.category, removed.held_evidence, as_of or date.today().isoformat())
    restored = profile.model_copy(update={"removed": remaining})
    return _with_skills(restored, restored.skills + (entry,), now or now_iso())


def is_removed(profile: Profile, skill_id: str) -> bool:
    return any(item.skill_id == skill_id for item in profile.removed)


def add_interest(profile: Profile, interest: Interest, now: str | None = None) -> Profile:
    """Interests never override a skill the person already has."""
    if any(item.skill_id == interest.skill_id for item in profile.skills + profile.interests):
        return profile
    return profile.model_copy(update={"interests": profile.interests + (interest,), "updated_at": now or now_iso()})


def set_details(profile: Profile, *, name: str, target_role: str | None, now: str | None = None) -> Profile:
    return profile.model_copy(update={
        "name": name.strip()[:80],
        "target_role": (target_role or "").strip()[:80] or None,
        "updated_at": now or now_iso(),
    })


def to_json(profile: Profile) -> str:
    return profile.model_dump_json(indent=2)


def load_trusted_profile(path: Path) -> Profile:
    """For profiles committed to the repo (the demo). Uploaded files go through import_profile."""
    return Profile.model_validate_json(path.read_text(encoding="utf-8"))


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not allowed")


def _relabel(evidence: tuple[Evidence, ...], skill_id: str) -> tuple[Evidence, ...]:
    """Imported evidence was never checked against a CV here, so none of it counts as stated."""
    relabelled: dict[str, Evidence] = {}
    for item in evidence:
        moved = item.model_copy(update={"source": "imported", "method": "import"})
        moved = moved.model_copy(update={"id": evidence_id(moved, skill_id)})
        relabelled.setdefault(moved.id, moved)
    return tuple(relabelled.values())


def import_profile(data: bytes, *, now: str | None = None, as_of: str | None = None) -> Profile:
    """Read an uploaded profile.json. Every evidence row comes back as unverified."""
    if len(data) > MAX_IMPORT_BYTES:
        raise LedgerError("The file is too large for a profile (max 256 KB).")
    try:
        raw = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise LedgerError("The file is not valid JSON.") from None
    try:
        profile = Profile.model_validate(raw)
    except ValidationError:
        raise LedgerError("The file is not a Verity profile (schema version 2).") from None
    as_of = as_of or date.today().isoformat()
    skills = tuple(
        _derive(entry.skill_id, entry.name, entry.category, _relabel(entry.evidence, entry.skill_id), as_of)
        for entry in profile.skills
    )
    removed = tuple(
        item.model_copy(update={"held_evidence": _relabel(item.held_evidence, item.skill_id)})
        for item in profile.removed
    )
    return profile.model_copy(update={"skills": skills, "removed": removed, "updated_at": now or now_iso()})
