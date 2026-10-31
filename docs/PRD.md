# Varity: Product Requirements Document

Team Hokkien Mee Is Purple (Tay Ee Zhan, Goh Sheng Kuan, Universiti Malaya) · SDC Hackathon 2026, Domain 1
Version 1.1 · 25 Oct 2026 · Refined from v1.0 against `problem-statement.md` with a product diagnostic (who, pain, why now, MVP, anti-goals, metrics). Feature status checked in the code on `main`.

> **Pitch line:** *Tell us the role you want. We show how close you are, which skills AI is making essential, a dated plan to close the gap, and a new CV that proves it.*

---

## 1. Problem

> AI's coding ability is advancing faster than any curriculum can follow. Computer science students and early-career tech workers carry the highest exposure to this change, and their age group is losing jobs first. They have no tool that maps their current skills to a target role and shows which skills AI is making obsolete and which it is making essential.

### 1.1 Why now (evidence)

| Signal | Data | Source |
|---|---|---|
| AI coding ability jumped in one year | SWE-bench solved 4.4% (2023) → 71.7% (2024) | Stanford HAI, AI Index 2025 |
| Task length AI can handle | Doubles about every 7 months, for 6 years | METR, 2025 |
| Tools are the default | 84% of developers use or plan to use AI tools | Stack Overflow Developer Survey 2025 |
| Computer & math is the most exposed group | 94% of tasks theoretically coverable, 33% observed; programmers #1 at 75% | Anthropic, Massenkoff & McCrory, Mar 2026 |
| Juniors hit first | Employment of 22–25-year-olds in exposed jobs 19% below trend; no drop for seniors | Stanford Digital Economy Lab, *Canaries in the Coal Mine* |
| Skills reset | 39% of core skills change by 2030; AI & big data fastest-growing | WEF Future of Jobs 2025 |
| Malaysia | 56% of professionals use AI tools, only 26% have formal training; 600,000 workers must reskill in 3–5 years | Hays Asia Salary Guide 2025; MOSTI (Malay Mail, 7 Jan 2025) |

Degrees run on a timescale of years; AI capability moves in months. The jobs still exist (WEF: 170 million created, 92 million displaced), but the skills they need change faster than curricula.

### 1.2 The pain, made specific

1. **No real gap.** Job ads list skills, but nothing compares them to *this person's* CV with evidence.
2. **No signal on what is worth learning.** Hype hides the signal: in our Hacker News data, posts mentioning AI rose from 6.4% to 54.6% (Jan 2019 → Sep 2026), yet demand for the LLM/GenAI skill itself showed no clear change (Welch p = 0.207). Course lists ignore what is rising or being automated.
3. **Learning never reaches the CV.** The effort stays invisible to employers.

### 1.3 The gap Varity fills

| What exists today | What is missing | Varity's answer |
|---|---|---|
| AI-exposure studies (Anthropic, Stanford, WEF) | Applied to one person, one target role | Match % and skill gap for a chosen role, with each skill's AI stance |
| Course catalogues and roadmaps | Starts from the skills the person already has | Pathway built only from the gap, with free link-checked resources |
| Job boards | Which skills are rising or being automated | Backtested 12-month forecast, Rising/Falling label, dated source |

## 2. Goal and anti-goals

**Goal.** Close the gap between a user's current skills and their target role, then produce an updated CV that shows the new skills.

**MVP that proves the thesis.** CV → verified skills → target role → match % and gap → dated daily plan → mark skills learned → match % rises → generated CV. All of it is built (section 6).

**Anti-goals (we will not build these):**
- A job board, job listings, applications or recruiter matching.
- A chatbot or "AI career coach" that makes numbers up. Language models point or word; code decides.
- A precise jobs forecast. We forecast each skill's share of posts with a tested band, never a job count.
- Paid courses, or courses we have not link-checked.

## 3. Target users

Malaysia first.

| Persona | Description | Main need |
|---|---|---|
| **Student** | CS / IT / software engineering / data undergraduate, final year or intern | "Which skills do I need for my first role in X, and in what order?" |
| **Early-career worker** | Junior developer, 0–3 years, about 22–25 (e.g. *Aina, junior Python developer*, synthetic) | "My entry-level tasks are being automated. What do I learn next for the role I want?" |
| **Tech-adjacent switcher** | IS, engineering, data analyst, QA or IT support | "How far am I from a dev, AI or data role, and is it realistic?" |

