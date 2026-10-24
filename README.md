> [!IMPORTANT]
> ## 📁 Submission Documents
> **All required submission documents are in [`submission/`](submission/).**

---

# Varity

> Varity reads a tech developer's CV, forecasts which skills are rising or falling from dated public data, and gives ranked future roles and a learning plan, for junior and mid-level developers and career switchers in Malaysia.

---

## Team Information

| Field                  | Details |
| ---------------------- | ------- |
| **Team Name**          | Hokkien Mee Is Purple |
| **Team Domain**        | Domain 1 |
| **SDG Track (1–17)**   | SDG 4 — Quality Education (target 4.4); supporting SDG 8 |
| **Team Leader**        | Tay Ee Zhan |
| **University**         | Universiti Malaya |
| **Number of Members**  | 2 |

## Links

| Resource          | Link |
| ----------------- | ---- |
| GitHub Repository | https://github.com/TayEeZhan/varity |
| Live Demo         | https://verity--eezhan0805.replit.app |
| RunPod Endpoint   | Not used (no GPU workload) |
| Slide Deck        | Coming soon |
| Demo Video        | Coming soon |

---

## Overview

### Problem

In Malaysia, 56% of professionals already use AI tools at work, yet only 26% have received formal training (Hays Asia Salary Guide 2025), and MOSTI says more than 600,000 workers must reskill within three to five years. Developers cannot tell which skills to deepen, which to drop and what to learn next: skill lists carry no date or source, hype hides the signal, and free resources are scattered.

### Solution

Varity forecasts each skill's share of job posts from 48,508 Hacker News hiring posts (2019–2026), with a backtested range and a Rising / Falling label. Claude Haiku 5.5 reads the CV, and code checks every skill quote word for word. Varity then ranks roles and builds a dated learning plan with free, link-checked resources. Every number shows its source and date.

### Key Features

- **CV & routes** — Upload a CV (or try an example) and get ranked target roles with a match score and skill gap.
- **Pathway & Today** — An ordered learning plan with free resources, exportable to `.md`, `.ics` or Google Tasks.
- **Job forecast & Skills radar** — 12-month skill-demand forecasts with tested uncertainty bands.
- **Signals** — AI and dev-tooling news, ranked from dated sources.

### Tech Stack

| Layer         | Technology |
| ------------- | ---------- |
| Frontend      | HTML, CSS, JavaScript (no build step) |
| Backend       | Python 3.12, FastAPI, uvicorn |
| Database      | Replit PostgreSQL (SQLite fallback) |
| AI / Compute  | Claude Haiku 5.5 (Anthropic API); pandas and SciPy statistics on CPU |
| Hosting / Dev | Replit |

---

## Project Structure

```
.
├── backend/signals/         # FastAPI server: web app, APIs, CV intake, role advisor, signal ranker
├── data/                    # Committed aggregate data files + SOURCES.md
├── docs/                    # Architecture, submission drafts
├── engine/                  # Demand, forecast, backtest, exposure, role match, pathway
├── frontend/                # Varity web app (static HTML/CSS/JS)
├── submission/              # Required submission documents
│   ├── SDC2026_HokkienMeeIsPurple_Preliminary.pdf      # Preliminary submission
│   ├── SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf  # Technology declaration
│   └── SDC2026_HokkienMeeIsPurple_Replit_POU.pdf       # Replit proof of use
├── tests/                   # Engine tests (backend tests in backend/signals/tests/)
├── .env.example             # Example environment variables
├── .gitignore
├── .replit                  # Replit run configuration
├── LICENSE
├── requirements.txt         # Python dependencies
└── README.md
```

### Architecture

```
User ──► Replit (FastAPI + web app) ──► Anthropic API (Claude Haiku 5.5, CV intake)
                │
                ├──► Engine + committed data (forecasts, roles, pathway)
                ├──► Replit PostgreSQL / Replit Auth (optional accounts)
                └──► Response returned to user
```

More detail: [docs/architecture.md](docs/architecture.md).

---

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `.env.example` (all optional; without `ANTHROPIC_API_KEY` a keyword pass replaces the LLM).
3. Click **Run**. Replit uses the `.replit` file to start `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`.

### Option 2 — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/TayEeZhan/varity.git
cd varity

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env            # then fill in your values (optional)

