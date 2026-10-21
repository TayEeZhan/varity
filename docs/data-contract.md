# Data contract: signals -> engine

The ingestion side (Sheng Kuan) writes rows. The engine side (Ee Zhan) reads them. Change this file only when both agree.
`schema_version: 1`. The `hn_hiring` source belongs to the engine side (it is the forecast's training data). All other sources belong to the ingestion side.

## Shared reference files (engine side owns them)
| File | Content | Used by |
|---|---|---|
| `data/taxonomy.json` | `[{ "skill": "Kubernetes", "synonyms": ["k8s"], "pattern": "\\b(kubernetes|k8s)\\b", "sdg": ["8.2"] }]` | Engine tagging, CV extractor (must output these canonical `skill` names) |
| `data/roles.json` | `[{ "role": "Data Engineer", "skills": {"SQL": 1.0, "Python": 0.8} }]` | Role match |
| `data/resources.json` | `[{ "skill": "SQL", "title": "...", "url": "...", "minutes": 45, "cost": "free", "hrd_corp": false, "checked": "2026-10-23" }]` | Pathway. Ingestion side fills and verifies it |

## `data/profile.json` (CV extractor output)
```json
{ "name": "Aina (synthetic)", "skills": [ { "skill": "Python", "evidence_quote": "3 years building Flask APIs", "years": 3 } ], "target_role": null }
```
A skill without an exact `evidence_quote` from the CV is dropped. The user can edit the list and set `target_role`.

## `data/raw/signals.jsonl` (local only, gitignored: it holds raw text)
One JSON object per line. One row = one dated item from one source.

| Field | Type | Required | Example | Note |
|---|---|---|---|---|
| `id` | string | yes | `hn:41234567` | `<source>:<native id>`. Must be stable, so re-runs do not make duplicates. |
| `source` | string | yes | `hn_hiring` | One of: `hn_hiring`, `hn_story`, `github`, `arxiv`, `hf`, `rss`. (No Bluesky, X, LinkedIn or JobStreet: personal data and terms of service.) |
| `kind` | string | yes | `job_post` | One of: `job_post`, `news`, `release`, `repo`, `paper`, `post` |
| `url` | string | yes | `https://news.ycombinator.com/item?id=41234567` | The citation shown to the user |
| `title` | string | no | `Acme is hiring ML engineers` | |
| `text` | string | yes | `We use Python, dbt and Snowflake...` | Plain text, max 5000 chars |
| `published_at` | string | yes | `2026-10-01T00:00:00Z` | ISO 8601, UTC. Date of the item, not of the fetch |
| `fetched_at` | string | yes | `2026-10-22T09:15:00Z` | ISO 8601, UTC |
| `metrics` | object | no | `{"stars": 1200, "points": 340}` | Source-specific numbers |
| `location` | string | no | `Remote` / `Kuala Lumpur` | For job posts, if given |

Rules:
- No personal data. Do not store author names or profile links for posts from individuals.
- Keep the raw `text`. The engine does skill tagging, so the scraper does not need to.
- Append only. If an item changes, write a new row with a new `fetched_at`.

## `data/skill_scores.json` (engine output, UI reads it)
```json
{
  "schema_version": 1,
  "generated_at": "2026-10-23T10:00:00Z",
  "as_of": "2026-10",
  "partial_month": true,
  "scenario_params": {"k": 2},
  "interval": {"label": "80% target band", "level": 0.8, "model": "naive3", "window_origins": 24,
               "q_h12": 1.455, "earliest_supported_as_of": "2023-11"},
  "notes": ["exposure.csv (Anthropic Economic Index 2026-06) is not time-cut: the fast scenario uses the same exposure for every as_of.",
            "trend_label is observed (last 12 months against the 12 before), not a forecast."],
  "data_window": {"from": "2019-01", "to": "2026-10"},
  "skills": [
    {
      "skill": "Kubernetes",
      "sdg": ["8.2"],
      "demand_share_latest": 0.071,
      "mentions_last3": 53,
      "posts_last3": 743,
      "level_now": 0.069,
      "demand_slope": 0.12,
      "momentum": null,
      "ai_exposure": 0.41,
      "stance": "neutral",
      "status": "ok",
      "note": null,
      "trend_label": "Rising",
      "trend_p": 0.004,
      "mentions_last12": 210,
      "posts_last12": 3714,
      "mentions_prev12": 150,
      "posts_prev12": 3914,
      "forecast": {
        "moderate": {"value_12m": 0.069, "low": 0.052, "high": 0.091},
        "fast":     {"value_12m": 0.064, "low": 0.048, "high": 0.084}
      },
      "scenario_shift_pp": -0.5,
      "band_width_pp": 3.9,
      "evidence": ["hn:41234567"],
      "sources": [
        {"name": "Ask HN: Who is hiring? (October 2026)", "url": "https://news.ycombinator.com/item?id=41234567", "date": "2026-10-01"},
        {"name": "Anthropic Economic Index (release 2026-06-26)", "url": "https://huggingface.co/datasets/Anthropic/EconomicIndex", "date": "2026-06-26"},
        {"name": "Verity backtest (rolling conformal, naive3)", "url": "data/backtest.json", "date": "2026-10-21"}
      ]
    },
    {
      "skill": "Kafka",
      "sdg": ["8.2"],
      "demand_share_latest": 0.023,
      "mentions_last3": 17,
      "posts_last3": 743,
      "level_now": 0.023,
      "demand_slope": -0.06,
      "momentum": null,
      "ai_exposure": 0.61,
      "stance": "neutral",
      "status": "low_volume",
      "note": "Too few posts to forecast; observed counts shown.",
      "trend_label": "No clear change",
      "trend_p": 0.21,
      "mentions_last12": 50,
      "posts_last12": 3714,
      "mentions_prev12": 66,
      "posts_prev12": 3914,
      "forecast": {
        "moderate": {"value_12m": null, "low": null, "high": null},
        "fast":     {"value_12m": null, "low": null, "high": null}
      },
      "scenario_shift_pp": null,
      "band_width_pp": null,
      "evidence": ["hn:41234567"],
      "sources": []
    }
  ]
}
```
Numbers above are examples only. `sources` is shortened in the example. A real file has the last 3 HN threads, then AEI, then the backtest entry. `schema_version` is still 1. The value `insufficient_data` of `status` no longer exists: it is now `low_volume` or `rare`.

Fields (per skill, all always present):
| Field | Meaning |
|---|---|
| `status` | `ok`: mean >= 5 mentions per month over the last 12 months, so a forecast exists. `low_volume`: below that, but >= 30 mentions in the last 24 months: no forecast, no scenario, no band. Show the observed counts and the trend label, with `note` ("Too few posts to forecast; observed counts shown."). `rare`: < 30 mentions in 24 months: nothing reliable to show, `trend_label` is null. |
| `demand_share_latest` | RAW share for display: `mentions_last3 / posts_last3` (pooled over the last 3 months). |
| `mentions_last3`, `posts_last3` | The two counts behind `demand_share_latest`. |
| `level_now` | MODEL-scale level today: `inv_logit(mean(y[-3:]))`, y = logit of the smoothed share. |
| `demand_slope` | Straight-line slope of the raw monthly share over the last 24 months, in percentage points per year. Observed. |
| `forecast.moderate` | `value_12m` = the chosen model's 12-month point forecast (naive or naive3), `low` / `high` = the 80% target band. Shares between 0 and 1. All null unless `status` is `ok`. |
| `forecast.fast` | `moderate * (1 - 2 * e_s)` on the value and both band ends, clipped to [0, 1]. `e_s` = the skill's AI exposure minus the mean over the 40 skills. All null unless `status` is `ok`. |
| `scenario_shift_pp` | `(fast.value_12m - moderate.value_12m) * 100`. `ok` only, else null. |
| `band_width_pp` | `(moderate.high - moderate.low) * 100`. `ok` only, else null. If `abs(scenario_shift_pp) < band_width_pp / 2`, the UI can say the fast scenario is inside the band. |
| `trend_label` | OBSERVED, not a forecast. Welch t-test on the monthly logit shares, last 12 months against the 12 before. p < 0.05: `"Rising"` or `"Falling"` (sign of the mean difference), else `"No clear change"`. `null` if the skill has < 30 mentions over those 24 months. |
| `trend_p` | The Welch p-value. Null when `trend_label` is null. |
| `mentions_last12`, `posts_last12`, `mentions_prev12`, `posts_prev12` | Pooled counts for the last 12 months and the 12 before. Share = mentions / posts. |
| `note` | Text for the UI when `status` is not `ok`, else null. |

Top level:
| Field | Meaning |
|---|---|
| `partial_month` | `true` if the last month in the data is the current calendar month (UTC). Its HN thread is still open, so its counts are partial. The UI should say so. |
| `interval` | Describes the band: `label` ("80% target band"), `level`, the chosen `model`, `window_origins` (24), `q_h12` (the h=12 multiplier), `earliest_supported_as_of`. |
| `notes` | Plain-text caveats. Includes: `exposure.csv` (AEI 2026-06) is not time-cut. |

Scale rule: never subtract `demand_share_latest` (raw) from `forecast.*.value_12m` (model scale). Any change is `value_12m - level_now`.

How the numbers are made:
- Model: naive (last value) or naive3 (mean of the last 3 values) on the logit series. The one with the lower mean share-scale error at h=12 over origins whose 12-month target is <= `as_of` is used. Drift and damped are not shipped. Their backtest numbers stay in `data/backtest.json`.
- Band: rolling, symmetric, volatility-scaled conformal band. `sigma` = sample std (ddof=1) of the first differences of the logit series over 24 months. `q` = 80th percentile of `|actual - forecast| / sigma` over the last 24 origins whose target is <= `as_of`. Band = `inv_logit(point +/- q * sigma)`. The code is `band_offsets()` in `engine/forecast.py`. It is the 80% target band: coverage on test origins is in `data/backtest.json` (`coverage`).
- `as_of`: `build_scores(as_of)` uses only data with target <= `as_of`. The earliest supported `as_of` is the first month with 24 usable origins (2023-11 for data from 2019-01). Earlier values raise an error. `exposure.csv` is not time-cut.

## `data/diff.json` ("what changed and why")
```json
{ "from_run": "2026-10-23T10:00:00Z", "to_run": "2026-10-24T09:00:00Z",
  "changes": [ { "skill": "Kubernetes", "field": "forecast.fast.value_12m", "old": 0.072, "new": 0.069, "because": ["github:123", "rss:abc"] } ] }
```

## Privacy and size
- Commit monthly aggregates, IDs and URLs. Keep raw `text` local (`data/raw/` is in `.gitignore`). The ingestion side commits only aggregates (for example `data/signals_weekly.csv` = week, skill, mentions, source, example ids).
- Strip names, emails and phone numbers from job-post text before any processing.
