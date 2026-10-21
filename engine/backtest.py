"""Rolling-origin backtest of the four forecast models, plus conformal 80% bands.

Run: python -m engine.backtest        (writes data/backtest.json, prints a summary)

Method
1. Origins: every month from 2021-12 to 2025-10 (47 origins). At each origin we use
   only data up to that month, forecast h = 1..12 months ahead for every skill and
   every model, and compare with what happened (the target month exists in the data).
   The origin 2025-10 has its last target in 2026-10, the last month in the data.
2. Errors: on the logit scale, error = actual - forecast. On the share scale,
   absolute error in percentage points (pp) between inv_logit(actual) and inv_logit(forecast).
   "Actual" means p = (mentions + 0.5) / (n_posts + 1) of the target month, the
   same scale the models are fitted on.
3. Time split. CALIBRATION origins: 2021-12 to 2023-10. TEST origins: 2023-11 to 2025-10.
   - ONE model is chosen for all skills: lowest mean share-scale MAE at h=12 on
     CALIBRATION origins. TEST data is not used to choose the model or the bands.
   - Split-conformal 80% band: for each horizon h, take the CALIBRATION residuals
     (actual - forecast, logit scale) of the chosen model, pooled over skills. The
     10th and 90th percentiles q10, q90 give the band forecast + q10 .. forecast + q90,
     mapped back with the inverse logit.
   - Coverage = fraction of TEST targets inside the band.
4. Minimum-data rule: at each origin, a skill with a mean of fewer than 5 mentions per
   month over the 12 months up to that origin is "insufficient data". Those
   skill-origin pairs are left out of every metric.

Known limits (also written to backtest.json)
- Calibration targets run until 2024-10, so some calibration residuals were not yet
  known at the first test origins. The split is by origin month, as specified.
- Test errors of one skill are correlated across origins and horizons, so the
  effective number of test points is much smaller than the raw count.
- The last target month (2026-10) comes from an HN thread that was still open when fetched.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # allow "python engine/backtest.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.forecast import (  # noqa: E402
    DATA_DIR,
    HORIZON,
    MIN_MEAN_MENTIONS,
    MODELS,
    forecast_skill,
    has_enough_data,
    inv_logit,
    load_demand,
    logit_series,
    wide_tables,
)

BACKTEST_JSON = DATA_DIR / "backtest.json"
CAL_FIRST, CAL_LAST = "2021-12", "2023-10"
TEST_FIRST, TEST_LAST = "2023-11", "2025-10"
BAND = (0.10, 0.90)  # 80% interval
REPORT_HORIZONS = (1, 6, 12)
N_BOOT = 2000
SEED = 0


def month_range(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def conformal_quantiles(residuals: np.ndarray) -> tuple[float, float]:
    """10th and 90th percentile of the residuals (actual - forecast, logit scale)."""
    q10, q90 = np.quantile(np.asarray(residuals, dtype=float), BAND)
    return float(q10), float(q90)


def coverage(actual, low, high) -> float:
    """Fraction of actual values that lie inside [low, high] (ends included)."""
    actual, low, high = (np.asarray(a, dtype=float) for a in (actual, low, high))
    return float(np.mean((actual >= low) & (actual <= high)))


def collect_forecasts(demand: pd.DataFrame, origins: list[str], models=MODELS):
    """Forecast from every origin. Returns a dict of arrays.

    forecasts[model]  shape (origins, skills, 12), logit scale
    actual            shape (origins, skills, 12), logit scale
    eligible          shape (origins, skills), False = insufficient data at that origin
    """
    mentions, _ = wide_tables(demand)
    y = logit_series(demand=demand)
    months = list(y.index)
    skills = list(y.columns)
    yv = y.to_numpy()
    mv = mentions.to_numpy()

    shape = (len(origins), len(skills), HORIZON)
    forecasts = {m: np.full(shape, np.nan) for m in models}
    actual = np.full(shape, np.nan)
    eligible = np.zeros((len(origins), len(skills)), dtype=bool)

    for i, origin in enumerate(origins):
        end = months.index(origin) + 1  # history = months[:end], nothing later
        if end + HORIZON > len(months):
            raise ValueError(f"origin {origin} has no 12-month target in the data")
        for j in range(len(skills)):
            eligible[i, j] = has_enough_data(mv[:end, j])
            if not eligible[i, j]:
                continue
            actual[i, j] = yv[end : end + HORIZON, j]
            for m in models:
                forecasts[m][i, j] = forecast_skill(yv[:end, j], m, HORIZON)
    return {"forecasts": forecasts, "actual": actual, "eligible": eligible, "skills": skills}


def share_abs_error_pp(actual_y, forecast_y):
    """Absolute error on the share scale, in percentage points."""
    return np.abs(inv_logit(actual_y) - inv_logit(forecast_y)) * 100.0


def _mae_by_h(err_pp: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Mean over eligible (origin, skill) pairs, for each horizon. err_pp: (O, S, H)."""
    return err_pp[mask].mean(axis=0)


