# Handoff: SDC Hackathon 2026 / Verity (updated Thu 29 Oct 2026)

Read this first in any new chat. Then read `C:\Users\eezha\sdc-hackathon\BRIEF.md` (rules, rubric, deadlines) and `C:\Users\eezha\verity\docs\architecture.md` (every feature, with its status).
The "Update 29 Oct" section is the newest. The sections after it are the 24 Oct state, kept for history.

## Update 30 Oct 2026 (newest; supersedes the AI-labeller notes in 29 Oct)

**Git state:**
- Phase 1 is on main (8a867c8).
- Everything below and in the 29 Oct "Built" list (Phases 2–7, nowcast, ledger, labeller, new roles, docs) is **uncommitted**. Commit only when the user says so.

### How the job forecast works now (plain version)
1. **Daily job** (Replit Scheduled Deployment, `python -m engine.scheduled`): starts from the last saved snapshot and downloads this month's HN "Who is hiring?" thread.
2. **New titles** (`engine/role_discover.daily`):
   - Counts job titles per month into `title_counts_monthly.csv` (history since 2019 is committed).
   - Lists titles no role covers: ≥30 posts in 12 months, or ≥15 in 3 months after <5 before.
   - With AI credits, Claude Haiku reviews each title: new_role, existing or noise.
   - A new_role needs 3 different quotes from 3 different posts, and code checks each quote.
   - Accepted roles are added to `roles.json` automatically (`ranked: false`, `auto_added`), with history from the title counts.
   - Decisions are kept in `role_reviews.json`. No person reviews anything.
3. **Labelling posts** (`engine/llm_labels.py`): **Claude first, title regex as backup.**
   - Claude must quote the words that show each role, and code drops any label whose quote isn't in the post.
   - Posts Claude didn't label get regex labels for the day. They aren't cached, so they're retried tomorrow.
   - A drift check compares today's Claude-vs-regex disagreement with the backfill baseline. Above baseline + 10 points, the month uses the regex that day.
   - Claude is used only after the one-off backfill has labelled all history (`role_labeller.json` says `llm`). Until then, everything is regex.
4. Code counts shares, then trend (Welch, 12 vs 12 months), forecast (naive3 + conformal band), the open-month nowcast, the ledger and the role scenario. **No LLM produces a number.**
5. The snapshot is saved to Replit App Storage. Its `OPTIONAL_FILES` now include `roles.json`, the title counts, reviews, candidates and the labeller config. The website reads it within 10 minutes.

### Decisions on 30 Oct
- **Malaysian job boards: dropped.** HN only. `engine/my_jobs.py` stays in the repo, unused.
- **No human review or gold set.** The user wants it all automatic. Accuracy is limited by quote checks plus the drift check. It isn't measured against human labels; say so if judges ask.
- **The relabel runs on Replit AI credits (about $20–40, an estimate), not the Pro plan.**

### Waiting on the user: Replit AI credits (organisers haven't added them yet)
Once the credits are in, in the Replit workspace:
1. Tools → Integrations → **Anthropic** → enable. Check that Secrets has `AI_INTEGRATIONS_ANTHROPIC_API_KEY` and `AI_INTEGRATIONS_ANTHROPIC_BASE_URL`.
2. Shell: `python -m engine.backfill_hn`. This downloads all 94 raw threads (about 80 MB) into `data/raw/hn`.
3. Shell: `python -m engine.llm_labels backfill`. It prints the post count and the estimated $. Then run `python -m engine.llm_labels backfill --yes`.
4. Commit the new `data/llm_role_labels.csv`, `data/role_labeller.json` and the rebuilt role files from the Replit Git pane, then republish.
5. The daily job then labels new posts with Claude and reviews new titles automatically.

Still needed for the daily job at all: App Storage bucket and Scheduled Deployment (`docs/replit-schedule.md`).

## Update 29 Oct 2026 (after the preliminary deadline)

