# Verity: judge Q&A prep sheet (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1. Branch `docs/submission`.
The final round gives 5 minutes of Q&A after a 10-minute pitch. Any member may be asked about any part, so both of you must be able to give every answer below in your own words.

How to use this sheet:

- Each answer has 3 sentences or fewer. Say it, then stop. Offer the file if the judge wants more.
- Each answer ends with the file or number it relies on. Paths are relative to the repo root.
- If you do not know, say "We did not test that" and name the file where the nearest result sits. Never guess a number.
- Items in [TEAM TO FILL] need a fact only the team has.

## Numbers to know cold

| Number | Meaning | File |
|---|---|---|
| 1.66, 1.81, 2.13, 2.27 | 12-month test error in percentage points: naive3, naive, drift, damped | `data/backtest.json` |
| 2.06 | Gradient boosting error on the same 616 skill-origin pairs | `data/ml_backtest.json` |
| 93.8% against 80% | Share of real values inside the band at 12 months | `data/backtest.json` |
| 67.2% (720 cases) | Rising or Falling label pointed the right way for the next 12 months | `data/backtest.json` |
| 94 threads, 48,508 posts | Hacker News "Who is hiring?" data, 2019-01 to 2026-10 | `data/hn_threads.csv`, `data/demand_monthly.csv` |
| 40 skills: 27 ok, 8 low volume, 5 rare | Data-volume status | `data/skill_scores.json` |
| 2,569 posts | Single-role posts behind the role profiles | `data/role_profiles.json` |
| 1 robust, 5 contested categories; 26 of 40 skills contested | Exposure cross-check | `data/exposure_robustness.csv` |
| -0.79 | Rank correlation of Microsoft's index with the Anthropic index | `data/exposure_agreement.json` |
| k = 2 (assumed); data says 1.8 per 12 months, 95% interval -1.0 to 2.9 | Fast scenario strength | `data/k_estimate.json` |
| 77 resources | Link-checked (HTTP 200 on 22 Oct 2026): 76 free, 1 free trial | `data/resources.json` |
| 3 of 15 | Radar hits at 2023-06 (base rate 0.30) | `docs/skill-discovery.md` |
| Over 700 | Automated tests that passed on 22 Oct | `docs/build-plan.md` |

## Innovation and Creativity (30%)

**1. Isn't this just a chatbot? Where is the AI?**
No. Verity has no chatbot, and the running app calls no language model, because a language model can invent numbers and the brief forbids invented statistics. The AI is statistical learning: role profiles learned from 2,569 single-role posts, forecasts with tested bands, and a gradient-boosting model we trained and then rejected. Language models appear only in planned or unmerged work: CV extraction with Claude Haiku, and Sheng Kuan's AI-news ranker on the branch `AI-trend-signal-layer`.
Relies on: `app.py` ("No LLM is used in this view"); `docs/ml-forecaster.md`; `docs/build-plan.md` item S1; `docs/submission/tech-declaration.md`.

**2. Why trust a forecast that is basically "no change"?**
We tested the alternatives and "no change" won: over 616 held-out forecasts, naive3 had 1.66 points of error, trend lines had 2.13 and 2.27, and gradient boosting had 2.06. So the app shows a level with a band that held 93.8% of real values, plus an observed trend label that pointed the right way 67.2% of the time. We make no claim of a precise future, and the user decides.
Relies on: `data/backtest.json` (`models`, `coverage`, `trend_label_backtest`); `data/ml_backtest.json`.

**3. Why did ML lose?**
Twelve months out, job demand is close to no change, and we have about 25 usable skills and a few dozen independent months, so a flexible model learns patterns that do not repeat. Its error was 0.98 points on its training data and 2.06 on new data, against 1.66 for naive3, and the 95% interval of the gap (-0.62 to -0.21) excludes zero. We kept the experiment as evidence and left production unchanged.
Relies on: `docs/ml-forecaster.md`; `data/ml_backtest.json` (`mae_table_h12_pp`, `feature_importance`).

