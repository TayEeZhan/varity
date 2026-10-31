# Phase 2 Final Project & Prototype Report: Varity

Source text for `SDC2026_HokkienMeeIsPurple_Final.pdf`, filled into the official template by `scripts/fill_submission.py`.
Items marked [TEAM TO FILL] are for the team. Every number comes from a file in this repository; the file is named next to it.

## 1. Team & Project Overview

| Field | Entry |
|---|---|
| Team Name | Hokkien Mee Is Purple |
| Project / Product Name | Varity |
| Final Live Deployment URL | https://verity--eezhan0805.replit.app |
| Codebase Repository URL | https://github.com/TayEeZhan/varity |
| Name (Leader) | Tay Ee Zhan |
| Email & phone (Leader) | eezhan0805@gmail.com · phone on the submitted copy |

## 2. Project Description

Varity helps a worker in Malaysia decide which tech role to aim for and what to learn next, as AI changes the job market. A user uploads a synthetic CV. Claude Haiku 5.5 points at each skill and quotes the CV line that proves it; code drops any skill whose quote is not in the CV.

The trend layer reads every monthly Hacker News "Who is hiring?" thread since January 2019 (about 48,500 posts). Code tags 40 skills and 9 roles, tests each one's change in share and forecasts 12 months ahead with a tested uncertainty band. A second layer ranks AI news every 15 minutes. Every number shows its source and date. A GitHub Action refreshes the data every day, and a judge can replay an older month and watch the results change.

Varity then ranks roles by a match score that splits into two parts: skill overlap (70%) and demand outlook (30%). It shows the skills gap and what each missing skill would add. It builds an ordered, dated plan from 77 link-checked free resources, with HRD Corp-claimable options where we found them. Every skill and role carries SDG targets with a one-line reason, and the plan adds up its SDG contribution. A "Fast AI disruption" scenario, driven by an explicit parameter on each skill's AI exposure, shifts the scores and the plan, labelled as estimates.

Varity supports a human decision. It never ranks people for hiring or invents a job, course or number.

## 3. Upgraded Product & Technical Execution

### 3.1 Final System Architecture

One Python server (FastAPI on uvicorn) serves a static web app (HTML, CSS and JavaScript, no build step) and the JSON APIs. It runs as a Replit Autoscale deployment.

```
Hacker News "Who is hiring?" (Algolia HN API) --> engine/ (Python)
  - role labels: DeepSeek V4 Flash via KrackedDevs gateway; code checks every quote
  - 40-skill tagger -> monthly shares -> backtest-chosen forecast (naive3) + conformal 80% band
  - Welch t-test: Growing / Steady / Shrinking
  - AI exposure per skill (Anthropic Economic Index); scenarios: fast = moderate x (1 - k*e), k = 2
  - SDG tags per role and skill, each with a one-line reason
AI news (RSS feeds, arXiv, Hugging Face papers, HN, Bluesky) --> signal ranker, re-ranks every 15 min
                              |
FastAPI server (backend/signals/trendsignal/web)
  - CV intake: Claude Haiku 5.5 points at skills with quotes -> code check -> skill profile
  - role match: 0.7 x skill overlap + 0.3 x outlook; skills gap; "what would raise it"
  - pathway: ordered stages, dated daily tasks, 77 checked free links, 3 HRD Corp programmes
  - CV builder + checked CV assistant (Claude Haiku 5.5)
  - project and certificate stations, checked by a 3-vendor AI jury (Claude, GPT-5.4 mini, DeepSeek)
Storage: Replit PostgreSQL (accounts, profiles; SQLite fallback); Replit App Storage (data snapshots,
the last good one kept); committed aggregates in data/; Replit Auth (sign-in)
Daily refresh: GitHub Actions, 09:00 MYT -> POST /api/data/refresh -> new snapshot in App Storage
```

**GenAI integration.** A language model never produces a forecast number, a rank or a course. Each model call has one narrow job, and code checks the answer before the app uses it. Claude Haiku 5.5 (Anthropic API) points at CV skills with quotes, writes the CV builder's wording and powers the CV assistant; code rejects an unquoted skill, an invented fact or a stronger verb. DeepSeek V4 Flash (KrackedDevs gateway) names the roles in each job post with a quote, and code drops a label whose quote is not in the post. GPT-5.4 mini (KrackedDevs gateway) reviews new job titles before code adds a role. With no key, or when a daily budget cap is reached, code takes over: a keyword pass, the formula ranking and the code pathway.

**Database structure.** PostgreSQL tables hold users, profiles (skills with evidence, target role, plan state, ticks) and CV drafts. An account unused for 365 days is deleted. The trend data are versioned snapshots (`meta.json` holds `fetched_at`). `latest.json` switches only after a full upload, so a failed refresh keeps the last good data.

**Frontend.** A landing page, then a CV-first pop-up, then seven screens: CV & routes, Today, Pathway, Signals, Job forecast, Skills radar and Method.

### 3.2 Implementation & Hackathon Deliverables

Phase 1 showed one feature: CV intake with quotes. Now the whole six-stage journey runs live.

