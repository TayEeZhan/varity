"""Estimate the scenario strength k from real data instead of assuming it (step 9, part B).

The fast scenario in engine/scores.py is: fast = moderate * (1 - k * e_s), with k = 2 as an
assumption. Here we ask what the Hacker News job-post data say about k.

Natural experiment: ChatGPT was released in Nov 2022.
    d_i = mean logit share of skill i over a post window  -  mean over 2021-11..2022-10
Post windows: 2023-11..2024-10, 2024-11..2025-10 and 2025-11..2026-10 (the last is the primary
one). The logit is the one the forecast uses: y = logit((mentions + 0.5) / (posts + 1)).
Regression across skills with status ok:  d_i = a + b * e_s,i   (e_s from data/exposure.csv).
The intercept a takes the change that all skills share (market, rates, HN sample). Only the
difference between more and less exposed skills identifies b.

From b to k (linearisation at the mean share)
    Scenario:  fast / moderate - 1 = -k * e.
    Data:      d logit = b * e, and  d share / share = (1 - s) * d logit  for a small change
               (derivative of the logistic function: d s / d logit = s * (1 - s)).
    So         d share / share = (1 - s_bar) * b * e, which gives
               k = -(1 - s_bar) * b,  s_bar = weighted mean pre-window share of the sample.
    A CI for b maps to a CI for k by the same linear map (the ends swap because of the minus).
    k is cumulative over the window. The scenario horizon is 12 months, so a per-12-month k
    is also reported: k_total / (years from Nov 2022 to the middle of the post window), which
    assumes the effect built up evenly. That scaling is an assumption, shown as such.

Uncertainty
    Skill-level pairs bootstrap (resample skills). It is too optimistic, because skills in one
    category share one e_s and move together.
    Cluster bootstrap (resample categories with all their skills). This is the headline CI.
    Category-level regression: one point per category (weighted mean change), with an exact
    permutation p-value, a t interval and a leave-one-category-out check. Only 5 categories have
    an "ok" skill (practice has none), so this has 3 degrees of freedom: very weak.
Checks
    Excluding the ai_ml category (its skills rise because they are AI skills, not because of how
    exposed their occupations are), a pre-trend placebo (2019-11..2020-10 to 2021-11..2022-10,
    before ChatGPT), and a control for the pre-window level (mean reversion).
Verdict: the data pin k down only if the headline cluster CI excludes 0 and every specification
(all skills / without ai_ml, every window) has the same sign. Otherwise we say so, and k = 2 stays
a labelled assumption.

Run:
    python -m engine.k_estimate      (writes data/k_estimate.json)
"""
from __future__ import annotations

import itertools
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

if __package__ in (None, ""):  # allow "python engine/k_estimate.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.forecast import (  # noqa: E402
    DATA_DIR, load_demand, logit_series, skill_status, smoothed_share, wide_tables,
)

K_JSON = DATA_DIR / "k_estimate.json"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"

PRE = ("2021-11", "2022-10")  # the 12 months before the first full year after ChatGPT
RELEASE = "2022-11"  # ChatGPT release month
POST_WINDOWS = {
    "2023-11..2024-10": ("2023-11", "2024-10"),
    "2024-11..2025-10": ("2024-11", "2025-10"),
    "2025-11..2026-10": ("2025-11", "2026-10"),
}
PRIMARY_WINDOW = "2025-11..2026-10"  # the most recent 12 months (its last month is partial)
PLACEBO = {"pre": ("2019-11", "2020-10"), "post": PRE}  # both before ChatGPT
N_BOOT = 5000
SEED = 20261022
CI_LEVEL = 0.95
K_ASSUMED = 2.0  # engine/scores.py K


# --------------------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------------------