**4. Your exposure index disagrees with others. Which is right?**
We do not know, and the app says so. The Anthropic-based stance has a rank correlation of -0.79 with Microsoft's index across eight occupations, and no correlation with the two capability indices. Only the language category (14 skills) holds up, so 26 of 40 skills carry a "contested" tag and we left the stance values unchanged.
Relies on: `docs/exposure-crosscheck.md`; `data/exposure_agreement.json`; `data/exposure_robustness.csv`.

**5. What is new compared with existing job sites and skill tools?**
We did not benchmark named products, so we make no claim against them. What we can show: every forecast has a band that was tested (93.8% coverage), the app reports where it loses (the ML test, the weak radar), and it displays disagreement between exposure indices. The pathway also adds a daily to-do list with deadlines, progress ticks and a calendar export.
Relies on: `data/backtest.json`; `docs/exposure-crosscheck.md`; `docs/pathway.md`.

**6. Does the new-skills radar work?**
Not well, and the app says so. At 2023-06, 3 of its top 15 terms kept growing (0.20, 95% interval 0.07 to 0.45), against a base rate of 0.30 for all candidates. We use it to surface terms for a person to review, such as MCP (1.5% of posts, up from 0.3%), and it never adds a skill itself.
Relies on: `docs/skill-discovery.md` (Backtest); `data/skill_candidates.json`.

**7. What is the Fast scenario, and why does it not reorder the roles?**
Fast equals Moderate times (1 minus k times e), where e is how far a skill's AI automation share sits above the average and k is 2. Because k is an assumption, the Roles tab only adds an estimate of demand change (about -6.1% for Backend Engineer) and never changes the ranking. On the Pathway tab it moves future-bet skills to second place and changes nothing else.
Relies on: `docs/build-plan.md` P9; `docs/pathway.md` (Order of stages); the "How the rank is computed" panel in `app.py`.

## Problem-Solution Fit (25%)

**8. Hacker News is US data. How is this Malaysian?**
It is not Malaysian data, and the limits slide says so. Hacker News gives a free, dated, monthly series back to 2019 with citable thread links, and skills such as Python or Kubernetes are global. A Malaysian source is next: JobStreet blocked us with a Cloudflare challenge and needs a data partnership, and the build plan lists DOSM and MyCOL as future work.
Relies on: `docs/build-plan.md` (status table, risks); `data/SOURCES.md`.

**9. Who is the user, and did you test with real users?**
The user is a junior or mid-level tech developer in Malaysia, such as a fresh graduate or a career switcher, and we built three synthetic personas (Aina, Ben, Chloe). We have not tested with real users yet. User testing is the first next step.
Relies on: `docs/build-plan.md` section 1; `app.py` (`PERSONAS`); `BRIEF.md` (data rules).

**10. How do you avoid inventing courses or jobs?**
Courses come only from `data/resources.json`: 77 resources, link-checked (HTTP 200 on 22 Oct 2026): 76 free, 1 free trial. Only entries that returned HTTP 200 stay; a skill with no usable resource shows a placeholder note and gets no tasks. We list roles, not vacancies: 9 roles whose skill weights are counted from real Hacker News posts. A test checks that every chosen resource URL exists in the resource file.
Relies on: `docs/pathway.md` (The "no invented courses" rule); `data/role_profiles.json`.

**11. How would you scale beyond tech?**
The engine needs three inputs: a dated public job-post source, a skill list with match patterns (`data/taxonomy.json`), and an exposure score per occupation. We started with tech because Hacker News gives the best free dated data, and we have not tested another field. A new field needs its own source and its own backtest before the app shows any forecast.
Relies on: `docs/build-plan.md` section 1; `data/taxonomy.json`.

**12. What is the SDG impact, and how do you measure it?**
Each plan carries two SDG lines: SDG 4.4 (skills added, hours, cost) and SDG 8.5 (movement toward a role, with its demand trend), and each skill has a tag with a one-line reason. We have not measured learner outcomes, so these numbers describe the plan and not an effect. The baseline and the KPI target are in the proposal's SDG table. [TEAM TO FILL: confirm they match `docs/submission/preliminary-proposal.md`]
Relies on: `docs/pathway.md` (SDG summary); `data/taxonomy.json`.

