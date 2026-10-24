# Technical Tools Declaration: Verity

Export to PDF as `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf`.
Items marked [TEAM TO FILL] are for the team. Do not submit with any of them left in.
Where a field has nothing to declare, we write "None".

## 1. Team overview

| Field | Entry |
|---|---|
| Team name | Hokkien Mee Is Purple |
| Domain | Domain 1: Aiversecity Future-Ready Workforce |
| Project name | Verity |
| Team leader | Tay Ee Zhan |
| Members | 2 (Tay Ee Zhan, Goh Sheng Kuan) |
| Live prototype | https://verity--eezhan0805.replit.app |
| Code repository | https://github.com/TayEeZhan/verity (private while building; public at submission and through judging) |
| Repository licence | Apache License 2.0 (`LICENSE` in the repository root) |

## 2. Technical architecture

### 2.1 Architecture overview

Verity is one Python server and a static web app. FastAPI, run with uvicorn, serves `frontend/` and the JSON APIs, and imports the engine modules.

**Data flow.** The engine downloads every monthly Hacker News "Who is hiring?" thread through the Algolia HN Search API: 94 threads and 48,508 job posts, January 2019 to October 2026. A tagger finds 40 taxonomy skills in each post. The engine turns the tags into a monthly share per skill. It forecasts 12 months ahead, adds a conformal band and a Welch trend label, and joins an AI exposure score from the Anthropic Economic Index. The role module learns role profiles from posts that name one role. The pathway module orders the learning plan. A ranker re-ranks AI news every 15 minutes.

**Storage and refresh.** The repository holds only aggregates. Raw post text stays in gitignored folders on the team's machines. The app reads the committed files in `data/` (demand data as of October 2026). A daily Replit Scheduled Deployment (code built; setup pending) will save snapshots to App Storage; the app does not read them yet.

Claude Haiku 5.5 (Anthropic API) points at CV skills; code checks each quote.

(195/200 words)

### 2.2 Libraries, versions and licences

A version with `==` is pinned in `requirements.txt` or `requirements-dev.txt`. A version with `>=` is the lower bound written in `backend/signals/requirements.txt`; the installed version can be newer. Licences of installed packages come from the package metadata. Licences of packages not installed in the local environment come from their PyPI pages and are marked (PyPI).

| Name & Version | Purpose | License |
|---|---|---|
| fastapi >=0.115 | Web server and JSON APIs (`backend/signals/trendsignal/web/`) | MIT |
| uvicorn[standard] >=0.30 | Server that runs the FastAPI app | BSD-3-Clause |
| jinja2 >=3.1 | HTML templates of the ranker pages (`/feed`, `/story`) | BSD-3-Clause (PyPI) |
| apscheduler >=3.10,<4 | Re-ranks the AI signals every 15 minutes (`--scheduler`) | MIT (PyPI) |
| feedparser >=6.0 | Reads RSS and Atom feeds in the signal ranker | BSD-2-Clause (PyPI) |
| pypdf >=6.21 | Reads text from an uploaded PDF CV | BSD-3-Clause |
| httpx >=0.28 | HTTP client in the signal ranker | BSD-3-Clause |
| pydantic >=2.10 | Checks API input and the structured output of the language model | MIT |
| anthropic >=2.0.0 | Client for the Anthropic Messages API (CV intake, optional advisor) | MIT |
| typesafe-sdk 0.7.5 | Client for the optional Jev ranker (off by default) | [TEAM TO FILL: licence, not installed locally] |
| pyyaml >=6.0 | Reads the ranker's configuration files | MIT |
| markdown >=3.7 | Turns the ranker's prose briefs into HTML | BSD-3-Clause |
| pandas 3.0.6 | Tables and CSV files | BSD-3-Clause |
| numpy 2.5.4 | Numeric arrays and the forecast maths | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| requests 2.34.2 | HTTP calls to the Algolia HN Search API | Apache-2.0 |
| statsmodels 0.15.0 | Damped-trend model, tested in the backtest only (not in production forecasts) | BSD-3-Clause |
| scipy 1.18.1 | Welch t-test for the Rising / Falling label | BSD (3-clause) |
| pytest 9.1.1 | Automated tests (over 700 tests) | MIT |
| replit-object-storage 1.0.2 | Client for Replit App Storage (daily snapshots) | ISC |
| scikit-learn 1.9.1 | Gradient-boosting experiment only (`requirements-dev.txt`; not installed on Replit) | BSD-3-Clause |
| joblib 1.6.0 | Dependency of scikit-learn (`requirements-dev.txt`) | BSD-3-Clause |
| threadpoolctl 3.7.0 | Dependency of scikit-learn (`requirements-dev.txt`) | BSD-3-Clause |

