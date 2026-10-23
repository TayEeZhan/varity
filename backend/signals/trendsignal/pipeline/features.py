"""Feature vector per story (ARCHITECTURE_JEV_RANKER.md section 5).

Code only. Every field is computable and auditable, and this record is exactly what Jev
receives. It is stored with each ranking so every rank can be reproduced.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime

from trendsignal.config import Weights
from trendsignal.pipeline.heuristics import content_flags, release_level
from trendsignal.pipeline.score import (ScoredItem, _term_patterns, count_origins, is_social_only,
                                        velocity)
from trendsignal.timeutil import hours_between

TIER_ORDER = "ABCD"
TRENDING_Z = 1.5
LOW_NOVELTY = 0.3
AGE_BUCKET_HOURS = 6  # Jev sees age rounded to 6 h so cached answers stay valid between runs


@dataclass(frozen=True)
class StoryFeatures:
    # Source
    best_tier: str
    authority: float
    has_official: bool
    has_research: bool
    social_only: bool
    # Corroboration
    origins: int
    source_families: int
    # Attention
    velocity_z: float
    peak_engagement: float
    # Content
    category_rule: str
    category_confidence: float
    release_level: str
    is_security: bool
    is_breaking: bool
    is_pricing: bool
    is_howto: bool
    model_name_hit: bool
    dev_terms_hit: int
    # Context
    novelty: float
    superseded: bool
    age_hours: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FeatureInputs:
    title: str
    text: str  # the anchor item's text
    category: str
    category_confidence: float
    items: tuple[ScoredItem, ...]
    novelty: float
    superseded: bool
    first_seen_at: datetime


@dataclass(frozen=True)
class BuiltFeatures:
    features: StoryFeatures
    best_source_name: str
    velocity_source: str | None


def peak_engagement(items: tuple[ScoredItem, ...]) -> float:
    """Largest raw attention number: HN points, HF upvotes, or likes (per 10k followers on X)."""
    peak = 0.0
    for item in items:
        e = item.engagement
        if "points" in e:
            value = e["points"]
        elif "upvotes" in e:
            value = e["upvotes"]
        elif "likes" in e:
            value = e["likes"] / max(e["followers"], 1.0) * 10_000 if e.get("followers") else e["likes"]
        else:
            continue
        peak = max(peak, float(value))
    return round(peak, 2)


def dev_terms_hit(title: str, text: str, dev_terms: tuple[str, ...]) -> int:
    haystack = f"{title} {text[:600]}".lower()
    return sum(1 for pattern in _term_patterns(dev_terms) if pattern.search(haystack))


def build_features(inputs: FeatureInputs, weights: Weights, baselines: dict[str, list[float]],
                   dev_terms: tuple[str, ...], now: datetime) -> BuiltFeatures:
    items = inputs.items
    best = min(items, key=lambda item: TIER_ORDER.index(item.tier))
    _velocity_feature, z, z_source = velocity(items, baselines, now)
    flags = content_flags(inputs.title, inputs.text)
    level = release_level(inputs.title) if inputs.category == "dev_tool_release" else "none"
    features = StoryFeatures(
        best_tier=best.tier,
        authority=weights.tier_trust[best.tier],
        has_official=any(item.tier == "A" for item in items),
        has_research=any(item.tier == "B" for item in items),
        social_only=is_social_only(items),
        origins=count_origins(items, weights.social_origin_cap),
        source_families=len({item.tier for item in items}),
        velocity_z=round(z, 2),
        peak_engagement=peak_engagement(items),
        category_rule=inputs.category,
        category_confidence=round(inputs.category_confidence, 2),
        release_level=level,
        is_security=flags["is_security"] or inputs.category == "security_incident",
        is_breaking=flags["is_breaking"],
        is_pricing=flags["is_pricing"] or inputs.category == "api_pricing_change",
        is_howto=flags["is_howto"],
        model_name_hit=flags["model_name_hit"],
        dev_terms_hit=dev_terms_hit(inputs.title, inputs.text, dev_terms),
        novelty=round(max(0.0, min(1.0, inputs.novelty)), 3),
        superseded=inputs.superseded,
        age_hours=round(hours_between(inputs.first_seen_at, now), 1),
    )
    return BuiltFeatures(features, best.source_name, z_source if z >= TRENDING_Z else None)


def jev_state(features: StoryFeatures) -> dict:
    """The feature vector as Jev sees it. Continuous values are rounded so that unchanged
    stories hash the same on the next run and reuse the cached answer."""
    state = features.as_dict()
    state["velocity_z"] = round(features.velocity_z, 1)
    state["peak_engagement"] = round(features.peak_engagement)
    state["novelty"] = round(features.novelty, 1)
    state["age_hours"] = round(features.age_hours / AGE_BUCKET_HOURS) * AGE_BUCKET_HOURS
    return state


def state_hash(state: dict) -> str:
    return hashlib.sha1(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()


def top_features(built: BuiltFeatures, limit: int = 5) -> tuple[str, ...]:
    """Plain-language drivers of the rank, strongest first. Derived from features only."""
    f = built.features
    drivers: list[str] = []
    if f.has_official:
        drivers.append(f"official source ({built.best_source_name})")
    elif f.has_research:
        drivers.append(f"research source ({built.best_source_name})")
    if f.origins >= 2:
        drivers.append(f"{f.origins} independent reports")
    if built.velocity_source:
        drivers.append(f"trending {f.velocity_z:.1f}σ on {built.velocity_source}")
    if f.is_security:
        drivers.append("security issue")
    if f.model_name_hit:
        drivers.append("model-name match")
    if f.is_breaking:
        drivers.append("breaking change")
    if f.release_level in ("major", "minor"):
        drivers.append(f"{f.release_level} release")
    if f.social_only:
        drivers.append("social posts only")
    if f.superseded:
        drivers.append("superseded by a newer release")
    if f.novelty < LOW_NOVELTY:
        drivers.append("similar to a recent story")
    return tuple(drivers[:limit])
