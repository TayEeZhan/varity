"""12-month demand forecasts for each skill, on the logit scale.

Input: data/demand_monthly.csv (month, skill, mentions, n_posts, ...).

Series for one skill
    p = (mentions + 0.5) / (n_posts + 1)   share of posts, kept away from 0 and 1
    y = logit(p) = ln(p / (1 - p))         the series every model works on
We fit on this raw monthly series, not on share_smooth. Smoothing makes the
residuals too small, so the bands would be too narrow.

Four candidate models (all four are backtested; production ships naive and naive3).
Each one takes the history y and returns 12 point forecasts:
    naive   the last value, repeated.
    naive3  the mean of the last 3 values, repeated.
    drift   last value + 0.5 * slope * h. The slope is a straight-line fit on the
            last 24 months. The 0.5 shrinks the slope, because trends rarely last.
    damped  exponential smoothing with a damped additive trend, fit on the last
            36 months (statsmodels ExponentialSmoothing).

Interval (v2): rolling, symmetric, volatility-scaled conformal band, logit scale.
    sigma_{s,o}  sample std (ddof=1) of the first differences of y over the 24 months
                 up to and including origin o.
    r            (actual - forecast) / sigma_{s,o}, for origin o, horizon h, skill s.
    q            80th percentile of |r| over the last W=24 origins o with o + h <= t
                 (t = the forecast date), eligible skills only, pooled over skills.
    band         inv_logit(point +/- q * sigma_{s,t}).
band_offsets() is the one function that computes q. The backtest, scores and every
as-of run call it. W=24 was set a priori, to match the 24-month windows.

Model choice (v2): naive or naive3, whichever has the lower mean share-scale absolute
error at h=12 over origins whose 12-month target is <= the forecast date.

Trend label (v2): an OBSERVED label, not a forecast. Welch t-test on the monthly logit
shares, last 12 months against the 12 before.

`as_of` (YYYY-MM): every public function that reads data uses only months up to
and including as_of. Changing a later month never changes an earlier forecast.

Note: the Oct 2026 HN thread was still open when it was fetched (22 Oct 2026), so
the last month is a partial count. Its share is a noisy estimate. We keep it
because the forecast date is the last month in the data.
"""
from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats  # installed together with statsmodels

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEMAND_CSV = DATA_DIR / "demand_monthly.csv"

MODELS = ("naive", "naive3", "drift", "damped")  # all four are backtested
PRODUCTION_MODELS = ("naive", "naive3")  # drift and damped are not shipped
HORIZON = 12
DRIFT_WINDOW = 24  # months used for the drift slope
DRIFT_SHRINK = 0.5  # the slope is multiplied by this
DAMPED_WINDOW = 36  # months used to fit the damped trend model
MIN_MEAN_MENTIONS = 5  # below this (mean per month, last 12 months) we show no forecast
MIN_MENTIONS_24M = 30  # below this (total, last 24 months) a skill is "rare"
SIGMA_WINDOW = 24  # months for the volatility sigma (first differences of y)
INTERVAL_WINDOW = 24  # W: origins used for the conformal quantile (set a priori)
INTERVAL_LEVEL = 0.8  # target coverage of the band
MIN_ORIGINS = 24  # fewest usable origins for band_offsets
TREND_ALPHA = 0.05
TREND_MIN_MENTIONS = 30  # mentions over the 24 trend months needed to label a skill

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


NOWCAST_JSON = DATA_DIR / "nowcast_backtest.json"


def nowcast_y(mentions, n_posts, k: float) -> np.ndarray:
    """Logit series with the last (still open) month blended toward the month before.

    share_last = (m_last + k * s_prev) / (n_last + k), s_prev = smoothed share of the month before.
    A month with n posts so far gets weight n / (n + k), so a thread with 40 posts barely moves the
    series and a full thread nearly replaces the old month. k = 0 leaves the series unchanged.
    k is chosen per day open by engine.nowcast_backtest on past threads cut at day 1, 3, 7 and 14.
    """
    m = np.asarray(mentions, dtype=float).copy()
    n = np.asarray(n_posts, dtype=float).copy()
    if k > 0 and m.size >= 2:
        m[-1] += k * float(smoothed_share(m[-2], n[-2]))
        n[-1] += k
    return logit(smoothed_share(m, n))


