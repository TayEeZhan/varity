# Technical & Tools Declaration (Finalist): Varity

Source text for `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf` (finalist template), filled by `scripts/fill_submission.py`.
It adds to the preliminary declaration (`docs/submission/tech-declaration.md`); everything new since then is marked **New**.
Items marked [TEAM TO FILL] are for the team.

## 1. Team & Project Overview

| Field | Entry |
|---|---|
| Team Name | Hokkien Mee Is Purple |
| Project / Solution Name | Varity |
| Name (Leader) | Tay Ee Zhan |
| Email & Phone (Leader) | (email removed) · phone on the submitted copy |
| University Affiliation(s) | (university removed) |
| Live Prototype URL | https://verity--eezhan0805.replit.app |
| Code Repository URL (public / access granted to judges) | https://github.com/TayEeZhan/varity (public) |

## 2. Architecture & Technology Stack

### 2.1 System Architecture Overview

Varity is one Python server and a static web app. FastAPI, run with uvicorn on a Replit Autoscale deployment, serves the HTML, CSS and JavaScript screens and the JSON APIs, and imports the engine modules.

The engine reads every monthly Hacker News "Who is hiring?" thread through the Algolia HN Search API (January 2019 to October 2026, about 48,500 posts). DeepSeek V4 Flash, through the KrackedDevs gateway, names the roles in each post with a quote; code checks every quote. Code tags 40 skills, builds monthly shares, forecasts 12 months ahead with a backtested model and a conformal band, labels trends with a Welch t-test, and joins an AI-exposure score per skill. A ranker re-ranks AI news every 15 minutes.

Claude Haiku 5.5 points at CV skills with quotes and writes CV wording; code checks each answer. Accounts and profiles live in Replit PostgreSQL. Each data refresh is saved as a snapshot in Replit App Storage, and the app serves the newest good one. A GitHub Action starts the refresh every day at 09:00 Malaysia time.

### 2.2 Languages, Frameworks & Libraries

| Name & Version | Purpose in Project | License |
|---|---|---|
| Python 3.12 | Server, engine and tests | PSF License |
| JavaScript, HTML, CSS (no framework, no build step) | Web app in `frontend/` | Our own code |
| fastapi >=0.115; uvicorn[standard] >=0.30 | Web server and JSON APIs | MIT; BSD-3-Clause |
| pydantic >=2.10 | Checks API input and structured model output | MIT |
| anthropic >=2.0.0 | Client for the Anthropic Messages API | MIT |
| httpx >=0.28; requests 2.34.2 | HTTP clients (signal ranker; Algolia HN API) | BSD-3-Clause; Apache-2.0 |
| apscheduler >=3.10,<4; feedparser >=6.0 | Re-ranks AI signals every 15 minutes; reads RSS and Atom feeds | MIT; BSD-2-Clause |
| pypdf >=6.21 | Reads text from an uploaded PDF CV | BSD-3-Clause |
| jinja2 >=3.1; markdown >=3.7; pyyaml >=6.0 | Ranker pages, briefs, configuration | BSD-3-Clause; BSD-3-Clause; MIT |
| pandas 3.0.6; numpy 2.5.4; scipy 1.18.1; statsmodels 0.15.0 | Tables, forecast maths, Welch t-test; damped trend (backtest only) | BSD-3-Clause (NumPy also 0BSD, MIT, Zlib, CC0) |
| psycopg[binary] 3.3.6; replit-object-storage 1.0.2 | PostgreSQL client for accounts; Replit App Storage client (snapshots) | LGPL-3.0-only; ISC |
| typesafe-sdk 0.7.5 | Optional Jev ranker (off by default) | MIT |
| pytest 9.1.1; pytest-cov >=5.0 | 1,375 automated tests | MIT |
| scikit-learn 1.9.1 (+ joblib, threadpoolctl) | Gradient-boosting experiment only, not deployed | BSD-3-Clause |
| Schibsted Grotesk and Lato (Google Fonts) | Web fonts | SIL Open Font License 1.1 |

