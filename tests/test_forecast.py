"""Tests for engine/forecast.py. Small synthetic series only."""

import numpy as np
import pandas as pd
import pytest

from engine import forecast as fc


def make_demand(n_months=48, mentions_by_skill=None, n_posts=300, start="2020-01"):
    """Synthetic demand table with the same columns as data/demand_monthly.csv."""
    months = [str(p) for p in pd.period_range(start, periods=n_months, freq="M")]
    mentions_by_skill = mentions_by_skill or {
        "A": [30 + (i % 5) for i in range(n_months)],
        "B": [60 + i for i in range(n_months)],
        "Rare": [1] * n_months,
    }
    rows = []
    for skill, values in mentions_by_skill.items():
        for month, m in zip(months, values):
            rows.append({"month": month, "skill": skill, "mentions": m, "n_posts": n_posts})
    return pd.DataFrame(rows)


# logit and share

def test_logit_inverse_round_trip():
    p = np.array([0.001, 0.05, 0.3, 0.5, 0.97])
    np.testing.assert_allclose(fc.inv_logit(fc.logit(p)), p)


def test_logit_of_half_is_zero():
    assert fc.logit(0.5) == 0.0


def test_smoothed_share_is_never_zero_or_one():
    p = fc.smoothed_share([0, 300], [300, 300])
    assert 0 < p[0] < p[1] < 1
    assert np.isfinite(fc.logit(p)).all()


def test_smoothed_share_formula():
    assert fc.smoothed_share(9.5, 99) == pytest.approx(0.1)


# models

def test_naive_forecast_equals_last_value():
    y = np.array([0.1, 0.5, -0.3, 0.8])
    out = fc.forecast_skill(y, "naive")
    assert out.shape == (12,)
    assert (out == 0.8).all()


def test_naive3_is_mean_of_last_three():
    y = np.array([9.0, 1.0, 2.0, 3.0])
    out = fc.forecast_skill(y, "naive3", horizon=5)
    assert out.shape == (5,)
    assert (out == 2.0).all()


def test_drift_extends_a_straight_line_with_shrunk_slope():
    t = np.arange(30)
    y = 1.0 + 0.1 * t
    out = fc.forecast_skill(y, "drift")
    expected = y[-1] + 0.5 * 0.1 * np.arange(1, 13)
    np.testing.assert_allclose(out, expected)


def test_drift_slope_uses_only_last_24_months():
    y = np.concatenate([np.linspace(10, 0, 40), np.full(24, 2.0)])  # flat at the end
    out = fc.forecast_skill(y, "drift")
    np.testing.assert_allclose(out, 2.0, atol=1e-9)


def test_damped_is_finite_and_flat_on_a_constant_series():
    out = fc.forecast_skill(np.full(40, -2.0), "damped")
    assert out.shape == (12,)
    np.testing.assert_allclose(out, -2.0, atol=1e-3)


def test_damped_follows_a_rising_series_up():
    y = np.linspace(-3, -2, 40)
    out = fc.forecast_skill(y, "damped")
    assert out[0] > y[-1] - 0.05
    assert out[-1] > out[0]


def test_unknown_model_and_empty_series_raise():
    with pytest.raises(ValueError):
        fc.forecast_skill([1.0, 2.0], "magic")
    with pytest.raises(ValueError):
        fc.forecast_skill([], "naive")


# as_of

def test_load_demand_cuts_at_as_of(tmp_path):
    path = tmp_path / "d.csv"
    make_demand().to_csv(path, index=False)
    cut = fc.load_demand("2020-06", path=path)
    assert cut["month"].max() == "2020-06"
    assert cut["month"].min() == "2020-01"


@pytest.mark.parametrize("bad", ["2020-6", "202006", "2020-13", "June 2020"])
def test_bad_as_of_format_is_rejected(bad):
    with pytest.raises(ValueError):
        fc.logit_series(bad, demand=make_demand())