def _mae_row(mae_h: np.ndarray) -> dict:
    row = {f"h{h}": round(float(mae_h[h - 1]), 4) for h in REPORT_HORIZONS}
    row["mean_h1_12"] = round(float(mae_h.mean()), 4)
    return row


def _skill_bootstrap(diff_pp: np.ndarray, mask: np.ndarray, rng) -> list[float]:
    """95% interval for the mean paired difference, resampling skills (clusters).

    diff_pp: (O, S) naive error minus model error at h=12. Positive = model is better.
    """
    n_s = mask.sum(axis=0).astype(float)
    sum_s = np.where(mask, diff_pp, 0.0).sum(axis=0)
    keep = n_s > 0
    n_s, sum_s = n_s[keep], sum_s[keep]
    idx = rng.integers(0, len(n_s), size=(N_BOOT, len(n_s)))
    means = sum_s[idx].sum(axis=1) / n_s[idx].sum(axis=1)
    lo, hi = np.quantile(means, [0.025, 0.975])
    return [round(float(lo), 4), round(float(hi), 4)]


def run_backtest(demand: pd.DataFrame, cal_origins: list[str], test_origins: list[str],
                 models=MODELS) -> dict:
    """Full backtest. Returns the dict that is written to backtest.json."""
    origins = cal_origins + test_origins
    res = collect_forecasts(demand, origins, models)
    skills, actual, eligible = res["skills"], res["actual"], res["eligible"]
    n_cal = len(cal_origins)
    cal_mask = eligible[:n_cal]
    test_mask = eligible[n_cal:]

    err_pp = {m: share_abs_error_pp(actual, res["forecasts"][m]) for m in models}

    # 1. MAE of every model on both splits
    mae = {m: {"calibration": _mae_by_h(err_pp[m][:n_cal], cal_mask),
               "test": _mae_by_h(err_pp[m][n_cal:], test_mask)} for m in models}

    # 2. Choose ONE model with calibration data only (mean MAE at h=12)
    chosen = min(models, key=lambda m: mae[m]["calibration"][HORIZON - 1])

    # 3. Conformal quantiles per horizon from calibration residuals (logit scale)
    resid = actual - res["forecasts"][chosen]  # (O, S, H)
    quantiles = [conformal_quantiles(resid[:n_cal][cal_mask][:, h]) for h in range(HORIZON)]
    q10 = np.array([q[0] for q in quantiles])
    q90 = np.array([q[1] for q in quantiles])

    # 4. Coverage on test origins
    low = res["forecasts"][chosen] + q10
    high = res["forecasts"][chosen] + q90
    cov_h = np.array([
        coverage(actual[n_cal:][test_mask][:, h], low[n_cal:][test_mask][:, h],
                 high[n_cal:][test_mask][:, h]) for h in range(HORIZON)
    ])
    cal_cov_h = np.array([
        coverage(actual[:n_cal][cal_mask][:, h], low[:n_cal][cal_mask][:, h],
                 high[:n_cal][cal_mask][:, h]) for h in range(HORIZON)
    ])
    # width of the band on the share scale, in pp, on test origins (so the band is useful)
    width_pp = (inv_logit(high) - inv_logit(low)) * 100.0
    mean_width_h12 = float(width_pp[n_cal:][test_mask][:, HORIZON - 1].mean())

    # 5. Does the chosen model beat naive on TEST? (paired, h=12, skills resampled)
    rng = np.random.default_rng(SEED)
    vs_naive = {}
    for m in models:
        if m == "naive":
            continue
        diff = (err_pp["naive"][n_cal:, :, HORIZON - 1] - err_pp[m][n_cal:, :, HORIZON - 1])
        vs_naive[m] = {
            "test_h12_mae_gain_pp": round(float(diff[test_mask].mean()), 4),
            "ci95_skill_bootstrap": _skill_bootstrap(diff, test_mask, rng),
        }
    naive_test_h12 = mae["naive"]["test"][HORIZON - 1]
    chosen_test_h12 = mae[chosen]["test"][HORIZON - 1]
    beats_naive = bool(chosen != "naive" and chosen_test_h12 < naive_test_h12)
    any_beats = [m for m in models if m != "naive" and mae[m]["test"][HORIZON - 1] < naive_test_h12]

    models_out = {m: {"calibration_mae_pp": _mae_row(mae[m]["calibration"]),
                      "test_mae_pp": _mae_row(mae[m]["test"])} for m in models}
    for m in vs_naive:
        models_out[m]["test_h12_vs_naive"] = vs_naive[m]

    ever_excluded = [s for j, s in enumerate(skills) if not eligible[:, j].all()]
    last_origin_ok = [s for j, s in enumerate(skills) if eligible[-1, j]]
    never_used = [s for j, s in enumerate(skills) if not eligible[:, j].any()]

    why = (f"{chosen} has the lowest mean share-scale MAE at h=12 on calibration origins "
           f"({cal_origins[0]} to {cal_origins[-1]}): "
           + ", ".join(f"{m} {mae[m]['calibration'][HORIZON - 1]:.3f} pp" for m in models) + ".")
    if chosen == "naive":
        verdict = ("The chosen model is naive, so no model beat naive on calibration. "
                   "We ship naive with conformal bands.")
    elif beats_naive:
        verdict = (f"On test origins {chosen} beats naive at h=12 "
                   f"({chosen_test_h12:.3f} vs {naive_test_h12:.3f} pp MAE).")
    else:
        verdict = (f"On test origins {chosen} does NOT beat naive at h=12 "
                   f"({chosen_test_h12:.3f} vs {naive_test_h12:.3f} pp MAE). "
                   "The calibration pick did not hold up out of sample.")

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_window": {"from": str(demand["month"].min()), "to": str(demand["month"].max())},
        "origins": {"calibration": [cal_origins[0], cal_origins[-1]],
                    "test": [test_origins[0], test_origins[-1]],
                    "n_calibration": len(cal_origins), "n_test": len(test_origins)},
        "horizon_months": HORIZON,
        "min_mean_mentions_last_12m": MIN_MEAN_MENTIONS,
        "n_skills_total": len(skills),
        "n_skills_used": len(skills) - len(never_used),
        "n_skills_eligible_at_last_origin": len(last_origin_ok),
        "excluded_skills_at_last_origin": [s for s in skills if s not in last_origin_ok],
        "skills_excluded_at_some_origin": ever_excluded,
        "n_skill_origin_pairs": {"calibration": int(cal_mask.sum()), "test": int(test_mask.sum()),
                                 "excluded": int((~eligible).sum())},
        "models": models_out,
        "chosen_model": chosen,
        "chosen_because": why,
        "beats_naive": beats_naive,
        "models_beating_naive_on_test_h12": any_beats,
        "verdict": verdict,
        "conformal": {
            "level": 0.8,
            "scale": "logit; band = forecast + q, then inverse logit",
            "q10_by_h": [round(float(q), 5) for q in q10],
            "q90_by_h": [round(float(q), 5) for q in q90],
        },
        "coverage": {
            "test_h12": round(float(cov_h[HORIZON - 1]), 4),
            "test_mean_over_h": round(float(cov_h.mean()), 4),
            "test_by_h": [round(float(c), 4) for c in cov_h],
            "calibration_h12": round(float(cal_cov_h[HORIZON - 1]), 4),
            "calibration_mean_over_h": round(float(cal_cov_h.mean()), 4),
            "test_mean_band_width_h12_pp": round(mean_width_h12, 3),
            "nominal": 0.8,
        },
        "caveats": [
            "Calibration targets run to 2024-10, so some calibration residuals were not yet "
            "known at the first test origins. The split is by origin month, as specified.",
            "Test errors of one skill are correlated across origins and horizons, so the "
            "effective sample is much smaller than the raw count.",
            "The last target month (2026-10) comes from an HN thread that was still open "
            "when fetched.",
            "Posts per month fell from a mean of 703 (2019) to 310 (last 12 months), so "
            "recent months are noisier than early ones.",
        ],
    }


