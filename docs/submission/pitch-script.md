# Verity pitch video script (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1.
Branch: `docs/submission`. Updated 24 Oct 2026 for the Varity-only app (the Streamlit demo flow is gone). Status: draft for the team to rehearse and edit. Nothing here is final until both members have read it aloud.

## Timing at a glance

- **Target length: 5:45.** Hard maximum: 7:00. The organisers want 5 to 7 minutes and take 1 point per 30 s over (`C:\Users\eezha\sdc-hackathon\BRIEF.md`). The headroom is 1:15.
- **Speaking split:** Sheng Kuan 176 s, Ee Zhan 169 s.
- **Words:** 583 written words. 685 spoken words once numbers are read aloud ("6.4%" is four words, "54.6%" is five). Average 119 words per minute. Fastest row 135 (row 10). Slowest row 87 (row 7). The aim is 140 or less on every row. All rows pass (see the check below).
- **Layout:** slides only at the start (0:00-0:40) and the end (3:45-5:45). The Varity app fills 0:40-3:45, as the organisers advise: keep the slides generic and focus on the system demo.

## Rules this script follows

1. Every number comes from a file in the repo. The last section maps each number to its file.
2. Aina is synthetic and the script says so (row 1). The app labels her "(synthetic)".
3. Only the CV intake and two optional steps (the route advisor and the pathway coach) use a language model, and the script says so (row 10). The forecast, role match, pathway dates and SDG parts use none. The demo uses "Try an example", which needs no model. Do not demo the CV upload unless you have tested it on the deployed app first. The model only points at skills. Code checks every quote.
4. The script claims no HRD Corp listing and no Malaysian data.
5. No sentence says the forecast predicts a precise future. The script says the simple method won.

## State of the app before the take starts (0:40)

| Item | Setting |
|---|---|
| URL | https://verity--eezhan0805.replit.app. It is live (published 24 Oct 2026). If it is down, record from a local run (`cd backend/signals && python -m trendsignal serve --port 8000`, then http://localhost:8000). Check that the page shows real data and no "offline snapshot" label |
| Screen | CV & routes, with a fresh browser session (no saved profile) |
| AI scenario | Expected (estimate) (API value `moderate`) |
| Example profile | "Aina (synthetic)", under "Try an example" |
| Route | the first route, Backend Engineer, as the current route |
| Pathway | Hours per week 5 (the default) |
| Signals | open once before recording so the live run is loaded |

## Timed script

The screen names are the ones in the Varity navigation: Flow map, CV & routes, Today, Pathway, Signals, Job forecast, Skills radar, Method.

