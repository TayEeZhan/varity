"""Rolling-origin backtest for role-level forecasts: the skill backtest, run on role shares.

Run: python -m engine.role_backtest   (writes data/role_backtest.json, prints a summary)

The design is the one in engine/backtest.py, unchanged, because we call run_backtest itself on the
role table (role_id renamed to skill, see engine.role_forecast.role_demand_frame):
- Origins: every month 2021-12 to 2025-10. Early 2021-12..2023-10, test 2023-11..2025-10.
  At each origin only data up to that month is used.
- Point errors: share-scale absolute error in percentage points (pp), MAE at h = 1, 6, 12 for naive,
  naive3, and (for reference) drift and damped. Only naive and naive3 are in production.
- Model choice: naive or naive3 by mean share-scale |error| at h = 12 over origins whose target is
  <= the forecast date. Applied again at every test origin (leak-free).
- Band: rolling, symmetric, volatility-scaled conformal 80% band, W = 24, set a priori. Coverage at
  h = 12 and the mean over h, and the mean width at h = 12, on the test origins only.
- Trend label: at each origin from 2021-12 to 2025-10, a role labelled Rising or Falling is a hit if
  its pooled share over the NEXT 12 months moved in that direction against the LAST 12 months.
- Minimum-data rule: a role with a mean below 5 mentions per month over the 12 months up to an
  origin is left out of every metric at that origin.
Nothing here was tuned on the test origins. The window, the horizon, the 5-mention rule and the
label test are the skill settings.

Small sample: only 8 ranked roles (not 40 skills). The number of role-origin pairs is reported next
to every rate. The roles are strongly correlated across origins, so the effective sample is smaller
still. Treat every rate here as a rough guide, not as a validation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow "python engine/role_backtest.py"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from engine.backtest import (  # noqa: E402
    EARLY_FIRST,
    EARLY_LAST,
    TEST_FIRST,
    TEST_LAST,
    month_range,
    run_backtest,
)
from engine.forecast import DATA_DIR  # noqa: E402
from engine.role_forecast import (  # noqa: E402
    ROLE_BACKTEST_JSON,
    ranked_role_ids,
    role_demand_frame,
)
from engine.roles import ROLE_DEMAND_CSV, ROLES_JSON, load_roles  # noqa: E402

SCHEMA_VERSION = 1
SMALL_SAMPLE_NOTE = (
    "Only {n_roles} ranked roles, so {n_test} role-origin pairs on test and {n_trend} labelled "
    "role-origins for the trend label. Roles move together over time and consecutive origins overlap, "
    "so the effective sample is much smaller. Rates here are a rough guide, not a validation."
)
CAVEATS = [
    "Small sample: 8 ranked roles. Test errors of one role are correlated across origins and horizons, "
    "so the effective sample is much smaller than the raw count.",
    "The trend-label hit rate uses overlapping origins, so its role-origins are correlated.",
    "The conformal quantile is pooled over the 8 roles, so one noisy role moves it.",
    "The last target month (2026-10) comes from an HN thread that was still open when fetched.",
    "Posts per month fell from a mean of 703 (2019) to 310 (last 12 months), so recent months are "
    "noisier than early ones.",
    "Role shares are shares of posts that name the role in the text. A post can name several roles.",
]


def _rename(value):
    """Skill wording to role wording, in keys and text (the engine functions say 'skill')."""
    if isinstance(value, dict):
        return {_rename(k): _rename(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rename(v) for v in value]
    if isinstance(value, str):
        return value.replace("skill", "role").replace("Skill", "Role")
    return value


def run_role_backtest(demand: pd.DataFrame, early_origins: list[str], test_origins: list[str],
                      trend_origins: list[str] | None = None) -> dict:
    """The role backtest dict (the one written to role_backtest.json).

    `demand` is the role table with the role id in the `skill` column (role_demand_frame).
    """
    raw = run_backtest(demand, early_origins, test_origins, trend_origins)
    out = _rename(raw)
    n_roles = int(raw["n_skills_total"])
    n_test = int(raw["n_skill_origin_pairs"]["test"])
    n_trend = int(raw["trend_label_backtest"]["n"])
    out = {
        "schema_version": SCHEMA_VERSION,
        "kind": "role",
        "role_ids": sorted(demand["skill"].unique()),
        "sample_note": SMALL_SAMPLE_NOTE.format(n_roles=n_roles, n_test=n_test, n_trend=n_trend),
        **{k: v for k, v in out.items() if k not in ("caveats",)},
        "caveats": list(CAVEATS),
    }
    return out


def print_summary(r: dict) -> None:
    o = r["origins"]
    print("Verity role backtest (share-scale MAE in percentage points)")
    print(f"Data {r['data_window']['from']} to {r['data_window']['to']}. "
          f"Origins: early {o['early'][0]}..{o['early'][1]} ({o['n_early']}), "
          f"test {o['test'][0]}..{o['test'][1]} ({o['n_test']}).")
    print(f"Roles used: {r['n_roles_used']} of {r['n_roles_total']}; "
          f"role-origin pairs: early {r['n_role_origin_pairs']['early']}, "
          f"test {r['n_role_origin_pairs']['test']}, left out {r['n_role_origin_pairs']['excluded']}.")
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
          f"mean width at h=12 {c['test_mean_band_width_h12_pp']:.2f} pp; n={c['n_role_origins']}.")
    for name, g in c["by_share_group"].items():
        print(f"  {name}: n={g['n_role_origins']} h12 {g['h12']} mean {g['mean_over_h']} "
              f"width12 {g['mean_band_width_h12_pp']} pp")
    for name, s in r["interval_sensitivity"].items():
        if isinstance(s, dict):
            print(f"  sensitivity {name}: h12 {s['test_h12']:.1%}, mean {s['test_mean_over_h']:.1%}, "
                  f"width12 {s['mean_band_width_h12_pp']:.2f} pp")
    t = r["trend_label_backtest"]
    hit = "n/a" if t["trend_label_hit_rate"] is None else f"{t['trend_label_hit_rate']:.1%}"
    print(f"Trend label hit rate: {hit} on n={t['n']} role-origins "
          f"(rising {t['n_rising']}, falling {t['n_falling']}).")
    print(r["sample_note"])


def main(data_dir: Path | str | None = None) -> int:
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    roles = load_roles(data_dir / ROLES_JSON.name)
    demand = role_demand_frame(path=data_dir / ROLE_DEMAND_CSV.name, role_ids=ranked_role_ids(roles))
    result = run_role_backtest(demand, month_range(EARLY_FIRST, EARLY_LAST),
                               month_range(TEST_FIRST, TEST_LAST))
    out_path = data_dir / ROLE_BACKTEST_JSON.name
    out_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print_summary(result)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
