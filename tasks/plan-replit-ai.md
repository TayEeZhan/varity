# Plan: Replit AI Integrations for the LLM + handoff follow-ups (24 Oct 2026)

Status: DRAFT. Edit freely, then say "go". Nothing is built yet.
Branch: `feat/replit-ai-llm` → PR → merge only on your go.

## What I found (after pulling main, now at c9c9bf9 = PR #16)
- PR #16 (SK) moved the AI trend signal layer to `backend/signals/`, added the Varity frontend (`frontend/`, served by FastAPI at `/`) and the CV intake API (`POST /api/cv/extract`). So HANDOFF items 2 and 3 are partly done.
- Two LLM call sites, both Anthropic SDK, both off today because no key is set:
  1. **CV intake** `backend/signals/intake/llm_extract.py` (Claude Haiku 5.5). Gated on `ANTHROPIC_API_KEY` at `llm_extract.py:126` and `trendsignal/web/cv_api.py:140`. Without a key it falls back to the keyword pass.
  2. **Signal enrich / brief** `backend/signals/trendsignal/llm.py` (Haiku fallback, Sonnet brief, both off by default). Gated by `Settings.has_llm_credentials` (`trendsignal/config.py:96`).
- Jev already uses Replit AI Integrations (OpenRouter env vars, `config.py:118`). The same pattern can serve Anthropic.
- `.replit` still runs only the Streamlit `app.py`. The Varity FastAPI app (with CV upload) is **not deployed** anywhere.

## How Replit AI Integrations works here
Replit provisions two env vars in the Repl: `AI_INTEGRATIONS_ANTHROPIC_API_KEY` and `AI_INTEGRATIONS_ANTHROPIC_BASE_URL`. Usage is billed to Replit credits (no Anthropic account). The `anthropic` SDK already reads `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` from the environment.
Bonus: it is extra proof of Replit use (compulsory tool).

## Changes

### A. Code (small)
| File | Change |
|---|---|
| `backend/signals/trendsignal/config.py` | In the startup env step: if `ANTHROPIC_API_KEY` is unset and the Replit pair is set, copy them to `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` (`setdefault`, so a real key still wins). ~5 lines. Every existing gate and client then works unchanged |
| `backend/signals/intake/llm_extract.py` | Same mapping for the CLI path (`python -m intake.llm_extract`); `MODEL_LABEL` says "via Replit AI Integrations" when that route is used |
| `backend/signals/.env.example` | Document the Replit route next to `ANTHROPIC_API_KEY` |
| `backend/signals/tests/` | 1 test: Replit vars → mapped; real key → not overwritten; none → still no credentials |

No new dependency. Budget gates (`$1/day` intake, `$2/day` signals) stay as they are.

### B. Replit setup (you or SK, in the Replit UI, ~10 min)
1. In the Repl, enable AI Integrations → Anthropic (Agent or Integrations pane). Check the two env vars appear.
2. Check which Claude models Replit lists. If `claude-haiku-5-5` is not listed, set `VERITY_INTAKE_MODEL` / `TRENDSIGNAL_ENRICH_MODEL` to the listed Haiku id.
3. Pull, `pip install -r backend/signals/requirements.txt`, restart, republish.

### C. Deployment decision (NEEDS YOUR CALL)
The CV upload only lives in the Varity FastAPI app, which Replit does not run. Pick one:
- **C1 (my pick):** switch `.replit` run + deployment to `cd backend/signals && python -m trendsignal serve --port 8080`. Varity becomes the live prototype; Streamlit stays in the repo but is no longer the live link. Check first that Varity covers the forecast / roles / pathway screens judges need.
- **C2:** keep Streamlit live and call `intake.pipeline` from `cv_intake_slot()` in `app.py` (more code, two UIs to explain).
- **C3:** run both (Streamlit on 8080, FastAPI on a second port). Replit autoscale deploys expose one port, so this is fragile. Not recommended.

### D. Docs that must change (an LLM is now in use)
- `docs/submission/tech-declaration.md`: AI models = Claude Haiku 5.5 via Replit AI Integrations (Anthropic); what it does (points at skills in a CV; code verifies every quote); privacy (synthetic CVs only, CV text sent to Anthropic via Replit); cloud = Replit.
- `docs/submission/preliminary-proposal.md`, `pitch-script.md`, `qa-prep.md`, `demo-checklist.md`, `deck-outline.md`: replace every "no LLM" line (checklist in `docs/submission/README.md`).
- `docs/architecture.md`, `README.md`, `app.py` "no LLM" UI copy (5 hits; only if C2 or still shown).
- `HANDOFF.md`: mark items 2 and 3 as merged via PR #16; add the Replit AI step; record the deploy decision.

### E. Verify
- `pytest -q` in `backend/signals/` and root (root takes ~8 min).
- On Replit: upload `intake/samples/aina.txt`; the review screen shows "Claude Haiku 5.5", quotes verified, cost under 1 cent. Screenshot for the video.
- Opus review of the diff before calling it done.

## Not in this plan (still open from HANDOFF)
- Submission PDFs and [TEAM TO FILL] fields, video recording, AIOE licence, cloud_devops stance, Gmail history rewrite, old worktree cleanup.
- `HANDOFF.md` and `BRIEF.md` are untracked in the repo root. I will not commit them unless you say so.

## Risks
- Replit's Anthropic model list may lag; fallback is the listed Haiku id or keyword pass (already built).
- Deadline: our target is tonight 21:00. A and D take ~1–2 h; C1 needs a Replit republish and a check of the Varity screens.
