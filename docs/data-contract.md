# Data contract: signals -> engine

The ingestion side (Sheng Kuan) writes rows. The engine side (Ee Zhan) reads them. Change this file only when both agree.
`schema_version: 1`. The `hn_hiring` source belongs to the engine side (it is the forecast's training data). All other sources belong to the ingestion side.

## Shared reference files (engine side owns them)
| File | Content | Used by |
|---|---|---|
| `data/taxonomy.json` | `[{ "skill": "Kubernetes", "synonyms": ["k8s"], "pattern": "\\b(kubernetes|k8s)\\b", "sdg": ["8.2"] }]` | Engine tagging, CV extractor (must output these canonical `skill` names) |
| `data/roles.json` | `[{ "id": "data_engineer", "name": "Data Engineer", "title_pattern": "\\bdata[\\s-]+engineers?\\b", "description": "...", "sdg": ["8.2", "16.6"], "sdg_reason": "..." }]`. `title_pattern` is a case-insensitive regex (shortened here); optional `ranked` / `note`. Skill weights are NOT here: they are learned, see `role_profiles.json` | Role match |
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

## Role match files (engine output, UI reads them) - E7
Code: `engine/roles.py`. Build (about 2 minutes): `python -m engine.roles --raw-dir <folder with the raw HN thread JSON>`. Tests: `tests/test_roles.py`. UI: the Roles tab in `app.py`.
A post belongs to a role if its cleaned text matches the role's `title_pattern` (case-insensitive). One post can belong to several roles. Counting rules are the same as `demand_monthly.csv` (top-level, non-deleted, non-empty posts; a post counts once per role and once per skill).
None of these files holds post text. They hold counts, shares, skill names and HN thread ids only.

How profiles are learned (each rule fixes a measured problem):
- **Title masking.** Before skills are tagged in a role post, the matched title span is replaced by spaces. The title cannot create its own skill ("LLM engineer" does not tag LLM / GenAI by itself).
- **Single-role posts only.** Many role posts name 2 or more roles. These tell us little about either role, so profiles use only posts that match exactly ONE role. `n_role_posts` counts all matching posts, `n_single_role_posts` the ones used.
- **Minimum evidence.** A skill must appear in at least 10 single-role posts (`MIN_SKILL_POSTS`), have `p_role >= 0.08` and `lift >= 1.1`. Top 10 by `p_role`.
- **Confidence tier** from `n_single_role_posts`: `solid` (>= 150 AND at least 5 profile skills), `rough` (>= 50 posts but not solid, shown with a note), `not_ranked` (< 50, left out of the ranking). A role can also be switched off with `"ranked": false` in `roles.json` (Analytics Engineer: "Not ranked: too few posts to learn a profile").
- **As-of points.** One profile per as_of point (2023-12, 2024-06, 2024-12, 2025-06, 2025-12, 2026-10), each from the 24 months up to that point. `profile_for(as_of, doc)` picks the latest profile with point <= as_of, so the As-of slider never uses a profile that saw later posts. It raises `ValueError` before the first point.

### `data/roles.json`
`id`, `name`, `title_pattern`, `description`, `sdg` (1 or 2 codes from the taxonomy), `sdg_reason`, and optional `ranked` (default true) and `note`. 9 roles, 8 ranked.

### `data/role_profiles.json`
```json
{
  "schema_version": 2, "generated_at": "2026-10-22T12:00:00Z",
  "params": {"months": 24, "min_p_role": 0.08, "min_lift": 1.1, "min_skill_posts": 10, "top_k": 10, "...": "..."},
  "as_of_points": ["2023-12", "2024-06", "2024-12", "2025-06", "2025-12", "2026-10"],
  "profiles": {
    "2026-10": {
      "as_of": "2026-10", "window": {"from": "2024-11", "to": "2026-10", "months": 24},
      "n_posts_all": 7628, "thread_ids": ["..."],
      "roles": [{
        "role_id": "backend_engineer", "name": "Backend Engineer", "description": "...", "sdg": ["9.c"],
        "n_role_posts": 759, "n_single_role_posts": 445, "window": {"from": "2024-11", "to": "2026-10", "months": 24},
        "tier": "solid", "ranked": true, "note": null,
        "skills": [{"skill": "Python", "weight": 0.21, "p_role": 0.5, "p_all": 0.3, "lift": 1.6, "single_role_posts": 220}],
        "thread_ids": ["..."]
      }]
    }
  }
}
```
| Field | Meaning |
|---|---|
| `p_role` | Share of the role's single-role posts that mention the skill (title masked). |
| `p_all` | Share of all posts in the window that mention the skill (no masking). |
| `lift` | `p_role / p_all`. Above 1 means the role asks for the skill more than the average post. |
| `skills` | Skills passing the three filters above, top 10 by `p_role`, sorted by weight (high to low). May be empty. |
| `weight` | `p_role` divided by the sum of `p_role` over the kept skills, so the weights of one role sum to 1. Learned from the posts, not invented. |
| `tier`, `ranked`, `note` | Confidence tier. `ranked` is false when the tier is `not_ranked` or `roles.json` says so. `note` explains `rough` and `not_ranked`. |
| `thread_ids` | Per role: threads in the window that hold at least one single-role post for it. Per profile: all threads in the window. |

### `data/role_demand_monthly.csv`
Columns: `month, role_id, mentions, n_posts, share`. `mentions` = posts in that month that match the role (single-role or not). `n_posts` = all posts that month (same as `demand_monthly.csv`). One row per month in `hn_threads.csv` and role.

### `data/role_trends.json`
```json
{ "schema_version": 1, "generated_at": "...", "as_of": "2026-10", "partial_month": true, "method": "...",
  "roles": { "backend_engineer": { "trend_label": "Rising", "trend_p": 0.017,
             "mentions_last12": 393, "posts_last12": 3714, "mentions_prev12": 366, "posts_prev12": 3914 } } }
```
`trend_label` uses the same rule as skills (`engine.forecast.trend_label`): Welch t-test on the monthly logit share, last 12 months against the 12 before, p < 0.05 gives `Rising` or `Falling`, else `No clear change`. `null` when there are fewer than 30 mentions in the 24 months. Observed, not a forecast. The committed file equals `build_role_trends(read_demand_rows(role_demand_monthly.csv), roles)`. For an older as_of the app calls `build_role_trends(..., as_of=...)`, which cuts the rows at that month: later data is never used.

### `match_roles(user_skills, role_profiles, skill_scores, role_trends, scenario="moderate", exposure=None, k=None)`
- `user_skills`: set (or list) of canonical skill names, or a dict skill -> years. A plain string raises `TypeError`. Having `TypeScript` counts as having `JavaScript / TypeScript`. If a profile has both rows, the TypeScript weight is added to the combined row, so nobody sees "gap: TypeScript" after picking JS/TS.
- `role_profiles`: ONE profile (from `profile_for`). `skill_scores`: the `skill_scores.json` for the same as_of (from `build_scores(as_of=...)` for a past view). `role_trends`: from `build_role_trends(..., as_of=...)`.
- `exposure`: skill -> `e_s` from `exposure.csv` (`load_exposure`). `k`: from `skill_scores.scenario_params`.
- Returns `{"scenario", "formula", "roles", "low_match", "not_ranked", "unmatched"}`. `unmatched` = user skills that are not in the taxonomy. `not_ranked` lists the roles left out because of the profile (tier or `ranked: false`), with a note.
- **Low match.** A role with `match_score < 0.20` is NOT ranked, so it cannot rank on its outlook alone. It goes to `low_match` (same fields as a ranked role, `rank` is null), sorted by `match_score`, highest first. `roles` can be empty: then the UI says "None of the roles match well yet; pick a target to see the gap" and still lists `low_match`. The limit is `formula.low_match_below` (0.20, team judgement). `low_match_below=0` ranks every role (used in tests).

Per role in `roles` (sorted by `rank_score`; each has `rank` 1..n):
| Field | Meaning |
|---|---|
| `match_score` | Weight of the role's skills the user has / total weight, 0 to 1. |
| `have`, `gap` | The role's skills the user has / lacks, both sorted by weight. Each has `skill`, `weight`, and (gap) `status`, `trend_label`, `stance` from `skill_scores.json`. `have` also has `years`. |
| `future_score` | From the role trend: Rising 1.0, No clear change 0.5, Falling 0.0, unknown 0.5. The same in both scenarios. |
| `rank_score` | `0.7 * match_score + 0.3 * future_score`, in BOTH scenarios. The 0.7 / 0.3 split is team judgement, not fitted to data. `formula` in the output says so. The Fast scenario never changes the rank. |
| `fast_shift` | Fraction, for example `+0.088`: how much the role's demand moves in the Fast scenario relative to Moderate. `-k * sum(weight * e_s)`, the skill rule `fast = moderate * (1 - k * e_s)` applied to the role's weights. An estimate for display only. |
| `outlook` | `trend_label`, `trend_p`, `mentions_*`, `posts_*` and `share_last12`, `share_prev12` of the role. |
| `tier`, `tier_note`, `n_role_posts`, `n_single_role_posts` | Confidence of the profile. |
| `reason` | Plain sentence, for example "You have 4 of its top 7 skills (Python, AWS, PostgreSQL, Docker). Biggest gaps: Go, Kubernetes, Terraform. Role demand: Rising (10.6% of posts vs 9.4% the year before)." |

### `data/role_forecast.json` (role level and band)
Code: `engine/role_forecast.py`. Build: `python -m engine.role_backtest` first, then `python -m engine.role_forecast`. Tests: `tests/test_role_forecast.py`. UI: one line on each role card in the Roles tab (hidden if the file is missing).
It applies the skill machinery of `engine/forecast.py` to the 8 ranked roles in `role_demand_monthly.csv` (`role_id` is renamed to `skill`; no maths is copied). Same series `y = logit((mentions + 0.5) / (n_posts + 1))`, same model choice (naive or naive3 by mean share-scale |error| at h=12 over origins whose target is <= the forecast date), same rolling W=24 symmetric volatility-scaled conformal 80% band (one pooled `q` over the roles), same Welch trend label as `role_trends.json`, same minimum-data rule (mean mentions per month over the last 12 months >= 5).
```json
{ "schema_version": 1, "generated_at": "...", "as_of": "2026-10", "partial_month": true,
  "interval": {"label": "80% target band", "level": 0.8, "model": "naive3", "window_origins": 24,
               "q_h12": 1.55, "model_scores_h12_pp": {"naive": 1.63, "naive3": 1.58},
               "n_roles_pooled": 8, "earliest_supported_as_of": "2023-11"},
  "notes": ["..."], "data_window": {"from": "2019-01", "to": "2026-10"},
  "excluded_roles": [{"role_id": "analytics_engineer", "name": "Analytics Engineer", "reason": "..."}],
  "roles": { "backend_engineer": {
      "name": "Backend Engineer", "status": "ok", "note": null,
      "share_now": {"value": 0.102, "mentions": 76, "posts": 743, "months": ["2026-08", "2026-09", "2026-10"]},
      "level_now": 0.104,
      "forecast_moderate": {"value_12m": 0.104, "low": 0.083, "high": 0.129}, "band_width_pp": 4.7,
      "trend": {"label": "Rising", "p": 0.017, "share_last12": 0.106, "share_prev12": 0.094,
                "mentions_last12": 393, "posts_last12": 3714, "mentions_prev12": 366, "posts_prev12": 3914},
      "sources": [{"name": "Ask HN: Who is hiring? (October 2026)", "url": "...", "date": "2026-10-01"},
                  {"name": "Verity role backtest (data/role_backtest.json)", "url": "data/role_backtest.json", "date": "2026-10-22"}],
      "as_of": "2026-10", "partial_month": true } } }
```
| Field | Meaning |
|---|---|
| `status` | `ok`: a forecast and a band. `low_volume`: mean mentions per month over the last 12 months below 5; counts and trend label only, `forecast_moderate` values and `band_width_pp` are `null`, and `note` says why. Roles have only these two statuses. A role with fewer than 30 mentions in 24 months has a `null` trend label, as in `role_trends.json`. |
| `share_now` | Raw share, pooled over the last 3 months: `mentions / posts` (shown as m/n). Display value. |
| `level_now` | Model-scale level: `inv_logit(mean of the last 3 values of y)`. Change over 12 months is `value_12m - level_now`. Never subtract `share_now.value` from `value_12m`. With naive3 the 12-month value equals `level_now` (a persistence forecast). |
| `forecast_moderate` | `value_12m` and the 80% target band `low` / `high`, as shares. The band is `inv_logit(point +/- q_h12 * sigma)`. It is a rolling conformal target, not a guarantee: see the coverage in `role_backtest.json`. There is no Fast scenario for roles here; `fast_shift` in the role match output stays a labelled estimate. |
| `trend` | Observed Welch label with p and the pooled shares (not a forecast). It equals `role_trends.json` for the same month. |
| `sources` | The HN threads of the last 3 months and `data/role_backtest.json`. |
| `excluded_roles` | Roles that are not ranked in `roles.json` (Analytics Engineer). They are not forecast and do not enter the pooled `q`. |

`role_forecast_for(as_of=None, backtest=None, demand=None, today=None, data_dir=None)` builds the same dict from data with month <= `as_of` only. It writes nothing. The earliest supported `as_of` is 2023-11, as for skills. The Roles tab uses the file for the latest month and calls this function for an older As-of month.

### `data/role_backtest.json` (role backtest)
Code: `engine/role_backtest.py` (`python -m engine.role_backtest`, about 30 seconds). It calls `engine.backtest.run_backtest` on the role table, so the design is the skill design: rolling origins 2021-12 to 2025-10, early 2021-12..2023-10, test 2023-11..2025-10, share-scale MAE in pp at h = 1, 6, 12 for naive, naive3, drift and damped (only naive and naive3 ship), coverage of the 80% target band at h=12 and as a mean over h on test origins with the model choice and `q` re-made at every origin from earlier data, mean band width at h=12, and the trend-label hit rate (pooled share over the next 12 months against the last 12, Rising or Falling only).
The keys of `backtest.json` are kept with `skill` read as `role`: `n_roles_total`, `n_role_origin_pairs` (`early`, `test`, `excluded`), `models.<m>.early_mae_pp` / `test_mae_pp` (`h1`, `h6`, `h12`, `mean_h1_12`), `coverage` (`test_h12`, `test_mean_over_h`, `test_by_h`, `by_share_group`, `test_mean_band_width_h12_pp`, `n_role_origins`), `interval_sensitivity`, `trend_label_hit_rate`, `trend_label_backtest` (`n`, `n_rising`, `n_falling`, `caveat`). Extra keys: `kind` (`"role"`), `role_ids`, `sample_note` and `caveats`.
Small sample: only 8 ranked roles. `n_role_origin_pairs` and `trend_label_backtest.n` are counts of correlated role-origins, not independent tests. Treat the rates as a rough guide. Nothing was tuned on the test origins.

## `data/diff.json` ("what changed and why")
```json
{ "from_run": "2026-10-23T10:00:00Z", "to_run": "2026-10-24T09:00:00Z",
  "changes": [ { "skill": "Kubernetes", "field": "forecast.fast.value_12m", "old": 0.072, "new": 0.069, "because": ["github:123", "rss:abc"] } ] }
```

## Privacy and size
- Commit monthly aggregates, IDs and URLs. Keep raw `text` local (`data/raw/` is in `.gitignore`). The ingestion side commits only aggregates (for example `data/signals_weekly.csv` = week, skill, mentions, source, example ids).
- Strip names, emails and phone numbers from job-post text before any processing.
