"""Jev client against the real TypeSafe SDK response and error types, with a fake transport."""

import httpx2
import pytest
from typesafe_sdk import (ChoiceAnswer, NoulAnswer, ScoreAnswer, SystemOneResponse, TypeSafeAPITimeoutError,
                          TypeSafeAuthenticationError, Usage)

from trendsignal.decision.jev import (IMPACT_LEVELS, JevCache, JevClient, JevError, make_jev_client,
                                      parse_story_answers, story_questions)
from trendsignal.pipeline.features import StoryFeatures

FEATURES = StoryFeatures(
    best_tier="A", authority=1.0, has_official=True, has_research=False, social_only=False, origins=2,
    source_families=2, velocity_z=3.1, peak_engagement=900.0, category_rule="model_release",
    category_confidence=0.85, release_level="none", is_security=False, is_breaking=False, is_pricing=False,
    is_howto=False, model_name_hit=True, dev_terms_hit=2, novelty=0.9, superseded=False, age_hours=10.0)


def response(tier=None, impact=None, *, legend=True, input_tokens=1000):
    tier = tier or {"must_know": 0.72, "worth_a_look": 0.23, "minor": 0.05}
    impact = impact or {0: 0.0, 1: 0.05, 2: 0.1, 3: 0.35, 4: 0.5}
    legend_map = {i: IMPACT_LEVELS[i] for i in range(5)} if legend else {}
    return SystemOneResponse(model="jev-1.13.0", usage=Usage(input_tokens=input_tokens), answers={
        "tier": ChoiceAnswer(choice=max(tier, key=tier.get), confidence=0.8, probabilities=tier),
        "impact": ScoreAnswer(score=3.2, confidence=0.7, legend=legend_map, probabilities=impact),
    })


class FakeTypeSafe:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def system_one(self, state, questions, *, timeout=None):
        self.calls.append((state, questions, timeout))
        outcome = self.outcomes.pop(0) if self.outcomes else response()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_questions_use_the_sdk_shapes():
    questions = story_questions()
    assert questions["tier"]["type"] == "choice" and set(questions["tier"]["criteria"]) == {"must_know", "worth_a_look", "minor"}
    assert questions["impact"]["type"] == "score" and len(questions["impact"]["criteria"]) == 5


def test_answers_map_to_tier_and_impact_probabilities():
    decision = parse_story_answers(response(), "jev-1.13.0")
    assert decision.tier_probs == {"must_know": 0.72, "worth_a_look": 0.23, "minor": 0.05}
    assert decision.impact_probs == {1: 0.0, 2: 0.05, 3: 0.1, 4: 0.35, 5: 0.5}
    assert decision.tier_confidence == 0.8 and decision.impact_confidence == 0.7


def test_impact_keys_without_a_legend_are_mapped_by_position():
    decision = parse_story_answers(response(legend=False, impact={1: 0.1, 2: 0.1, 3: 0.2, 4: 0.3, 5: 0.3}), "m")
    assert decision.impact_probs[5] == 0.3


@pytest.mark.parametrize("tier", [
    {"must_know": 0.9, "worth_a_look": 0.9, "minor": 0.9},  # does not sum to 1
    {"must_know": 0.5, "worth_a_look": 0.5},  # missing a tier
    {"must_know": -0.1, "worth_a_look": 0.6, "minor": 0.5},  # negative
])
def test_invalid_distributions_are_rejected(tier):
    with pytest.raises(JevError):
        parse_story_answers(response(tier=tier), "m")


def test_decide_sends_the_feature_vector_with_the_timeout_and_counts_cost():
    fake = FakeTypeSafe(response(input_tokens=2_000_000))
    client = JevClient(fake, "jev-1.13.0", timeout_s=2.0)
    decision = client.decide(FEATURES)
    state, questions, timeout = fake.calls[0]
    assert state["category_rule"] == "model_release" and state["origins"] == 2 and timeout == 2.0
    assert set(questions) == {"tier", "impact"}
    assert decision.tier_probs["must_know"] == 0.72 and client.cost_usd == pytest.approx(0.084)


def test_timeouts_fail_one_call_but_keep_the_client_open():
    client = JevClient(FakeTypeSafe(TypeSafeAPITimeoutError(2.0)), "m")
    with pytest.raises(JevError, match="TimeoutError"):
        client.decide(FEATURES)
    assert client.open


def test_authentication_errors_close_the_client_for_the_run():
    error = TypeSafeAuthenticationError(401, {}, httpx2.Headers())
    fake = FakeTypeSafe(error)
    client = JevClient(fake, "m")
    with pytest.raises(JevError):
        client.decide(FEATURES)
    assert not client.open
    with pytest.raises(JevError):
        client.decide(FEATURES)
    assert len(fake.calls) == 1  # no second paid call after a fatal error


def test_call_limit_stops_runaway_spend():
    client = JevClient(FakeTypeSafe(), "m", max_calls=1)
    client.decide(FEATURES)
    with pytest.raises(JevError, match="limit"):
        client.decide(FEATURES)


def test_cache_avoids_paying_twice_for_the_same_state(settings):
    fake = FakeTypeSafe()
    client = JevClient(fake, "jev-1.13.0", cache=JevCache(settings.db_path))
    first, second = client.decide(FEATURES), client.decide(FEATURES)
    assert len(fake.calls) == 1 and second.cached and second.tier_probs == first.tier_probs


def test_same_story_returns_the_noul_probability():
    reply = SystemOneResponse(model="m", usage=Usage(input_tokens=10), answers={"same_story": NoulAnswer(noul=0.83)})
    fake = FakeTypeSafe(reply)
    assert JevClient(fake, "m").same_story({"item_a": {}, "item_b": {}}) == 0.83
    assert fake.calls[0][1]["same_story"]["type"] == "noul"


def test_no_client_without_a_key(settings):
    assert make_jev_client(settings) is None


def test_real_sdk_client_is_built_when_a_key_is_set(settings):
    from dataclasses import replace

    client = make_jev_client(replace(settings, jev_api_key="ts-test-key"))
    assert isinstance(client, JevClient) and client.model == "jev-1.13.0"
    assert make_jev_client(replace(settings, jev_api_key="ts-test-key", jev_mode="off")) is None
