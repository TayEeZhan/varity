"""Honest test: does the pooled ML forecaster beat naive3 at the 12-month horizon?

Run: python -m engine.ml_backtest      (writes data/ml_backtest.json, prints a summary)

Method (same rolling-origin idea as engine/backtest.py)
1. Origins: EARLY 2021-12..2023-10 and TEST 2023-11..2025-10. Every origin has a full
   12-month target in the data (the last target is 2026-10, the last month).
2. At each origin t the model is retrained from scratch on all eligible (skill, origin s)
   pairs with target month s+12 <= t. Then it predicts h=12 for every eligible skill at t
   (same eligibility rule as production: mean mentions >= 5 over the last 12 months).
   Retraining runs at EVERY origin (it takes seconds, so no 3-origin shortcut is needed).
   With fewer than 100 training rows (the first few EARLY origins) there is no model and
   the prediction is naive3.
3. Metric: share-scale absolute error in percentage points (pp) between inv_logit(actual)
   and inv_logit(forecast), at h=12, on the SAME skill-origin pairs for ML, naive3, naive.
4. Gain = naive3 error - ML error (positive = ML better). The 95% interval resamples SKILLS
   (clusters), 2000 draws, seed 0, as in engine/backtest.py.
5. Hyperparameters are chosen on EARLY only: a small grid (feature set, loss, L2, leaf size)
   scored by the mean h=12 error on the 12 EARLY origins that have >= 12 training origins
   behind them (2022-11..2023-10). The choice is fixed before TEST is touched. Fixed by
   the spec: max_depth 3, learning_rate 0.05, max_iter 200.
6. Verdict: "promote" only if the lower end of the 95% interval of the TEST h=12 gain over
   naive3 is above 0. Otherwise "keep naive3".
7. Also: grouped permutation importance on the last training set, and a leak test.
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # allow "python engine/ml_backtest.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sklearn  # noqa: E402

from engine.backtest import (  # noqa: E402
    EARLY_FIRST, EARLY_LAST, N_BOOT, SEED, TEST_FIRST, TEST_LAST, _skill_bootstrap, month_range,
)
from engine.forecast import DATA_DIR, HORIZON, MIN_MEAN_MENTIONS, inv_logit, load_demand  # noqa: E402
from engine.ml_forecast import (  # noqa: E402
    CATEGORIES, FIRST_ORIGIN_IDX, MIN_TRAIN_ROWS, MLConfig, build_panel,
    feature_columns, fit_corrector, forecast_h12, load_ai_context, load_skill_info, predict_at,
)

ML_BACKTEST_JSON = DATA_DIR / "ml_backtest.json"
MATURE_MIN_TRAIN_ORIGINS = 12  # an EARLY origin is "mature" with >= 12 training origins behind it
GRID = {
    "feature_set": ("base", "gaps"),
    "loss": ("squared_error", "absolute_error"),
    "l2_regularization": (1.0, 10.0),
    "min_samples_leaf": (20, 50),
}
N_PERM_REPEATS = 20


def decide(ci_low: float) -> str:
    """"promote" only if the lower end of the 95% interval of the gain vs naive3 is > 0."""
    return "promote" if np.isfinite(ci_low) and ci_low > 0 else "keep naive3"


def share_err_pp(actual_y, forecast_y):
    return np.abs(inv_logit(actual_y) - inv_logit(forecast_y)) * 100.0


# ---------------------------------------------------------------------------
# Rolling-origin evaluation
# ---------------------------------------------------------------------------

def evaluate(panel: pd.DataFrame, origins: list[str], config: MLConfig,
             retrain_every: int = 1) -> pd.DataFrame:
    """One row per (origin, eligible skill): actual, naive, naive3 and ML forecasts (logit).

    The model used at origin t is trained with targets <= the origin where it was last
    (re)trained, which is <= t, so nothing from the future is used.
    """
    parts, fitted = [], None
    for i, origin in enumerate(origins):
        if fitted is None or i % retrain_every == 0:
            fitted = fit_corrector(panel, origin, config)
        pred = predict_at(panel, fitted, origin)
        rows = panel[(panel["origin"] == origin) & panel["eligible"]].set_index("skill")
        df = pd.DataFrame({
            "origin": origin,
            "skill": pred["skill"],
            "category": rows.loc[pred["skill"], "category"].to_numpy(),
            "y_actual": rows.loc[pred["skill"], "y_actual"].to_numpy(),
            "naive": rows.loc[pred["skill"], "y_last"].to_numpy(),
            "naive3": pred["naive3"],
            "ml": pred["pred_y"],
            "n_train_rows": fitted.n_train_rows,
            "trained": fitted.model is not None,
        })
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    if out["y_actual"].isna().any():
        raise ValueError("an origin has no 12-month target in the data")
    for name in ("naive", "naive3", "ml"):
        out[f"err_{name}"] = share_err_pp(out["y_actual"], out[name])
    return out


def _gain(df: pd.DataFrame, base: str) -> dict:
    """Mean paired gain (base error - ML error, pp) and its skill-bootstrap 95% interval."""
    diff = (df.assign(d=df[f"err_{base}"] - df["err_ml"])
            .pivot_table(index="origin", columns="skill", values="d", aggfunc="first"))
    mask = diff.notna().to_numpy()
    rng = np.random.default_rng(SEED)
    lo, hi = _skill_bootstrap(diff.to_numpy(), mask, rng)
    return {"gain_pp": round(float(df[f"err_{base}"].mean() - df["err_ml"].mean()), 4),
            "ci95_skill_bootstrap": [lo, hi]}


def summarise(df: pd.DataFrame) -> dict:
    """h=12 share-scale MAE of ML, naive3, naive on the same pairs, and the paired gains."""
    return {
        "n_skill_origin_pairs": int(len(df)),
        "n_origins": int(df["origin"].nunique()),
        "mae_pp": {m: round(float(df[f"err_{m}"].mean()), 4) for m in ("ml", "naive3", "naive")},
        "gain_vs_naive3": _gain(df, "naive3"),
        "gain_vs_naive": _gain(df, "naive"),
    }


def by_category(df: pd.DataFrame) -> dict:
    out = {}
    for cat in CATEGORIES:
        sub = df[df["category"] == cat]
        if sub.empty:
            continue
        out[cat] = {
            "n_skill_origin_pairs": int(len(sub)),
            "n_skills": int(sub["skill"].nunique()),
            "mae_pp": {m: round(float(sub[f"err_{m}"].mean()), 4) for m in ("ml", "naive3", "naive")},
            "gain_vs_naive3_pp": round(float(sub["err_naive3"].mean() - sub["err_ml"].mean()), 4),
        }
    return out


# ---------------------------------------------------------------------------
# Hyperparameter choice on EARLY only
# ---------------------------------------------------------------------------

def mature_early_origins(early: list[str], months: list[str]) -> list[str]:
    """EARLY origins with at least MATURE_MIN_TRAIN_ORIGINS training origins behind them."""
    first_idx = FIRST_ORIGIN_IDX + HORIZON + MATURE_MIN_TRAIN_ORIGINS - 1
    return [o for o in early if months.index(o) >= first_idx]


def candidate_configs() -> list[MLConfig]:
    """The pre-specified default first, then the rest of the grid in a fixed order."""
    default = MLConfig()
    grid = [MLConfig(feature_set=f, loss=lo, l2_regularization=l2, min_samples_leaf=leaf)
            for f, lo, l2, leaf in itertools.product(*GRID.values())]
    return [default] + [c for c in grid if c != default]


def tune_on_early(panel: pd.DataFrame, early: list[str], months: list[str]) -> tuple[MLConfig, list[dict]]:
    """Score every config on EARLY (mature origins) and return the best. Never touches TEST."""
    mature = mature_early_origins(early, months)
    table, best, best_mae = [], None, np.inf
    for cfg in candidate_configs():
        df = evaluate(panel, early, cfg)
        mae = float(df[df["origin"].isin(mature)]["err_ml"].mean())
        mae_all = float(df["err_ml"].mean())
        table.append({**cfg.as_dict(), "early_mature_mae_h12_pp": round(mae, 4),
                      "early_all_mae_h12_pp": round(mae_all, 4)})
        if mae < best_mae - 1e-12:  # strict: ties keep the earlier (simpler, default-first) config
            best, best_mae = cfg, mae
    return best, table


# ---------------------------------------------------------------------------
# Importance and leak test
# ---------------------------------------------------------------------------

def grouped_permutation_importance(panel: pd.DataFrame, config: MLConfig, as_of: str,
                                   n_repeats: int = N_PERM_REPEATS, seed: int = 0) -> dict:
    """Increase in share-scale MAE (pp) when a feature (or the category group) is shuffled.

    Computed on the training set of the model fitted at `as_of`, as the spec asks. It is an
    in-sample measure: it says what the model uses, not what generalises.
    """
    from engine.ml_forecast import training_rows

    fitted = fit_corrector(panel, as_of, config)
    train = training_rows(panel, as_of)
    X = train[fitted.columns].reset_index(drop=True)
    actual, base = train["y_actual"].to_numpy(), train["naive3"].to_numpy()

    def score(frame):
        return float(share_err_pp(actual, base + fitted.model.predict(frame)).mean())

    baseline = score(X)
    cat_cols = [c for c in X.columns if c.startswith("cat_")]
    groups = {c: [c] for c in X.columns if c not in cat_cols}
    if cat_cols:
        groups["category (one-hot group)"] = cat_cols
    rng = np.random.default_rng(seed)
    out = {}
    for name, cols in groups.items():
        deltas = []
        for _ in range(n_repeats):
            shuffled = X.copy()
            perm = rng.permutation(len(X))
            shuffled[cols] = X[cols].to_numpy()[perm]
            deltas.append(score(shuffled) - baseline)
        out[name] = round(float(np.mean(deltas)), 4)
    ranked = dict(sorted(out.items(), key=lambda kv: -kv[1]))
    return {
        "as_of": as_of,
        "n_train_rows": int(len(train)),
        "train_mae_pp": round(baseline, 4),
        "metric": "increase in in-sample share-scale MAE (pp) when the feature is shuffled",
        "n_repeats": n_repeats,
        "importance_pp": ranked,
        "not_in_fit": [c for c in feature_columns(config) if c not in fitted.columns],
    }


def _scramble_future(demand: pd.DataFrame, ai: pd.DataFrame, origin: str, seed: int = 1):
    """Copies of the data with every month after `origin` replaced by random valid values."""
    rng = np.random.default_rng(seed)
    d, a = demand.copy(), ai.copy()
    later = d["month"] > origin
    posts = rng.integers(100, 1000, size=int(later.sum()))
    d.loc[later, "n_posts"] = posts
    d.loc[later, "mentions"] = rng.integers(0, posts + 1)
    later_ai = a["month"] > origin
    posts_ai = rng.integers(100, 1000, size=int(later_ai.sum()))
    a.loc[later_ai, "n_posts"] = posts_ai
    a.loc[later_ai, "mentions"] = rng.integers(0, posts_ai + 1)
    return d, a


def leak_test(demand: pd.DataFrame, ai: pd.DataFrame, skill_info: pd.DataFrame,
              origins: list[str], config: MLConfig) -> dict:
    """Changing any data after the origin must not change the origin's prediction.

    Three routes must agree exactly: (A) panel built on all data, (B) data cut at the origin
    before anything is built (forecast_h12), (C) panel built on data whose later months are
    scrambled.
    """
    results = []
    for origin in origins:
        panel = build_panel(demand, ai, skill_info)
        a = predict_at(panel, fit_corrector(panel, origin, config), origin).set_index("skill")["pred_y"]
        b = pd.Series({k: v for k, v in forecast_h12(origin, config, demand, ai, skill_info).items()
                       if v is not None})
        d2, ai2 = _scramble_future(demand, ai, origin)
        panel2 = build_panel(d2, ai2, skill_info)
        c = predict_at(panel2, fit_corrector(panel2, origin, config), origin).set_index("skill")["pred_y"]
        b, c = b.reindex(a.index), c.reindex(a.index)
        diff = float(max(np.abs(a - b).max(), np.abs(a - c).max()))
        results.append({"origin": origin, "n_skills": int(len(a)), "max_abs_diff": diff,
                        "passed": bool(diff == 0.0)})
    return {"description": ("prediction at the origin: full-data panel vs data cut at the origin "
                            "vs later months scrambled; the three must be identical"),
            "origins": results, "passed": all(r["passed"] for r in results)}


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------

def run_ml_backtest(demand: pd.DataFrame, ai: pd.DataFrame, skill_info: pd.DataFrame,
                    early: list[str], test: list[str], config: MLConfig | None = None,
                    tune: bool = True, leak_origins: list[str] | None = None) -> dict:
    t0 = time.perf_counter()
    panel = build_panel(demand, ai, skill_info)
    months = sorted(demand["month"].unique())
    tuning = None
    if tune:
        config, tuning = tune_on_early(panel, early, months)
    elif config is None:
        config = MLConfig()

    early_df = evaluate(panel, early, config)
    test_df = evaluate(panel, test, config)
    mature = mature_early_origins(early, months)
    test_sum = summarise(test_df)
    ci_low = test_sum["gain_vs_naive3"]["ci95_skill_bootstrap"][0]
    verdict = decide(ci_low)

    default_cfg = MLConfig()
    default_test = None
    if config != default_cfg:
        d = evaluate(panel, test, default_cfg)
        default_test = {"note": ("pre-specified default config, shown for transparency only; the "
                                 "verdict uses the config chosen on EARLY"),
                        **summarise(d)}

    importances = grouped_permutation_importance(panel, config, test[-1])
    leak = leak_test(demand, ai, skill_info, leak_origins or [test[0], test[len(test) // 2], test[-2]],
                     config)
    fallback = sorted(early_df.loc[~early_df["trained"], "origin"].unique())

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verdict": verdict,
        "verdict_rule": ("promote only if the lower end of the 95% skill-bootstrap interval of the "
                         "TEST h=12 gain over naive3 is above 0, otherwise keep naive3"),
        "setup": {
            "model": "sklearn HistGradientBoostingRegressor, one pooled model for all skills",
            "sklearn_version": sklearn.__version__,
            "design": ("residual on naive3: target = y[t+12] - naive3_t, prediction = naive3_t + "
                       "model(features at t); y = logit((mentions + 0.5) / (n_posts + 1))"),
            "training_pairs": ("all eligible (skill, origin s) pairs with target month s+12 <= the "
                               "forecast origin t; retrained from scratch at every origin"),
            "retrain_every_n_origins": 1,
            "retrain_note": "Full retrain at every origin takes seconds, so no 3-origin shortcut was used.",
            "eligibility": f"mean mentions >= {MIN_MEAN_MENTIONS} over the last 12 months (production rule)",
            "min_train_rows": MIN_TRAIN_ROWS,
            "origins_without_a_model_early": fallback,
            "origins": {"early": [early[0], early[-1]], "test": [test[0], test[-1]],
                        "n_early": len(early), "n_test": len(test),
                        "early_mature": [mature[0], mature[-1]] if mature else None, "n_early_mature": len(mature)},
            "horizon_months": HORIZON,
            "metric": "mean absolute error on the share scale, percentage points, h=12",
            "ci_method": f"skill bootstrap (clusters), {N_BOOT} draws, seed {SEED}, as in engine/backtest.py",
            "chosen_config": config.as_dict(),
            "tuning": ("grid over feature set, loss, L2 and min leaf size, scored on EARLY mature "
                       "origins only; max_depth 3, learning_rate 0.05, max_iter 200 are fixed by spec"
                       if tune else "no tuning (config given)"),
        },
        "features": {
            "used": feature_columns(config),
            "ext_momentum": ("placeholder for the ranker momentum, NaN for now. Pass ext_momentum= "
                             "(months x skills, point-in-time) to build_panel / forecast_h12. A fully "
                             "empty column is left out of the fit; it joins when it has values."),
            "exposure_not_time_cut": ("ai_exposure and e_s come from exposure.csv (Anthropic Economic "
                                      "Index 2026-06), one value per skill used at every origin."),
        },
        "mae_table_h12_pp": {
            "early_all": summarise(early_df),
            "early_mature": summarise(early_df[early_df["origin"].isin(mature)]),
            "test": test_sum,
        },
        "test_by_category": by_category(test_df),
        "tuning_grid_early": tuning,
        "pre_specified_default_on_test": default_test,
        "feature_importance": importances,
        "leak_test": leak,
        "runtime_s": round(time.perf_counter() - t0, 1),
        "caveats": [
            "Test errors of one skill are correlated across origins, so the effective sample is much "
            "smaller than the raw count. The skill bootstrap respects this; the raw pair count does not.",
            "The pooled model has ~25 eligible skills and at most ~47 training origins. Training rows "
            "from consecutive origins overlap heavily, so the data is small and highly correlated.",
            "ai_level is nearly a time index (it rises through the whole period). The model can "
            "memorise time with it; trees cannot extrapolate beyond the range seen in training.",
            "ai_exposure and e_s (exposure.csv) are not time-cut: the same 2026-06 value is used at "
            "every origin. They are constant per skill, so they act as skill identifiers.",
            "The first EARLY origins have too few training rows for a model; they use naive3. "
            "early_mature (2022-11..2023-10) is the fair EARLY comparison.",
            "Permutation importance is computed on the training set (in-sample), as specified.",
            "The last target month (2026-10) comes from an HN thread that was still open when fetched.",
            "Production forecasting is unchanged by this experiment; a promote verdict needs review.",
        ],
    }


def print_summary(r: dict) -> None:
    print("Verity ML forecaster backtest (h=12, share-scale MAE in pp, same pairs)")
    cfg = r["setup"]["chosen_config"]
    print(f"Config chosen on EARLY: {cfg}")
    print(f"{'period':13} {'pairs':>6} | {'ML':>7} {'naive3':>7} {'naive':>7} | gain vs naive3 [95% CI]")
    for name, s in r["mae_table_h12_pp"].items():
        g = s["gain_vs_naive3"]
        m = s["mae_pp"]
        print(f"{name:13} {s['n_skill_origin_pairs']:6d} | {m['ml']:7.3f} {m['naive3']:7.3f} "
              f"{m['naive']:7.3f} | {g['gain_pp']:+.3f} {g['ci95_skill_bootstrap']}")
    g = r["mae_table_h12_pp"]["test"]["gain_vs_naive"]
    print(f"TEST gain vs naive: {g['gain_pp']:+.3f} {g['ci95_skill_bootstrap']}")
    print("TEST by category (ML / naive3 / naive):")
    for c, v in r["test_by_category"].items():
        m = v["mae_pp"]
        print(f"  {c:13} n={v['n_skill_origin_pairs']:4d}  {m['ml']:.3f} / {m['naive3']:.3f} / {m['naive']:.3f}")
    print("Top importances:", list(r["feature_importance"]["importance_pp"].items())[:8])
    print("Leak test passed:", r["leak_test"]["passed"], "| runtime", r["runtime_s"], "s")
    print("VERDICT:", r["verdict"])


def main() -> int:
    demand, ai, info = load_demand(), load_ai_context(), load_skill_info()
    result = run_ml_backtest(demand, ai, info, month_range(EARLY_FIRST, EARLY_LAST),
                             month_range(TEST_FIRST, TEST_LAST))
    ML_BACKTEST_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print_summary(result)
    print(f"Wrote {ML_BACKTEST_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
