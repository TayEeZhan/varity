"""Tests for engine/backtest.py. Small synthetic series only."""

import numpy as np
import pandas as pd
import pytest

from engine import backtest as bt
from engine.forecast import HORIZON, MODELS


def make_demand(n_months=72, start="2019-01", seed=1):
    """Four skills with noise. 'Rare' never has enough mentions."""
    rng = np.random.default_rng(seed)
    months = [str(p) for p in pd.period_range(start, periods=n_months, freq="M")]
    n_posts = 400
    series = {
        "Up": 40 + 0.5 * np.arange(n_months) + rng.normal(0, 3, n_months),
        "Flat": 60 + rng.normal(0, 4, n_months),
        "Down": 90 - 0.4 * np.arange(n_months) + rng.normal(0, 3, n_months),
        "Rare": np.ones(n_months),
    }
    rows = []
    for skill, values in series.items():
        for month, m in zip(months, np.clip(np.round(values), 0, n_posts)):
            rows.append({"month": month, "skill": skill, "mentions": int(m), "n_posts": n_posts})
    return pd.DataFrame(rows)


CAL = bt.month_range("2022-01", "2022-06")
TEST = bt.month_range("2022-07", "2022-12")


@pytest.fixture(scope="module")
def result():
    return bt.run_backtest(make_demand(), CAL, TEST)


def test_month_range_is_inclusive():
    assert bt.month_range("2021-11", "2022-02") == ["2021-11", "2021-12", "2022-01", "2022-02"]
    assert len(bt.month_range(bt.CAL_FIRST, bt.CAL_LAST)) == 23
    assert len(bt.month_range(bt.TEST_FIRST, bt.TEST_LAST)) == 24


def test_coverage_on_a_toy_case():
    actual = [1, 2, 3, 4]
    low = [0, 0, 0, 5]
    high = [2, 2, 2, 6]
    assert bt.coverage(actual, low, high) == 0.5
    assert bt.coverage([1.0], [1.0], [1.0]) == 1.0  # band ends count as inside


def test_conformal_quantiles_are_the_10th_and_90th_percentiles():
    resid = np.arange(-50, 51, dtype=float)  # -50 .. 50
    q10, q90 = bt.conformal_quantiles(resid)
    assert q10 == pytest.approx(-40.0)
    assert q90 == pytest.approx(40.0)


def test_share_error_is_in_percentage_points():
    # logit(0.5) = 0, logit(0.6) differs by 10 pp on the share scale
    err = bt.share_abs_error_pp(np.log(0.6 / 0.4), 0.0)
    assert err == pytest.approx(10.0)


def test_result_has_the_required_fields(result):
    for key in ("models", "chosen_model", "chosen_because", "beats_naive", "conformal",
                "coverage", "n_skills_used", "origins", "excluded_skills_at_last_origin",
                "generated_at"):
        assert key in result
    assert set(result["models"]) == set(MODELS)
    for m in MODELS:
        for split in ("calibration_mae_pp", "test_mae_pp"):
            assert {"h1", "h6", "h12"} <= set(result["models"][m][split])
    assert len(result["conformal"]["q10_by_h"]) == HORIZON
    assert len(result["conformal"]["q90_by_h"]) == HORIZON


def test_chosen_model_has_lowest_calibration_mae_at_h12(result):
    cal12 = {m: result["models"][m]["calibration_mae_pp"]["h12"] for m in MODELS}
    assert cal12[result["chosen_model"]] == min(cal12.values())


def test_band_contains_the_point_forecast(result):
    q10 = np.array(result["conformal"]["q10_by_h"])
    q90 = np.array(result["conformal"]["q90_by_h"])
    assert (q10 <= q90).all()
    assert (q10 < 0).all() and (q90 > 0).all()


def test_calibration_coverage_is_about_80_percent(result):
    assert result["coverage"]["calibration_mean_over_h"] == pytest.approx(0.8, abs=0.06)
    assert 0.0 <= result["coverage"]["test_h12"] <= 1.0
    assert 0.0 <= result["coverage"]["test_mean_over_h"] <= 1.0


def test_insufficient_data_skill_is_excluded(result):
    assert "Rare" in result["excluded_skills_at_last_origin"]
    assert result["n_skills_total"] == 4
    assert result["n_skills_used"] == 3
    assert result["n_skill_origin_pairs"]["excluded"] == len(CAL + TEST)  # Rare, every origin


def test_test_data_does_not_change_model_choice_or_quantiles():
    base = make_demand()
    changed = base.copy()
    # months after the last calibration target (2022-06 + 12 = 2023-06)
    late = changed["month"] > "2023-06"
    changed.loc[late & (changed["skill"] != "Rare"), "mentions"] = 5
    a = bt.run_backtest(base, CAL, TEST)
    b = bt.run_backtest(changed, CAL, TEST)
    assert a["chosen_model"] == b["chosen_model"]
    assert a["conformal"] == b["conformal"]
    assert a["models"]["naive"]["calibration_mae_pp"] == b["models"]["naive"]["calibration_mae_pp"]
    assert a["models"]["naive"]["test_mae_pp"] != b["models"]["naive"]["test_mae_pp"]


def test_origin_without_a_12_month_target_raises():
    with pytest.raises(ValueError):
        bt.run_backtest(make_demand(n_months=40), bt.month_range("2021-01", "2021-03"),
                        bt.month_range("2022-01", "2022-02"))


def test_beats_naive_flag_is_false_when_chosen_model_is_naive():
    # A random walk with no trend: whichever model is chosen, the flag must follow the numbers.
    r = bt.run_backtest(make_demand(seed=7), CAL, TEST)
    chosen = r["chosen_model"]
    gain_ok = r["models"]["naive"]["test_mae_pp"]["h12"] > r["models"][chosen]["test_mae_pp"]["h12"]
    assert r["beats_naive"] == (chosen != "naive" and gain_ok)
