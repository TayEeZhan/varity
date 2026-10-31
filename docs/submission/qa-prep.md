# Verity: judge Q&A prep sheet (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1. Branch `docs/submission`. Updated 24 Oct 2026 for the Varity-only app (Streamlit is retired).
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
| 2,580 posts | Single-role posts behind the role profiles | `data/role_profiles.json` |
| 1 robust, 5 contested categories; 26 of 40 skills contested | Exposure cross-check | `data/exposure_robustness.csv` |
| -0.79 | Rank correlation of Microsoft's index with the Anthropic index | `data/exposure_agreement.json` |
| k = 2 (assumed); data says 1.8 per 12 months, 95% interval -1.0 to 2.9 | "If AI speeds up" scenario strength | `data/k_estimate.json` |
| 77 resources | Link-checked (HTTP 200 on 22 Oct 2026): 76 free, 1 free trial | `data/resources.json` |
| 3 of 15 | New-skills radar hits at 2023-06 (base rate 0.30). The radar is in the engine only, not in the app | `docs/skill-discovery.md` |
| 1,332 | Automated tests collected on 31 Oct 2026: 868 in the root suite and 464 in `backend/signals/`. Collected, not a full pass run. | `pytest --collect-only` |

## Innovation and Creativity (30%)

**1. Isn't this just a chatbot? Where is the AI?**
No. Verity has no chatbot. The forecast, role match numbers, pathway dates and SDG parts use no language model, because a language model can invent numbers and the brief forbids invented statistics. The AI there is statistical learning: role profiles learned from 2,580 single-role posts, forecasts with tested bands, and a gradient-boosting model we trained and then rejected. Language models appear in the CV intake, where Claude Haiku 5.5 only points at skill mentions and code checks every quote (see #26), in an optional route advisor that moves a role at most 2 places and writes one checked summary line, and in an optional pathway coach that re-orders steps within a stage, picks among listed resources and writes one checked "why" line. Code checks all of it and takes over when the model is off. Optional Claude use in Sheng Kuan's signal ranker is off by default.
Relies on: `backend/signals/advisor/llm.py` (the "at most 2 places" rule); `docs/ml-forecaster.md`; `docs/skill-profile-intake-architecture.md`; `docs/submission/tech-declaration.md` section 4.1.

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
We did not benchmark named products, so we make no claim against them. What we can show: every forecast has a band that was tested (93.8% coverage), the Method screen reports where the method is weak (band coverage above target, contested exposure stances), and it displays disagreement between exposure indices. The pathway also adds a Today list of dated stops with ticks, and a calendar export.
Relies on: `data/backtest.json`; `docs/exposure-crosscheck.md`; `docs/pathway.md`.

**6. Does the new-skills radar work?**
Not well, and we removed it from the app with the Streamlit version. At 2023-06, 3 of its top 15 terms kept growing (0.20, 95% interval 0.07 to 0.45), against a base rate of 0.30 for all candidates. `engine/discover.py` stays as a tool to surface terms for a person to review, and it never adds a skill itself.
Relies on: `docs/skill-discovery.md` (Backtest); `data/skill_candidates.json`.

**7. What is the "If AI speeds up" scenario, and why does it not reorder the roles?**
On screen the two scenarios are "Expected (estimate)" and "If AI speeds up (estimate)". The API values are `moderate` and `fast`. "If AI speeds up" equals Expected times (1 minus k times e), where e is how far a skill's AI automation share sits above the average and k is 2. Because k is an assumption, the CV & routes screen only adds an estimate of demand change (about -6.1% for Backend Engineer) and never changes the ranking. On the Pathway screen it moves future-bet skills to second place and changes nothing else.
Relies on: `docs/build-plan.md` P9; `docs/pathway.md` (Order of stages); the route note on the CV & routes screen ("Ranked by the formula").

## Problem-Solution Fit (25%)

**8. Hacker News is US data. How is this Malaysian?**
It is not Malaysian data, and the limits slide says so. Hacker News gives a free, dated, monthly series back to 2019 with citable thread links, and skills such as Python or Kubernetes are global. A Malaysian source is next: JobStreet blocked us with a Cloudflare challenge and needs a data partnership, and the build plan lists DOSM and MyCOL as future work.
Relies on: `docs/build-plan.md` (status table, risks); `data/SOURCES.md`.

**9. Who is the user, and did you test with real users?**
The user is a junior or mid-level tech developer in Malaysia, such as a fresh graduate or a career switcher, and we built three synthetic example profiles (Aina, Ben, Chloe). We have not tested with real users yet. User testing is the first next step.
Relies on: `docs/build-plan.md` section 1; `data/example_profiles.json`; `BRIEF.md` (data rules).

**10. How do you avoid inventing courses or jobs?**
Courses come only from `data/resources.json`: 77 resources, link-checked (HTTP 200 on 22 Oct 2026): 76 free, 1 free trial. Only entries that returned HTTP 200 stay; a skill with no usable resource shows a placeholder note and gets no tasks. We list roles, not vacancies: 9 roles whose skill weights are counted from real Hacker News posts. 8 of them have enough posts to rank, so the Destination list shows 8; Analytics Engineer is left out with the reason "too few posts to learn a profile". A test checks that every chosen resource URL exists in the resource file.
Relies on: `docs/pathway.md` (The "no invented courses" rule); `data/role_profiles.json`.

**10b. Why only 8 destination roles? There are many more jobs.**
The list shows only roles we can forecast and backtest: each needs enough Hacker News posts for a trend, a learned skill profile, and its own projects and certs. A role with a handful of posts would give numbers we cannot defend, so Analytics Engineer is excluded (`data/role_forecast.json`, `excluded_roles`). Adding a role is data work, not code: a title pattern in `data/roles.json`, a post-count check, then its projects and certs.
Relies on: `data/roles.json`; `data/role_forecast.json`; `data/role_backtest.json`.

**11. How would you scale beyond tech?**
The engine needs three inputs: a dated public job-post source, a skill list with match patterns (`data/taxonomy.json`), and an exposure score per occupation. We started with tech because Hacker News gives the best free dated data, and we have not tested another field. A new field needs its own source and its own backtest before the app shows any forecast.
Relies on: `docs/build-plan.md` section 1; `data/taxonomy.json`.

**12. What is the SDG impact, and how do you measure it?**
Each plan carries two SDG lines: SDG 4.4 (skills added, hours, cost) and SDG 8.5 (movement toward a role, with its demand trend), and each skill has a tag with a one-line reason. We have not measured learner outcomes, so these numbers describe the plan and not an effect. The baseline and the KPI target are in the proposal's SDG table. [TEAM TO FILL: confirm they match `docs/submission/preliminary-proposal.md`]
Relies on: `docs/pathway.md` (SDG summary); `data/taxonomy.json`.

**13. How does Verity support human judgement?**
The user picks an example or uploads a CV, ticks which skills to keep, chooses the route and sees every estimate labelled as an estimate. The footer says "Varity supports your judgement; it does not replace it." Code sets the plan order by stated rules, and the optional advisor can move a role at most 2 places among reasons that code wrote.
Relies on: `frontend/index.html` (footer); `docs/pathway.md`; `backend/signals/advisor/llm.py`.

## Feasibility of Build (25%)

**14. Why is the k = 2 assumption OK?**
It is a labelled assumption, not a finding. We tried to measure k: the best estimate is 1.8 per 12 months, with a 95% interval of -1.0 to 2.9, so 2 is inside it and so is 0. The slope changes sign when the AI/ML category is left out, so the data cannot pin k down, and the Skills radar shows the "If AI speeds up" estimate next to the Expected one, both with their bands (for Python, 25.1% against 26.3%).
Relies on: `data/k_estimate.json` (`headline`, `verdict`); `docs/exposure-crosscheck.md` Part B; `data/skill_scores.json` (Python).

**15. What happens if a source goes down?**
The app reads committed files in `data/`, so a failed Hacker News fetch cannot break it. If the server cannot be reached, the page shows a dated offline snapshot and says so. The daily refresh job never changes the stored `latest.json` when it fails, and it is code built with its Replit setup pending. For the final round we also upload a backup pitch video.
Relies on: `frontend/data.js`; `docs/replit-schedule.md`; `docs/architecture.md` section 3.13; `BRIEF.md` (final deliverables).

**16. Privacy and PDPA?**
Sign-in is optional, and the three example profiles are synthetic. A signed-in user's email and name are personal data under the PDPA (question 27). We use synthetic CVs only. CV text goes to Anthropic directly, and code redacts contact details and ID numbers first, but names can remain. We commit only counts and thread links; raw post text stays in gitignored folders on our machines and, during a refresh, in a temporary folder on the Replit server. Tests check that no committed data file holds an email address and that radar output holds no author names. Real CVs would need a PDPA assessment. The retention rule in code: an account with no login for 365 days is deleted, with its profile and cleaned CV text.
Relies on: `docs/submission/tech-declaration.md` section 6.1; `docs/build-plan.md` P2 and P12; `docs/skill-discovery.md`.

**17. What is your hardest technical risk, and what is the fallback?**
The hardest risk is forecast skill: 12-month demand is close to no change, and 13 of 40 skills have too few posts. The fallback is built in: 8 low-volume skills show observed counts and a trend label, 5 rare skills show counts only, and neither group gets a forecast. A failed data source or a failed live demo falls back to the last good data and the backup video.
Relies on: `data/skill_scores.json` (`status`); `docs/build-plan.md` P8.

**18. What is built, and what is only planned?**
In the Varity app: forecast, bands, trend labels, scenarios, role match with reason chips, the pathway with `.md` and `.ics` export, the Job forecast, Skills radar and Method screens, the AI-signal ranker and the CV intake, with 1,332 tests collected on 31 Oct 2026 (868 root, 464 in `backend/signals/`). Built but not yet tested live: optional Replit sign-in. Not built: Google sign-in and Google Tasks, JobStreet data and a full "what changed" diff. Also built: a per-viewer replay of a past month (`?asOf=YYYY-MM`) and a "Fetch latest HN" button (one fetch per 10 minutes for the whole server). Removed with Streamlit: the new-skills radar. The Team (HR) view was built and then removed. The CV intake calls Claude Haiku 5.5 through the Anthropic API. The route advisor was confirmed live on 24 Oct with a synthetic example profile; the CV-intake call is not yet confirmed live. [TEAM TO FILL: update after the first live run]
Relies on: `docs/architecture.md`; `docs/build-plan.md` (status table, 22 Oct).

**19. What is the stack, which model, and where is Replit?**
Python 3.12 with FastAPI and uvicorn, serving a static HTML, CSS and JavaScript front end (no Streamlit), on a Replit Autoscale deployment (2 vCPU / 4 GiB), with optional Replit Auth sign-in and Replit PostgreSQL for accounts, and with pandas 3.0.6, numpy 2.5.4, scipy 1.18.1 and statsmodels 0.15.0. The forecast, role match and pathway dates call no language model. The CV intake, the optional route advisor and the optional pathway coach call Claude Haiku 5.5 (`claude-haiku-5-5`) through a direct Anthropic API key, billed by Anthropic to a team member's account. There are two separate caps of $1 per day, each per server process: one for the CV intake, one for the advisor and coach together. We use no GPU, so there is no RunPod use; the organisers confirmed on 22 Oct that RunPod proof is not needed. Claude Code is declared as a major development tool.
Relies on: `requirements.txt`, `backend/signals/requirements.txt`; `docs/submission/tech-declaration.md`; `BRIEF.md` (answered 22 Oct).

**20. How do you know the code is correct?**
1,332 automated tests were collected on 31 Oct 2026 (868 root, 464 in `backend/signals/`; a full pass run is not yet re-counted), including tests that the future cannot leak into a past forecast. The ML experiment has its own leak test: scrambling every month after the origin left the prediction unchanged at 3 test origins. The build plan requires a stronger-model review of each major part before it merges, and the merged work sits in pull requests #1 to #7.
Relies on: `docs/build-plan.md`; `data/ml_backtest.json` (`leak_test`).

## Clarity of Proposal and integrity (20%)

**21. Is this AI plagiarism? Explain the conformal band.**
Claude Code wrote much of the code from our prompts and plans, and we declared it as a major tool; the choices are ours and recorded: keep naive3, label k an assumption, show disagreement. The band in plain words: every past forecast has a known error, so we take the last 24 errors, scaled by how noisy the skill is, find their 80th percentile, and add and subtract it around the forecast, using only errors known before the forecast date. It held 93.8% of real values in the held-out test. [TEAM TO CONFIRM: each of you can explain this without notes]
Relies on: `docs/submission/tech-declaration.md` section 4.3; `data/backtest.json` (`interval`, `coverage`); `docs/build-plan.md` P6.

**22. What did each member build?**
On 24 Oct, `main` has 59 non-merge commits: 43 from Ee Zhan's GitHub account (TayEeZhan, under the names greenrobot8888 and Tay Ee Zhan), covering the engine, the first Streamlit app (now retired), role match, pathway, the ML experiment, the exposure cross-check and the radar; 14 from Sheng Kuan (GOH SHENG KUAN), covering `backend/signals/` (AI-news collectors, story clustering, a ranker, the CV intake) and the Varity frontend; plus 2 setup commits from Replit Agent. Sheng Kuan's work is merged (PR #16) and is now part of the live Varity app (published 24 Oct 2026). [TEAM TO FILL: Sheng Kuan's other parts, such as `data/resources.json`, document drafts and the CV plan]
Relies on: `git log --format="%an %s"` and `git log --all` in the repo; `docs/build-plan.md` (who does what).
Prepare for this follow-up: six of the 11 branch commits share one timestamp (22 Oct 13:13) and the branch adds about 9,400 lines. The organisers say one big late commit can disqualify a final-round repo, so be ready to say when and how that code was written, and declare any part that pre-dates the build clock (19 Oct, 8 PM MYT). [TEAM TO FILL]

**23. Explain the Rising or Falling label in plain words.**
We compare the monthly share of posts that mention a skill over the last 12 months with the 12 months before, using a Welch t-test on the logit of the share. A skill gets Rising or Falling only when p is below 0.05 and it has at least 30 mentions in 24 months; otherwise it shows "No clear change". The label describes what already happened, and it pointed the right way for the next 12 months 67.2% of the time over 720 overlapping cases, which are not 720 independent tests.
Relies on: `docs/build-plan.md` P7; `data/backtest.json` (`trend_label_backtest`).

**24. Explain the match score and the rank.**
Match score is the weight of the role's skills you have divided by the weight of all its skills, and a weight is the share of that role's single-role posts that mention the skill, kept when the role asks for it at least 1.1 times as often as the average post. Rank score is 0.7 times match plus 0.3 times outlook (Rising 1.0, No clear change 0.5, Falling 0.0), and the team chose 0.7 and 0.3 without fitting them to data. A role under 20% match is not ranked, so it cannot rank on outlook alone.
Relies on: `engine/roles.py` (`match_roles`); the route note on the CV & routes screen; `data/role_profiles.json`; `data/role_trends.json`.

**25. Your band covered 93.8% against an 80% target. Is it useless?**
It is wider than it needs to be, and the Method screen says "a coverage above the target means the band is wide, not tight". The mean width at 12 months is 8.4 points. The window of 24 forecasts was set in advance, and windows of 36 forecasts or all history gave 92.9% and 91.9%, so one choice does not cause the over-coverage; the first fixed-width band covered only 65.9%, so we prefer to err wide.
Relies on: `data/backtest.json` (`coverage`, `interval_sensitivity`); `docs/build-plan.md` P6.

**26. Why an LLM, and how do you stop it inventing skills?**
CVs are free text, and people name the same skill in many ways. The LLM only points: it returns where a skill is mentioned, with a quote. Code proves: it drops any skill whose quote is not in the CV word for word, and it reads the years itself. If the call fails or no credentials exist, a keyword pass takes over, and "Try an example" needs no model at all.
Relies on: `docs/skill-profile-intake-architecture.md` (the LLM contract); `backend/signals/intake/llm_extract.py`.

**27. What personal data do you store?**
Only if a user chooses to sign in with Replit. Then we store, per account: the Replit user id, email, display name, profile image link, and the created and last-login times. Per profile we store the skill list, the target role and the pathway ticks. We never store the uploaded CV file or any token. For the CV builder we store the cleaned CV text, with emails, phone numbers and links replaced by placeholders (`owner_cvs`); it is deleted with the profile. Accounts with no login for 365 days are deleted. The privacy page (`frontend/privacy.html`) says the same. The data sit in Replit PostgreSQL when a database is configured, and in a SQLite file if not. The session is a signed HttpOnly cookie that lasts 30 days. These are personal data under the PDPA. Purpose: keep the user's profile and progress. The user can delete the account and the profile at any time (`DELETE /api/me`). We sell or share none of it. Without sign-in, the whole app still works ("Try an example", or a browser token). A profile made before sign-in moves into the account at first sign-in. Real CVs are still out of scope. Not yet tested on the live Replit app; Replit sign-in only, no Google.
Relies on: `backend/signals/trendsignal/web/auth_api.py`; `backend/signals/trendsignal/web/accounts_store.py`; `docs/submission/tech-declaration.md` section 6.1.

## Questions to expect that this sheet does not answer

- Cost to run and a business model: nothing in the repo covers it. Say so, and say the app is free to run on Replit within the declared plan. [TEAM TO FILL]
- Why a web app and not a mobile app: one Python server serves a static page and reuses the engine, and Replit is compulsory (`docs/build-plan.md` P11 records the earlier Streamlit choice, now retired).
- LinkedIn or X data: we did not use them (terms of service and personal data; `docs/build-plan.md` decisions).
