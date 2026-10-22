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

## 4. GPTs are GPTs: occupation-level exposure (Eloundou, Manning, Mishkin, Rock)

Step 9, exposure cross-check. One of the indices we compare the AEI score against. Not used for the production stance.

- **Name:** "GPTs are GPTs: An Early Look at the Labor Market Impact Potential of Large Language Models", occupation-level exposure ratings, GitHub repository `openai/GPTs-are-GPTs`.
- **Repository:** https://github.com/openai/GPTs-are-GPTs
- **File we use (pinned to commit `0471612fef3cc22b74fb884d27bff9dbd3770582`, committed 2025-10-04):**
  https://raw.githubusercontent.com/openai/GPTs-are-GPTs/0471612fef3cc22b74fb884d27bff9dbd3770582/data/occ_level.csv
  (SHA-256 `40c74f53de40aec91c0017d80690cbba915f83a8bb414bcf2f884692f1749acb`, 923 occupations, O*NET-SOC 2019 codes).
  Downloaded to `data/raw/ext/gpts/` on 22 Oct 2026.
- **Columns we use:** `dv_rating_beta` (GPT-4 rating) and `human_rating_beta` (annotator rating). The repository README says
  "_alpha=E1, _beta = E1+.5*E2, _gamma=E1+E2" and "dv_rating is the GPT-4 rating and human is from the annotators". We use beta,
  the middle variant (E1 = direct exposure, E2 = exposure through extra tools).
- **Licence:** MIT (repository `LICENSE`, "Copyright (c) 2024 OpenAI"; GitHub also reports MIT). Reuse is allowed; the licence
  text must be kept with copies.
- **What we use it for:** `data/exposure_indices.csv`, `data/exposure_agreement.json`, `data/exposure_robustness.csv`. The O*NET-SOC
  codes match the AEI file directly, so no crosswalk is needed. We commit only the eight occupation values we need.
- **Limits:** the ratings say what a model could do for the tasks of an occupation (a capability view), not how people use a chatbot.
  The GPT-4 and human ratings differ a lot for some occupations (Software Developers: 0.87 against 0.45). The raw file is not committed.

## 5. AIOE: AI Occupational Exposure (Felten, Raj, Seamans)

Step 9, exposure cross-check. Not used for the production stance.

- **Name:** AIOE data appendix and the language-modelling variant, GitHub repository `AIOE-Data/AIOE`.
- **Repository:** https://github.com/AIOE-Data/AIOE
- **Files we use (pinned to commit `adca5fc2cd0e9a659ff05278b7fa7a53f4f324c1`, committed 2024-06-03):**
  - https://raw.githubusercontent.com/AIOE-Data/AIOE/adca5fc2cd0e9a659ff05278b7fa7a53f4f324c1/AIOE_DataAppendix.xlsx
    (SHA-256 `c123b4c64840aff3568ae6c97256678719b88a74d45b6362dbefb5af34667b95`), sheet "Appendix A" (AIOE by 6-digit SOC code).
  - https://raw.githubusercontent.com/AIOE-Data/AIOE/adca5fc2cd0e9a659ff05278b7fa7a53f4f324c1/Language%20Modeling%20AIOE%20and%20AIIE.xlsx
    (SHA-256 `ccdd1fb916dfa404914367eafde7c00b7148ea86f18fe616240bc85cf6131c8b`), sheet "LM AIOE" (language-modelling variant).
  Downloaded to `data/raw/ext/aioe/` on 22 Oct 2026.
- **Version:** the repository has no version tag; we cite the commit. The README ties the data to the SMJ paper below.
- **Licence:** NO LICENCE FILE. GitHub shows no licence for the repository and the README gives no terms except one request:
  "If you use any of the AIOE data, please include the following citation". We read this as permission to use with citation, and we
  do not redistribute the files (raw files stay gitignored; only eight derived values per index are in `data/exposure_indices.csv`).
  This is a judgement, not a licence. If it is not acceptable, delete the `aioe` and `aioe_lm` entries from `INDEX_SPECS` in
  `engine/exposure_indices.py` and rebuild; the other indices stay.
- **Citation:** Felten E, Raj M, Seamans R (2021) Occupational, industry, and geographic exposure to artificial intelligence: A novel
  dataset and its potential uses. Strategic Management Journal 42(12):2195-2217. https://doi.org/10.1002/smj.3286
- **SOC version:** the appendix uses 6-digit SOC codes of the 2010 system (it has 15-1132 Software Developers, Applications and
  15-1133 Systems Software, not 15-1252). We map through the O*NET crosswalk (section 7); see "How the exposure indices are compared".
- **Limits:** AIOE is built from the match between AI application progress (2010s benchmarks) and O*NET abilities. It is older than the
  other indices. It has no value for Data Scientists (15-2051; its SOC 2010 parent 15-2099 is not in the appendix) and only a broad
  value for 15-1299.08 (parent 15-1199 "Computer Occupations, All Other").

## 6. Microsoft "Working with AI": AI applicability scores (Tomlinson et al.)

Step 9, exposure cross-check. Not used for the production stance.

