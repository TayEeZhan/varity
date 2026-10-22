# New-skill discovery

**Problem:** the taxonomy has 40 fixed skills. A new tool can become popular and Verity would not see it.
**What this does:** `engine/discover.py` reads the same raw Hacker News "Who is hiring?" posts as `engine/demand.py`.
It lists terms that are **not** in the taxonomy but are used like tech names, with evidence.
**What it never does:** add a skill. A person reads the evidence and decides.

Output: `data/skill_candidates.json`. The app shows the top 15 at the bottom of the Method tab, under
"Candidate new skills (not yet in Verity; need human review)".

Run (about one minute on 8 processes; the raw posts stay local):

```
python -m engine.discover --raw-dir C:\Users\eezha\verity\data\raw\hn
```

## How a term is found

Four simple rules. Each can be read and checked.

| Rule | Finds | Example |
|---|---|---|
| `camel_case` | mixed case inside the word | FastAPI, LangChain, ClickHouse |
| `tech_style` | dot or digits in tech style, or a `++` / `#` ending | Next.js, gpt-4o, llama3, F#, .NET |
| `all_caps` | 2 to 6 capital letters | MCP, ECS, SRE |
| `list` | a single word inside a comma/slash list that already holds at least 2 different taxonomy skills | "Python, **FastAPI**, Postgres" |

- `list` is the strongest signal because it finds plain lowercase names (redis, graphql) that no form rule can see.
  It has the largest weight in the rank (see below).
- A list stops at a full stop, colon, `|`, a new line, or an item of more than 3 words.
- `camel_case`, `tech_style` and `all_caps` ignore the header cell of a post (the text before the first `|`), because that cell is the company name.
- Variants are one term: `nextjs`, `Next.js` -> `next.js`; `GPT-4o`, `gpt4o` -> `gpt4o`.
- A term is dropped when the taxonomy already covers it (pattern, skill name or synonym) or when it is in `data/discover_stoplist.txt`.
- Single letters followed by digits (`v2`, `q3`, `s3` as a form rule) are ignored. They are mostly versions and quarters.
  (`S3` still appears through the `list` rule.)

## How a term is counted and ranked

- A post counts at most once per term, in the month of its thread. A term "is in" a post when the post contains it as a word, in any case.
- A term must have **>= 30 posts in the last 12 months**, and **>= 50% of those posts** must show it in rule style
  (form rule or list). That second filter removes ordinary words that only look odd sometimes.
- `share_last` = posts with the term in the last 12 months / all posts in those months. `share_prior` is the same for the 12 months before.
- `growth = share_last / max(share_prior, 1 / n_prior_posts)`. A term with no posts in the prior 12 months is `new`; the app shows "new since <first month in the last 12>".
- `score = growth x (0.5 + 0.5 x list_fraction)`, where `list_fraction` = posts where the term sits in a skill list / posts with the term.
  A term seen only in prose style gets half weight. This is the rank.
- `label` is the existing Welch test from `engine/forecast.py` (`trend_label`): last 12 months of logit share against the 12 before.
- `first_seen` = first month with a post. `co_occurring_skills` = the 3 taxonomy skills with the highest lift in the last 12 months (at least 5 shared posts).
  `suggested_category` is the category of those skills. It is only a suggestion.
- `examples` = 2 Hacker News thread URLs (the month with most posts, and the latest other month). Thread URL only.
  The output never holds post text, author names, emails or per-post links. A test checks this.
- `as_of`: only months up to `as_of` are used to pick and rank terms. A test builds the same result from a data set that ends at `as_of`.

## How a person adds a skill

1. Open `data/skill_candidates.json`. Read `evidence`, `co_occurring_skills`, `examples`, and the thread links.
   Ask: is this a skill someone can learn, or a company, a place or a word?
   If it is noise, add it to `data/discover_stoplist.txt` so it does not come back.
2. Check the `draft_pattern` (status "draft, needs review and tests"). Look at 20 matching posts locally. Fix false matches
   (for example a pattern for `Express` must not match "express interest").
3. Add an entry to `data/taxonomy.json`: `skill`, `category` (use an existing one: `exposure.py` maps categories to occupations),
   `synonyms`, `pattern`, `case_sensitive`, `sdg` and `sdg_reason`.
