# Plan: final-round gaps (Domain 1 Finalist Guide)

Written 30 Oct 2026. **Status: plan only. Nothing is built. The user reviews this first.**

Workflow for every work package (WP):
1. Opus (big model) owns this plan and the design.
2. Sonnet or Haiku subagents write the code, one WP at a time, on a `feat/final-*` branch.
3. A Haiku subagent writes and runs the tests (`.venv\Scripts\python -m pytest -q` and `pytest -q` in `backend/signals/`).
4. Opus reviews the diff and the test output before the WP is called done.
5. No commit or push until the user says so (CLAUDE.md).

Guide items 1+5 are the same work (WP1). Items 2+6 are the same work (WP2). Item 3 is WP3. Items 4+7 are WP4.

---

## WP1. "Change the trend data now": a live refresh with fetch dates (guide items 1 and 5)

**Problem.** The judges say "please change the trend data now". Today the app reads a snapshot. The daily job is not set up on Replit, and there is no button. So we cannot show that the results change.

**Design: two buttons on the Skills radar, both honest.**
- **A. "Fetch latest HN now"** calls the real pipeline (`engine.refresh.refresh`) on the server. It downloads this month's thread, rebuilds the scores and saves a new snapshot with `fetched_at`. Early in a month the change can be small. That is real, but it is a weak demo.
- **B. "Replay an older snapshot (demo)"** switches the app to a real, dated, older data cut: `build_scores(as_of="2025-10")` with the role profile for that date (`roles.profile_for`). The banner says "Showing real data as of 2025-10 (replay)". The routes, scores and pathway visibly shift. This is real data, not invented, and it proves that the output follows the data. "Back to latest" restores the newest snapshot.

**Architecture**
```
Skills radar screen ──POST /api/data/refresh──▶ engine.refresh.refresh(work_dir)
   │                                               └▶ engine.store.save_snapshot (fetched_at)
   │
   └──GET /api/* ?asOf=YYYY-MM (kept in sessionStorage)──▶ service.load_data(as_of)
                                      └▶ engine.scores.build_scores(as_of) + roles.profile_for(as_of)
All screens ──GET /api/*──▶ service.current_data_dir()  (override > newest snapshot > committed data/)
                             └▶ every reply carries meta {source, as_of, fetched_at}
Frontend banner: "Source: HN Who is hiring · as of 2025-10 · fetched 2026-10-30 09:12 MYT"
```
- Files: `backend/signals/trendsignal/web/app.py` (2 routes), `backend/signals/advisor/service.py` (override), `frontend/screens-explore.js` (buttons and banner), `frontend/app.js` (re-fetch after a change).
- Guard: the replay is per viewer (query parameter, no server state), so a visitor cannot change the data for anyone else. The refresh starts at most once per 10 minutes for the whole server (429 otherwise).