**Built in the upgrading round (28 to 30 Oct).** A daily refresh of the role forecast that serves the newest snapshot; a nowcast for the month in progress; a forecast ledger (track record); role scenarios; new-role discovery; the CV builder with a checked CV assistant.

**Built in the 48-hour physical sprint (31 Oct to 1 Nov).**
- Live data replay: a judge picks an older month, and the radar, roles and plan change (the change test).
- A score breakdown and "what would raise it" on every role; an SDG goal picker; a fairness check on the Method screen.
- A DOSM Malaysia vacancy check, and HRD Corp-claimable options with fees and days.
- The KrackedDevs gateway: DeepSeek V4 Flash relabelled 48,491 posts for US$2.63 (`data/llm_usage.csv`), with every quote checked by code.
- Project and certificate stations, with a three-vendor AI jury that must cite `file:line`.
- A landing page, Replit sign-in, a CV-first pop-up with upload, and four "not a CV" checks.
- A daily GitHub Actions refresh; its first run passed.

**Pivots from Phase 1.**
1. Replit allows one deployment type per app, so a Scheduled Deployment could not run beside the live site. We moved the daily job to GitHub Actions, which calls the app's own refresh endpoint.
2. The Replit AI credits did not arrive, so bulk labelling moved to the KrackedDevs sponsor gateway.
3. Persistence (the mean of the last 3 months) still beats trend models, so we show a tested band and a "Steady" label, not a confident trend line.
4. Mentors found the app confusing after the landing, so we added a CV-first entry, departure-board screens and locked future weeks in the plan.

## 4. Environmental & SDG Impact Verification

| Metric Category | Your Response |
|---|---|
| Target SDG Metric Achievement | **Phase 1 targets were shares of test users:** 50% finish a plan step with a link-checked resource (SDG 4.4); 80% pick a role after they see the score and gap (8.5); 60% add a Rising or AI-complement skill (8.2). **We ran no real-user test:** the rules forbid real CVs, and the sprint left no time for volunteers. So we measured what the system delivers to every synthetic profile: 10 runs (3 example profiles and 7 demo CVs; 8 people). **4.4:** 10 of 10 got a plan whose steps all use free, link-checked resources (100% of plan minutes free). **8.5:** 10 of 10 got ranked roles with a match score, a skills gap and the gain from each missing skill. **8.2:** 10 of 10 plans hold an AI-complement skill. **SDG tags:** 32 of 32 plan steps carry a target and a reason. **Scenarios:** the Fast scenario changed the role outlook for all 10 and the plan itself for 5 of 10. These numbers show that the system can deliver each KPI. They are not user outcomes. |
| Verification Evidence Method | `scripts/measure_impact.py` sends every synthetic profile through the real API (no mocks, no model calls) and writes `data/impact_check.json` (run on 1 Nov 2026). Forecast accuracy: rolling-origin backtests with no look-ahead (`data/backtest.json`, `data/role_backtest.json`). Cost: `data/llm_usage.csv`, one row per gateway call. Freshness: the GitHub Actions run log. Fairness: `backend/signals/tests/test_fairness.py` proves that name, age, gender, nationality and school do not move the ranking. 1,375 automated tests in all. |
| Socio-Economic / Civic Value | **Reach:** first through university and TVET career centres, which advise whole cohorts, and through HR teams that plan HRD Corp-funded training. **Cost per user:** at most US$0.0041 per CV read (price table in `intake/llm_extract.py`), under a US$1-a-day cap. Labelling all 48,491 posts cost US$2.63 once, and a day's new posts cost under one cent. **Learning cost:** the plan uses free resources first (100% of minutes in all 10 runs), with HRD Corp-claimable courses as an employer-funded option. **Freshness:** daily at 09:00 MYT. **Privacy (PDPA):** synthetic CVs only; contact details are redacted before any model call; users can delete their account, and an account unused for 365 days is deleted. |
| Deployment & Commercial Feasibility | Free for individuals. Paid seats for career centres and HR teams, and the same JSON API for a learning-management system or HR portal. The running cost is small and mostly fixed: one CPU server, one daily refresh and sub-cent model calls per user. No GPU and no model training in production. The data layer does not depend on one source, so a Malaysian job feed can join or replace Hacker News once a provider grants access. |

### 4.1 Mathematical Proof / Code Logic Snippet

**(a) The impact count.** `scripts/measure_impact.py` (excerpt), run on 1 Nov 2026:

```python
steps = plans["moderate"]["steps"]                       # the plan the user sees
"step_with_checked_free_resource": any((s.get("resource") or {}).get("cost") in FREE and s["resource"].get("url") for s in steps),
"rising_or_ai_complement_step":   any(s.get("trendLabel") == "Rising" or STANCE.get(s["skill"]) == "AI-complement" for s in steps),
"scenario_changes_plan": [s["skill"] for s in steps] != [s["skill"] for s in plans["fast"]["steps"]],
```

