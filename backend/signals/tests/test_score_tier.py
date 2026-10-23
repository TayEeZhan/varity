from dataclasses import replace
from datetime import date, timedelta

import pytest
import yaml

from trendsignal.config import ConfigError, load_weights
from trendsignal.pipeline.score import ScoredItem, ScoreInputs, count_origins, freshness, robust_z, score_story
from trendsignal.pipeline.tier import TierInput, assign_tiers
from trendsignal.timeutil import now_utc
from tests.conftest import CONFIG_DIR

NOW = now_utc()
DEV_TERMS = ("python", "pytorch", "api")


def scored(source_id, tier, *, social=False, author=None, engagement=None, hours_ago=3.0, name=None):
    return ScoredItem(source_id=source_id, source_name=name or source_id, tier=tier, is_social=social, author=author,
                      published_at=NOW - timedelta(hours=hours_ago), engagement=engagement or {})


def inputs(items, *, magnitude=4, category="model_release", novelty=0.9, title="New model with Python API"):
    return ScoreInputs(title=title, category=category, change_magnitude=magnitude, entity_names=("python",),
                       tldr="", is_breaking_change=False, items=tuple(items), novelty=novelty)


HN_BASELINE = {"hn": [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}


def test_corroborated_trending_story_beats_a_lone_official_post(weights):
    lone = score_story(inputs([scored("openai", "A")]), weights, HN_BASELINE, DEV_TERMS, NOW)
    echoed = score_story(inputs([scored("openai", "A"), scored("hn", "C", engagement={"points": 900})]),
                         weights, HN_BASELINE, DEV_TERMS, NOW)
    assert echoed.importance > lone.importance
    assert echoed.features["velocity"] > 0.9
    assert any("trending" in reason for reason in echoed.reasons)
    assert lone.confirmed and echoed.origins == 2


def test_social_only_story_is_penalised_and_flagged(weights):
    social = score_story(inputs([scored("x", "D", social=True, author="a")]), weights, {}, DEV_TERMS, NOW)
    assert social.social_only and not social.confirmed
    assert social.penalty == pytest.approx(weights.penalty_unconfirmed)
    assert "social posts only" in social.reasons[-1]


def test_opinion_pieces_are_penalised(weights):
    news = score_story(inputs([scored("hn", "C")], category="product_feature"), weights, {}, DEV_TERMS, NOW)
    opinion = score_story(inputs([scored("hn", "C")], category="opinion"), weights, {}, DEV_TERMS, NOW)
    assert opinion.importance < news.importance


def test_social_pile_on_counts_as_at_most_the_cap(weights):
    items = tuple(scored("x", "D", social=True, author=f"user{i}") for i in range(20))
    assert count_origins(items, weights.social_origin_cap) == weights.social_origin_cap


def test_robust_z_needs_a_baseline_and_handles_zero_spread():
    assert robust_z(100.0, [1.0, 2.0]) == 0.0
    assert robust_z(10.0, [5.0] * 6) == pytest.approx(1.0)
    assert robust_z(20.0, [1, 2, 3, 4, 5]) > 5


def test_freshness_decays_with_age():
    assert freshness(0, 36) == 1.0
    assert freshness(36, 36) == pytest.approx(0.3679, abs=1e-3)


def tier_input(story_id, importance, *, confirmed=True, social_only=False, velocity=0.0, superseded=False,
               day=date(2026, 10, 22)):
    return TierInput(story_id, importance, confirmed, social_only, velocity, day, superseded)


def test_must_know_is_capped_per_day_and_overflow_drops_a_tier(weights):
    entries = [tier_input(i, 90 - i) for i in range(7)]
    tiers = assign_tiers(entries, weights)
    assert [tiers[i] for i in range(7)].count("must_know") == weights.daily_must_know_cap
    assert tiers[5] == tiers[6] == "worth_a_look"


def test_cap_applies_separately_to_each_day(weights):
    entries = [tier_input(i, 90, day=date(2026, 10, 21 + i % 2)) for i in range(8)]
    assert list(assign_tiers(entries, weights).values()).count("must_know") == 8


def test_community_only_story_cannot_be_must_know(weights):
    assert assign_tiers([tier_input(1, 95, confirmed=False)], weights)[1] == "worth_a_look"


def test_social_only_goes_to_emerging_only_when_trending(weights):
    tiers = assign_tiers([tier_input(1, 40, social_only=True, confirmed=False, velocity=0.9),
                          tier_input(2, 40, social_only=True, confirmed=False, velocity=0.1)], weights)
    assert tiers == {1: "emerging", 2: "minor"}


def test_superseded_release_is_minor(weights):
    assert assign_tiers([tier_input(1, 80, superseded=True)], weights)[1] == "minor"


def test_single_source_routine_change_is_minor(weights):
    entries = [TierInput(1, 60, True, False, 0.0, date(2026, 10, 22), low_impact=True),
               TierInput(2, 60, True, False, 0.0, date(2026, 10, 22), low_impact=False)]
    assert assign_tiers(entries, weights) == {1: "minor", 2: "worth_a_look"}


def test_low_scores_are_minor(weights):
    assert assign_tiers([tier_input(1, 20)], weights)[1] == "minor"


def test_weights_must_sum_to_one(tmp_path):
    data = yaml.safe_load((CONFIG_DIR / "weights.yaml").read_text(encoding="utf-8"))
    data["feature_weights"]["impact"] = 0.9
    (tmp_path / "weights.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_weights(tmp_path)
