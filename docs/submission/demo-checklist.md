# Verity demo and recording checklist (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). Matches `docs/submission/pitch-script.md` (5:45 target, 7:00 hard maximum; each 30 s over costs 1 point).
Tick each box as you do it. Items marked [TEAM TO FILL] need a decision from you.

## 1. Decide first

- [ ] Who drives the screen? One person drives all of the demo. Both speak, as the script assigns. [TEAM TO FILL: driver]
- [ ] Recording tool and output: 1920 x 1080, 30 frames per second, the system audio off, one microphone. [TEAM TO FILL: tool]
- [ ] Voices: record the voice live over the demo, or record the screen first and the voice after. A voice-over after the screen take lets you cut waits and keeps the timing exact. [TEAM TO FILL: choice]
- [ ] YouTube visibility (public or unlisted) and the upload account. The organisers' Submission Files tutorial video should say. [TEAM TO FILL]

## 2. The day before

- [ ] Both members read the script aloud with a stopwatch, three times. Log each take in section 8.
- [ ] Both members read `docs/ml-forecaster.md`, the backtest part of `docs/build-plan.md`, and `docs/submission/qa-prep.md`. Sheng Kuan speaks the forecast-test rows (5 and 8) and may get those questions.
- [ ] Open https://verity--eezhan0805.replit.app in a private window. It must show real data. If the page shows "Prototype: showing sample data", the deployment is old: redeploy `main` first.
- [ ] Compare the page with the numbers in section 4. If a value differs, find out why (a refresh, a new snapshot) and fix the script, not the screen.
- [ ] Do not click "Refresh live data" before the take. Once App Storage is set up (Replit setup pending), it publishes to the shared store, so the numbers can change for everyone, including the judges. If someone clicked it, repeat the number check.
- [ ] Open the app once on `main` locally (`streamlit run app.py`) as a second source for the backup take (section 6).
- [ ] Choose the account for the recording: a clean browser profile with no extensions, no saved logins, and no bookmarks bar.

## 3. 30 minutes before the take

- [ ] Close every other browser tab and window. Quit chat apps, mail and cloud-sync pop-ups. Turn on Windows Focus assist (do not disturb).
- [ ] Browser window at 1920 x 1080 with the page zoom at 110%. If the model table or the exposure table is hard to read in a 720p preview, raise it to 125%. (A suggestion: test it with a short clip.)
- [ ] Theme: pick one (light or dark) and keep it for every shot, including the slides. The app follows the browser theme.
- [ ] Mouse: slow pointer speed, a visible pointer. Move it to point at things and leave it still while you speak.
- [ ] Microphone: record 10 seconds, play it back, check for fan noise and clipping. Close the window or door.
- [ ] Phone on silent. Charger plugged in. Stable network (wired if possible).
- [ ] Wake the Replit app: open the URL 10 minutes before and click through all five tabs once. An autoscale deployment can be slow on its first request after a quiet period. (Likely, not tested.)
- [ ] Warm the As-of cache: set the sidebar "As of" slider to 2023-12 and wait for the Skill detail tab to load, then set the slider back to the latest month. The first calculation takes a few seconds. [Source: the spinner text in `app.py`.]
- [ ] Reload the page so the session is fresh. The target role, ticks, scenario and slider all reset.

## 4. State to check at 0:40 and the numbers to expect

Committed snapshot: `data/skill_scores.json` generated 2026-10-21T21:09:03Z, as of 2026-10. Values below come from the files and from a read-only run of the app's own functions on 22 Oct 2026.

