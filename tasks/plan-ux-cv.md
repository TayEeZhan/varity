# Plan: clearer app after the landing, tailored CVs, longer plans

Written 1 Nov 2026 after the mentor session. **Plan only. Nothing is built.** The user reviews it first.
Inputs: the mentor feedback (from memory, not recorded), a walk through the local app with Aina, and the code.
Related: `docs/ui-simplification-plan.md` (the teammate's landing and sign-in plan, built 31 Oct).

## 0. The "only week 1" question: not a bug

Aina's plan (Backend Engineer, 5 h a week) has **2 weeks**: 2–6 Nov and 9–11 Nov.
- 4 steps, 15 tasks, 450 min = 7.5 h in total (`STATE.plan.totals`).
- Week 2 is drawn, but it starts about 3 screens down the Today page (y ≈ 2,330 px). Nothing at the top says the plan has 2 weeks.
- The plan is short because each step is one **starter course** (Node.js 60 min, Go 180, Kubernetes 90, Terraform 120). The page already says a starter course does not close a professional gap. So the plan ends where the honest data ends.

Fix (P1 and P2 below): show the plan length at the top, fold the weeks, and add the next level after each starter course.

## 1. What makes the app confusing (found in the app, 1 Nov)

| Screen | Length | Controls | Problems |
|---|---|---|---|
| CV & routes | 5.6 screens | 18 buttons, 30 links, 14 fold-outs | Three jobs on one page: manage the profile (Read another CV, Delete, 3 examples), edit skills (5 Remove buttons), choose a route (7 cards, each with "Switch to this route"). Then a goal picker, a scenario toggle, a DOSM line and an SDG section. No clear "do this next". |
| Today | 4.5 screens | 17 buttons | A transit strip with letter codes (N, F, D) to decode. Every day of every week is listed. Week 2 is far down. |
| Pathway | 3.3 screens | 4 buttons, 1 select | The scenario toggle appears again. Stage names use jargon ("no-regret", "future bet"). A stale note still says "Fast scenario". |
| Signals | 2.2 screens | 6 filters | "Service notices" is transit wording; a new user does not know why AI news matters to them. |
| Job forecast | 2.5 screens | 0 buttons | OK to read, but no link back to "what this means for my plan". |

Root causes:
1. **No path after the landing.** The landing guides the user. After it, 5 tabs look equal, and nothing says which one comes first.
2. **Each page does several jobs at once.** The main action (choose a route, tick today's task) is mixed with settings and evidence.
3. **Metaphor and jargon.** Transit words (stops, lines, service notices), stage words (no-regret), and formula text appear before plain words.
4. **Everything is open at once.** All routes, all weeks and all evidence are shown in full. Details should open on request.

Fixed by the user on 31 Oct (keep, unless the user reopens it): the landing, the tab set, and **no** regrouping into 3 tabs. The plan below works inside the current tabs.

## 2. UX plan

| # | Change | What the user sees | Size | AI? |
|---|---|---|---|---|
| U1 | **"Your next step" bar** | One line under the header on every signed-in screen: `Step 2 of 4 · Your plan is ready. Tick today's first task. [Open Today]`. The 4 steps: Choose a job → Check your plan → Do today's tasks → Tailor your CV. Done steps get a tick. | M | No |
| U2 | **Tab names by task** | `1 Choose a job` · `2 Your plan` · `3 Today` · then a gap · `AI news` · `Job trends`. The same screens and routes; only labels and order change. The numbered tabs show the order. | S | No |
| U3 | **Shorter CV & routes** | The top 3 routes are shown; "Show 4 more routes" opens the rest. Profile actions (Read another CV, Delete, examples) move into one "Profile ▾" menu. The skills table becomes chips with an "Edit skills" button. The SDG section and the DOSM line move into a fold-out "Why these jobs matter". | M | No |
| U4 | **One main button per screen** | Each page has one filled button for its main action (Make my plan, Tick, Tailor CV). Other buttons become plain text links. | S | No |
| U5 | **Plain words** | "no-regret" → "useful for most of your jobs"; "future bet" → "may grow"; "Service notices" → "Top AI news this week"; the N/F/D letters get a one-line key, or words replace them. Fix the stale "Fast scenario" note in `engine/pathway.py`. | S | No |
| U6 | **Scenario toggle in one place** | Only on Pathway, inside the "Details" fold-out. Other screens show which scenario is on. | S | No |
| U7 | **Each page says why it matters to me** | The lede under each title becomes an instruction: "Pick one job to aim for, then press Make my plan." AI news gets: "Skills in your plan that are in the news this week: Go, Kubernetes." (This uses existing momentum data.) | S | No |
| P1 | **Plan length at the top of Today** | "Your plan: 2 weeks · 15 tasks · 2–11 Nov · 5 h a week [change]". The current week is open, later weeks are folded with their counts ("Week 2 · 5 tasks · locked until week 1 is done"). | S | No |
| P2 | **After the starter course** | Each step shows a "Next level" line after its tasks: the practice project (Sheng Kuan's feature, when merged) and the HRD Corp course where one is listed (days and fee from `data/hrd_programmes.json`). These go on the timeline only if their time comes from a source. Code never invents a duration. | M | No |

Visual checks from the redesign skill that apply here: show the current tab clearly, add empty and error states to every list, keep one accent colour, and add a visible focus ring. The landing and its style stay as they are.

### UX architecture

```
app.js
  STATE (profile, suggest, plan, done, cvDraft)
    └─ nextStep(STATE) ──► {n, of, text, action, href}        NEW, pure function, unit-testable
  rerender()
    ├─ header nav (index.html): new labels/order (U2)
    ├─ <div id="next-step"> outside <main> ◄── nextStep()     NEW (U1). Outside <main> so the
    │                                                          redraw and the CV pop-up are not affected
    └─ <main> ◄── SCREENS[screen]()
          profile  → screens.js renderProfile   (U3, U4, U5)
          today    → screens.js renderToday     (P1: summary + folded weeks)
          pathway  → screens.js renderPathway   (U6, P2)
          signals  → screens-explore.js         (U5, U7)
          forecast → screens-explore.js         (U7)
backend: no change for U1–U7 and P1. P2 reads hrd_programmes.json (already served) and SK's practice list.
```

## 3. CV plan

What exists now (your teammate's build): one CV draft per user (`owner_cv_drafts`), an optional pasted job ad, the CV assistant chat (`/api/cv/agent`), one bullet style (XYZ, fixed in the prompt), one layout (print to PDF), and code guards (no invented facts, no stronger verbs, word-for-word copies).

### Is "a CV for each company" possible? Yes, without much work

The bottleneck is building company data. **We do not need a company list.** The user already has the job ad when they apply. They paste it, and the app tailors one version for that ad, on demand. Ten applications give ten versions, each made in one click. The data comes from the user; we never scrape company sites.

| # | Change | What the user sees | Size | AI? |
|---|---|---|---|---|
| C1 | **One CV version per application** | "My applications": + New version → company name, role and the pasted ad → Tailor. A list of saved versions (company, role, date), each with Open, Download and Delete. Your current CV becomes the "Base CV". | M–L | 1 call per version |
| C2 | **Job ad check (code only)** | After the paste: "The ad asks for Python, AWS, Kubernetes. Your CV shows Python and AWS. Not on your CV: Kubernetes. It is in your plan, week 2." Never adds a skill to the CV. | S | No |
| C3 | **Bullet styles** | Style picker: XYZ (now), STAR, CAR, Short (action + result), Plain for ATS. The assistant also accepts "Rewrite in STAR style". The same guards apply to every style. | S | Same calls |
| C4 | **Layout templates** | Classic, Compact one page, Two-column. Print CSS only, so PDF output changes and the AI is not involved. | S | No |
| C5 | Tone per company type (startup, corporate, government) | **Wait.** The mentors' words "more styles for the job descriptions" are unclear. Ask them whether they meant C3, C4 or C5. | — | — |

### CV architecture

```
screens-cv.js (CV pop-up)
  ├─ Version list   GET  /api/cv/versions                       NEW (C1)
  ├─ New version    POST /api/cv/versions {company, roleId, jobAd, style}
  │                   └─ cv_writer.generate(..., job_ad, style)  style param NEW (C3)
  ├─ Ad check       POST /api/cv/ad-check {jobAd}               NEW (C2): the intake skill patterns
  │                   └─ {asked, onCv, missing, inPlan}           (taxonomy) run on the ad; code only
  ├─ Chat           POST /api/cv/agent {versionId, ...}         versionId NEW; the agent reads that version
  └─ Download       window.print() + template class (C4) | .md
accounts_store.py
  owner_cv_drafts (kept = Base CV, so old clients still work)
  owner_cv_versions (owner_key, version_id, company, role_id, job_ad, style, draft_json, updated_at)  NEW
  OWNED += owner_cv_versions  → deleted with the profile and by the 365-day retention job
```

## 4. Risks and problems

| # | Risk | Severity | What we do |
|---|---|---|---|
| 1 | **The user decided on 31 Oct: tabs and screens unchanged, no 3-tab regroup.** U2 and U3 change labels and fold content. | High | The user approves U2 and U3 first. U1, P1 and U5 need no layout change and can go first. |
| 2 | **Teammate's files.** The landing gate and CV pop-up live in `app.js`, `index.html`, `landing.*` and `screens-cv.js`. Parallel edits cause conflicts. | High | Never touch `landing.*`. Agree who edits `app.js` and `screens-cv.js`. Pull before each change. |
| 3 | **Demo video and scripts** name the old tabs and texts. | Medium | Update `demo-checklist.md`, `pitch-script.md` and `video-script.md` in the same change. Record after the build. |
| 4 | **C1 and C3 need a live LLM.** Claude runs only if `ANTHROPIC_API_KEY` is in Secrets; the Replit credits have not arrived. | High | With no AI, the code fallback still saves a version with the original bullets plus the ad check (C2). Do not route CVs to KrackedDevs without a decision: CVs hold personal data, and the privacy notice says Anthropic. |
| 5 | **Styles weaken the guards.** STAR and CAR invite invented situations or results. | Medium | The style changes only the wording rule. Verb levels, word-for-word sources and "no invented numbers" stay in force. Test one CV in each style for invented facts. |
| 6 | **More stored personal data** (several CV versions and pasted ads). | Medium | At most 10 versions per user; delete with the profile; 365-day retention; update `privacy.html`. |
| 7 | **The ad check misses skills outside our 40-skill taxonomy** (for example "Salesforce"). | Low | Say so on screen: "Checked against our 40 tech skills." |
| 8 | **The "next step" bar is wrong for some states** (no plan yet, plan finished, signed out). | Medium | `nextStep()` is a pure function with one test per state. |
| 9 | **P2 durations.** A practice project or HRD course on the timeline needs a time from a source. | Medium | HRD: days from the provider page. Practice projects: SK's sourced list. With no source, show the item as a link, not a dated task. |
| 10 | **Mentor feedback is from memory.** We may build the wrong "styles". | Medium | Build C2, C3 and C4 (cheap, clearly useful). Ask the mentors about C5 before building it. |
| 11 | **Time.** The final is close. | High | Build in the order below; stop at any point with a working app. |

## 5. Build order (each step ships alone)

1. **P1 + U5** (S): plan summary, folded weeks, plain words, stale note. Answers "where is week 2".
2. **U1** (M): next-step bar with tests.
3. **C2 + C3 + C4** (S each): ad check, bullet styles, templates.
4. **U3 + U4 + U6 + U7** (M): shorter CV & routes, one main button, toggle in one place, "why it matters to me". Needs the user's OK (risk 1).
5. **U2** (S): tab labels. Needs the user's OK (risk 1).
6. **C1** (M–L): CV versions per application. Needs a live LLM for the tailored wording (risk 4).
7. **P2** when SK's practice-project list is merged.
8. Browser check of each screen (Aina, Ben, Chloe; phone width), full tests, docs (`app-explained.md`, demo scripts, HANDOFF).

## 6. Questions for the mentors

1. "More styles": bullet styles (STAR, XYZ), page layouts, or tone per company type?
2. "More tailored": tailored to each job ad (C1), or to the user's career level (student, career changer)?
3. Which step after the landing confused them most: choosing a route, the plan, or Today?
