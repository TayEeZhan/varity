# ML forecaster (step 5): does a real model beat "about the same"?

Status: tested, **not used**. Verdict in `data/ml_backtest.json`: **keep naive3**.
Production forecasting (`engine/scores.py`) is unchanged.

## The 1-minute version (for judges)

- Our production forecast is simple: next year's share of job posts for a skill is about the average of its last 3 months ("naive3").
- A judge may ask: "Why not machine learning?" So we tried it, with a fair test.
- We trained **one** small gradient-boosting model on **all 40 skills together**. It does not predict the share directly. It predicts a **correction** to naive3. If it learns nothing, it gives naive3 back.
- We tested it the way we test everything: we pretend it is a past month, train only on what was known then, and predict 12 months ahead. We did this for 24 test months (2023-11 to 2025-10) and compared with what really happened.
- Result on the test months: the ML model was **worse**. Its average error was 2.06 percentage points. naive3 had 1.66. Plain "last month" had 1.81. The 95% interval of the difference does not touch zero, so this is not luck.
- Why: 12 months ahead, job demand is close to "no change". There are few skills (about 25 with enough data) and few independent months, so the model learns patterns that do not repeat. On its own training data its error was 0.98, on new data 2.06. That gap is overfitting.
- So we keep naive3. We say this in the pitch as an honest finding: we tested ML, and the simple method won.

## What the model is

- **Target:** the change in `y` over 12 months, relative to naive3. Here `y = logit((mentions + 0.5) / (posts + 1))`, the same series as the production forecast.
- **Prediction:** `naive3 + model(features)`. The model only learns a correction.
- **Model:** scikit-learn `HistGradientBoostingRegressor` (many small decision trees, added one by one). Depth 3, learning rate 0.05, 200 trees, L2 regularisation, fixed random seed, runs on CPU in about 0.3 s. Same input gives same output.
- **One pooled model:** all skills share the same model. A training example is one (skill, origin month) pair.
- **No look-ahead:** for a forecast made in month `t`, the training examples are the pairs whose 12-month outcome was already known at `t`. A skill must also pass the production data rule (mean 5 or more mentions per month over the last 12 months).

## Features (what the model sees at month t)

| Group | Features |
|---|---|
| Recent level | last value, mean of last 3 / 6 / 12 months of `y` |
| Trend | slope of `y` over 6, 12 and 24 months; change vs 12 months ago |
| Noise | volatility (std of month-to-month changes, 24 months) |
| Size | current share, log of mean mentions (12 months) |
| AI context | level of the "AI mentioned" series, and its 12-month change |
| Calendar | month of the year |
| Skill type | category (language, framework, data, cloud/devops, AI/ML, practice) |
| Exposure | `ai_exposure` and `e_s` from `exposure.csv` |
| Optional gaps | last minus mean3, mean3 minus mean12 (chosen on EARLY data only) |
| Placeholder | `ext_momentum`, empty (NaN) for now |

Caveat: `ai_exposure` and `e_s` are **not time-cut**. They come from the 2026-06 release and are the same at every past month.

### Plugging in Sheng Kuan's ranker momentum

Pass a table `ext_momentum` (rows = months `YYYY-MM`, columns = skill names) to `build_panel(...)` or `forecast_h12(...)` in `engine/ml_forecast.py`. The value in row `m` must be what the ranker knew in month `m`, using data up to `m` only. Gaps (NaN) are fine. While the whole column is empty it is left out of the fit (scikit-learn 1.9.1 crashes on a fully empty column; we found this in testing). When it has values it joins the fit automatically. Then run `python -m engine.ml_backtest` and read the new verdict.

## How it was tested

Same idea as `engine/backtest.py`: rolling origins. At each origin we retrain from scratch on data known at that time, predict 12 months ahead, and compare with the real value. Error is measured on the share scale in percentage points (pp), on the **same skill-origin pairs** for all methods.

- EARLY origins: 2021-12 to 2023-10. TEST origins: 2023-11 to 2025-10.
- Settings were chosen on EARLY only: a grid of 16 variants (feature set, loss, L2, leaf size), scored on the 12 EARLY origins that have at least 12 training months behind them. TEST was never used to tune.
- The 95% interval resamples skills (not rows), because the errors of one skill are linked over time.
- Rule fixed in advance: **promote only if the lower end of the 95% interval of the TEST gain over naive3 is above 0.**
- Leak test: after scrambling every month after the origin, the prediction is identical. Passed at 3 test origins.

## Result (h = 12 months, MAE in pp, lower is better)

| Period | Pairs | ML | naive3 | naive | Gain vs naive3 (95% CI) |
|---|---|---|---|---|---|
| EARLY, all origins | 689 | 1.833 | 1.548 | 1.612 | -0.286 (-0.440, -0.150) |
| EARLY, 12 mature origins | 346 | 1.692 | 1.440 | 1.563 | -0.251 (-0.420, -0.103) |
| **TEST** | 616 | **2.064** | **1.661** | 1.806 | **-0.403 (-0.622, -0.209)** |

Gain = naive3 error minus ML error. Negative means ML is worse. On TEST the gain over plain naive is also negative: -0.258 (-0.481, -0.054).

- ML lost to naive3 in every category on TEST (cloud/devops 1.93 vs 1.46, language 2.12 vs 1.69, data 1.64 vs 1.41, framework 2.39 vs 1.91, AI/ML 2.46 vs 2.16).
- ML lost on EARLY too, for all 16 variants. The tuned variant was the best of a bad set. The pre-specified default is even worse on TEST (2.13).
- What the model leans on most (in-sample permutation importance): AI-context level, skill category, AI-context 12-month change, 24-month slope, last value. The AI-context level behaves like a clock (it rises all through the period), so the model can memorise "what happened in which year". That does not carry over to new years.

## Why we do not use it

The test says it is worse, and the interval excludes zero. With about 25 usable skills and a few dozen independent months, a flexible model has more freedom than the data can support. The simple average is hard to beat at 12 months because most of the movement is noise. This agrees with our earlier result, where the trend models (drift, damped) were also worse than naive.

When to look again: more months of data, or an outside signal such as the ranker momentum. The code is ready for that (`ext_momentum`).

## Limits

- Few independent test points. The bootstrap accounts for skill clustering, but the true sample is still small.
- Training pairs from nearby origins overlap heavily.
- The first 3 EARLY origins have too few training rows (under 100) for a model, so they use naive3.
- The last target month (2026-10) comes from a thread that was still open when fetched.
- Importance is measured on the training set, as specified. It shows what the model uses, not what generalises.

## Files

- `engine/ml_forecast.py`: features, training, prediction (`forecast_h12`).
- `engine/ml_backtest.py`: the test. Run `python -m engine.ml_backtest`. Takes about 80 s with a full retrain at every origin.
- `data/ml_backtest.json`: all numbers.
- `tests/test_ml_forecast.py`: no-leak, training set, determinism, `naive3 + correction`, `ext_momentum`, verdict rule.