| Screen | Setting | Expect |
|---|---|---|
| Header | none | "Data as of: 2026-10"; the info line "The latest month's thread is still open" |
| Sidebar | Scenario | Moderate selected; As of at the latest month |
| Roles tab | Example profile | "Aina, junior Python dev (synthetic)": Python, SQL, PostgreSQL, Docker, AWS |
| Roles tab, card #1 | Backend Engineer | Match 66%; "Role demand: Rising 10.6% of posts in the last 12 months vs 9.4% the 12 months before"; gaps Go, Kubernetes, Terraform, Node.js; confidence "solid (445 single-role posts)" |
| Roles tab, ranking | order | #1 Backend Engineer (66%), #2 AI/LLM Application Engineer (39%), #3 Data Engineer (51%), #4 Data Scientist (43%), #5 Platform/DevOps Engineer (38%), #6 ML Engineer (24%), #7 Full-stack Web Developer (22%); "Not a fit yet": Mobile Developer |
| Roles tab, Fast | card #1 caption | "Fast AI scenario (estimate): about -6.1% role demand vs moderate. Does not change the ranking." The order is the same as above |
| Pathway tab | Backend Engineer, 5 hours a week | 4 skills, 15 daily tasks, about 7.5 hours. Stage 1 Node.js; stage 2 Go, Kubernetes; stage 3 Terraform |
| Pathway, first tick | task T001 | Progress "10% done (1 of 15 tasks, 45 of 450 minutes)" |
| Pathway, SDG links | two sentences | "SDG 4.4 ... adds 4 job-listed skills in 7.5 hours (estimate) at RM0 cost using free resources." "SDG 8.5 ... moves you toward Backend Engineer (role demand: Rising, 10.6% ... vs 9.4% ...)" |
| Pathway, notice | HRD Corp | "HRD Corp-claimable status not verified ..." (the script mentions this in the Limits row) |
| Skill detail, Python | Moderate | Forecast for 2027-10: 26.3%, band 22.1% to 30.9%; trend label "No clear change" (923 vs 923 mentions) |
| Skill detail, As of 2023-12 | Python | Forecast 20.2%, band 16.1% to 25.0%; "What happened": 18.0%, "inside the band" |
| Method, forecast table | test h=12 | naive 1.81, naive3 1.66, drift 2.13, damped 2.27; chosen model naive3 |
| Method, band | coverage | 93.8% (target 80%), mean width 8.4 pp |
| Method, label | hit rate | 67.2% (n = 720); Rising 60.5%, Falling 71.9% |
| Method, exposure | stances | "Most indices agree with our stance: language. Contested: ai_ml, cloud_devops, data, framework, practice."; correlation line with Microsoft -0.79 |
| Method, k line | text | "The data cannot pin k down (point estimate 1.8 per 12 months, 95% CI -1.0 to 2.9). We use k = 2 as a labelled assumption." |
| Method, radar | top row | MCP, 1.45% / 0.26% of posts, growth x5.69, Rising, first seen 2025-04 |

If the app shows a different value, use the screen as the truth and edit the spoken number in the script. The Method tab backtest values do not change with the As-of slider, but the AI-share chart does.

## 5. Take order (one pass, in this order)

The order avoids resets: the slider is moved back before the Method tab, and Refresh comes last because it resets the slider and changes the data.

1. Slides 1 to 3 (record separately, 0:00-0:40).
2. Roles tab: Aina, cards, Fast, back to Moderate (0:40-1:21).
3. Pathway tab: choose Backend Engineer, stages, tick, calendar download, SDG links (1:21-2:05).
4. Skill detail: Python (2:05-2:20).
5. As-of slider to 2023-12, "What happened", slider back to 2026-10 (2:20-2:44).
6. Method tab: model table, band, label (2:44-3:09), then exposure, k line, radar (3:09-3:34).
7. Refresh live data (3:34-3:45).
8. Slides 4 to 8 (3:45-5:45).

## 6. Fallback plan

- [ ] **Backup take on the local copy.** Run `streamlit run app.py` from `main` and record the same demo at `http://localhost:8501`. The local copy shows the committed snapshot, so its numbers match section 4. Keep it unedited as `backup-local-demo` outside the repo.
- [ ] **If the Replit site is slow or down during the take:** stop, wait one minute, reload and retry. After two failures, record the demo on the local copy and say nothing about it in the video (the numbers are the same). Record the real-site Refresh later and cut it in.
- [ ] **If Refresh fails during the take:** keep the take. The app then shows "Refresh failed: ..." and "The last good data is shown: data as of ...". Replace the spoken line in row 7 with: "If a source is down, Verity keeps the last good data and shows its date." Do not hide the failure.
- [ ] **If the new thread makes the numbers change:** do not re-record the earlier rows. Speak the numbers you see only if they differ from the script, and fix the script text in the same commit as the video.
- [ ] **Backup pitch video for the final round.** The organisers want a backup video on YouTube for 1 Nov, used only if the live demo fails (BRIEF). Plan a second recording after the final-round changes.
- [ ] **Live-site check on pitch day.** Open the URL 10 minutes before pitching and click through the tabs once.

