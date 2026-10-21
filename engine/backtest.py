"""Rolling-origin backtest of the forecast models, the rolling conformal band and the trend label.

Run: python -m engine.backtest        (writes data/backtest.json, prints a summary)

Method
1. Origins: every month from 2021-12 to 2025-10. At each origin we use only data up to
   that month, forecast h = 1..12 months ahead for every skill and every model, and
   compare with what happened. The origin 2025-10 has its last target in 2026-10, the
   last month in the data.
2. Point errors: on the logit scale, error = actual - forecast. On the share scale,
   absolute error in percentage points (pp) between inv_logit(actual) and inv_logit(forecast).
   "Actual" means p = (mentions + 0.5) / (n_posts + 1) of the target month.
   All four models (naive, naive3, drift, damped) are reported, on EARLY origins
   (2021-12 to 2023-10) and TEST origins (2023-11 to 2025-10). Only naive and naive3
   are used in production. This split is for reporting only: nothing is tuned on it.
3. Model choice (production): naive or naive3, whichever has the lower mean share-scale
   |error| at h=12 over origins whose 12-month target is <= the forecast date. In the
   test evaluation this rule is applied again at every test origin (leak-free).
4. Interval: rolling, symmetric, volatility-scaled conformal band (see engine/forecast.py,
   band_offsets). Residuals are scaled by sigma, the std of first differences of the
   logit series over the 24 months up to the origin. For test origin t and horizon h,
   q = the 80th percentile of |scaled residual| over the last W=24 origins whose target
   is <= t, eligible skills only. Band = inv_logit(point +/- q * sigma_t).
   W=24 was set a priori to match the 24-month windows. It was not chosen on test data.
   W=36 and all-history are reported as sensitivity only.
5. Trend label: observed, not a forecast. At each origin from 2021-12 to 2025-10, a skill
   with a label of Rising or Falling is a hit if its pooled share (sum of mentions / sum of
   posts) over the NEXT 12 months moved in that direction compared with the LAST 12 months.
6. Minimum-data rule: at each origin, a skill with a mean of fewer than 5 mentions per
   month over the 12 months up to that origin is left out of every metric.

Known limits (also written to backtest.json)
- Test errors of one skill are correlated across origins and horizons, so the
  effective number of test points is much smaller than the raw count.
- Origins overlap, so the trend-label hit rate is built from correlated skill-origins.
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
    INTERVAL_LEVEL,
    INTERVAL_WINDOW,
    MIN_MEAN_MENTIONS,
    MODELS,
    PRODUCTION_MODELS,
    SIGMA_WINDOW,
    band_offsets,
    build_residual_tables,
    choice_scores,
    choose_model,
    earliest_as_of,
    forecast_skill,
    has_enough_data,
    inv_logit,
    load_demand,
    logit_series,
    trend_label,
    wide_tables,
)

BACKTEST_JSON = DATA_DIR / "backtest.json"
EARLY_FIRST, EARLY_LAST = "2021-12", "2023-10"
TEST_FIRST, TEST_LAST = "2023-11", "2025-10"
TREND_FIRST, TREND_LAST = "2021-12", "2025-10"
REPORT_HORIZONS = (1, 6, 12)
SHARE_GROUPS = (("lt_3pct", None, 0.03), ("3_to_10pct", 0.03, 0.10), ("gt_10pct", 0.10, None))
N_BOOT = 2000
SEED = 0
BAND_LABEL = "80% target band"
W_A_PRIORI = "W=24 set a priori to match the 24-month windows"


def month_range(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


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


def _group_masks(share: np.ndarray) -> dict[str, np.ndarray]:
    out = {}
    for name, lo, hi in SHARE_GROUPS:
        mask = np.ones(share.shape, dtype=bool)
        if lo is not None:
            mask &= share >= lo
        if hi is not None:
            mask &= share < hi
        out[name] = mask
    return out


def evaluate_bands(tables: dict, test_origins: list[str], window: int | None = INTERVAL_WINDOW,
                   fixed_model: str | None = None) -> dict:
    """Coverage and width of the rolling conformal band on the test origins.

    For every test origin t: the model is chosen with choose_model(as_of=t) (or fixed_model),
    q comes from band_offsets(as_of=t), so only residuals with target <= t are used.
    """
    inside, share, width, sigma_ok, used = [], [], [], [], []
    for origin in test_origins:
        model = fixed_model or choose_model(tables, origin)
        used.append(model)
        t = tables[model]
        i = t.origin_pos(origin)
        q = np.array([band_offsets(t, origin, h, window) for h in range(1, HORIZON + 1)])
        keep = t.eligible[i] & np.isfinite(t.sigma[i]) & np.isfinite(t.actual[i]).all(axis=1)
        point, act = t.forecast[i][keep], t.actual[i][keep]
        half = q[None, :] * t.sigma[i][keep][:, None]
        inside.append((act >= point - half) & (act <= point + half))
        width.append((inv_logit(point + half) - inv_logit(point - half)) * 100.0)
        share.append(t.share_now[i][keep])
    inside = np.concatenate(inside)
    width = np.concatenate(width)
    share = np.concatenate(share)

    cov_h = inside.mean(axis=0)
    groups = {}
    for name, mask in _group_masks(share).items():
        groups[name] = {
            "n_skill_origins": int(mask.sum()),
            "h12": round(float(inside[mask, HORIZON - 1].mean()), 4) if mask.any() else None,
            "mean_over_h": round(float(inside[mask].mean(axis=0).mean()), 4) if mask.any() else None,
            "mean_band_width_h12_pp": round(float(width[mask, HORIZON - 1].mean()), 3) if mask.any() else None,
        }
    return {
        "test_by_h": [round(float(c), 4) for c in cov_h],
        "test_mean_over_h": round(float(cov_h.mean()), 4),
        "test_h12": round(float(cov_h[HORIZON - 1]), 4),
        "by_share_group": groups,
        "mean_band_width_h12_pp": round(float(width[:, HORIZON - 1].mean()), 3),
        "n_skill_origins": int(inside.shape[0]),
        "model_used_at_test_origins": {m: used.count(m) for m in tables},
    }


def trend_hit_rate(demand: pd.DataFrame, origins: list[str]) -> dict:
    """Does a Rising / Falling label match the next 12 months?

    Pooled share = sum of mentions / sum of posts. Hit = the pooled share over the next 12
    months moved from the last 12 months in the labelled direction.
    """
    mentions, n_posts = wide_tables(demand)
    y = logit_series(demand=demand)
    months = list(y.index)
    yv, mv, pv = y.to_numpy(), mentions.to_numpy(float), n_posts.to_numpy(float)
    n_skills = yv.shape[1]
    hits = {"Rising": [], "Falling": []}
    n_none = n_unlabelled = 0
    for origin in origins:
        end = months.index(origin) + 1
        if end < 24 or end + 12 > len(months):
            raise ValueError(f"origin {origin} needs 24 months of history and 12 months ahead")
        for j in range(n_skills):
            label, _ = trend_label(yv[end - 24:end, j], mv[end - 24:end, j])
            if label is None:
                n_unlabelled += 1
            elif label == "No clear change":
                n_none += 1
            else:
                nxt = mv[end:end + 12, j].sum() / pv[end:end + 12, j].sum()
                last = mv[end - 12:end, j].sum() / pv[end - 12:end, j].sum()
                moved_up = nxt > last
                hits[label].append(moved_up if label == "Rising" else (nxt < last))
    n_up, n_down = len(hits["Rising"]), len(hits["Falling"])
    n = n_up + n_down
    all_hits = hits["Rising"] + hits["Falling"]
    return {
        "trend_label_hit_rate": round(float(np.mean(all_hits)), 4) if n else None,
        "n": n,
        "n_rising": n_up,
        "n_falling": n_down,
        "hit_rate_rising": round(float(np.mean(hits["Rising"])), 4) if n_up else None,
        "hit_rate_falling": round(float(np.mean(hits["Falling"])), 4) if n_down else None,
        "n_no_clear_change": n_none,
        "n_unlabelled_under_30_mentions": n_unlabelled,
        "origins": [origins[0], origins[-1]],
        "definition": ("Labelled skill-origins (Rising or Falling): the fraction where the pooled "
                       "share (sum mentions / sum posts) over the next 12 months moved from the last "
                       "12 months in the labelled direction."),
        "caveat": ("Consecutive origins overlap and the same skill appears at many origins, so "
                   "the skill-origins are correlated. n is not the number of independent tests."),
    }


def run_backtest(demand: pd.DataFrame, early_origins: list[str], test_origins: list[str],
                 trend_origins: list[str] | None = None, models=MODELS) -> dict:
    """Full backtest. Returns the dict that is written to backtest.json."""
    origins = early_origins + test_origins
    res = collect_forecasts(demand, origins, models)
    skills, actual, eligible = res["skills"], res["actual"], res["eligible"]
    n_early = len(early_origins)
    early_mask = eligible[:n_early]
    test_mask = eligible[n_early:]
    last_month = str(demand["month"].max())

    err_pp = {m: share_abs_error_pp(actual, res["forecasts"][m]) for m in models}

    # 1. MAE of every model (production ships only naive and naive3)
    mae = {m: {"early": _mae_by_h(err_pp[m][:n_early], early_mask),
               "test": _mae_by_h(err_pp[m][n_early:], test_mask)} for m in models}

    # 2. Rolling conformal band on the TEST origins, leak-free at every origin
    tables = build_residual_tables(demand, PRODUCTION_MODELS)
    prod = tables[PRODUCTION_MODELS[0]]
    min_as_of = earliest_as_of(prod)
    main = evaluate_bands(tables, test_origins, INTERVAL_WINDOW)
    sensitivity = {
        "W36": evaluate_bands(tables, test_origins, 36),
        "all_history": evaluate_bands(tables, test_origins, None),
        "naive3_fixed_W24": evaluate_bands(tables, test_origins, INTERVAL_WINDOW, "naive3"),
        "naive_fixed_W24": evaluate_bands(tables, test_origins, INTERVAL_WINDOW, "naive"),
    }
    for v in sensitivity.values():
        v.pop("by_share_group")
        v.pop("model_used_at_test_origins")

    # 3. Model at the forecast date (the one production uses)
    scores_now = choice_scores(tables, last_month)
    chosen = choose_model(tables, last_month)
    q_now = [round(band_offsets(tables[chosen], last_month, h), 5) for h in range(1, HORIZON + 1)]

    # 4. Does the chosen model beat naive on TEST? (paired, h=12, skills resampled)
    rng = np.random.default_rng(SEED)
    vs_naive = {}
    for m in models:
        if m == "naive":
            continue
        diff = (err_pp["naive"][n_early:, :, HORIZON - 1] - err_pp[m][n_early:, :, HORIZON - 1])
        vs_naive[m] = {
            "test_h12_mae_gain_pp": round(float(diff[test_mask].mean()), 4),
            "ci95_skill_bootstrap": _skill_bootstrap(diff, test_mask, rng),
        }
    naive_test_h12 = mae["naive"]["test"][HORIZON - 1]
    chosen_test_h12 = mae[chosen]["test"][HORIZON - 1]
    beats_naive = bool(chosen != "naive" and chosen_test_h12 < naive_test_h12)
    any_beats = [m for m in models if m != "naive" and mae[m]["test"][HORIZON - 1] < naive_test_h12]

    models_out = {m: {"early_mae_pp": _mae_row(mae[m]["early"]),
                      "test_mae_pp": _mae_row(mae[m]["test"]),
                      "in_production": m in PRODUCTION_MODELS} for m in models}
    for m in vs_naive:
        models_out[m]["test_h12_vs_naive"] = vs_naive[m]

    ever_excluded = [s for j, s in enumerate(skills) if not eligible[:, j].all()]
    last_origin_ok = [s for j, s in enumerate(skills) if eligible[-1, j]]
    never_used = [s for j, s in enumerate(skills) if not eligible[:, j].any()]

    why = (f"{chosen} has the lower mean share-scale |error| at h=12 over origins whose 12-month "
           f"target is <= {last_month}: "
           + ", ".join(f"{m} {scores_now[m] * 100:.3f} pp" for m in scores_now) + ".")
    if chosen == "naive":
        verdict = "The chosen model is naive: naive3 did not beat it. We ship naive with the rolling band."
    elif beats_naive:
        verdict = (f"On test origins {chosen} beats naive at h=12 "
                   f"({chosen_test_h12:.3f} vs {naive_test_h12:.3f} pp MAE).")
    else:
        verdict = (f"On test origins {chosen} does NOT beat naive at h=12 "
                   f"({chosen_test_h12:.3f} vs {naive_test_h12:.3f} pp MAE).")

    if trend_origins is None:
        trend_origins = month_range(TREND_FIRST, TREND_LAST)
    trend = trend_hit_rate(demand, trend_origins)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_window": {"from": str(demand["month"].min()), "to": last_month},
        "origins": {"early": [early_origins[0], early_origins[-1]],
                    "test": [test_origins[0], test_origins[-1]],
                    "n_early": len(early_origins), "n_test": len(test_origins)},
        "horizon_months": HORIZON,
        "min_mean_mentions_last_12m": MIN_MEAN_MENTIONS,
        "n_skills_total": len(skills),
        "n_skills_used": len(skills) - len(never_used),
        "n_skills_eligible_at_last_origin": len(last_origin_ok),
        "excluded_skills_at_last_origin": [s for s in skills if s not in last_origin_ok],
        "skills_excluded_at_some_origin": ever_excluded,
        "n_skill_origin_pairs": {"early": int(early_mask.sum()), "test": int(test_mask.sum()),
                                 "excluded": int((~eligible).sum())},
        "models": models_out,
        "production_models": list(PRODUCTION_MODELS),
        "dropped_from_production": [m for m in models if m not in PRODUCTION_MODELS],
        "model_choice": {
            "rule": ("naive or naive3, lowest mean share-scale |error| at h=12 over origins whose "
                     "12-month target is <= the forecast date"),
            "scores_at_forecast_date_pp": {m: round(v * 100, 4) for m, v in scores_now.items()},
            "model_used_at_test_origins": main["model_used_at_test_origins"],
        },
        "chosen_model": chosen,
        "chosen_because": why,
        "beats_naive": beats_naive,
        "models_beating_naive_on_test_h12": any_beats,
        "verdict": verdict,
        "interval": {
            "label": BAND_LABEL,
            "level": INTERVAL_LEVEL,
            "type": "rolling, symmetric, volatility-scaled conformal band",
            "scale": "logit; band = inv_logit(point +/- q_h * sigma), q_h = 80th percentile of |scaled residual|",
            "sigma": f"sample std (ddof=1) of first differences of the logit series over {SIGMA_WINDOW} months up to the origin",
            "window_origins": INTERVAL_WINDOW,
            "window_note": W_A_PRIORI,
            "earliest_supported_as_of": min_as_of,
            "q_by_h_at_forecast_date": q_now,
        },
        "coverage": {
            "label": BAND_LABEL,
            "nominal": INTERVAL_LEVEL,
            "evaluation": ("TEST origins only. At each test origin the model choice and q use only "
                           "residuals with target <= that origin."),
            "test_h12": main["test_h12"],
            "test_mean_over_h": main["test_mean_over_h"],
            "test_by_h": main["test_by_h"],
            "by_share_group": main["by_share_group"],
            "share_group_definition": "raw share over the 3 months up to the origin: <3%, 3-10%, >10%",
            "test_mean_band_width_h12_pp": main["mean_band_width_h12_pp"],
            "n_skill_origins": main["n_skill_origins"],
        },
        "interval_sensitivity": {
            "note": ("Sensitivity only, not used to choose W. " + W_A_PRIORI + ". Where fewer origins "
                     "than the window exist, all available origins are used."),
            **sensitivity,
        },
        "trend_label_hit_rate": trend["trend_label_hit_rate"],
        "trend_label_backtest": trend,
        "caveats": [
            "Test errors of one skill are correlated across origins and horizons, so the "
            "effective sample is much smaller than the raw count.",
            "The trend-label hit rate uses overlapping origins, so its skill-origins are correlated.",
            "The last target month (2026-10) comes from an HN thread that was still open "
            "when fetched.",
            "Posts per month fell from a mean of 703 (2019) to 310 (last 12 months), so "
            "recent months are noisier than early ones.",
            "exposure.csv (Anthropic Economic Index 2026-06) is not time-cut: the fast scenario "
            "uses the same exposure for every as_of.",
        ],
    }


def print_summary(r: dict) -> None:
    o = r["origins"]
    print("Verity backtest (share-scale MAE in percentage points)")
    print(f"Data {r['data_window']['from']} to {r['data_window']['to']}. "
          f"Origins: early {o['early'][0]}..{o['early'][1]} ({o['n_early']}), "
          f"test {o['test'][0]}..{o['test'][1]} ({o['n_test']}).")
    print(f"Skills used: {r['n_skills_used']} of {r['n_skills_total']}; "
          f"eligible at last origin: {r['n_skills_eligible_at_last_origin']}; "
          f"skill-origin pairs left out: {r['n_skill_origin_pairs']['excluded']}.")
    print(f"{'model':8} | {'early h1':>8} {'early h6':>8} {'early h12':>9} | "
          f"{'test h1':>7} {'test h6':>7} {'test h12':>8}")
    for m, v in r["models"].items():
        c, t = v["early_mae_pp"], v["test_mae_pp"]
        print(f"{m:8} | {c['h1']:8.3f} {c['h6']:8.3f} {c['h12']:9.3f} | "
              f"{t['h1']:7.3f} {t['h6']:7.3f} {t['h12']:8.3f}")
    print(f"Chosen model at the forecast date: {r['chosen_model']}. {r['chosen_because']}")
    print(r["verdict"])
    c = r["coverage"]
    print(f"{c['label']} coverage on test: h=12 {c['test_h12']:.1%}, mean over h {c['test_mean_over_h']:.1%}; "
          f"mean width at h=12 {c['test_mean_band_width_h12_pp']:.2f} pp.")
    for name, g in c["by_share_group"].items():
        print(f"  {name}: n={g['n_skill_origins']} h12 {g['h12']} mean {g['mean_over_h']} "
              f"width12 {g['mean_band_width_h12_pp']} pp")
    for name, s in r["interval_sensitivity"].items():
        if isinstance(s, dict):
            print(f"  sensitivity {name}: h12 {s['test_h12']:.1%}, mean {s['test_mean_over_h']:.1%}, "
                  f"width12 {s['mean_band_width_h12_pp']:.2f} pp")
    t = r["trend_label_backtest"]
    print(f"Trend label hit rate: {t['trend_label_hit_rate']:.1%} on n={t['n']} skill-origins "
          f"(rising {t['n_rising']}, falling {t['n_falling']}).")
    print(f"beats_naive = {r['beats_naive']}")


def main() -> int:
    demand = load_demand()
    result = run_backtest(demand, month_range(EARLY_FIRST, EARLY_LAST),
                          month_range(TEST_FIRST, TEST_LAST))
    BACKTEST_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print_summary(result)
    print(f"Wrote {BACKTEST_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
