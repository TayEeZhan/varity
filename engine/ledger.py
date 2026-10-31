"""Forecast ledger: every daily run writes down its role forecasts, and later months grade them.

forecast_ledger.csv (in the data folder, saved with each store snapshot), one row per run and role:
    run_date, as_of, target_month, role_id, share_now, point_12m, low, high, label, model, nowcast_k,
    actual, hit
actual and hit stay empty until the target month (as_of + 12) is a full month in the role demand
table; then actual = that month's share and hit = low <= actual <= high.
A second run on the same day replaces that day's rows. The track record counts one forecast per
role and as_of month (the last run in that month), so daily runs do not count one forecast 30 times.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

LEDGER_NAME = "forecast_ledger.csv"
COLUMNS = ["run_date", "as_of", "target_month", "role_id", "share_now", "point_12m", "low", "high",
           "label", "model", "nowcast_k", "actual", "hit"]
HORIZON = 12


def target_month(as_of: str, months: int = HORIZON) -> str:
    return str(pd.Period(as_of, freq="M") + months)


def read(data_dir: Path | str) -> list[dict]:
    path = Path(data_dir) / LEDGER_NAME
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(data_dir: Path | str, rows: list[dict]) -> None:
    path = Path(data_dir) / LEDGER_NAME
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({c: r.get(c, "") for c in COLUMNS} for r in rows)
    tmp.replace(path)


def record(data_dir: Path | str, forecast: Mapping[str, Any], demand_rows: list[dict], run_date: str,
           current_month: str) -> list[dict]:
    """Add today's rows from a role_forecast document, grade old rows, write the file, return all rows."""
    rows = [r for r in read(data_dir) if r["run_date"] != run_date]
    model = forecast.get("interval", {}).get("model", "")
    k = (forecast.get("nowcast") or {}).get("k") or 0
    for rid, r in forecast.get("roles", {}).items():
        f = r.get("forecast_moderate") or {}
        if r.get("status") != "ok" or f.get("value_12m") is None:
            continue
        rows.append({"run_date": run_date, "as_of": forecast["as_of"], "target_month": target_month(forecast["as_of"]),
                     "role_id": rid, "share_now": f"{r['share_now']['value']:.6f}", "point_12m": f"{f['value_12m']:.6f}",
                     "low": f"{f['low']:.6f}", "high": f"{f['high']:.6f}", "label": r["trend"]["label"] or "",
                     "model": model, "nowcast_k": k, "actual": "", "hit": ""})
    actual = {(d["month"], d["role_id"]): d["share"] for d in demand_rows if d["month"] < current_month}
    for r in rows:
        share = actual.get((r["target_month"], r["role_id"]))
        if share is not None and r["actual"] == "":
            r["actual"] = f"{float(share):.6f}"
            r["hit"] = "1" if float(r["low"]) <= float(share) <= float(r["high"]) else "0"
    rows.sort(key=lambda r: (r["run_date"], r["role_id"]))
    _write(data_dir, rows)
    return rows


def summary(rows: list[dict]) -> dict:
    """Track record and the change since the previous run, for the forecast screen."""
    last_per_month: dict[tuple[str, str], dict] = {}
    for r in rows:  # rows are sorted by run_date, so the last one wins
        last_per_month[(r["as_of"], r["role_id"])] = r
    graded = [r for r in last_per_month.values() if r["hit"] != ""]
    dates = sorted({r["run_date"] for r in rows})
    changes: dict[str, dict] = {}
    if len(dates) >= 2:
        prev = {r["role_id"]: r for r in rows if r["run_date"] == dates[-2]}
        for r in rows:
            if r["run_date"] == dates[-1] and r["role_id"] in prev:
                changes[r["role_id"]] = {"since": dates[-2], "share_now_from": float(prev[r["role_id"]]["share_now"]),
                                         "share_now_to": float(r["share_now"])}
    return {
        "first_run": dates[0] if dates else None,
        "runs": len(dates),
        "forecasts_graded": len(graded),
        "forecasts_in_band": sum(r["hit"] == "1" for r in graded),
        "next_grading_month": min((r["target_month"] for r in last_per_month.values() if r["hit"] == ""), default=None),
        "changes_since_last_run": changes,
    }
