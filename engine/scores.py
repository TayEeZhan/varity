"""Build data/skill_scores.json: the file the app reads (see docs/data-contract.md).

Run: python -m engine.scores        (needs data/backtest.json: run python -m engine.backtest first)

Per skill
- Moderate scenario = the chosen model's 12-month point forecast, and its conformal
  80% band, both mapped back to shares with the inverse logit. The model and the band
  offsets come from data/backtest.json (chosen on calibration origins only).
- Fast scenario = moderate * (1 - k * e_s), applied to the point and to both band
  ends, then clipped to [0, 1]. e_s is the skill's AI exposure relative to the mean
  of the 40 skills (data/exposure.csv). k = 2 is an assumption, stored in scenario_params.
- A skill with a mean of fewer than 5 mentions per month over the last 12 months is
  "insufficient_data": its forecast fields are null.

The forecast date is the last month in the data (2026-10). That month's HN thread was
still open when it was fetched on 22 Oct 2026, so its counts are partial.
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
    forecast_skill,
    has_enough_data,
    inv_logit,
    load_demand,
    logit_series,
    wide_tables,
)

SCORES_JSON = DATA_DIR / "skill_scores.json"
TAXONOMY_JSON = DATA_DIR / "taxonomy.json"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"
THREADS_CSV = DATA_DIR / "hn_threads.csv"

K = 2  # fast-scenario strength: an assumption shown in the app
SLOPE_WINDOW = 24  # months for demand_slope
LATEST_WINDOW = 3  # months averaged for demand_share_latest
EVIDENCE_MONTHS = 3  # threads cited per skill

# From data/SOURCES.md, section 1.
AEI_SOURCE = {
    "name": "Anthropic Economic Index (release 2026-06-26)",
    "url": "https://huggingface.co/datasets/Anthropic/EconomicIndex",
    "date": "2026-06-26",
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


def moderate_band(point_y: np.ndarray, q10: np.ndarray, q90: np.ndarray) -> dict:
    """12-month value and 80% band as shares, from logit-scale forecasts and offsets."""
    h = HORIZON - 1
    return {
        "value_12m": float(inv_logit(point_y[h])),
        "low": float(inv_logit(point_y[h] + q10[h])),
        "high": float(inv_logit(point_y[h] + q90[h])),
    }


def _empty_forecast() -> dict:
    null = {"value_12m": None, "low": None, "high": None}
    return {"moderate": dict(null), "fast": dict(null)}


def _fast_block(moderate: dict, e_s: float, k: float) -> dict:
    return {key: fast_scenario(value, e_s, k) for key, value in moderate.items()}


def _thread_sources(threads: pd.DataFrame, months: list[str]) -> list[dict]:
    rows = threads.set_index("month").loc[months]
    return [
        {
            "name": row["title"],
            "url": row["url"],
            "date": str(row["created_at"])[:10],
        }
        for _, row in rows.iterrows()
    ]


def build_scores(as_of: str | None = None, backtest: dict | None = None, k: float = K,
                 demand: pd.DataFrame | None = None) -> dict:
    """Build the skill_scores dict using only data up to and including `as_of` (YYYY-MM).

    as_of defaults to the last month in the data.
    """
    if backtest is None:
        if not BACKTEST_JSON.exists():
            raise FileNotFoundError(f"{BACKTEST_JSON} not found. Run: python -m engine.backtest")
        backtest = json.loads(BACKTEST_JSON.read_text(encoding="utf-8"))
    model = backtest["chosen_model"]
    q10 = np.array(backtest["conformal"]["q10_by_h"])
    q90 = np.array(backtest["conformal"]["q90_by_h"])

    if demand is None:
        demand = load_demand()
    last_month = str(demand["month"].max())
    if as_of is None:
        as_of = last_month
    elif as_of > last_month:
        raise ValueError(f"as_of {as_of} is after the last month in the data ({last_month})")
    demand = demand[demand["month"] <= as_of]

    mentions, n_posts = wide_tables(demand)
    y = logit_series(demand=demand)
    share = demand.pivot(index="month", columns="skill", values="share").sort_index()
    months = list(mentions.index)
    latest_months = months[-EVIDENCE_MONTHS:]
    thread_ids = demand.groupby("month")["thread_id"].first()

    taxonomy = {t["skill"]: t for t in json.loads(TAXONOMY_JSON.read_text(encoding="utf-8"))}
    exposure = pd.read_csv(EXPOSURE_CSV).set_index("skill")
    threads = pd.read_csv(THREADS_CSV)
    thread_sources = _thread_sources(threads, latest_months)
    evidence = [f"hn:{thread_ids[m]}" for m in latest_months]

    skills_out = []
    for skill in taxonomy:
        e_s = float(exposure.loc[skill, "e_s"])
        enough = has_enough_data(mentions[skill].to_numpy())
        if enough:
            point = forecast_skill(y[skill].to_numpy(), model, HORIZON)
            moderate = moderate_band(point, q10, q90)
            forecast = {"moderate": moderate, "fast": _fast_block(moderate, e_s, k)}
        else:
            forecast = _empty_forecast()
        skills_out.append({
            "skill": skill,
            "sdg": taxonomy[skill]["sdg"],
            "demand_share_latest": float(share[skill].to_numpy()[-LATEST_WINDOW:].mean()),
            "demand_slope": slope_pp_per_year(share[skill].to_numpy()),
            "momentum": None,
            "ai_exposure": float(exposure.loc[skill, "ai_exposure"]),
            "stance": str(exposure.loc[skill, "stance"]),
            "status": "ok" if enough else "insufficient_data",
            "forecast": forecast,
            "evidence": list(evidence),
            "sources": [dict(s) for s in thread_sources] + [dict(AEI_SOURCE)],
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "scenario_params": {"k": k},
        "data_window": {"from": months[0], "to": months[-1]},
        "skills": skills_out,
    }


def main() -> int:
    scores = build_scores()
    SCORES_JSON.write_text(json.dumps(scores, indent=2) + "\n", encoding="utf-8")
    ok = sum(s["status"] == "ok" for s in scores["skills"])
    print(f"Wrote {SCORES_JSON}: {len(scores['skills'])} skills, {ok} with a forecast, as_of {scores['as_of']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