**Rule: do not commit or push anything to GitHub** (the user's instruction; the submission deadline is done). All the work below is uncommitted in the working tree.

### Built this week (uncommitted, tests pass)
- **Phase 1 of `tasks/plan-dynamic-forecast.md`: the role forecast refreshes daily.**
  - `engine/refresh.py` `_update_roles` rebuilds the current month's role demand, then trends, backtest and forecast. On failure it restores the old role files (`roles_error`).
  - `engine/store.py` adds the role files to the snapshot. `engine/scheduled.py` reports `roles_updated`.
  - `backend/signals/advisor/service.py` `current_data_dir()` reads the newest store snapshot (checked every 10 min).
  - `/api/roles/forecast` returns `meta.source` = "daily refresh" or "committed". The frontend shows "updated YYYY-MM-DD · N posts so far this month".
  - The scheduler job `forecast_refresh` runs daily at 06:30.
  - Tests: `tests/test_refresh.py` (2 new), `backend/signals/tests/test_ops.py`.
- **Changed files for Phase 1:**
  - `engine/refresh.py`, `engine/store.py`, `engine/scheduled.py`;
  - `backend/signals/advisor/service.py`, `backend/signals/trendsignal/web/app.py`, `backend/signals/trendsignal/scheduler.py`;
  - `frontend/app.js`, `frontend/screens-explore.js`;
  - tests: `tests/test_refresh.py`, `backend/signals/tests/test_ops.py`.

  Replit needs these files; it pulls from GitHub. The steps are in `docs/replit-schedule.md`.
- **Not done for deploy:**
  - attach Replit App Storage;
  - add a Replit Scheduled Deployment running `python -m engine.scheduled`. On Autoscale the 06:30 in-process cron only runs if an instance is alive.
- **Docs:**
  - `tasks/plan-dynamic-forecast.md`: the full plan, Phases 1–7.
  - `docs/diagrams/dynamic-forecast.html`: architecture, code changes and risks.

### Built 29 Oct: Phases 2–7 and the AI labeller (uncommitted until the user says)
- **Phase 2, nowcast:**
  - `engine/forecast.nowcast_y` blends the open month toward last month: `(m + k*s_prev)/(n + k)`.
  - k is chosen per day open by `engine/nowcast_backtest.py`, on past threads cut at day 1/3/7/14 (choose before 2024-07, test after). Result in `data/nowcast_backtest.json`: k = 100 / 50 / 10 / 0 for roles.
  - Held-out error for roles: day 1 0.77 → 0.65 pp, day 3 0.53 → 0.46 pp. From day 14 there is no blending: a 2-week-old thread is nearly complete.
  - Used by both `scores.py` and `role_forecast.py`.
- **Phase 3, ledger:**
  - `engine/ledger.py` writes `forecast_ledger.csv` on each daily run. Rows are graded when the target month (as_of + 12) is complete.
  - `role_forecast.json` gets `track_record` (runs, graded, in band, change since the last run).
  - `engine/scheduled.py` now starts from the last store snapshot, so months and the ledger survive a fresh container.
- **AI labeller:**
  - `engine/llm_labels.py` uses Claude via Replit AI Integrations to say which roles a post hires for.
  - It's off until it wins. Steps: `sample` → a person fills `gold_roles` → `eval` sets `role_labeller.json` to `llm` only if Claude's micro F1 beats the regex on ≥100 posts → `backfill --yes` relabels all history.
  - After that, the daily job labels only new posts (cached by post id) and keeps the old files if Claude is unreachable.
  - **Not run yet:** no AI credits.
- **Phase 4:** each role gets `ai_exposure_e_r` and `forecast_fast` (same rule as skills, k = 2). I didn't replace `future_score` with the forecast change: naive3 is flat, so it would erase the trend signal from the ranking.
- **Phase 6:**
  - The `declining` flag means: Falling AND more than 50% of the skill weight in Falling skills. No role meets it today.
  - `engine/role_discover.py` writes `data/role_candidates.json` with 8 titles for human review. Examples: forward deployed engineer 21 → 83 posts/yr, research engineer 19 → 38.
- **Phase 7:** `planner.outlook_change` compares the target role's ledger row on the day the plan was accepted with today's. The pathway reply has `outlookChange`, and the plan screen shows "Outlook changed".
- **Phase 5: not built.**
  - The Malaysian collectors need written permission from Hiredly / Jobstore.
  - A second source and news momentum need months of history before a backtest can judge them.
- Frontend: the forecast screen shows the declining tag, the Fast scenario, the change since the last run, the month-in-progress weight, the track record and who labels the posts.

### Decisions
- **MiroFish: dropped.** It can't be backtested, it produces LLM opinions rather than data, it has an AGPL licence and it costs about $5 per run.
- **Google Tasks: drop as the main action.** OAuth Testing mode only allows listed test users, and judges are unknown. Make the existing `.ics` export (and "Add to Google Calendar" links) the main button. Tasks code is still in `frontend/app.js` (`pushToGoogleTasks`), unchanged.
- **The forecast stays statistical:** naive3, a conformal band and the Welch label. ML (gradient boosting, `engine/ml_forecast.py`) lost the backtest (`data/ml_backtest.json`: "keep naive3"). Every challenger must beat naive3 on held-out months.
- **LLMs never produce forecast numbers, parameters or rankings.** They are used for post labelling, CV reading and writing, and explanations, always checked by code.
- **All AI runs on the Replit $100 credits** via AI Integrations. The code already maps `AI_INTEGRATIONS_ANTHROPIC_*` for all three Claude call sites. Jev uses Replit OpenRouter. Still to do in the Replit UI: enable it and check the model list (the intake default on Replit is `claude-haiku-4-5`, about 10× the price of 5.5).
- **RunPod credits:** for training and benchmarks only. Replit can't host a GPU.
  1. Label HN posts with Claude (on the Replit credits) and hand-check a gold set of about 200.
  2. Fine-tune a small open model on RunPod.
  3. Keep it only if it comes within about 2 points of Claude on the gold set. Hybrid: the small model for confident posts, Claude for unsure ones.
- **Better models to try** (each as a backtest challenger):
  - a state-space / local-level model with binomial counts (handles partial months);
  - a hierarchical model across roles;
  - Chronos (Amazon's zero-shot time-series model) as one benchmark row on RunPod.
- **Monte Carlo:** use it for a scenario fan (sample k from `k_estimate.json`) and for error bars on backtest accuracy. It is not the forecast itself.

### Next build: CV upgrade (not started)
`backend/signals/advisor/cv_writer.py` already rewrites the saved CV for the one target role. Code drops unbacked numbers, and the output is `.md` only. Add:
1. **XYZ bullets.** Only use numbers that are in the original CV. Otherwise leave a placeholder like `[add a number]` for the user to fill in.
2. **New skills.** Add only skills learned in Varity, in Skills plus a Projects/Training section from the completed pathway. Never add them to old job bullets.
3. **Jake's resume layout.** Output an HTML print-to-PDF page plus a `.tex` download for Overleaf.
4. **Tailoring to a pasted job ad.** Code extracts the ad's skills. Show a match list (have / missing). Missing skills are suggested, never added to the CV.

### Status of everything the user has asked for
| # | Request | Status |
|---|---|---|
| 1 | Is MiroFish usable / a mini version | Answered; dropped |
| 2 | Review the forecast architecture | Done (`tasks/plan-dynamic-forecast.md`) |
| 3 | Plan for a dynamic, constantly updated forecast | Done (Phases 1–7) |
| 4 | Archify diagrams (run by Haiku) | Done (`docs/diagrams/dynamic-forecast.html`) |
| 5 | Phase 1: daily role-forecast refresh | Built, committed to main (8a867c8); Replit setup is the user's |
| 6 | Phases 2–7 (nowcast, ledger, role scenarios, 2nd source, title discovery) | Built except Phase 5 (needs permission / history); not committed |
| 7 | Google OAuth workaround | Advice given; `.ics` to become the main button (UI not changed) |
| 8 | Does the forecast use AI/ML | Answered: statistics; ML lost |
| 9 | Use RunPod credits for ML | Planned (post tagger), not built |
| 10 | Agent that grabs data | The scheduled daily refresh (item 5); no LLM agent by design |
| 11 | Backtest | Exists |
| 12 | Monte Carlo | Not built |
| 13 | Models better than Monte Carlo | Recommended, not built |
| 14 | LLMs where they fit | CV read/write, advice; post labelling built (`engine/llm_labels.py`), not run (no credits) |
| 15 | Own specialised AI on RunPod | Not built (needs the Claude labels and gold set first) |
| 16 | AI/ML across the app | Plan given (tagger, embeddings, title discovery); none built |
| 17 | CV improved from the previous resume with new skills | Partly (no Projects/Training section) |
| 18 | CV in Jake's format | Not built |
| 19 | CV bullets in XYZ | Not built |
| 20 | CV tailored to the roles applied for | Partly (one target role); pasted job ad not built |
| 21 | Generate and download the new CV | Partly (`.md` only) |
| 22 | All AI through the Replit credits | Code done; Replit UI setup not verified |
| 23 | Drop Google Tasks | Recommended; UI not changed |
| 24 | No commits to GitHub | Followed |

## The hackathon
- XMUM "Sustainably Developing Code" Hackathon 2026, **Domain 1: Aiversecity Future-Ready Workforce**.
- Team **Hokkien Mee Is Purple**: Ee Zhan (the user) and Goh Sheng Kuan (SK).
- **Preliminary deadline: Sun 25 Oct 2026, 07:59:59 MYT.** No commits after it. Our own target: submit Sat 24 Oct, 21:00.
- Rubric: Innovation 30, Problem-Solution Fit 25, Feasibility 25, Clarity 20.
- Key rules:
  - Never invent numbers; fabrication means instant DQ.
  - Public or synthetic data only.
  - Declare every AI tool.
  - Replit is compulsory.
  - Any member may be asked to explain any code.
  - Video is 5–7 min, demo first.
- Organisers allow scrapers. But organiser OK does not override a site's robots.txt, terms or bot protection; we never bypass a challenge.

## The product: Verity
- **Repo:** https://github.com/TayEeZhan/verity (private until submission). Local clone: `C:\Users\eezha\verity`.
- **Live app:** https://verity--eezhan0805.replit.app. It still serves older code until the user pulls and republishes on Replit.
- **Stack:** Python 3.12, Streamlit 1.66.1, Pillow 13.0.0, all pins in `requirements.txt`. ML experiment packages are in `requirements-dev.txt`. Virtual env: `C:\Users\eezha\verity\.venv`.
- **Tests:** 975 pass on main (`.venv\Scripts\python -m pytest -q`, about 8 min).
- **App flow:** 1 You (persona or skill picker) → 2 Skills radar → 3 Future roles (match + outlook + SDG goal + MyCOL badges + role forecast) → 4 Your plan (staged pathway, daily to-do, .md/.ics export, SDG lines) → Evidence (Skills, Skill detail, Method).

## Built and merged into main (PRs #1–#15, all merged)
| Area | Key facts (all sourced in data/) |
|---|---|
| Demand data | 94 HN "Who is hiring" threads, 2019-01..2026-10, 48,508 posts; 40-skill taxonomy and tagger |
| Skill forecast | naive3 beat naive, drift, damped and gradient boosting on held-out 2024–25 (MAE 1.66 pp at 12 months); rolling volatility-scaled conformal 80% band covered 93.8% |
| Trend label | Welch test, last 12 vs prior 12 months, p<0.05; held 67.2% (n=720) |
| AI exposure | Anthropic Economic Index automation share by occupation. Cross-check with GPTs-are-GPTs, AIOE and Microsoft: only the "language" stance is robust, the rest are shown as contested. k=2 is a labelled assumption; the data cannot pin it down |
| Roles | 9 roles (8 ranked); profiles learned from single-role posts with the title masked; rank = 0.7 match + 0.3 outlook; under 20% match is not ranked. Role forecast band covered 93.6%; label held 69.3% (n=228, 8 roles = a rough guide) |
| Pathway | no-regret → near-term → future-bet stages; ≤45-min daily tasks; 77 link-checked resources (76 free, 1 free trial); no HRD Corp claims |
| SDG | Employer-sector shares per role from posts (8 sectors, hand-checked precision ~85–95%). Goal re-rank needs ≥10 sector posts; with real data no example profile is re-ordered |
| Malaysia | MyCOL 2024/2025 (TalentCorp), 10 tech occupations mapped to roles (team judgement; read by eye from the PDF). Job-site collectors (Hiredly, Jobstore) are built but **refuse to run without `--permission-confirmed`**. JobStreet, Maukerja, Indeed and Ricebowl block with a Cloudflare challenge |
| Live data | Refresh button; scheduled job + Replit App Storage code (**Replit UI setup still pending**, see docs/replit-schedule.md) |
| Other | New-skill discovery radar (weak backtest, human review only); VS Code CodeTour (`.tours/`); submission drafts in `docs/submission/` |

## Open / to do
1. **Replit:** in Git, Pull → `pip install -r requirements.txt` → restart → Republish. Optional: scheduled job + bucket (docs/replit-schedule.md).
2. **Varity is the only app (PR #21, `feat/varity-only`, not merged).** Streamlit UI retired; #18/#19/#20 are on main. Varity renders only from the API (no synthetic numbers), with example profiles, SDG + MyCOL, .md/.ics export, Skills radar, Method page. `.replit` = Reserved VM running `backend/signals` on 8080. `app.py` and `engine/outcome.py` are deleted. The HN demand data is the committed 2026-10 snapshot (no Refresh button now).
3. **Replit after merging #21:** Pull → republish as Reserved VM → enable AI Integrations → Anthropic → confirm `AI_INTEGRATIONS_ANTHROPIC_API_KEY` / `_BASE_URL` names in Secrets → run one synthetic CV and click all 8 screens. Claude model on Replit: `claude-haiku-4-5`.
4. **Submission docs:** fill [TEAM TO FILL] (email, phone, university, workshop ticks, Replit plan, signatures). Export `SDC2026_HokkienMeeIsPurple_Preliminary.pdf` and `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf`.
5. **Pitch script and Q&A** in docs/submission/ predate the journey UI, SDG goal and role forecast. Update them, then record the video. Don't click Refresh during recording.
6. **Decisions still open:**
   - the AIOE licence (no licence file);
   - cloud_devops stance;
   - Gmail in 20 old commits (rewriting needs a force push and the user's yes; new commits use `168839221+TayEeZhan@users.noreply.github.com`).
7. **Housekeeping:** old git worktrees exist at `C:\Users\eezha\verity-*` (safe to remove with `git worktree remove`).

## How we work (user preferences)
- Plan first and confirm. Major work goes on `feat/*` branches with PRs; never merge to main without the user's go.
- Sonnet and Haiku subagents build; Opus plans and reviews before anything is called done. Prove work with tests and screenshots.
- Simplified Technical English: short sentences, active voice.
- After major work, explain how it works for judge Q&A.
- Ponytail mode (full) is active: the smallest complete change.
- A "Fact-Forcing Gate" hook asks for facts before the first write or Bash command; state them and retry.