## 3. APIs & Cloud Services

### 3.1 External APIs

| API & Provider | Purpose in Project | Access Tier (free / paid / sponsor-provided) |
|---|---|---|
| Algolia HN Search API (hn.algolia.com/api) | Monthly "Who is hiring?" threads (job demand) and HN stories for the ranker | Free, public, no key |
| Anthropic Messages API (Claude Haiku 5.5; Claude Sonnet 5.5) | CV intake with quotes; route advisor; pathway coach; CV builder and CV assistant; project-jury seat; Signals story labels; optional Signals brief | Paid, on a team member's Anthropic account (Goh Sheng Kuan); key in Replit Secrets |
| **New:** KrackedDevs LiteLLM gateway (OpenAI-compatible) | DeepSeek V4 Flash: role labels on every HN post (48,491 posts, US$2.63 in total), project "why" lines, project-jury seat. GPT-5.4 mini: review of new job titles, project-jury seat | Sponsor-provided (KrackedDevs US$20 keys); key in Replit Secrets only |
| News and research sources: the RSS / Atom feeds in `backend/signals/config/sources.yaml`, the arXiv API, Hugging Face Daily Papers, the Bluesky public API | The AI-trend signal layer (Signals screen) | Free, public |
| Replit Auth (OpenID Connect with PKCE) | Sign-in | Part of the Replit app |
| **New:** GitHub REST API | Reads a public repository the user submits (owner, push days, files) for the project station | Free; server read-only token |
| **New:** Credly public badge pages | Checks a certificate badge the user submits | Free, public |
| DOSM open data (Excel download) | Malaysian online-vacancy check, sector level | Free, Government Open Data Terms of Use 1.0 |

### 3.2 Cloud Platforms & Deployment

| Service & Provider | Purpose in Project | Plan / Region |
|---|---|---|
| Replit Autoscale deployment | Hosts the FastAPI server and the web app. Build `pip install -r requirements.txt`; run `python -m trendsignal serve --scheduler` | Autoscale, 2 vCPU / 4 GiB RAM, region Asia |
| Replit PostgreSQL | Accounts, saved profiles, CV drafts (SQLite file when no database is set) | Replit-hosted |
| **New:** Replit App Storage | Daily data snapshots (`latest.json` points to the newest good one; the last 14 are kept) | Default bucket of the app, set up 1 Nov 2026 |
| Replit Secrets | `ANTHROPIC_API_KEY`, `KD_API_KEY`, `SESSION_SECRET`, `GITHUB_TOKEN`, `VERITY_STORE` and others; never in the repository | Replit |
| **New:** GitHub Actions | Daily refresh at 09:00 MYT: wakes the app, calls `POST /api/data/refresh`, waits until it ends (`.github/workflows/daily-refresh.yml`). Replit allows one deployment type per app, so a Replit Scheduled Deployment could not run beside the site | Free tier, ubuntu-latest runner |

## 4. AI Tools, Models & Datasets

### 4.1 AI Models Used in the Solution

