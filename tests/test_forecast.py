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
