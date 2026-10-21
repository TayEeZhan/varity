# Data sources

One section per external dataset. Raw downloads live in `data/raw/ext/` (gitignored).
Re-download from the URLs below to rebuild. Checked on 22 Oct 2026.

The category-to-occupation mapping in `data/exposure_occupations.csv` is team judgement.
`data/exposure_map.csv` (per-task map) is v1 and superseded: it is kept for the record and is no longer used.

## 1. Anthropic Economic Index (AEI), release 2026-06-26

- **Name:** The Anthropic Economic Index, Hugging Face dataset `Anthropic/EconomicIndex`.
- **Dataset page:** https://huggingface.co/datasets/Anthropic/EconomicIndex
- **File we use (pinned to commit `4e5f69fab13a9c3f7d0dcc31a6f893a9818738f6`, repo last modified 2026-09-30):**
  https://huggingface.co/datasets/Anthropic/EconomicIndex/resolve/4e5f69fab13a9c3f7d0dcc31a6f893a9818738f6/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv
  (SHA-256 `f974b358bce0e5a8417510c61da4342234cd0de9d9d0b62acf4c6dbcf8ec7b68`)
- **Documentation:** https://huggingface.co/datasets/Anthropic/EconomicIndex/blob/4e5f69fab13a9c3f7d0dcc31a6f893a9818738f6/release_2026_06_26/data_documentation.md
- **Version / date:** release 2026-06-26 ("Cadences", sixth report). The file holds two calendar months of
  Claude.ai usage: April 2026 (`2026-04-01` to `2026-05-01`) and May 2026 (`2026-05-01` to `2026-06-01`).
- **Licence:** Data CC BY; code MIT. Source: the dataset README ("Data released under CC-BY, code released under MIT License")
  and `data_documentation.md` ("Data released under CC-BY"). Note: the Hugging Face metadata header of the README
  says `license: mit`. We follow the stricter text in the body and credit Anthropic as CC BY requires.
- **Citation:** Massenkoff, Lyubich, Sacher, Hitzig, Zhang, Heller, McCrory. "Anthropic Economic Index report: Cadences", 2026-06-26.
  https://www.anthropic.com/research/economic-index-june-2026-report
- **What we use it for:** `data/exposure_occupations.csv` and `data/exposure.csv` (task E3 v2). We read only rows with
  `geo_id = GLOBAL`, `category_name = soc_occupation`, `hierarchy_level = 0` (Detailed Occupation) and
  `metric_id = collaboration_bucket_automation_pct` (percent of that occupation's conversations in the
  "automation" collaboration bucket). `node_external_id` is the O*NET-SOC code and `node_name` the occupation title.
  The file has two months (April and May 2026); we take the mean of the two. Fetched and checked on 22 Oct 2026.
- **Licence and attribution:** CC BY. Attribution: "Anthropic Economic Index" (Anthropic, release 2026-06-26, see Citation).
- **Limits:** Claude.ai conversations only (chat and Cowork). API and Claude Code usage are not included. Automation
  share is the share of conversations where the AI did the task rather than helped. It describes how people use
  Claude.ai today for an occupation, not how much of the job AI can do. Cells below the publication thresholds
  are not published. Values are rounded to two decimals by AEI. Our occupation-to-skill link goes through a skill
  category, so all skills in one category get the same score.
- **Superseded v1 use:** the task-level rows (`category_name = onet`, metric `pct`) behind `data/exposure_map.csv`
  measured traffic volume, not exposure.

## 2. O*NET 31.0 Database, Task Statements (v1 only, superseded)

Used only by the v1 file `data/exposure_map.csv`, which is superseded and no longer feeds `exposure.csv`.
The occupation codes in v2 come from the AEI file itself (`node_external_id`).

- **Name:** O*NET 31.0 Database, `task_statements.csv`. U.S. Department of Labor, Employment and Training Administration (USDOL/ETA).
- **Database page:** https://www.onetcenter.org/database.html
- **File we use:** https://www.onetcenter.org/dl_files/database/db_31_0_csv/task_statements.csv
  (SHA-256 `4568e14d8db6f05551ad37e056e909b13ebae4a26bcb5ff915bb5f281d582c57`). It is one file from the CSV bundle
  https://www.onetcenter.org/dl_files/database/db_31_0_csv.zip
- **Version / date:** O*NET 31.0, the current release on the database page on 22 Oct 2026. The page we fetched does
  not print the release date, so we cite the version number and the download date.
- **Licence:** Creative Commons Attribution 4.0 International (CC BY 4.0). Source: https://www.onetcenter.org/license_db.html
- **Attribution (verbatim, as the licence page asks):** "This page includes information from the O*NET 31.0 Database by
  the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the CC BY 4.0 license.
  O*NET is a trademark of USDOL/ETA." We selected a small subset of tasks and added our own skill labels; USDOL/ETA has not
  approved, endorsed, or tested these changes.
- **What we use it for:** the task text and occupation code (`onet_soc`) for each task ID in `data/exposure_map.csv`.
  The AEI 2026-06-26 task IDs match this release (2,820 of the 2,823 AEI task IDs are in O*NET 31.0), and the task text
  we store equals the AEI `node_name` for all 179 mapped task rows that AEI publishes.

## 3. Hacker News "Ask HN: Who is hiring?"

- **Name:** Hacker News monthly "Ask HN: Who is hiring?" threads, posted by the user `whoishiring`.
- **Source:** Algolia HN Search API, https://hn.algolia.com/api (list threads with `search_by_date`, fetch each
  thread with `/api/v1/items/<id>`).
- **Thread index:** `data/hn_threads.csv` (one row per thread: id, month, created_at, title, URL, number of top-level comments).
- **Fetched:** 22 Oct 2026. The Oct 2026 thread was still open at fetch time, so its counts will grow.
- **What we use it for:** `data/demand_monthly.csv` (monthly share of job posts that mention each skill).
  Top-level comments only; each top-level comment is one job post.
- **Committed:** only aggregates (the thread index and the monthly skill counts). Raw post text stays in
  `data/raw/hn/` (gitignored) because posts hold personal data.
- **Limits:** the threads are a self-selected sample of employers who post there, not the whole job market.
  Posts per month fell from a mean of 703 in 2019 to a mean of 310 in the last 12 months (minimum 228, Aug 2026; from data/hn_threads.csv), so we use shares, not counts.

## How the numbers are built

See the docstring in `engine/exposure.py`. Rebuild with `python engine/exposure.py` (needs the raw AEI file).

- `automation_pct` (per occupation) = mean of April and May 2026 `collaboration_bucket_automation_pct`
  (percent points), from `data/exposure_occupations.csv`.
- `automation_share` (per skill) = mean `automation_pct` of the occupations mapped to the skill's category.
- `ai_exposure` = `automation_share` / 100, a 0-1 ratio (not min-max).
- `e_s` = `automation_share / 100` minus the mean of `automation_share / 100` over the 40 skills.
- `stance` = "AI-complement" for category `ai_ml`; otherwise "AI-substitutable" if `e_s > 0.02`, "neutral" if
  `|e_s| <= 0.02`, "AI-complement" if `e_s < -0.02`.

Skills in the same category get the same score (for example Java and C#), because AEI publishes occupations, not
languages or products. Treat small differences between categories as noise.
