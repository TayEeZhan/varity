# Verity deck outline (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). XMUM SDC Hackathon 2026, Domain 1. Branch `docs/submission`.

The organisers advise generic slides and a demo-first video (`C:\Users\eezha\sdc-hackathon\BRIEF.md`, opening-ceremony Q&A). So the deck is short: 9 slides, at most 25 words each, big type, one visual per slide. The live app carries the pitch from 0:40 to 3:45 in the video.

Matches `docs/submission/pitch-script.md` (target 5:45). Slides 1 to 3 run before the demo. Slides 4 to 8 run after it. Slide 9 is for the final-round pitch and for Q&A. The video does not show it.

Format: the preliminary round asks for "Pitch deck slides" and the final round asks for a `.pptx` (BRIEF). [TEAM TO CONFIRM: file format and name for the preliminary upload, in the Submission Files tutorial video]

## Slide list

| # | Title | On the slide | Visual | Video time | Script row |
|---|---|---|---|---|---|
| 1 | Verity | "Future-ready skills for tech developers". Hokkien Mee Is Purple. Ee Zhan and Sheng Kuan. XMUM SDC Hackathon 2026, Domain 1. | Title and app logo or plain wordmark | 0:00-0:05 | 1 |
| 2 | The signal is loud | "AI mentions in Hacker News hiring posts: 6.4% (Jan 2019) to 51.9% (Oct 2026)." "Which skills should a junior developer learn?" | Line chart from `data/ai_context_monthly.csv` (monthly and 3-month smoothed). Footnote: "Oct 2026 thread still open." | 0:05-0:30 | 1 |
| 3 | Meet Aina | "Aina, junior Python developer (synthetic). No real CVs." Chain: dated data, forecast with band, role match, daily plan, SDG links. | Five boxes in one row, Aina's name above the first | 0:30-0:40 | 1 |
| | *Live demo of the app* | *Full-screen recording of the app, 3:05 long; see `demo-checklist.md`* | App | 0:40-3:45 | 2 to 7 |
| 4 | How it works | Hacker News hiring posts (94 threads, 48,508 posts) and Anthropic Economic Index. 40 skills. Forecast and band. Learned role profiles. Plan ordered by code. Streamlit on Replit. | One-line block diagram, left to right | 3:45-3:55 | 8 |
| 5 | We tested before we trusted | 12-month error (points): naive3 1.66, naive 1.81, gradient boosting 2.06, drift 2.13, damped 2.27. "Band covered 93.8% (target 80%)." | Horizontal bar chart from `data/backtest.json` and `data/ml_backtest.json`. Highlight naive3 | 3:55-4:32 | 8 |
| 6 | We show disagreement | "Role profiles: 2,569 single-role posts." "Exposure stance: 1 category robust, 5 contested; 26 of 40 skills tagged." "Rank correlation with Microsoft's index: -0.79." | Left: small profile diagram. Right: the exposure table's last column (robust or contested) | 4:32-5:00 | 9 |
| 7 | Limits and next steps | "Hacker News is US and startup heavy." "JobStreet needs a data partnership." "CV upload with Claude Haiku is next." "HRD Corp status unverified." | Four short bullets | 5:00-5:20 | 10 |
| 8 | Impact | "SDG 4.4 skills for employment. SDG 8.5 productive work. SDG 8.2 productivity." "Estimates, not facts. You decide." Repo and app URLs. | Three SDG icons, team name, QR or short link | 5:20-5:45 | 11 |
| 9 | Appendix: team, tools, evidence | Who built what. Tools declared: Claude Code (major), Replit. Link list: repo, app, docs. Gradient-boosting table. | Table | not in video | Q&A |

## Notes per slide

1. **Title.** Show for 5 s while Sheng Kuan says the team name and Verity.
2. **Problem.** Use our own series. The Domain 1 brief gives no labour-market statistic (it has four SDG targets only). If the team adds an outside figure, cite it on the slide. [TEAM TO FILL]
3. **Aina.** Say "synthetic" on the slide, not only aloud. The five boxes are the brief's chain: track AI progress, predict skills, match roles, build paths, link SDGs.
4. **How it works.** Keep it to one line of boxes. Judges see the detail in the demo and in the repo.
5. **Tests.** The ML bar uses `data/ml_backtest.json` (2.064 on the same 616 pairs). Label the axis "mean absolute error in percentage points, lower is better, 12 months ahead, held-out test".
6. **Disagreement.** Do not rank the indices. The slide's point is that the app shows the disagreement.
7. **Limits.** Keep this slide even if the video runs long. The organisers' rule: do not exaggerate what the prototype can do.
8. **Impact.** SDG 4.3 is in the brief's list, but the app does not produce a 4.3 line, so the slide does not claim it. Add 4.3 only if the proposal's SDG table does.
9. **Appendix.** For the final round (10 minutes pitch, 5 minutes Q&A). The Q&A numbers table in `qa-prep.md` can go here.

## Final-round version

The final round (1 Nov) asks for an updated `.pptx` and a 10-minute pitch. Reuse slides 1 to 8, add: (a) a "what changed since the preliminary round" slide, as the updated PRD requires; (b) a slide for Sheng Kuan's AI-trend signal work, only if it is merged into `main` by then. Update every "no language model today" line if a model enters the running app, and update the tech declaration to match.

## Source of every number on the slides

| Slide | Number | File |
|---|---|---|
| 2 | 6.4%, 51.9% | `data/ai_context_monthly.csv` (49 of 765 posts in 2019-01; 138 of 266 in 2026-10) |
| 4 | 94 threads, 48,508 posts, 40 skills | `data/hn_threads.csv`, `data/demand_monthly.csv`, `data/taxonomy.json` |
| 5 | 1.66, 1.81, 2.13, 2.27, 2.06, 93.8%, 80% | `data/backtest.json`, `data/ml_backtest.json` |
| 6 | 2,569; 1 and 5 categories; 26 of 40; -0.79 | `data/role_profiles.json`, `data/exposure_agreement.json`, `data/exposure_robustness.csv` |
| 7 | none | `docs/build-plan.md` |
| 8 | SDG 4.4, 8.2, 8.5 | `docs/pathway.md`, `data/taxonomy.json` |
