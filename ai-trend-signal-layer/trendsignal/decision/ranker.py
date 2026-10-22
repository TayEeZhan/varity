"""Ranker: turns Jev's probabilities (or the formula's score) into a ranked list with hard guardrails.

    expected_impact = sum(k * P(impact = k)) for k = 1..5
    confidence      = 1 - normalised entropy of impact_probs
    final_score     = 100 * [P(must_know) + 0.5 * P(worth_a_look)] * (0.5 + 0.5 * confidence)

The plan writes the score as 0.6 * P(must_know) + 0.3 * P(worth_a_look). That has the same ordering;
dividing by 0.6 puts it on the 0-100 scale the formula uses, so the two can sit in one list.

Guardrails apply to both paths: superseded releases are Minor, social-only stories are never
Must-know, Must-know needs an official or research source or 3 independent reports, and at most
5 stories a day are Must-know.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from trendsignal.config import Weights
from trendsignal.decision.jev import TIER_KEYS, JevDecision
from trendsignal.pipeline.features import BuiltFeatures, top_features

TIER_ORDER = {tier: index for index, tier in enumerate(TIER_KEYS)}
WORTH_WEIGHT = 0.5  # P(worth_a_look) counts half as much as P(must_know)
LOW_IMPACT_MAX = 2  # formula path: impact at or below this needs a second origin to rise above Minor


def expected_impact(impact_probs: dict[int, float]) -> float:
    return round(sum(level * p for level, p in impact_probs.items()), 3)


def impact_confidence(impact_probs: dict[int, float]) -> float:
    entropy = -sum(p * math.log(p) for p in impact_probs.values() if p > 0)
    return round(max(0.0, 1.0 - entropy / math.log(len(impact_probs))), 3)


def jev_final_score(tier_probs: dict[str, float], confidence: float) -> float:
    weighted = tier_probs["must_know"] + WORTH_WEIGHT * tier_probs["worth_a_look"]
    return round(100.0 * weighted * (0.5 + 0.5 * confidence), 2)


def jev_tier(tier_probs: dict[str, float]) -> str:
    return max(TIER_KEYS, key=lambda tier: (tier_probs[tier], -TIER_ORDER[tier]))


def formula_tier(importance: float, weights: Weights, low_impact: bool) -> str:
    if low_impact:
        return "minor"
    if importance >= weights.must_know_threshold:
        return "must_know"
    return "worth_a_look" if importance >= weights.worth_a_look_threshold else "minor"


@dataclass(frozen=True)
class RankEntry:
    """Everything the ranker needs about one story."""

    story_id: int
    day: date  # local day first seen, for the daily Must-know cap
    built: BuiltFeatures
    formula_score: float
    change_magnitude: int  # rule-based impact, used when the formula ranks
    confirmed: bool
    jev: JevDecision | None = None
    jev_error: str | None = None


@dataclass(frozen=True)
class RankedStory:
    story_id: int
    rank: int
    tier: str
    final_score: float
    ranked_by: str  # "jev" or "formula"
    expected_impact: float
    confidence: float | None
    tier_probs: dict[str, float] | None  # present whenever Jev answered, even as a second opinion
    impact_probs: dict[int, float] | None
    jev_model: str | None
    jev_error: str | None
    formula_score: float
    built: BuiltFeatures
    top_features: tuple[str, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class _Scored:
    entry: RankEntry
    ranked_by: str
    final_score: float
    proposed: str
    expected: float
    confidence: float | None


def _score(entry: RankEntry, mode: str, weights: Weights) -> _Scored:
    if mode == "jev" and entry.jev is not None:
        confidence = impact_confidence(entry.jev.impact_probs)
        return _Scored(entry, "jev", jev_final_score(entry.jev.tier_probs, confidence), jev_tier(entry.jev.tier_probs),
                       expected_impact(entry.jev.impact_probs), confidence)
    low_impact = entry.change_magnitude <= LOW_IMPACT_MAX and entry.built.features.origins < 2
    return _Scored(entry, "formula", entry.formula_score, formula_tier(entry.formula_score, weights, low_impact),
                   float(entry.change_magnitude), None)


def apply_guardrails(scored: list[_Scored], cap: int) -> dict[int, tuple[str, tuple[str, ...]]]:
    """Return story_id -> (tier, notes explaining any demotion)."""
    result: dict[int, tuple[str, tuple[str, ...]]] = {}
    must_by_day: dict[date, list[_Scored]] = defaultdict(list)
    for item in scored:
        features = item.entry.built.features
        tier, notes = item.proposed, ()
        if features.superseded:
            tier, notes = "minor", ("superseded by a newer release",)
        elif tier == "must_know" and features.social_only:
            tier, notes = "worth_a_look", ("social posts only: cannot be Must-know",)
        elif tier == "must_know" and not item.entry.confirmed:
            tier, notes = "worth_a_look", ("Must-know needs an official or research source, or 3 reports",)
        if tier == "must_know":
            must_by_day[item.entry.day].append(item)
        result[item.entry.story_id] = (tier, notes)
    for items in must_by_day.values():
        for overflow in sorted(items, key=lambda i: (-i.final_score, i.entry.story_id))[cap:]:
            result[overflow.entry.story_id] = ("worth_a_look", (f"daily Must-know cap of {cap} reached",))
    return result


def rank_stories(entries: list[RankEntry], mode: str, weights: Weights) -> list[RankedStory]:
    """mode "jev": Jev ranks, the formula steps in per story when Jev has no answer.
    mode "formula": the formula ranks; Jev's answers, if any, are kept as a second opinion."""
    if mode not in ("jev", "formula"):
        raise ValueError("mode must be 'jev' or 'formula'")
    scored = [_score(entry, mode, weights) for entry in entries]
    tiers = apply_guardrails(scored, weights.daily_must_know_cap)
    ordered = sorted(scored, key=lambda s: (TIER_ORDER[tiers[s.entry.story_id][0]], -s.final_score, s.entry.story_id))
    ranked = []
    for rank, item in enumerate(ordered, start=1):
        entry = item.entry
        tier, notes = tiers[entry.story_id]
        ranked.append(RankedStory(
            story_id=entry.story_id, rank=rank, tier=tier, final_score=item.final_score, ranked_by=item.ranked_by,
            expected_impact=item.expected, confidence=item.confidence,
            tier_probs=entry.jev.tier_probs if entry.jev else None,
            impact_probs=entry.jev.impact_probs if entry.jev else None,
            jev_model=entry.jev.model if entry.jev else None, jev_error=entry.jev_error,
            formula_score=entry.formula_score, built=entry.built, top_features=top_features(entry.built),
            notes=notes,
        ))
    return ranked
