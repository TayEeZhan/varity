"""12-month forecast for each ranked role: the same machinery as skills, applied to role shares.

Run: python -m engine.role_forecast   (writes data/role_forecast.json; needs data/role_backtest.json
for the source date: run python -m engine.role_backtest first)

Input: data/role_demand_monthly.csv (month, role_id, mentions, n_posts, share). A role is a
"mentions" series in exactly the way a skill is: mentions = posts in the month that name the role,
n_posts = posts in the month. So we rename role_id to skill and call the functions in
engine/forecast.py. No maths is copied. The functions are:
    smoothed_share / logit / inv_logit   y = logit((m + 0.5) / (n + 1))
    forecast_skill                       naive and naive3 point forecast at h = 12
    build_residual_tables, choose_model  naive or naive3, by mean share-scale |error| at h = 12 over
                                         origins whose 12-month target is <= as_of
    band_offsets, volatility             rolling (W = 24), symmetric, volatility-scaled conformal 80% band
    has_enough_data                      mean mentions per month over the last 12 months >= 5
    trend_label                          Welch t-test, last 12 months against the 12 before (the same
                                         label as data/role_trends.json)
Pooling: the conformal quantile q is pooled over the ranked roles (8 today), exactly as it is pooled
over skills. With 8 roles there are few residuals, so the band is less well supported than for skills
(see data/role_backtest.json for coverage).

Roles: only roles that are ranked in data/roles.json (ranked is true unless the file says false).
An unranked role (Analytics Engineer) is listed under excluded_roles and does not enter q.

Status per role
    ok          mean mentions per month over the last 12 months >= 5: point forecast and band.
    low_volume  below that: observed counts and trend label only, no forecast, no band.

`as_of` (YYYY-MM): role_forecast_for uses only months <= as_of, so a later month never changes an
earlier forecast. The model choice and q use only residuals with target <= as_of. as_of must be at
least earliest_supported(months) (2023-11 for the real data).

The last month (2026-10) comes from an HN thread that was still open when fetched (partial_month).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):  # allow "python engine/role_forecast.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.forecast import (  # noqa: E402
    DATA_DIR,
    HORIZON,
    INTERVAL_LEVEL,
    INTERVAL_WINDOW,
    MIN_MEAN_MENTIONS,
    PRODUCTION_MODELS,
    _check_month,
    band_offsets,
    build_residual_tables,
    choice_scores,
    choose_model,
    earliest_supported,
    forecast_skill,
    has_enough_data,
    inv_logit,
    load_demand,
    logit_series,
    trend_label,
    volatility,
    wide_tables,
)
from engine.roles import ROLE_DEMAND_CSV, ROLES_JSON, load_roles  # noqa: E402
from engine.scores import EVIDENCE_MONTHS, LATEST_WINDOW, _thread_sources, moderate_band  # noqa: E402

ROLE_FORECAST_JSON = DATA_DIR / "role_forecast.json"
ROLE_BACKTEST_JSON = DATA_DIR / "role_backtest.json"
THREADS_CSV = DATA_DIR / "hn_threads.csv"
SCHEMA_VERSION = 1
BAND_LABEL = "80% target band"
LOW_VOLUME_NOTE = (f"Fewer than {MIN_MEAN_MENTIONS} posts a month on average over the last 12 months; "
                   "observed counts shown, no forecast and no band.")
OUTPUT_NOTES = [
    "trend label is observed (last 12 months against the 12 before), not a forecast.",
    "The band is pooled over the ranked roles, so it rests on few roles; "
    "see data/role_backtest.json for how often it covered held-out outcomes.",
    "Share of HN hiring posts is a sample of tech hiring, not a count of jobs.",
]


def ranked_role_ids(roles: list[dict]) -> list[str]:
    """Ids of the roles with ranked != false in roles.json, in file order."""
    return [r["id"] for r in roles if r.get("ranked", True)]


def role_demand_frame(as_of: str | None = None, path: Path | str = ROLE_DEMAND_CSV,
                      role_ids: list[str] | None = None) -> pd.DataFrame:
    """The role table in the shape engine.forecast expects: role_id is renamed to skill.

    Keeps months <= as_of (load_demand does that) and, if role_ids is given, only those roles.
    """
    frame = load_demand(as_of, path=path).rename(columns={"role_id": "skill"})
    if role_ids is not None:
        frame = frame[frame["skill"].isin(role_ids)]
        missing = sorted(set(role_ids) - set(frame["skill"]))
        if missing:
            raise ValueError(f"no demand rows for roles {missing}")
    return frame.reset_index(drop=True)


def backtest_source(generated_at: str) -> dict:
    """The source entry that points to data/role_backtest.json."""
    return {
        "name": "Verity role backtest (data/role_backtest.json)",
        "url": "data/role_backtest.json",
        "date": str(generated_at)[:10],
    }


def _read_backtest(data_dir: Path) -> dict:
    path = data_dir / ROLE_BACKTEST_JSON.name
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python -m engine.role_backtest")
    return json.loads(path.read_text(encoding="utf-8"))


def role_forecast_for(as_of: str | None = None, backtest: dict | None = None,
                      demand: pd.DataFrame | None = None, today: datetime | None = None,
                      data_dir: Path | str | None = None) -> dict:
    """Build the role_forecast dict using only data up to and including `as_of` (YYYY-MM).

    Writes nothing (only main() writes a file), so the as-of slider can call it safely.
    `data_dir` (default: the repo data/ folder) holds roles.json, role_demand_monthly.csv,
    hn_threads.csv and role_backtest.json. A `demand` (role table with skill = role id) or
    `backtest` argument wins over the file. `backtest` is only used for its generated_at date.
    `today` (default now, UTC) only decides partial_month.
    """
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    if backtest is None:
        backtest = _read_backtest(data_dir)
    if today is None:
        today = datetime.now(timezone.utc)

    roles = load_roles(data_dir / ROLES_JSON.name)
    names = {r["id"]: r["name"] for r in roles}
    if demand is None:
        demand = role_demand_frame(path=data_dir / ROLE_DEMAND_CSV.name, role_ids=ranked_role_ids(roles))
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
    months = list(mentions.index)
    latest_months = months[-EVIDENCE_MONTHS:]

    tables = build_residual_tables(demand, PRODUCTION_MODELS)
    scores = choice_scores(tables, as_of)
    model = choose_model(tables, as_of)
    q12 = band_offsets(tables[model], as_of, HORIZON)

    threads = pd.read_csv(data_dir / THREADS_CSV.name)
    sources = ([dict(s) for s in _thread_sources(threads, latest_months)]
               + [backtest_source(backtest["generated_at"])])
    partial = months[-1] == today.strftime("%Y-%m")

    roles_out: dict[str, dict] = {}
    for rid in mentions.columns:
        m = mentions[rid].to_numpy(dtype=float)
        p = n_posts[rid].to_numpy(dtype=float)
        ys = y[rid].to_numpy()
        status = "ok" if has_enough_data(m) else "low_volume"
        label, trend_p = trend_label(ys, m)
        m3, p3 = int(m[-LATEST_WINDOW:].sum()), int(p[-LATEST_WINDOW:].sum())
        m12, p12 = int(m[-12:].sum()), int(p[-12:].sum())
        mp12, pp12 = int(m[-24:-12].sum()), int(p[-24:-12].sum())

        if status == "ok":
            point = forecast_skill(ys, model, HORIZON)
            moderate = moderate_band(point, q12, volatility(ys))
            width_pp = (moderate["high"] - moderate["low"]) * 100.0
            note = None
        else:
            moderate = {"value_12m": None, "low": None, "high": None}
            width_pp = None
            note = LOW_VOLUME_NOTE

        roles_out[rid] = {
            "name": names.get(rid, rid),
            "status": status,
            "note": note,
            "share_now": {"value": m3 / p3, "mentions": m3, "posts": p3, "months": list(latest_months)},
            "level_now": float(inv_logit(ys[-LATEST_WINDOW:].mean())),
            "forecast_moderate": moderate,
            "band_width_pp": width_pp,
            "trend": {
                "label": label,
                "p": None if trend_p is None else float(trend_p),
                "share_last12": m12 / p12,
                "share_prev12": mp12 / pp12,
                "mentions_last12": m12,
                "posts_last12": p12,
                "mentions_prev12": mp12,
                "posts_prev12": pp12,
            },
            "sources": [dict(s) for s in sources],
            "as_of": as_of,
            "partial_month": partial,
        }

    ranked = set(roles_out)
    excluded = [{"role_id": r["id"], "name": r["name"], "reason": r.get("note") or "not ranked in roles.json"}
                for r in roles if r["id"] not in ranked]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "as_of": as_of,
        "partial_month": partial,
        "interval": {"label": BAND_LABEL, "level": INTERVAL_LEVEL, "model": model,
                     "window_origins": INTERVAL_WINDOW, "q_h12": q12,
                     "model_scores_h12_pp": {k: round(v * 100, 4) for k, v in scores.items()},
                     "n_roles_pooled": len(roles_out), "earliest_supported_as_of": earliest},
        "notes": list(OUTPUT_NOTES),
        "data_window": {"from": months[0], "to": months[-1]},
        "excluded_roles": excluded,
        "roles": roles_out,
    }


def main(data_dir: Path | str | None = None) -> int:
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    out_path = data_dir / ROLE_FORECAST_JSON.name
    doc = role_forecast_for(data_dir=data_dir)
    out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    iv = doc["interval"]
    print(f"Wrote {out_path}: {len(doc['roles'])} roles, as_of {doc['as_of']}, model {iv['model']}, "
          f"q_h12 {iv['q_h12']:.3f}, partial_month {doc['partial_month']}.")
    print(f"{'role':<26} {'status':<10} {'now':>6} {'12m':>6} {'low':>6} {'high':>6} {'width':>6}  trend")
    for rid, r in doc["roles"].items():
        f = r["forecast_moderate"]
        pct = lambda v: "   n/a" if v is None else f"{v * 100:5.1f}%"  # noqa: E731
        width = "   n/a" if r["band_width_pp"] is None else f"{r['band_width_pp']:5.1f}p"
        print(f"{rid:<26} {r['status']:<10} {pct(r['share_now']['value'])} {pct(f['value_12m'])} "
              f"{pct(f['low'])} {pct(f['high'])} {width}  {r['trend']['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