| Time | Who speaks | On screen | Exact spoken words |
|---|---|---|---|
| 0:00-0:40<br>(40 s)<br>**Problem**<br>row 1 | Sheng Kuan | Slide 1 (title) for 5 s, then slide 2 (line chart: share of Hacker News hiring posts that mention AI, 6.4% to 54.6%) until 0:30, then slide 3 (Aina and the Verity chain). | We are Hokkien Mee Is Purple. This is Verity, for Domain 1. The brief asks us to track AI progress, predict skills, match roles and build reskilling paths, linked to SDG 4.3, 4.4, 8.2 and 8.5. AI mentions in Hacker News hiring posts grew from 6.4% in January 2019 to 54.6% in September 2026. Meet Aina, a junior Python developer. She is synthetic; we use no real CVs. |
| 0:40-1:21<br>(41 s)<br>**Demo 1: CV & routes**<br>row 2 | Ee Zhan | Varity, CV & routes screen. Under "Try an example", press Aina (synthetic). Point at card #1 (match 66%, "Strong fit, rising demand", the gap chips) and hover one reason chip to show its source and date. Press "If AI speeds up (estimate)" in the AI scenario switch and point at the estimate note on card #1. Press "Expected (estimate)" again before the cut. | On CV and routes we press Try an example and pick Aina: Python, SQL, PostgreSQL, Docker and AWS. Code ranks the routes: seventy percent match, thirty percent demand. Backend Engineer ranks first, at 66%. She lacks Go, Kubernetes, Terraform and Node.js. Every reason is a chip with a source and a date. Flip to "If AI speeds up": the card adds an estimate, Backend demand about 6.1% lower. The order stays the same. |
| 1:21-2:05<br>(44 s)<br>**Demo 2: Pathway and Today**<br>row 3 | Sheng Kuan | Keep Backend Engineer as the route. Open Pathway. Hold on the route map and hover the stations for Node.js, Go, Kubernetes and Terraform to show the reason for each. Scroll to the SDG lines. Open Today and hold on "Next stops". | Aina keeps that route, and the Pathway screen turns her gaps into a plan. Stage one is no-regret: Node.js, which more than one of her roles needs. Stage two is near-term demand: Go and Kubernetes. Stage three is a future bet: Terraform, which is Rising. The plan has 4 skills, 15 daily tasks and 7.5 hours, all with free resources. Today lists her next stops, ready for today. The SDG lines name SDG 4.4 for skills and SDG 8.5 for work. |
| 2:05-2:20<br>(15 s)<br>**Demo 3: Skills radar**<br>row 4a | Ee Zhan | Open Skills radar. Select the Python dot (or its table row). Hold on the detail panel: share now, trend label, AI stance, 12-month estimate with its band. | Skills radar, Python. Its panel shows the share now, the trend label and the 12-month estimate: 26.3%, band 22.1% to 30.9%. |
| 2:20-2:44<br>(24 s)<br>**Demo 4: Job forecast**<br>row 4b | Ee Zhan | Open Job forecast. Hold on the Backend Engineer row: share now, the 12-month bar and band, and the line "393 posts ... vs 366". Point at the note that the forecast is a share of HN posts, not a count of jobs. | Job forecast. Backend Engineer is Rising: 10.6% of hiring posts in the last 12 months, up from 9.4%. The 12-month estimate is 10.4%, band 8.3% to 12.9%. It is a share of posts, not a count of jobs. |
| 2:44-3:09<br>(25 s)<br>**Demo 5a: Method, backtest**<br>row 5 | Sheng Kuan | Open Method. Hold on the model table of "How good is the skill forecast?" (naive3 row), then scroll to "Band coverage" (93.8%) and "Trend label hit rate" (67.2%). | The Method screen shows our scores. The three-month average, naive3, has the lowest 12-month error: 1.66 percentage points. The 80% band covered 93.8% of real values. The Rising or Falling label pointed the right way 67.2% of the time. |
| 3:09-3:34<br>(25 s)<br>**Demo 5b: Method, exposure and k**<br>row 6 | Ee Zhan | Scroll to "AI exposure": the cross-check table, then the contested/robust lines. Scroll to "The size of the AI effect (k)" with its "assumption" tag. | The exposure cross-check compares our AI stance with three other indices. The language category alone holds up; five are contested, and the app says so. The k line is tagged as an assumption, and the data cannot pin it down. |
| 3:34-3:45<br>(11 s)<br>**Demo 6: Signals**<br>row 7 | Ee Zhan | Open Signals. Hold on the top of the ranked list and one rank's reasons. Do not read the story titles aloud: they change with each run. | Last, Signals ranks AI news by a fixed formula, each rank with its reasons and sources. |
| 3:45-4:32<br>(47 s)<br>**Trust: tests and band**<br>row 8 | Sheng Kuan | Slide 4 (how it works: one-line block diagram) for 10 s, then slide 5 (bar chart of 12-month error: naive3 1.66, naive 1.81, gradient boosting 2.06, drift 2.13, damped 2.27; callout 93.8% vs 80%). | Verity tags 40 skills across 48,508 hiring posts. Over 616 held-out forecasts, 12 months ahead, the three-month average had 1.66 percentage points of error. Last month alone had 1.81. Trend lines had 2.13 and 2.27. Gradient boosting had 2.06. The simple method won, so Verity shows a band and makes no promise. The band uses the errors of the last 24 past forecasts, a conformal method. It covered 93.8%, against an 80% target. |
| 4:32-5:00<br>(28 s)<br>**Trust: profiles and disagreement**<br>row 9 | Ee Zhan | Slide 6 (left: 2,569 single-role posts feed the role profiles; right: exposure table summary, 1 robust category, 5 contested, rank correlation -0.79). | Role profiles are learned from 2,569 Hacker News posts that name a single role. Code sets the plan order. Only the language category holds up across the indices, so 26 of our 40 skills carry a contested tag. Microsoft's index even ranks occupations almost opposite to ours: minus 0.79. |
| 5:00-5:20<br>(20 s)<br>**Limits and next steps**<br>row 10 | Sheng Kuan | Slide 7 (four short bullets: US and startup-heavy data; JobStreet needs a data partnership; CV intake, advisor and coach: the model points, code checks every answer; HRD Corp status unverified). | Limits. Hacker News is US and startup heavy, so this is not Malaysian data. JobStreet needs a data partnership. Only CV intake and two optional steps, advisor and coach, use a language model; code checks every answer. We could not verify HRD Corp status. |
| 5:20-5:45<br>(25 s)<br>**SDG close**<br>row 11 | Ee Zhan | Slide 8 (SDG 4.4, 8.2, 8.5 icons, team name, repo and app URL). | Verity serves SDG 4.4, skills for employment, and SDG 8.5, productive work, with free resources and a dated source for every skill. The app says: Estimates, not facts. You decide. We are Hokkien Mee Is Purple. Thank you. |

Row 11 includes a 5 s end card (team name, repo link, app link) after the last word.

## Words per minute check

