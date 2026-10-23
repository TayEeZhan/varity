# Verity

Verity reads a tech developer's CV, forecasts which skills are rising or falling from dated public data, and gives ranked future roles and a learning plan. Every claim shows its source and date, and the plan changes when the data changes. The app shows real forecasts built from public data.

**Live prototype:** https://verity--eezhan0805.replit.app

**Architecture:** [docs/architecture.md](docs/architecture.md) covers every feature, its status, and how future job roles are predicted.

## Repository layout

| Folder | What it is |
|---|---|
| `frontend/` | Varity web app (static HTML/CSS/JS, no build step) |
| `backend/signals/intake/` | Skill profile intake: reads a CV and keeps the skill profile behind the CV page (`/api/cv/extract`, `/api/profile`) |
| `backend/signals/` | AI trend signal system: collects, ranks and serves the Signals page data (`GET /api/signals`) |
| `app.py`, `engine/`, `data/` | Current Streamlit prototype (skill forecast); moves into `backend/` later |

## Run the Varity web app

```
cd backend/signals
pip install -r requirements.txt
python -m trendsignal serve --scheduler --port 8000
```

Open http://localhost:8000. The backend serves `frontend/` at `/`, re-ranks every 15 minutes, and the Signals page loads live data from `/api/signals`. The old ranker feed is at `/feed`. Opened without the backend, the page shows the bundled snapshot in `frontend/data.js`.

## Run the Streamlit prototype locally

```
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Replit

1. Import this GitHub repo into Replit.
2. Press Run. The app starts on port 8080 (see `.replit`).
3. Press Deploy. Use the Deployment URL, not the dev URL.

## Data and AI disclosure

Current data sources:

- Hacker News "Who is hiring?" threads, read through the Algolia HN API. Used for skill demand.
- Anthropic Economic Index (release 2026-06-26), data licensed CC BY. Used for the AI exposure index.
- O*NET 31.0 Database, Task Statements, licensed CC BY 4.0. Used to map skills to tasks.

Full sources and licences: data/SOURCES.md

This product includes information from O*NET OnLine by the U.S. Department of Labor, Employment and Training Administration (USDOL/ETA). Used under the CC BY 4.0 license.

AI tools used in development: Claude Code (Anthropic).

## Code tour

The repo has guided tours for the VS Code CodeTour extension, in the `.tours/` folder.

1. Install the **CodeTour** extension (publisher vsls-contrib) from the VS Code Marketplace.
2. Open this folder in VS Code.
3. Click **CodeTour** in the Explorer panel.
4. Pick a tour: `01-data-to-forecast`, `02-roles-to-pathway` or `03-live-data`.