# 5. Run the app
cd backend/signals
python -m trendsignal serve --port 8000
```

Open http://localhost:8000.

### Run Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## How We Use Replit *(Required)*

- **Hosting:** The app is deployed with Replit Deployments (Autoscale, 2 vCPU / 4 GiB, region Asia) at the Live Demo link above.
- **Database & Auth:** Replit PostgreSQL stores accounts and saved profiles; optional sign-in uses Replit Auth.
- **Secrets:** API keys are stored in Replit Secrets, never in the code.
- **Credits:** SDC-provided Replit credits.

📄 Proof of use: [`submission/SDC2026_HokkienMeeIsPurple_Replit_POU.pdf`](submission/SDC2026_HokkienMeeIsPurple_Replit_POU.pdf)

## How We Use RunPod *(Required)*

Not used. Varity has no GPU workload: forecasts are CPU statistics and the CV intake calls the Anthropic API. The organisers confirmed that RunPod proof is not needed without GPU use.

---

## Challenges & Learnings

- **Simple beat clever.** A rolling-origin backtest showed that "mean of the last 3 months" beat trend models and gradient boosting at 12 months, so we shipped the simple model with a tested band.
- **Data access.** LinkedIn and X break terms; JobStreet blocks bots. We used public Hacker News hiring threads and say plainly that they are US-heavy.
- **Trusting an LLM.** The model only points at skills; code verifies every quote and sets every number.

## Future Improvements

- [ ] Malaysian job-post sources
- [ ] Daily automatic data refresh on a Replit Scheduled Deployment
- [ ] User testing with Malaysian students and developers

## Team

| Name           | Role                   | GitHub |
| -------------- | ---------------------- | ------ |
| Tay Ee Zhan    | Team Lead / Full stack | [@TayEeZhan](https://github.com/TayEeZhan) |
| Goh Sheng Kuan | Data / Backend         | [@shengkuan06](https://github.com/shengkuan06) |

---

## More Details

### Screens

Varity is the only app. It has eight screens:

- **Flow map**: the planned user flow as a transit map. It says that Google sign-in and two-way Google Tasks sync are not built. Replit sign-in is built (see Optional sign-in).
- **CV & routes**: upload a CV, or press "Try an example" (3 synthetic profiles). Shows ranked routes to roles.
- **Today**: your next stops, taken from your pathway.
- **Pathway**: the ordered stops from your skills to your route. You can download it as `.md` or `.ics`.
- **Signals**: AI and dev-tooling signals, ranked from dated sources.
- **Job forecast**: 12-month outlook for tech roles, from Hacker News hiring posts.
- **Skills radar**: skill demand and change, with a forecast per skill.
- **Method**: backtests, AI exposure cross-check, and data sources.

### Optional sign-in

Press "Sign in" to use Replit Auth (OpenID Connect). It is optional: the whole app works without it. A signed-in user keeps the skill ledger, target role and pathway ticks in an account. We store the Replit user id, email, display name and profile image URL, never the raw CV text or tokens. `DELETE /api/me` deletes the account and the profile. Google sign-in is not built. Not yet tested on the live Replit app.

Environment variables:

- `SESSION_SECRET`: signs the 30-day session cookie. Sign-in is on only when this and `REPL_ID` (set by Replit) exist.
- `GOOGLE_CLIENT_ID`: a Google OAuth web client id (Google Cloud console, Tasks API enabled, your site's origin under Authorized JavaScript origins). With it, Today shows "Send today to Google Tasks": the browser gets a Tasks-only token from Google and writes a dated list itself, so the server never sees the token or the tasks. Without it, the button is hidden.
- `DATABASE_URL`: Replit PostgreSQL for accounts and profiles. With no value, the server uses SQLite.

### Data and AI disclosure

Current data sources:

- Hacker News "Who is hiring?" threads, read through the Algolia HN API. Used for skill demand.
- Anthropic Economic Index (release 2026-06-26), data licensed CC BY. Used for the AI exposure index.
- O*NET 31.0 Database, Task Statements, licensed CC BY 4.0. Used to map skills to tasks.

Full sources and licences: data/SOURCES.md

This product includes information from O*NET OnLine by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the CC BY 4.0 license.

AI models in the running app:

- CV intake: Claude Haiku 5.5 (`claude-haiku-5-5`) through the Anthropic API. The key (`ANTHROPIC_API_KEY`) is a team member's, set in Replit Secrets and Production app secrets, and Anthropic bills that account. With no key, a keyword pass takes over. The model only points at skill mentions. Code checks every quote word for word. A daily cap of $1 applies (`VERITY_INTAKE_DAILY_BUDGET_USD`). The CV-intake call is not yet confirmed on the live app (the route advisor is). Use synthetic CVs only: CV text goes to Anthropic directly.
- The skill forecast, role match, pathway steps, dates and SDG parts are code. Only the CV intake and two optional steps use an LLM. The optional route advisor re-orders roles by at most 2 places, picks reason chips that code wrote and writes one checked summary line; the fit label always comes from code. The optional pathway coach re-orders steps within a stage, picks among listed resources and writes one checked "why" line. All of it runs within code's limits and falls back to code.
- "Try an example" needs no LLM.
- The signal ranker (`backend/signals/`) can use Claude and Jev (TypeSafe AI), but both are off by default.

AI tools used in development: Claude Code (Anthropic), Replit Agent (setup only).

### Code tour

The repo has guided tours for the VS Code CodeTour extension, in the `.tours/` folder.

1. Install the **CodeTour** extension (publisher vsls-contrib) from the VS Code Marketplace.
2. Open this folder in VS Code.
3. Click **CodeTour** in the Explorer panel.
4. Pick a tour: `01-data-to-forecast`, `02-roles-to-pathway` or `03-live-data`.

---

## Submission Checklist

- [x] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [x] Replit used, with proof of use in `submission/`
- [x] RunPod: not used (no GPU workload)
- [x] Preliminary submission completed (`SDC2026_HokkienMeeIsPurple_Preliminary.pdf`)
- [x] Technology declaration completed (`SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf`)
- [x] Submission files renamed with your team name
- [x] "How to Run" steps verified
- [x] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