Spoken words count every number as spoken ("1.66" is four words: one point six six). "naive3" counts as two.

| Row | Time | Who | Seconds | Written words | Spoken words | Words per minute | Check (140 or less) |
|---|---|---|---|---|---|---|---|
| 1 | 0:00-0:40 | Sheng Kuan | 40 | 68 | 84 | 126 | ok |
| 2 | 0:40-1:21 | Ee Zhan | 41 | 72 | 77 | 113 | ok |
| 3 | 1:21-2:05 | Sheng Kuan | 44 | 84 | 90 | 123 | ok |
| 4a | 2:05-2:20 | Ee Zhan | 15 | 21 | 30 | 120 | ok |
| 4b | 2:20-2:44 | Ee Zhan | 24 | 38 | 53 | 132 | ok |
| 5 | 2:44-3:09 | Sheng Kuan | 25 | 39 | 49 | 118 | ok |
| 6 | 3:09-3:34 | Ee Zhan | 25 | 40 | 40 | 96 | ok |
| 7 | 3:34-3:45 | Ee Zhan | 11 | 16 | 16 | 87 | ok |
| 8 | 3:45-4:32 | Sheng Kuan | 47 | 73 | 101 | 129 | ok |
| 9 | 4:32-5:00 | Ee Zhan | 28 | 49 | 58 | 124 | ok |
| 10 | 5:00-5:20 | Sheng Kuan | 20 | 45 | 45 | 135 | ok |
| 11 | 5:20-5:45 | Ee Zhan | 25 | 38 | 42 | 101 | ok |
| **All** | 0:00-5:45 | both | 345 | 583 | 685 | 119 | ok |

The demo rows (2 to 7) need pauses for clicks and page loads, so their rates are the real limit. If a row feels rushed in rehearsal, use the cut list and keep the voice at the same pace.

## Cut list (if the take runs long)

Drop lines in this order. Seconds use a rate of 125 words per minute. Make the cuts in the script before recording, so the voice stays calm.

| Priority | Row | Line to drop | Spoken words | Saves | Total saved | What stays |
|---|---|---|---|---|---|---|
| 1 | 4b | "It is a share of posts, not a count of jobs." | 10 | 5 s | 5 s | The screen note says it. Say it in Q&A if asked. |
| 2 | 8 | "Verity tags 40 skills across 48,508 hiring posts." | 13 | 6 s | 11 s | Slide 4 still shows it. |
| 3 | 3 | "Today lists her next stops, ready for today." | 11 | 5 s | 16 s | No click needed. |
| 4 | 2 | "Every reason is a chip with a source and a date." | 11 | 5 s | 21 s | The chips stay on screen, with the source in the tooltip. |
| 5 | 8 | "Last month alone had 1.81." | 8 | 4 s | 25 s | Keep 1.66, 2.13, 2.27 and 2.06. |
| 6 | 9 | "Role profiles are learned from 2,569 Hacker News posts that name a single role. Code sets the plan order." | 24 | 12 s | 37 s | Q&A covers it. |
| 7 | 4a | "Its panel shows the share now, the trend label and the 12-month estimate: 26.3%, band 22.1% to 30.9%." | 26 | 12 s | 49 s | Say only "Skills radar, Python." |
| 8 | 1 | "The brief asks us to track AI progress, predict skills, match roles and build reskilling paths, linked to SDG 4.3, 4.4, 8.2 and 8.5." | 32 | 15 s | 64 s | Judges know the brief. Last resort. |

Stopwatch checkpoints during a take: row 2 starts at 0:40, row 8 starts at 3:45, row 11 starts at 5:20. If row 8 starts after 4:05, apply cuts 1 to 4 at once. If the finished video is over 7:00, cut demo lines. Keep the Limits row (row 10).

## Where each number comes from

All files are in the repository. "Computed" means `advisor.service.suggestions` and `advisor.service.pathway` (the functions behind `GET /api/roles/suggestions` and `GET /api/pathway`) ran with the language model switched off, for the example profile Aina, on 24 Oct 2026. The app must show the same values. If it does not, trust the screen and fix the script.

