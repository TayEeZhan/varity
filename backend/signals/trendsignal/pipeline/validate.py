"""Validate LLM enrichment output: strict schema, then every evidence quote must exist in the source."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trendsignal.models import Enrichment, Entity

MIN_QUOTE_CHARS = 8

Category = Literal[
    "model_release", "research", "product_feature", "dev_tool_release", "api_pricing_change",
    "security_incident", "policy_regulation", "funding_business", "benchmark", "opinion",
]
Audience = Literal["ml_engineer", "backend", "frontend", "data", "devops", "security", "student"]
EntityType = Literal["model", "org", "library", "product", "topic", "person"]


class EntityPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    type: EntityType


class EnrichmentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    entities: list[EntityPayload] = Field(max_length=8)
    change_magnitude: int = Field(ge=1, le=5)
    magnitude_reason: str = Field(min_length=3, max_length=300)
    audience: list[Audience] = Field(min_length=1, max_length=7)
    is_breaking_change: bool
    tldr: str = Field(min_length=10, max_length=400)
    why_it_matters: str = Field(min_length=10, max_length=300)
    evidence_quotes: list[str] = Field(min_length=1, max_length=3)


class EnrichmentInvalid(ValueError):
    """The model's output failed the schema or the evidence check."""


def _normalise(text: str) -> str:
    return " ".join(re.sub(r"[\"'“”‘’`]", "", text).split()).casefold()


def quote_supported(quote: str, source_text: str) -> bool:
    cleaned = _normalise(quote).strip(" .,;:")
    return len(cleaned) >= MIN_QUOTE_CHARS and cleaned in _normalise(source_text)


def validate_enrichment(raw: str | dict, source_text: str, model: str) -> Enrichment:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        payload = EnrichmentPayload.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise EnrichmentInvalid(f"schema check failed: {exc}") from exc
    unsupported = [q for q in payload.evidence_quotes if not quote_supported(q, source_text)]
    if unsupported:
        raise EnrichmentInvalid(f"evidence quotes not found in the source: {unsupported[:2]}")
    return Enrichment(
        category=payload.category,
        entities=tuple(Entity(name=e.name, type=e.type) for e in payload.entities),
        change_magnitude=payload.change_magnitude,
        magnitude_reason=payload.magnitude_reason,
        audience=tuple(dict.fromkeys(payload.audience)),
        is_breaking_change=payload.is_breaking_change,
        tldr=payload.tldr.strip(),
        why_it_matters=payload.why_it_matters.strip(),
        evidence_quotes=tuple(q.strip() for q in payload.evidence_quotes),
        enriched_by=model,
    )