def window_mean(y: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Mean of the monthly values over start..end (inclusive). Raises if a month is missing."""
    want = pd.period_range(start, end, freq="M").strftime("%Y-%m")
    missing = [m for m in want if m not in y.index]
    if missing:
        raise ValueError(f"window {start}..{end} is missing months {missing}")
    return y.loc[list(want)].mean()


def wls(x, y, w=None) -> tuple[float, float]:
    """Weighted least squares y = a + b x. Returns (a, b). Raises if x has no spread."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    w = np.ones_like(x) if w is None else np.asarray(w, dtype=float)
    sw = w.sum()
    if sw <= 0:
        raise ValueError("weights sum to zero")
    xm, ym = (w * x).sum() / sw, (w * y).sum() / sw
    sxx = (w * (x - xm) ** 2).sum()
    if sxx <= 1e-15:
        raise ValueError("x has no spread: the slope is not defined")
    b = (w * (x - xm) * (y - ym)).sum() / sxx
    return float(ym - b * xm), float(b)


def wls_two(x, z, y, w=None) -> tuple[float, float]:
    """y = a + b x + c z by weighted least squares. Returns (b, c)."""
    x, z, y = (np.asarray(v, dtype=float) for v in (x, z, y))
    w = np.ones_like(x) if w is None else np.asarray(w, dtype=float)
    X = np.column_stack([np.ones_like(x), x, z])
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return float(beta[1]), float(beta[2])


def percentile_ci(values, level: float = CI_LEVEL) -> tuple[float, float]:
    lo, hi = np.percentile(values, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def bootstrap_slope(x, y, w=None, clusters=None, n_boot: int = N_BOOT, seed: int = SEED
                    ) -> dict:
    """Bootstrap the WLS slope b. With `clusters` (one label per row) whole clusters are resampled,
    otherwise single rows. Resamples where x has no spread are skipped and counted.

    The same seed gives the same result (a fresh default_rng(seed) is used on every call).
    """
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    w = np.ones_like(x) if w is None else np.asarray(w, dtype=float)
    rng = np.random.default_rng(seed)
    slopes: list[float] = []
    if clusters is None:
        n = len(x)
        for _ in range(n_boot):
            idx = rng.integers(0, n, n)
            try:
                slopes.append(wls(x[idx], y[idx], w[idx])[1])
            except ValueError:
                continue
    else:
        labels = np.asarray(clusters)
        uniq = list(dict.fromkeys(labels.tolist()))
        members = {c: np.flatnonzero(labels == c) for c in uniq}
        for _ in range(n_boot):
            pick = rng.integers(0, len(uniq), len(uniq))
            idx = np.concatenate([members[uniq[i]] for i in pick])
            try:
                slopes.append(wls(x[idx], y[idx], w[idx])[1])
            except ValueError:
                continue
    if not slopes:
        return {"ci_low": None, "ci_high": None, "n_valid": 0, "n_boot": n_boot}
    lo, hi = percentile_ci(slopes)
    return {"ci_low": lo, "ci_high": hi, "n_valid": len(slopes), "n_boot": n_boot}


def k_from_b(b: float, s_bar: float) -> float:
    """k = -(1 - s_bar) * b (linearisation of the scenario formula at the mean share)."""
    return float(-(1.0 - s_bar) * b)


def k_interval(b_low: float, b_high: float, s_bar: float) -> tuple[float, float]:
    """Map a CI of b to a CI of k. The ends swap because k = -(1 - s_bar) * b."""
    return k_from_b(b_high, s_bar), k_from_b(b_low, s_bar)


def years_since_release(window: tuple[str, str]) -> float:
    """Years from the ChatGPT release month to the middle of a post window (start + 6 months)."""
    months = (pd.Period(window[0], "M") - pd.Period(RELEASE, "M")).n + 6
    return months / 12.0


def category_regression(df: pd.DataFrame) -> dict:
    """One point per category: weighted mean change d against e_s. Weak by construction."""
    g = df.groupby("category")
    cat = pd.DataFrame({
        "e_s": g["e_s"].first(),
        "d": g.apply(lambda s: np.average(s["d"], weights=s["w"]), include_groups=False),
        "w": g["w"].sum(),
    })
    n = len(cat)
    out: dict = {"n_categories": n, "points": {c: {"e_s": float(r.e_s), "d": float(r.d), "w": float(r.w)}
                                              for c, r in cat.iterrows()}}
    if n < 3 or cat["e_s"].nunique() < 3:
        out["note"] = "fewer than 3 categories: no regression"
        return out
    out["b_unweighted"] = wls(cat["e_s"], cat["d"])[1]
    out["b_weighted"] = wls(cat["e_s"], cat["d"], cat["w"])[1]
    # exact permutation p-value for the unweighted slope: all orderings of d over the categories
    obs = out["b_unweighted"]
    xs, ds = cat["e_s"].to_numpy(), cat["d"].to_numpy()
    hits = total = 0
    for perm in itertools.permutations(range(n)):
        total += 1
        hits += abs(wls(xs, ds[list(perm)])[1]) >= abs(obs) - 1e-12
    out["p_permutation_unweighted"] = hits / total
    # t interval (n - 2 degrees of freedom)
    a, b = wls(xs, ds)
    resid = ds - (a + b * xs)
    df_t = n - 2
    se = math.sqrt((resid ** 2).sum() / df_t / ((xs - xs.mean()) ** 2).sum())
    t = float(stats.t.ppf((1 + CI_LEVEL) / 2, df_t))
    out["b_unweighted_t_ci"] = [b - t * se, b + t * se]
    out["t_df"] = df_t
    # leave one category out
    loo = {}
    for c in cat.index:
        rest = cat.drop(index=c)
        try:
            loo[c] = wls(rest["e_s"], rest["d"])[1]
        except ValueError:
            loo[c] = None
    out["leave_one_category_out_b_unweighted"] = loo
    return out


# --------------------------------------------------------------------------------------
# The experiment
# --------------------------------------------------------------------------------------

def build_sample(demand: pd.DataFrame, exposure: pd.DataFrame,
                 pre: tuple[str, str], post: tuple[str, str], ok_skills: list[str]) -> pd.DataFrame:
    """One row per ok skill: category, e_s, change d in mean logit share, weight, pre share and level."""
    y = logit_series(demand=demand)
    mentions, n_posts = wide_tables(demand)
    share = pd.DataFrame(smoothed_share(mentions.to_numpy(), n_posts.to_numpy()),
                         index=mentions.index, columns=mentions.columns)
    d = window_mean(y, *post) - window_mean(y, *pre)
    weight = (mentions.loc[pre[0]:pre[1]].sum() + mentions.loc[post[0]:post[1]].sum())
    ex = exposure.set_index("skill")
    df = pd.DataFrame({
        "skill": ok_skills,
        "category": [ex.loc[s, "category"] for s in ok_skills],
        "e_s": [float(ex.loc[s, "e_s"]) for s in ok_skills],
        "d": [float(d[s]) for s in ok_skills],
        "w": [float(weight[s]) for s in ok_skills],
        "share_pre": [float(window_mean(share, *pre)[s]) for s in ok_skills],
        "level_pre": [float(window_mean(y, *pre)[s]) for s in ok_skills],
    })
    return df


def fit(df: pd.DataFrame, weighted: bool, window: tuple[str, str], n_boot: int, seed: int) -> dict:
    """Slope, CIs and implied k for one sample and one weighting."""
    w = df["w"].to_numpy() if weighted else None
    a, b = wls(df["e_s"], df["d"], w)
    wts = df["w"].to_numpy() if weighted else np.ones(len(df))
    s_bar = float((wts * df["share_pre"]).sum() / wts.sum())
    skill_ci = bootstrap_slope(df["e_s"], df["d"], w, None, n_boot, seed)
    cluster_ci = bootstrap_slope(df["e_s"], df["d"], w, df["category"], n_boot, seed)
    yrs = years_since_release(window)
    out = {
        "n_skills": int(len(df)), "n_categories": int(df["category"].nunique()),
        "weighted": weighted, "intercept_a": a, "slope_b": b, "s_bar": s_bar,
        "b_ci_skill_bootstrap": [skill_ci["ci_low"], skill_ci["ci_high"]],
        "b_ci_cluster_bootstrap": [cluster_ci["ci_low"], cluster_ci["ci_high"]],
        "cluster_bootstrap_valid_resamples": cluster_ci["n_valid"],
        "k_total": k_from_b(b, s_bar),
        "years_since_release": yrs,
        "k_per_12m": k_from_b(b, s_bar) / yrs,
    }
    for name, ci in (("skill", skill_ci), ("cluster", cluster_ci)):
        if ci["ci_low"] is not None:
            lo, hi = k_interval(ci["ci_low"], ci["ci_high"], s_bar)
            out[f"k_total_ci_{name}_bootstrap"] = [lo, hi]
            out[f"k_per_12m_ci_{name}_bootstrap"] = [lo / yrs, hi / yrs]
        else:
            out[f"k_total_ci_{name}_bootstrap"] = [None, None]
            out[f"k_per_12m_ci_{name}_bootstrap"] = [None, None]
    return out


def ci_includes_zero(ci) -> bool:
    return ci[0] is None or ci[1] is None or ci[0] <= 0.0 <= ci[1]


def verdict_from(headline_k_ci, slopes_by_spec: dict[str, float]) -> dict:
    """The data pin k down only if the headline CI excludes 0 and all specifications share a sign."""
    signs = {np.sign(b) for b in slopes_by_spec.values() if b is not None and b != 0}
    same_sign = len(signs) <= 1
    excludes_zero = not ci_includes_zero(headline_k_ci)
    pinned = bool(excludes_zero and same_sign)
    reasons = []
    if not excludes_zero:
        reasons.append("the headline 95% CI includes 0")
    if not same_sign:
        reasons.append("the sign of the slope changes between specifications")
    return {"pins_k_down": pinned, "ci_excludes_zero": excludes_zero,
            "same_sign_in_all_specs": same_sign, "reasons": reasons,
            "verdict": ("The data pin k down." if pinned else
                        "The data cannot pin k down: " + " and ".join(reasons) + ". "
                        "k = 2 stays a labelled assumption.")}


def estimate(demand: pd.DataFrame | None = None, exposure: pd.DataFrame | None = None,
             n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    demand = load_demand() if demand is None else demand
    exposure = pd.read_csv(EXPOSURE_CSV) if exposure is None else exposure
    mentions, _ = wide_tables(demand)
    last_month = mentions.index[-1]
    ok = [s for s in mentions.columns if skill_status(mentions[s].to_numpy()) == "ok"]

    results: dict = {}
    for name, window in POST_WINDOWS.items():
        df = build_sample(demand, exposure, PRE, window, ok)
        no_ai = df[df["category"] != "ai_ml"]
        no_llm = df[df["skill"] != "LLM / GenAI"]
        block = {
            "all_ok_skills": {"weighted": fit(df, True, window, n_boot, seed),
                              "unweighted": fit(df, False, window, n_boot, seed)},
            "excluding_ai_ml": {"weighted": fit(no_ai, True, window, n_boot, seed),
                                "unweighted": fit(no_ai, False, window, n_boot, seed)},
            "excluding_llm_genai_only": {"weighted": fit(no_llm, True, window, n_boot, seed)},
            "category_level_all": category_regression(df),
            "category_level_excluding_ai_ml": category_regression(no_ai),
        }
        b_ctrl, c_ctrl = wls_two(df["e_s"], df["level_pre"], df["d"], df["w"])
        block["control_for_pre_level_weighted"] = {"b_exposure": b_ctrl, "c_pre_level": c_ctrl}
        results[name] = block

    placebo_df = build_sample(demand, exposure, PLACEBO["pre"], PLACEBO["post"], ok)
    # the placebo "window" ends before ChatGPT: do not scale by years since release
    placebo = {
        "pre": list(PLACEBO["pre"]), "post": list(PLACEBO["post"]),
        "all_ok_skills_weighted": _placebo_fit(placebo_df, n_boot, seed),
        "excluding_ai_ml_weighted": _placebo_fit(placebo_df[placebo_df["category"] != "ai_ml"], n_boot, seed),
        "note": ("Both windows are before ChatGPT (2019 to 2022, includes the COVID hiring swing). "
                 "A slope here of similar size means the pattern is an older trend, not an AI effect."),
    }

    head = results[PRIMARY_WINDOW]["all_ok_skills"]["weighted"]
    head_k_ci = head["k_total_ci_cluster_bootstrap"]
    slopes = {}
    for wname, block in results.items():
        slopes[f"{wname} all weighted"] = block["all_ok_skills"]["weighted"]["slope_b"]
        slopes[f"{wname} all unweighted"] = block["all_ok_skills"]["unweighted"]["slope_b"]
        slopes[f"{wname} excl ai_ml weighted"] = block["excluding_ai_ml"]["weighted"]["slope_b"]
        slopes[f"{wname} excl ai_ml unweighted"] = block["excluding_ai_ml"]["unweighted"]["slope_b"]
    verdict = verdict_from(head_k_ci, slopes)

    return {
        "generated_by": "engine/k_estimate.py",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assumed_k_in_production": K_ASSUMED,
        "method": {
            "design": ("Natural experiment: change in mean logit share from the 12 months before "
                       f"{PRE[0]}..{PRE[1]} to each post window, regressed on e_s across skills with "
                       "status ok: d = a + b * e_s."),
            "transform": "y = logit((mentions + 0.5) / (posts + 1)), the same series the forecast uses",
            "weights": "mentions in the pre and post windows together (and an unweighted fit)",
            "pre_window": list(PRE), "post_windows": {k: list(v) for k, v in POST_WINDOWS.items()},
            "primary_window": PRIMARY_WINDOW,
            "last_data_month": last_month,
            "primary_window_note": "The last month (2026-10) was still open when fetched, so it is partial.",
            "skills_used": ok, "n_skills_ok": len(ok),
            "linearisation": {
                "scenario": "fast/moderate - 1 = -k * e",
                "data": "d share / share = (1 - s_bar) * d logit = (1 - s_bar) * b * e",
                "result": "k = -(1 - s_bar) * b; a CI of b maps to a CI of k by the same linear map (ends swap)",
                "per_12m": ("k_per_12m = k_total / years from 2022-11 to the middle of the post window; "
                            "assumes the effect built up evenly. The scenario horizon is 12 months."),
            },
            "ci": (f"{int(CI_LEVEL * 100)}% percentile bootstrap, {n_boot} resamples, seed {seed}. "
                   "Headline = cluster bootstrap (categories resampled); skill-level bootstrap is "
                   "reported but ignores that skills in one category share e_s."),
            "category_level": ("5 points only: category 'practice' has no ok skill. Weighted mean change "
                               "per category against its e_s; exact permutation p-value; t interval with "
                               "n - 2 = 3 degrees of freedom."),
        },
        "results": results,
        "placebo_pre_trend": placebo,
        "headline": {
            "window": PRIMARY_WINDOW, "sample": "all ok skills", "weighting": "mentions",
            "b": head["slope_b"], "b_ci_cluster_bootstrap": head["b_ci_cluster_bootstrap"],
            "b_ci_skill_bootstrap": head["b_ci_skill_bootstrap"],
            "k_total": head["k_total"], "k_total_ci_cluster_bootstrap": head["k_total_ci_cluster_bootstrap"],
            "k_total_ci_skill_bootstrap": head["k_total_ci_skill_bootstrap"],
            "k_per_12m": head["k_per_12m"], "k_per_12m_ci_cluster_bootstrap": head["k_per_12m_ci_cluster_bootstrap"],
            "k_per_12m_ci_skill_bootstrap": head["k_per_12m_ci_skill_bootstrap"],
            "s_bar": head["s_bar"],
            "k_assumed": K_ASSUMED,
            "assumed_k_inside_total_cluster_ci": _inside(K_ASSUMED, head["k_total_ci_cluster_bootstrap"]),
            "assumed_k_inside_per_12m_cluster_ci": _inside(K_ASSUMED, head["k_per_12m_ci_cluster_bootstrap"]),
        },
        "slopes_by_specification": slopes,
        "verdict": verdict,
        "caveats": [
            "Confounders: the 2023 tech layoffs, interest-rate rises, and shifts in who posts on Hacker News "
            "(posts per month fell from about 700 in 2019 to about 310) all hit tech skills at the same time.",
            "e_s has only 6 distinct values (one per category) and only 5 categories have an ok skill, so "
            "40 skills carry 5 independent points. The cluster bootstrap and the category-level fit show this.",
            "The ai_ml skills (LLM / GenAI, RAG, Machine Learning, PyTorch) rose because they are AI skills. "
            "ai_ml also has the lowest e_s, so it can create a negative slope by itself. See excluding_ai_ml.",
            "e_s is built from AEI 2026-06 usage and is not time-cut: it is the same for every window.",
            "Categories are coarse: all languages share one e_s.",
            "k is cumulative over the window; the per-12-month version assumes an even build-up.",
            "The most recent window includes the partial month 2026-10.",
            "This is an association across skills, not proof that AI exposure caused the change.",
        ],
    }


def k_line(k_est: dict) -> str:
    """The one-line statement for the Method tab, built from data/k_estimate.json."""
    head = k_est.get("headline") or {}
    assumed = k_est.get("assumed_k_in_production", K_ASSUMED)
    ci = head.get("k_per_12m_ci_cluster_bootstrap") or [None, None]
    have = all(isinstance(v, (int, float)) for v in (head.get("k_per_12m"), ci[0], ci[1]))
    if (k_est.get("verdict") or {}).get("pins_k_down") and have:
        return (f"Data-implied k: {head['k_per_12m']:.1f} (95% CI {ci[0]:.1f} to {ci[1]:.1f}); "
                f"we use k = {assumed:g} as a labelled assumption.")
    if have:
        return (f"The data cannot pin k down (point estimate {head['k_per_12m']:.1f} per 12 months, "
                f"95% CI {ci[0]:.1f} to {ci[1]:.1f}). We use k = {assumed:g} as a labelled assumption.")
    return f"The data cannot pin k down. We use k = {assumed:g} as a labelled assumption."


def k_caption(k_est: dict) -> str:
    reasons = (k_est.get("verdict") or {}).get("reasons") or []
    return ("Method: change in logit share of each skill from the 12 months before ChatGPT (2021-11 to "
            "2022-10) to the latest 12 months, regressed on the exposure of the skill. "
            + (f"Reason: {'; '.join(reasons)}. " if reasons else "")
            + "Only 5 categories carry the signal, AI skills rise for reasons other than exposure, and "
            "layoffs, interest rates and Hacker News sample shifts hit the same months. Details: "
            "`data/k_estimate.json`.")


def _placebo_fit(df: pd.DataFrame, n_boot: int, seed: int) -> dict:
    a, b = wls(df["e_s"], df["d"], df["w"])
    ci = bootstrap_slope(df["e_s"], df["d"], df["w"], df["category"], n_boot, seed)
    return {"n_skills": int(len(df)), "slope_b": b, "b_ci_cluster_bootstrap": [ci["ci_low"], ci["ci_high"]]}


def _inside(value: float, ci) -> bool | None:
    if ci[0] is None or ci[1] is None:
        return None
    return bool(ci[0] <= value <= ci[1])


def _clean(obj):
    """Round floats and turn NaN into None so the JSON stays strict."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else round(obj, 6)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return _clean(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def main() -> int:
    out = _clean(estimate())
    K_JSON.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    h = out["headline"]
    print(f"Wrote {K_JSON}")
    print(f"headline {h['window']}: b = {h['b']}, k_total = {h['k_total']} "
          f"cluster CI {h['k_total_ci_cluster_bootstrap']}, k_per_12m = {h['k_per_12m']} "
          f"CI {h['k_per_12m_ci_cluster_bootstrap']}")
    print(out["verdict"]["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
