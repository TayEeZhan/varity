# Plan: remove Streamlit, ship the newest Varity (24 Oct 2026)

Status: DRAFT. Edit freely, then say "go". Nothing is built yet.
Branch: `feat/varity-only`, cut after the merges in step 1. PR → merge only on your go.

## Where things stand
- **Newest Varity = SK's PR #19** (`feat/role-suggestions-pathway`, stacked on PR #18 `feat/job-forecast-api`, pushed 04:13 today). It adds `/api/role-suggestions`, `/api/pathway` and `/api/target-role`, built on the real `engine/roles.py::match_roles` and `engine/pathway.py`. The job forecast page reads `data/role_forecast.json`. An optional LLM only picks "reason chips" that code writes.
- After #19, `frontend/data.js` still holds SYNTHETIC `PROFILE`, `ROUTES`, `PATHWAY`, `TODAY` and `TARGET` ("62% match") as an offline fallback. If the backend fails or no profile is saved, judges could see invented numbers. That is the DQ risk to close.
- `backend/signals` reads the root `engine/` and `data/`. Those stay. Only the Streamlit UI goes.
- #19 and my #20 both edit `trendsignal/config.py` and `cv_api.py`. #19's `advisor/llm.py` checks only `ANTHROPIC_API_KEY`, so it needs the Replit route too.

## Steps

### 1. Merge in order (needs your go on SK's PRs)
1. Opus review of #18 and #19 (I review; a subagent fixes any findings on SK's branches, or I list them for SK).
2. Merge #18 → #19 → #20 into main. Resolve the `config.py` / `cv_api.py` conflicts. Point `advisor/llm.py` at the same Replit route (model `claude-haiku-4-5` on Replit).

### 2. Close the gaps Streamlit covered (subagent A, frontend + backend API)
| Must-have / feature | Today in Varity (after #19) | Change |
|---|---|---|
| No invented numbers | Synthetic fallback in `data.js` | Delete the synthetic `ROUTES`/`PATHWAY`/`TODAY`/`TARGET`/`PROFILE`. With no data, show an empty state ("Upload a CV or pick an example profile"). Keep the 3 synthetic example personas, but labelled "synthetic example" |
| Example profiles (no CV needed) | Missing | "Try an example" button: posts one of the existing synthetic personas from `app.py` as a profile, so the demo works without the LLM |
| SDG tags | Static `SDG 4.4` label | Read `data/role_sdg.json` / `data/skill_sdg.json` via `engine/sdg.py` and serve them in the role and pathway payloads |
| ≥2 scenarios as estimates | #18 wires the role forecast | Check that moderate and fast both come from the engine, labelled "estimate" |
| Method / evidence page | Missing | One static page: backtest numbers from `data/backtest.json` and `data/role_backtest.json`, sources from `data/SOURCES.md`, caveats. It reads the files and types no numbers |
| MyCOL badges, .md/.ics export, skills radar, AI-exposure view | Missing | **Skip** for the preliminary (not must-haves). Listed as a known gap in the docs. Tell me if you want any of them |

### 3. Remove Streamlit (subagent B)
- Delete `app.py`, `.streamlit/`, `tests/test_app.py`. Remove the Streamlit-only tests in `tests/test_store.py`, `test_role_forecast.py`, `test_discover.py` and `test_exposure_indices.py`; keep their engine tests.
- `engine/live.py`, `engine/exposure_indices.py`: drop the Streamlit imports and caching (keep the logic the backend or the scheduled job uses).
- `requirements.txt`: remove `streamlit` (and Pillow if only Streamlit needs it). One install line covers root + `backend/signals/requirements.txt`.
- `.replit` run and deployment: `cd backend/signals && python -m trendsignal serve --host 0.0.0.0 --port 8080 --scheduler`, with a build that installs both requirement files.
- Signals DB: a fresh deploy has 0 stories. Run one pipeline pass at startup when the DB is empty, so the Signals page has dated live data.
- The HN refresh: the Streamlit Refresh button goes. The scheduled job (`docs/replit-schedule.md`) stays the only refresh path.
- `.tours/02` and `03`: repoint the steps from `app.py` to the backend files.

### 4. Docs (subagent C)
`README.md` (run instructions, live link unchanged), `docs/architecture.md`, `docs/submission/*` (the demo flow is now Varity screens; tech stack: FastAPI + static JS on Replit, no Streamlit; pitch script and demo checklist screen names), `HANDOFF.md`, CodeTour text.

### 5. Verify
- `pytest` in root and `backend/signals`. (Root modules that use statsmodels are blocked on this PC by Windows Application Control. Allow the DLL, or run them on Replit.)
- Local run of the full journey in the browser (example profile → routes → pathway → forecast → signals → method), with screenshots. A grep shows no typed match or forecast number left in `frontend/`.
- Opus review of the whole diff.
- Replit (you): pull, install, enable AI Integrations → Anthropic, republish, click through once.

## Risks
- Time: our target is tonight 21:00. Steps 1–3 are the core (~4–6 h with subagents). If short, ship step 2 without the method page.
- SK's PRs: changing his branches needs his OK, or we merge as is and fix on ours.
- Removing Streamlit removes features judges could have seen (radar, MyCOL, export). The docs must stop claiming them.
