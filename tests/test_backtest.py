"""Tests for engine/backtest.py. Small synthetic series only."""

import numpy as np
import pandas as pd
import pytest

from engine import backtest as bt
from engine import forecast as fc
from engine.forecast import HORIZON, MODELS, PRODUCTION_MODELS


def make_demand(n_months=96, start="2019-01", seed=1):
    """Four skills with noise. 'Rare' never has enough mentions."""
    rng = np.random.default_rng(seed)
    months = [str(p) for p in pd.period_range(start, periods=n_months, freq="M")]
    n_posts = 400
    series = {
        "Up": 40 + 0.5 * np.arange(n_months) + rng.normal(0, 3, n_months),
        "Flat": 60 + rng.normal(0, 4, n_months),
        "Down": 120 - 0.6 * np.arange(n_months) + rng.normal(0, 3, n_months),
        "Rare": np.ones(n_months),
    }
    rows = []
    for skill, values in series.items():
        for month, m in zip(months, np.clip(np.round(values), 0, n_posts)):
            rows.append({"month": month, "skill": skill, "mentions": int(m), "n_posts": n_posts})
    return pd.DataFrame(rows)


# The first test origin with 24 usable origins at h=12 is 2023-11 (month index 58 of 96).
EARLY = bt.month_range("2022-01", "2022-06")
TEST = bt.month_range("2023-11", "2024-04")  # last target 2025-04
TREND = bt.month_range("2021-12", "2022-06")


@pytest.fixture(scope="module")
def result():
    return bt.run_backtest(make_demand(), EARLY, TEST, TREND)


def test_month_range_is_inclusive():
    assert bt.month_range("2021-11", "2022-02") == ["2021-11", "2021-12", "2022-01", "2022-02"]
    assert len(bt.month_range(bt.EARLY_FIRST, bt.EARLY_LAST)) == 23
    assert len(bt.month_range(bt.TEST_FIRST, bt.TEST_LAST)) == 24
    assert bt.TEST_FIRST == fc.earliest_supported(bt.month_range("2019-01", "2026-10"))


def test_coverage_on_a_toy_case():
    actual = [1, 2, 3, 4]
    low = [0, 0, 0, 5]
    high = [2, 2, 2, 6]
    assert bt.coverage(actual, low, high) == 0.5
    assert bt.coverage([1.0], [1.0], [1.0]) == 1.0  # band ends count as inside


def test_share_error_is_in_percentage_points():
    # logit(0.5) = 0, logit(0.6) differs by 10 pp on the share scale
    err = bt.share_abs_error_pp(np.log(0.6 / 0.4), 0.0)
    assert err == pytest.approx(10.0)


def test_result_has_the_required_fields(result):
    for key in ("models", "chosen_model", "chosen_because", "beats_naive", "interval", "coverage",
                "interval_sensitivity", "trend_label_hit_rate", "trend_label_backtest",
                "n_skills_used", "origins", "excluded_skills_at_last_origin", "generated_at",
                "production_models", "dropped_from_production", "model_choice"):
        assert key in result
    assert set(result["models"]) == set(MODELS)
    for m in MODELS:
        for split in ("early_mae_pp", "test_mae_pp"):
            assert {"h1", "h6", "h12"} <= set(result["models"][m][split])
    assert result["production_models"] == list(PRODUCTION_MODELS)
    assert result["dropped_from_production"] == ["drift", "damped"]
    assert result["models"]["drift"]["in_production"] is False  # numbers kept, not shipped
    assert len(result["interval"]["q_by_h_at_forecast_date"]) == HORIZON


def test_chosen_model_is_naive_or_naive3_with_the_lower_score(result):
    scores = result["model_choice"]["scores_at_forecast_date_pp"]
    assert result["chosen_model"] in PRODUCTION_MODELS
    assert scores[result["chosen_model"]] == min(scores.values())
    assert sum(result["model_choice"]["model_used_at_test_origins"].values()) == len(TEST)


def test_interval_and_coverage_blocks(result):
    assert result["interval"]["label"] == "80% target band"
    assert result["coverage"]["label"] == "80% target band"
    assert "set a priori" in result["interval"]["window_note"]
    assert result["interval"]["window_origins"] == 24
    assert result["interval"]["earliest_supported_as_of"] == "2023-11"
    c = result["coverage"]
    assert len(c["test_by_h"]) == HORIZON
    assert c["test_h12"] == c["test_by_h"][HORIZON - 1]
    assert c["test_mean_over_h"] == pytest.approx(np.mean(c["test_by_h"]), abs=1e-3)
    assert 0.0 <= c["test_h12"] <= 1.0
    assert c["test_mean_band_width_h12_pp"] > 0
    assert set(c["by_share_group"]) == {"lt_3pct", "3_to_10pct", "gt_10pct"}
    assert sum(g["n_skill_origins"] for g in c["by_share_group"].values()) == c["n_skill_origins"]
    sens = result["interval_sensitivity"]
    assert {"W36", "all_history"} <= set(sens)
    assert "Sensitivity only" in sens["note"]
    assert "set a priori" in sens["note"]