`requirements.txt` also pins five transitive packages for security (Replit's security scan): anyio 4.15.1, certifi 2026.10.19, h11 0.16.0, idna 3.20 and pygments 2.21.0. We do not call them directly.

## 3. External services

### 3.1 External APIs

| API | Access tier | Use |
|---|---|---|
| Algolia HN Search API, https://hn.algolia.com/api | Free. Public. No key or account. | Lists the monthly "Who is hiring?" threads and fetches each thread. The backfill makes one request at a time, with pauses and retries. The daily job fetches only the newest thread. |
| HTTP GET requests to learning-resource URLs | Free. Public web pages. | One-time check on 22 Oct 2026 that each of the 77 links in `data/resources.json` returns HTTP 200. We keep only links that returned 200. This check is not part of the running app. |
| Anthropic Messages API (Claude Haiku 5.5, `claude-haiku-5-5`) | Paid tier, on a team member's Anthropic account (Goh Sheng Kuan). The key (`ANTHROPIC_API_KEY`) is in Replit Secrets and Production app secrets. Anthropic bills that account. | CV intake (one call per CV, returns skill mentions with exact quotes), optional route advisor, optional pathway coach. Details in 4.1. |

No other API is used. Only the CV intake and the two optional steps (route advisor, pathway coach) call an LLM API. The forecast, role match, pathway dates and SDG parts call none.

### 3.2 Cloud platform and plan

| Service | Use | Plan and region |
|---|---|---|
| Replit Autoscale deployment (`deploymentTarget = "cloudrun"` in `.replit`) | Hosts the Varity server (FastAPI, no Streamlit). Build: `pip install -r requirements.txt`. Run: `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`. Live, published 24 Oct 2026. | 2 vCPU / 4 GiB. Recommended setting: max 1 instance. Plan: [TEAM TO FILL: Replit plan on the deploying account]. Region: [TEAM TO FILL: region shown in Replit] |
| Replit Secrets | Hold `ANTHROPIC_API_KEY` (and the Production app secrets copy). | Replit AI Integrations is not used. |
| Replit App Storage | Will store the newest data snapshot (keeps the last 14). The Varity app does not read it yet. | Code built; Replit setup pending. [TEAM TO FILL: confirm the bucket exists] |
| Replit Scheduled Deployment | Will run `python -m engine.scheduled` daily at 09:00 Malaysia time (cron `0 1 * * *` in UTC). | Code built; Replit setup pending. [TEAM TO FILL: confirm the Scheduled Deployment is created and has run once] |

Known limit: saved profiles and the signals database live on the instance's disk, so a profile can reset when the app sleeps or restarts. "Try an example" re-creates one in one click. When the signals database is empty, a background pipeline run at startup rebuilds it (seen live: run 20261024T062256, 235 stories).

Status note: the code for App Storage and the scheduled job is built, but the Replit setup is pending. Our setup guide (`docs/replit-schedule.md`) lists the steps. Do them, then remove "pending" from this table and from the proposal (sections 3.1 and 3.2).

## 4. AI, models and data

### 4.1 AI models

**Only the CV intake and two optional steps use an LLM.** All three call Claude Haiku 5.5 with one Anthropic API key. The two optional steps are the route advisor and the pathway coach. Every other part uses no LLM. The forecast, the Welch label, the role match, the learning pathway and the SDG sector links are code and statistics. The app uses no GPU and no self-hosted model.

| Model | Provider | Use | Status |
|---|---|---|---|
| Statistical models: naive, mean of last 3 months ("naive3"), drift, damped trend; Welch t-test; conformal band | Our code, with SciPy and statsmodels | Forecast, band and Rising / Falling label | In production: naive3 and the band. Drift and damped trend lost the backtest and are not shipped. |
| HistGradientBoostingRegressor (scikit-learn 1.9.1) | scikit-learn | Experiment: a correction to the naive3 forecast | **Not deployed.** It lost the backtest (error 2.06 against 1.66 percentage points). |
| Claude Haiku 5.5 (`claude-haiku-5-5`) through the Anthropic API | Anthropic | CV intake. One call per CV. The model only points at skill mentions in the CV text and returns a quote for each. Code checks that every quote appears word for word in the CV. Code turns the phrase into a skill id and reads the years. The model sets no score, rank, forecast or date. | Key `ANTHROPIC_API_KEY` in Replit Secrets and Production app secrets. Paid tier on a team member's Anthropic account; Anthropic bills it. The live CV-intake call is not yet confirmed. [TEAM TO FILL: confirm after the first live CV run] |
| Same model and key (`VARITY_ADVISOR_MODEL`, `VARITY_COACH_MODEL` default to the intake model) | Anthropic | Optional route advisor: re-orders the ranked roles by at most 2 places and picks among reason chips that code wrote. Optional pathway coach: re-orders steps inside one stage and picks among resource links that code listed. Code checks both answers. The fit label, scores and dates always come from code. | Route advisor confirmed live on 24 Oct 2026 with a synthetic example profile: route cards show "Ranked by AI within limits, checked against the data" and one AI summary line. Without a key, code's order stands. |
| Claude Haiku 4.5 (`claude-haiku-4-5`) through Replit AI Integrations | Anthropic, via Replit | Fallback route in the code when no `ANTHROPIC_API_KEY` is set. Same checks. | Unused option. The team does not use it. |
| Keyword pass | Our code | The same job with no credentials, or when the Claude call fails: matches skill names in the CV text | Fallback. Needs no key and costs nothing. |

**Budget caps.** Each cap is per server process. The CV intake has $1 per day (`VERITY_INTAKE_DAILY_BUDGET_USD`). The advisor and coach together have $1 per day (`VARITY_ADVISOR_DAILY_BUDGET_USD`). When a cap is reached, or with no key, code takes over: keyword pass, formula ranking, code pathway.

**Optional uses in the signal ranker (`backend/signals/`).** Claude can pick a story category when the rules are unsure, and can write a prose brief. Both are off by default. Jev (TypeSafe AI) can score signals through OpenRouter, but `TRENDSIGNAL_RANKER` defaults to the formula. [TEAM TO FILL: declare Jev's exact model id and the OpenRouter models if you turn this on for the demo.]

### 4.2 Datasets

| Name | Source / URL | Type | License | Personal data (Y/N) |
|---|---|---|---|---|
| Hacker News "Ask HN: Who is hiring?" threads | Algolia HN Search API, https://hn.algolia.com/api (threads by user `whoishiring`) | Public job posts; we commit monthly skill counts and thread links only | No licence stated in `data/SOURCES.md` | Y for the raw text (it can hold names and contact details). The raw text is not stored in the repository or in App Storage. It sits in gitignored folders on the team's machines and, during a refresh, in a temporary folder on the Replit server. Committed files: N. |
| Anthropic Economic Index, release 2026-06-26 | https://huggingface.co/datasets/Anthropic/EconomicIndex | Occupation-level AI usage (automation share) | CC BY (data), MIT (code) | N |
| O*NET 31.0 Database, Task Statements | https://www.onetcenter.org/database.html | Task text by occupation (used in an earlier version only) | CC BY 4.0 | N |
| GPTs are GPTs, occupation-level ratings | https://github.com/openai/GPTs-are-GPTs | Exposure ratings (cross-check only) | MIT | N |
| AIOE (Felten, Raj, Seamans) | https://github.com/AIOE-Data/AIOE | Exposure index (cross-check only) | No licence file. We use it with citation and do not redistribute the files. | N |
| Microsoft Working with AI, AI applicability scores | https://github.com/microsoft/working-with-ai | Exposure index (cross-check only) | CC BY 4.0 | N |
| O*NET-SOC crosswalk tables | https://www.onetcenter.org/taxonomy/2019/walk.html | Occupation code mapping only | O*NET data is mostly CC BY 4.0; the pages state no licence of their own | N |
| Three synthetic example profiles (Aina, Ben, Chloe) | Written by the team, in `data/example_profiles.json` | Synthetic example skill lists | Our own work | N (synthetic) |
| Learning resources list (77 links) | Written by the team, in `data/resources.json`. Links point to the providers. | Titles and links only. We copy no page content. | Our own work | N |

Full URLs, versions, commit hashes and file checksums: `data/SOURCES.md`.

### 4.3 AI-assisted development tools

| Tool | Vendor | Models | Extent | Used for |
|---|---|---|---|---|
| Claude Code | Anthropic | Claude Opus 5.5, Claude Sonnet 5.5, Claude Haiku 5.5 | **Major** | Code, tests, data pipeline and documents, from the team's prompts and plans |
| Replit Agent | Replit | [TEAM TO FILL: model, if shown in Replit] | **Minor** | Environment setup only. Its two commits change only the `.replit` file. |

Other AI tools: None declared. [TEAM TO FILL: add any other AI tool that either member used, including chat tools, before you sign.]

#### How the team reviewed AI output (max 100 words)

A stronger model reviews each major part before we call it done. The team reviews every pull request. We run over 700 automated tests, including tests that block look-ahead leaks. Every statistic traces to a file in `data/` or a cited source. Reviews found real faults, and we fixed them: bare "AI" inflated Machine Learning to 55% of posts, the first exposure score measured traffic, and the first uncertainty band covered only 65.9% of real values. Both members must be able to explain each part.

(85/100 words)

## 5. Sponsor resources

**Replit** (Core plan: [TEAM TO FILL: confirm]). We use it for hosting only: an Autoscale deployment, live and published 24 Oct 2026. We do not use Replit AI Integrations. Claude calls use a team member's Anthropic API key, held in Replit Secrets. We plan to use App Storage and Scheduled Deployments (code built; Replit setup pending). Replit is essential for the hackathon (compulsory). It is replaceable. `engine/store.py` has a local-folder store. Proof of use: the live URL https://verity--eezhan0805.replit.app. [TEAM TO FILL: attach any extra proof, such as a project history link.]

(93/100 words)

**RunPod:** Not used. We do no GPU work. The organisers confirmed on 22 Oct 2026 that RunPod proof is not needed without GPU use.

## 6. Data handling and limitations

### 6.1 Data handling and privacy

The app has no sign-in and stores no account data. Raw Hacker News posts can hold names and contact details. They stay in gitignored folders on the team's machines and, during a refresh, in a temporary folder on the Replit server. Only aggregates are committed or stored: monthly counts per skill and role, thread links and derived scores. The code strips HTML and links before it tags skills. A test checks that no committed data file holds an email address. Outputs never hold post text, author names or per-post links. The three example profiles are synthetic. We use synthetic CVs only and no real CVs. CV text goes to Anthropic directly. Code redacts phone numbers, emails and ID numbers first, but names can remain. We design for the Personal Data Protection Act 2010 (PDPA) by keeping real personal data out of the demo.

(144/150 words)

### 6.2 Known limitations and risks

1. Hacker News is US-heavy and startup-heavy, not Malaysian.
2. Persistence won. At 12 months, the mean of the last 3 months (1.66 points of error) beat every trend model and our gradient-boosting model.
3. The exposure indices disagree. Only the "language" category holds across them. Microsoft's index ranks eight occupations almost opposite to ours (rank correlation -0.79).
4. The scenario factor k = 2 is an assumption. The data give a 95% interval of -1.0 to 2.9 per 12 months, which includes 0.
5. New-skill discovery is late and weak: 3 hits in 15 at the 2023-06 test. A term needs 30 posts in 12 months.
6. JobStreet Malaysia is blocked by a bot challenge, so we use no Malaysian job feed.
7. The October 2026 month is partial: its thread was still open.
8. CV intake can miss a skill. The user edits the list. The CV-intake Claude call is not yet confirmed live.

(145/150 words)

## 7. Compliance checklist

- [x] The repository was created after the build clock started. First commit: 21 Oct 2026, 23:49 (+0800).
- [x] The repository root holds an Apache License 2.0 file.
- [ ] The repository is public. [TEAM TO FILL: tick at submission]
- [ ] The committee accounts are added as collaborators. [TEAM TO FILL]
- [x] No secrets in the repository. A search for key patterns on 22 Oct 2026 found none, and the data job needs no secret.
- [x] The live prototype is a working deployment, not a video or mock-up: https://verity--eezhan0805.replit.app
- [x] Replit is part of the solution. RunPod proof is not needed (no GPU work).
- [ ] We declared every AI development tool we used. Claude Code and Replit Agent are declared. [TEAM TO FILL: tick after you confirm no other tool was used]
- [x] We use no real CVs in the demo. The personas and test CVs are synthetic. CV text goes to Anthropic directly (see 6.1).
- [x] Every dataset and library is listed with its licence. Open point: AIOE has no licence file (see 4.2).
- [ ] Both members completed the mandatory GenAI, Database and Cloud Deployment workshops. [TEAM TO FILL: tick only if both completed all three]
- [ ] Both members can explain every part of the project. [TEAM TO FILL: tick after you rehearse]

## 8. Declaration

[TEAM TO FILL: the template declaration wording, then the signature of the team leader, the name, and the date.]

Signature: [TEAM TO FILL]
Name: Tay Ee Zhan
Date: [TEAM TO FILL]
