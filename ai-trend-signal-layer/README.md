# AI Trend Signal Ranker (Jev Edition)

Collects AI and tech updates from trusted sources, merges duplicate reports into stories, and outputs a
**ranked list with scores** showing which updates are the most impactful, for CS students and developers.
Design: [ARCHITECTURE_JEV_RANKER.md](ARCHITECTURE_JEV_RANKER.md). The earlier full-app plan
(brief writer, web feed) is [ARCHITECTURE_PLAN.md](ARCHITECTURE_PLAN.md); that code is still here but off the core path.

**Code extracts, Jev decides, code ranks.** No LLM is in the scoring path by default.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m trendsignal rank --force            # collect all sources, rank, print the top 20
```

Output goes to `data/ranked/`:
- `latest.json`, `latest.csv`: the ranked list (format below)
- `ranked-<run_id>.json`: a copy per run
- `skills.json`: weekly skill momentum for SKidea's matching

No keys are needed: without Jev the deterministic formula ranks (the documented fallback).
Add `TYPESAFE_API_KEY` to get Jev's probabilities (see `.env.example`).

| Command | What it does |
|---|---|
| `rank [--no-collect] [--force] [--ranker formula\|jev] [--limit N] [--hours H] [--format table\|json\|csv] [--out DIR]` | Collect, rank, write the files, print the list |
| `run [--force] [--source ID]` | Collect and rank without printing the list |
| `sources` | Source health (ok / stale / disabled) |
| `serve --scheduler` | Re-rank every 15 minutes and rewrite `data/ranked/`; also serves the optional web feed |

## Pipeline

```
sources.yaml → collectors → normalise → cluster ──(borderline pairs)──► Jev: same_story?
                                           │
                                           ▼
                      rules label + category_confidence ──(< 0.5, optional)──► Haiku 5.5
                                           │
                                           ▼
                            feature vector (code only, 21 fields)
                                │                         │
                                ▼                         ▼
                   Jev: tier + impact probs        formula score (fallback)
                                └───────────┬─────────────┘
                                            ▼
                      ranker + hard guardrails → rankings table → JSON / CSV / table