def test_as_of_before_data_raises(tmp_path):
    path = tmp_path / "d.csv"
    make_demand().to_csv(path, index=False)
    with pytest.raises(ValueError):
        fc.load_demand("2019-01", path=path)


@pytest.mark.parametrize("model", fc.MODELS)
def test_as_of_never_uses_later_data(model):
    base = make_demand()
    changed = base.copy()
    late = changed["month"] > "2022-06"
    changed.loc[late, "mentions"] = 250  # a very different future
    a = fc.forecast_all(model, as_of="2022-06", demand=base)
    b = fc.forecast_all(model, as_of="2022-06", demand=changed)
    assert a.keys() == b.keys()
    for skill in a:
        if a[skill] is None:
            assert b[skill] is None
        else:
            np.testing.assert_array_equal(a[skill], b[skill])


def test_later_as_of_does_see_the_change():
    base = make_demand()
    changed = base.copy()
    changed.loc[changed["month"] > "2022-06", "mentions"] = 250
    a = fc.forecast_all("naive", as_of="2023-06", demand=base)
    b = fc.forecast_all("naive", as_of="2023-06", demand=changed)
    assert not np.allclose(a["A"], b["A"])


def test_wide_tables_rejects_gap_in_months():
    d = make_demand()
    d = d[d["month"] != "2020-05"]
    with pytest.raises(ValueError):
        fc.wide_tables(d)


# minimum-data rule

def test_has_enough_data_threshold_is_mean_5_over_last_12_months():
    assert fc.has_enough_data([5] * 12)
    assert not fc.has_enough_data([4.9] * 12)
    # only the last 12 months count
    assert not fc.has_enough_data([100] * 20 + [1] * 12)
    assert fc.has_enough_data([0] * 20 + [5] * 12)
    assert not fc.has_enough_data([])


def test_forecast_all_hides_skills_with_too_little_data():
    out = fc.forecast_all("naive", demand=make_demand())
    assert out["Rare"] is None
    assert out["A"] is not None and out["A"].shape == (12,)


# ---------------------------------------------------------------------------
# v2: volatility, statuses, rolling conformal band, model choice, trend label
# ---------------------------------------------------------------------------

def make_noisy_demand(n_months=96, seed=3, n_posts=400):
    """Four skills with noise and different shapes. 'Rare' never has enough mentions."""
    rng = np.random.default_rng(seed)
    t = np.arange(n_months)
    series = {
        "Up": 40 + 0.5 * t + rng.normal(0, 4, n_months),
        "Flat": 60 + rng.normal(0, 5, n_months),
        "Down": 110 - 0.6 * t + rng.normal(0, 4, n_months),
        "Rare": np.ones(n_months),
    }
    months = [str(p) for p in pd.period_range("2019-01", periods=n_months, freq="M")]
    rows = []
    for skill, values in series.items():
        for month, m in zip(months, np.clip(np.round(values), 0, n_posts)):
            rows.append({"month": month, "skill": skill, "mentions": int(m), "n_posts": n_posts})
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def noisy():
    return make_noisy_demand()


@pytest.fixture(scope="module")
def tables(noisy):
    return fc.build_residual_tables(noisy)


def test_volatility_is_sample_std_of_first_differences_over_24_months():
    y = np.concatenate([np.full(10, 99.0), np.arange(24) ** 2 / 50.0])  # older months must not count
    expected = np.std(np.diff(y[-24:]), ddof=1)
    assert fc.volatility(y) == pytest.approx(expected)
    assert np.isnan(fc.volatility(np.arange(23.0)))
    assert fc.volatility(np.arange(24.0)) == pytest.approx(0.0)


