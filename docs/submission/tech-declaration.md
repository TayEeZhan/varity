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
| Code repository | https://github.com/TayEeZhan/varity (private while building; public at submission and through judging) |
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
| typesafe-sdk 0.7.5 | Client for the optional Jev ranker (off by default) | MIT (package metadata) |
| pyyaml >=6.0 | Reads the ranker's configuration files | MIT |
| markdown >=3.7 | Turns the ranker's prose briefs into HTML | BSD-3-Clause |
| pandas 3.0.6 | Tables and CSV files | BSD-3-Clause |
| numpy 2.5.4 | Numeric arrays and the forecast maths | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| requests 2.34.2 | HTTP calls to the Algolia HN Search API | Apache-2.0 |
| statsmodels 0.15.0 | Damped-trend model, tested in the backtest only (not in production forecasts) | BSD-3-Clause |
| scipy 1.18.1 | Welch t-test for the Rising / Falling label | BSD (3-clause) |
| pytest 9.1.1 | Automated tests (1,332 collected on 31 Oct 2026) | MIT |
| psycopg[binary] 3.3.6 | PostgreSQL client for accounts (`DATABASE_URL`) | LGPL-3.0-only (package metadata) |
| pytest-cov >=5.0 | Test coverage (`backend/signals/requirements.txt`) | MIT (package metadata) |
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
| Replit Auth (OpenID Connect), issuer https://replit.com/oidc | Part of the Repl. No client secret: the client id is the Repl's `REPL_ID`, and the flow uses PKCE (S256). | Optional "Sign in". Returns the user id (`sub`), email, display name and profile image URL. The session is a signed cookie (key `SESSION_SECRET`). Not yet tested on the live app. |
| Google Tasks API v1 (scope `https://www.googleapis.com/auth/tasks`) with Google Identity Services (token client, `accounts.google.com/gsi/client`) | Free Google API. Needs the team's OAuth web client id (`GOOGLE_CLIENT_ID`, public, no secret); the button is hidden without it. The user consents in Google's own pop-up. | Optional "Send today to Google Tasks" on Today: creates one dated list with today's stops (title, minutes, resource link, why today) and an Undo that deletes it. The browser calls Google directly; the access token stays in the page's memory and Varity's server never sees it or the tasks. Built and tested with Google simulated; not yet tested with a real Google account or on the live app. [TEAM TO FILL: tick once tested live] |

The full list of APIs, models, datasets and tools, found by searching the code, is in section 4.4. Only the CV intake and the two optional steps (route advisor, pathway coach) call an LLM API. The forecast, role match, pathway dates and SDG parts call none.

### 3.2 Cloud platform and plan

| Service | Use | Plan and region |
|---|---|---|
| Replit Autoscale deployment (`deploymentTarget = "cloudrun"` in `.replit`) | Hosts the Varity server (FastAPI, no Streamlit). Build: `pip install -r requirements.txt`. Run: `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`. Live, published 24 Oct 2026. | 2 vCPU / 4 GiB. Recommended setting: max 1 instance. Plan: [TEAM TO FILL: Replit plan on the deploying account]. Region: [TEAM TO FILL: region shown in Replit] |
| Replit Secrets | Hold `ANTHROPIC_API_KEY`, `SESSION_SECRET` and `DATABASE_URL` (and the Production app secrets copy). | Replit AI Integrations is supported in code (section 4.4) and is used only when the team enables it. |
| Replit PostgreSQL (`DATABASE_URL`) | Holds accounts (table `users`) and saved profiles when configured. With no `DATABASE_URL`, the server uses the SQLite file. | Not yet tested on the live app. [TEAM TO FILL: confirm the database is attached to the deployment] |
| Replit App Storage | Will store the newest data snapshot (keeps the last 14). The Varity app does not read it yet. | Code built; Replit setup pending. [TEAM TO FILL: confirm the bucket exists] |
| Replit Scheduled Deployment | Will run `python -m engine.scheduled` daily at 09:00 Malaysia time (cron `0 1 * * *` in UTC). | Code built; Replit setup pending. [TEAM TO FILL: confirm the Scheduled Deployment is created and has run once] |

