"""12-month demand forecasts for each skill, on the logit scale.

Input: data/demand_monthly.csv (month, skill, mentions, n_posts, ...).

Series for one skill
    p = (mentions + 0.5) / (n_posts + 1)   share of posts, kept away from 0 and 1
    y = logit(p) = ln(p / (1 - p))         the series every model works on
We fit on this raw monthly series, not on share_smooth. Smoothing makes the
residuals too small, so the bands would be too narrow.

Four candidate models. Each one takes the history y and returns 12 point forecasts:
    naive   the last value, repeated.
    naive3  the mean of the last 3 values, repeated.
    drift   last value + 0.5 * slope * h. The slope is a straight-line fit on the
            last 24 months. The 0.5 shrinks the slope, because trends rarely last.
    damped  exponential smoothing with a damped additive trend, fit on the last
            36 months (statsmodels ExponentialSmoothing).

`as_of` (YYYY-MM): every public function that reads data uses only months up to
and including as_of. Changing a later month never changes an earlier forecast.

Note: the Oct 2026 HN thread was still open when it was fetched (22 Oct 2026), so
the last month is a partial count. Its share is a noisy estimate. We keep it
because the forecast date is the last month in the data.
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEMAND_CSV = DATA_DIR / "demand_monthly.csv"

MODELS = ("naive", "naive3", "drift", "damped")
HORIZON = 12
DRIFT_WINDOW = 24  # months used for the drift slope
DRIFT_SHRINK = 0.5  # the slope is multiplied by this
DAMPED_WINDOW = 36  # months used to fit the damped trend model
MIN_MEAN_MENTIONS = 5  # below this (mean per month, last 12 months) we show no forecast

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def logit(p):
    """Logit: ln(p / (1 - p)). p must be strictly between 0 and 1."""
    p = np.asarray(p, dtype=float)
    return np.log(p / (1.0 - p))


def inv_logit(y):
    """Inverse of logit: 1 / (1 + exp(-y)). Result is always between 0 and 1."""
    y = np.asarray(y, dtype=float)
    return 1.0 / (1.0 + np.exp(-y))


def smoothed_share(mentions, n_posts):
    """p = (mentions + 0.5) / (n_posts + 1). Never 0 or 1, so logit is finite."""
    return (np.asarray(mentions, dtype=float) + 0.5) / (np.asarray(n_posts, dtype=float) + 1.0)


def _check_month(name: str, value: str) -> None:
    if not isinstance(value, str) or not _MONTH_RE.match(value):
        raise ValueError(f"{name} must look like 'YYYY-MM', got {value!r}")


def load_demand(as_of: str | None = None, path: Path | str = DEMAND_CSV) -> pd.DataFrame:
    """Read the demand table and keep only months <= as_of (all months if None)."""
    demand = pd.read_csv(path)
    if as_of is not None:
        _check_month("as_of", as_of)
        demand = demand[demand["month"] <= as_of]
        if demand.empty:
            raise ValueError(f"no data on or before {as_of}")
    return demand


def wide_tables(demand: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (mentions, n_posts), each with one row per month and one column per skill."""
    mentions = demand.pivot(index="month", columns="skill", values="mentions").sort_index()
    n_posts = demand.pivot(index="month", columns="skill", values="n_posts").sort_index()
    months = pd.PeriodIndex(mentions.index, freq="M")
    if len(months) > 1 and (np.diff(months.asi8) != 1).any():
        raise ValueError("demand table has a gap in its months")
    if mentions.isna().any().any() or n_posts.isna().any().any():
        raise ValueError("demand table is missing a skill-month")
    return mentions, n_posts


def logit_series(as_of: str | None = None, demand: pd.DataFrame | None = None) -> pd.DataFrame:
    """y = logit(p) for every skill (columns) and month (rows), months <= as_of only."""
    if demand is None:
        demand = load_demand(as_of)
    elif as_of is not None:
        _check_month("as_of", as_of)
        demand = demand[demand["month"] <= as_of]
    mentions, n_posts = wide_tables(demand)
    return pd.DataFrame(
        logit(smoothed_share(mentions.to_numpy(), n_posts.to_numpy())),
        index=mentions.index,
        columns=mentions.columns,
    )


def has_enough_data(recent_mentions) -> bool:
    """True if the mean mentions per month over the last 12 months is at least 5."""
    last12 = np.asarray(recent_mentions, dtype=float)[-12:]
    return last12.size > 0 and last12.mean() >= MIN_MEAN_MENTIONS


def forecast_skill(y_series, model: str, horizon: int = HORIZON) -> np.ndarray:
    """Point forecasts for h = 1..horizon, on the logit scale.

    y_series is the history (oldest first). It must already end at the forecast date.
    """
    y = np.asarray(y_series, dtype=float)
    if y.size == 0:
        raise ValueError("y_series is empty")
    steps = np.arange(1, horizon + 1)

    if model == "naive":
        return np.full(horizon, y[-1])
    if model == "naive3":
        return np.full(horizon, y[-3:].mean())
    if model == "drift":
        recent = y[-DRIFT_WINDOW:]
        slope = np.polyfit(np.arange(recent.size), recent, 1)[0] if recent.size >= 2 else 0.0
        return y[-1] + DRIFT_SHRINK * slope * steps
    if model == "damped":
        recent = y[-DAMPED_WINDOW:]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # statsmodels warns on flat or short series
            fit = ExponentialSmoothing(
                recent, trend="add", damped_trend=True, initialization_method="estimated"
            ).fit()
        return np.asarray(fit.forecast(horizon), dtype=float)
    raise ValueError(f"unknown model {model!r}, expected one of {MODELS}")


def forecast_all(model: str, as_of: str | None = None, horizon: int = HORIZON,
                 demand: pd.DataFrame | None = None) -> dict[str, np.ndarray | None]:
    """Point forecasts (logit scale) per skill, using months <= as_of.

    A skill with too few recent mentions gets None: we show no forecast for it.
    """
    if demand is None:
        demand = load_demand(as_of)
    elif as_of is not None:
        demand = demand[demand["month"] <= as_of]
    mentions, _ = wide_tables(demand)
    y = logit_series(demand=demand)
    out: dict[str, np.ndarray | None] = {}
    for skill in y.columns:
        if has_enough_data(mentions[skill].to_numpy()):
            out[skill] = forecast_skill(y[skill].to_numpy(), model, horizon)
        else:
            out[skill] = None
    return out