def test_status_ok_low_volume_rare():
    assert fc.skill_status([5] * 12) == "ok"
    assert fc.skill_status([1] * 12 + [3] * 12) == "low_volume"  # 48 mentions, 3 per month last year
    assert fc.skill_status([1] * 24) == "rare"  # 24 mentions in 24 months
    assert fc.skill_status([0] * 18 + [5] * 6) == "low_volume"  # exactly 30
    assert fc.skill_status([0] * 18 + [4] * 6 + [0]) == "rare"  # 24 mentions in the last 24 months


def test_residual_table_shapes_and_first_origin(tables, noisy):
    t = tables["naive3"]
    assert set(tables) == set(fc.PRODUCTION_MODELS)
    assert t.origins[0] == "2020-12"  # 24 months of history are needed for sigma
    assert t.forecast.shape == (96 - 23, 4, 12)
    assert not t.eligible[:, t.skills.index("Rare")].any()
    assert np.isnan(t.actual[-1]).all()  # the last origin has no targets
    i = t.origin_pos("2022-06")
    y = fc.logit_series(demand=noisy)
    assert t.actual[i, 0, 0] == pytest.approx(y.iloc[t.months.index("2022-06") + 1, 0])


def test_earliest_supported_as_of_is_58_months_after_the_start(tables):
    t = tables["naive"]
    assert fc.earliest_as_of(t) == "2023-11"  # 2019-01 + 58 months
    assert fc.earliest_supported(t.months) == "2023-11"
    with pytest.raises(ValueError, match="2023-11"):
        fc.band_offsets(t, "2023-10", 12)
    assert fc.band_offsets(t, "2023-11", 12) > 0
    # a short horizon still needs 24 usable origins
    with pytest.raises(ValueError):
        fc.band_offsets(t, "2022-10", 1)


def test_band_offsets_is_q80_of_scaled_residuals_of_the_last_24_origins(tables):
    t = tables["naive3"]
    as_of, h = "2024-12", 6
    last = t.months.index(as_of) - h - t.first_origin
    r = np.abs(t.scaled_residuals()[last - 23:last + 1, :, h - 1][t.eligible[last - 23:last + 1]])
    assert fc.band_offsets(t, as_of, h) == pytest.approx(np.quantile(r[np.isfinite(r)], 0.8))
    # a hand-made scaled residual for one cell
    i, j = last, t.skills.index("Up")
    expected = (t.actual[i, j, h - 1] - t.forecast[i, j, h - 1]) / t.sigma[i, j]
    assert t.scaled_residuals()[i, j, h - 1] == pytest.approx(expected)


def test_band_offsets_windows_differ_and_all_history_uses_everything(tables):
    t = tables["naive3"]
    a24 = fc.band_offsets(t, "2025-06", 3)
    a36 = fc.band_offsets(t, "2025-06", 3, window=36)
    aall = fc.band_offsets(t, "2025-06", 3, window=None)
    assert len({a24, a36, aall}) == 3
    # with exactly 24 usable origins all-history equals W=24
    assert fc.band_offsets(t, "2023-11", 12, window=None) == fc.band_offsets(t, "2023-11", 12)


def test_band_is_symmetric_on_the_logit_scale(tables):
    q = fc.band_offsets(tables["naive"], "2024-06", 12)
    point, sigma = -2.0, 0.3
    low, high = point - q * sigma, point + q * sigma
    assert (point - low) == pytest.approx(high - point)


def _changed_after(demand, cutoff):
    changed = demand.copy()
    late = changed["month"] > cutoff
    changed.loc[late & (changed["skill"] != "Rare"), "mentions"] = 7  # a very different future
    return changed


def test_changing_data_after_as_of_does_not_change_offsets_choice_or_points(noisy, tables):
    as_of = "2024-06"
    other = fc.build_residual_tables(_changed_after(noisy, as_of))
    for m in fc.PRODUCTION_MODELS:
        for h in range(1, 13):
            assert fc.band_offsets(tables[m], as_of, h) == fc.band_offsets(other[m], as_of, h)
    assert fc.choice_scores(tables, as_of) == fc.choice_scores(other, as_of)
    assert fc.choose_model(tables, as_of) == fc.choose_model(other, as_of)
    # point forecasts and sigma at every origin up to as_of are the same
    n = tables["naive3"].origin_pos(as_of) + 1
    for m in fc.PRODUCTION_MODELS:
        np.testing.assert_array_equal(tables[m].forecast[:n], other[m].forecast[:n])
        np.testing.assert_array_equal(tables[m].sigma[:n], other[m].sigma[:n])


