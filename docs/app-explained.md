# Verity (Varity) explained: a guide for the team lead

For: Ee Zhan. Goal: you can explain the whole app to judges in 1 to 2 hours of reading, and answer any question.
Written 31 Oct 2026 from the working tree (uncommitted changes included), not only from the docs.
Rule used in this guide: every number comes from a file in the repo. The file name is in brackets, for example `(data/backtest.json)`.
When a doc and the code disagree, the code wins. The mismatches are listed in the last section.

How to read it. Section 1 is the one-page version: read it first and say it aloud. Section 2 walks the app. Section 3 is the "7 pillars" of app infrastructure. Section 4 is the data and the maths. Section 5 is AI. Section 6 is trust. Section 7 is Q&A. Section 8 is the glossary. Section 9 lists doc-versus-code mismatches.

---

## 1. Verity in one page

**Brand note.** The repo and docs say "Verity". The app on screen says "Varity". They are the same app.

**The problem (Domain 1 brief, `BRIEF.md`).** The organisers ask for an AI tool that does 4 things:
1. It tracks AI progress.
2. It predicts which skills and jobs rise and fall.
3. It matches people to future roles.
4. It builds reskilling pathways with SDG links.

Hard rules from the brief: public, open or synthetic data only; name the LLM you use; cite a source for every recommendation; never invent jobs, courses or statistics; support human judgement, do not replace it. The brief also requires: a profile intake (CV or form), a dated and updatable trend source, an explainable match score with a skills gap, an ordered pathway with time estimates and free or low-cost resources (HRD Corp), SDG tags, and at least 2 scenarios labelled as estimates.

**Who it is for.** Junior and mid-level tech developers and career switchers in Malaysia (`README.md`). The demo user is **Aina**, a synthetic person (`data/example_profiles.json`): Python, SQL, PostgreSQL, Docker, AWS.

**The 6-stage journey** (this is the "flow map" in the app):
1. **Give your skills.** Upload a CV or press "Try an example".
2. **Check them.** The app shows each skill with a quote from the CV. You keep or remove each one.
3. **See your routes.** The app ranks up to 8 future roles for you, with a match score and a skill gap.
4. **Pick a route.** You choose one role.
5. **Get a pathway.** An ordered learning plan with free resources and dated daily tasks.
6. **Do it day by day.** The Today screen lists the next stops. You tick them off, or send them to Google Tasks.

**Aina in one example** (I re-ran the code on 31 Oct to check this):
- Her 5 skills give **#1 Backend Engineer, match 66%** (exact: 0.655), **rank score 0.759**, outlook Rising.
- Rank = 0.7 x match + 0.3 x outlook = 0.7 x 0.655 + 0.3 x 1.0 = 0.759.
- Biggest gap skills: Go, Kubernetes, Terraform. **Adding Go lifts the rank to 0.843** (Kubernetes 0.819, Terraform 0.817).
- Her #2 is AI/LLM Application Engineer (match 39%, rank 0.571) and #3 is Data Engineer (match 51%, rank 0.509).
- Replay the data as of 2025-06 and Backend Engineer drops to 58% and Data Engineer (48%) becomes #2. The output follows the data. That is the "change the trend data now" proof.

**What makes it different** (say these 4 things):
1. **Code makes every number.** No language model makes a score, a rank, a forecast or a date. The LLM only points at words in a CV (and code checks the quote).
2. **Every forecast was tested before we trusted it.** A simple method ("about the same as the last 3 months") beat trend lines and machine learning in a backtest. We ship the simple method with a tested uncertainty band.
3. **Everything has a source and a date.** Each number links to Hacker News threads or a data file.
4. **We say what is weak.** The Method screen shows where our own tests are poor (for example, the band is too wide, the AI-exposure stance is contested).

**Honest limit to say first.** The job data is Hacker News "Who is hiring?" posts. It is US- and startup-heavy, not Malaysian. The judges flagged this. We added a Malaysian check from DOSM (official online vacancies). It is at sector level, not per role. See sections 2.3, 6 and 7.

---

## 2. A walk through the app, screen by screen

The page is one HTML file with no build step. The address uses a hash (`#/route`). The top bar shows: Flow map, CV & routes, Today, Pathway, My CV, Signals, Job forecast, How Varity works (`frontend/index.html`). Two screens are not in the top bar but exist: **Skills radar** (`#/radar`) and **Method** (`#/method`). The landing page links to them (`frontend/landing.js`, `frontend/app.js` route table).

Note: the "Team" (HR) page was built and then removed on 1 Nov because it does not fit a worker-facing site (`HANDOFF.md`). The files are deleted in the working tree.

### 2.1 Landing page (`#/`)
- A short pitch, a live mini view of the skills radar, and links to "Open the skills radar" and "See the method".
- Calls `GET /api/roles/forecast`, `GET /api/skills/radar`, `GET /api/evidence` for the live bits (`frontend/landing.js`).

### 2.2 Flow map (`#/flow`)
- The 6-stage journey drawn like a transit map (`frontend/diagram.js`).
- It says plainly what is not built: Google sign-in, and two-way Google Tasks sync.

### 2.3 CV & routes (`#/profile`) - the main screen
**What you do.** Tick a consent box ("I use a sample CV, not a real person's. The text goes to Anthropic for reading", `frontend/screens.js`), upload a CV, or press "Try an example" (Aina, Ben or Chloe; Ben and Chloe are also synthetic).

**API calls (in order).**
1. `POST /api/cv/extract` reads the CV and returns review rows (skill, quote, years). Nothing is saved yet.
2. `POST /api/profile/apply` saves the rows you kept.
3. Or `POST /api/profile/example` saves a synthetic example. No LLM and no CV.
4. `GET /api/roles/suggestions` returns the ranked roles.
5. `POST /api/profile/target-role` saves the route you pick.
6. `POST /api/profile/remove` removes one skill (it stays removed).

**What a route card shows.**
- Role name, match % and a fit label (code decides the label).
- Reason chips (short facts with a source and a date, written by code in `backend/signals/advisor/chips.py`).
- A **scenario toggle**: "Expected (estimate)" and "If AI speeds up (estimate)". These were renamed from Moderate and Fast (`frontend/screens.js`, `advisor/service.py` `SCENARIO_LABELS`). The "If AI speeds up" scenario adds a note such as "about -6.1% role demand vs expected" and **never changes the ranking**.
- **"Why NN%?"** panel (details/summary). It shows the formula parts and the top 3 skills that would raise the score, each with a free resource. See 2.4.
- **"Details"** panel. It holds the SDG tags, the "reason line" for the SDG sector, the goal line, and the MyCOL badge (see below).
- A **goal picker** ("I care about: health, climate, education ..."; 8 sectors in `data/role_sdg.json`). See 2.5.
- **One Malaysia line under the header** (not per card): "Malaysia check (DOSM, official online vacancies): Information and communication sector 13,960 in Q2 2026 (-17.8% on a year ago) ..." with a Source link. Code builds it from `meta.malaysia` on `GET /api/roles/suggestions` (`frontend/screens.js` `malaysiaLine`, `frontend/app.js` `STATE.malaysia`). Why one line and not one per role: DOSM does not split vacancies by job title, so any per-role number would be invented.