Not targeted: non-tech career changers and senior roles (our data is thin there).

## 4. Product principles

1. **Code computes every number.** Scores, ranks, forecasts and dates come from code.
2. **Models point or word; code proves.** Every model output is checked, with a code fallback.
3. **Every number shows a source and a date.**
4. **Tested before trusted.** A method ships only if a backtest or evaluation supports it. (The ML forecaster and the Jev ranker both lost and were not promoted.)
5. **The human decides.** The user approves skills, picks the role and marks skills learned.
6. **Never invent on the CV.** The generated CV may only reword facts in the original CV and skills in the verified profile.
7. **Public or synthetic data only.** No scraping behind logins or bot walls; the demo uses synthetic CVs.

## 5. User journey

```
Upload CV ─► Review skills ─► Choose destination ─► Match % + gap ─► Pathway ─► Today's tasks ─► Mark as learned ─► Generate CV
(or example)                 (or "Not sure yet" →                               ▲                        │
                              ranked routes)                                    └──── match % rises ◄────┘
```

Time-to-value target: a ranked route with a match % in under 60 seconds from landing ("Try an example" needs no upload and no model).

## 6. Features and requirements

Status: ✅ built and in the app · 🟡 built, partial or unconfirmed live · ⏳ planned

### F1. Skill profile intake ✅
- **FR1.1** Upload a CV as PDF, DOCX, ODT, RTF, HTML, TXT or MD, up to 5 MB and 4 pages (`POST /api/cv/extract`).
- **FR1.2** "Try an example" with 3 synthetic profiles (no model needed).
- **FR1.3** Claude Haiku 5.5 points at skill mentions with a quote; code drops any skill whose quote is not in the CV word for word. A keyword pass runs without a key.
- **FR1.4** Skills map to a fixed taxonomy; unmapped skills are shown as "not in the job data yet", never silently dropped.
- **FR1.5** The user ticks or removes skills before saving (`POST /api/profile/apply`).
- **FR1.6** Emails, phone and ID numbers are redacted before the model call and before storage.

### F2. Target role ✅ / ⏳
- **FR2.1** Optional "Destination" picker; the chosen role is pinned on top, even with a low match. ✅
- **FR2.2** "Not sure yet" shows ranked routes: match 0.7 + outlook 0.3, have/gap lists and reason chips with source and date (`GET /api/roles/suggestions`). ✅
- **FR2.3** Switching role rebuilds the pathway (`POST /api/profile/target-role`). ✅
- **FR2.4** Free-text target role ("I want to be an AI engineer") mapped to the nearest known role, confirmed by the user. ⏳

### F3. Gap analysis and AI outlook ✅
- **FR3.1** Weighted match % from role profiles learned from single-role job posts (`engine/roles.py`).
- **FR3.2** Each missing skill shows its trend label (Rising / No clear change / Falling) and its AI stance (AI-complement, neutral, AI-substitutable). Contested stances are marked as contested.
- **FR3.3** 12-month role outlook with a tested band, labelled as an estimate.
- **FR3.4** Optional Claude advisor may move a role at most 2 places and write one checked summary line.

### F4. Personalised pathway ✅
- **FR4.1** Stages: no-regret, near-term, future bet (`engine/pathway.py`, `GET /api/pathway`).
- **FR4.2** Resources only from `data/resources.json` (77 link-checked, 76 free).
- **FR4.3** SDG 4.4 / 8.x lines per stage. (Plan `.md` / `.ics` export removed 1 Nov 2026.)
- **FR4.4** Optional pathway coach re-orders steps within a stage and writes one checked "why" line.
- **FR4.5** A new skill is offered only when AI-news momentum and job-post trend both rise, a nearby role needs it and a checked resource exists; at most one offer a week.

### F5. Daily tasks and progress ✅
- **FR5.1** Today shows the next tasks (≤ 45 min, Mon–Fri) and "Coming up".
- **FR5.2** Stable plan memory: ticks survive rebuilds; a rebuild that changes skills shows a Keep / Revert banner with reasons.
- **FR5.3** "Mark as learned" adds a finished skill to the profile; the match % rises.
- **FR5.4** Send today's tasks to Google Tasks (browser-side, Tasks-only scope, with Undo). 🟡 needs `GOOGLE_CLIENT_ID`; not tested with a real Google account live.

