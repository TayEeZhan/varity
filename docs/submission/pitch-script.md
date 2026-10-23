# Verity pitch video script (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1.
Branch: `docs/submission`. Status: draft for the team to rehearse and edit. Nothing here is final until both members have read it aloud.

## Timing at a glance

- **Target length: 5:45.** Hard maximum: 7:00. The organisers want 5 to 7 minutes and take 1 point per 30 s over (`C:\Users\eezha\sdc-hackathon\BRIEF.md`). The headroom is 1:15.
- **Speaking split:** Sheng Kuan 176 s, Ee Zhan 169 s.
- **Words:** 594 written words. 718 spoken words once numbers are read aloud ("6.4%" is four words, "54.6%" is five). Average 125 words per minute. Fastest rows 129 (rows 1 and 8). Slowest row 101 (row 11). The aim is 140 or less on every row. All rows pass (see the check below).
- **Layout:** slides only at the start (0:00-0:40) and the end (3:45-5:45). The live app fills 0:40-3:45, as the organisers advise: keep the slides generic and focus on the system demo.

## Rules this script follows

1. Every number comes from a file in the repo. The last section maps each number to its file.
2. Aina is synthetic and the script says so (row 1). The app labels her "(synthetic)".
3. Only the CV intake uses a language model, and the script says so (row 10). The forecast, role match, pathway and SDG parts use none. The model only points at skills. Code checks every quote.
4. The script claims no HRD Corp listing and no Malaysian data.
5. No sentence says the forecast predicts a precise future. The script says the simple method won.

## State of the app before the take starts (0:40)

| Item | Setting |
|---|---|
| URL | https://verity--eezhan0805.replit.app (from `docs/build-plan.md`). Check that it shows real data and no "Prototype: showing sample data" banner |
| Sidebar Scenario | Moderate |
| Sidebar As of | latest month (2026-10 in the committed data) |
| Roles tab | Example profile "Aina, junior Python dev (synthetic)" (the first entry, so the default) |
| Target role | none chosen yet (a fresh browser session) |
| Pathway | Hours per week 5 (the default) |
| As of 2023-12 | open it once before recording so the result is cached |

## Timed script