```

| Stage | File | What it does |
|---|---|---|
| Collectors | `trendsignal/collectors/` | RSS/Atom, GitHub releases, arXiv, HF Daily Papers, Hacker News, Bluesky, X, Threads; official APIs only |
| Normalise | `pipeline/normalise.py` | Clean text; one canonical URL per article (arXiv and HF paper links unify) |
| Cluster | `pipeline/cluster.py`, `similarity.py` | URL/hash match, then TF-IDF plus a shared distinctive name; pairs with similarity 0.25–0.6 go to Jev |
| Labels | `pipeline/heuristics.py` | Rule category with `category_confidence` (title match > body match > default), release level, keyword flags |
| Optional Haiku | `pipeline/enrich.py` | Only when `TRENDSIGNAL_HAIKU_FALLBACK=1` and confidence < 0.5; output passes the evidence-quote check |
| Feature builder | `pipeline/features.py` | The flat vector Jev receives (section 5 of the design), stored with every ranking |
| Jev | `decision/jev.py` | Typed questions to TypeSafe's System One API: `tier` (Choice), `impact` (Score), `same_story` (Noul) |
| Formula | `pipeline/score.py` | The deterministic weighted score; always computed |
| Ranker | `decision/ranker.py` | Expected impact, entropy confidence, final score, guardrails, rank order |
| Output | `output.py` | JSON / CSV / table |

### Ranking

With Jev:

```
expected_impact = Σ k · P(impact = k)                         k = 1..5
confidence      = 1 − normalised entropy of impact_probs
final_score     = 100 · [P(must_know) + 0.5 · P(worth_a_look)] · (0.5 + 0.5 · confidence)
tier            = argmax of tier_probs
```

The design writes the score as `0.6·P(must_know) + 0.3·P(worth_a_look)`. That has the same ordering;
dividing by 0.6 puts it on the formula's 0–100 scale, so rows from both can share one list.

**Hard guardrails, applied to both rankers:**
- Superseded releases are Minor.
- Social-only stories are never Must-know.
- Must-know needs an official or research source, or 3 independent reports.
- Must-know is capped at 5 per day.

### Who ranks: the promotion rule

| `TRENDSIGNAL_RANKER` | Jev key set? | Result |
|---|---|---|
| `formula` (default) | no | Formula ranks |
| `formula` | yes | Formula ranks; Jev's probabilities are stored and shown as a **second opinion** |
| `jev` | yes | Jev ranks; any story Jev can't answer (error, > 2 s timeout) falls back to the formula, marked `ranked_by: formula` |

Switch to `jev` only after `python -m eval.metrics` shows Jev beating the formula on the gold set.

### Jev guardrails

- Model pinned to `jev-1.13.0` (aliases like `jev-latest` can move).
- 2-second timeout and no SDK retries.
- Authentication, permission, unknown-model and rate-limit errors stop Jev for the rest of the run.
- Every answer is validated: all tiers present, probabilities sum to 1.
- Answers are cached by a hash of the rounded feature vector, so unchanged stories aren't paid for twice.
- At most 400 calls per run.
- Cost is logged per run (TypeSafe lists $0.042 per million input tokens; output is free).

## Output format

```json
{
  "generated_at": "2026-10-22T12:00:00+08:00",
  "run_id": "20261022T040000-1a2b3c",
  "ranked_by": "jev",
  "stories": [
    {
      "rank": 1,
      "title": "...", "url": "...", "sources": ["OpenAI News", "Hacker News"],
      "tier": "must_know",
      "tier_probs": {"must_know": 0.72, "worth_a_look": 0.23, "minor": 0.05},
      "impact_probs": {"1": 0.0, "2": 0.05, "3": 0.1, "4": 0.35, "5": 0.5},
      "expected_impact": 4.3, "confidence": 0.4, "final_score": 59.4,
      "top_features": ["official source (OpenAI News)", "2 independent reports", "trending 3.1σ on Hacker News"],
      "ranked_by": "jev", "formula_score": 72.9, "notes": []
    }
  ]
}
```

`tier_probs`, `impact_probs` and `confidence` are `null` when the formula ranked a story without a Jev answer.
CSV cells that would start a spreadsheet formula are prefixed with `'`.

## Evaluation (design section 9)

```bash
.venv/Scripts/python -m pytest --cov                          # 180 tests, ~93% coverage, no network
.venv/Scripts/python -m eval.metrics --gold eval/gold_set.csv
```

`eval/metrics.py` reports, for the same run:
- precision@5 and NDCG@10 for the formula's order and for Jev's order;
- the Brier score and a reliability table for `P(must_know)`.

Copy `eval/gold_set_template.csv` to `eval/gold_set.csv`, then label about 150 recent stories with two labellers.

## Models (for the Tech Declaration)

| Use | Model | When |
|---|---|---|
| Tier, impact and same-story decisions | Jev `jev-1.13.0` (TypeSafe AI, `typesafe-sdk` 0.7.5) | When `TYPESAFE_API_KEY` is set |
| Category fallback for unsure stories | Claude Haiku 5.5 (`claude-haiku-5-5`) | Only with `TRENDSIGNAL_HAIKU_FALLBACK=1` |
| Optional prose brief (not core) | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Only with `TRENDSIGNAL_BRIEFS=1` |

## Known limitations

- Jev has not been tested against the live API here: there was no key. The client is built on the
  installed `typesafe-sdk` 0.7.5 types and is tested with that SDK's real response and error classes over a fake transport.
- TypeSafe notes Jev is weak at arithmetic and large noisy inputs; the vector keeps all maths in code
  and stays small.
- Rule categories are rough on some stories; `category_confidence` and the optional Haiku fallback exist for that.
- SQLite and in-process locks suit one instance.
