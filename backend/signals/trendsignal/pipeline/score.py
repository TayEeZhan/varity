"""Deterministic importance score (ARCHITECTURE_PLAN.md section 7.3). No LLM involved."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from trendsignal.config import Weights
from trendsignal.models import ScoreResult
from trendsignal.timeutil import hours_between

MIN_BASELINE_SIZE = 5
TRENDING_REASON_Z = 1.5
MAD_TO_SIGMA = 1.4826
CATEGORY_LABELS = {
    "model_release": "new model", "research": "research", "product_feature": "product feature",
    "dev_tool_release": "tool release", "api_pricing_change": "pricing/deprecation",
    "security_incident": "security", "policy_regulation": "policy", "funding_business": "business",
    "benchmark": "benchmark", "opinion": "opinion",
}


@dataclass(frozen=True)
class ScoredItem:
    source_id: str
    source_name: str
    tier: str
    is_social: bool
    author: str | None
    published_at: datetime
    engagement: dict[str, float]


@dataclass(frozen=True)
class ScoreInputs:
    title: str
    category: str
    change_magnitude: int
    entity_names: tuple[str, ...]
    tldr: str
    is_breaking_change: bool
    items: tuple[ScoredItem, ...]
    novelty: float


def count_origins(items: tuple[ScoredItem, ...], social_cap: int) -> int:
    official = {item.source_id for item in items if not item.is_social}
    social = {(item.source_id, item.author or "") for item in items if item.is_social}
    return len(official) + min(len(social), social_cap)


def is_confirmed(items: tuple[ScoredItem, ...], origins: int) -> bool:
    return any(item.tier in ("A", "B") for item in items) or origins >= 3


def is_social_only(items: tuple[ScoredItem, ...]) -> bool:
    return all(item.is_social or item.tier == "D" for item in items)


def engagement_rate(item: ScoredItem, now: datetime) -> float | None:
    """Engagement per hour since publication, on each platform's main metric."""
    e = item.engagement
    if "points" in e:
        value = e["points"]
    elif "upvotes" in e:
        value = e["upvotes"]
    elif "likes" in e:
        value = e["likes"] + 2 * e.get("reposts", 0.0)
        if e.get("followers"):
            value = value / max(e["followers"], 1.0) * 10_000  # per 10k followers
    else:
        return None
    return value / max(1.0, hours_between(item.published_at, now))


def robust_z(value: float, baseline: list[float]) -> float:
    if len(baseline) < MIN_BASELINE_SIZE:
        return 0.0
    median = statistics.median(baseline)
    mad = statistics.median(abs(x - median) for x in baseline)
    scale = mad * MAD_TO_SIGMA if mad > 0 else max(median, 1.0)
    return (value - median) / scale


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def velocity(items: tuple[ScoredItem, ...], baselines: dict[str, list[float]], now: datetime) -> tuple[float, float, str | None]:
    """Return (feature, best z, source name of the best z). No engagement data means 0."""
    best_z, best_source = None, None
    for item in items:
        rate = engagement_rate(item, now)
        if rate is None:
            continue
        z = robust_z(rate, baselines.get(item.source_id, []))
        if best_z is None or z > best_z:
            best_z, best_source = z, item.source_name
    if best_z is None:
        return 0.0, 0.0, None
    return sigmoid(best_z - 1.0), best_z, best_source


@lru_cache(maxsize=8)
def _term_patterns(terms: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])") for term in terms)


def dev_relevance(inputs: ScoreInputs, dev_terms: tuple[str, ...]) -> float:
    text = " ".join((inputs.title, inputs.tldr, *inputs.entity_names)).lower()
    matches = sum(1 for pattern in _term_patterns(dev_terms) if pattern.search(text))
    return min(1.0, matches / 3.0 + (0.3 if inputs.is_breaking_change else 0.0))


def freshness(age_hours: float, tau_hours: float) -> float:
    return math.exp(-age_hours / tau_hours)


def _reasons(inputs: ScoreInputs, origins: int, confirmed: bool, social_only: bool,
             z: float, z_source: str | None) -> tuple[str, ...]:
    reasons = []
    best = min(inputs.items, key=lambda item: "ABCD".index(item.tier))
    if best.tier == "A":
        reasons.append(f"official source ({best.source_name})")
    elif best.tier == "B":
        reasons.append(f"research source ({best.source_name})")
    reasons.append(f"{origins} independent report{'s' if origins != 1 else ''}")
    reasons.append(f"impact {inputs.change_magnitude}/5 ({CATEGORY_LABELS.get(inputs.category, inputs.category)})")
    if z >= TRENDING_REASON_Z and z_source:
        reasons.append(f"trending {z:.1f}σ above normal on {z_source}")
    if inputs.is_breaking_change:
        reasons.append("breaking change")
    if inputs.novelty < 0.3:
        reasons.append("close to a recent story")
    if social_only:
        reasons.append("social posts only: not yet confirmed")
    elif not confirmed:
        reasons.append("community source only: Must-know needs an official source or 3 reports")
    return tuple(reasons)


def score_story(inputs: ScoreInputs, weights: Weights, baselines: dict[str, list[float]],
                dev_terms: tuple[str, ...], now: datetime) -> ScoreResult:
    origins = count_origins(inputs.items, weights.social_origin_cap)
    confirmed = is_confirmed(inputs.items, origins)
    social_only = is_social_only(inputs.items)
    velocity_value, z, z_source = velocity(inputs.items, baselines, now)
    features = {
        "impact": inputs.change_magnitude / 5.0,
        "authority": max(weights.tier_trust[item.tier] for item in inputs.items),
        "corroboration": 1.0 - math.exp(-weights.corroboration_k * origins),
        "velocity": velocity_value,
        "dev_relevance": dev_relevance(inputs, dev_terms),
        "novelty": max(0.0, min(1.0, inputs.novelty)),
    }
    base = sum(weights.feature_weights[name] * value for name, value in features.items())
    penalty = (weights.penalty_unconfirmed if social_only else 0.0) + (
        weights.penalty_opinion if inputs.category == "opinion" else 0.0
    )
    importance = round(100.0 * max(0.0, base - penalty), 1)
    rounded = {name: round(value, 3) for name, value in features.items()}
    return ScoreResult(importance, rounded, round(penalty, 3), confirmed, social_only, origins,
                       _reasons(inputs, origins, confirmed, social_only, z, z_source))