### F6. Generate an updated CV ✅
- **FR6.1** "Generate CV for this role" on Today and Pathway (`POST /api/cv/generate`).
- **FR6.2** Code picks and orders the skills; Claude rewrites summary and bullets; a checker drops any job, school, date, number or skill the original CV or profile cannot back.
- **FR6.3** No model → original CV plus a code-built skills section. No saved CV → skills-only CV.

### F7. Market context ✅
- **Signals:** AI and dev-tooling news ranked every 15 minutes. Graded by an independent 3-model AI jury: fixing clustering and adding a guarded urgent-security rule raised NDCG@10 from 0.37 to 0.53. Jev (0.25) is shown as a second opinion, not the ranker.
- **Skills radar** and **Method** (backtests, exposure cross-check, sources).

### F8. Account and privacy ✅ / 🟡
- **FR8.1** Works fully without sign-in.
- **FR8.2** Optional Replit Auth keeps skills, role, ticks and cleaned CV across devices. 🟡 not tested live.
- **FR8.3** `DELETE /api/me` / `DELETE /api/profile` deletes account, profile and stored CV.

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Cost | $1/day cap per model gate; every model step has a code fallback |
| Accuracy | Forecast band coverage 93.8% (target 80%); trend label right 67.2% of 720 cases (`data/backtest.json`) |
| Honesty | Real / synthetic / snapshot badge on every screen; estimates labelled |
| Security | Rate limits, error envelope, upload size limit, secrets in env vars |
| Privacy | Redaction before model and storage; synthetic CVs in the demo; delete on request (PDPA) |
| Deploy | One FastAPI server on Replit Autoscale (Asia); static frontend, no build step |

## 8. Success metrics

Aligned with the KPIs in our Preliminary submission (Phase 2 test users; targets, not results).

| Metric | SDG | Target |
|---|---|---|
| Finish at least one plan step with a link-checked free resource within 14 days | 4.4 | ≥ 50% |
| Pick a target role after seeing the match % and gap | 8.5 | ≥ 80% |
| Add at least one Rising or AI-complement skill to the plan | 8.2 | ≥ 60% |
| Time from landing to first ranked route | — | < 60 s |
| Invented claims in generated CVs | — | 0 (checker test suite) |

Today the app shows progress counts but stores no analytics events; we will record these in the Phase 2 test session.

## 9. Risks and limits

| Risk | Mitigation |
|---|---|
| Hacker News is US- and startup-heavy | Stated in the app; MyCOL adds the Malaysian shortage list; Malaysian job data needs a partnership (JobStreet blocks bots) |
| AI-exposure indices disagree | Only the language category is robust; contested stances shown hollow |
| "Can you predict jobs?" | No single number: a tested band and label; the user decides |
| Model invents skills or CV facts | Exact-quote check; CV claim checker; resource whitelist |
| "Learned" is self-reported | Labelled; future: project, quiz or GitHub evidence |
| Personal data in the stored CV | Redacted, token-gated, deleted with the profile |

## 10. Future work (ranked by impact × confidence ÷ effort)

1. Free-text target role mapping (FR2.4). High impact, low effort.
2. Phase 2 user testing with Malaysian students; record the section 8 KPIs.
3. Malaysian role data (DOSM, a job-site partnership).
4. Skill evidence beyond ticks (mini-projects, quizzes, GitHub).
5. A "what changed and why" view when the data updates.

## Sources

Anthropic (2026) https://www.anthropic.com/research/labor-market-impacts · Stanford Digital Economy Lab https://digitaleconomy.stanford.edu/publications/canaries-in-the-coal-mine/ · WEF Future of Jobs 2025 https://www.weforum.org/publications/the-future-of-jobs-report-2025/ · Stanford HAI AI Index 2025 https://hai.stanford.edu/ai-index/2025-ai-index-report/technical-performance · METR https://arxiv.org/abs/2503.14499 · Stack Overflow 2025 https://survey.stackoverflow.co/2025/ai · Hays Asia Salary Guide 2025 (via People Matters) · MOSTI (Malay Mail, 7 Jan 2025)