| Time | Who speaks | On screen | Exact spoken words |
|---|---|---|---|
| 0:00-0:40<br>(40 s)<br>**Problem**<br>row 1 | Sheng Kuan | Slide 1 (title) for 5 s, then slide 2 (line chart: share of Hacker News hiring posts that mention AI, 6.4% to 54.6%) until 0:30, then slide 3 (Aina and the Verity chain). | We are Hokkien Mee Is Purple. This is Verity, for Domain 1. The brief asks us to track AI progress, predict skills, match roles and build reskilling paths, linked to SDG 4.3, 4.4, 8.2 and 8.5. AI mentions in Hacker News hiring posts grew from 6.4% in January 2019 to 54.6% in September 2026. Meet Aina, a junior Python developer. She is synthetic; we use no real CVs. |
| 0:40-1:21<br>(41 s)<br>**Demo 1: Roles**<br>row 2 | Ee Zhan | App, Roles tab. Select Example profile "Aina, junior Python dev (synthetic)". Hover the match bar and the Gaps list of card #1. Point at the Role demand line. Click "Fast AI disruption" in the sidebar Scenario switch and point at the caption on card #1. Click "Moderate" again before the cut. | In the Roles tab we pick Aina: Python, SQL, PostgreSQL, Docker and AWS. Each card has a match bar and her gaps. Backend Engineer ranks first, at 66%. She lacks Go, Kubernetes, Terraform and Node.js. Role demand is Rising: 10.6% of posts, up from 9.4%. Flip the sidebar to Fast AI disruption. The card adds an estimate: Backend demand about 6.1% lower. The order stays the same. The app labels k equals 2 as an assumption. |
| 1:21-2:05<br>(44 s)<br>**Demo 2: Pathway**<br>row 3 | Sheng Kuan | Click "Choose this as my target role" on Backend Engineer. Open the Pathway tab. Scroll the three stages (Node.js; Go, Kubernetes; Terraform). Scroll to the Daily to-do list. Tick the first task (progress bar shows 10%). Click "Download calendar (.ics)". Scroll to "SDG links" and hold on the two sentences. | Aina picks Backend Engineer, and the Pathway tab turns her gaps into a plan. Stage one is no-regret: Node.js, which more than one of her roles needs. Stage two is near-term demand: Go and Kubernetes. Stage three is a future bet: Terraform, which is Rising. The plan has 4 skills, 15 daily tasks and 7.5 hours, all with free resources. Aina ticks a task, and progress moves to 10%. She downloads a calendar file. The SDG lines name SDG 4.4 for skills and SDG 8.5 for work. |
| 2:05-2:20<br>(15 s)<br>**Demo 3: Skill detail**<br>row 4a | Ee Zhan | Open the Skill detail tab. In the Skill box choose Python. Hold on the chart: grey monthly line, blue smoothed line, orange forecast point with its bar. | Skill detail, Python. The chart shows monthly share, a smoothed line, and the forecast: 26.3%, band 22.1% to 30.9%. |
| 2:20-2:44<br>(24 s)<br>**Demo 4: As-of slider**<br>row 4b | Ee Zhan | Drag the sidebar "As of" slider to 2023-12. Wait for the recompute (pre-warmed). Scroll to "What happened" on the Python chart: green diamond inside the orange bar. Drag the slider back to 2026-10 before the cut. | Next, the As-of slider, set to December 2023. The engine sees no later data. It forecast Python at 20.2%, band 16.1% to 25.0%. In December 2024 the real value was 18.0%. Inside the band. |
| 2:44-3:09<br>(25 s)<br>**Demo 5a: Method, backtest**<br>row 5 | Sheng Kuan | Open the Method tab. Hold on the model table (naive3 row), then scroll to "How good is the band?" (93.8%) and "How good is the trend label?" (67.2%). | The Method tab shows our scores. The three-month average, naive3, has the lowest 12-month error: 1.66 percentage points. The 80% band covered 93.8% of real values. The Rising or Falling label pointed the right way 67.2% of the time. |
| 3:09-3:34<br>(25 s)<br>**Demo 5b: Method, exposure, k, radar**<br>row 6 | Ee Zhan | Scroll to "Exposure cross-check": the table, then the Contested line. Scroll to the "k from data" line. Scroll to "Candidate new skills" and hold on the MCP row. | The exposure cross-check compares our AI stance with three other indices. The language category alone holds up; five are contested, and the app says so. The k line admits the data cannot pin k down. The new-skills radar flags MCP: 1.5% of posts, up from 0.3%. |
| 3:34-3:45<br>(11 s)<br>**Demo 6: Refresh**<br>row 7 | Ee Zhan | Scroll the sidebar to "Refresh live data" and click it. Wait for the green "Refreshed ..." message. Point at the header line "Data as of ..." and the generated time beside it. | Last, Refresh live data. It fetches the open Hacker News thread and rebuilds the scores. The header shows when the data was rebuilt. |
| 3:45-4:32<br>(47 s)<br>**Trust: tests and band**<br>row 8 | Sheng Kuan | Slide 4 (how it works: one-line block diagram) for 10 s, then slide 5 (bar chart of 12-month error: naive3 1.66, naive 1.81, gradient boosting 2.06, drift 2.13, damped 2.27; callout 93.8% vs 80%). | Verity tags 40 skills across 48,508 hiring posts. Over 616 held-out forecasts, 12 months ahead, the three-month average had 1.66 percentage points of error. Last month alone had 1.81. Trend lines had 2.13 and 2.27. Gradient boosting had 2.06. The simple method won, so Verity shows a band and makes no promise. The band uses the errors of the last 24 past forecasts, a conformal method. It covered 93.8%, against an 80% target. |
| 4:32-5:00<br>(28 s)<br>**Trust: profiles and disagreement**<br>row 9 | Ee Zhan | Slide 6 (left: 2,569 single-role posts feed the role profiles; right: exposure table summary, 1 robust category, 5 contested, rank correlation -0.79). | Role profiles are learned from 2,569 Hacker News posts that name a single role. Code sets the plan order. Only the language category holds up across the indices, so 26 of our 40 skills carry a contested tag. Microsoft's index even ranks occupations almost opposite to ours: minus 0.79. |
| 5:00-5:20<br>(20 s)<br>**Limits and next steps**<br>row 10 | Sheng Kuan | Slide 7 (four short bullets: US and startup-heavy data; JobStreet needs a data partnership; CV intake: the model points, code checks every quote; HRD Corp status unverified). | Limits. Hacker News is US and startup heavy, so this is not Malaysian data. JobStreet needs a data partnership. Only CV intake uses a language model: it points at skills, and code checks every quote. We could not verify HRD Corp status. |
| 5:20-5:45<br>(25 s)<br>**SDG close**<br>row 11 | Ee Zhan | Slide 8 (SDG 4.4, 8.2, 8.5 icons, team name, repo and app URL). | Verity serves SDG 4.4, skills for employment, and SDG 8.5, productive work, with free resources and a dated source for every skill. The app says: Estimates, not facts. You decide. We are Hokkien Mee Is Purple. Thank you. |

Row 11 includes a 5 s end card (team name, repo link, app link) after the last word.

## Words per minute check

Spoken words count every number as spoken ("1.66" is four words: one point six six). "naive3" counts as two.

