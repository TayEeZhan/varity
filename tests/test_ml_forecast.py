"""Tests for engine/ml_forecast.py and engine/ml_backtest.py. Small synthetic data only,
plus two consistency checks against the real data files."""
import json

import numpy as np
import pandas as pd
import pytest

# scikit-learn is a dev-only dependency (requirements-dev.txt); skip where it is absent.
pytest.importorskip("sklearn")

from engine import forecast as fc
from engine import ml_backtest as mlb
from engine import ml_forecast as mlf
from engine.backtest import DATA_DIR

FAST = mlf.MLConfig(max_iter=30)
SKILLS = {  # skill -> (category, base mentions per 400 posts, trend per month)
    "A": ("language", 60, 0.4), "B": ("language", 90, -0.3), "C": ("framework", 50, 0.0),
    "D": ("data", 70, 0.2), "E": ("ai_ml", 40, 0.5), "Rare": ("practice", 1, 0.0),
}
N_MONTHS = 96


def make_data(seed=1):
    rng = np.random.default_rng(seed)
    months = [str(p) for p in pd.period_range("2019-01", periods=N_MONTHS, freq="M")]
    rows = []
    for skill, (_, base, trend) in SKILLS.items():
        for i, month in enumerate(months):
            m = np.clip(round(base + trend * i + rng.normal(0, 4)), 0, 400)
            rows.append({"month": month, "skill": skill, "mentions": int(m), "n_posts": 400})
    demand = pd.DataFrame(rows)
    ai = pd.DataFrame({"month": months, "mentions": np.clip(40 + 2 * np.arange(N_MONTHS), 0, 399),
                       "n_posts": 400})
    info = pd.DataFrame({"category": [v[0] for v in SKILLS.values()],
                         "ai_exposure": np.linspace(0.3, 0.7, len(SKILLS)),
                         "e_s": np.linspace(-0.02, 0.03, len(SKILLS))}, index=list(SKILLS))
    return demand, ai, info


@pytest.fixture(scope="module")
def data():
    return make_data()


@pytest.fixture(scope="module")
def panel(data):
    return mlf.build_panel(*data)


ORIGIN = "2024-06"  # month index 65


def scramble_after(demand, ai, origin, seed=7):
    d, a = mlb._scramble_future(demand, ai, origin, seed)
    return d, a


# --- feature builder: no future data -------------------------------------------------

def test_feature_builder_only_sees_history(data):
    """Features at an origin are identical when every later month is scrambled."""
    demand, ai, info = data
    d2, a2 = scramble_after(demand, ai, ORIGIN)
    p1 = mlf.build_panel(demand, ai, info)
    p2 = mlf.build_panel(d2, a2, info)
    cols = mlf.feature_columns(mlf.MLConfig(feature_set="gaps")) + ["naive3", "eligible"]
    keep1 = p1[p1["origin"] <= ORIGIN][["skill", "origin"] + cols].reset_index(drop=True)
    keep2 = p2[p2["origin"] <= ORIGIN][["skill", "origin"] + cols].reset_index(drop=True)
    pd.testing.assert_frame_equal(keep1, keep2)


def test_features_at_origin_values():
    y = np.arange(30, dtype=float)  # a perfect line, slope 1
    f = mlf.features_at_origin(y, np.full(30, 10.0), np.full(30, 100.0), np.zeros(30),
                               "2021-07", "data", 0.5, 0.01)
    assert f["y_last"] == 29 and f["y_mean3"] == 28 and f["y_mean12"] == pytest.approx(23.5)
    assert f["slope6"] == pytest.approx(1) and f["slope24"] == pytest.approx(1)
    assert f["yoy_change"] == 12 and f["month_of_year"] == 7
    assert f["share_level"] == pytest.approx(0.1)
    assert f["cat_data"] == 1.0 and f["cat_language"] == 0.0
    assert np.isnan(f[mlf.EXT_COLUMN])
    assert f["vol24"] == pytest.approx(0.0)


def test_features_need_24_months_and_known_category():
    short = np.zeros(23)
    with pytest.raises(ValueError, match="at least 24"):
        mlf.features_at_origin(short, short, short + 1, short, "2021-01", "data", 0.5, 0.0)
    ok = np.zeros(24)
    with pytest.raises(ValueError, match="unknown category"):
        mlf.features_at_origin(ok, ok, ok + 1, ok, "2021-01", "nope", 0.5, 0.0)


def test_unknown_feature_set_is_rejected():
    with pytest.raises(ValueError, match="feature_set"):
        mlf.MLConfig(feature_set="everything")


# --- training set --------------------------------------------------------------------

def test_training_rows_exclude_targets_after_the_origin(panel):
    months = list(panel.drop_duplicates("origin_idx").sort_values("origin_idx")["origin"])
    origin_idx = {m: i + mlf.FIRST_ORIGIN_IDX for i, m in enumerate(months)}
    train = mlf.training_rows(panel, ORIGIN)
    assert len(train) > 0
    assert train["target_idx"].max() <= origin_idx[ORIGIN]
    assert train["eligible"].all() and train["target_change"].notna().all()
    assert "Rare" not in set(train["skill"])  # never passes the eligibility rule
    # an earlier origin trains on fewer rows, a later one on at least as many
    assert len(mlf.training_rows(panel, "2023-06")) < len(train) <= len(mlf.training_rows(panel, "2024-12"))


