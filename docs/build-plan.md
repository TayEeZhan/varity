# Verity: full build plan

Team **Hokkien Mee Is Purple** (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1 (Aiversecity Future-Ready Workforce).
Preliminary deadline: **Sun 25 Oct 2026, 07:59:59 MYT**. Our target: submit **Sat 24 Oct, 21:00**.
Live prototype: https://verity--eezhan0805.replit.app (shows sample data until step A2 is done).
Status on 22 Oct 2026: 221 tests pass.

Legend: ✅ built and tested · 🟡 built, not yet shown in the app · ⏳ planned · ❓ needs a team decision

## Current status (22 Oct 2026, after PRs #1-#7 were merged into main; 713 tests pass)
Sections 2 and 3 below are the plan as written earlier. This table is the current truth.

| Part | Status | Where |
|---|---|---|
| P1-P11 skill engine and app on real data (forecast, band, trend label, statuses, scenarios, refresh, as-of view) | ✅ merged | PR #1 |
| E7 role match (profiles learned from single-role HN posts, tiers, Roles tab, personas) | ✅ merged | PR #2 |
| E8 pathway (stages, daily to-do, progress, .md/.ics export, SDG lines, 77 verified resources) | ✅ merged | PR #4 |
| Step 4 daily scheduled refresh + Replit App Storage | ✅ merged; Replit UI setup still to do | PR #3, docs/replit-schedule.md |
| Step 5 ML forecaster (gradient boosting) | ✅ merged as evidence; lost to naive3, not used in production | PR #5, docs/ml-forecaster.md |
| Step 9 exposure cross-check (3 indices) and data-based k | ✅ merged; only "language" stance robust; k cannot be pinned down | PR #6, docs/exposure-crosscheck.md |
| Step 7 new-skill discovery radar | ✅ merged; weak backtest, human review only | PR #7, docs/skill-discovery.md |
| Step 8 JobStreet Malaysia | ❌ stopped: Cloudflare challenge; needs a data partnership | docs/jobstreet.md (branch feat/jobstreet-my) |
| E9 "what changed and why" | 🟡 partial: Refresh lists changed skills; no full diff view | app.py |
| S1 CV extraction (Claude Haiku) | ⏳ Sheng Kuan | not started in this repo |
| S2 AI news ranker feed | ⏳ Sheng Kuan; plugs into `ext_momentum` | docs/ml-forecaster.md |
| Submission documents, pitch script, Q&A | ⏳ drafts on branch docs/submission | docs/submission/ |
| Open decisions | ❓ AIOE licence; cloud_devops stance; JobStreet route; Gmail in old commits | — |

---

## 1. What Verity is

**One line:** Verity reads a tech developer's CV, shows which skills are rising or falling from dated public data, ranks future roles with a match score and skill gap, and turns the gap into a daily learning plan. Every number shows its source and date.

**User:** a junior or mid-level tech developer in Malaysia (fresh grad, career switcher), for example "Aina, junior Python developer". CS and tech is our starting group because it has the best free, dated, public data. The design does not depend on the field.

**The brief's chain and where each part lives:**

| Brief asks for | Verity part | Status |
|---|---|---|
| Track AI advancement continuously | Hiring-demand series (P2, P3), live refresh (P10), AI news feeds (S2) | ✅ / ⏳ |
| Predict emerging and declining skills | Forecast (P5), band (P6), trend label (P7), statuses (P8) | 🟡 |
| Match people to future roles | Role match (E7) | ⏳ |
| Personalised reskilling pathway | Pathway and daily to-do list (E8) | ⏳ |
| Link to the 17 SDGs | SDG tag per skill (P1), per role and per plan (E7, E8) | 🟡 / ⏳ |
| Profile intake (CV, form) | CV extractor (S1) | ⏳ (Sheng Kuan) |
| More than one scenario, labelled as estimates | Moderate and fast scenarios (P9) | 🟡 |
| Name the LLM, cite every source, never invent | Sources on every record, tests, SOURCES.md | ✅ (LLM not chosen yet ❓) |

**Data flow:**

```
HN "Who is hiring?" threads (2019-01 .. now)          Anthropic Economic Index + O*NET
        |  P2 fetch, P10 live refresh                          |  P4
        v                                                      v
  P1 tagger -> P3 monthly demand per skill            exposure per skill category
        |                                                      |
        +-----> P5 forecast -> P6 band -> P7 trend label -> P8 status -> P9 scenarios
                                         |
                                 data/skill_scores.json  (one record per skill, with sources)
                                         |
   S1 CV extractor -> profile.json -> E7 role match -> E8 pathway / daily to-do -> E9 "what changed"
                                         |
                                  Streamlit app on Replit
```

---

## 2. What is built

### P0. Plan and data contract ✅
- **What:** `tasks/todo.md` (plan, timeline, checklist) and `docs/data-contract.md` (the file formats both of us write and read).
- **Why:** two people build in parallel. A fixed file format lets Sheng Kuan's fetchers and the engine work without waiting for each other.

### P1. Skill taxonomy and tagger ✅
- **What it does:** finds which of 40 tech skills a job post mentions.
- **How:** `data/taxonomy.json` has 40 skills. Each has a canonical name, synonyms, a regular-expression pattern, an SDG tag and a one-line SDG reason. `engine/tagging.py` removes HTML and links, then matches the patterns.
- **Why this way:**
  - Patterns, not an LLM, so the result is the same every run, free, fast, and easy to explain.
  - Hard names have tested rules: "Go" vs "go to market", "R" vs "R&D", C vs C++ vs C#, "Swift" vs "swift delivery", React vs React Native.
  - **Fix from review:** bare "AI" in company blurbs ("we are an AI startup") made Machine Learning look like 55% of jobs. Now Machine Learning needs real skill words (ML engineer, PyTorch, deep learning). Posts that only say "AI" go to a separate series (`ai_context_monthly.csv`: 6.5% in 2019 to 51.2% now). That series is a real AI-trend signal, but it measures company context, not a skill.
  - **Fix from review:** "JavaScript / TypeScript" is one combined row (flat, about 25%), so JS developers are not told their skill is dying. TypeScript keeps its own row to show the shift.
- **Proof:** tests for every hard name.

### P2. Hacker News hiring backfill ✅
- **What it does:** downloads every monthly "Ask HN: Who is hiring?" thread from Jan 2019 to Oct 2026.
- **How:** `engine/backfill_hn.py` uses the public Algolia HN API. One request at a time, with pauses and retries.
- **Result:** 94 threads, 48,508 job posts, no missing months.
- **Why this source:**
  - It is free, public, dated and monthly, and goes back years, which a forecast needs.
  - It is tech-specific.
  - Each thread has a URL we can cite.
  - We do not scrape LinkedIn, JobStreet or X: that breaks their terms and touches personal data.
- **Privacy:** raw post text stays on our machines (`data/raw/`, not in git). Only counts and thread links are committed.

### P3. Monthly demand series ✅
- **What it does:** for each skill and month, gives the share of job posts that mention the skill (`data/demand_monthly.csv`).
- **Why share, not count:** posts per month fell from 703 (2019 mean) to 310 (last 12 months). Raw counts would make every skill look like it is dying.
- **Why each post counts once per skill:** a post that says "Python" five times is still one job asking for Python.

### P4. AI exposure per skill ✅ (v2)
- **What it does:** says how much AI already does the work tied to a skill: "AI-complement", "neutral" or "AI-substitutable".
- **How:**
  - Each skill category maps to 1 or 2 O*NET occupations, for example Data Scientists, Web Developers or Systems Administrators.
  - For each occupation we take the **automation share** from the Anthropic Economic Index: the share of Claude.ai conversations where the AI did the task, not just helped.
  - ai_ml is 47.4%, the lowest. cloud_devops is 64.9%, the highest.
- **Why v1 was replaced:** v1 used how much traffic each task got. That measures popularity, not exposure, and gave results we could not defend (Ruby ranked above Python, AI skills near 0).
- **Limits we state:**
  - Claude.ai data only.
  - Skills in one category share a score, because the data is per occupation, not per language.
  - The data is dated 2026-06.

### P5. Forecast 🟡
- **What it does:** predicts each skill's share of job posts 12 months ahead.
- **How:** works on the logit of (mentions + 0.5) / (posts + 1). This keeps shares between 0 and 1 and handles zero counts. We tested 4 models: naive (last month), naive3 (mean of the last 3 months), drift (trend line), and damped trend.
- **Why naive3:**
  - It had the lowest error on held-out 2024–25 data: 1.66 percentage points at 12 months, vs 1.81 for naive.
  - The trend models were **worse** than naive (2.13 and 2.27).
  - This is an honest finding: 12-month job demand is close to "no change". We say this in the pitch instead of hiding it.

### P6. Backtest and uncertainty band 🟡
- **What it does:** proves how good the forecast is, and gives every forecast an "80% target band".
- **How:**
  - We replay history: from every month between Dec 2021 and Oct 2025 we forecast 12 months ahead, then compare with what happened.
  - The band width comes from the errors of the last 24 forecasts whose outcome was already known, scaled to how noisy that skill is.
  - It only uses data from before the forecast date, so nothing leaks from the future.
- **Result:** on held-out 2024–25 data the band covered **93.8%** of real values at 12 months. That is above the 80% target, so the band is conservative, not tight, and it holds for small and big skills alike.
- **Why it changed:** v1 used a fixed band and covered only 65.9%. A stronger model reviewed it and chose this method. All numbers are in `data/backtest.json`.

### P7. Rising / Falling label 🟡
- **What it does:** labels each skill **Rising**, **Falling** or **No clear change**, based on what already happened.
- **How:** a statistical test (Welch t-test) compares the last 12 months with the 12 before. It gives a label only when p < 0.05 and the skill has at least 30 mentions.
- **Result:** in the backtest the label's direction held for the next 12 months **67.2%** of the time (720 cases).
- **Now (Oct 2026):**
  - Rising: Rust, PostgreSQL, Terraform, RAG.
  - Falling: Ruby, Microservices.
  - LLM / GenAI is **flat** (566 mentions in the last 12 months vs 561 in the 12 before). It rose fast in 2023 and has now levelled off.
- **Why:** the brief asks which skills emerge or decline, and the best forecast is "about the same". So we show an observed, tested trend label, plus the forecast level and band. We never claim a precise future number.

### P8. Data-volume status 🟡
- **What it does:** stops the app from showing unreliable forecasts for skills with too few posts.
- **Rules:**
  - **ok** (27 skills): at least 5 mentions per month. Forecast, band and scenarios are shown.
  - **low_volume** (8 skills): too few for a forecast, but at least 30 mentions in 24 months. Observed counts and the trend label are shown. Examples: Vector Databases, dbt, Kafka.
  - **rare** (5 skills): only the counts are shown. Perl, R, AngularJS, jQuery, Hadoop.
- **Why:** an earlier version hid emerging skills like Vector Databases. Now they are visible, with honest counts.

### P9. Scenarios 🟡
- **What it does:** shows a **Moderate** and a **Fast AI disruption** future for each skill.
- **How:** fast = moderate × (1 − k × e). Here e is how far the skill's automation share is above the average, and k = 2. The app shows k as an assumption.
- **Why:**
  - The brief asks for more than one scenario, labelled as estimates.
  - One stated formula is easy to explain and to challenge.
  - The app also shows the shift next to the band width. When the shift is inside the band, we say so, so a small shift is not oversold.

### P10. Live refresh ✅ (not yet a button in the app)
- **What it does:** re-downloads the current, still-open HN thread and updates only that month, in about 7 seconds.
- **Why:** the brief says "updatable source" and "the output visibly changes when the trend data changes". This is the live part of the demo.
- **Safety:**
  - If the Replit disk is read-only, it works in a temporary folder.
  - If the network fails, it keeps the last good data and shows its date.

### P11. Streamlit app on Replit ✅ (shows sample data)
- **What it does now:** title, data date, a Moderate/Fast toggle, a table of skills, and sources per skill. It is deployed at the URL above.
- **Why Streamlit:** one Python program reads the engine directly. No separate server is needed, and it is fast to build and deploy on Replit, which is compulsory.
- **Why the versions are pinned:** Replit's package firewall blocks Pillow versions with known security issues (six advisories on 20 Oct 2026). We moved to Streamlit 1.66.1 with Pillow 13.0.0, and checked every package against the OSV advisory database.

### P12. Quality, sources and privacy ✅
- 221 automated tests: tagger, demand, exposure, forecast, backtest (including tests that the future does not leak into the past), scores, refresh and the app.
- `data/SOURCES.md` lists every dataset with URL, date and licence. O*NET (CC BY 4.0) and the Anthropic Economic Index (CC BY) are credited in the README.
- A test checks that no committed data file holds an email address.
- The repo is private while we build. It has an Apache 2.0 licence.

---

## 3. What is planned

### A1. Scores can use any data folder ⏳ (small)
- **What:** `build_scores(data_dir=...)`.
- **Why:** on Replit the refresh may need a temporary folder. Without this, Refresh can fail when a new month's thread appears.

### A2. App on real data ⏳ (Ee Zhan)
- **Skills screen:**
  - Columns: status, Rising/Falling label with counts, current share, forecast with band, stance.
  - For each skill, a chart: history, forecast band and sources.
- **Fast scenario:** shows the shift and says "inside the band" when it is.
- **Partial month:** a note that Oct 2026 is still open.
- **Refresh button:** calls P10 and shows "last updated" and what changed.
- **As-of slider (Nov 2023 to Oct 2026):** reruns the engine with only the data known at that date. For example, "in Dec 2023 we forecast X; what happened was Y".
- **Model name and "Estimate. You decide." line:** always visible.
- **Why:** this is what the judges see in the live demo. Today the deployed app still shows sample data.

### E7. Role match ⏳ (Ee Zhan)
- **What it does:** ranks about 8 future tech roles for the user. Each role gets a match score, the skills the user has, the skills missing, and one line on why.
- **Roles (draft):** Data Engineer, Analytics Engineer, ML Engineer, AI/LLM Application Engineer, Backend Engineer, Full-stack Web Developer, Platform/DevOps Engineer, Mobile Developer.
- **How (planned):**
  - **Role skill weights from data:** in the HN posts, find posts that name the role (for example "data engineer"), then count which skills those posts ask for. A hand-made list is the fallback, labelled "team judgement".
  - **Match score** = the weighted share of the role's skills that the user has.
  - **Role outlook** = the role's own share of posts and its trend label, plus the stance of its skills.
  - **Ranking** = match score combined with outlook, with the formula shown in the app.
- **Why:**
  - The brief wants an explainable match score and a clear skill gap.
  - Weights from real posts can be cited. Weights we invented could not.

### E8. Reskilling pathway and daily to-do list ⏳ (Ee Zhan engine, Sheng Kuan resources)
- **What it does:** turns the gap for the chosen role into an ordered plan, then into daily tasks such as "Day 3: SQL window functions, 45 min, free resource X".
- **Order:**
  1. **No-regret skills** first: needed by more than one of the user's top roles, and not Falling.
  2. **Near-term demand:** high current share.
  3. **Future bets:** Rising, or AI-complement.
  - The Fast scenario moves future bets earlier.
- **Each step shows:** time estimate, one real free or low-cost resource (HRD Corp-claimable where possible), source, SDG tag and the reason it is in the plan.
- **Resources:** `data/resources.json`. Sheng Kuan fills and checks every link. **No course is invented.**
- **Export:** in-app list plus `.ics` or Markdown. Google Tasks sync is a stretch goal.
- **Why:**
  - The brief wants an ordered pathway with time estimates.
  - A daily list (Sheng Kuan's idea) makes it a habit, not a one-time report.
  - The order is set by code. The LLM only writes the sentences, so it cannot change the plan.

### E9. "What changed and why" ⏳ (Ee Zhan)
- **What it does:** compares two runs and lists changes: label flips, level moves, band changes and the role ranking. Each change shows the data that caused it (new month, new posts).
- **Why:** the brief's success test says the output visibly changes when the trend data changes. This makes the change explicit and traceable.

### S1. CV intake ⏳ (Sheng Kuan)
- **What it does:** reads a CV and returns skills with an **exact quote** from the CV and years of experience.
- **How:**
  - An LLM extracts the skills.
  - Code then drops any skill whose quote is not in the CV. That stops the LLM from inventing skills.
  - Skill names must match `data/taxonomy.json`.
- **Human control:** the user can remove or add skills and choose a target role.
- **Data:** 3 synthetic CVs only (for example "Aina, junior Python developer"). No real CVs.

### S2. AI advancement feeds ⏳ (Sheng Kuan)
- **What it does:** collects dated AI news from official sources: AI lab blogs (RSS), GitHub (new and fast-rising repos), arXiv papers and Hugging Face trending.
- **How it is used:**
  1. **Shown as evidence** for each skill, for example "this month: 3 new RAG releases".
  2. **Tested as an early signal:** does a rise in GitHub or arXiv activity come before a rise in hiring demand? It joins the forecast **only if the backtest shows it helps.** Until then its weight is 0, and we say so.
- **Why:** the brief says "tracks AI advancement". Hiring posts show demand. These feeds show what is new in AI. We do not let unproven signals change the numbers.

### S3. UI pages and the resource list ⏳ (Sheng Kuan)
- CV upload page, roles page and plan page in Streamlit.
- Fill and check `data/resources.json`.

### LLM ❓
- We must choose **one** hosted model and name it in the app and the documents. It is used only for CV extraction and for wording explanations.
- **Option to check:** Replit's built-in AI integration. It needs no separate API key, and it adds more proof of Replit use. Otherwise, one Anthropic or OpenAI model with a spending cap.
- No local models and no fine-tuning, so no GPU and no RunPod.

### Documents ⏳
| Document | Owner | Content |
|---|---|---|
| `SDC2026_HokkienMeeIsPurple_Preliminary.pdf` | Sheng Kuan drafts, Ee Zhan writes method | Problem (250 words), AI solution (300), tech stack + block diagram, design and deployment (200), SDG impact table with numbers and sources, checklist, IP declaration |
| `SDC2026_HokkienMeeIsPurple_TechDeclaration.pdf` | Sheng Kuan | Every library with version and licence, APIs, Replit plan, models, datasets with licences, AI dev tools (Claude Code: major, plus how we checked it), privacy, limits |
| Pitch deck | Both | Problem → user → demo → method and backtest → limits and risks → SDG |
| Pitch video, 5–7 min | Both | Demo first; slides short |

---

## 4. Timeline

| When | Ee Zhan | Sheng Kuan | Done when |
|---|---|---|---|
| Fri 23 Oct, morning | A1, A2 (app on real data, Refresh, as-of slider) | S1 CV extractor + 3 synthetic CVs, S2 feeds | Live site shows real forecasts |
| Fri 23 Oct, afternoon | E7 role match, E8 pathway, E9 diff | S3 pages, `resources.json`, draft proposal and declaration | CV → roles → plan works on Replit |
| Sat 24 Oct | 12:00 feature freeze, fixes, method section, backtest chart | SDG table, deck | 14:00 record video, 18:00 upload, 21:00 submit |
| Sun 25 Oct | Buffer only. No commits after 07:59 | | |

Every major part gets a stronger-model review before it is called done, and a short "how it works" note so both of us can answer judges.

---

## 5. Risks and our answers

| Risk | What we do |
|---|---|
| Judges ask "can you really predict jobs?" | No single number. Persistence won the backtest, so we say that, show a tested band (93.8% coverage) and a tested label (67.2%), and the user decides. |
| HN is US- and startup-heavy, not Malaysian | Stated as a limit. Malaysian sources (DOSM, MyCOL) are future work. |
| A data source is down during the demo | Refresh keeps the last good data and shows its date. |
| LLM invents a skill or a course | Exact-quote check for skills. Courses only from the checked `resources.json`. |
| Replit blocks a package | Exact pinned versions, checked against advisories. |
| "Is this AI plagiarism?" | Both members can explain every part (see the "how it works" notes). Claude Code is declared as a major tool. |
| Commit history looks like one person | Sheng Kuan commits his own work from now on. |

## 6. Decisions needed
1. ❓ Which LLM (check Replit's AI integration first).
2. ❓ Git email: commits show a personal email that becomes public when the repo opens. Option: switch to the GitHub noreply address for future commits.
3. ❓ Final list of 8 roles (draft above).