**13. How does Verity support human judgement?**
The user picks the profile, edits the skills, chooses the target role and sets the pace, and every screen says "Estimates, not facts. You decide." A person must approve any new skill from the radar. Code sets the plan order by stated rules, so a language model cannot change the order or the numbers.
Relies on: `app.py`; `docs/skill-discovery.md`; `docs/pathway.md`.

## Feasibility of Build (25%)

**14. Why is the k = 2 assumption OK?**
It is a labelled assumption, not a finding. We tried to measure k: the best estimate is 1.8 per 12 months, with a 95% interval of -1.0 to 2.9, so 2 is inside it and so is 0. The slope changes sign when the AI/ML category is left out, so the data cannot pin k down, and the app shows the Fast shift next to the band width (for Python, -1.1 points against a band 8.8 points wide).
Relies on: `data/k_estimate.json` (`headline`, `verdict`); `docs/exposure-crosscheck.md` Part B; `data/skill_scores.json` (Python).

**15. What happens if a source goes down?**
Refresh keeps the last good data and shows its date with the error, for example "The last good data is shown: data as of ...". If the Replit disk is read-only, the refresh works in a temporary folder, and the committed files are a full fallback. For the final round we also upload a backup pitch video. The daily scheduled refresh is code merged; its Replit setup is pending.
Relies on: `docs/build-plan.md` P10; `app.py` (`show_refresh_result`); `docs/replit-schedule.md`; `BRIEF.md` (final deliverables).

**16. Privacy and PDPA?**
The app collects no personal data: the three profiles are synthetic and it has no sign-in. We commit only counts and thread links; raw post text stays in gitignored folders on our machines and, during a refresh, in a temporary folder on the Replit server. Tests check that no committed data file holds an email address and that radar output holds no author names. When CV upload arrives, we need a PDPA assessment and a retention rule. [TEAM TO FILL: retention rule]
Relies on: `docs/submission/tech-declaration.md` section 6.1; `docs/build-plan.md` P2 and P12; `docs/skill-discovery.md`.

**17. What is your hardest technical risk, and what is the fallback?**
The hardest risk is forecast skill: 12-month demand is close to no change, and 13 of 40 skills have too few posts. The fallback is built in: 8 low-volume skills show observed counts and a trend label, 5 rare skills show counts only, and neither group gets a forecast. A failed data source or a failed live demo falls back to the last good data and the backup video.
Relies on: `data/skill_scores.json` (`status`); `docs/build-plan.md` P8.