def test_changing_data_before_as_of_does_change_offsets(noisy, tables):
    as_of = "2024-06"
    changed = noisy.copy()
    inside = (changed["month"] > "2023-12") & (changed["month"] <= as_of) & (changed["skill"] == "Up")
    changed.loc[inside, "mentions"] = 5  # data that is allowed to be used
    other = fc.build_residual_tables(changed)
    assert fc.band_offsets(tables["naive3"], as_of, 1) != fc.band_offsets(other["naive3"], as_of, 1)


def test_choose_model_picks_the_lower_h12_share_error_and_needs_a_target():
    # a very noisy series: naive3 smooths it, so it beats naive at h=12
    rng = np.random.default_rng(0)
    n = 96
    mentions = {"A": np.clip(np.round(80 + rng.normal(0, 25, n)), 1, 399).astype(int)}
    tabs = fc.build_residual_tables(make_demand(n, mentions, n_posts=400, start="2019-01"))
    scores = fc.choice_scores(tabs, "2026-12")
    assert fc.choose_model(tabs, "2026-12") == min(scores, key=scores.get)
    assert scores["naive3"] < scores["naive"]
    with pytest.raises(ValueError):
        fc.choose_model(tabs, "2020-12")  # no origin has a 12-month target yet


# trend label

def _y_from_shares(p):
    return fc.logit(np.asarray(p, dtype=float))


def test_trend_label_rising():
    y = _y_from_shares(np.concatenate([np.linspace(0.05, 0.06, 12), np.linspace(0.09, 0.10, 12)]))
    label, p = fc.trend_label(y, np.full(24, 20))
    assert label == "Rising" and p < 0.05


def test_trend_label_falling():
    y = _y_from_shares(np.concatenate([np.linspace(0.10, 0.09, 12), np.linspace(0.06, 0.05, 12)]))
    label, p = fc.trend_label(y, np.full(24, 20))
    assert label == "Falling" and p < 0.05


def test_trend_label_flat_noise_is_no_clear_change():
    rng = np.random.default_rng(1)
    y = _y_from_shares(0.08 + rng.normal(0, 0.003, 24) * np.tile([1, -1], 12))
    label, p = fc.trend_label(y, np.full(24, 20))
    assert label == "No clear change" and p >= 0.05


def test_trend_label_is_none_with_too_few_mentions_or_months():
    wobble = np.tile([0.9, 1.1], 12)
    y = _y_from_shares(np.concatenate([np.full(12, 0.001), np.full(12, 0.01)]) * wobble)
    assert fc.trend_label(y, np.ones(24)) == (None, None)  # 24 mentions < 30
    assert fc.trend_label(y, [0] * 23 + [30])[0] is not None  # exactly 30 is labelled
    assert fc.trend_label(y[:23], np.full(23, 20)) == (None, None)


def test_trend_label_uses_only_the_last_24_months_and_the_welch_test():
    from scipy import stats
    rng = np.random.default_rng(2)
    y = rng.normal(-2.5, 0.3, 40)
    y[-12:] += 0.5
    label, p = fc.trend_label(y, np.full(40, 20))
    assert p == pytest.approx(stats.ttest_ind(y[-12:], y[-24:-12], equal_var=False).pvalue)
    assert label == "Rising"


def test_trend_label_on_a_constant_series_does_not_crash():
    assert fc.trend_label(np.full(24, -3.0), np.full(24, 20)) == ("No clear change", 1.0)