**Example run (Aina: Python, SQL, PostgreSQL, Docker, AWS; real numbers from today's files)**
1. Latest data: #1 Backend Engineer, match 0.655, rank 0.759, Rising. #2 AI/LLM Application Engineer, match 0.388, rank 0.571, Rising. #3 Data Engineer, match 0.513, rank 0.509, No clear change.
2. The judge asks for a change. Click "Replay 2025-10". Profiles, trend labels and forecasts come only from data before 2025-10. The routes re-rank. Code computes the new order at build time; we record it in `docs/submission/demo-checklist.md`.
3. Click "Back to latest". The original order returns. The banner date changes both times.

**Risks**
- A refresh takes time on Replit (one thread download, then a role rebuild of maybe tens of seconds). Mitigation: run it in the background with a "refreshing…" state. The last good data stays on failure (this already exists).
- The replay needs old role profiles. `role_profiles.json` already holds 6 as-of points (2023-12 … 2026-10), so no raw posts are needed. The replay can only use those 6 dates.
- An old cut can look "wrong" to judges. Label it "replay of real data as of …" every time.
- The 975 tests must stay green. `build_scores(as_of)` already has no-look-ahead tests.

---

## WP2. "Why this score, and what would raise it?" (guide items 2 and 6)

**Problem.** The route card shows the score and the gap. It does not show the score's parts, or what each missing skill would add.

**Design.** Pure arithmetic from the numbers `match_roles` already returns. No new model.
- `match = Σ weight(have) / Σ weight(all)`. The profile weights sum to 1.
- `rank = 0.7 × match + 0.3 × outlook` (outlook: Rising 1.0, No clear change 0.5, Falling 0.0).
- For each gap skill: `+match = weight`, `+rank = 0.7 × weight`. Sort by `+rank`. Show the top 3.

**Architecture**
```
engine/roles.match_roles ──▶ new helper engine/roles.score_breakdown(role)  (≈15 lines)
                              └▶ {"parts": {match, outlook, 0.7/0.3}, "raise": [{skill, +match, +rank, resource}]}
roles API / advisor service adds "breakdown" to each route ──▶ route card: "Why 0.759?" panel
```

**Example run (Aina → Backend Engineer, real numbers)**
- Why 0.759: 0.7 × 0.655 (you have 65.5% of the role's skill weight) + 0.3 × 1.0 (Rising) = 0.459 + 0.300 = 0.759.
- What would raise it: Go +0.120 match → rank 0.843. Kubernetes +0.086 → 0.819. Terraform +0.083 → 0.817. Each links to its first link-checked resource.

**Risks.** Small. Merged synonym parents (`merge_synonyms`) must not count twice. The panel must say that 0.7/0.3 is team judgement, not fitted.

---

## WP3. HRD Corp programmes (guide item 3)

**Problem.** The guide names "HRD Corp-claimable programmes". `resources.json` says the claim status is not verified, so we show none.

**Design.** Do not invent. Add a small, separate list of real programmes, each checked by a person.
- New file `data/hrd_programmes.json`: `{skill, title, provider, url, hrd_status, checked_on, source_url}`. `hrd_status` is "listed on the HRD Corp directory" or "provider page says claimable".
- A team member (not an LLM) finds about 5–10 programmes for our common gap skills (Python, cloud, Kubernetes, data, AI) on the HRD Corp site (https://hrdcorp.gov.my) or on the provider's page. Each entry keeps the link that shows the claim.
- The pathway shows them as an **optional "employer-funded" line** next to the free resource. It never replaces the free one, and it says "for employees of HRD Corp-registered employers".
- Code: `engine/pathway.py` reads the file like `resources.json`. The link check (HTTP 200) is re-used.

**Example.** Aina's Kubernetes step shows the free resource first, then "Employer-funded option: <course> by <provider> (HRD Corp listed, checked <date>, source link)".

**Risks.**
- This is manual research, and we can't do it from code. If no programme is found for a skill, show nothing.
- Fees and claim rules change. Show the check date. Judges may open a link, so re-check all links the day before the final.

---

## WP4. An SDG goal that changes choices, and a reason line per role (guide items 4 and 7)

**Problem.** The guide's test: "if the tag were removed, would the user lose anything?" Today the answer is no. `rerank_for_goal` exists but nothing calls it.

**Important finding.** With real data, wiring it in as it is will re-order nothing. Sector counts per role are small (for example, Data Engineer in the last 12 months: 61 posts, 5 from health employers, 1 from climate). The re-rank needs ≥10 sector posts. So a plain wire-up is still decorative.

**Design: let the goal act where the data is strong enough, and say so where it isn't.**
1. **Goal picker** on CV & routes ("I care about: health, climate, education, …", the 8 sectors in `role_sdg.json`).
2. **Roles:** call `rerank_for_goal`. Each card gets a goal line: "5 of 61 Data Engineer posts (8%) came from health employers, against X% of all posts". When `reliable` is false, it adds "too few posts to re-rank (n = 5)". This is honest, and the user still learns which roles serve the goal.
3. **Pathway (where the goal does change things):** skills already carry SDG targets and a reason (`taxonomy.json`: `sdg` and `sdg_reason` for all 40 skills). With a goal, the pathway moves goal-linked skills to the front **inside a stage**. It never changes stages, dates or minutes. It adds the goal line from `plan_sdg_summary(..., goal_sector)`.
4. **Reason line per role:** new helper `engine/sdg.role_reason(role_sdg, role_id)`. Code builds one sentence from `role_sdg.json`: "Most-linked sector: health, 8% of posts in 12 months (SDG 3), source threads". No LLM writes it.

**Architecture**
```
goal picker ──goal_sector──▶ routes API ──▶ match_roles ──▶ sdg.rerank_for_goal ──▶ cards: goal line + reliable flag
            ──goal_sector──▶ /api/pathway ──▶ pathway.build_pathway(goal skills from taxonomy sdg)
                                          └▶ sdg.plan_sdg_summary(plan, role, role_sdg, goal_sector)
sdg.role_reason ──▶ one reason sentence on every route card
```

**Example (Aina, goal = health)**
- Routes: probably the same order (no role reaches 10 health posts). Each card shows its health share and "too few posts to re-rank".
- Pathway for Backend Engineer: inside each stage, any gap skill tagged to the goal's SDG moves first. Code decides; if none of her gap skills has the tag, the plan says so. The plan line reads "N% of Backend Engineer posts came from health employers (SDG 3), against Z% of all posts".

**Risks.**
- Judges may still see "no change" on the routes. The pathway change and the honest "too few posts" line are our answer. **Do not lower the 10-post threshold to force a change.** That would fake a signal.
- Skill SDG tags are team judgement (`sdg_reason`). Say so on screen.
- The skill-tag-to-sector link (for example, which SDG targets count as "health") needs a small mapping table. That table is team judgement and must be shown.

---

## Item 8. Uncommitted work (as of 30 Oct 2026)

Committed on main: Phase 1, the daily role-forecast refresh (8a867c8). Everything below is **not committed** (17 modified files, +403/−22 lines, plus new files). The Replit redeploy is the user's job after the $100 credits arrive.

1. **Nowcast for the open month (Phase 2):** `engine/forecast.py`, `engine/nowcast_backtest.py`, `data/nowcast_backtest.json`. It blends a part-month toward last month. A backtest chooses the weight k (day 1/3/7/14 → k = 100/50/10/0).
2. **Forecast ledger (Phase 3):** `engine/ledger.py`, `engine/store.py`. It saves each day's forecast and grades it when the target month is complete. It adds `track_record` to `role_forecast.json`.
3. **Role scenarios and declining flag (Phases 4, 6):** `engine/role_forecast.py`, `engine/roles.py`, `engine/scores.py`, `data/role_forecast.json`, `data/skill_scores.json`. Each role gets AI exposure, a Fast scenario and a declining rule.
4. **New-role discovery:** `engine/role_discover.py`, `data/title_counts_monthly.csv`. It counts job titles per month and finds titles no role covers. With credits, Claude Haiku reviews them; a new role needs 3 checked quotes.
5. **Claude post labeller:** `engine/llm_labels.py`. Claude labels each post's roles with quotes, and code drops labels whose quote isn't in the post. It has a regex backup and a drift check. It stays off until the backfill runs on credits.
6. **Refresh and scheduler changes:** `engine/refresh.py`, `engine/scheduled.py`. The job starts from the last snapshot, and it stores `roles.json`, the title counts and the labeller config.
7. **"Outlook changed" on the plan (Phase 7):** `backend/signals/advisor/planner.py`, `backend/signals/advisor/service.py`, `backend/signals/tests/test_planner.py`. The plan shows when the target role's outlook moved after you accepted it.
8. **Frontend:** `frontend/screens.js`, `frontend/screens-explore.js`. The forecast screen shows the declining tag, the Fast scenario, the change since the last run, the month-in-progress weight, the track record and who labels the posts.
9. **Tests:** `tests/test_dynamic_forecast.py` (new), `tests/test_refresh.py`, `tests/test_scheduled.py`, `tests/test_scores.py`.
10. **Docs and plans (untracked):** `HANDOFF.md`, `CLAUDE.md`, `BRIEF.md`, `tasks/plan-landing.md`, `tasks/plan-replit-ai.md`, `tasks/plan-varity-only.md`, `docs/diagrams/dynamic-forecast*.{html,json}`, `branding/`, `.claude/`.

Risk: all of this lives on one laptop only. One wrong `git checkout` loses it. Recommendation: commit to a local branch (no push) when the user says so.

---

## Item 9. Good-to-have features: plan, and advice

They earn credit only inside the criteria, and they never replace a must-have. **Do WP1–WP4 first.**

| Feature | Size | Risk to existing code | Advice |
|---|---|---|---|
| **G1. Fairness test** | S (half a day) | None: a new test file and one Method-screen line | **Do.** The cheapest Impact & Feasibility points |
| **G2. HR / team view** | M (1–2 days) | Low: a new screen and a new route that call `match_roles` once per profile. Existing screens are untouched | **Removed on 1 Nov: does not fit a worker-facing site.** |
| **G3. Bahasa Malaysia labels** | M | Low–medium: UI strings go through a `t()` lookup, so there are many small edits in `frontend/` | Main journey labels only (about 60 strings), BM only. Skip Chinese |
| **G4. SDG view for a team** | S, after G2 | Low | Do with G2: add up `plan_sdg_summary` numbers over the team |
| **G5. Skill badges** | S | Low | Skip. Design & UX is only 5% |
| **G6. Low-bandwidth** | none | none | Already mostly true (no build step, few images). Measure the page weight and state it |

**G1. Fairness test.** The matcher reads only the skill list. Prove it:
- Test: 3 synthetic CVs with the same skills but different names, ages, gender words and schools must give the same ranked roles and scores.
- The CV intake must not pass name, age or gender into `match_roles`. A test asserts that the profile holds only skills and years.
- Method screen: "Fairness check: the same skills always give the same result (test name, date)". Limit: the HN data may itself carry hiring bias; say so.

**G2. HR / team view.**
```
New "Team" screen ──upload N synthetic profiles (JSON/CSV, or pick the 3 examples)──▶ POST /api/team
  └▶ for each profile: match_roles(...) ──▶ heatmap: rows = people, columns = target role skills (have / gap)
  └▶ team plan: gap skills ranked by (people missing it) and skill trend
```
Example: the 3 example profiles with the target Backend Engineer. The heatmap shows who misses Go and Kubernetes. The team plan puts the most-missed Rising skill first. Risk: none to existing screens. The data stays synthetic.

---

## Item 10. Reach: meaning and plan

**Meaning.** Reach = who uses Verity first, how they find it, and how many people that is in a realistic year. Judges want a named channel and a sourced number, not "everyone in Malaysia".

**Plan**
1. **First users:** final-year computing students and recent graduates, through a university career centre. Start with XMUM, because we are there and can run a pilot.
2. **Second channel:** TVET providers and HR teams (with the G2 team view).
3. **Numbers. TEAM TO FILL, each with a source; do not guess:**
   - XMUM computing students per year (university figures or the faculty office).
   - Malaysian ICT graduates per year (Ministry of Higher Education graduate statistics).
   - Pilot size: one cohort of N students in one semester, with the career centre's consent.
4. **Cost to reach:** zero for the pilot (the career centre shares a link).
5. Final report Section 4 funnel: channel → people reached → people who finish a profile → people who finish one plan step (from the WP-M counters).

---

## Item 11. Freshness and cost: estimates, and what could be better

All numbers below are **planning estimates**. Check the prices on the Anthropic and Replit pages before they go into the report.

**Freshness today.** HN data refreshes daily once the Scheduled Deployment is set up. The source is monthly (one thread a month, filled over about 2 weeks). The nowcast handles the open month. The AI-news ranker updates every 15 minutes.

**Cost per month**
| Item | Assumption | Estimate |
|---|---|---|
| Hosting (Replit Reserved VM, smallest) | Replit price page | about $10–20 per month (check) |
| App Storage | a few MB of snapshots | under $1 |
| CV reading (Claude Haiku) | about 3k tokens in + 1k out per CV; Haiku 4.5 list price $1 in / $5 out per million tokens ≈ $0.008 per CV | about $8 per 1,000 CVs |
| Daily post labelling | about 15 new posts a day × about 900 tokens | under $1 per month |
| Title review | a few titles a week | under $1 per month |
| One-off relabel of 48,508 posts | about 850 tokens per post ≈ 41M tokens | $20–40 (HANDOFF estimate). **The command prints its own estimate before `--yes`. Use that number.** |
| **Total at 1,000 users a month** | | **about $20–30 a month ≈ $0.02–0.03 per user** |

**What could be better**
- **Measure, don't estimate:** log `usage.input_tokens` and `output_tokens` of each Claude call into a counter file, then report the real cost per CV.
- Cache the CV result by file hash, so a re-upload costs nothing.
- Use the Batch API for the one-off backfill (about half price, if Replit's integration allows it).
- Say clearly: forecast, match and pathway cost zero per user (plain Python on files). The only marginal cost is the CV read, and "Try an example" makes no LLM call.

---

## Item 11b. Measured SDG impact (WP-M)

**Problem.** Phase 1 set targets: 50% finish one plan step in 14 days, 80% pick a role, 60% add a Rising or AI-complement skill. We have no results, and "unsupported claims are not credited".

**Plan**
1. **Counters (small code):** an append-only event log (anonymous session id, event, time): `profile_done`, `route_picked`, `rising_skill_in_plan`, `step_ticked`. No name, no email, no CV text.
2. **"Impact" panel on the Method screen:** reads the log and shows the 3 KPIs against the Phase 1 targets, with n and dates.
3. **Pilot (people, not code):** 10–20 students use synthetic profiles or a typed skill list (not a real CV) over 7–14 days, each with consent.
4. **Report Section 4.1 proof:** the counter code and a log excerpt.
5. Honesty: report "pilot, n = X, 7 days". Never present it as a population effect.

**Risk.** Time. 14 days may not fit before the final. Use 7 days and say so.

---

## Item 12. Privacy and fairness: meaning and plan

**Meaning**
- **Privacy:** how personal data is protected under Malaysia's Personal Data Protection Act 2010 (PDPA). Its 7 principles: General, Notice and Choice, Disclosure, Security, Retention, Data Integrity, Access. Judges ask what we keep, why, for how long, who sees it, and how a user deletes it.
- **Fairness:** recommendations must not differ by age, gender, race or background. We must show a check, not just claim it.

**What exists.** Sign-in is optional. CVs are synthetic. Contact details and ID numbers are redacted before Claude sees a CV. The raw CV is not stored. `DELETE /api/me` exists. Only counts are committed.

**Plan**
1. **Privacy notice page** (short, static, linked from the CV upload), mapped to the 7 principles: what we collect, why, where it is stored (Replit PostgreSQL), who processes it (Anthropic for CV reading), how to delete it.
2. **Retention rule** (fills the TEAM TO FILL in `qa-prep.md`): for example, delete accounts with no login for 12 months. A small scheduled clean-up, with a test.
3. **Name redaction:** also strip the CV's first line (usually the name) before Claude. Say that names can still remain.
4. **Consent checkbox** before CV upload: "Use a sample CV. The text goes to Anthropic for reading."
5. **Fairness:** G1 above, plus the stated limit: "the source data (HN posts) is US-heavy and may carry hiring bias; we do not correct it".

---

## Suggested order
1. WP1 live data change (M) and WP2 score breakdown (S): the biggest score gains.
2. WP4 SDG goal and role reasons (M).
3. WP-M counters and pilot (S code + people time); G1 fairness test (S).
4. Item 12 privacy page (S); item 11 cost logging (S); WP3 HRD list (manual research).
5. Optional: G2 team view, G3 BM labels.
6. Update the pitch script, the demo checklist and HANDOFF.md. Commit when the user says so.

---

## WP-MY. A Malaysian demand source (judges' feedback, 1 Nov 2026). **Built as a sector-level check (see Design).**

**Feedback.** "Hacker News posts aren't very representative of Malaysia, so adding a Malaysian data source would make a big difference."

**Source.** DOSM, *Job Vacancies Advertised Online* (also called "Big Data Analytics: Job Market Insights and My Job Profile"). It is official, public and quarterly. It breaks vacancies down by occupation (MASCO), economic activity, state, skills and field of study. DOSM collects it by web scraping and says it does not cover every vacancy in Malaysia. Example release: Q3 2023, published 29 Feb 2024 (https://www.dosm.gov.my/portal-main/release-content/big-data-analytics-job-market-insights-and-my-job-profile-third-quarter-of-). Interactive data: ILMIA (ilmia.gov.my) and OpenDOSM (open.dosm.gov.my).

**Why it fits.** `data/mycol_role_map.json` already maps our roles to MASCO codes. So a role can show "Malaysia: N online vacancies for <MASCO occupation> in Qx YYYY (DOSM), up/down from the last quarter".

**Design (built 1 Nov as a sector-level check: DOSM has no per-job-title split, see engine/my_dosm.py)**
```
DOSM quarterly summary table (PDF/Excel) ──engine/my_dosm.py (parse ICT MASCO rows)──▶ data/my_vacancies_quarterly.csv
   (quarter, masco_code, occupation, vacancies, source_url, published)
mycol_role_map (role → MASCO) ──▶ service.py adds "malaysia" to each route ──▶ route card Details: Malaysia line + source + date
```
- Quarterly refresh: the scheduled job checks the DOSM release page once a week and parses a new release.
- It is a **cross-check**, not a forecast input, until we have enough quarters to backtest it (same rule as HN: no model enters without a backtest).

**Steps:** 1) find whether OpenDOSM has a CSV/API for this series (preferred) or only PDF tables; 2) parse the last 8 quarters for the ~10 ICT MASCO codes; 3) show the Malaysia line on route cards and the Method screen; 4) tests: parser on a saved table, no invented rows.

**Risks.** The tables may be PDF only (fragile parsing; the fallback is a hand-entered CSV with the page reference per row). MASCO groups are broad (for example, "software developers"), so the match to our roles is team judgement, as with MyCOL. If the fine detail is only on the ILMIA dashboard, we read it by hand and say so.

**Effort.** About half a day to a day if CSV, 1–2 days if PDF.