Known limit: with no `DATABASE_URL`, saved profiles live on the instance's disk, so a profile can reset when the app sleeps or restarts. The signals database always lives on that disk. "Try an example" re-creates one in one click. When the signals database is empty, a background pipeline run at startup rebuilds it (seen live: run 20261024T062256, 235 stories).

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
| Claude Haiku 4.5 (`claude-haiku-4-5`) through Replit AI Integrations | Anthropic, via Replit | The default whenever Replit AI Integrations is active (`intake/llm_extract.py`: `claude-haiku-4-5` if on Replit, else `claude-haiku-5-5`). Same checks. | Supported in code; used when the team enables the integration. |
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

A stronger model reviews each major part before we call it done. The team reviews every pull request. We run 1,332 automated tests (collected 31 Oct 2026), including tests that block look-ahead leaks. Every statistic traces to a file in `data/` or a cited source. Reviews found real faults, and we fixed them: bare "AI" inflated Machine Learning to 55% of posts, the first exposure score measured traffic, and the first uncertainty band covered only 65.9% of real values. Both members must be able to explain each part.

(85/100 words)

### 4.4 Full inventory (found by searching the code)

Sources for this list: `requirements.txt`, `backend/signals/requirements.txt`, every environment variable read in `engine/` and `backend/`, the base URLs and model ids in the code, `backend/signals/config/sources.yaml` and `data/SOURCES.md`. Where a licence or term is not recorded in the repository, the table says "not reviewed". Do not change that to a licence name without checking the source.

#### Language models and AI services

| Item | What for | Where in code | Terms |
|---|---|---|---|
| Anthropic Claude Haiku 5.5 (`claude-haiku-5-5`), Anthropic Messages API, direct key `ANTHROPIC_API_KEY` | CV intake; route advisor; pathway coach; CV builder agent; post labeller; new-title review; optional ranker steps | `backend/signals/intake/llm_extract.py` (`MODEL`), `advisor/llm.py`, `advisor/cv_agent.py`, `engine/llm_labels.py`, `engine/role_discover.py`, `trendsignal/config.py` (`enrich_model`) | Anthropic commercial API terms; paid tier on a team member's account |
| Anthropic Claude Sonnet 5.5 (`claude-sonnet-5-5`; `claude-sonnet-5` on Replit) | Optional prose brief ("editor") in the signal ranker; off by default | `trendsignal/config.py` (`editor_model`), `trendsignal/llm.py` | Same |
| Anthropic Claude Haiku 4.5 (`claude-haiku-4-5`) through Replit AI Integrations (`AI_INTEGRATIONS_ANTHROPIC_API_KEY`, `AI_INTEGRATIONS_ANTHROPIC_BASE_URL`) | The same jobs as Haiku 5.5, when the integration is active and no direct key is set | `trendsignal/config.py` (`use_replit_anthropic`), `intake/llm_extract.py` | Replit AI Integrations terms and credits; Anthropic terms. Not yet enabled on the live app (waiting for credits) |
| Replit AI Integrations (Anthropic and OpenRouter proxies) | Routes the calls above through Replit, billed to Replit credits | `trendsignal/config.py` (`_jev_connection`, `use_replit_anthropic`) | Replit terms |
| OpenRouter, through Replit AI Integrations (`AI_INTEGRATIONS_OPENROUTER_API_KEY`, `AI_INTEGRATIONS_OPENROUTER_BASE_URL`); model id `jev-latest` | Jev, TypeSafe AI's System One decision model, scores signals when `TRENDSIGNAL_RANKER=jev` (default is the formula, so off) | `trendsignal/config.py` (`_jev_connection`), `trendsignal/decision/jev.py` | OpenRouter and Replit terms; TypeSafe terms not reviewed |
| TypeSafe AI API, model id `jev-1.13.0` (`TYPESAFE_API_KEY`, `TYPESAFE_BASE_URL`) | Same Jev scoring, direct route. `typesafe-sdk` 0.7.5 (MIT) | `trendsignal/config.py`, `trendsignal/decision/jev.py` | TypeSafe terms not reviewed |
| OpenRouter chat models chosen at run time (`python -m eval.jury models` lists them) | Evaluation only: an LLM jury marks stories to test the ranker. Not part of the running app | `backend/signals/eval/jury.py` | OpenRouter and model-maker terms. Model ids are not fixed in code; record them when you run it |
| Statistical models (naive3, drift, damped trend, Welch test, conformal bands; gradient boosting rejected) | Forecast, band, trend label | `engine/forecast.py`, `engine/backtest.py`, `engine/scores.py` | Our code; SciPy, statsmodels and scikit-learn licences in 2.2 |