| Spoken | Value | Source |
|---|---|---|
| SDG 4.3, 4.4, 8.2, 8.5 | the four targets | `C:\Users\eezha\sdc-hackathon\BRIEF.md`, Domain 1 |
| AI mentions 6.4% to 54.6% | 49 of 765 posts (2019-01); 136 of 249 posts (2026-09) | `data/ai_context_monthly.csv`. September 2026 is the last full month. October 2026 (138 of 266, 51.9%) is partial, so the script does not use it |
| Aina's skills | Python, SQL, PostgreSQL, Docker, AWS | `data/example_profiles.json` |
| Backend Engineer first, 66%; gaps Go, Kubernetes, Terraform, Node.js; "Strong fit, rising demand" | match 0.66; rank = 0.7 match + 0.3 outlook | computed; profile from `data/role_profiles.json`; formula in `engine/roles.py` |
| Job forecast: Backend Engineer Rising, 10.6% up from 9.4%; 12-month estimate 10.4%, band 8.3% to 12.9% | 393 of 3,714 posts vs 366 of 3,914 posts; value_12m 0.1038, low 0.0828, high 0.1293 | `data/role_forecast.json`, `backend_engineer` (trend and forecast_moderate) |
| If AI speeds up: Backend demand about 6.1% lower | `fastShift` -0.0606 | computed; formula and k = 2 in `engine/roles.py`; the card note says "If AI speeds up (estimate)" |
| 4 skills, 15 daily tasks, 7.5 hours, free resources | 450 minutes at 5 hours a week | computed; `data/resources.json`; wording from `sdg_headline` in `docs/pathway.md` |
| SDG 4.4 for skills, SDG 8.5 for work | plan-level SDG lines | `sdgSummary` of the computed pathway; `docs/pathway.md`, section "SDG summary". Check the wording on the Pathway screen |
| Python 26.3%, band 22.1% to 30.9% | 0.2627, 0.2211, 0.3089 | `data/skill_scores.json`, Python, `forecast.moderate`; shown on the Skills radar detail panel |
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
| 40 skills, 48,508 posts (94 threads) | counts | `data/taxonomy.json`; `data/hn_threads.csv` (94 rows); `data/demand_monthly.csv` |
| 2,569 single-role posts | sum over ranked roles, 2024-11 to 2026-10 | `data/role_profiles.json` (the app prints the same total) |
| Forecast, role match scores and pathway dates use no language model | scores and dates come from code; the optional advisor moves a role at most 2 places and writes one checked summary line; the optional coach re-orders steps within a stage, picks among listed resources and writes one checked "why" line | `engine/roles.py`, `engine/pathway.py`, `backend/signals/advisor/llm.py` (prompt rule "at most 2 places") |
| CV intake (and the optional advisor and coach) are the only language-model uses; it points, code checks every quote | design: one Claude call, every quote checked word for word | `docs/skill-profile-intake-architecture.md`, `backend/signals/intake/llm_extract.py` |
| HN is US and startup heavy; JobStreet needs a partnership | stated limits | `docs/build-plan.md` (risks table, Step 8 status) |

## Open items for the team

1. **AI-share numbers.** The script uses 6.4% (January 2019) and 54.6% (September 2026, the last full month) from `data/ai_context_monthly.csv`. `docs/build-plan.md` states its 12-month pooled figures and says so. The deck (slide 2) and the proposal use the same two values.
2. **Claude Haiku.** The script says that only the CV intake and two optional steps (route advisor, pathway coach) use a language model (Claude Haiku 5.5 through the team's Anthropic API key; the route advisor is confirmed live, the CV-intake call is not yet). The tech declaration says the same. Demo "Try an example", which needs no model. Do not demo the CV upload unless you have tested it on the deployed app first.
3. **Data does not change in the app.** The Skills radar has a "Fetch latest HN" button. Do not click it while recording. The Hacker News data is the committed snapshot (as of 2026-10), so the numbers in the table above change only after a fetch, the daily refresh or a re-run of the engine. Signals is different: it is re-ranked while the server runs, so never read its story titles or ranks aloud.
4. **Live site version.** The Replit deployment is live (published 24 Oct 2026). Check every number in the table above on the live URL before you record.
5. **Rows rewritten on 24 Oct.** Rows 2, 3, 4a, 4b, 5, 6 and 7 were rewritten for the Varity screens. The old as-of slider, skill detail, candidate-skills radar and Refresh steps no longer exist in the app. Rehearse the new rows against the running app: the screen text in the "On screen" column is from the code, not from a recording.
6. **Who explains what.** Sheng Kuan speaks rows 5 and 8, which cover the forecast tests that Ee Zhan built. Both members should read `docs/ml-forecaster.md` and the backtest section of `docs/build-plan.md` before recording. Judges may ask either of you about any row.
7. **Destination (new, 24 Oct, branch `feat/dream-job-destination`).** The CV review step has an optional "Destination" select; the chosen role is pinned first in the planner with a DESTINATION plate (a low-match one gets a "Long ride" note). Mentor feedback: pitch Varity as "tell us the job you want; we show how close you are and the fastest way there". It is **not** in rows 2-3 yet: "Try an example" skips the review step, so the select never shows on the scripted path. To show it, either demo the sample CV ("Use the synthetic sample CV", which goes through review; test it on the deployed app first, see item 2), or add one spoken line to row 2 and take the matching cut from the cut list: "Aina can name the job she wants; Varity pins it first and shows how far it is." Re-run the words-per-minute check for row 2 after any change.
