# Data sources

One section per external dataset. Raw downloads live in `data/raw/ext/` (gitignored).
Re-download from the URLs below to rebuild. Checked on 22 Oct 2026.

The skill-to-task mapping in exposure_map.csv is team judgement.

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
- **What we use it for:** `data/exposure.csv`. We read only rows with `geo_id = GLOBAL`, `category_name = onet`,
  `hierarchy_level = 0` (task level). Metric `pct` = share of Claude.ai usage on that O*NET task (percent).
  Metric `collaboration_bucket_automation_pct` = share of that task's conversations labelled "automation" (percent).
  `node_external_id` is the O*NET Task ID.
- **Limits:** Claude.ai (chat and Cowork) only. API and Claude Code traffic are not in this file. Cells below
  the publication thresholds are not published; we count a missing task as 0 usage, so those tasks may be
  under-counted. Values are rounded to two decimals by AEI.

## 2. O*NET 31.0 Database, Task Statements

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

## How the numbers are built

See the docstring in `engine/exposure.py`. Rebuild with `python engine/exposure.py`.

- `ai_usage_share` = mean over the skill's mapped tasks of the task usage. Task usage = mean of April and May 2026 `pct`
  (percent points). A month with no row counts as 0.
- `automation_share` = usage-weighted mean of `collaboration_bucket_automation_pct` (percent points).
- `ai_exposure` = min-max of `ai_usage_share` across the 40 skills, from 0 to 1.
- `n_tasks_found_in_aei` = mapped tasks that have at least one published AEI row.

O*NET tasks are written for jobs, not for tools. They do not name languages or products, so skills that share tasks
get the same score (for example Java and C#). Treat small differences between skills as noise.