#### Live data and web services called by the running app

| Item | What for | Where in code | Terms |
|---|---|---|---|
| Hacker News via the Algolia HN Search API, https://hn.algolia.com/api (`search_by_date`, `items/<id>`) | "Who is hiring?" threads (demand data); "Fetch latest HN" button; daily refresh | `engine/backfill_hn.py`, `engine/refresh.py`, `POST /api/data/refresh` in `trendsignal/web/app.py` | Public, no key. No licence stated in `data/SOURCES.md` |
| Signal ranker sources (`backend/signals/config/sources.yaml`): 25 RSS or Atom feeds (lab and company blogs such as OpenAI, Google DeepMind, Hugging Face, Microsoft Research, NVIDIA, AWS; GitHub release feeds such as PyTorch, transformers, vLLM, LangChain; press such as TechCrunch AI and The Verge AI; Simon Willison's Weblog) | AI-trend ranking on the Signals screen | `trendsignal/collectors/rss.py` (`feedparser`) | Each publisher's own terms; not reviewed. We keep titles, links and short excerpts |
| arXiv API, https://export.arxiv.org/api/query (cs.AI, cs.CL, cs.LG, cs.SE) | Research papers for the ranker | `trendsignal/collectors/arxiv.py` | arXiv API terms; not reviewed in the repository |
| Hugging Face Daily Papers, https://huggingface.co/api/daily_papers | Papers for the ranker | `trendsignal/collectors/hf_papers.py` | Hugging Face terms; not reviewed |
| Hacker News front-page search (Algolia `search_by_date`, 60+ points, AI and software keywords) | Stories for the ranker | `trendsignal/collectors/hn.py` | Same as above |
| Bluesky public API (`public.api.bsky.app`), one curated account (`simonwillison.net`) | Posts for the ranker | `trendsignal/collectors/bluesky.py` | Bluesky terms; not reviewed |
| X API and Threads API | Built but **disabled** in `sources.yaml` (`enabled: false`; no keys). Not used | `trendsignal/collectors/x_api.py`, `threads.py` | Not used |
| Telegram Bot API | Optional alert delivery; off unless `TELEGRAM_BOT_TOKEN` is set. Not used | `trendsignal/delivery.py` | Not used |
| Replit Auth (OpenID Connect, https://replit.com/oidc) | Optional sign-in | `trendsignal/web/auth_api.py` | Replit terms |
| Google Identity Services and Google Tasks API v1 (`GOOGLE_CLIENT_ID`) | Optional "Send today to Google Tasks"; the browser calls Google, not our server | `frontend/app.js` | Google API terms; the user consents in Google's pop-up. Hidden without the client id |

#### Hosting and storage

| Item | What for | Where in code | Terms |
|---|---|---|---|
| Replit Autoscale deployment (`deploymentTarget = "cloudrun"`) | Hosts the app | `.replit` | Replit terms and plan |
| Replit PostgreSQL (`DATABASE_URL`) | Accounts and saved profiles (SQLite file if unset) | `trendsignal/web/accounts_store.py`, `psycopg` | Replit terms |
| Replit App Storage (`replit-object-storage`) | Data snapshots for the scheduled job (setup pending) | `engine/store.py` | Replit terms |
| Replit Secrets | `ANTHROPIC_API_KEY`, `SESSION_SECRET`, `DATABASE_URL` | Replit | Replit terms |

#### Datasets and reference files (committed in `data/`)

| Item | What for | Where | Licence |
|---|---|---|---|
| Hacker News "Who is hiring?" threads, 94 threads, 48,508 posts | Skill demand, role profiles, SDG sector tags | `data/hn_threads.csv`, `data/demand_monthly.csv`, `data/role_profiles.json` | Not stated (`data/SOURCES.md`). We commit counts and links only |
| Anthropic Economic Index, release 2026-06-26 | AI exposure of each skill | `data/exposure*.csv` | CC BY (data) |
| O*NET 31.0 and O*NET-SOC crosswalks | Occupation task text (first version) and code mapping | `data/exposure_map.csv` | CC BY 4.0 |
| GPTs are GPTs (Eloundou et al.) | Exposure cross-check | `data/exposure_indices.csv` | MIT |
| AIOE (Felten, Raj, Seamans) | Exposure cross-check | `data/exposure_indices.csv` | No licence file; we cite it |
| Microsoft "Working with AI" (Tomlinson et al.) | Exposure cross-check | `data/exposure_indices.csv` | CC BY 4.0 |
| MyMahir Malaysia Critical Occupations List (MyCOL) 2024/2025, TalentCorp | Shortage-occupation badges on routes | `data/mycol.json`, `data/mycol_role_map.json` | Public PDF; terms not reviewed. Read by eye from the PDF |
| DOSM, Big Data Analytics: Job Market Insights, quarterly "Data" Excel (release-document-log id 20742 for Q2 2026, release dated 18 Aug 2026), Department of Statistics Malaysia | Malaysian check under the CV & routes header and on the Skills radar. Sector level only (Information and communication; Professionals; Technicians and associate professionals), 28 quarters, Q3 2019 to Q2 2026. Not per role. | `engine/my_dosm.py`, `data/my_vacancies_quarterly.csv`, `engine/scheduled.py` (weekly update) | Official public statistics. Terms of use not reviewed: no terms page found on dosm.gov.my (its home page footer shows only a copyright line) |
| Trainocate Malaysia course pages (HRD Corp claimable programmes), 3 entries | HRD Corp option under a free resource | `data/hrd_programmes.json` (`checked_on` 2026-11-01), `frontend/screens.js` | Provider's own pages; we copy title, days, fee, link and its claim statement. Terms not reviewed |
| HRD Corp claimable-courses scheme page, https://hrdcorp.gov.my/hrdcorp-claimable-courses | Link only | `data/hrd_programmes.json` (`scheme_url`) | Not reviewed |
| Learning resources: 77 links to 50 providers (for example Microsoft Learn, freeCodeCamp, Hugging Face, TypeScript, Go, Rust, React, Node.js, PostgreSQL) | Free resource per skill; the team checked each link (HTTP 200) on 22 Oct 2026 | `data/resources.json` | Titles and links only; each provider's own terms |
| Synthetic example profiles (Aina, Ben, Chloe) | "Try an example" | `data/example_profiles.json` | Our own work |

Built but not used: collectors for Hiredly and Jobstore in `engine/`. They refuse to run without `--permission-confirmed`. JobStreet, Maukerja, Indeed and Ricebowl are not used because of bot challenges.

#### Python libraries of note

FastAPI, uvicorn, pydantic, httpx, requests, feedparser, apscheduler, jinja2, markdown, pyyaml, pypdf, anthropic, typesafe-sdk, psycopg, replit-object-storage, pandas, numpy, scipy, statsmodels, pytest. Versions and licences are in section 2.2. scikit-learn, joblib and threadpoolctl are for the rejected experiment only (`requirements-dev.txt`).

#### AI development tools

| Tool | Models | Extent |
|---|---|---|
| Claude Code (Anthropic CLI coding agent) | Claude Opus, Sonnet and Haiku models, as listed in 4.3 | Major: code, tests, data pipeline and documents |
| Replit Agent | [TEAM TO FILL: model] | Minor: environment setup |

### 4.5 Planned, not yet used

| Item | Plan | Status |
|---|---|---|
| KrackedDevs LiteLLM gateway (OpenAI-compatible, base URL `https://litellm.rapidscreen.io/v1`), models `deepseek-v4-flash` and `gpt-5.4-mini` | Bulk and background jobs only: relabel the HN posts, label new posts daily, review new job titles. Public HN text only, never CVs. Code checks every output. See `tasks/plan-credits.md` | **Not in code.** Nothing calls it. Declare it again when it is used, and add it to the Method screen |
| Runpod | None | **Not used.** No GPU work |

## 5. Sponsor resources

**Replit** (Core plan: [TEAM TO FILL: confirm]). We use it for hosting (Autoscale deployment, live and published 24 Oct 2026), optional sign-in (Replit Auth) and, when set up, PostgreSQL for accounts. Replit AI Integrations (Claude and OpenRouter) is supported in code and used when enabled. Claude calls otherwise use a team member's Anthropic key in Replit Secrets. We plan to use App Storage and Scheduled Deployments (code built; Replit setup pending). Replit is essential for the hackathon (compulsory). It is replaceable. `engine/store.py` has a local-folder store. Proof of use: the live URL https://verity--eezhan0805.replit.app. [TEAM TO FILL: attach any extra proof, such as a project history link.]

(98/100 words)

**RunPod:** Not used. We do no GPU work. The organisers confirmed on 22 Oct 2026 that RunPod proof is not needed without GPU use.

## 6. Data handling and limitations

### 6.1 Data handling and privacy

Sign-in is optional. For a signed-in user we store the Replit user id, email, display name and profile image link. These are personal data under Malaysia's Personal Data Protection Act 2010 (PDPA). Purpose: keep the user's profile and progress. The user can delete the account at any time. The data sit in Replit-hosted PostgreSQL. We sell or share none of it. A profile holds the skill list, target role and pathway ticks. For the CV builder we also store the cleaned CV text (emails, phones and links replaced by placeholders; deleted with the profile). We never store the uploaded file or tokens. An account with no login for 365 days is deleted. The privacy page is `frontend/privacy.html`. Raw Hacker News posts can hold names and contact details. They stay in gitignored folders on the team's machines and, during a refresh, in a temporary folder on the Replit server. A test checks that no committed data file holds an email address. Real CVs are out of scope: we use synthetic CVs only. CV text goes to Anthropic directly. Code redacts contact details and ID numbers first, but names can remain.

(150/150 words)

### 6.2 Known limitations and risks

1. Hacker News skews US and startup, not Malaysian.
2. Persistence won. At 12 months, the mean of the last 3 months (1.66 points of error) beat every trend model and gradient boosting.
3. The exposure indices disagree. Only "language" holds across them. Microsoft's index ranks eight occupations almost opposite to ours (rank correlation -0.79).
4. The scenario factor k = 2 is an assumption: the data give a 95% interval of -1.0 to 2.9 per 12 months, including 0.
5. New-skill discovery is late and weak: 3 hits in 15 at the 2023-06 test. A term needs 30 posts a year.
6. A bot challenge blocks JobStreet Malaysia, so we use no Malaysian job feed.
7. The Hacker News data is a US and startup sample; a Malaysian check (DOSM online vacancies, sector level, not per role) is in the app and is listed in section 4.4.
8. October 2026 is partial: its thread was open.
9. CV intake can miss a skill; the user edits the list. Its Claude call is not yet confirmed live.
10. Sign-in is untested on the live app and uses Replit only, not Google.

(150/150 words)

## 7. Compliance checklist

- [x] The repository was created after the build clock started. First commit: 21 Oct 2026, 23:49 (+0800).
- [x] The repository root holds an Apache License 2.0 file.
- [ ] The repository is public. [TEAM TO FILL: tick at submission]
- [ ] The committee accounts are added as collaborators. [TEAM TO FILL]
- [x] No secrets in the repository. A search for key patterns on 22 Oct 2026 found none, and the data job needs no secret.
- [x] The live prototype is a working deployment, not a video or mock-up: https://verity--eezhan0805.replit.app
- [x] Replit is part of the solution. RunPod proof is not needed (no GPU work).
- [ ] We declared every AI development tool we used. Claude Code and Replit Agent are declared. [TEAM TO FILL: tick after you confirm no other tool was used]
- [x] We use no real CVs in the demo. The personas and test CVs are synthetic. CV text goes to Anthropic directly. Signed-in users' email and name are personal data under PDPA (see 6.1).
- [ ] Sign-in works on the live Replit app. [TEAM TO FILL: tick after one live sign-in, sign-out and account delete]
- [x] Every dataset and library is listed with its licence. Open point: AIOE has no licence file (see 4.2).
- [ ] Both members completed the mandatory GenAI, Database and Cloud Deployment workshops. [TEAM TO FILL: tick only if both completed all three]
- [ ] Both members can explain every part of the project. [TEAM TO FILL: tick after you rehearse]

## 8. Declaration

[TEAM TO FILL: the template declaration wording, then the signature of the team leader, the name, and the date.]

Signature: [TEAM TO FILL]
Name: Tay Ee Zhan
Date: [TEAM TO FILL]
