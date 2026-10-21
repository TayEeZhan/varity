# Verity

Verity reads a tech developer's CV, forecasts which skills are rising or falling from dated public data, and gives ranked future roles and a learning plan. Every claim shows its source and date, and the plan changes when the data changes. The app currently shows sample data from `data/fixtures/`, not real forecasts.

**Live prototype:** https://verity--eezhan0805.replit.app

## Run locally

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