- **Name:** "Working with AI: Measuring the Applicability of Generative AI to Occupations", results files, GitHub repository `microsoft/working-with-ai`.
- **Repository:** https://github.com/microsoft/working-with-ai
- **File we use (pinned to commit `18ec44905db3383a7fd7fd0c1ff3ab36ad7729db`, committed 2026-10-09):**
  https://raw.githubusercontent.com/microsoft/working-with-ai/18ec44905db3383a7fd7fd0c1ff3ab36ad7729db/ai_applicability_scores.csv
  (SHA-256 `204c7e6a5ec704156212f88a6282dba7508c8b90e5df7c0d590088b2b44aa7d2`, 785 SOC 2018 codes). Downloaded to `data/raw/ext/msft/` on 22 Oct 2026.
- **Version:** v1.1 ("referenced by the arXiv paper revision v6", README). Data: Bing Copilot conversations in the US, 1 Jan to 30 Sep 2024; O*NET 29.0.
- **Licence:** CC BY 4.0 (README: "This repository is licensed under CC BY 4.0"; `LICENSE.txt` says the same). The README also says
  the metrics "should not be misconstrued or misrepresented as measuring the ability of AI to replace jobs". We use them only as one view of how
  applicable AI is to an occupation, and we say so in the app.
- **Citation:** Kiran Tomlinson, Sonia Jaffe, Will Wang, Scott Counts, Siddharth Suri. Working with AI: Measuring the Applicability of
  Generative AI to Occupations. arXiv:2507.07935, 2025.
- **What we use it for:** `data/exposure_indices.csv` and the cross-check. We commit only the eight occupation values we need.
- **Limits:** a usage-based measure like AEI, but from Copilot (Microsoft) and for 2024. 15-1299.08 gets the score of the broad
  code 15-1299.

## 7. O*NET-SOC crosswalks (code mapping only)

Used to map occupation codes for the AIOE and Microsoft files. No values are taken from them.

- **Files:** `2010_to_2019_Crosswalk.csv`
  (https://www.onetcenter.org/taxonomy/2019/walk/2010_to_2019_Crosswalk.csv?fmt=csv, SHA-256 `8f026a33134bfde5770308d1c6117cf70d9dd41c2b3467e6dd271d65bdeecc5a`)
  and `2019_to_SOC_Crosswalk.xlsx`
  (https://www.onetcenter.org/taxonomy/2019/soc/2019_to_SOC_Crosswalk.xlsx?fmt=xlsx, SHA-256 `bfc6722a92c2d607e5a99dee88b7826cf5aa91f7c0453182e0c8268e32a20a19`).
  From the O*NET Resource Center, pages https://www.onetcenter.org/taxonomy/2019/walk.html and https://www.onetcenter.org/taxonomy/2019/soc.html.
  Downloaded to `data/raw/ext/onet_xwalk/` on 22 Oct 2026.
- **Licence:** O*NET says "The majority of O*NET information is available under a Creative Commons (CC BY 4.0) license"
  (https://www.onetcenter.org/license_agreements.html). The crosswalk pages state no licence of their own. We only read code pairs
  from them and do not redistribute the files.
- **Tried and not used:** the BLS file https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx returns an "Access Denied" page to
  automated downloads. We did not work around that; the O*NET crosswalk covers what we need.

## Skipped sources (step 9)

- **ILO generative AI exposure index** (Gmyrek et al. 2025, ILO Working Paper 140; CC BY 4.0; repository
  https://github.com/pgmyrek/2025_GenAI_scores_ISCO08, file `Final_Scores_ISCO08_Gmyrek_et_al_2025.xlsx`). The repository loads and the licence
  allows reuse, but the scores are for ISCO-08 4-digit groups. The only official ISCO-08 to SOC crosswalk is at the BLS, which blocks
  automated downloads. A guessed mapping would be coarse: Software Developers, Computer Programmers and Web Developers would share one or two
  ISCO groups, so the check would mostly compare ISCO groups, not our eight occupations. Skipped, not downloaded.

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

## How the exposure indices are compared (step 9)

See the docstring in `engine/exposure_indices.py` and `docs/exposure-crosscheck.md`. Rebuild with `python -m engine.exposure_indices`
(needs the raw files from sections 4 to 7). Measured k: `python -m engine.k_estimate` (needs only `data/demand_monthly.csv`).

- Six indices from four source families: AEI (production), GPTs-are-GPTs (GPT-4 and human variants), AIOE (all applications and language
  modelling), Microsoft. A family casts one vote.
- Code mapping. GPTs and AEI use O*NET-SOC 2019 codes directly. Microsoft uses 6-digit SOC 2018: the O*NET 2019 to SOC 2018 table gives the
  code. AIOE uses 6-digit SOC 2010: the O*NET 2010 to 2019 crosswalk lists the 2010 codes that feed each 2019 code; AIOE is the unweighted
  mean over their 6-digit parents that have a value. Examples: 15-1252 = mean of 15-1132 and 15-1133; 15-1243 = mean of 15-1141 and 15-1199;
  15-1299.08 = 15-1199; 15-2051 has no AIOE value.
- `exposure_indices.csv`: raw value, rank (1 = most exposed) and z over the eight occupations, per index.
- `exposure_agreement.json` and `exposure_robustness.csv`: see the module docstring for the support rule behind `stance_robust`.
- `k_estimate.json`: see the docstring in `engine/k_estimate.py`.