| Model & Version | Source / Provider | Usage (pre-trained / fine-tuned / self-trained) | License / Terms |
|---|---|---|---|
| Claude Haiku 5.5 (`claude-haiku-5-5`) | Anthropic API | Pre-trained. CV intake (points at skills with quotes; code checks each quote word for word); route advisor and pathway coach (re-order within code limits); CV builder and CV assistant (code rejects invented facts and stronger verbs); project-jury seat; Signals story labels | Anthropic commercial API terms |
| Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Anthropic API | Pre-trained. Optional Signals brief writer; runs only when `TRENDSIGNAL_BRIEFS=1` | Anthropic commercial API terms |
| **New:** DeepSeek V4 Flash (`deepseek-v4-flash`) | DeepSeek, via the KrackedDevs gateway | Pre-trained. Names the roles in each HN job post with a quote (code drops a label whose quote is not in the post); writes the project "why" line (code checks it); project-jury seat | KrackedDevs sponsor terms; DeepSeek API terms |
| **New:** GPT-5.4 mini (`gpt-5.4-mini`) | OpenAI, via the KrackedDevs gateway | Pre-trained. Reviews new job titles before code adds a role (it needs three quotes from real posts); project-jury seat | KrackedDevs sponsor terms; OpenAI API terms |
| Forecast models: naive3 (mean of the last 3 months) in production; naive, drift and damped trend tested; conformal 80% band; Welch t-test | Our code (NumPy, SciPy, statsmodels) | Self-built statistical models, chosen by a rolling-origin backtest | Our code (Apache-2.0) |
| Evaluation jury (offline, not in the running app): Claude Sonnet 5.5, GPT-6.1 Sol, Gemini 4 Argon | Anthropic, OpenAI, Google, via OpenRouter (Replit AI Integrations) | Pre-trained. Each labels the same news stories as human labellers, to grade the Signals ranker (`backend/signals/eval/jury.py`); NDCG@10 rose from 0.37 to 0.53 after the fixes it showed | OpenRouter and model-maker terms |
| HistGradientBoostingRegressor (scikit-learn 1.9.1) | scikit-learn | Self-trained experiment. **Not deployed:** it lost the backtest (2.06 vs 1.66 pp) | BSD-3-Clause |

A language model never sets a forecast, score, rank, date or course. With no key, or over a daily budget cap, code takes over (keyword pass, formula ranking, code pathway).

### 4.2 Datasets

| Dataset Name | Source / URL | Type (public / private / self-collected / synthetic) | License | Personal Data? (Y/N) |
|---|---|---|---|---|
| Hacker News "Ask HN: Who is hiring?" threads, 2019-01 to 2026-10 | hn.algolia.com/api | Public; we commit only aggregates and thread links | No data licence published; read through the public API only | Y in raw posts (kept out of the repository); N in committed files |
| Anthropic Economic Index, release 2026-06-26 | huggingface.co/datasets/Anthropic/EconomicIndex | Public | CC BY (data) | N |
| GPTs are GPTs; AIOE; Microsoft Working with AI; O*NET 31.0 | GitHub repositories and onetcenter.org (`data/SOURCES.md`) | Public (exposure cross-checks) | MIT; no licence file (cited); CC BY 4.0; CC BY 4.0 | N |
| **New:** DOSM Big Data Analytics: Job Market Insights (quarterly) | dosm.gov.my | Public | Government Open Data Terms of Use 1.0 | N |
| **New:** MyMahir Malaysia Critical Occupations List 2024/2025 | TalentCorp (public PDF) | Public | Terms not reviewed | N |
| **New:** HRD Corp-claimable programmes (3, Trainocate Malaysia); project (11) and certificate (13) lists | Provider pages, checked 31 Oct 2026 (`data/hrd_programmes.json`, `data/projects.json`, `data/certs.json`) | Self-collected (titles, days, fees, links) | Providers' own terms | N |
| Learning resources: 77 links (76 free, 1 free trial), HTTP 200 on 22 Oct 2026 | `data/resources.json` | Self-collected (titles and links) | Providers' own terms | N |
| Example profiles (Aina, Ben, Chloe) and 7 demo CVs | `data/example_profiles.json`, `demo-cvs/` | Synthetic | Our own work | N (synthetic) |

### 4.3 AI-Assisted Development Tools

Did your team use any generative-AI tool to help create code, design, text, or other project material? **Yes**

| Tool & Version | Used For | Extent of Use (minor / moderate / major) |
|---|---|---|
| Claude Code (Anthropic CLI), with Claude Opus 5.5, Sonnet 5.5 and Haiku 5.5, and its skills and plugins (for example design and code-review skills) | Code, tests, data pipeline, documents, UI design and the CodeTour guides (`.tours/`), from the team's prompts and plans. 126 commits carry its "Co-Authored-By: Claude" line; `CLAUDE.md` and `.claude/` hold its project settings | Major |
| Replit Agent | Replit environment setup: the `.replit` file, the App Storage bucket link and the "Published your App" commits (27). It wrote no app code | Minor |