**Where the numbers come from.**
- Malaysia line: DOSM "Big Data Analytics: Job Market Insights", see 4.14.
- Match score: learned skill weights per role (`data/role_profiles.json`), see section 4.
- Outlook (Rising / No clear change / Falling): Welch test on role demand (`data/role_trends.json`).
- Forecast and band: `data/role_forecast.json`.
- MyCOL badge: `data/mycol.json` (10 occupations from TalentCorp's MyCOL 2024/2025 list) mapped to our roles by `data/mycol_role_map.json`. The badge says it is "our direct or partial match (team judgement)". It never says the role itself is on the list. MyCOL is a shortage list, not a vacancy count.

### 2.4 "Why NN%?" - the score breakdown
This is pure arithmetic from numbers `match_roles` already returns (`engine/roles.py` `score_breakdown`). No model.
- `match` = weight of the role's skills you have / weight of all its skills. The weights sum to 1.
- `rank` = 0.7 x match + 0.3 x outlook. Outlook = 1.0 Rising, 0.5 No clear change, 0.0 Falling (`engine/roles.py`: `MATCH_WEIGHT`, `FUTURE_WEIGHT`, `FUTURE_BY_TREND`).
- For each gap skill: "+match" equals its weight; "+rank" equals 0.7 x weight. The top 3 are shown.
- Aina / Backend Engineer, real output: Go +0.120 match, new rank 0.843; Kubernetes +0.086, 0.819; Terraform +0.083, 0.817.
- **The 0.7 / 0.3 split is team judgement, not fitted to data.** Say this before a judge asks.
- A role with match below 0.20 is not ranked (`LOW_MATCH_BELOW`). It cannot rank on outlook alone.

### 2.5 The goal picker (SDG goal)
- You pick a sector (health, climate, ...). The request adds `goal=<sector id>`.
- **Routes:** the app adds a goal line, for example "N of M posts came from health employers". If the sample is too small it says "too few posts to re-rank; the order is unchanged". Re-ranking happens only when a sector cell is reliable: at least 30 role posts, 3 different employers, and 10 posts in the sector (`engine/sdg.py`: `MIN_N`, `MIN_EMPLOYERS`, `MIN_SECTOR_POSTS`). **We did not lower these to force a change.** With today's data the route order does not change (`HANDOFF.md`).
- **Pathway:** here the goal does change things. Skills linked to the goal's SDG targets move to the front inside each stage. Stages, dates and minutes stay the same. If none of your gap skills links to the goal, the plan says so.
- The skill-to-SDG tags are team judgement (`sdg_reason` in `data/taxonomy.json`), and the screen says so.
- The "reason line" per role is built by code from `data/role_sdg.json` (`engine/sdg.py` `role_reason`), for example "Most over-represented sector".

### 2.6 Pathway (`#/pathway`)
- `GET /api/pathway?roleId=...&scenario=...&goal=...&hoursPerWeek=...` returns the plan.
- **Three stages** (`engine/pathway.py`):
  1. *No-regret*: needed by 2 or more of your ranked roles, not Falling, not AI-substitutable.
  2. *Near-term*: in the top half of your gap skills by current share of posts.
  3. *Future bet*: Rising, or AI-complement.
  Also a leftover group "other". In the "If AI speeds up" scenario, stage 3 moves to second place.
- **Dated tasks.** Each task is at most 45 minutes (`MAX_TASK_MINUTES`), Monday to Friday, Malaysia time (UTC+8). Daily budget = hours per week x 60 / 5.
- **Resources** come only from `data/resources.json`: 77 resources, all link-checked (HTTP 200) on 2026-10-22. The minutes are a team estimate, not a provider figure. A skill with no verified resource gets no task. The engine cannot invent a course.
- **Learning-time note** (new): "Times are for the starter course only. Job-level skill needs practice on real projects after it." (`LEARNING_NOTE` in `engine/pathway.py`). Say this if a judge asks "is 12 hours really enough?"
- **HRD Corp employer-funded option** (new, `data/hrd_programmes.json`). It shows as an optional line next to the free resource: "Employer-funded option (HRD Corp): course by provider, N days, RM fee". Today the file has **3 entries** only: Python (PCAP, 3 days, RM3,500), AWS (Developing on AWS, 3 days, RM5,400) and GCP (Data Engineering on Google Cloud, 4 days, RM9,600), all from Trainocate Malaysia's own page. The file says it is for staff of HRD Corp-registered employers, and that the employer must apply through HRD Corp before training starts. The `checked_on` date in the file reads 2026-11-01. Re-check the links before the pitch. A skill with no programme shows nothing.
- **Plan changes.** If you saved a plan and the data later changes it, the app offers Keep / Revert (`POST /api/pathway/decision`). If a new rising skill appears, it offers Add / Not now. "Outlook changed" shows when your target role's outlook moved since you accepted the plan (`advisor/planner.py`).
- "I learned it" marks a skill as learned: `POST /api/profile/learned`. Tick state: `PUT /api/profile/progress`.

### 2.7 Today (`#/today`)
- The next dated stops from the pathway, each with a "Why today" line and its source and date.
- Button: "Send today to Google Tasks" (only if `GOOGLE_CLIENT_ID` is set). The browser gets a Tasks-only token from Google and writes the list itself, so our server never sees the token or the tasks.

### 2.8 Skills radar (`#/radar`) with "Trend data" bar
- A chart of every skill: demand (share of posts) and tested change. **Only a skill with a tested Rising or Falling label gets a colour.** All others are grey, so the chart never claims a change the test did not find (`engine/radar.py`). Your own skills are marked. A skill with a contested AI stance shows a hollow mark.
- Today's tested labels (`data/skill_scores.json`): Rising: Rust, PostgreSQL, Terraform, RAG. Falling: Ruby, Microservices. The other 29 labelled skills show "No clear change"; 5 rare skills have no label.
- **The "Trend data" bar** is the answer to "change the trend data now":
  - **Replay** (dropdown): pick a past month, one of 2023-12, 2024-06, 2024-12, 2025-06, 2025-12, 2026-10 (the as-of points of the role profiles, `data/role_profiles.json`). The browser keeps the month in `sessionStorage` and sends `asOf=YYYY-MM` on these calls: `/api/roles/suggestions`, `/api/pathway`, `/api/skills/radar`, `/api/data/status`. The server recomputes scores and role trends cut at that month (`advisor/service.py` `_replayed`, which calls `engine.scores.build_scores(as_of=...)` and `build_role_trends(..., as_of=...)`). A bad month returns 422. **No server state changes, so one judge's replay does not affect another viewer.**
  - **Back to latest**: clears the stored month.
  - **Fetch latest HN now**: `POST /api/data/refresh`. It starts a background thread that downloads the newest HN thread and rebuilds the data. At most 1 start per 10 minutes for the whole server (otherwise 429 with `retryAfter`). A failure keeps the last good data.
  - **Limit to say honestly:** the replay cuts the skill scores and the role trends. The forecast chips (`role_forecast.json`) stay at latest (`HANDOFF.md`).
  - The bar always shows: "Source: HN Who is hiring - as of YYYY-MM - fetched <date>".

- **Malaysia block** (from `malaysia` in `GET /api/skills/radar`, drawn by `frontend/screens-evidence.js` `malaysiaSeries`): a small line chart and the last 8 quarters of DOSM online vacancies for the Information and communication sector, with the note "DOSM does not split by job title, so this is not a per-role number" and a source link.

### 2.9 Job forecast (`#/forecast`)
- `GET /api/roles/forecast` returns `data/role_forecast.json` untouched (or the newest daily-refresh snapshot). The `meta.source` says "daily refresh" or "committed".
- For each of 8 ranked roles: share of HN posts now, 12-month forecast with an 80% target band, a Rising / Falling label, the "If AI speeds up" value, and a "declining" flag (Falling AND more than 50% of the role's skill weight in Falling skills; no role meets it today).
- Today: Full-stack Web Developer has the biggest share (11.7%), then Backend Engineer (10.2%) and Platform/DevOps (9.0%); AI/LLM Application Engineer is 6.5% and Rising (`data/role_forecast.json`, 3-month pooled share).
- The October 2026 thread is still open, so a **nowcast** blends the part-month toward last month (section 4.6). The page shows posts so far this month.
- The Analytics Engineer role is not ranked: only 11 single-role posts (`data/role_profiles.json`).

### 2.10 Signals (`#/signals`)
- `GET /api/signals`. The top 10 AI and dev-tooling stories, ranked by impact, plus weekly skill momentum.
- **Skill momentum table** (`renderSignals` in `frontend/screens-explore.js`; changed 31 Oct 2026). Columns: Skill, "This week", "Usual week" (the average of the 4 weeks before this one), and "Change" as a % of the usual week. Counts are news mentions. "New" shows when the usual week is under 1 mention, because a percentage would mislead. Rows are sorted by change.
- Built by the "AI Trend Signal Layer" in `backend/signals/` (Sheng Kuan's part). It polls RSS feeds (OpenAI, DeepMind, Google AI, Hugging Face, Microsoft Research, NVIDIA, AWS, GitHub releases, Meta, arXiv, HF Daily Papers, Hacker News front page, Simon Willison, TechCrunch AI, The Verge AI and more; `backend/signals/config/sources.yaml`) every 15 minutes while the server runs with `--scheduler`.
- Stories are cleaned, merged when they are duplicates (URL match, then TF-IDF), turned into a feature vector by code, and scored. **A deterministic formula ranks by default.** Jev (TypeSafe AI's decision model, via OpenRouter on Replit) can rank only if it beats the formula on a hand-labelled gold set (`backend/signals/ARCHITECTURE_JEV_RANKER.md`). Each row says who ranked it ("deterministic formula", "Jev", or mixed).
- **Honest limit.** The Signals screen is evidence and context. It is **not** fed into the forecast. The link from news momentum to the forecast is a plan that must pass a backtest first (`docs/architecture.md` 3.17, 4.3).
- Footer text: if the server is unreachable, the page falls back to a dated offline snapshot and says so (`frontend/data.js`).

### 2.11 Method (`#/method`)
- `GET /api/evidence`. Shows the backtests for skills and roles, the AI-exposure cross-check, the k assumption and the data sources with licences.
- This is where you prove "we tested it". Numbers: section 4.
- **Fairness check block** (new, `frontend/screens-evidence.js` `fairnessBlock`): "Same skills, same result" (points at `backend/signals/tests/test_fairness.py`) and the limit "the job-post data itself may carry hiring bias; we do not correct it".
- **Privacy notice link** (`privacy.html`) under that block.

### 2.12 My CV (`#/cv`) - the CV builder
- `POST /api/cv/generate` writes a new CV for a target role from your saved (cleaned) CV text and your skill ledger. `GET/PUT /api/cv/draft` load and save the draft. `POST /api/cv/agent` is a chat agent that proposes one edit at a time.
- **Guardrails** (`advisor/cv_writer.py`, `advisor/cv_agent.py`): the model copies each job and project word for word; a checker drops every claim that the original CV, the skill ledger or your own answers cannot back; it refuses stronger verbs than the original (for example "helped" cannot become "led"); jobs the model left out are put back; an edit is only a proposal until you accept it; at most 15 tool steps per message. With no model or no usable answer, you get the original CV with an updated skills section.
- Learned-through-Verity skills are marked "learned through Varity".

### 2.13 Privacy notice (`privacy.html`)
- A page that follows Malaysia's PDPA 2010 and its 7 principles (General, Notice and Choice, Disclosure, Security, Retention, Data Integrity, Access). Linked from the footer and from the CV consent box. Details in section 6.

### 2.14 Sign-in chip (top right)
- Optional Replit sign-in. Without it everything works with a browser token. See pillar 4 below.

---

## 3. The 7 pillars of app infrastructure, mapped to Verity

A "pillar" is one layer that every real app needs. Judges ask about them in the Technical Execution score. Here is each one.

### 3.1 Frontend
- **What it is.** The part the user sees in the browser.
- **Verity.** Plain HTML, CSS and JavaScript. **No build step, no framework.** Files in `frontend/`: `index.html`, `app.js` (state, routing, API calls), `screens.js`, `screens-explore.js`, `screens-evidence.js`, `screens-cv.js`, `landing.js`, `diagram.js`, `data.js` (offline snapshot), CSS files, and `privacy.html`.
- **How it is served.** FastAPI mounts the folder at `/` (`app.py`: `StaticFiles`). One server serves both the pages and the API.
- **Why.** Fast to load, nothing to compile, easy to read in a demo, and low-bandwidth friendly. Fonts come from Google Fonts (a third-party request).
- **Offline.** If the API is down, `data.js` shows dated real snapshots, labelled "offline snapshot". It never shows synthetic data as real.
- **Page state.** Kept in a JavaScript object (`STATE` in `app.js`). The replay month sits in `sessionStorage`.

### 3.2 Backend
- **What it is.** The server code that does the work and answers API calls.
- **Verity.** Python 3.12 (`.replit`), **FastAPI** served by uvicorn. Entry: `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`.
- **Layout.**
  - `backend/signals/trendsignal/web/` : the routes (`app.py`, `cv_api.py`, `roles_api.py`, `evidence_api.py`, `auth_api.py`) and the account store (`accounts_store.py`).
  - `backend/signals/advisor/` : role advisor, reason chips, pathway planner, CV writer, CV agent, LLM wrapper.
  - `backend/signals/intake/` : CV intake (read, redact, ask the model, verify, review).
  - `backend/signals/trendsignal/` : the AI-news pipeline (collectors, clustering, scoring, ranker, scheduler).
  - `engine/` (repo root): the maths. Plain Python that reads and writes files in `data/`. No server, no database.
- **Envelope.** Every `/api` answer has the same shape: `{success, data, error, meta}` (`app.py` `envelope`).
- **Rate limits** (in memory, per IP): 6 CV reads a minute, 30 profile calls, 30 role calls, 4 paid-model calls a minute, 10 admin calls (`cv_api.py`, `roles_api.py`, `app.py`).
- **Background jobs** (APScheduler, only with `--scheduler`; `trendsignal/scheduler.py`): AI-news pipeline every 15 minutes; `forecast_refresh` daily at 06:30; `retention` clean-up daily at 06:45 and once at start-up.
- **Dependencies** (`requirements.txt`): pandas 3.0.6, numpy 2.5.4, scipy 1.18.1, statsmodels 0.15.0, requests 2.34.2, replit-object-storage 1.0.2, plus `backend/signals/requirements.txt`.

### 3.3 Database
Verity has two stores. Do not mix them up.

**A. The app database (read and write).** Code: `backend/signals/trendsignal/web/accounts_store.py`. It uses **Replit PostgreSQL when `DATABASE_URL` is set, else a SQLite file**. Tables:

| Table | What it holds |
|---|---|
| `owner_profiles` | `owner_key`, `profile_json` (skills with evidence, target role, plan state, tick progress), `updated_at` |
| `users` | Replit user id (`sub`), email, display name, image URL, created and last-login times (only if you sign in) |
| `owner_cvs` | the **cleaned** CV text (emails, phones and IDs replaced) for the CV builder |
| `owner_cv_drafts` | the CV builder draft |
| `owner_cv_notes` | notes you gave the CV agent |

- `owner_key` is `t:<hash>` for a browser token (only the SHA-256 of the token is stored) or `u:<id>` for a signed-in account.
- A second SQLite file, `backend/signals/data/trendsignal.db`, holds the AI-news pipeline results and a cache of LLM answers (`advisor/llm.py` `cached_call`).
- The uploaded CV **file** is never stored.

**B. The "data warehouse" (read-only files in `data/`).** There is no warehouse server. The committed files are the warehouse:
- Demand: `demand_monthly.csv`, `role_demand_monthly.csv`, `title_counts_monthly.csv`, `ai_context_monthly.csv`, `hn_threads.csv` (94 threads).
- Results: `skill_scores.json`, `role_profiles.json`, `role_trends.json`, `role_forecast.json`, `role_sdg.json`, `skill_sdg.json`.
- Tests of the method: `backtest.json`, `role_backtest.json`, `nowcast_backtest.json`, `ml_backtest.json`, `k_estimate.json`, `exposure_agreement.json`.
- Reference: `taxonomy.json` (40 skills), `roles.json` (9 roles), `resources.json` (77), `hrd_programmes.json` (3), `mycol.json` (10), `example_profiles.json` (3), `SOURCES.md`.
- **Only aggregates are committed.** Raw post text stays in `data/raw/` (gitignored) because posts hold personal data.
- **Snapshots.** The daily job writes new results to **Replit App Storage** (`engine/store.py`): `snapshots/<UTC time>/...`, newest 14 kept, with `latest.json` written last so a failed run never breaks readers. The web app reads the newest snapshot (checked every 10 minutes) and falls back to the committed `data/` (`advisor/service.py` `current_data_dir`). **Status per the docs: the bucket and Scheduled Deployment are not yet set up** (`HANDOFF.md`, `docs/replit-schedule.md`).

### 3.4 Authentication
- **What it is.** How the app knows who you are.
- **Verity has two modes. Sign-in is optional.**
  1. **No sign-in: browser token.** The first save creates a random 32-byte token. The browser sends it as the `X-Profile-Token` header. The server stores only its SHA-256.
  2. **Replit sign-in.** OpenID Connect with PKCE. Issuer `https://replit.com/oidc`; client id is the Repl's `REPL_ID`. Routes: `/api/login/prepare`, `/api/login`, `/api/callback`, `/api/me`, `/api/logout`. On only if `REPL_ID` and `SESSION_SECRET` are set (`auth_api.py`).
- **Session cookie.** `varity_session`: HMAC-SHA256 signed with `SESSION_SECRET`, **HttpOnly**, `Secure` (except on local http), **SameSite=Lax**, 30 days. Tokens from Replit are used once in the callback and are never stored.
- **First sign-in** moves your anonymous profile into the account.
- **Delete.** `DELETE /api/me` deletes the user and the profile.
- **Admin routes** (`/api/admin/run`) need an `X-Admin-Token` header and return 404 if no admin token is set.
- Status per docs: tested locally; "not yet tested on the live Replit app" (`README.md`, `docs/architecture.md` 3.20).

### 3.5 APIs

**Internal APIs** (all under `/api`; unknown `/api/...` paths return 404 or 405 in the same envelope):

| Method and path | Purpose | Main inputs | Main output |
|---|---|---|---|
| `GET /api/signals` | AI-news page | none | run info, top 10 stories, skill momentum |
| `GET /api/roles/forecast` | Job forecast page | none | `role_forecast.json`; `meta.source` |
| `GET /api/health` | source health of the news pipeline | none | per-source status |
| `POST /api/admin/run` | start the news pipeline now | `X-Admin-Token` | 202 started |
| `GET /api/data/status` | which data this viewer sees | `asOf` | mode, asOf, fetchedAt, replayMonths |
| `POST /api/data/refresh` | fetch newest HN thread, rebuild | none | 202, or 429 with `retryAfter` |
| `POST /api/cv/extract` | read a CV, return review rows | `text` or `file_b64` or `sample`; `use_ai` | `review_id`, rows, redaction counts, dropped |
| `POST /api/profile/apply` | save the rows you kept | `review_id`, `kept_ids`, years, name, target role | profile (+ token) |
| `GET /api/profile/examples` | list the 3 synthetic examples | none | examples |
| `POST /api/profile/example` | save a synthetic example | `id` | profile (+ token) |
| `GET /api/profile` | read saved profile | token or cookie | profile |
| `POST /api/profile/remove` | remove one skill | `skill_id` | profile |
| `PUT /api/profile/progress` | save ticked tasks | `signature`, `doneIds` | profile |
| `DELETE /api/profile` | delete the profile | token or cookie | `deleted` |
| `POST /api/profile/learned` | mark a pathway skill as learned | `skill` | profile |
| `POST /api/profile/target-role` | save the chosen route | `roleId` | profile |
| `GET /api/roles/suggestions` | ranked roles + reasons + breakdown | `scenario`, `hoursPerWeek`, `goal`, `asOf` | roles, lowMatch, notRanked, formula; `meta.malaysia` (DOSM block) |
| `GET /api/pathway` | the plan with dated tasks | `roleId`, `scenario`, `hoursPerWeek`, `goal`, `asOf` | steps, tasks, SDG lines, HRD option |
| `POST /api/pathway/decision` | Keep/Revert a changed plan, Add/Later a skill | `roleId`, `action`, `skill` | new pathway |
| `GET /api/skills/radar` | the radar | `asOf` | points, sentences, table, `malaysia` (DOSM block) |
| `GET /api/evidence` | Method screen | none | backtests, exposure, k, sources |
| `POST /api/cv/generate` | new CV for a role | `roleId`, `jobAd` | draft + markdown |
| `GET /api/cv/draft`, `PUT /api/cv/draft` | load, save the draft | draft, facts | draft + markdown |
| `POST /api/cv/agent` | one chat turn with the CV agent | message, history | ask / plan / edit / say |
| `POST /api/login/prepare`, `GET /api/login`, `GET /api/callback`, `GET /api/logout` | Replit sign-in flow | | redirects, cookie |
| `GET /api/me`, `DELETE /api/me` | who am I; delete my account | cookie | account / `deleted` |

That is still 31 routes, recounted on 31 Oct from the `@app.get/post/put/delete` decorators in `trendsignal/web/*.py`. The DOSM check added fields to 2 existing routes, not new routes.

**External APIs and services Verity calls:**

| Service | Used for | When | Key needed |
|---|---|---|---|
| **Hacker News via Algolia API** (`hn.algolia.com/api`) | download "Who is hiring?" threads | backfill (one-off), daily refresh, "Fetch latest HN now" | none |
| **Anthropic Claude** | read a CV; optional route advisor; optional pathway coach; CV writer and agent; (planned, not run yet) post labeller and title review | when a key exists | `ANTHROPIC_API_KEY` (team key) or Replit AI Integrations (`AI_INTEGRATIONS_ANTHROPIC_*`) |
| **Jev (TypeSafe AI) via OpenRouter** | optional second ranker for the Signals screen | only if configured; off by default; the formula ranks | `TYPESAFE_API_KEY` or `AI_INTEGRATIONS_OPENROUTER_*` |
| **RSS / arXiv / HF Papers / HN front page** | news for the Signals screen | every 15 min | none |
| **Replit Auth (OIDC)** | optional sign-in | on sign-in | `REPL_ID`, `SESSION_SECRET` |
| **Replit App Storage** | daily snapshots | scheduled job | set up in Replit |
| **Google Identity Services + Tasks API** | optional "Send today to Google Tasks" | in the browser | `GOOGLE_CLIENT_ID` |
| **Google Fonts** | page fonts | page load | none |

Datasets used offline (not live APIs): Anthropic Economic Index release 2026-06-26 (CC BY), O*NET 31.0 (CC BY 4.0, v1 only, superseded), GPTs-are-GPTs, AIOE and Microsoft "Working with AI" indices (cross-check only), TalentCorp MyCOL 2024/2025 (`data/SOURCES.md`, `docs/architecture.md` 3.4, 3.15).

**DOSM** is used offline, not as a live API: a weekly job downloads the quarterly Data Excel from dosm.gov.my and rewrites `data/my_vacancies_quarterly.csv` (see 4.14). The running app only reads the CSV. OpenRouter and Jev are optional and off by default.

### 3.6 Payments and third parties
- **Payments: none. Out of scope** per the brief. Verity sells nothing and charges nothing. Course fees (HRD list) are shown for information only.
- **Third parties and what they see:**
  - **Anthropic** sees redacted CV text, only when AI is on. Contacts and IDs are replaced first, but a name can remain.
  - **Hacker News / Algolia** gives public posts. We send no user data.
  - **Replit** hosts the app and holds the database, secrets and storage. Replit sees sign-in data.
  - **Google** only if the optional Tasks button is used, and the data goes browser-to-Google.
  - **TalentCorp (MyCOL), Anthropic Economic Index, O*NET** : public datasets, read offline.
  - **Course providers** : we only link to them. **Trainocate Malaysia** links appear in the HRD option. Free resources link to official docs (Go tour, Kubernetes docs, MDN and so on).
- **Cost to run** (planning estimates, `tasks/plan-final-round.md` item 11). Forecast, match and pathway cost nothing per user (plain Python on files). The only per-user cost is the CV read. The plan estimates about $20 to $30 a month at 1,000 users. These are estimates: check current prices before you say a number. Spend caps in code: $1 a day each for the CV intake and for the advisor (`VERITY_INTAKE_DAILY_BUDGET_USD`, `VERITY_ADVISOR_DAILY_BUDGET_USD`).

### 3.7 Infrastructure and DevOps
- **Hosting.** Replit. `.replit` sets `deploymentTarget = "cloudrun"`, which is Replit's **Autoscale** deployment. Build: `pip install -r requirements.txt`. Run: `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`. Port 8080 maps to external port 80. The README says 2 vCPU / 4 GiB, region Asia. The live URL is https://verity--eezhan0805.replit.app/#/.
  - The deployed app is on Autoscale, not a Reserved VM. A Reserved VM would keep the scheduler alive all day. On Autoscale the in-process 06:30 job only runs if an instance is awake. That is why the plan uses a separate **Scheduled Deployment** (`python -m engine.scheduled`) (`docs/replit-schedule.md`). The Scheduled Deployment is not set up yet.
- **Secrets.** In Replit Secrets, never in the code: `ANTHROPIC_API_KEY`, `SESSION_SECRET`, `DATABASE_URL`, `GOOGLE_CLIENT_ID` (`.env.example`).
- **Source control.** GitHub `TayEeZhan/varity` (README and the submission files all use `varity`). 149 commits from 2026-10-21 to 2026-10-31 (`git log`). The brief warns that a pre-built-looking repo or one big late commit can disqualify a final-round team.
- **Tests.** Root `pytest` collects **1,332 tests** (868 in `tests/`, 464 in `backend/signals/tests/`; I counted with `pytest --collect-only` on 31 Oct). Full run is about 8 minutes (`CLAUDE.md`). Backend only: `pytest -q` in `backend/signals/`. There are tests that the future cannot leak into a past forecast, that every chosen resource link exists in the resource list, that no committed data file holds an email, and the new fairness test (section 6). `HANDOFF.md` still says 975 (old). Use 1,332 only after you re-run the full suite and it passes. I did not run the full suite.
- **How a deploy happens.** You commit and push to GitHub (only when you say so, `CLAUDE.md`). In Replit: Git pane, Pull, then Republish. Replit runs the build command and starts the server. Data files ship in the repo.
- **How data stays current.** Daily job: download newest HN thread, rebuild skill and role files, save a snapshot to App Storage. The web app reads it within 10 minutes. If the job fails, `latest.json` does not move.

---

## 4. The data pipeline end to end

```
HN threads (Algolia) -> clean posts -> tag 40 skills -> monthly shares
   -> logit -> Welch trend label  +  naive3 forecast + conformal band -> backtest
   -> skill scores (+ AI exposure, scenarios)
posts -> match role by title -> mask title -> single-role posts -> learn skill weights per role
   -> role trends + role forecast -> match_roles (rank) -> pathway -> SDG tags
```

### 4.1 Source: Hacker News "Who is hiring?"
- A monthly thread. Each top-level comment is one job post.
- `data/hn_threads.csv`: **94 threads, 48,508 top-level posts, 2019-01 to 2026-10**.
- Strength: free, public, dated, monthly, tech-only, with a URL to cite per thread.
- Weakness: self-selected, US- and startup-heavy; posts per month fell, so we use shares, not counts (`data/SOURCES.md`).

### 4.2 Tagging: 40 skills
- `data/taxonomy.json` has 40 skills in 6 categories: language 14, data 9, cloud/devops 6, framework 5, ai_ml 5, practice 1.
- Each skill has a regex pattern. `engine/tagging.py` cleans HTML and URLs, then tests each pattern.
- Plain rules: "PostgreSQL" counts as PostgreSQL only (not SQL). "React Native" is not React. A bare "AI" in a company blurb is not a skill.
- Why regex and not an LLM: it gives the same answer every run, costs nothing, and a judge can read it.

### 4.3 Demand share
- For each skill and month: share = posts that mention the skill / all posts that month (`data/demand_monthly.csv`).
- A 3-month trailing smooth is kept (`share_smooth`). It only looks back, so no future month changes the past.
- Why share and not count: posts per month fell (a mean of 703 in 2019 to 310 in the last 12 months, `data/SOURCES.md`). Counts would make every skill look like it is dying.

### 4.4 Logit (the scale we do the maths on)
- Shares are stuck between 0 and 1. The logit stretches them: `logit(p) = ln(p / (1 - p))`. The app uses `y = logit((m + 0.5) / (n + 1))` where m = mentions and n = posts (`docs/architecture.md` 3.5; `engine/forecast.py` `smoothed_share`).
- The +0.5 and +1 stop a zero count from breaking the logit.
- Errors are shown back on the share scale in percentage points (pp).

### 4.5 Trend label: Welch test
- Question: is the last 12 months different from the 12 months before?
- A **Welch t-test** compares the two sets of monthly logit shares. It does not assume the two sets have the same spread.
- Rule (`engine/forecast.py`): p below 0.05 gives Rising or Falling; otherwise "No clear change". A skill needs at least 30 mentions in the 24 months (`TREND_MIN_MENTIONS`).
- **The label describes the past. It is not a forecast.**
- Tested: the label pointed the right way over the next 12 months in **67.2% of 720 labelled cases** (Rising 60.5%, Falling 71.9%) (`data/backtest.json`). Cases overlap, so this is a rough guide, not 720 independent tests. For roles: 69.3% (`data/role_backtest.json`).

### 4.6 Forecast: naive3 and the nowcast
- **naive3** = the mean of the last 3 months on the logit scale, held flat for 12 months. In plain words: "demand next year looks like the last 3 months".
- Four models were backtested: naive (last month), naive3, drift (trend line) and damped trend. Production allows only naive and naive3; the choice goes by lowest 12-month error (`engine/forecast.py`).
- **Backtest.** Rolling origins: at each past month, forecast 12 months ahead using only earlier data, then compare with what happened. Early origins 2021-12 to 2023-10 (23) are for choosing. **Test origins 2023-11 to 2025-10 (24) are held out.** 616 skill-origin pairs on test (`data/backtest.json`).
- **MAE** (mean absolute error) at 12 months, test, in percentage points of share:

| Model | MAE at 12 months |
|---|---|
| naive3 | 1.661 |
| naive | 1.806 |
| drift | 2.128 |
| damped | 2.266 |
| gradient boosting (ML, rejected) | 2.064 (`data/ml_backtest.json`) |

- naive3 beats naive by 0.145 pp, 95% interval 0.068 to 0.222 (skill-resampled) (`data/backtest.json`). Trend models lose because 12-month demand is close to "no change".
- **For roles:** naive3 1.604 pp vs naive 1.632 pp. The gain (0.028) has an interval that includes zero, so with only 8 roles we cannot tell them apart (`data/role_backtest.json`, `docs/architecture.md` 4.4).
- **Nowcast** (new). The open month is incomplete (October 2026: 266 posts so far, `data/skill_scores.json`, `data/role_forecast.json`). The code blends it toward last month: `(m + k x s_prev) / (n + k)`. The weight k is chosen per day open, by a backtest on past threads cut at day 1, 3, 7 and 14 (choose with months before 2024-07; test from 2024-07). Result for roles: k = 100, 50, 10, 0 for days 1, 3, 7, 14. Test error for roles: day 1 0.765 -> 0.653 pp; day 3 0.526 -> 0.459 pp; from day 14 there is no blending (`data/nowcast_backtest.json`).

### 4.7 The conformal band (uncertainty)
- **Idea.** Every past forecast has a known error. Use the recent errors to size the band for the next forecast.
- **How** (`engine/forecast.py`): take the last 24 forecast errors whose outcome is known (window set in advance), scale each by how noisy the skill is (sigma of month-to-month change over 24 months), take the 80th percentile, then add and subtract it around the forecast on the logit scale and convert back. Target: 80% of real values inside the band.
- **Result on held-out data:** the 80% band covered **93.8%** of real values at 12 months (mean over horizons 91.1%) (`data/backtest.json`). For roles: 93.6% at 12 months, mean 88.0% (`data/role_backtest.json`).
- **Read it honestly.** 93.8% against a target of 80% means the band is **too wide, not too tight**. It is conservative. The mean width at 12 months runs from 5.2 pp (skills under 3% share) to 12.8 pp (skills over 10% share) (`data/backtest.json` `by_share_group`). A window of 36 months gave 92.9%, so the window is not the cause. The Method screen says this.

### 4.8 Data-volume status
- `ok`: mean 5 or more mentions a month over 12 months. Forecast and band shown.
- `low_volume`: below that but 30 or more mentions in 24 months. Counts and label only.
- `rare`: under 30 mentions in 24 months. Counts only.
- Today: **27 ok, 8 low_volume, 5 rare** (`data/skill_scores.json`).

### 4.9 AI exposure and the "If AI speeds up" scenario
- **AI exposure `e_s`.** From the Anthropic Economic Index (release 2026-06-26): the share of an occupation's Claude.ai conversations where the AI did the task ("automation" bucket). Skills inherit it through a skill category mapped to occupations; that map is **team judgement** (`data/SOURCES.md`). Each skill gets a stance: AI-complement, neutral or AI-substitutable.
- **Cross-check.** We compared with 3 other indices. Only the `language` category (14 skills) is robust; the other 5 categories are contested (`data/exposure_agreement.json`). The production stance was not changed; a flag was added.
- **Scenario formula.** `fast = expected x (1 - k x e_s)`, where `e_s` is the skill's exposure minus the mean of the 40 skills. **k = 2 is an assumption.**
- **Can data pin k down?** No. The estimate is 1.81 per 12 months, 95% interval -1.04 to 2.91. So k = 2 is inside it, and so is k = 0 (`data/k_estimate.json`). Say: "k is a labelled assumption. We tried to measure it and the data cannot decide."
- The "If AI speeds up" band is never graded; only the expected band is backtested.

### 4.10 Roles: profiles and match
- 9 roles in `data/roles.json`; 8 are ranked (Analytics Engineer is not: only 11 single-role posts).
- **Which posts belong to a role.** A regex on the post's title text. One post can match several roles.
- **Mask the title, keep single-role posts.** The title is hidden before skills are tagged, so "LLM engineer" does not create an LLM skill by itself. Only posts that name exactly one role are used to learn skills. Total single-role posts behind the 2026-10 profiles: **2,580** (sum of `n_single_role_posts` in `data/role_profiles.json`).
- **A skill enters a role profile** if it appears in at least 10 single-role posts, has `p_role` of at least 0.08 (share of the role's posts that mention it), and **lift** of at least 1.1 (how much more often the role mentions it than all posts). The top 10 stay; their weights sum to 1 (`engine/roles.py`).
- **Tiers:** solid (150+ single-role posts and 5+ skills), rough (50+), not_ranked (under 50). Today: solid = Data Engineer, Backend, Full-stack, Platform/DevOps; rough = Data Scientist, ML Engineer, AI/LLM App Engineer, Mobile; not ranked = Analytics Engineer.
- **No look-ahead.** Six profile as-of points exist: 2023-12, 2024-06, 2024-12, 2025-06, 2025-12, 2026-10. Each learned only from posts before its date. A replay picks the latest point at or before the chosen month.
- **Match and rank.** See 2.4. Example profile (Data Engineer, 2026-10): Python weight 0.213, Machine Learning 0.129, TypeScript 0.129, PostgreSQL 0.119, AWS 0.097, SQL 0.084, dbt 0.065, Airflow 0.058, Snowflake 0.058, GCP 0.048 (`data/role_profiles.json`). Aina holds Python, PostgreSQL, AWS, SQL = 0.213 + 0.119 + 0.097 + 0.084 = 0.513 -> 51% match. That is exactly what the app shows.
- **Synonyms.** TypeScript merges into "JavaScript / TypeScript" so a skill never counts twice (`engine/roles.py` `merge_synonyms`).

### 4.11 Role forecast, ledger and new roles
- **Role forecast** reuses the skill functions (no copied maths; a test checks the function objects are identical). 12 months ahead, naive3 level, 80% band pooled over 8 roles (q at 12 months = 1.549), `data/role_forecast.json`.
- **Ledger** (`engine/ledger.py`): each daily run saves the forecast and grades it when the target month completes. This builds a public track record.
- **New-role discovery** (`engine/role_discover.py`): counts job titles per month (`data/title_counts_monthly.csv`, history since 2019). It lists titles no role covers. With AI credits, Claude Haiku reviews each title; a new role needs 3 quotes from 3 different posts, and code checks each quote. **Not run yet:** AI credits are not in.
- **Claude post labeller** (`engine/llm_labels.py`): built but **not run**. The files it would create (`role_labeller.json`, `llm_role_labels.csv`) do not exist in `data/`. Role labels today come from the title regex. Say so.

### 4.12 Pathway
Section 2.6 covers the rules. In one line: gap skills -> three stages -> one free, link-checked resource each -> dated tasks of at most 45 minutes -> SDG lines. The stage rule is code. Minutes are a team estimate. The reasons shown (chips) have a source and a date.

### 4.13 SDG
- **Skill tags.** Each of the 40 skills has SDG targets and a one-line reason in `data/taxonomy.json` (team judgement).
- **Role/sector tags** are measured, not hand-written: code finds which sectors (8 in `data/sdg_sectors.json`) employers in the role's posts belong to, after removing perk and legal lines so a benefits line does not tag a post as "health" (`engine/sdg.py`). Output: `data/role_sdg.json`, counts, shares and thread URLs only.
- **Plan lines.** Each plan carries SDG 4.4 (skills added, hours) and SDG 8.5 (movement toward a role and its demand trend) lines.
- **The user test from the finalist guide:** "if the tag were removed, would the user lose anything?" Now yes: the goal picker reorders the pathway inside stages and adds goal lines. On routes it re-ranks only when data is reliable.
- Sector sectors and SDG targets: 8 sectors with targets e.g. climate 7.2 and 13.2, health 3.8 and 3.b, education 4.3 and 4.4 (`data/role_sdg.json`).

### 4.14 Malaysia check: DOSM online vacancies (`engine/my_dosm.py`)
- **Source.** DOSM "Big Data Analytics: Job Market Insights", quarterly "Data" Excel (release-document-log id 20742 for Q2 2026, released 18 Aug 2026).
- **What is kept.** 3 rows x 28 quarters (Q3 2019 to Q2 2026) = 84 rows in `data/my_vacancies_quarterly.csv`: sector "Information and communication", and MASCO major groups "Professionals" and "Technicians and associate professionals". Each row names its sheet and cell.
- **Checks.** Code reads the Excel with zipfile and XML (no Excel library) and asserts that each stored number equals the cell it names. A changed layout raises an error and the old CSV stays. Code does the percentages (`summary()`). No LLM touches this.
- **Not per role.** DOSM gives only two tables: by economic activity and by MASCO major group. There is no job-title split, so the app never shows a Malaysia number for one role.
- **Update.** `engine/scheduled.py` runs `my_dosm.update()` on Mondays (UTC). It looks for the next quarter's release page. It never raises and keeps the old CSV on any failure.
- **Use.** A cross-check only. It does not feed the forecast or the rank score.
- **Test.** `tests/test_my_dosm.py` with `tests/fixtures/my_dosm_mini.xlsx`. (I did not run it.)

---

## 5. Where AI is used, and where it is NOT

**Rule: LLMs never produce forecast numbers, parameters, scores, ranks or dates.** (`CLAUDE.md`, `docs/architecture.md` 1.)

### 5.1 Where an LLM is used

| Feature | What the model does | What code does | Always works without it? |
|---|---|---|---|
| **CV intake** (`intake/llm_extract.py`) | Points at skill mentions and returns an exact quote for each (schema-constrained JSON). | Drops any skill whose quote is not in the CV word for word; checks the skill name is in the taxonomy; reads years itself from dated lines; caps at 40 mentions. | Yes: a keyword pass takes over. "Try an example" uses no model. |
| **Route advisor** (`advisor/llm.py`) | Optionally re-orders roles by **at most 2 places** and picks among reason chips that code wrote; writes one summary line. | Checks IDs, the 2-place limit, banned number words; the **fit label always comes from code**. | Yes: formula order stands. |
| **Pathway coach** (`advisor/llm.py`) | Optionally re-orders steps **inside one stage**, picks among listed resources, writes one "why" line. | Never changes a date, minute count or stage. | Yes. |
| **CV writer / agent** (`advisor/cv_writer.py`, `cv_agent.py`) | Rewrites bullets; proposes edits. | Checker drops unsupported claims, blocks stronger verbs, keeps all jobs. User must accept each edit. | Yes: original CV + updated skills. |
| **Signals ranker** (`trendsignal/`) | Optional Jev decision model for tier and impact probabilities; optional Haiku to pick a category only when rules are unsure (off by default). | A deterministic formula ranks by default; guardrails in the ranker. | Yes. |
| **Post labeller and title review** (`engine/llm_labels.py`, `role_discover.py`) | Labels which roles a post hires for, with quotes; reviews new titles. | Drops any label whose quote is not in the post; regex backup; a drift check. | Built, **not run** (no credits yet). |

### 5.2 Where an LLM is NOT used
Tagging skills in posts, demand shares, the Welch test, the forecast and band, backtests, AI exposure, the scenario formula, role profiles and match, the rank score, the score breakdown, the pathway stages and dates, SDG tags and goal lines, resource selection, HRD options, fairness. All of that is plain Python (pandas, numpy, scipy, statsmodels).

### 5.3 Which model
- **Default model id: `claude-haiku-5-5`** ("Claude Haiku 5.5") with the team's own Anthropic key (`intake/llm_extract.py` `MODEL`).
- If no Anthropic key is set and Replit AI Integrations are enabled, the code uses **`claude-haiku-4-5`** (Replit's list lags). The same rule is in `advisor/llm.py` and `engine/llm_labels.py`.
- You can override with `VERITY_INTAKE_MODEL`, `VERITY_ADVISOR_MODEL`, `VERITY_COACH_MODEL`, `VERITY_CV_AGENT_MODEL`, `VERITY_LABEL_MODEL`.
- Temperature 0 and a pinned model id for the labeller. A daily spend gate stops calls after the budget ($1 each by default).
- The brief says "name the LLM": say "Claude Haiku (5.5 on our own key, 4.5 through Replit AI Integrations)". The README and tech docs say only 5.5. See section 9.

### 5.3b Credits plan: which AI job runs where (`tasks/plan-credits.md`; KrackedDevs side **built, not run yet**)
Two credit pools: Replit ($100, Claude through Replit AI Integrations, also pays hosting) and KrackedDevs ($20 per teammate key, GPT and DeepSeek models, **no Claude**, OpenAI-compatible gateway).
- **Replit (Claude Haiku), live and user-facing:** CV reading, route advisor, pathway coach, CV builder and CV agent.
- **KrackedDevs, bulk and background:** the one-off relabel of the 48,508 HN posts (`deepseek-v4-flash`, fall back `gpt-5.4-nano`), daily labelling of new posts, weekly new-title review (`gpt-5.4-mini`), and, as a proposal that needs Sheng Kuan's agreement, the Signals ranker steps.
- **Stays as now:** Jev scoring through Replit OpenRouter.
- **Safety:** code checks every quote, so a cheaper model can miss labels but cannot invent them. Only public HN text goes to KrackedDevs, never CVs.
- **Status:** built, runs only when `KD_API_KEY` is set. `engine/llm_client.py` (stdlib HTTP, usage log `data/llm_usage.csv`, budget guard `KD_CAP_USD`, default $15). `llm_labels.py` and `role_discover.py` pick it automatically. **Not run yet** (no key used, no relabel done).
  - **Details.** `engine/llm_client.py` is used by `engine/llm_labels.py` and `engine/role_discover.py` when `KD_API_KEY` is set. Models: `deepseek-v4-flash` for labels, `gpt-5.4-mini` for the title review. Every call is logged to `data/llm_usage.csv` (tokens and USD, never the key or any text). The per-job cap is `KD_CAP_USD`, default 15. `python -m engine.llm_labels backfill --limit N` is a dry run: it labels the first N posts, writes nothing and prints the real cost. Prices in the log are assumed list prices unless the gateway returns a cost header. The Signals ranker is unchanged (needs Sheng Kuan's approval). Do not say it is running.

### 5.4 Guardrails (say these)
1. **Quote check.** The model must give an exact quote. Code looks for it in the text. No quote, no skill.
2. **Whole-word check.** The skill phrase must sit inside its own quote.
3. **Schema.** The model returns JSON in a fixed shape; anything else is dropped.
4. **Limits.** At most 2 places of re-order; no number words in free text; chips carry all numbers.
5. **Prompt-injection hint.** Lines in a CV that look like instructions are flagged (`injection_hint`) and CV text is passed as data only.
6. **Cost caps and rate limits.** $1 a day per feature; 4 paid calls a minute per IP.
7. **Fallback.** Any model failure returns the code-only answer; it is never an HTTP error. The answer says why (`llmStatus`).
8. **Cache.** The same prompt returns the stored answer, so the demo is repeatable.

---

## 6. Trust, privacy and fairness

### 6.1 Privacy (PDPA 2010, `privacy.html`)
- **Demo uses synthetic CVs only.** The page tells users not to upload a real person's CV, and a consent tick comes before upload.
- **What is stored:** the skill list with quotes, target role, pathway ticks; the cleaned CV text for the CV builder; and, only if you sign in, your Replit id, email, name, image link and sign-in times.
- **Not stored:** the CV file; Replit tokens.
- **Redaction.** Before the model sees the CV, code replaces emails, phone numbers (9+ digits) and ID numbers (`intake/normalise.py`). **A name can still remain.** Evidence quotes are cut to the sentence around each skill, but a name in the same sentence can remain. The plan item "strip the first line" is not in the privacy notice; do not claim it.
- **Disclosure.** Only Anthropic sees CV text (when AI is on).
- **Retention.** Accounts with no sign-in for **365 days** are deleted, with their profiles: at start-up and by a daily job at 06:45 (`accounts_store.py` `RETENTION_DAYS = 365`). The notice says "12 months".
- **Access and deletion.** You can see your profile on CV & routes. "Delete my profile" calls `DELETE /api/profile`. Account deletion is `DELETE /api/me`.
- **Security.** HttpOnly signed cookie, 30 days; rate limits; token stored only as a hash.
- **Aggregate data only** is committed; raw posts stay out of git.

### 6.2 Fairness
- **Claim.** The matcher reads only skills (and years). Name, age, gender, nationality and school cannot move the result.
- **Proof.** `backend/signals/tests/test_fairness.py`: three CVs with the **same skills line** but different name, age, pronoun, title, nationality and school are read through the real API and must give the same ranked roles and scores. (I read the test setup; I did not run it.)
- **Limit to state.** The source data (HN posts) may carry hiring bias. We do not correct it.

### 6.3 Limits you must say out loud
1. **HN is US-heavy, not Malaysian.** The judges flagged it. Our answer: skills like Python and Kubernetes are global; MyCOL badges add a Malaysian shortage-list cross-check; and the **DOSM online-vacancy check is now built** (4.14). Limit: it is sector level (Information and communication; Professionals; Technicians), not per role, and it is a cross-check, not a forecast input. Online ads are not jobs, and the ad counts are not comparable in size to HN posts.
2. **A share is not a job count.** HN posts are a sample.
3. **The 0.7 / 0.3 rank weights and the k = 2 are judgement,** and the app labels them.
4. **Labeller accuracy is unmeasured against human labels** (the user chose a fully automatic process, `HANDOFF.md`).
5. **No real-user testing yet.** The pilot idea (XMUM career centre) is a next step.
6. **Malaysian job boards were dropped.** JobStreet blocked bots with a Cloudflare challenge, and we do not bypass bot protection (`docs/jobstreet.md`). `engine/my_jobs.py` stays in the repo, unused; `data/my_jobs_snapshots.csv` holds only a header.
7. **HRD list is small** (3 entries). A person must check each programme, so an empty list is safer than an invented one.
8. **Exposure is the 2026-06 release and is not cut by date,** so a replay uses today's exposure.

---

## 7. Judge Q&A (short, honest answers, with where to click)

The Finalist guide asks for 7 things. Questions 1 to 7 match them.

**1. "Please change the trend data now."**
Go to Skills radar. In "Trend data", pick Replay 2025-06. The page shows "Replay of real data as of 2025-06" and the routes change: for Aina, Backend Engineer falls from 66% to 58% and Data Engineer (48%) becomes #2. Click "Back to latest" and it returns. "Fetch latest HN now" downloads the real newest thread (limit: once per 10 minutes). The replay changes only your own tab. Limit: forecast chips stay at latest.

**2. "Where does this recommendation come from?"**
CV & routes -> Details and the reason chips. Each chip has a source and a date. The role weights come from counted Hacker News posts (`data/role_profiles.json`), the outlook from a Welch test on role demand, and each resource from a link-checked list of 77 (`data/resources.json`). No model wrote the number.

**3. "Why this score?"**
Click "Why 66%?" on Backend Engineer. It shows 0.7 x 0.655 + 0.3 x 1.0 = 0.759, and what each missing skill would add: Go +0.120 match (rank 0.843). We say that 0.7 / 0.3 is our judgement, not fitted.

**4. "How do you keep the data current, and what does it cost?"**
A daily job downloads the newest HN thread and rebuilds the files; the app reads the snapshot within 10 minutes. Setup of the bucket and the scheduled deployment is the open task. Forecast, match and pathway cost nothing per user; the CV read costs a few cents at most. Our plan estimate is $20 to $30 a month at 1,000 users (`tasks/plan-final-round.md`, an estimate, not measured). The code caps spend at $1 a day per feature.

**5. "What if AI moves faster than your forecast?"**
Switch the scenario to "If AI speeds up (estimate)". The formula is expected x (1 - k x exposure) with k = 2. It moves future-bet skills earlier in the pathway and shows a demand-change estimate, but never reorders roles. We tried to measure k and the data cannot pin it down (interval -1.04 to 2.91), so we label it an assumption.

**6. "How do you stop invented jobs or courses?"**
Courses come only from `data/resources.json`; each URL returned HTTP 200 on 2026-10-22; a skill with no verified resource gets no task. A test checks every chosen link exists in that list. We list roles whose skills are counted from real posts, not vacancies. For CVs, the model must quote the CV and code checks the quote.

**7. "Show me the SDG link. Would the user lose anything without it?"**
CV & routes -> pick a goal, e.g. health. The pathway moves goal-linked skills first inside each stage and adds a goal line. On routes we show the sector share and say "too few posts to re-rank" when the sample is small. We did not lower the thresholds to force a change.

**8. "Hacker News is US data. How is this Malaysian?"**
It is not Malaysian data, and we say so. Skills are global; MyCOL badges add Malaysian shortage evidence; HRD Corp options and Malaysia-time scheduling are local. The DOSM online-vacancy series is built as a sector-level cross-check (see 8a).

**8a. "Is this relevant to Malaysia?"**
Partly, and we say which part. The job-post data is Hacker News: global and US-heavy. The Malaysian parts are: (1) the DOSM check, official online vacancies for the Information and communication sector, Q3 2019 to Q2 2026 (latest, Q2 2026: 13,960, which is -17.8% on Q2 2025, both from `data/my_vacancies_quarterly.csv`), shown under the CV & routes header and on the Skills radar; (2) MyCOL shortage badges; (3) HRD Corp options (3 entries); (4) the PDPA privacy notice and Malaysia-time scheduling. What we do not claim: a Malaysian number for one role (DOSM has no job-title split), or a Malaysian forecast. The DOSM series checks the HN sample; it does not drive scores. Click: CV & routes (Malaysia line), then Skills radar (Malaysia block).

**9. "Isn't this just a chatbot? Where is the AI?"**
There is no chatbot for the core. Statistics and learned role profiles do the work, and a gradient-boosting model was trained and rejected. LLMs only read CVs and word a few checked lines.

**10. "Why trust a forecast that is basically 'no change'?"**
Because we tested it. On 616 held-out forecasts naive3 had 1.66 pp error, trend lines 2.13 and 2.27, and gradient boosting 2.06. So we show a level, a tested band and an observed label, and make no claim of a precise future. (Method screen.)

**11. "Why did machine learning lose?"**
At 12 months demand is near "no change", and we have about 25 usable skills and a few dozen independent months, so a flexible model learns patterns that do not repeat. It scored 2.064 pp against 1.661. The rule was fixed in advance: promote only if the 95% interval of the gain is above zero. We kept the experiment as evidence (`data/ml_backtest.json`).

**12. "Your band covered 93.8% against 80%. Is it useless?"**
It is wider than needed, and the Method screen says so. Other window sizes gave 92.9% and 91.9%, so it is not one choice. We prefer wide to falsely tight; an early fixed-width band covered 65.9% (`docs/submission/qa-prep.md`, from `data/backtest.json` sensitivity).

**13. "Explain the Rising / Falling label."**
A Welch t-test compares the last 12 months of logit shares with the 12 before. p under 0.05 and 30+ mentions gives Rising or Falling. It describes the past; it pointed the right way next year 67.2% of the time (720 overlapping cases).

**14. "Explain the match score and the rank."**
Match = weight of the role's skills you have / total weight. Rank = 0.7 x match + 0.3 x outlook. Weights are the share of single-role posts that mention each skill, kept when lift is at least 1.1. Under 20% match, a role is not ranked.

**15. "How does the CV reading work and what stops it inventing skills?"**
The model returns skill + exact quote. Code keeps a skill only if the quote is in the CV word for word and the phrase is inside the quote. You review every skill and can remove it.

**16. "What personal data do you keep?"**
Skills, target role and ticks; cleaned CV text for the CV builder (emails/phones/IDs replaced); account details only if you sign in. Not the CV file. Accounts idle for 365 days are deleted. See the Privacy notice. (Note: older docs say we never store CV text; that is out of date.)

**17. "Is it fair? Does it use my name, age or gender?"**
No. The matcher reads skills only. `test_fairness.py` gives three CVs with the same skills and different name, age, gender, nationality and school and requires the same result. Limit: the HN data may carry bias.

**18. "What is the hardest technical risk and the fallback?"**
Forecast skill: 12-month demand is near flat, and 13 of 40 skills have too few posts (8 low volume, 5 rare). Fallback is built in: those skills show counts and a label, no forecast. For a live-demo failure we have a backup video and an offline snapshot.

**19. "What if a source goes down?"**
The app reads committed files, so a failed HN fetch cannot break it. The daily job never moves `latest.json` on failure. The page shows a dated offline snapshot if the server is unreachable.

**Why doesn't the Job forecast use arXiv, GitHub, Hugging Face or X?**
Those are news and talk sources, not job posts. GitHub Jobs closed in 2021. X needs a paid API, and scraping it breaks its terms. The forecast needs hiring data it can backtest: HN "Who is hiring?" gives 94 months. The Signals screen sits beside the forecast as an "AI boost" hint and a planner tie-break. It is never inside the forecast numbers. A future step is to test whether news rises lead hiring rises.

**20. "What is built and what is only planned?"**
Built: skills forecast, role forecast, replay and fetch, score breakdown, goal picker, HRD option (3 entries), privacy notice, fairness test, CV builder, Signals. Also built: the DOSM Malaysia check (sector level) and the Fairness block on the Method screen. Planned or waiting: KrackedDevs credits plan, Claude post labeller backfill (needs credits), Scheduled Deployment and App Storage set-up, impact counters, Bahasa Malaysia labels, Google two-way sync.

**21. "What is the stack, which model, and where is Replit?"**
Python 3.12, FastAPI, static HTML/JS, Replit Autoscale, Replit PostgreSQL and Auth, pandas/numpy/scipy/statsmodels. Claude Haiku for CV reading and optional steps. Forecast, match and pathway use no model.

**22. "Is the pathway time realistic?"**
Times are for the starter course only, and the app says job-level skill needs practice on real projects (`LEARNING_NOTE`). Minutes are our estimate, not the provider's.

**23. "HRD Corp: is it really claimable?"**
Three entries from Trainocate Malaysia, each with the provider page's own claim statement. The employer must apply through HRD Corp first. We show them as an optional line; the free resource stays first. A skill with no verified programme shows none.

**24. "Is the AI-exposure index reliable?"**
Only partly. The language category (14 skills) is robust across indices; 5 categories are contested, so 26 of 40 skills carry a "contested" mark. We left the stance values unchanged and show the disagreement on the Method screen (`data/exposure_agreement.json`).

**25. "How would you scale beyond tech?"**
The engine needs a dated job-post source, a skill list with patterns, and an exposure score per occupation. We have not tested another field; each field needs its own backtest first.

**26. "Who did what? Is this AI plagiarism?"**
Claude Code wrote much of the code from our prompts and plans, and we declared it as a major tool. The decisions are ours and recorded: keep naive3, label k an assumption, show disagreement, add the goal picker without lowering thresholds. Know the band, the Welch test and the rank formula without notes. Be ready to say when the Sheng Kuan code (`backend/signals/`) was written and merged.

**27. "Did you test with real users? What is the impact?"**
Not yet. We have no outcome numbers and we do not claim any. The plan is a pilot with the XMUM career centre, measuring the 3 Phase 1 KPIs. The SDG lines describe the plan, not an effect.

**28. "Why not just use a job site's data?"**
JobStreet blocks bots with a Cloudflare challenge, and bypassing it would break its terms. LinkedIn and X also break terms. HN is public and dated.

**29. "What happens when a new role appears?"**
The daily job counts job titles. A title no role covers is listed. With AI credits, Claude Haiku reviews it; a new role needs 3 quotes from 3 posts, checked by code, and it is added unranked. Not run yet because credits are not in.

**30. "Can you show the forecast is honest about the open month?"**
Job forecast shows posts so far this month. The nowcast weight comes from a backtest: with 1 day of data, k = 100; from day 14, no blending (`data/nowcast_backtest.json`).

---

## 8. Glossary

- **API.** A set of web addresses a program can call to ask for data or send data. Verity's API is the `/api/...` routes.
- **Endpoint / route.** One address in an API, for example `GET /api/pathway`.
- **HTTP methods.** GET reads. POST sends something to create or run. PUT replaces. DELETE removes.
- **Envelope.** The fixed shape of every answer: `success`, `data`, `error`, `meta`.
- **Status code.** 200 OK, 202 accepted (work started), 404 not found, 422 bad input, 429 too many requests.
- **Rate limit.** A cap on how often one client can call. Stops abuse and cost spikes.
- **FastAPI / uvicorn.** A Python web framework and the server that runs it.
- **Frontend / backend.** What the browser shows / the server code behind it.
- **Static files.** Files sent as they are (HTML, CSS, JS). No build step means no compile or bundle.
- **Cookie.** A small value the browser stores and sends back. **HttpOnly** means JavaScript cannot read it. **SameSite=Lax** limits cross-site sending. **Secure** means HTTPS only.
- **Token (browser token).** A random secret kept in your browser that proves "this is my profile". We store only its hash (SHA-256).
- **Hash / SHA-256.** A one-way fingerprint of a value. You cannot get the value back.
- **HMAC.** A signature made with a secret key. Proves a cookie was not changed.
- **OIDC / OpenID Connect, PKCE.** A standard way to sign in with another service (Replit). PKCE protects the code exchange.
- **Environment variable / Secret.** A setting kept outside the code (for example `ANTHROPIC_API_KEY`).
- **PostgreSQL / SQLite.** Two databases. PostgreSQL runs as a server. SQLite is a single file.
- **Scheduler / cron.** A job that runs on a timetable (daily at 06:30).
- **Autoscale / Reserved VM / Scheduled Deployment.** Replit hosting types: scale with traffic / one always-on machine / a job that runs on a timetable.
- **App Storage.** Replit's file bucket. We keep daily data snapshots there.
- **Snapshot.** A saved copy of the data at one time, with its fetch date.
- **LLM.** Large language model, such as Claude. Writes and reads text; can invent facts.
- **Prompt injection.** Text in a document that tries to give the model orders. We treat CV text as data.
- **Guardrail.** A code rule that checks or limits what a model returns.
- **Schema-constrained JSON.** The model must answer in a fixed data shape.
- **Taxonomy.** Our fixed list of 40 skills with match patterns.
- **Regex.** A text pattern. Finds skill names in posts.
- **Share (demand share).** Posts that mention a skill / all posts that month.
- **pp (percentage point).** A difference between two percentages. 12% to 14% is 2 pp.
- **Logit.** `ln(p/(1-p))`. Turns a 0 to 1 share into a scale where adding and averaging behave well.
- **Welch t-test.** A test of whether two groups have different averages, without assuming equal spread. We use it for the Rising / Falling label.
- **p-value.** How surprising the data would be if nothing had changed. Below 0.05 we call it a real change.
- **naive / naive3.** Forecast methods: repeat last month / repeat the mean of the last 3 months.
- **Drift / damped.** Trend-line forecasts. Both lost in the backtest.
- **Backtest.** Pretend it is a past date, forecast, then compare with what really happened. Repeat across many dates.
- **Rolling origin.** The "past date" moves forward month by month.
- **Held-out (test) data.** Months not used to choose the method.
- **MAE.** Mean absolute error: the average size of the miss, ignoring direction.
- **Conformal band.** A range sized from recent real forecast errors, not from a theory. Made to cover the stated share of outcomes.
- **Coverage.** The share of real values that landed inside the band. Target 80%; we got 93.8% (too wide).
- **Look-ahead / leakage.** Using future data by mistake. Our tests check it cannot happen.
- **Nowcast.** An estimate for a month that is not finished.
- **Single-role post.** A post that names exactly one of our roles. Used to learn clean role profiles.
- **Lift.** How much more often a role's posts mention a skill than all posts do. Lift 2 = twice as often.
- **Match score.** Weight of the role's skills you hold / total weight of its skills.
- **Rank score.** 0.7 x match + 0.3 x outlook.
- **Outlook.** 1.0 Rising, 0.5 No clear change, 0.0 Falling.
- **AI exposure (`e_s`).** How much of a job's tasks the AI did in Anthropic's data. Higher = more exposed.
- **Stance.** AI-complement (AI helps), neutral, or AI-substitutable (AI can do it).
- **k.** The strength of the "If AI speeds up" scenario. Set at 2 as an assumption.
- **Tier (solid / rough / not_ranked).** How many posts support a role profile.
- **MASCO.** Malaysia Standard Classification of Occupations. Each job type has a code. MyCOL and DOSM use it.
- **MyCOL.** Malaysia Critical Occupations List (TalentCorp). A shortage list, not a vacancy count.
- **DOSM.** Department of Statistics Malaysia. Source of the quarterly online-vacancy check (sector level, not per role).
- **HRD Corp.** Malaysian agency that funds employer training. "Claimable" means an employer can reclaim the fee, after applying first.
- **PDPA.** Personal Data Protection Act 2010 (Malaysia). Has 7 principles.
- **SDG / SDG target.** UN Sustainable Development Goal / one of its sub-goals (for example 4.4 skills for employment, 8.5 productive employment).
- **Sector.** A group of employers (health, climate, ...) used to link roles to SDGs.
- **Replay.** Showing real data cut at an earlier month. **asOf** is the query parameter.
- **Ledger (forecast ledger).** A saved log of each daily forecast, graded later.
- **Jev.** TypeSafe AI's decision model, optional for the Signals ranker.
- **Gold set.** A hand-labelled test set used to decide if a model may replace a formula.

---

## 9. Where docs and code disagree (code wins)

### Resolved in the working tree (checked 31 Oct 2026)
- **CV text storage.** `docs/submission/qa-prep.md` and `tech-declaration.md` now say the cleaned CV text is stored and deleted with the profile. (README not re-checked.)
- **Retention.** qa-prep now states 365 days (`RETENTION_DAYS`).
- **Test count.** qa-prep, tech-declaration and HANDOFF now say 1,332 collected (868 root + 464 backend). Collected, not a full pass run.
- **Single-role posts.** qa-prep now says 2,580.
- **Repo name.** README, `BRIEF.md`, HANDOFF, the proposal and the declaration all use `TayEeZhan/varity`.
- **Method-screen fairness line.** Built (`fairnessBlock`), with a Privacy link.
- **HRD Corp.** HANDOFF now says built with 3 entries. `checked_on` in `data/hrd_programmes.json` is 2026-10-31.
- **Replit AI Integrations.** The declaration no longer says it is unused: it says supported in code, used when enabled, Haiku 4.5 on Replit.
- **DOSM.** Built (4.14) and listed in the declaration (4.4).

- **Resolved 1 Nov 2026 (docs only, no code changed):**
  - **Architecture doc.** `docs/architecture.md` now says replay (`?asOf=`), `POST /api/data/refresh` and the daily role update (`_update_roles`) exist. Emerging-role discovery is built (`engine/role_discover.py`) and not run on real data. The Team page is noted as removed.
  - **Scenario names.** The pitch script, Q&A prep, demo checklist, video script and architecture doc now use "Expected (estimate)" and "If AI speeds up (estimate)". API values stay `moderate` and `fast`.
  - **Team page.** `tasks/plan-final-round.md` now says built, then removed on 1 Nov.
  - **Hosting.** Docs now say Autoscale (`.replit` `deploymentTarget = "cloudrun"`). The Scheduled Deployment is not set up yet.
  - **Plan docs.** `tasks/plan-final-round.md` WP-MY and `tasks/plan-credits.md` now describe the sector-level DOSM check. `plan-credits.md` also says the KrackedDevs side is built and not run.
  - **Signals footer.** `loadSignals()` in `frontend/app.js` replaces the "offline snapshot of 22 Oct" time and the run id with the live run when `/api/signals` answers with stories. The static text shows only when the API fails or has no ranked run, and it says so.

### Resolved 1 Nov 2026 (second pass)
- **Model naming.** One public rule, in the declaration (section 3): a direct Anthropic key gives Claude Haiku 5.5; Replit AI Integrations gives Claude Haiku 4.5. The deployed app uses the direct key.
- **Licences reviewed:** DOSM (Government Open Data Terms of Use 1.0; the app now shows "Data source: Department of Statistics Malaysia" as DOSM requires), arXiv (metadata CC0 1.0, 1 request per 3 s), HN (no data licence; Y Combinator's terms forbid scraping, and we use only the APIs), Hugging Face, Bluesky, AIOE (cite the 2021 paper).
- **Tech declaration `.docx`** regenerated from `tech-declaration.md`.

### Still open
1. **Licences still not reviewed:** TypeSafe (off by default), the 25 publisher RSS feeds, the Trainocate/HRD pages and MyCOL. The declaration says "not reviewed" for each.
2. **The Preliminary `.docx`** is the submitted preliminary round. It is kept as it was.
3. **`[TEAM TO FILL]` items** remain in the declaration (Replit plan, Replit Agent model, live CV-intake confirmation).

### What I did not check
- I did not run the full test suite, `tests/test_my_dosm.py`, or the app in a browser. Numbers come from files, and Aina's results from running the engine code on 31 Oct.
- I did not open the live Replit site, so I cannot confirm the deployment state, region or plan.
- Frontend text was read from source, not seen rendered.
