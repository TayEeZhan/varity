# Verity demo and recording checklist (draft)

Team: Hokkien Mee Is Purple (Ee Zhan, Sheng Kuan). Updated 24 Oct 2026 for the Varity-only app (the Streamlit demo steps were removed). Matches `docs/submission/pitch-script.md` (5:45 target, 7:00 hard maximum; each 30 s over costs 1 point).
Tick each box as you do it. Items marked [TEAM TO FILL] need a decision from you.

## 1. Decide first

- [ ] Who drives the screen? One person drives all of the demo. Both speak, as the script assigns. [TEAM TO FILL: driver]
- [ ] Recording tool and output: 1920 x 1080, 30 frames per second, the system audio off, one microphone. [TEAM TO FILL: tool]
- [ ] Voices: record the voice live over the demo, or record the screen first and the voice after. A voice-over after the screen take lets you cut waits and keeps the timing exact. [TEAM TO FILL: choice]
- [ ] YouTube visibility (public or unlisted) and the upload account. The organisers' Submission Files tutorial video should say. [TEAM TO FILL]

## 2. The day before

- [ ] Both members read the script aloud with a stopwatch, three times. Log each take in section 8.
- [ ] Both members read `docs/ml-forecaster.md`, the backtest part of `docs/build-plan.md`, and `docs/submission/qa-prep.md`. Sheng Kuan speaks the forecast-test rows (5 and 8) and may get those questions.
- [ ] Check the Replit deployment (live, published 24 Oct 2026). Open https://verity--eezhan0805.replit.app in a private window. It must show the eight Varity screens and real data, not an "offline snapshot" label on Job forecast or Skills radar. If the page still shows the Streamlit app, the deployment is old.
- [ ] Compare the page with the numbers in section 4. If a value differs, find out why (a refresh, a new snapshot) and fix the script, not the screen.
- [ ] CV intake: the demo uses "Try an example", which needs no model. Show the CV upload in the video only if you have run it on the deployed app. Use a synthetic CV only, never a real one. The CV-intake Claude call is not yet confirmed live. With no key, a keyword pass takes over, and the page then shows no Claude result. Check which of the two you will show.
- [ ] The Skills radar has a "Fetch latest HN" button (one fetch per 10 minutes). Do not click it while recording. The Hacker News numbers are the committed snapshot (as of 2026-10) unless a fetch or the daily refresh changed them. If the data files changed since section 4 was written, repeat the number check. The Signals screen is different: the server re-ranks it while it runs, so its stories change.
- [ ] Run the app once locally as a second source for the backup take (section 6): `pip install -r requirements.txt`, then `cd backend/signals` and `python -m trendsignal serve --port 8000`, then open http://localhost:8000.
- [ ] Choose the account for the recording: a clean browser profile with no extensions, no saved logins, and no bookmarks bar.

## 3. 30 minutes before the take

- [ ] Close every other browser tab and window. Quit chat apps, mail and cloud-sync pop-ups. Turn on Windows Focus assist (do not disturb).
- [ ] Browser window at 1920 x 1080 with the page zoom at 110%. If the model table or the exposure table is hard to read in a 720p preview, raise it to 125%. (A suggestion: test it with a short clip.)
- [ ] Theme: pick one (light or dark) and keep it for every shot, including the slides. The app follows the browser theme.
- [ ] Mouse: slow pointer speed, a visible pointer. Move it to point at things and leave it still while you speak.
- [ ] Microphone: record 10 seconds, play it back, check for fan noise and clipping. Close the window or door.
- [ ] Phone on silent. Charger plugged in. Stable network (wired if possible).
- [ ] Wake the Replit app: open the URL 10 minutes before and click through all eight screens once.
- [ ] Open Signals once. On a fresh deploy with no ranked run, one pipeline pass starts in the background, so Signals can show the offline snapshot until it finishes. Wait until the badge says live data.
- [ ] Optional sign-in, not yet tested on the live app. In a private window on the live URL, click "Sign in", sign in with Replit, check that the profile and ticks stay after a reload, then sign out and delete the test account. Add a sign-in step to the demo script only if all of this works live. The demo does not need it: "Try an example" works without an account. [TEAM TO FILL: result and date]
- [ ] Use a private window so no saved profile, route or ticks remain from an earlier take. Press "Try an example" fresh at 0:40.

## 4. State to check at 0:40 and the numbers to expect