Output (`data/impact_check.json`): profiles 10 · kpi_4_4 1.0 · kpi_8_5 1.0 · kpi_8_2 1.0 · mean_free_minutes_share 1.0 · steps_tagged_sdg 32/32 · fast_scenario_changes_plan 0.5.

**(b) The explainable score** (`engine/roles.py`):

```
match_score  = sum(weight of skills the user holds) / sum(weight of all role skills)   weights learned from posts that name one role
future_score = 1.0 Growing, 0.5 Steady, 0.0 Shrinking        Welch t-test, last 12 vs previous 12 months, p < 0.05
rank_score   = 0.7 * match_score + 0.3 * future_score         "what would raise it" = the weight of each gap skill
fast         = moderate * (1 - k * e_s), k = 2                e_s = the skill's AI exposure (Anthropic Economic Index)
```

**(c) Why the numbers can be trusted.** Rolling-origin backtests, test origins 2023-11 to 2025-10, no look-ahead:

| | 12-month error, mean of last 3 months | 12-month error, last month only | 80% band covered | trend label right |
|---|---|---|---|---|
| 40 skills (`data/backtest.json`) | 1.66 pp | 1.81 pp | 93.8% | 67.2% |
| 8 roles (`data/role_backtest.json`) | 2.20 pp | 2.31 pp | 90.1% | 72.1% |

Trend models and gradient boosting lost on skills (drift 2.13, damped trend 2.27, gradient boosting 2.06 pp), so the app ships the simplest model that won and shows its band.

## 5. Market Viability & Future Scalability Plan

**Who pays.** Career centres and HR teams pay per seat for a cohort view that turns a group's skills gap into HRD Corp-claimable training plans. Individuals use Varity free.

**Scaling the data.** Today the job signal is Hacker News, a US and startup-heavy sample. With funding or a partner, we would:
1. License a Malaysian job feed (for example JobStreet or Hiredly, which blocked automated access during the hackathon) and run it through the same tagger, backtest and band. The code already has collectors that refuse to run without written permission.
2. Join DOSM's quarterly vacancy data, already shown in the app as a sector check, wherever it matches a role.
3. Move the snapshot store to a managed database and the daily job to a managed scheduler. The pipeline is already one command.

**Scaling the users.** The server keeps no state apart from the database, so more instances serve more users. Model cost stays under one US cent per CV, with a daily cap. Bulk labelling stays on the cheapest model that passes the quote check.

**Partners.** Through SDC's Rotary network and XMUM research links: career centres for a pilot with real, consenting users, to measure the three Phase 1 KPIs; TalentCorp (the MyCOL shortage list, already shown in the app) and HRD Corp for course data; and a joint study on whether the forecast band holds on Malaysian data.

**First six months.** A pilot with one career centre and 200 students, logging the three KPIs.

## 6. Final Submission Checklist

- [x] The application is fully compiled, live, and accessible via the deployment link provided in Section 1.
- [x] The GitHub (or equivalent) repository contains a clean, well-documented README with installation instructions.
- [x] The GitHub (or equivalent) repository shows the history of incremental code updates made throughout the official live hacking window.
- [ ] The final pitch deck has been exported and saved as a flattened PDF file. [TEAM TO FILL: tick after the deck is exported]
- [x] All fields in this template have been completed and word limits respected.

## 7. IP & Originality Declaration

### 7.1 Pre-Existing / Prior-Owned Work

No change from Phase 1 declaration. The repository was created on 21 Oct 2026, after the build clock started. Its first commit holds only the licence and a one-line README.

### 7.2 Third-Party Code, Datasets, or Models

Yes. The full list, with versions and licences, is in the Technical & Tools Declaration (sections 2.2, 4.1 and 4.2). Added since Phase 1:

| Name | Type (code/dataset/model) | License |
|---|---|---|
| DeepSeek V4 Flash, via the KrackedDevs LiteLLM gateway | Model | KrackedDevs sponsor terms; DeepSeek API terms |
| GPT-5.4 mini, via the KrackedDevs LiteLLM gateway | Model | KrackedDevs sponsor terms; OpenAI API terms |
| DOSM Big Data Analytics: Job Market Insights (quarterly) | Dataset | Government Open Data Terms of Use 1.0 (credit shown in the app) |
| MyMahir Malaysia Critical Occupations List 2024/2025 (TalentCorp) | Dataset | Public document; terms not reviewed |
| Trainocate Malaysia HRD Corp-claimable course pages (3) | Dataset (titles, days, fees, links) | The provider's pages; terms not reviewed |
| psycopg 3.3.6 | Code | LGPL-3.0-only |
| GitHub Actions (ubuntu-latest runner) | Service | GitHub terms |

### 7.3 Employment-Related IP Conflicts

No. Neither member (Tay Ee Zhan, Goh Sheng Kuan) is bound by an employment, internship or consulting agreement under which an employer could claim work made during this hackathon.

## 8. Declaration

By submitting this report, the team leader confirms that the deployed application and data presented above are the original work of the team, completed within the official SDC 2026 hackathon period.

Signature: see the signed copy · Name: Tay Ee Zhan · Date: 1 November 2026
