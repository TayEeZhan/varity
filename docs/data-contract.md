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
  "scenario_params": {"k": 0.5},
  "data_window": {"from": "2019-01", "to": "2026-10"},
  "skills": [
    {
      "skill": "Kubernetes",
      "sdg": ["8.2"],
      "demand_share_latest": 0.071,
      "demand_slope": 0.0012,
      "momentum": 0.34,
      "ai_exposure": 0.41,
      "forecast": {
        "moderate": {"value_12m": 0.078, "low": 0.066, "high": 0.090},
        "fast":     {"value_12m": 0.072, "low": 0.058, "high": 0.087}
      },
      "evidence": ["hn:41234567", "arxiv:2410.01234"],
      "sources": [{"name": "HN Who is hiring", "url": "...", "date": "2026-10-01"}]
    }
  ]
}
```
Numbers above are examples only.

## `data/diff.json` ("what changed and why")
```json
{ "from_run": "2026-10-23T10:00:00Z", "to_run": "2026-10-24T09:00:00Z",
  "changes": [ { "skill": "Kubernetes", "field": "forecast.fast.value_12m", "old": 0.072, "new": 0.069, "because": ["github:123", "rss:abc"] } ] }
```

## Privacy and size
- Commit monthly aggregates, IDs and URLs. Keep raw `text` local (`data/raw/` is in `.gitignore`). The ingestion side commits only aggregates (for example `data/signals_weekly.csv` = week, skill, mentions, source, example ids).
- Strip names, emails and phone numbers from job-post text before any processing.