**18. What is built, and what is only planned?**
Built and merged: forecast, bands, trend labels, scenarios, as-of view, role match, pathway with exports, live refresh, exposure cross-check, k estimate and the radar, with over 700 tests passing on 22 Oct. Not in the app: CV upload (the app takes a profile and a skill picker), the AI-news feed (Sheng Kuan's ranker sits on an unmerged branch), JobStreet data, and a full "what changed" diff (Refresh lists changed skills only). Claude Haiku for CV extraction is planned and not built.
Relies on: `docs/build-plan.md` (status table, 22 Oct).

**19. What is the stack, which model, and where is Replit?**
Python and Streamlit 1.66.1 on a Replit Autoscale deployment, with pandas 3.0.6, numpy 2.5.4, scipy 1.18.1 and statsmodels 0.15.0. The app calls no language model and uses no GPU, so there is no RunPod use; the organisers confirmed on 22 Oct that RunPod proof is not needed. Claude Code is declared as a major development tool.
Relies on: `requirements.txt`; `docs/submission/tech-declaration.md`; `BRIEF.md` (answered 22 Oct).

**20. How do you know the code is correct?**
Over 700 automated tests passed on 22 Oct, including tests that the future cannot leak into a past forecast. The ML experiment has its own leak test: scrambling every month after the origin left the prediction unchanged at 3 test origins. The build plan requires a stronger-model review of each major part before it merges, and the merged work sits in pull requests #1 to #7.
Relies on: `docs/build-plan.md`; `data/ml_backtest.json` (`leak_test`).

## Clarity of Proposal and integrity (20%)

**21. Is this AI plagiarism? Explain the conformal band.**
Claude Code wrote much of the code from our prompts and plans, and we declared it as a major tool; the choices are ours and recorded: keep naive3, label k an assumption, show disagreement. The band in plain words: every past forecast has a known error, so we take the last 24 errors, scaled by how noisy the skill is, find their 80th percentile, and add and subtract it around the forecast, using only errors known before the forecast date. It held 93.8% of real values in the held-out test. [TEAM TO CONFIRM: each of you can explain this without notes]
Relies on: `docs/submission/tech-declaration.md` section 4.3; `data/backtest.json` (`interval`, `coverage`); `docs/build-plan.md` P6.

**22. What did each member build?**
The git log shows 42 commits on `main`: 40 from Ee Zhan's GitHub account (TayEeZhan, under the names greenrobot8888 and Tay Ee Zhan), covering the engine, the app, role match, pathway, the ML experiment, the exposure cross-check and the radar, plus 2 setup commits from Replit Agent. Sheng Kuan's 11 commits (22 Oct, as GOH SHENG KUAN) are on the branch `origin/AI-trend-signal-layer`: AI-news collectors, story clustering, a ranker and a web feed; they are not merged and not connected to the app. [TEAM TO FILL: Sheng Kuan's other parts, such as `data/resources.json`, document drafts and the CV plan]
Relies on: `git log --format="%an %s"` and `git log --all` in the repo; `docs/build-plan.md` (who does what).
Prepare for this follow-up: six of the 11 branch commits share one timestamp (22 Oct 13:13) and the branch adds about 9,400 lines. The organisers say one big late commit can disqualify a final-round repo, so be ready to say when and how that code was written, and declare any part that pre-dates the build clock (19 Oct, 8 PM MYT). [TEAM TO FILL]

**23. Explain the Rising or Falling label in plain words.**
We compare the monthly share of posts that mention a skill over the last 12 months with the 12 months before, using a Welch t-test on the logit of the share. A skill gets Rising or Falling only when p is below 0.05 and it has at least 30 mentions in 24 months; otherwise it shows "No clear change". The label describes what already happened, and it pointed the right way for the next 12 months 67.2% of the time over 720 overlapping cases, which are not 720 independent tests.
Relies on: `docs/build-plan.md` P7; `data/backtest.json` (`trend_label_backtest`).

**24. Explain the match score and the rank.**
Match score is the weight of the role's skills you have divided by the weight of all its skills, and a weight is the share of that role's single-role posts that mention the skill, kept when the role asks for it at least 1.1 times as often as the average post. Rank score is 0.7 times match plus 0.3 times outlook (Rising 1.0, No clear change 0.5, Falling 0.0), and the team chose 0.7 and 0.3 without fitting them to data. A role under 20% match is not ranked, so it cannot rank on outlook alone.
Relies on: the "How the rank is computed" panel in `app.py`; `data/role_profiles.json`; `data/role_trends.json`.

**25. Your band covered 93.8% against an 80% target. Is it useless?**
It is wider than it needs to be, and the Method tab says "a coverage above the target means the band is wide, not tight". The mean width at 12 months is 8.4 points. The window of 24 forecasts was set in advance, and windows of 36 forecasts or all history gave 92.9% and 91.9%, so one choice does not cause the over-coverage; the first fixed-width band covered only 65.9%, so we prefer to err wide.
Relies on: `data/backtest.json` (`coverage`, `interval_sensitivity`); `docs/build-plan.md` P6.

## Questions to expect that this sheet does not answer

- Cost to run and a business model: nothing in the repo covers it. Say so, and say the app is free to run on Replit within the declared plan. [TEAM TO FILL]
- Why Streamlit and not a mobile app: one Python program reads the engine directly, and Replit is compulsory (`docs/build-plan.md` P11).
- LinkedIn or X data: we did not use them (terms of service and personal data; `docs/build-plan.md` decisions).
