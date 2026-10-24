# Verity

Verity reads a tech developer's CV, forecasts which skills are rising or falling from dated public data, and gives ranked future roles and a learning plan. Every claim shows its source and date, and the plan changes when the data changes. The app shows real forecasts built from public data.

**Live prototype:** https://verity--eezhan0805.replit.app (live, published 24 Oct 2026)

**Architecture:** [docs/architecture.md](docs/architecture.md) covers every feature, its status, and how future job roles are predicted.

## Repository layout

| Folder | What it is |
|---|---|
| `frontend/` | Varity web app (static HTML/CSS/JS, no build step) |
| `backend/signals/` | The only server: FastAPI app (`python -m trendsignal serve`) that serves `frontend/` at `/` and the JSON APIs. It also holds the AI trend ranker (`trendsignal/`), the CV intake (`intake/`) and the role advisor (`advisor/`) |
| `engine/` | Plain Python: demand, forecast, backtest, exposure, role match, pathway, radar. Imported by the backend. Not a server |
| `data/` | Committed CSV and JSON files that the engine writes and the backend reads, plus `SOURCES.md` |
| `docs/` | Architecture, build plan, data contract, submission documents |
| `tests/` | Tests for `engine/` (backend tests are in `backend/signals/tests/`) |

## Screens

Varity is the only app. It has eight screens:

- **Flow map**: the planned user flow as a transit map. It says that Google sign-in and two-way Google Tasks sync are not built. Replit sign-in is built (see Optional sign-in).
- **CV & routes**: upload a CV, or press "Try an example" (3 synthetic profiles). Shows ranked routes to roles.
- **Today**: your next stops, taken from your pathway.
- **Pathway**: the ordered stops from your skills to your route. You can download it as `.md` or `.ics`.
- **Signals**: AI and dev-tooling signals, ranked from dated sources.
- **Job forecast**: 12-month outlook for tech roles, from Hacker News hiring posts.
- **Skills radar**: skill demand and change, with a forecast per skill.
- **Method**: backtests, AI exposure cross-check, and data sources.

## Optional sign-in

Press "Sign in" to use Replit Auth (OpenID Connect). It is optional: the whole app works without it. A signed-in user keeps the skill ledger, target role and pathway ticks in an account. We store the Replit user id, email, display name and profile image URL, never the raw CV text or tokens. `DELETE /api/me` deletes the account and the profile. Google sign-in is not built. Not yet tested on the live Replit app.

Environment variables:

- `SESSION_SECRET`: signs the 30-day session cookie. Sign-in is on only when this and `REPL_ID` (set by Replit) exist.
- `GOOGLE_CLIENT_ID`: a Google OAuth web client id (Google Cloud console, Tasks API enabled, your site's origin under Authorized JavaScript origins). With it, Today shows "Send today to Google Tasks": the browser gets a Tasks-only token from Google and writes a dated list itself, so the server never sees the token or the tasks. Without it, the button is hidden.
- `DATABASE_URL`: Replit PostgreSQL for accounts and profiles. With no value, the server uses SQLite.

## Run Varity locally

```
pip install -r requirements.txt
cd backend/signals
python -m trendsignal serve --port 8000
```

Open http://localhost:8000. The backend serves `frontend/` at `/`. Add `--scheduler` to re-rank the Signals every 15 minutes; only with `--scheduler` does the first start also fill an empty database (without it the Signals page may be empty until you run `python -m trendsignal run`). Opened without the backend, the page shows dated offline snapshots and says so.

## Deploy on Replit

1. Import this GitHub repo into Replit.
2. Press Run. The app starts on port 8080 (see `.replit`; the command is `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`).
3. Press Deploy. Use the Deployment URL, not the dev URL.

## Data and AI disclosure

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

AI tools used in development: Claude Code (Anthropic).

## Code tour

The repo has guided tours for the VS Code CodeTour extension, in the `.tours/` folder.

1. Install the **CodeTour** extension (publisher vsls-contrib) from the VS Code Marketplace.
2. Open this folder in VS Code.
3. Click **CodeTour** in the Explorer panel.
4. Pick a tour: `01-data-to-forecast`, `02-roles-to-pathway` or `03-live-data`.