def test_training_rows_unknown_origin_raises(panel):
    with pytest.raises(ValueError, match="not an origin month"):
        mlf.training_rows(panel, "2018-01")  # before the first origin


def test_fit_ignores_the_future_outcomes(data, panel):
    """Rewriting y after the origin cannot change the fitted model's predictions."""
    demand, ai, info = data
    d2, a2 = scramble_after(demand, ai, ORIGIN)
    p2 = mlf.build_panel(d2, a2, info)
    f1, f2 = mlf.fit_corrector(panel, ORIGIN, FAST), mlf.fit_corrector(p2, ORIGIN, FAST)
    r1, r2 = mlf.predict_at(panel, f1, ORIGIN), mlf.predict_at(p2, f2, ORIGIN)
    pd.testing.assert_frame_equal(r1, r2)
    assert f1.n_train_rows == f2.n_train_rows


def test_forecast_h12_matches_full_panel_and_ignores_later_months(data, panel):
    demand, ai, info = data
    expected = mlf.predict_at(panel, mlf.fit_corrector(panel, ORIGIN, FAST), ORIGIN)
    out = mlf.forecast_h12(ORIGIN, FAST, demand, ai, info)
    assert out["Rare"] is None
    for _, row in expected.iterrows():
        assert out[row["skill"]] == row["pred_y"]  # exactly equal
    d2, a2 = scramble_after(demand, ai, ORIGIN)
    assert mlf.forecast_h12(ORIGIN, FAST, d2, a2, info) == out


# --- determinism and prediction = naive3 + correction -----------------------------------

def test_fixed_seed_gives_identical_results(panel):
    a = mlf.predict_at(panel, mlf.fit_corrector(panel, ORIGIN, FAST), ORIGIN)
    b = mlf.predict_at(panel, mlf.fit_corrector(panel, ORIGIN, FAST), ORIGIN)
    pd.testing.assert_frame_equal(a, b)


def test_prediction_is_naive3_plus_correction(data, panel):
    demand, _, _ = data
    fitted = mlf.fit_corrector(panel, ORIGIN, FAST)
    assert fitted.model is not None
    pred = mlf.predict_at(panel, fitted, ORIGIN)
    assert (pred["pred_y"] == pred["naive3"] + pred["correction"]).all()
    assert pred["correction"].abs().max() > 0  # the model really adds something
    # naive3 equals the production naive3 forecast on the same history
    y = fc.logit_series(ORIGIN, demand)
    for _, row in pred.iterrows():
        assert row["naive3"] == pytest.approx(fc.forecast_skill(y[row["skill"]].to_numpy(), "naive3")[0])


def test_too_little_training_data_falls_back_to_naive3(panel):
    fitted = mlf.fit_corrector(panel, "2021-12", FAST)  # one training origin only
    assert fitted.model is None and fitted.n_train_rows < mlf.MIN_TRAIN_ROWS
    pred = mlf.predict_at(panel, fitted, "2021-12")
    assert (pred["correction"] == 0).all()
    assert (pred["pred_y"] == pred["naive3"]).all()


# --- ext_momentum placeholder ----------------------------------------------------------

def test_ext_momentum_is_nan_by_default_and_the_fit_still_works(panel):
    assert panel[mlf.EXT_COLUMN].isna().all()
    fitted = mlf.fit_corrector(panel, ORIGIN, FAST)
    assert mlf.EXT_COLUMN not in fitted.columns  # a fully empty column is left out of the fit
    assert np.isfinite(mlf.predict_at(panel, fitted, ORIGIN)["pred_y"]).all()


def test_ext_momentum_joins_the_fit_once_it_has_values(data):
    demand, ai, info = data
    months = sorted(demand["month"].unique())
    rng = np.random.default_rng(3)
    ext = pd.DataFrame(rng.normal(size=(len(months), len(SKILLS))), index=months, columns=list(SKILLS))
    ext.iloc[::5, 0] = np.nan  # some missing cells are fine
    p = mlf.build_panel(demand, ai, info, ext)
    row = p[(p["origin"] == "2022-03") & (p["skill"] == "A")].iloc[0]
    assert row[mlf.EXT_COLUMN] == ext.loc["2022-03", "A"] or np.isnan(row[mlf.EXT_COLUMN])
    fitted = mlf.fit_corrector(p, ORIGIN, FAST)
    assert mlf.EXT_COLUMN in fitted.columns
    pred = mlf.predict_at(p, fitted, ORIGIN)
    assert np.isfinite(pred["pred_y"]).all()


