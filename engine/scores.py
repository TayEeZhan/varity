"""Build data/skill_scores.json: the file the app reads (see docs/data-contract.md).

Run: python -m engine.scores        (needs data/backtest.json for the source date: run
python -m engine.backtest first)

Per skill
- status "ok" (>= 5 mentions per month over the last 12 months): a forecast.
  Moderate scenario = the 12-month point forecast of the chosen model (naive or naive3) and
  its rolling conformal band (80% target band), mapped back to shares with the inverse logit.
  The model and the band come from engine.forecast (choose_model, band_offsets), computed
  here from data with target <= as_of only. Nothing is read from backtest.json except its date.
  Fast scenario = moderate * (1 - k * e_s), applied to the point and to both band ends, then
  clipped to [0, 1]. e_s is the skill's AI exposure relative to the mean of the 40 skills
  (data/exposure.csv). k = 2 is an assumption, stored in scenario_params.
- status "low_volume" (< 5 per month, but >= 30 mentions in the last 24 months): no forecast
  and no scenario. Observed pooled counts and the trend label are shown.
- status "rare" (< 30 mentions in the last 24 months): no forecast, no trend label.
- trend_label is OBSERVED (Welch t-test, last 12 months against the 12 before), not a forecast.
- Scale: demand_share_latest is a raw share (sum mentions / sum posts over the last 3 months,
  for display). level_now is the model-scale level, inv_logit(mean of the last 3 values of y).
  Any change is value_12m - level_now. Never subtract demand_share_latest from value_12m.

The forecast date is the last month in the data (2026-10). That month's HN thread was
still open when it was fetched on 22 Oct 2026, so its counts are partial (partial_month).
exposure.csv (AEI 2026-06) is not time-cut: it is the same for every as_of.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if __package__ in (None, ""):  # allow "python engine/scores.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.backtest import BACKTEST_JSON  # noqa: E402
from engine.forecast import (  # noqa: E402
    DATA_DIR,
    HORIZON,
    INTERVAL_LEVEL,
    INTERVAL_WINDOW,
    PRODUCTION_MODELS,
    band_offsets,
    build_residual_tables,
    choose_model,
    earliest_supported,
    forecast_skill,
    inv_logit,
    load_demand,
    logit_series,
    skill_status,
    trend_label,
    volatility,
    wide_tables,
    _check_month,
)

# Default locations in the repo data/ folder. build_scores(data_dir=...) uses the same
# file names inside any other folder.
SCORES_JSON = DATA_DIR / "skill_scores.json"
TAXONOMY_JSON = DATA_DIR / "taxonomy.json"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"
THREADS_CSV = DATA_DIR / "hn_threads.csv"
DEMAND_NAME = "demand_monthly.csv"

K = 2  # fast-scenario strength: an assumption shown in the app
SLOPE_WINDOW = 24  # months for demand_slope
LATEST_WINDOW = 3  # months pooled for demand_share_latest and level_now
EVIDENCE_MONTHS = 3  # threads cited per skill

LOW_VOLUME_NOTE = "Too few posts to forecast; observed counts shown."
RARE_NOTE = "Fewer than 30 mentions in 24 months; too rare to forecast or to label a trend."
OUTPUT_NOTES = [
    "exposure.csv (Anthropic Economic Index 2026-06) is not time-cut: the fast scenario uses "
    "the same exposure for every as_of.",
    "trend_label is observed (last 12 months against the 12 before), not a forecast.",
]

# From data/SOURCES.md, section 1.
AEI_SOURCE = {
    "name": "Anthropic Economic Index (release 2026-06-26)",
    "url": "https://huggingface.co/datasets/Anthropic/EconomicIndex",
    "date": "2026-06-26",
}


def backtest_source(model: str, generated_at: str) -> dict:
    """The source entry that points to data/backtest.json."""
    return {
        "name": f"Verity backtest (rolling conformal, {model})",
        "url": "data/backtest.json",
        "date": str(generated_at)[:10],
    }


def fast_scenario(moderate: float | None, e_s: float, k: float = K) -> float | None:
    """fast = moderate * (1 - k * e_s), clipped to [0, 1]. None stays None."""
    if moderate is None:
        return None
    return float(np.clip(moderate * (1.0 - k * e_s), 0.0, 1.0))


def slope_pp_per_year(share, window: int = SLOPE_WINDOW) -> float:
    """Slope of a straight line through the last `window` monthly shares, in pp per year."""
    recent = np.asarray(share, dtype=float)[-window:]
    if recent.size < 2:
        return 0.0
    per_month = np.polyfit(np.arange(recent.size), recent, 1)[0]
    return float(per_month * 12 * 100)


def moderate_band(point_y: np.ndarray, q: float, sigma: float) -> dict:
    """12-month value and 80% band as shares, from the logit point forecast.

    Half-width on the logit scale = q * sigma. Band = inv_logit(point +/- half-width).
    """
    point = float(np.asarray(point_y, dtype=float)[HORIZON - 1])
    half = q * sigma
    return {
        "value_12m": float(inv_logit(point)),
        "low": float(inv_logit(point - half)),
        "high": float(inv_logit(point + half)),
    }


def _empty_forecast() -> dict:
    null = {"value_12m": None, "low": None, "high": None}
    return {"moderate": dict(null), "fast": dict(null)}


def _fast_block(moderate: dict, e_s: float, k: float) -> dict:
    return {key: fast_scenario(value, e_s, k) for key, value in moderate.items()}


def _thread_sources(threads: pd.DataFrame, months: list[str]) -> list[dict]:
    """One source per month that has a row in hn_threads.csv. A missing month is skipped."""
    by_month = threads.drop_duplicates("month", keep="last").set_index("month")
    return [
        {
            "name": by_month.at[month, "title"],
            "url": by_month.at[month, "url"],
            "date": str(by_month.at[month, "created_at"])[:10],
        }
        for month in months
        if month in by_month.index
    ]


def build_scores(as_of: str | None = None, backtest: dict | None = None, k: float = K,
                 demand: pd.DataFrame | None = None, today: datetime | None = None,
                 data_dir: Path | str | None = None) -> dict:
    """Build the skill_scores dict using only data up to and including `as_of` (YYYY-MM).

    Returns the dict and writes nothing (only main() writes a file), so an as-of view is safe.
    `data_dir` (default: the repo data/ folder) holds demand_monthly.csv, taxonomy.json,
    exposure.csv, backtest.json and hn_threads.csv. A `demand` or `backtest` argument wins
    over the file in data_dir.

    as_of defaults to the last month in the data. The model choice and the band use only
    residuals whose target is <= as_of. as_of must be at least earliest_supported(months)
    (2023-11 for the real data); earlier values raise ValueError.
    `backtest` is only used for its generated_at date (the backtest source entry).
    `today` (default now, UTC) only decides partial_month.
    """
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    if backtest is None:
        backtest_path = data_dir / BACKTEST_JSON.name
        if not backtest_path.exists():
            raise FileNotFoundError(f"{backtest_path} not found. Run: python -m engine.backtest")
        backtest = json.loads(backtest_path.read_text(encoding="utf-8"))
    if today is None:
        today = datetime.now(timezone.utc)

    if demand is None:
        demand = load_demand(path=data_dir / DEMAND_NAME)
    all_months = sorted(demand["month"].unique())
    last_month = all_months[-1]
    if as_of is None:
        as_of = last_month
    else:
        _check_month("as_of", as_of)
        if as_of > last_month:
            raise ValueError(f"as_of {as_of} is after the last month in the data ({last_month})")
    earliest = earliest_supported(all_months)
    if as_of < earliest:
        raise ValueError(
            f"as_of {as_of} is too early: the rolling band needs at least 24 usable origins "
            f"whose 12-month target is <= as_of. Earliest supported as_of is {earliest}.")
    demand = demand[demand["month"] <= as_of]

    mentions, n_posts = wide_tables(demand)
    y = logit_series(demand=demand)
    share = demand.pivot(index="month", columns="skill", values="share").sort_index()
    months = list(mentions.index)
    latest_months = months[-EVIDENCE_MONTHS:]
    thread_ids = demand.groupby("month")["thread_id"].first()

    tables = build_residual_tables(demand, PRODUCTION_MODELS)
    model = choose_model(tables, as_of)
    q12 = band_offsets(tables[model], as_of, HORIZON)

    taxonomy = {t["skill"]: t
                for t in json.loads((data_dir / TAXONOMY_JSON.name).read_text(encoding="utf-8"))}
    exposure = pd.read_csv(data_dir / EXPOSURE_CSV.name).set_index("skill")
    threads = pd.read_csv(data_dir / THREADS_CSV.name)
    sources = ([dict(s) for s in _thread_sources(threads, latest_months)] + [dict(AEI_SOURCE)]
               + [backtest_source(model, backtest["generated_at"])])
    evidence = [f"hn:{thread_ids[m]}" for m in latest_months]

    skills_out = []
    for skill in taxonomy:
        e_s = float(exposure.loc[skill, "e_s"])
        m = mentions[skill].to_numpy(dtype=float)
        p = n_posts[skill].to_numpy(dtype=float)
        ys = y[skill].to_numpy()
        status = skill_status(m)
        label, trend_p = trend_label(ys, m)

        m3, p3 = int(m[-LATEST_WINDOW:].sum()), int(p[-LATEST_WINDOW:].sum())
        if status == "ok":
            point = forecast_skill(ys, model, HORIZON)
            moderate = moderate_band(point, q12, volatility(ys))
            forecast = {"moderate": moderate, "fast": _fast_block(moderate, e_s, k)}
            shift_pp = (forecast["fast"]["value_12m"] - moderate["value_12m"]) * 100.0
            width_pp = (moderate["high"] - moderate["low"]) * 100.0
            note = None
        else:
            forecast = _empty_forecast()
            shift_pp = width_pp = None
            note = LOW_VOLUME_NOTE if status == "low_volume" else RARE_NOTE

        skills_out.append({
            "skill": skill,
            "sdg": taxonomy[skill]["sdg"],
            "demand_share_latest": m3 / p3,
            "mentions_last3": m3,
            "posts_last3": p3,
            "level_now": float(inv_logit(ys[-LATEST_WINDOW:].mean())),
            "demand_slope": slope_pp_per_year(share[skill].to_numpy()),
            "momentum": None,
            "ai_exposure": float(exposure.loc[skill, "ai_exposure"]),
            "stance": str(exposure.loc[skill, "stance"]),
            "status": status,
            "note": note,
            "trend_label": label,
            "trend_p": None if trend_p is None else float(trend_p),
            "mentions_last12": int(m[-12:].sum()),
            "posts_last12": int(p[-12:].sum()),
            "mentions_prev12": int(m[-24:-12].sum()),
            "posts_prev12": int(p[-24:-12].sum()),
            "forecast": forecast,
            "scenario_shift_pp": shift_pp,
            "band_width_pp": width_pp,
            "evidence": list(evidence),
            "sources": [dict(s) for s in sources],
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "partial_month": months[-1] == today.strftime("%Y-%m"),
        "scenario_params": {"k": k},
        "interval": {"label": "80% target band", "level": INTERVAL_LEVEL, "model": model,
                     "window_origins": INTERVAL_WINDOW, "q_h12": q12,
                     "earliest_supported_as_of": earliest},
        "notes": list(OUTPUT_NOTES),
        "data_window": {"from": months[0], "to": months[-1]},
        "skills": skills_out,
    }


def main(data_dir: Path | str | None = None) -> int:
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    out_path = data_dir / SCORES_JSON.name
    scores = build_scores(data_dir=data_dir)
    out_path.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for s in scores["skills"]:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    print(f"Wrote {out_path}: {len(scores['skills'])} skills, as_of {scores['as_of']}, "
          f"model {scores['interval']['model']}, partial_month {scores['partial_month']}.")
    print("Status counts:", counts)
    for label in ("Rising", "Falling"):
        names = [s["skill"] for s in scores["skills"] if s["trend_label"] == label]
        print(f"{label} ({len(names)}):", ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