Committed snapshot: `data/skill_scores.json` generated 2026-10-21T21:09:03Z, as of 2026-10. Values below come from the files and from a read-only run of the backend's own functions (`advisor.service.suggestions` and `advisor.service.pathway`, model switched off) on 24 Oct 2026. The screen text in the "Expect" column is from the front-end code, not from a recording: confirm it in the running app.

| Screen | Setting | Expect |
|---|---|---|
| Job forecast, Skills radar | badge | "Real data · HN hiring posts · as of 2026-10" (with "(month in progress)" while the thread is open). "Offline snapshot" means the server was not reached |
| CV & routes | Try an example | "Aina (synthetic)": Python, SQL, PostgreSQL, Docker, AWS |
| CV & routes, route #1 | Backend Engineer | "#1 Backend Engineer"; 66% "match now"; "Strong fit, rising demand"; "Demand: Rising (job forecast, 2026-10)"; 4 skills to learn: Go, Kubernetes, Terraform, Node.js; reason chips with a source and date; an SDG tag; a TalentCorp MyCOL badge (Software Developers, direct) |
| CV & routes, ranking | order | #1 Backend Engineer (66%), #2 AI/LLM Application Engineer (39%), #3 Data Engineer (51%), #4 Data Scientist (43%), #5 Platform/DevOps Engineer (38%), #6 ML Engineer (24%), #7 Full-stack Web Developer (22%); "Low match, not ranked": Mobile Developer (0%). "Ranked by the formula (match 70% + demand 30%)" when no model is used |
| CV & routes, "If AI speeds up" (API value `fast`) | card #1 note | "If AI speeds up (estimate): about -6.1% role demand vs expected. Does not change the ranking." The order is the same as above |
| Pathway | Backend Engineer, 5 hours a week | 4 skills, 15 daily tasks, about 7.5 hours. Stage 1 Node.js; stage 2 Go, Kubernetes; stage 3 Terraform (the stage reasons show when you hover a station; confirm in the app) |
| Pathway, SDG lines | text | "SDG 4.4 ... adds 4 job-listed skills in 7.5 hours (estimate) at RM0 cost using free resources." "SDG 8.5 ... moves you toward Backend Engineer (role demand: Rising, 10.6% ... vs 9.4% ...)" |
| Today | after the plan loads | "Next stops" with minutes and a reason for each stop; an "Open CV builder" button. Progress reads "x of N stops done" (N is the number of stops in the plan), not a percentage of minutes |
| Job forecast | Backend Engineer row | Rising; 393 posts in the last 12 months vs 366 (10.6% vs 9.4%); share now 10.2%; 12-month estimate 10.4%, band 8.3% to 12.9% |
| Skills radar, Python | Expected (API value `moderate`) | 12-month estimate 26.3%, band 22.1% to 30.9%; trend label "No clear change" |
| Method, forecast table | test h=12 | naive 1.81, naive3 1.66, drift 2.13, damped 2.27; chosen model naive3 |
| Method, band | coverage | 93.8% (target 80%), mean width 8.4 pp |
| Method, label | hit rate | 67.2% (n = 720); Rising 60.5%, Falling 71.9% |
| Method, exposure | stances | "Most indices agree with our stance: language. Contested: ai_ml, cloud_devops, data, framework, practice."; correlation line with Microsoft -0.79 |
| Method, k line | text | "The data cannot pin k down (point estimate 1.8 per 12 months, 95% CI -1.0 to 2.9). We use k = 2 as a labelled assumption." |
| Signals | list | Live ranked stories from the last run. The numbers and titles change with each run: do not read them aloud |
| Flow map | note | Says that Google sign-in (step 2) and Google Tasks sync back (step 10) are not built. Push to Google Tasks (step 8) is built when `GOOGLE_CLIENT_ID` is set. Replit sign-in is built; it is a different feature |

If the app shows a different value, use the screen as the truth and edit the spoken number in the script.

## 5. Take order (one pass, in this order)

The order follows the navigation, so nothing is reset between steps. Start with a fresh private window.

1. Slides 1 to 3 (record separately, 0:00-0:40).
2. CV & routes: Try an example (Aina), card #1, "If AI speeds up", back to "Expected" (0:40-1:21).
3. Pathway, then Today: stations, SDG lines, next stops (1:21-2:05).
4. Skills radar: Python (2:05-2:20).
5. Job forecast: Backend Engineer (2:20-2:44).
6. Method: model table, band, label (2:44-3:09), then exposure and k line (3:09-3:34).
7. Signals (3:34-3:45).
8. Slides 4 to 8 (3:45-5:45).