**How the team reviewed AI output.** Both members read and run every change, and every pull request is reviewed. 1,375 automated tests run before a merge, including tests that block look-ahead leaks and tests that check every model answer. Every statistic traces to a file in `data/` or a cited source. Reviews found real faults that we fixed: a bare "AI" keyword inflated Machine Learning to 55% of posts, the first exposure score measured traffic, and the first uncertainty band covered only 65.9%. Both members can explain each part.

## 5. Sponsor-Provided Resources

Did your project use any official SDC sponsor-provided resource? **Yes**

| Sponsor | Resource (API / credits / platform / data) | How It Was Used in the Project |
|---|---|---|
| KrackedDevs | US$100 AI API credit (five US$20 keys), LiteLLM gateway | DeepSeek V4 Flash labelled the roles in 48,491 HN posts (US$2.63, `data/llm_usage.csv`) and labels each day's new posts; GPT-5.4 mini reviews new job titles; both sit on the project jury |
| Replit | Platform: Autoscale deployment, Auth, PostgreSQL, App Storage, Secrets | Hosts the live app, sign-in, accounts and the data snapshots. The US$100 Replit credits did not reach us; the organisers waived the Replit proof of usage |
| RunPod | None | Not used: no GPU work |

**Essential or replaceable?** Both can be replaced. KrackedDevs makes the role labels sharper and cheap; without its key, code falls back to title rules or to Claude. Replit hosts the app; the server is plain FastAPI, the snapshot store has a local-folder version (`engine/store.py`) and the daily job is one command, so any Python host works.

## 6. Security, Privacy & Responsible Use

### 6.1 Data Handling & Privacy

Users sign in with Replit Auth. We store the Replit user id, email, display name and profile image link, which are personal data under Malaysia's PDPA 2010, only to keep the user's profile and progress. A profile holds skills with their evidence quotes, the target role, the plan and its ticks, and, for the CV builder, the cleaned CV text. Code replaces emails, phones and links with placeholders before any model call and before storage. We never store the uploaded file. Data sit in Replit PostgreSQL; we sell or share none of it. A user can delete the account at any time, and an account unused for 365 days is deleted. CV text goes to Anthropic (Claude Haiku) for reading. Only public Hacker News text goes to KrackedDevs. Real CVs are out of scope: the consent box asks for synthetic CVs. Privacy page: `frontend/privacy.html`.

### 6.2 Known Limitations & Risks

1. Hacker News is a US and startup sample, not Malaysian; the app shows a DOSM sector check beside it.
2. Twelve months ahead, persistence beats trend models, so most roles read "Steady"; we show a band, not a promise.
3. The Fast scenario's k = 2 is an assumption (the data interval is −1.0 to 2.9).
4. A model can miss or invent; every answer is checked against quotes or code limits, and code takes over on failure.
5. Single providers (Anthropic, KrackedDevs, Replit): each has a code fallback and a daily budget cap.
6. Autoscale sleeps: the daily refresh wakes it, and a failed run keeps the last good snapshot.
7. The fairness tests cover name, age, gender, nationality and school, not every bias.

## 7. Compliance & Readiness Checklist

- [x] All APIs, cloud services, AI tools, models, and datasets used in the project are declared in this document.
- [x] All third-party code, datasets, and models are used in accordance with their licenses, and attribution is provided where required.
- [x] No API keys, passwords, or other credentials are exposed in the code repository, prototype, or this document.
- [x] Any use of generative-AI tools for development has been disclosed and reviewed by the team.
- [x] Any use of official SDC sponsor resources has been declared in Section 5.
- [x] The prototype described here is accessible to judges through the links provided in Section 1.
- [x] All fields in this template have been completed within the word limits stated.

## 8. Declaration

By submitting this document, the team leader confirms that the information provided is complete and accurate to the best of the team's knowledge, and that every API, cloud service, AI tool, dataset, model, and sponsor resource used in the project has been declared.

Signature: see the signed copy · Name: Tay Ee Zhan · Date: 1 November 2026
