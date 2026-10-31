# Live Demo Materials: Varity (Final, 1 Nov 2026)

Team Hokkien Mee Is Purple · 10 min pitch + live demo, then 5 min Q&A (−1 point per 30 s over).
The judges watch one synthetic user go through all six stages in one live session.

## 1. What judges need

| Item | Where |
|---|---|
| Live app | https://verity--eezhan0805.replit.app |
| Code | https://github.com/TayEeZhan/varity (public) |
| Synthetic CVs to upload | `demo-cvs/` in the repo: `aisyah-backend.docx`, `arjun-data.odt`, `daniel-devops.txt` / `.md` / `.html`, `sitihajar-ml.rtf`, `weijie-frontend.pdf` (all synthetic). In the app: Aina (her CV is read, with quotes), Ben and Chloe (skills only) |
| Login | Judges sign in with their own Replit or Google account ("Get started"). No test password is shared. On the demo laptop: the team's demo account, already signed in to Google in a normal window (not incognito) |
| Backup | Local copy with login off (section 5), and the backup video [TEAM TO FILL: YouTube link, if recorded] |
| Proof files | `data/impact_check.json` (impact run), `data/backtest.json`, `data/role_backtest.json`, `data/llm_usage.csv`, the GitHub Actions run log |

## 2. Before the slot (15 minutes before)

- [ ] Open the live app once to wake it (Autoscale sleeps; the first load can take about 30 s).
- [ ] GitHub → Actions → "Daily data refresh" → Run workflow. Wait for the green tick; Job forecast then says "updated <today>".
- [ ] Demo account: account menu (top right) → Delete account…, so the demo starts as a new user.
- [ ] Open a second tab on `#/radar` for the replay check.
- [ ] Local backup running on the laptop (section 5); HDMI adapter; charger.
- [ ] Open every link once in an incognito window.

## 3. The six-stage journey (about 6 minutes)

| # | Stage (guide wording) | Do this | Show and say |
|---|---|---|---|
| 1 | **Tell us about yourself** | Landing → **Get started** → sign in → pop-up "Start with your CV" → tick the synthetic box → drop `aisyah-backend.docx` (or pick **Aina (synthetic)**) | Each skill appears with **the sentence from the CV that proves it**. Untick one skill to show the user controls the profile, then press **Save N skills**. "Skills come from the CV; nothing is pre-filled." |
| 2 | **Future Skills Radar** | Landing → **Open the skills radar** (`#/radar`); then the **Signals** and **Job forecast** tabs | Rising and declining skills, each with **source and date** ("Source: HN Who is hiring · as of 2026-10 · fetched …"). Signals: AI news ranked from dated sources, with scores. Job forecast: roles with range bars, the Past year change and Growing / Steady / Shrinking. |
| 3 | **Get matched** | **CV & routes** → open **Why NN%?** on the top route | Ranked roles, each with a **match %** and **skills gap**. The breakdown shows 0.7 × skill overlap + 0.3 × outlook, and **What would raise it** lists each gap skill with the new score and a free course. |
| 4 | **Follow a pathway** | **Pathway** tab (the top route is the default; **Switch to this route** picks another), then **Today** | Ordered stages with **minutes per step** and free resources (click one: the real course opens), plus an **HRD Corp-claimable** option with days and fee. This week is open; later weeks are locked until it is done. |
| 5 | **SDG contribution** | Pathway → the SDG section; **I care about** (SDG goal picker) | Every role and skill has an SDG target **with a one-line reason**, and the plan adds them up ("How this plan contributes: SDG 8.2 (4), SDG 7.3 (1)"). Pick a goal: the route order changes, so the tag changes a choice. |
| 6 | **Compare futures** | Toggle **Expected (estimate)** ↔ **If AI speeds up (estimate)** on CV & routes or Pathway | Scores and the plan shift; both are labelled estimates. "The scenario applies one explicit parameter, k = 2, to each skill's AI exposure; it is not a hand-written alternative." |

## 4. Live checks the judges may ask for

| Judge asks | Do this | What to say |
|---|---|---|
| "Change the trend data now." | Skills radar → **Replay** → pick 2023-12 → open CV & routes and Pathway | The radar, the role scores and the plan change, because they read that month's data. **Back to latest** restores it. **Fetch latest HN now** pulls the newest posts (one fetch per 10 minutes). |
| "Is this course / number real?" | Click a resource link in the Pathway; click an HN thread link on Job forecast | Every resource link was checked (HTTP 200); every number names its file and date. |
| "Why this score? What would raise it?" | **Why NN%?** on the route | match = Σ weights held ÷ Σ role weights; rank = 0.7 × match + 0.3 × outlook; each gap skill shows the new score. |
| "How do you keep data current? Cost?" | Job forecast header "updated …"; GitHub Actions log | Daily at 09:00 MYT. Labelling all 48,491 posts cost US$2.63 once; a CV read costs at most US$0.0041. |
| "What if AI moves faster or slower?" | Scenario toggle; Method screen | k = 2 is an assumption; the data give −1.0 to 2.9; the Fast scenario shows the effect, labelled as an estimate. |
| "How do you stop it inventing?" | Upload a recipe file → "This does not look like a CV … try again"; the review line "Dropped because the quote is not in your CV" | Models only point at quotes; code checks each quote and sets every number, rank and course. |
| "Is it fair?" | Method → **Fairness check** | The test swaps name, age, gender, nationality and school; the ranking does not move. |

## 5. Backup if Wi-Fi or Replit fails

On the demo laptop (login is off on a local copy, so no sign-in is needed), from the `verity` folder:

```bash
cd backend\signals
```
```bash
..\..\.venv\Scripts\python -m trendsignal serve --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and run the same six stages. If the laptop also fails, play the backup video.

## 6. Say this honestly

- Predictions are estimates: we show an 80% band, and "Steady" when the change could be noise.
- Hacker News is a US and startup sample; DOSM gives a Malaysian sector check, not a per-role number.
- We tested with synthetic profiles only; the three Phase 1 user KPIs need a real-user pilot.
- Varity supports a decision; it does not make hiring decisions.