def load_nowcast_k(data_dir: Path | str, kind: str, days_open: float | None) -> float:
    """k for "roles" or "skills" at the cut day nearest to days_open (nowcast_backtest.json).

    0 (no blending) when the file is missing or days_open is unknown.
    """
    path = Path(data_dir) / NOWCAST_JSON.name
    try:
        by_day = {float(d): float(k) for d, k in json.loads(path.read_text(encoding="utf-8"))[kind]["k_by_day"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 0.0
    if days_open is None or not by_day:
        return 0.0
    return by_day[min(by_day, key=lambda d: abs(d - days_open))]


def days_open(threads: pd.DataFrame, month: str, today) -> float | None:
    """Days since the HN thread of `month` was posted (created_at in hn_threads.csv), or None."""
    row = threads[threads["month"] == month]
    if row.empty or "created_at" not in row:
        return None
    created = pd.Timestamp(row["created_at"].iloc[0])
    created = created.tz_localize("UTC") if created.tzinfo is None else created
    return max((pd.Timestamp(today) - created).total_seconds() / 86400, 0.0)


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


def skill_status(mentions) -> str:
    """"ok" (>= 5 mentions/month over the last 12 months), else "low_volume" if the
    last 24 months hold >= 30 mentions, else "rare"."""
    m = np.asarray(mentions, dtype=float)
    if has_enough_data(m):
        return "ok"
    return "low_volume" if m[-24:].sum() >= MIN_MENTIONS_24M else "rare"


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
        # Imported here: only the backtest uses the damped model, so the app starts without statsmodels.
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
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


# ---------------------------------------------------------------------------
# Rolling conformal band, model choice, trend label
# ---------------------------------------------------------------------------

def volatility(y_series, window: int = SIGMA_WINDOW) -> float:
    """Sample std (ddof=1) of the first differences of the last `window` values of y.

    NaN if there are fewer than `window` values.
    """
    y = np.asarray(y_series, dtype=float)
    if y.size < window or window < 3:
        return float("nan")
    return float(np.std(np.diff(y[-window:]), ddof=1))


@dataclass(frozen=True)
class ResidualTable:
    """Forecasts, outcomes and volatilities of one model, for every origin.

    Origin i is months[first_origin + i]. Arrays (O origins, S skills, H = 12):
      forecast  (O, S, H)  logit point forecasts; NaN where the skill was not eligible
      actual    (O, S, H)  logit y at the target month; NaN if the target is not in the data
      sigma     (O, S)     volatility at the origin (see volatility())
      eligible  (O, S)     mean mentions over the 12 months up to the origin >= 5
      share_now (O, S)     raw share (sum mentions / sum posts) over the 3 months up to the origin
    """

    model: str
    months: tuple[str, ...]
    skills: tuple[str, ...]
    first_origin: int
    forecast: np.ndarray
    actual: np.ndarray
    sigma: np.ndarray
    eligible: np.ndarray
    share_now: np.ndarray

    @property
    def origins(self) -> tuple[str, ...]:
        return self.months[self.first_origin:]

    def origin_pos(self, month: str) -> int:
        """Row of the table for an origin month."""
        i = self.months.index(month) - self.first_origin
        if i < 0:
            raise ValueError(f"{month} is before the first origin {self.origins[0]}")
        return i

    def scaled_residuals(self) -> np.ndarray:
        """r = (actual - forecast) / sigma, shape (O, S, H). NaN where undefined."""
        with np.errstate(divide="ignore", invalid="ignore"):
            sigma = np.where(self.sigma > 1e-9, self.sigma, np.nan)[..., None]
            return (self.actual - self.forecast) / sigma


def build_residual_tables(demand: pd.DataFrame, models=PRODUCTION_MODELS,
                          horizon: int = HORIZON) -> dict[str, ResidualTable]:
    """One ResidualTable per model, from every origin with SIGMA_WINDOW months of history.

    Forecast, sigma and eligibility at origin o read only months <= o. `actual` reads
    o+1 .. o+h; band_offsets and choose_model keep only targets <= as_of.
    """
    mentions, n_posts = wide_tables(demand)
    y = logit_series(demand=demand)
    months = tuple(y.index)
    skills = tuple(y.columns)
    yv, mv, pv = y.to_numpy(), mentions.to_numpy(float), n_posts.to_numpy(float)
    first = SIGMA_WINDOW - 1
    n_orig = len(months) - first
    if n_orig <= 0:
        raise ValueError(f"need at least {SIGMA_WINDOW} months of data, have {len(months)}")

    shape = (n_orig, len(skills), horizon)
    forecast = {m: np.full(shape, np.nan) for m in models}
    actual = np.full(shape, np.nan)
    sigma = np.full((n_orig, len(skills)), np.nan)
    eligible = np.zeros((n_orig, len(skills)), dtype=bool)
    share_now = np.full((n_orig, len(skills)), np.nan)

    for i in range(n_orig):
        end = first + i + 1  # history = months[:end]
        n_target = min(horizon, len(months) - end)
        for j in range(len(skills)):
            sigma[i, j] = volatility(yv[:end, j])
            share_now[i, j] = mv[end - 3:end, j].sum() / pv[end - 3:end, j].sum()
            if n_target > 0:
                actual[i, j, :n_target] = yv[end:end + n_target, j]
            eligible[i, j] = has_enough_data(mv[:end, j])
            if eligible[i, j]:
                for m in models:
                    forecast[m][i, j] = forecast_skill(yv[:end, j], m, horizon)
    return {m: ResidualTable(m, months, skills, first, forecast[m], actual, sigma,
                             eligible, share_now) for m in models}


def _last_usable_origin(table: ResidualTable, as_of: str, h: int) -> int:
    """Row of the last origin whose h-month target is <= as_of (-1 or less if none)."""
    _check_month("as_of", as_of)
    if as_of not in table.months:
        raise ValueError(f"as_of {as_of} is not a month in the table")
    return table.months.index(as_of) - h - table.first_origin


def earliest_supported(months) -> str:
    """First month at which band_offsets works for every horizon, given the data months.

    The first origin needs 24 months of history (for sigma), and h=12 needs 24 origins whose
    target is <= as_of, so as_of must be at least 23 + 12 + 23 = 58 months after the start.
    For data starting 2019-01 this is 2023-11.
    """
    months = list(months)
    idx = SIGMA_WINDOW - 1 + HORIZON + MIN_ORIGINS - 1
    if idx >= len(months):
        raise ValueError(f"need at least {idx + 1} months of data for any supported as_of, "
                         f"have {len(months)}")
    return months[idx]


def earliest_as_of(table: ResidualTable) -> str:
    """earliest_supported() for the months of a table."""
    return earliest_supported(table.months)


def band_offsets(table: ResidualTable, as_of: str, h: int,
                 window: int | None = INTERVAL_WINDOW) -> float:
    """q = 80th percentile of |scaled residual| at horizon h, using targets <= as_of.

    Takes the last `window` origins o with o + h <= as_of (all of them if window is
    None), eligible skills only, pooled over skills. The half-width of the band on the
    logit scale for skill s is q * sigma_{s,as_of}. The backtest, build_scores and every
    as-of run use this one function, so they cannot differ.
    """
    if not 1 <= h <= table.forecast.shape[2]:
        raise ValueError(f"h must be between 1 and {table.forecast.shape[2]}, got {h}")
    n_usable = _last_usable_origin(table, as_of, h) + 1
    if n_usable < MIN_ORIGINS:
        raise ValueError(
            f"as_of {as_of} is too early for h={h}: {max(n_usable, 0)} usable origins, "
            f"need {MIN_ORIGINS}. Earliest supported as_of is {earliest_as_of(table)}.")
    first = 0 if window is None else max(0, n_usable - window)
    r = np.abs(table.scaled_residuals()[first:n_usable, :, h - 1][table.eligible[first:n_usable]])
    r = r[np.isfinite(r)]
    if r.size == 0:
        raise ValueError(f"no eligible residuals for as_of {as_of}, h={h}")
    return float(np.quantile(r, INTERVAL_LEVEL))


def choice_scores(tables: dict[str, ResidualTable], as_of: str) -> dict[str, float]:
    """Mean share-scale |error| at h=12 per model, over origins whose target is <= as_of."""
    scores = {}
    for name, t in tables.items():
        n_usable = _last_usable_origin(t, as_of, HORIZON) + 1
        if n_usable < 1:
            raise ValueError(f"as_of {as_of} is too early to choose a model "
                             "(no origin with a 12-month target)")
        a = t.actual[:n_usable, :, HORIZON - 1]
        f = t.forecast[:n_usable, :, HORIZON - 1]
        mask = t.eligible[:n_usable] & np.isfinite(a) & np.isfinite(f)
        scores[name] = float(np.abs(inv_logit(a[mask]) - inv_logit(f[mask])).mean())
    return scores


def choose_model(tables: dict[str, ResidualTable], as_of: str) -> str:
    """naive or naive3: lowest choice_scores() (h=12, targets <= as_of). Ties go to the first."""
    scores = choice_scores(tables, as_of)
    return min(scores, key=scores.get)


def trend_label(y_last24, mentions_last24=None) -> tuple[str | None, float | None]:
    """Observed trend: Welch t-test, last 12 months of logit share vs the 12 before.

    Returns (label, p). Label is "Rising" / "Falling" when p < 0.05 (sign of the mean
    difference), otherwise "No clear change". Returns (None, None) if fewer than 24
    months are given, or if mentions_last24 sums to less than 30.
    """
    y = np.asarray(y_last24, dtype=float)
    if y.size < 24:
        return None, None
    y = y[-24:]
    if mentions_last24 is not None:
        if np.asarray(mentions_last24, dtype=float)[-24:].sum() < TREND_MIN_MENTIONS:
            return None, None
    recent, prev = y[12:], y[:12]
    if recent.std(ddof=1) == 0 and prev.std(ddof=1) == 0:
        p = 1.0 if recent.mean() == prev.mean() else 0.0
    else:
        p = float(stats.ttest_ind(recent, prev, equal_var=False).pvalue)
        if not np.isfinite(p):
            p = 1.0
    if p < TREND_ALPHA:
        return ("Rising" if recent.mean() > prev.mean() else "Falling"), p
    return "No clear change", p
