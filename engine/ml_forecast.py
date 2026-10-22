"""Machine-learning 12-month forecaster: one pooled model, a correction on top of naive3.

Status: EXPERIMENT. Production forecasting (engine/scores.py) is unchanged. The backtest
in engine/ml_backtest.py decides whether this model is worth promoting.

Design (residual-on-naive3)
    y = logit((mentions + 0.5) / (n_posts + 1))      same series as engine/forecast.py
    naive3_t   = mean of the last 3 values of y up to the origin t
    target     = y[t + 12] - naive3_t                the 12-month-ahead CHANGE vs naive3
    prediction = naive3_t + model(features at t)
So the model only learns a correction. If it learns nothing, it returns naive3.

ONE global model is trained on all skills together (pooled). A training row is a pair
(skill, origin s). An origin t may only use rows whose target month s + 12 <= t, so no
outcome after t is ever seen. Skills must pass the production eligibility rule
(has_enough_data: mean mentions over the last 12 months >= 5) at the row's origin.

Model: sklearn HistGradientBoostingRegressor (CPU, small): max_depth 3, learning_rate 0.05,
max_iter 200, L2 regularisation, fixed random_state, no early stopping, so results repeat.

Features at origin t (the feature builder is given only history up to t, so it cannot read
the future; see tests/test_ml_forecast.py):
    y_last, y_mean3, y_mean6, y_mean12      lags of y
    slope6, slope12, slope24                least-squares slope of y over 6/12/24 months
    vol24                                   std (ddof=1) of first differences of y, 24 months
    yoy_change                              y_t - y_{t-12}
    share_level                             raw share, sum mentions / sum posts, last 3 months
    log_mean_mentions12                     log(1 + mean mentions per month, last 12 months)
    ai_level, ai_change12                   AI-context series (logit share, mean of last 3
                                            months) and its change vs 12 months earlier
    month_of_year                           1..12, month of the origin
    cat_<category>                          one-hot category from data/taxonomy.json
    ai_exposure, e_s                        from data/exposure.csv. NOT time-cut: one value
                                            per skill, from the 2026-06 release, used at every
                                            origin. This is a look-ahead of the source data,
                                            not of the demand series.
    ext_momentum                            PLACEHOLDER, NaN for now (see below)
Optional "gap" features (feature_set="gaps", chosen on EARLY only):
    gap_last_mean3 = y_last - y_mean3 ,  gap_mean3_mean12 = y_mean3 - y_mean12

Plugging in Sheng Kuan's ranker momentum
    Pass ext_momentum= a DataFrame (index = months "YYYY-MM", columns = skill names) to
    build_panel() / forecast_h12(). Value at row (month m, skill s) must be what the ranker
    knew on month m, using data up to m only (point-in-time). The panel reads the value at
    the origin month. Missing cells stay NaN, which gradient boosting handles. While the
    column is all NaN in the training rows it is left out of the fit (sklearn 1.9.1 raises
    an error on a fully empty column); it joins the fit automatically once it has values.
    Then re-run `python -m engine.ml_backtest` and read the new verdict.

`as_of` (YYYY-MM): forecast_h12 only reads months <= as_of.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from engine.forecast import (
    DATA_DIR,
    HORIZON,
    SIGMA_WINDOW,
    has_enough_data,
    inv_logit,
    load_demand,
    logit,
    smoothed_share,
    volatility,
    wide_tables,
    _check_month,
)

AI_CONTEXT_CSV = DATA_DIR / "ai_context_monthly.csv"
EXPOSURE_CSV = DATA_DIR / "exposure.csv"
TAXONOMY_JSON = DATA_DIR / "taxonomy.json"

CATEGORIES = ("ai_ml", "cloud_devops", "data", "framework", "language", "practice")
FIRST_ORIGIN_IDX = SIGMA_WINDOW - 1  # 24 months of history are needed for vol24 and slope24
MIN_TRAIN_ROWS = 100  # fewer training rows than this: no model, prediction = naive3
EXT_COLUMN = "ext_momentum"

BASE_FEATURES = (
    "y_last", "y_mean3", "y_mean6", "y_mean12",
    "slope6", "slope12", "slope24",
    "vol24", "yoy_change", "share_level", "log_mean_mentions12",
    "ai_level", "ai_change12", "month_of_year",
    *[f"cat_{c}" for c in CATEGORIES],
    "ai_exposure", "e_s",
    EXT_COLUMN,
)
GAP_FEATURES = ("gap_last_mean3", "gap_mean3_mean12")


@dataclass(frozen=True)
class MLConfig:
    """Hyperparameters of the pooled model. Defaults are the pre-specified setup."""

    max_depth: int = 3
    learning_rate: float = 0.05
    max_iter: int = 200
    l2_regularization: float = 1.0
    min_samples_leaf: int = 20
    loss: str = "squared_error"
    feature_set: str = "base"  # "base" or "gaps"
    random_state: int = 0

    def __post_init__(self):
        if self.feature_set not in ("base", "gaps"):
            raise ValueError(f"feature_set must be 'base' or 'gaps', got {self.feature_set!r}")

    def as_dict(self) -> dict:
        return asdict(self)


def feature_columns(config: MLConfig = MLConfig()) -> list[str]:
    """Feature names, in the order the model sees them."""
    cols = list(BASE_FEATURES)
    if config.feature_set == "gaps":
        cols += list(GAP_FEATURES)
    return cols


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_ai_context(as_of: str | None = None, path: Path | str = AI_CONTEXT_CSV) -> pd.DataFrame:
    """AI-context table (month, mentions, n_posts, ...), months <= as_of only."""
    ai = pd.read_csv(path)
    if as_of is not None:
        _check_month("as_of", as_of)
        ai = ai[ai["month"] <= as_of]
    return ai.reset_index(drop=True)


def load_skill_info(taxonomy_path: Path | str = TAXONOMY_JSON,
                    exposure_path: Path | str = EXPOSURE_CSV) -> pd.DataFrame:
    """One row per skill: category (taxonomy.json), ai_exposure and e_s (exposure.csv)."""
    tax = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
    category = pd.Series({t["skill"]: t["category"] for t in tax}, name="category")
    expo = pd.read_csv(exposure_path).set_index("skill")[["ai_exposure", "e_s"]]
    info = pd.concat([category, expo], axis=1)
    unknown = set(info["category"].dropna()) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"unknown categories {sorted(unknown)}, expected {CATEGORIES}")
    return info


def ai_logit_series(ai: pd.DataFrame, months) -> np.ndarray:
    """logit of the smoothed AI-context share, aligned to `months` (the demand months)."""
    ai = ai.set_index("month")
    missing = [m for m in months if m not in ai.index]
    if missing:
        raise ValueError(f"ai_context is missing months, first: {missing[0]}")
    ai = ai.loc[list(months)]
    return logit(smoothed_share(ai["mentions"].to_numpy(), ai["n_posts"].to_numpy()))


# ---------------------------------------------------------------------------
# Feature builder: given ONLY the history up to the origin
# ---------------------------------------------------------------------------

def _slope(y: np.ndarray, n: int) -> float:
    seg = y[-n:]
    return float(np.polyfit(np.arange(seg.size), seg, 1)[0])


def features_at_origin(y_hist, mentions_hist, posts_hist, ai_hist, month: str, category: str,
                       ai_exposure: float, e_s: float, ext_value: float = np.nan) -> dict:
    """Feature dict for one skill at one origin.

    Every *_hist argument holds months up to and including the origin (oldest first).
    The function receives nothing later, so it cannot use the future.
    Needs at least 24 months of history.
    """
    y = np.asarray(y_hist, dtype=float)
    m = np.asarray(mentions_hist, dtype=float)
    p = np.asarray(posts_hist, dtype=float)
    a = np.asarray(ai_hist, dtype=float)
    if y.size < SIGMA_WINDOW:
        raise ValueError(f"need at least {SIGMA_WINDOW} months of history, have {y.size}")
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}")
    y_mean3, y_mean12 = float(y[-3:].mean()), float(y[-12:].mean())
    feats = {
        "y_last": float(y[-1]),
        "y_mean3": y_mean3,
        "y_mean6": float(y[-6:].mean()),
        "y_mean12": y_mean12,
        "slope6": _slope(y, 6),
        "slope12": _slope(y, 12),
        "slope24": _slope(y, 24),
        "vol24": volatility(y, SIGMA_WINDOW),
        "yoy_change": float(y[-1] - y[-13]),
        "share_level": float(m[-3:].sum() / p[-3:].sum()),
        "log_mean_mentions12": float(np.log1p(m[-12:].mean())),
        "ai_level": float(a[-3:].mean()),
        "ai_change12": float(a[-3:].mean() - a[-15:-12].mean()),
        "month_of_year": int(month[5:7]),
        "ai_exposure": float(ai_exposure),
        "e_s": float(e_s),
        EXT_COLUMN: float(ext_value),
        "gap_last_mean3": float(y[-1] - y_mean3),
        "gap_mean3_mean12": float(y_mean3 - y_mean12),
    }
    for c in CATEGORIES:
        feats[f"cat_{c}"] = 1.0 if c == category else 0.0
    return feats


def build_panel(demand: pd.DataFrame, ai: pd.DataFrame, skill_info: pd.DataFrame,
                ext_momentum: pd.DataFrame | None = None, horizon: int = HORIZON) -> pd.DataFrame:
    """One row per (skill, origin) for every origin with 24 months of history.

    Columns: skill, origin, origin_idx, target_idx, eligible, naive3, y_actual (y at
    origin + horizon, NaN if not in the data), target_change (= y_actual - naive3), and all
    features. Each row's features come from history up to its origin only. `y_actual` and
    `target_change` look ahead, so use training_rows() / predict_at(), which filter on the
    target month, never these columns directly.
    """
    mentions, n_posts = wide_tables(demand)
    months = list(mentions.index)
    skills = list(mentions.columns)
    yv = logit(smoothed_share(mentions.to_numpy(float), n_posts.to_numpy(float)))
    mv, pv = mentions.to_numpy(float), n_posts.to_numpy(float)
    ai_y = ai_logit_series(ai, months)
    missing = [s for s in skills if s not in skill_info.index or skill_info.loc[s].isna().any()]
    if missing:
        raise ValueError(f"skill_info is missing skills: {missing[:3]}")
    ext = None
    if ext_momentum is not None:
        ext = ext_momentum.reindex(index=months, columns=skills)

    rows = []
    for t in range(FIRST_ORIGIN_IDX, len(months)):
        end = t + 1
        for j, skill in enumerate(skills):
            info = skill_info.loc[skill]
            ext_value = np.nan if ext is None else ext.iat[t, j]
            f = features_at_origin(yv[:end, j], mv[:end, j], pv[:end, j], ai_y[:end], months[t],
                                   info["category"], info["ai_exposure"], info["e_s"], ext_value)
            y_actual = yv[t + horizon, j] if t + horizon < len(months) else np.nan
            naive3 = f["y_mean3"]
            rows.append({
                "skill": skill, "category": info["category"], "origin": months[t],
                "origin_idx": t, "target_idx": t + horizon,
                "eligible": bool(has_enough_data(mv[:end, j])),
                "naive3": naive3, "y_actual": y_actual, "target_change": y_actual - naive3,
                **f,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Training and prediction
# ---------------------------------------------------------------------------

def training_rows(panel: pd.DataFrame, as_of: str) -> pd.DataFrame:
    """Eligible (skill, origin s) rows whose target month s+12 is <= as_of.

    The filter is on the target month, so no outcome after as_of can enter training.
    """
    _check_month("as_of", as_of)
    hit = panel.loc[panel["origin"] == as_of, "origin_idx"]
    if hit.empty:
        raise ValueError(f"as_of {as_of} is not an origin month of the panel")
    last_idx = int(hit.iloc[0])
    mask = panel["eligible"] & (panel["target_idx"] <= last_idx) & panel["target_change"].notna()
    return panel[mask]


@dataclass
class FittedCorrector:
    """A fitted model plus the exact columns it was trained on."""

    model: HistGradientBoostingRegressor | None
    columns: list[str]
    config: MLConfig
    n_train_rows: int
    as_of: str

    def correction(self, X: pd.DataFrame) -> np.ndarray:
        """Predicted 12-month change vs naive3. Zeros if no model was trained."""
        if self.model is None:
            return np.zeros(len(X))
        return self.model.predict(X[self.columns])


def fit_corrector(panel: pd.DataFrame, as_of: str, config: MLConfig = MLConfig()) -> FittedCorrector:
    """Train the pooled model with every row whose target month is <= as_of."""
    train = training_rows(panel, as_of)
    wanted = feature_columns(config)
    # sklearn 1.9.1 cannot fit a column that is NaN in every row (ext_momentum today)
    columns = [c for c in wanted if train[c].notna().any()] if len(train) else wanted
    if len(train) < MIN_TRAIN_ROWS:
        return FittedCorrector(None, columns, config, len(train), as_of)
    model = HistGradientBoostingRegressor(
        loss=config.loss, learning_rate=config.learning_rate, max_iter=config.max_iter,
        max_depth=config.max_depth, l2_regularization=config.l2_regularization,
        min_samples_leaf=config.min_samples_leaf, early_stopping=False,
        random_state=config.random_state,
    )
    model.fit(train[columns], train["target_change"])
    return FittedCorrector(model, columns, config, len(train), as_of)


def predict_at(panel: pd.DataFrame, fitted: FittedCorrector, origin: str) -> pd.DataFrame:
    """h=12 forecast (logit scale) for every eligible skill at `origin`.

    Columns: skill, naive3, correction, pred_y = naive3 + correction.
    """
    rows = panel[(panel["origin"] == origin) & panel["eligible"]]
    if rows.empty:
        raise ValueError(f"no eligible skills at origin {origin}")
    corr = fitted.correction(rows)
    out = rows[["skill", "naive3"]].copy()
    out["correction"] = corr
    out["pred_y"] = out["naive3"] + out["correction"]
    return out.reset_index(drop=True)


def forecast_h12(as_of: str, config: MLConfig = MLConfig(), demand: pd.DataFrame | None = None,
                 ai: pd.DataFrame | None = None, skill_info: pd.DataFrame | None = None,
                 ext_momentum: pd.DataFrame | None = None) -> dict[str, float | None]:
    """ML point forecast at h=12 (logit scale) per skill, from months <= as_of only.

    A skill that fails the production eligibility rule gets None (no forecast).
    The data is cut at as_of BEFORE anything is built, so a later month cannot matter.
    """
    _check_month("as_of", as_of)
    demand = load_demand(as_of) if demand is None else demand[demand["month"] <= as_of]
    ai = load_ai_context(as_of) if ai is None else ai[ai["month"] <= as_of]
    skill_info = load_skill_info() if skill_info is None else skill_info
    if ext_momentum is not None:
        ext_momentum = ext_momentum.loc[ext_momentum.index <= as_of]
    panel = build_panel(demand, ai, skill_info, ext_momentum)
    fitted = fit_corrector(panel, as_of, config)
    pred = predict_at(panel, fitted, as_of)
    out: dict[str, float | None] = {s: None for s in panel["skill"].unique()}
    out.update(dict(zip(pred["skill"], pred["pred_y"].astype(float))))
    return out


def share_forecast(pred_y) -> np.ndarray:
    """Logit forecast -> share (0..1)."""
    return inv_logit(pred_y)