## 6. Fallback plan

- [ ] **Backup take on the local copy.** Run `cd backend/signals && python -m trendsignal serve --port 8000` and record the same demo at `http://localhost:8000`. The local copy shows the committed snapshot, so its numbers match section 4. Signals will show the offline snapshot or a fresh local run, so do not read its stories aloud. Keep it unedited as `backup-local-demo` outside the repo.
- [ ] **If the Replit site is slow or down during the take:** stop, wait one minute, reload and retry. After two failures, record the demo on the local copy and say nothing about it in the video (the numbers are the same).
- [ ] **If the Signals screen shows "offline snapshot" during the take:** keep the take. The page says so on its own. Say only: "If the live run is not reachable, Varity shows a dated offline snapshot and says so." Do not hide it.
- [ ] **If the data files change before the take:** do not re-record the earlier rows. Speak the numbers you see only if they differ from the script, and fix the script text in the same commit as the video.
- [ ] **Backup pitch video for the final round.** The organisers want a backup video on YouTube for 1 Nov, used only if the live demo fails (BRIEF). Plan a second recording after the final-round changes.
- [ ] **Live-site check on pitch day.** Open the URL 10 minutes before pitching and click through the screens once.

## 7. Shot list

Times follow the script. "Hold" is how long the screen stays still while the voice speaks the key number.

| Shot | Script row | Time | Screen | Action | Hold |
|---|---|---|---|---|---|
| S1 | 1 | 0:00-0:05 | Slide 1 | Title; voice starts at 0:01 | 5 s |
| S2 | 1 | 0:05-0:30 | Slide 2 | AI-mention chart; highlight 6.4% and 54.6% | 25 s |
| S3 | 1 | 0:30-0:40 | Slide 3 | Aina and the five boxes; the word "synthetic" visible | 10 s |
| D1 | 2 | 0:40-0:48 | App, CV & routes | Press "Try an example", then Aina (synthetic); the skills list is visible | 3 s |
| D2 | 2 | 0:48-1:02 | Route #1 | Point at the match (66%), the gap chips and the Demand line; hover one reason chip | 4 s on the match |
| D3 | 2 | 1:02-1:21 | AI scenario switch and route #1 | Press "If AI speeds up (estimate)"; point at the estimate note; press "Expected (estimate)" | 5 s on the note |
| D4 | 3 | 1:21-1:31 | Pathway | Open Pathway; the route map is visible | 2 s |
| D5 | 3 | 1:31-1:49 | Pathway, route map | Hover the stations for Node.js, Go, Kubernetes and Terraform | 3 s per station |
| D6 | 3 | 1:49-2:05 | SDG lines, Today | Scroll to the two SDG sentences; open Today; hold on "Next stops" | 3 s on the SDG lines |
| D7 | 4a | 2:05-2:20 | Skills radar | Select the Python dot; the detail panel is visible | 5 s |
| D8 | 4b | 2:20-2:44 | Job forecast | Hold on the Backend Engineer row: share now, 12-month bar and band, the post counts | 4 s on the band |
| D9 | 5 | 2:44-3:09 | Method | Model table (naive3 row); "Band coverage"; "Trend label hit rate" | 3 s each |
| D10 | 6 | 3:09-3:34 | Method, lower | "AI exposure" cross-check table and the contested lines; "The size of the AI effect (k)" with its tag | 3 s each |
| D11 | 7 | 3:34-3:45 | Signals | Open Signals; hold on the top of the ranked list | 3 s |
| S4 | 8 | 3:45-3:55 | Slide 4 | How it works | 10 s |
| S5 | 8 | 3:55-4:32 | Slide 5 | Error bars and the 93.8% callout | 37 s |
| S6 | 9 | 4:32-5:00 | Slide 6 | Profiles and disagreement | 28 s |
| S7 | 10 | 5:00-5:20 | Slide 7 | Limits | 20 s |
| S8 | 11 | 5:20-5:45 | Slide 8 | SDG close, team name, links | 25 s |

Editing rules:

- [ ] Cut spinners and waits so the timestamps above hold. The first load of Signals and of Method can take several seconds.
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