| Row | Time | Who | Seconds | Written words | Spoken words | Words per minute | Check (140 or less) |
|---|---|---|---|---|---|---|---|
| 1 | 0:00-0:40 | Sheng Kuan | 40 | 68 | 86 | 129 | ok |
| 2 | 0:40-1:21 | Ee Zhan | 41 | 76 | 87 | 127 | ok |
| 3 | 1:21-2:05 | Sheng Kuan | 44 | 87 | 94 | 128 | ok |
| 4a | 2:05-2:20 | Ee Zhan | 15 | 19 | 30 | 120 | ok |
| 4b | 2:20-2:44 | Ee Zhan | 24 | 34 | 51 | 128 | ok |
| 5 | 2:44-3:09 | Sheng Kuan | 25 | 39 | 52 | 125 | ok |
| 6 | 3:09-3:34 | Ee Zhan | 25 | 46 | 52 | 125 | ok |
| 7 | 3:34-3:45 | Ee Zhan | 11 | 23 | 23 | 125 | ok |
| 8 | 3:45-4:32 | Sheng Kuan | 47 | 73 | 101 | 129 | ok |
| 9 | 4:32-5:00 | Ee Zhan | 28 | 49 | 58 | 124 | ok |
| 10 | 5:00-5:20 | Sheng Kuan | 20 | 42 | 42 | 126 | ok |
| 11 | 5:20-5:45 | Ee Zhan | 25 | 38 | 42 | 101 | ok |
| **All** | 0:00-5:45 | both | 345 | 594 | 718 | 125 | ok |

The demo rows (2 to 7) need pauses for clicks and page loads, so their rates are the real limit. If a row feels rushed in rehearsal, use the cut list and keep the voice at the same pace.

## Cut list (if the take runs long)

Drop lines in this order. Seconds use the script's average rate (125 words per minute). Make the cuts in the script before recording, so the voice stays calm.

| Priority | Row | Line to drop | Spoken words | Saves | Total saved | What stays |
|---|---|---|---|---|---|---|
| 1 | 6 | "The new-skills radar flags MCP: 1.5% of posts, up from 0.3%." | 17 | 8 s | 8 s | The radar stays on screen with no words. Say it in Q&A if asked. |
| 2 | 8 | "Verity tags 40 skills across 48,508 hiring posts." | 13 | 6 s | 15 s | Slide 4 still shows it. |
| 3 | 3 | "She downloads a calendar file." | 5 | 2 s | 17 s | Keep the click. The file name shows on screen. |
| 4 | 2 | "The app labels k equals 2 as an assumption." | 9 | 4 s | 21 s | The sidebar label "Fast AI disruption (k = 2, an assumption)" stays visible. |
| 5 | 8 | "Last month alone had 1.81." | 8 | 4 s | 25 s | Keep 1.66, 2.13, 2.27 and 2.06. |
| 6 | 9 | "Role profiles are learned from 2,569 Hacker News posts that name a single role. Code sets the plan order." | 24 | 12 s | 37 s | Q&A covers it. |
| 7 | 4a | "The chart shows monthly share, a smoothed line, and the forecast: 26.3%, band 22.1% to 30.9%." | 27 | 13 s | 50 s | Say only "Skill detail, Python." The next row quotes the band. |
| 8 | 1 | "The brief asks us to track AI progress, predict skills, match roles and build reskilling paths, linked to SDG 4.3, 4.4, 8.2 and 8.5." | 32 | 15 s | 65 s | Judges know the brief. Last resort. |

Stopwatch checkpoints during a take: row 2 starts at 0:40, row 8 starts at 3:45, row 11 starts at 5:20. If row 8 starts after 4:05, apply cuts 1 to 4 at once. If the finished video is over 7:00, cut demo lines. Keep the Limits row (row 10).

## Where each number comes from

All files are in the worktree `C:\Users\eezha\verity-docs`. "Computed" means the engine ran read-only on 22 Oct 2026 with the functions `app.py` calls (`engine.roles.match_roles`, `engine.pathway.build_pathway`, `engine.scores.build_scores`). The app must show the same values. If it does not, trust the screen and fix the script.