## 7. Shot list

Times follow the script. "Hold" is how long the screen stays still while the voice speaks the key number.

| Shot | Script row | Time | Screen | Action | Hold |
|---|---|---|---|---|---|
| S1 | 1 | 0:00-0:05 | Slide 1 | Title; voice starts at 0:01 | 5 s |
| S2 | 1 | 0:05-0:30 | Slide 2 | AI-mention chart; highlight 6.4% and 54.6% | 25 s |
| S3 | 1 | 0:30-0:40 | Slide 3 | Aina and the five boxes; the word "synthetic" visible | 10 s |
| D1 | 2 | 0:40-0:48 | App, Roles tab | Select the example profile "Aina, junior Python dev (synthetic)"; skills list visible | 3 s |
| D2 | 2 | 0:48-1:02 | Card #1 | Point at the match bar (66%), the gaps list, the Role demand line | 4 s on the bar |
| D3 | 2 | 1:02-1:21 | Sidebar and card #1 | Click "Fast AI disruption (k = 2, an assumption)"; point at the caption; click Moderate | 5 s on the caption |
| D4 | 3 | 1:21-1:31 | Card #1, Pathway tab | Click "Choose this as my target role"; open the Pathway tab | 2 s |
| D5 | 3 | 1:31-1:49 | Pathway, stages | Scroll slowly past stages 1, 2 and 3 | 3 s per stage |
| D6 | 3 | 1:49-2:05 | Daily to-do, Export, SDG links | Tick the first task (progress 10%); click "Download calendar (.ics)"; scroll to the two SDG sentences | 3 s on the bar, 3 s on the SDG lines |
| D7 | 4a | 2:05-2:20 | Skill detail | Open the tab; choose Python; point at the chart bands | 5 s |
| D8 | 4b | 2:20-2:44 | Sidebar and Skill detail | Slider to 2023-12; scroll to "What happened"; slider back to 2026-10 | 4 s on the diamond |
| D9 | 5 | 2:44-3:09 | Method tab | Model table (naive3 row); "How good is the band?"; "How good is the trend label?" | 3 s each |
| D10 | 6 | 3:09-3:34 | Method tab, lower | "Exposure cross-check" table and the Contested line; the "k from data" line; the radar's MCP row | 3 s each |
| D11 | 7 | 3:34-3:45 | Sidebar | Click "Refresh live data"; show the green message and the header date | 3 s on the date |
| S4 | 8 | 3:45-3:55 | Slide 4 | How it works | 10 s |
| S5 | 8 | 3:55-4:32 | Slide 5 | Error bars and the 93.8% callout | 37 s |
| S6 | 9 | 4:32-5:00 | Slide 6 | Profiles and disagreement | 28 s |
| S7 | 10 | 5:00-5:20 | Slide 7 | Limits | 20 s |
| S8 | 11 | 5:20-5:45 | Slide 8 | SDG close, team name, links | 25 s |

Editing rules:

- [ ] Cut spinners and waits so the timestamps above hold. The first As-of calculation and the Refresh can both take several seconds.
- [ ] Keep the pointer on the number the voice is saying.
- [ ] No music is needed. If you add any, use a track you have the right to use and declare it.
- [ ] Final length: at most 7:00. The target is 5:45. Check the exported file, not the timeline.
- [ ] Watch the export once in full, on a phone-size window, to check the tables are readable.
- [ ] After upload, open the YouTube link in a private window and check that it plays. Broken links are the team's own risk (BRIEF).

## 8. Rehearsal log

| Take | Date and time | Total length | Row 8 starts at | Cuts used | Problem noticed |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
