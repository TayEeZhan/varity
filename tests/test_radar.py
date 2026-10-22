"""Tests for engine/radar.py: the Future Skills Radar data and the plain sentences under it."""

import json
import statistics
from pathlib import Path

import pytest

from engine import radar

DATA = Path(__file__).resolve().parent.parent / "data"


def skill(name, share=0.10, m12=100, p12=1000, mprev=100, pprev=1000, label=None, p=None, stance="neutral",
          status="ok"):
    """A skill_scores.json record with only the keys the radar reads."""
    return {"skill": name, "status": status, "demand_share_latest": share, "mentions_last12": m12,
            "posts_last12": p12, "mentions_prev12": mprev, "posts_prev12": pprev, "trend_label": label,
            "trend_p": p, "stance": stance}


@pytest.fixture
def skills():
    """8 plotted skills (4 above the median share, 4 below) and 1 rare skill that is not plotted."""
    return [
        skill("Big flat", share=0.30, m12=90, label="No clear change", p=0.5, stance="AI-substitutable"),
        skill("Big riser", share=0.20, m12=180, mprev=100, label="Rising", p=0.01, stance="AI-complement"),
        skill("Mid b", share=0.05, label="No clear change", p=0.4),
        skill("Mid a", share=0.013, label="No clear change", p=0.9),
        skill("Small riser", share=0.012, m12=60, mprev=40, label="Rising", p=0.03),
        skill("Small flat", share=0.011, m12=40, mprev=38, label="No clear change", p=0.8),
        skill("Small faller", share=0.010, m12=30, mprev=60, label="Falling", p=0.02, stance="AI-substitutable"),
        skill("Thin", share=0.005, status="low_volume", label=None),
        skill("Rare", share=0.0, status="rare", m12=0, mprev=0),
    ]


def by_name(out):
    return {p["skill"]: p for p in out["points"]}


def test_only_ok_and_low_volume_skills_are_plotted(skills):
    out = radar.radar_points(skills)
    assert set(by_name(out)) == {"Big flat", "Big riser", "Mid a", "Mid b", "Small riser", "Small faller",
                                 "Small flat", "Thin"}


def test_change_is_share_last_12_over_share_prior_12_minus_one():
    assert radar.share_change(skill("a", m12=150, p12=1000, mprev=100, pprev=1000)) == pytest.approx(0.5)
    assert radar.share_change(skill("a", m12=100, p12=500, mprev=100, pprev=1000)) == pytest.approx(1.0)
    assert radar.share_change(skill("a", m12=30, mprev=60)) == pytest.approx(-0.5)


@pytest.mark.parametrize("record", [
    skill("a", mprev=0), skill("a", pprev=0), skill("a", p12=0),
    {**skill("a"), "mentions_last12": None}, {**skill("a"), "posts_prev12": "x"}])
def test_change_is_none_when_the_counts_cannot_give_one(record):
    assert radar.share_change(record) is None


def test_a_skill_without_a_usable_share_or_change_is_skipped_and_named(skills):
    skills.append(skill("No share", share=None))
    skills.append(skill("Zero prior", mprev=0))
    out = radar.radar_points(skills)
    assert out["skipped"] == ["No share", "Zero prior"]
    assert "No share" not in by_name(out) and "Zero prior" not in by_name(out)


def test_only_a_welch_rising_or_falling_label_gets_a_colour(skills):
    pts = by_name(radar.radar_points(skills, contested={"Small riser"}))
    assert pts["Big riser"]["mark"] == radar.MARK_FILLED and pts["Big riser"]["group"] == "AI-complement"
    assert pts["Small faller"]["mark"] == radar.MARK_FILLED and pts["Small faller"]["group"] == "AI-substitutable"
    assert pts["Small riser"]["mark"] == radar.MARK_HOLLOW  # tested, but the stance is contested
    assert pts["Small riser"]["group"] == "neutral"
    for name in ("Big flat", "Mid a", "Small flat", "Thin"):
        assert pts[name]["mark"] == radar.MARK_GREY and pts[name]["group"] == radar.GREY_GROUP


def test_a_contested_skill_without_a_tested_label_stays_grey(skills):
    assert by_name(radar.radar_points(skills, contested={"Big flat"}))["Big flat"]["mark"] == radar.MARK_GREY