| Spoken | Value | Source |
|---|---|---|
| SDG 4.3, 4.4, 8.2, 8.5 | the four targets | `C:\Users\eezha\sdc-hackathon\BRIEF.md`, Domain 1 |
| AI mentions 6.4% to 54.6% | 49 of 765 posts (2019-01); 136 of 249 posts (2026-09) | `data/ai_context_monthly.csv`. September 2026 is the last full month. October 2026 (138 of 266, 51.9%) is partial, so the script does not use it |
| Aina's skills | Python, SQL, PostgreSQL, Docker, AWS | `app.py`, `PERSONAS` |
| Backend Engineer 66%; gaps Go, Kubernetes, Terraform, Node.js | match 0.66 | computed; profile from `data/role_profiles.json` |
| Role demand Rising, 10.6% up from 9.4% | 393 of 3,714 posts vs 366 of 3,914 posts | `data/role_trends.json`, `backend_engineer` |
| Fast: Backend demand about 6.1% lower | `fast_shift` -0.0606 | computed; formula and k = 2 in `engine/roles.py`, shown in the app |
| 4 skills, 15 daily tasks, 7.5 hours, free resources | 450 minutes at 5 hours a week | computed; `data/resources.json`; wording from `sdg_headline` in `docs/pathway.md` |
| Progress 10% after one tick | 45 of 450 minutes | computed (task T001 is 45 minutes) |
| SDG 4.4 for skills, SDG 8.5 for work | plan-level SDG lines | `docs/pathway.md`, section "SDG summary" |
| Python 26.3%, band 22.1% to 30.9% | 0.2627, 0.2211, 0.3089 | `data/skill_scores.json`, Python, `forecast.moderate` |
| As of 2023-12: 20.2%, band 16.1% to 25.0%; real value 18.0% (December 2024) | 0.2018, 0.1609, 0.2499; actual 0.1798, place "inside" | computed with `build_scores(as_of="2023-12")` and `engine.outcome.band_verdict` on `data/demand_monthly.csv` |
| naive3 1.66; last month 1.81; trend lines 2.13 and 2.27 | test MAE at 12 months, in pp: 1.6613, 1.8059, 2.1279 (drift), 2.2662 (damped) | `data/backtest.json`, `models.*.test_mae_pp.h12` |
| Gradient boosting 2.06 | 2.064 | `data/ml_backtest.json`, `mae_table_h12_pp.test`; `docs/ml-forecaster.md` |
| 616 held-out forecasts | 616 skill-origin pairs | `data/backtest.json`, `n_skill_origin_pairs.test` |
| Band covered 93.8%; 80% target | 0.9383; level 0.8 | `data/backtest.json`, `coverage.test_h12` |
| Errors of the last 24 past forecasts | `window_origins` 24 | `data/backtest.json`, `interval` |
| Label right 67.2% | 0.6722 (720 labelled cases) | `data/backtest.json`, `trend_label_backtest` |
| Language holds up; five contested | `robust_categories` ["language"]; 5 contested | `data/exposure_agreement.json`; `docs/exposure-crosscheck.md` |
| 26 of 40 skills contested | 26 rows with `stance_robust` false | `data/exposure_robustness.csv` |
| Rank correlation minus 0.79 | -0.7857 (Microsoft vs AEI, 8 occupations) | `data/exposure_agreement.json`, `occupation_level.spearman_vs_aei` |
| k cannot be pinned down | verdict text; k per 12 months 1.8 (-1.0 to 2.9) | `data/k_estimate.json`, `verdict`, `headline` |
| MCP 1.5% up from 0.3% | 0.01454 and 0.002555 | `data/skill_candidates.json` |
| 40 skills, 48,508 posts (94 threads) | counts | `data/taxonomy.json`; `data/hn_threads.csv` (94 rows); `data/demand_monthly.csv` |
| 2,569 single-role posts | sum over ranked roles, 2024-11 to 2026-10 | `data/role_profiles.json` (the app prints the same total) |
| Forecast, role match and pathway use no language model | app text "No LLM is used in this view" (this text must be re-checked, see open item 2) | `app.py` |
| Only CV intake uses a language model; it points, code checks every quote | design: one Claude call, every quote checked word for word | `docs/skill-profile-intake-architecture.md`, `backend/signals/intake/llm_extract.py` |
| HN is US and startup heavy; JobStreet needs a partnership | stated limits | `docs/build-plan.md` (risks table, Step 8 status) |

## Open items for the team

1. **AI-share numbers.** The script uses 6.4% (January 2019) and 54.6% (September 2026, the last full month) from `data/ai_context_monthly.csv`. `docs/build-plan.md` now states its 12-month pooled figures and says so. The deck (slide 2) and the proposal use the same two values.
2. **Claude Haiku.** The script says that only the CV intake uses a language model (Claude Haiku 4.5 through Replit AI Integrations, a design not yet verified on the live app). The tech declaration says the same. Check that the `app.py` text "No LLM is used in this view" is still true for the view you show. Do not demo the CV page live unless you have tested it on the deployed app first.
3. **Refresh changes the data.** The "Refresh live data" button also publishes to the shared store (`live.publish`) once App Storage is set up (Replit setup pending), so judges may then see the refreshed numbers. After any refresh, check every number in the table above before you record.
4. **Live site version.** Confirm the Replit deployment runs the merged `main` (PRs #1 to #7). The older build showed sample data.
5. **Who explains what.** Sheng Kuan speaks rows 5 and 8, which cover the forecast tests that Ee Zhan built. Both members should read `docs/ml-forecaster.md` and the backtest section of `docs/build-plan.md` before recording. Judges may ask either of you about any row.
