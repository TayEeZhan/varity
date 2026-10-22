import math
from dataclasses import replace
from datetime import date

import pytest

from trendsignal.decision.jev import JevDecision
from trendsignal.decision.ranker import (RankEntry, expected_impact, impact_confidence, jev_final_score, jev_tier,
                                         rank_stories)
from trendsignal.pipeline.features import BuiltFeatures
from tests.test_jev import FEATURES

DAY = date(2026, 10, 22)
UNIFORM = {k: 0.2 for k in range(1, 6)}
CERTAIN = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 1.0}


def decision(must=0.72, worth=0.23, impact=None):
    return JevDecision({"must_know": must, "worth_a_look": worth, "minor": round(1 - must - worth, 4)},
                       impact or {1: 0.0, 2: 0.05, 3: 0.1, 4: 0.35, 5: 0.5}, 0.8, 0.7, "jev-1.13.0")


def entry(story_id, *, formula=60.0, magnitude=3, confirmed=True, jev=None, day=DAY, error=None, **feature_changes):
    features = replace(FEATURES, **feature_changes)
    return RankEntry(story_id, day, BuiltFeatures(features, "OpenAI News", None), formula, magnitude, confirmed,
                     jev, error)


def test_expected_impact_and_entropy_confidence():
    assert expected_impact(CERTAIN) == 5.0 and expected_impact(UNIFORM) == 3.0
    assert impact_confidence(CERTAIN) == 1.0 and impact_confidence(UNIFORM) == 0.0


def test_final_score_follows_the_plan_scaled_to_100():
    probs = {"must_know": 0.72, "worth_a_look": 0.23, "minor": 0.05}
    plan_score = 100 * (0.6 * 0.72 + 0.3 * 0.23) * (0.5 + 0.5 * 0.81)
    assert jev_final_score(probs, 0.81) == pytest.approx(plan_score / 0.6, abs=0.01)
    assert jev_final_score({"must_know": 1.0, "worth_a_look": 0.0, "minor": 0.0}, 1.0) == 100.0


def test_jev_tier_is_the_argmax():
    assert jev_tier({"must_know": 0.2, "worth_a_look": 0.5, "minor": 0.3}) == "worth_a_look"


def test_jev_mode_ranks_by_probabilities():
    ranked = rank_stories([entry(1, jev=decision(0.9, 0.08)), entry(2, jev=decision(0.1, 0.3))], "jev", _weights())
    assert [r.story_id for r in ranked] == [1, 2] and ranked[0].tier == "must_know" and ranked[0].ranked_by == "jev"
    assert ranked[0].expected_impact == pytest.approx(4.3) and 0 < ranked[0].confidence < 1


def test_jev_mode_falls_back_to_the_formula_per_story():
    ranked = rank_stories([entry(1, formula=80.0, jev=None, error="Jev call failed (TimeoutError)")], "jev", _weights())
    assert ranked[0].ranked_by == "formula" and ranked[0].final_score == 80.0
    assert ranked[0].jev_error.startswith("Jev call failed") and ranked[0].confidence is None


def test_formula_mode_keeps_jev_as_a_second_opinion():
    ranked = rank_stories([entry(1, formula=55.0, jev=decision(0.9, 0.08))], "formula", _weights())
    assert ranked[0].ranked_by == "formula" and ranked[0].final_score == 55.0
    assert ranked[0].tier == "worth_a_look" and ranked[0].tier_probs["must_know"] == 0.9


@pytest.mark.parametrize("changes, note", [
    ({"superseded": True}, "superseded"),
    ({"social_only": True}, "social posts only"),
    ({"confirmed": False}, "official or research source"),
])
def test_guardrails_override_a_must_know_proposal(changes, note):
    confirmed = changes.pop("confirmed", True)
    ranked = rank_stories([entry(1, confirmed=confirmed, jev=decision(0.95, 0.04), **changes)], "jev", _weights())
    assert ranked[0].tier != "must_know" and note in ranked[0].notes[0]


def test_must_know_cap_is_per_day():
    entries = [entry(i, jev=decision(0.9 - i * 0.01, 0.05)) for i in range(7)]
    entries.append(entry(99, jev=decision(0.9, 0.05), day=date(2026, 10, 21)))
    ranked = {r.story_id: r for r in rank_stories(entries, "jev", _weights())}
    assert [ranked[i].tier for i in range(7)].count("must_know") == 5
    assert "cap" in ranked[6].notes[0] and ranked[99].tier == "must_know"


def test_formula_low_impact_single_source_is_minor():
    ranked = rank_stories([entry(1, formula=60.0, magnitude=2, origins=1)], "formula", _weights())
    assert ranked[0].tier == "minor"


def test_rank_numbers_follow_tier_then_score():
    ranked = rank_stories([entry(1, formula=55.0), entry(2, formula=90.0), entry(3, formula=10.0)], "formula", _weights())
    assert [(r.rank, r.story_id, r.tier) for r in ranked] == [(1, 2, "must_know"), (2, 1, "worth_a_look"), (3, 3, "minor")]


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        rank_stories([], "magic", _weights())


def _weights():
    from tests.conftest import CONFIG_DIR
    from trendsignal.config import load_weights

    return load_weights(CONFIG_DIR)


def test_entropy_matches_definition():
    probs = {1: 0.5, 2: 0.5, 3: 0.0, 4: 0.0, 5: 0.0}
    assert impact_confidence(probs) == pytest.approx(1 - math.log(2) / math.log(5), abs=1e-3)