def test_the_users_skills_are_flagged(skills):
    pts = by_name(radar.radar_points(skills, my_skills=["Big flat", "Small riser", "Not on the chart"]))
    assert {n for n, p in pts.items() if p["mine"]} == {"Big flat", "Small riser"}


def test_quadrants_split_at_the_median_share_and_at_no_change(skills):
    out = radar.radar_points(skills)
    shares = [p["share"] for p in out["points"]]
    assert out["share_cut"] == statistics.median(shares)
    for p in out["points"]:
        assert p["quadrant"] == radar.QUADRANT_NAMES[(p["share"] >= out["share_cut"], p["change"] >= 0)]
    pts = by_name(out)
    assert pts["Big riser"]["quadrant"] == "Strong and growing"
    assert pts["Big flat"]["quadrant"] == "Strong but slowing"
    assert pts["Small riser"]["quadrant"] == "Small but rising"
    assert pts["Small faller"]["quadrant"] == "Small and fading"


def test_an_empty_input_gives_no_points_and_no_cut():
    out = radar.radar_points([])
    assert out == {"points": [], "share_cut": None, "skipped": []}


def test_user_counts_split_steady_into_strong_and_small(skills):
    out = radar.radar_points(skills, my_skills=["Big flat", "Small flat", "Big riser", "Small faller"])
    c = radar.user_counts(out["points"], out["share_cut"])
    assert [p["skill"] for p in c["rising"]] == ["Big riser"]
    assert [p["skill"] for p in c["falling"]] == ["Small faller"]
    assert [p["skill"] for p in c["strong_steady"]] == ["Big flat"]
    assert [p["skill"] for p in c["small_steady"]] == ["Small flat"]
    assert c["n"] == 4


def test_summary_sentences_are_built_from_the_counts(skills):
    out = radar.radar_points(skills, my_skills=["Big flat", "Small flat", "Big riser", "Rare"])
    first, second, third = radar.summary_sentences(out, ["Big flat", "Small flat", "Big riser", "Rare"])
    assert first == ("Your skills: 1 strong and steady, 1 small and steady, 1 rising (Big riser), "
                     "0 falling. 1 of your skills is too rare in posts to plot.")
    assert second == ("Across all 8 skills on the chart: 2 rising, 1 falling and 5 with no clear "
                      "change over the last 12 months.")
    assert third == ("Tested movers, with the change in their share of posts: rising, Big riser (+80%), "
                     "Small riser (+50%); falling, Small faller (-50%).")


def test_summary_without_user_skills_asks_for_them(skills):
    first = radar.summary_sentences(radar.radar_points(skills), [])[0]
    assert first == "Pick your skills in step 1 to see where they sit on the chart."


def test_summary_names_no_movers_as_none():
    out = radar.radar_points([skill("a", label="No clear change"), skill("b", share=0.3, label=None)])
    assert radar.summary_sentences(out, [])[2].endswith("rising, none; falling, none.")


def test_how_to_read_quotes_the_backtest_hit_rate_and_the_encoding():
    backtest = {"trend_label_backtest": {"trend_label_hit_rate": 0.6722, "n": 720}}
    text = radar.how_to_read(backtest)
    assert "67% of the time" in text and "n = 720" in text
    for needle in ("log scale", "Hacker News", "Welch", "hollow", "Grey", "black ring"):
        assert needle in text
    assert "backtest" not in radar.how_to_read(None)  # no number is invented without the file


# --- on the real data file ----------------------------------------------------------------

needs_real_data = pytest.mark.skipif(not (DATA / "skill_scores.json").exists(), reason="no real data")


@needs_real_data
def test_real_data_every_ok_or_low_volume_skill_with_counts_is_plotted_once():
    scores = json.loads((DATA / "skill_scores.json").read_text(encoding="utf-8"))
    out = radar.radar_points(scores["skills"])
    expected = [s["skill"] for s in scores["skills"]
                if s["status"] in radar.PLOT_STATUSES and s["demand_share_latest"] > 0 and s["mentions_prev12"] > 0]
    assert [p["skill"] for p in out["points"]] == expected
    assert len(expected) == len(set(expected)) > 20
    assert all(p["share"] > 0 for p in out["points"])  # a log axis needs positive values
    labelled = {s["skill"] for s in scores["skills"] if s["trend_label"] in radar.TESTED_LABELS}
    assert {p["skill"] for p in out["points"] if p["mark"] != radar.MARK_GREY} <= labelled