def print_summary(r: dict) -> None:
    o = r["origins"]
    print("Verity backtest (share-scale MAE in percentage points)")
    print(f"Data {r['data_window']['from']} to {r['data_window']['to']}. "
          f"Origins: calibration {o['calibration'][0]}..{o['calibration'][1]} ({o['n_calibration']}), "
          f"test {o['test'][0]}..{o['test'][1]} ({o['n_test']}).")
    print(f"Skills used: {r['n_skills_used']} of {r['n_skills_total']}; "
          f"eligible at last origin: {r['n_skills_eligible_at_last_origin']}; "
          f"skill-origin pairs left out: {r['n_skill_origin_pairs']['excluded']}.")
    print(f"{'model':8} | {'cal h1':>7} {'cal h6':>7} {'cal h12':>8} | "
          f"{'test h1':>7} {'test h6':>7} {'test h12':>8}")
    for m, v in r["models"].items():
        c, t = v["calibration_mae_pp"], v["test_mae_pp"]
        print(f"{m:8} | {c['h1']:7.3f} {c['h6']:7.3f} {c['h12']:8.3f} | "
              f"{t['h1']:7.3f} {t['h6']:7.3f} {t['h12']:8.3f}")
    print(f"Chosen model (calibration only): {r['chosen_model']}")
    print(r["verdict"])
    for m, v in r["models"].items():
        if "test_h12_vs_naive" in v:
            g = v["test_h12_vs_naive"]
            print(f"  {m} vs naive, test h=12: gain {g['test_h12_mae_gain_pp']:+.3f} pp, "
                  f"95% CI (skills resampled) {g['ci95_skill_bootstrap']}")
    c = r["coverage"]
    print(f"80% band coverage on test: h=12 {c['test_h12']:.1%}, mean over h {c['test_mean_over_h']:.1%} "
          f"(calibration h=12 {c['calibration_h12']:.1%}). Mean band width at h=12: "
          f"{c['test_mean_band_width_h12_pp']:.2f} pp.")
    print(f"beats_naive = {r['beats_naive']}")


def main() -> int:
    demand = load_demand()
    result = run_backtest(demand, month_range(CAL_FIRST, CAL_LAST), month_range(TEST_FIRST, TEST_LAST))
    BACKTEST_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print_summary(result)
    print(f"Wrote {BACKTEST_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
