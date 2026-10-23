"""Tier assignment: Must-know (capped per day), Worth a look, Minor, and the Emerging lane."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from trendsignal.config import Weights


@dataclass(frozen=True)
class TierInput:
    story_id: int
    importance: float
    confirmed: bool  # Tier A/B source or 3+ origins: eligible for Must-know
    social_only: bool  # only social posts: never Must-know or Worth a look
    velocity: float
    day: date  # local calendar day the story was first seen
    superseded: bool = False  # an older release of a tool that has shipped a newer one since
    low_impact: bool = False  # impact <= 2/5 reported by a single origin: routine, not worth a look


def assign_tiers(inputs: list[TierInput], weights: Weights) -> dict[int, str]:
    tiers: dict[int, str] = {}
    by_day: dict[date, list[TierInput]] = defaultdict(list)
    for entry in inputs:
        if entry.social_only:
            tiers[entry.story_id] = "emerging" if entry.velocity >= weights.emerging_velocity_min else "minor"
        elif entry.superseded or entry.low_impact:
            tiers[entry.story_id] = "minor"
        else:
            by_day[entry.day].append(entry)

    for entries in by_day.values():
        must_know_slots = weights.daily_must_know_cap
        for entry in sorted(entries, key=lambda e: (-e.importance, e.story_id)):
            if entry.confirmed and entry.importance >= weights.must_know_threshold and must_know_slots > 0:
                tiers[entry.story_id] = "must_know"
                must_know_slots -= 1
            elif entry.importance >= weights.worth_a_look_threshold:
                tiers[entry.story_id] = "worth_a_look"
            else:
                tiers[entry.story_id] = "minor"
    return tiers