def test_insufficient_data_skill_is_excluded(result):
    assert "Rare" in result["excluded_skills_at_last_origin"]
    assert result["n_skills_total"] == 4
    assert result["n_skills_used"] == 3
    assert result["n_skill_origin_pairs"]["excluded"] == len(EARLY + TEST)  # Rare, every origin


def test_data_after_the_last_target_changes_nothing_in_the_test_evaluation():
    base = make_demand()
    changed = base.copy()
    changed.loc[(changed["month"] > "2025-04") & (changed["skill"] != "Rare"), "mentions"] = 5
    a = bt.run_backtest(base, EARLY, TEST, TREND)
    b = bt.run_backtest(changed, EARLY, TEST, TREND)
    assert a["coverage"] == b["coverage"]
    assert a["interval_sensitivity"] == b["interval_sensitivity"]
    assert a["models"] == b["models"]
    assert a["model_choice"]["model_used_at_test_origins"] == b["model_choice"]["model_used_at_test_origins"]


def test_a_test_origin_never_uses_residuals_from_after_it():
    # Evaluate ONE test origin on two data sets that differ only after the last month it may use
    # as a residual target for h=12 (the origin itself) but before its own targets.
    base = make_demand()
    changed = base.copy()
    changed.loc[(changed["month"] > "2023-11") & (changed["skill"] != "Rare"), "mentions"] = 5
    t_a = fc.build_residual_tables(base)
    t_b = fc.build_residual_tables(changed)
    for m in PRODUCTION_MODELS:
        for h in range(1, HORIZON + 1):
            assert fc.band_offsets(t_a[m], "2023-11", h) == fc.band_offsets(t_b[m], "2023-11", h)
    assert fc.choose_model(t_a, "2023-11") == fc.choose_model(t_b, "2023-11")


def test_origin_without_a_12_month_target_raises():
    with pytest.raises(ValueError):
        bt.run_backtest(make_demand(n_months=64), bt.month_range("2021-01", "2021-03"),
                        bt.month_range("2023-11", "2024-02"), bt.month_range("2021-12", "2022-01"))


def test_beats_naive_flag_follows_the_numbers():
    r = bt.run_backtest(make_demand(seed=7), EARLY, TEST, TREND)
    chosen = r["chosen_model"]
    gain_ok = r["models"]["naive"]["test_mae_pp"]["h12"] > r["models"][chosen]["test_mae_pp"]["h12"]
    assert r["beats_naive"] == (chosen != "naive" and gain_ok)


# trend label backtest

def test_trend_hit_rate_on_series_that_keep_moving(result):
    t = result["trend_label_backtest"]
    assert result["trend_label_hit_rate"] == t["trend_label_hit_rate"]
    assert t["n"] == t["n_rising"] + t["n_falling"] > 0
    assert t["n_rising"] > 0 and t["n_falling"] > 0  # "Up" and "Down" are labelled
    assert t["hit_rate_rising"] >= 0.9 and t["hit_rate_falling"] >= 0.9  # their trends continue
    assert t["n_unlabelled_under_30_mentions"] == len(TREND)  # "Rare", every origin
    assert "correlated" in t["caveat"]
    assert t["origins"] == [TREND[0], TREND[-1]]


def test_trend_hit_rate_counts_a_reversal_as_a_miss():
    # Rises for 24 months, then falls: labelled Rising at the turn, next 12 months are lower.
    n_months, n_posts = 60, 400
    up = np.concatenate([np.linspace(30, 90, 30), np.linspace(90, 20, 30)])
    months = [str(p) for p in pd.period_range("2019-01", periods=n_months, freq="M")]
    demand = pd.DataFrame({"month": months, "skill": "Turn", "mentions": np.round(up).astype(int),
                           "n_posts": n_posts})
    r = bt.trend_hit_rate(demand, ["2021-06"])  # window 2019-07..2021-06 rising, then falling
    assert r["n_rising"] == 1 and r["n_falling"] == 0
    assert r["trend_label_hit_rate"] == 0.0
