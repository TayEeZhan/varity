from datetime import timedelta

import pytest

from trendsignal.pipeline.features import FeatureInputs, build_features, jev_state, state_hash, top_features
from trendsignal.pipeline.heuristics import classify_with_confidence, content_flags, release_level
from trendsignal.pipeline.score import ScoredItem
from trendsignal.timeutil import now_utc

NOW = now_utc()
DEV_TERMS = ("python", "pytorch", "api")
HN_BASELINE = {"hn": [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]}


def item(source_id, tier, *, social=False, author=None, engagement=None, name=None):
    return ScoredItem(source_id=source_id, source_name=name or source_id, tier=tier, is_social=social, author=author,
                      published_at=NOW - timedelta(hours=3), engagement=engagement or {})


def inputs(items, *, title="Introducing GPT-6 with a Python API", text="GPT-6 is available in the API.",
           category="model_release", confidence=0.85, novelty=0.9, superseded=False, hours_ago=10.0):
    return FeatureInputs(title=title, text=text, category=category, category_confidence=confidence,
                         items=tuple(items), novelty=novelty, superseded=superseded,
                         first_seen_at=NOW - timedelta(hours=hours_ago))


def test_vector_has_every_field_from_the_plan(weights):
    built = build_features(inputs([item("openai", "A", name="OpenAI News"),
                                   item("hn", "C", engagement={"points": 900}, name="Hacker News")]),
                           weights, HN_BASELINE, DEV_TERMS, NOW)
    f = built.features
    assert set(f.as_dict()) == {
        "best_tier", "authority", "has_official", "has_research", "social_only", "origins", "source_families",
        "velocity_z", "peak_engagement", "category_rule", "category_confidence", "release_level", "is_security",
        "is_breaking", "is_pricing", "is_howto", "model_name_hit", "dev_terms_hit", "novelty", "superseded",
        "age_hours"}
    assert (f.best_tier, f.authority, f.has_official, f.has_research, f.social_only) == ("A", 1.0, True, False, False)
    assert f.origins == 2 and f.source_families == 2
    assert f.velocity_z > 1.5 and f.peak_engagement == 900
    assert f.model_name_hit and f.dev_terms_hit == 2 and f.age_hours == 10.0
    assert built.best_source_name == "OpenAI News" and built.velocity_source == "Hacker News"


def test_social_only_story_and_follower_normalised_engagement(weights):
    built = build_features(inputs([item("x", "D", social=True, author="a", engagement={"likes": 50, "followers": 1000})]),
                           weights, {}, DEV_TERMS, NOW)
    assert built.features.social_only and built.features.peak_engagement == 500.0
    assert built.velocity_source is None


@pytest.mark.parametrize("title, expected", [
    ("Next.js 16.0.0", "major"), ("PyTorch 2.6.0", "minor"), ("vLLM v0.9.2", "patch"),
    ("Transformers v5.0.0rc1", "pre-release"), ("PyTorch trunk/1404563568be4b2d23634a409bd7a9c", "pre-release"),
    ("Some notes", "none"),
])
def test_release_level(title, expected):
    assert release_level(title) == expected


def test_release_level_only_counts_for_tool_releases(weights):
    built = build_features(inputs([item("blog", "A")], title="Our 2.0 strategy", category="product_feature"),
                           weights, {}, DEV_TERMS, NOW)
    assert built.features.release_level == "none"


@pytest.mark.parametrize("title, text, tier, release_feed, category, confidence", [
    ("Critical CVE-2026-1 in libfoo", "", "C", False, "security_incident", 0.85),
    ("Blog post", "A vulnerability was found.", "A", False, "security_incident", 0.6),
    ("LangChain 1.2.0", "", "A", True, "dev_tool_release", 0.95),
    ("Learning the 4D World", "", "B", False, "research", 0.6),
    ("A note on our new assistant", "", "A", False, "product_feature", 0.3),
])
def test_category_confidence_reflects_how_the_rule_matched(title, text, tier, release_feed, category, confidence):
    assert classify_with_confidence(title, text, tier, release_feed) == (category, confidence)


def test_content_flags():
    flags = content_flags("How to migrate: GPT-6 pricing changes", "This is a breaking change.")
    assert flags == {"is_security": False, "is_breaking": True, "is_pricing": True, "is_howto": True,
                     "model_name_hit": True}


def test_jev_state_rounds_so_unchanged_stories_hash_the_same(weights):
    a = build_features(inputs([item("openai", "A")], hours_ago=10.0), weights, {}, DEV_TERMS, NOW).features
    b = build_features(inputs([item("openai", "A")], hours_ago=11.5), weights, {}, DEV_TERMS, NOW).features
    c = build_features(inputs([item("openai", "A")], hours_ago=30.0), weights, {}, DEV_TERMS, NOW).features
    assert state_hash(jev_state(a)) == state_hash(jev_state(b)) != state_hash(jev_state(c))


def test_top_features_are_plain_language_and_capped(weights):
    built = build_features(inputs([item("openai", "A", name="OpenAI News"),
                                   item("hn", "C", engagement={"points": 900}, name="Hacker News")],
                                  text="A breaking change ships today.", novelty=0.1),
                           weights, HN_BASELINE, DEV_TERMS, NOW)
    drivers = top_features(built)
    assert drivers[0] == "official source (OpenAI News)" and "2 independent reports" in drivers
    assert any(d.startswith("trending") and d.endswith("Hacker News") for d in drivers)
    assert len(drivers) == 5
