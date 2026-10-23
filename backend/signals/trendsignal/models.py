"""Immutable records passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

CATEGORIES = (
    "model_release",
    "research",
    "product_feature",
    "dev_tool_release",
    "api_pricing_change",
    "security_incident",
    "policy_regulation",
    "funding_business",
    "benchmark",
    "opinion",
)

AUDIENCES = ("ml_engineer", "backend", "frontend", "data", "devops", "security", "student")

TIERS = ("must_know", "worth_a_look", "minor", "emerging")

FEEDBACK_SIGNALS = ("useful", "not_important", "already_knew", "wrong")


@dataclass(frozen=True)
class RawItemIn:
    """One post, release, paper or article as a collector found it."""

    source_id: str
    external_id: str
    url: str
    title: str
    text: str
    published_at: datetime
    author: str | None = None
    engagement: dict[str, float] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Item:
    """A normalised item as stored in the items table."""

    id: int
    source_id: str
    tier: str
    canonical_url: str
    title: str
    text: str
    author: str | None
    published_at: datetime
    engagement: dict[str, float]
    story_id: int | None


@dataclass(frozen=True)
class Entity:
    name: str
    type: str


@dataclass(frozen=True)
class Enrichment:
    category: str
    entities: tuple[Entity, ...]
    change_magnitude: int
    magnitude_reason: str
    audience: tuple[str, ...]
    is_breaking_change: bool
    tldr: str
    why_it_matters: str
    evidence_quotes: tuple[str, ...]
    enriched_by: str  # model id, or "heuristic"


@dataclass(frozen=True)
class ScoreResult:
    importance: float  # 0..100, no time decay: decides the tier
    features: dict[str, float]
    penalty: float
    confirmed: bool  # has a Tier A/B source or 3+ independent origins: may become Must-know
    social_only: bool  # every report is a social post: penalised, and goes to the Emerging lane
    origins: int
    reasons: tuple[str, ...]