4. Add tests for the pattern in `tests/test_tagging.py` (a few posts that must match, a few that must not).
   Update the "40 skills" counts in `tests/test_tagging.py`, `tests/test_demand.py` and `tests/test_scores.py`.
5. Rebuild: `python engine/demand.py`, then `python engine/exposure.py` (needs the local AEI file), `python -m engine.backtest`, `python -m engine.scores`.
   **The new skill gets its full history from 2019 at once.** Every post is tagged again from the raw files, so no waiting is needed.
6. Run the full test suite. Open a PR; do not merge to main before review.

### Backfill proof

`history(term)` returns the monthly share for every month from 2019-01 with the draft pattern. This is the count `engine/demand.py` makes once the skill is in the taxonomy.
A test checks that the two agree exactly. On the real data the top candidate today, MCP (Model Context Protocol), has almost no posts before mid-2025
and climbs to 4.5% of posts in October 2026. The series is stored in `data/skill_candidates.json` under `backfill_demo`.
The same series also shows why step 2 matters: it shows a draft pattern working, not that every match is right.

## Backtest (no leakage)

Run `discover(as_of="2023-06")`. Take the top 15. A **hit** is a term whose share of posts in 2023-07..2024-06 is above its share in 2022-07..2023-06.
No month after 2023-06 is used to choose the terms. Result (also in the JSON under `backtest`):

| Origin | Hits in top 15 | Precision | Base rate (all candidates) |
|---|---|---|---|
| **2023-06 (main)** | **3 / 15** | **0.20** (95% interval 0.07 to 0.45) | 0.30 over 47 candidates |
| 2021-06 | 5 / 15 | 0.33 | 0.26 |
| 2022-06 | 6 / 15 | 0.40 | 0.34 |
| 2024-06 | 4 / 15 | 0.27 | 0.26 |
| 2025-06 | 7 / 15 | 0.47 | 0.45 |

Top 15 at 2023-06: Redshift, CDK, WASM, ClickHouse (hit), FPGA, Nix, Nginx, FastAPI (hit), Flask, BigQuery, HPC (hit), gRPC, NoSQL, JVM, Redis.

**This result is weak, and we say so.** The ranking by growth does not predict which terms keep growing: precision is near the base rate at every origin.
Of the 10 terms labelled Rising at 2023-06, 3 kept growing (0.30). The first run, before the stoplist, gave 5/15 at 2023-06 (base rate 0.36); the stoplist removed two hits (ARR, DB)
and two misses (H1B, VA), which shows how fragile 15 terms are. The stoplist was written after reading candidate lists at several origins, so treat the numbers above as the honest ones, not as tuned ones.
Reasons it is weak: only 30% of all candidates grew in that year, growth from a small base is noisy, and 15 terms give a wide interval.

What the tool is good for: **surfacing** terms for a person to look at, with the evidence on one line. It is not a forecast. At 2023-06 it did not flag any LLM tool.

## Limits

- **Late.** A term needs 30 posts in 12 months. LangChain was first seen in 2023-04 but reached 30 posts in a trailing year only in 2026-04 (10 posts in 2024-10).
  MCP reached 30 in 2026-07. Hacker News hiring posts are few (about 200 to 800 top-level posts a month), so the tool sees a new tool 1 to 3 years after its first mention.
  `discover(min_mentions=10)` (or a lower value) finds terms earlier, with more noise.
- **Noise.** Company names, places, job words and business acronyms look like tech names. `data/discover_stoplist.txt` holds the known ones; expect to add more.
  Some candidates are real but not tools (HIPAA, ERP). Some are two names for one thing (`Vue` and `Vue.js` are two rows).
- **One-word terms only in lists.** Two-word names (Apache Kafka, Hugging Face) are found only if written as one word or in camel case.
- **Mention counts include prose.** A term counts when the word appears anywhere in a post. Ordinary words such as "Express" or "Vault" pass the 50% filter when they are mostly used as tool names.
  Check the sample posts before you add a skill.
- **Today's files.** The backtest uses today's taxonomy and stoplist for every origin.
- **Partial last month.** The current month's thread is still open; shares use posts so far.
- **Hacker News only.** Hiring posts are tech-heavy, so a term can be big here and small in the Malaysian job market.
