"""Data types for the CV intake.

Two groups:
- `Mention` / `Extraction`: what the LLM returns. Untrusted until intake.verify checks it.
- `Evidence` / `SkillEntry` / `Profile`: the skill ledger (profile.json v2). Frozen, so
  every change goes through intake.ledger and returns a new object.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 2

Context = Literal["work", "project", "education", "certification", "skills_list", "interest"]
EvidenceContext = Literal["work", "project", "education", "certification", "skills_list", "inferred", "user"]
Source = Literal["cv", "form", "inferred", "imported", "pathway", "github"]
Method = Literal[
    "llm", "keyword", "llm+keyword", "user_entry", "import", "task_done",
    "graph:requires", "graph:part_of", "graph:often_uses",
]
Basis = Literal["stated", "self_reported", "implied", "suggested"]

# Strongest first. A skill's basis is the strongest basis among its evidence.
BASIS_ORDER: tuple[Basis, ...] = ("stated", "self_reported", "implied", "suggested")

SKILL_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,59}$"
MAX_SKILLS = 150
MAX_EVIDENCE_PER_SKILL = 20
MAX_YEARS = 40.0


class Mention(BaseModel):
    """One skill mention, as the LLM reports it."""

    phrase: str
    evidence_quote: str
    context: Context
    years_quote: str | None


class Extraction(BaseModel):
    """The whole LLM answer for one CV."""

    mentions: list[Mention]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Evidence(_Frozen):
    """One reason to believe the person has a skill."""

    id: str = Field(default="", max_length=80)
    source: Source
    method: Method
    context: EvidenceContext | None = None
    quote: str | None = Field(default=None, max_length=300)
    rule: str | None = Field(default=None, max_length=200)
    from_skill: str | None = Field(default=None, pattern=SKILL_ID_PATTERN)
    years: float | None = Field(default=None, ge=0, le=MAX_YEARS)
    years_line: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=200)
    added_at: str = Field(max_length=40)
    added_by: str = Field(max_length=40)


class SkillEntry(_Frozen):
    """One skill in the ledger. `basis`, `evidence_quote` and `years` are derived from `evidence`."""

    skill_id: str = Field(pattern=SKILL_ID_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=30)
    basis: Basis
    evidence_quote: str | None = Field(default=None, max_length=300)
    years: float | None = Field(default=None, ge=0, le=MAX_YEARS)
    years_as_of: str | None = Field(default=None, max_length=10)
    evidence: tuple[Evidence, ...] = Field(min_length=1, max_length=MAX_EVIDENCE_PER_SKILL)


class Interest(_Frozen):
    """A skill the person is learning or wants to learn. Not counted as a skill."""

    phrase: str = Field(max_length=60)
    skill_id: str = Field(pattern=SKILL_ID_PATTERN)
    quote: str | None = Field(default=None, max_length=300)


class Removed(_Frozen):
    """A skill the user removed. Sticky: only the user can bring it back."""

    skill_id: str = Field(pattern=SKILL_ID_PATTERN)
    name: str = Field(min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=30)
    removed_at: str = Field(max_length=40)
    by: Literal["user"] = "user"
    held_evidence: tuple[Evidence, ...] = Field(default=(), max_length=MAX_EVIDENCE_PER_SKILL)


class Progress(_Frozen):
    """Pathway tasks the user ticked, for the pathway identified by `signature`."""

    signature: str = Field(max_length=128)
    doneIds: tuple[str, ...] = Field(default=(), max_length=500)
    updatedAt: str = Field(max_length=40)


class Declined(_Frozen):
    """A skill the user said "not now" to. Not offered again before `until` (YYYY-MM-DD)."""

    skill: str = Field(max_length=60)
    until: str = Field(max_length=10)


class PlanState(_Frozen):
    """The pathway the user last accepted, so a rebuild can say what changed (advisor/planner.py)."""

    role_id: str = Field(max_length=60)
    start_date: str = Field(max_length=10)  # fixed when first accepted, so task dates do not slide every day
    skills: tuple[str, ...] = Field(default=(), max_length=60)
    accepted_at: str = Field(max_length=40)
    pushed: tuple[str, ...] = Field(default=(), max_length=20)  # trend skills the user added
    declined: tuple[Declined, ...] = Field(default=(), max_length=60)
    last_offer_at: str | None = Field(default=None, max_length=40)
    offers: Literal["ask", "off"] = "ask"


class Profile(_Frozen):
    """The skill ledger: profile.json v2."""

    schema_version: Literal[2] = SCHEMA_VERSION
    profile_id: str = Field(pattern=SKILL_ID_PATTERN)
    name: str = Field(max_length=80)
    target_role: str | None = Field(default=None, max_length=80)
    updated_at: str = Field(max_length=40)
    skills: tuple[SkillEntry, ...] = Field(default=(), max_length=MAX_SKILLS)
    interests: tuple[Interest, ...] = Field(default=(), max_length=50)
    removed: tuple[Removed, ...] = Field(default=(), max_length=MAX_SKILLS)
    progress: Progress | None = None
    plan: PlanState | None = None