def test_ext_momentum_value_is_read_at_the_origin_month(data):
    demand, ai, info = data
    months = sorted(demand["month"].unique())
    ext = pd.DataFrame(np.arange(len(months) * len(SKILLS), dtype=float).reshape(len(months), -1),
                       index=months, columns=list(SKILLS))
    p = mlf.build_panel(demand, ai, info, ext)
    row = p[(p["origin"] == "2022-03") & (p["skill"] == "C")].iloc[0]
    assert row[mlf.EXT_COLUMN] == ext.loc["2022-03", "C"]


# --- verdict logic ----------------------------------------------------------------------

@pytest.mark.parametrize("ci_low,expected", [
    (0.0001, "promote"), (0.5, "promote"), (0.0, "keep naive3"), (-0.2, "keep naive3"),
    (float("nan"), "keep naive3"),
])
def test_verdict_rule(ci_low, expected):
    assert mlb.decide(ci_low) == expected


def _fake_eval(ml_better_by):
    rng = np.random.default_rng(0)
    rows = []
    for o in ["2024-01", "2024-02", "2024-03"]:
        for s in "ABCDEFGH":
            e3 = rng.uniform(1, 3)
            rows.append({"origin": o, "skill": s, "err_naive3": e3, "err_naive": e3 + 0.1,
                         "err_ml": e3 - ml_better_by})
    return pd.DataFrame(rows)


def test_summarise_gain_sign_and_ci():
    better = mlb.summarise(_fake_eval(0.5))
    assert better["gain_vs_naive3"]["gain_pp"] == pytest.approx(0.5, abs=1e-4)
    lo, hi = better["gain_vs_naive3"]["ci95_skill_bootstrap"]
    assert lo == pytest.approx(0.5, abs=1e-3) and mlb.decide(lo) == "promote"
    worse = mlb.summarise(_fake_eval(-0.5))
    assert worse["gain_vs_naive3"]["gain_pp"] < 0
    assert mlb.decide(worse["gain_vs_naive3"]["ci95_skill_bootstrap"][0]) == "keep naive3"


def test_evaluate_and_run_on_small_data(data, panel):
    demand, ai, info = data
    df = mlb.evaluate(panel, ["2024-01", "2024-02", "2024-03"], FAST)
    assert set(df["skill"]) == {"A", "B", "C", "D", "E"}
    assert len(df) == 15 and df["trained"].all()
    assert (df["err_ml"] >= 0).all()
    # same skill-origin pairs for all three methods, errors in percentage points
    expected = mlb.share_err_pp(df["y_actual"], df["naive3"])
    assert np.allclose(df["err_naive3"], expected)
    res = mlb.run_ml_backtest(demand, ai, info, mlb.month_range("2023-01", "2023-03"),
                              mlb.month_range("2023-11", "2023-12"), config=FAST, tune=False,
                              leak_origins=["2023-11"])
    assert res["verdict"] in ("promote", "keep naive3")
    assert res["leak_test"]["passed"]
    assert res["verdict"] == mlb.decide(res["mae_table_h12_pp"]["test"]["gain_vs_naive3"]["ci95_skill_bootstrap"][0])
    assert "ext_momentum" in res["feature_importance"]["not_in_fit"]


def test_grouped_importance_names_a_feature_the_model_really_uses(panel):
    imp = mlb.grouped_permutation_importance(panel, FAST, ORIGIN, n_repeats=3)
    assert "category (one-hot group)" in imp["importance_pp"]
    assert max(imp["importance_pp"].values()) > 0


def test_candidate_grid_starts_with_the_default_and_has_no_duplicates():
    cands = mlb.candidate_configs()
    assert cands[0] == mlf.MLConfig()
    assert len(set(cands)) == len(cands) == 16
    assert all(c.max_depth == 3 and c.learning_rate == 0.05 and c.max_iter == 200 for c in cands)


# --- consistency with the real data and the written results -------------------------------------

def test_real_data_naive3_matches_production_backtest():
    """The panel's naive3 error on TEST must equal the number in data/backtest.json."""
    demand, ai, info = fc.load_demand(), mlf.load_ai_context(), mlf.load_skill_info()
    p = mlf.build_panel(demand, ai, info)
    test = mlb.month_range(mlb.TEST_FIRST, mlb.TEST_LAST)
    sel = p[p["origin"].isin(test) & p["eligible"]]
    err = mlb.share_err_pp(sel["y_actual"], sel["naive3"]).mean()
    prod = json.loads((DATA_DIR / "backtest.json").read_text(encoding="utf-8"))
    assert len(sel) == prod["n_skill_origin_pairs"]["test"]
    assert err == pytest.approx(prod["models"]["naive3"]["test_mae_pp"]["h12"], abs=1e-4)


def test_written_results_follow_the_verdict_rule():
    path = DATA_DIR / "ml_backtest.json"
    if not path.exists():
        pytest.skip("run python -m engine.ml_backtest first")
    r = json.loads(path.read_text(encoding="utf-8"))
    lo = r["mae_table_h12_pp"]["test"]["gain_vs_naive3"]["ci95_skill_bootstrap"][0]
    assert r["verdict"] == mlb.decide(lo)
    assert r["leak_test"]["passed"]
    assert r["setup"]["origins"]["test"] == [mlb.TEST_FIRST, mlb.TEST_LAST]
