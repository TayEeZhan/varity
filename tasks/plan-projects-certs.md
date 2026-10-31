# Plan: Project and Cert stations (proof that a skill gap is closed)

Written 31 Oct 2026. **Built 1 Nov 2026** except: live catalog collectors (GitHub, Kaggle, HN briefs), the LLM "why" sentence (a code template is used) and the offline jury eval. See `docs/architecture.md` 3.21.
Preview mock-up (not app code): `projects-certs-preview.html` in the session scratchpad, served by the `projects-certs-mock` entry in `.claude/launch.json` (port 8131).

## Why
Judge feedback: "Finishing tasks does not mean a professional skill gap is closed."
Fix: each skill climbs an evidence ladder, and only outside proof moves it up.

| Level | Meaning | Proof |
|---|---|---|
| Learned | Tasks done | User ticks (as today) |
| Applied | Built something real | A project repo that passes review |
| Certified | Outside issuer agrees | A verified badge (Credly) |

No viva (oral check). Dropped by the user.

## Rules that stay in force
- LLMs never produce rankings, scores or numbers. Ranking is a formula.
- Job data is Hacker News only.
- An LLM may label or extract only with quotes that code checks.
- Hard rules sit outside the LLM. The LLM cannot override them.
- Say "graded by an LLM jury", never "human-checked".

## Part 1: Project station

### Backend flow
1. **Catalog collector** (scheduled, no LLM except step c)
   a. GitHub: `good first issue` / `help wanted` issues in active repos, via the REST API.
   b. Kaggle: datasets and competitions, via the Kaggle API (free, account key).
   c. Briefs from HN job posts: an LLM pulls the task and the skills **with quotes**. Code drops any brief whose quotes are not found in the post.
2. **Rule filter**: drop dead repos, closed issues and briefs with no acceptance criteria.
3. **Recommender (formula, no LLM)**: match % = coverage of the user's gap skills + target-role weight from HN demand. Gives Medium and Hard options.
4. **"Why this fits you" line (LLM)**: written only from facts the formula already produced.
5. **Board**: acceptance criteria are fixed when the user boards. Each criterion maps to one skill.
6. **Submit**: the user connects GitHub (see Part 3) and picks the repo.
7. **Hard checks (code, no LLM)**. If one fails, stop. The jury does not run and no LLM cost is spent.
   - The user owns the repo (from the GitHub App installation).
   - Commits are spread over time (not one dump).
   - The latest GitHub Actions run passed.
   - PR merged (for open-source issues).
   - The demo URL returns 200 (if given).
8. **Live AI jury per criterion** (see Part 4).
9. **Ladder update**: all pass → skill moves to Applied. Some fail → "Not yet" with a fix note per item.

### Mistakes and failures
| Case | What happens |
|---|---|
| Repo not owned by the user | Not possible with GitHub connect. Pasted-link fallback is labelled "Unverified owner". |
| CI failed | Stop at hard checks. Show the failing run link. |
| Criteria fail | "Not yet (n/5)". Fix note per item. Re-check is free. |
| Failed item needs a skill not on the route | Service-change band proposes a new stop (Part 5). |
| User disagrees | "Disagree?" sends one item back to the jury once, with the user's note. Hard rules still apply. |
| User gives up | Abandon or switch project. Old stop gets a CANCELLED stamp and stays visible. |

## Part 2: Cert station
1. **Catalog**: hand-curated list of credible certs per role (for example AWS Data Engineer Associate). No LLM.
2. **Rank (formula)**: share of HN hiring posts for the role that name the cert × the user's syllabus coverage.
3. **"Why this cert" line (LLM)**: explanation only.
4. **Add to my plan**: syllabus topics not on the route become new stops, through the service-change band.
5. **"I passed"**: the user pastes a Credly badge URL. Code fetches it from an allowed domain only and checks the name, the cert title and the issuer. Pass → Certified. Otherwise the cert is shown as "Self-reported".
6. No live jury for certs. A badge is verified or it is not.

## Part 3: GitHub connect
- Use a **GitHub App** (registered on GitHub, not on Replit). Replit only hosts the callback and webhook URLs and holds the secret in Replit Secrets.
- Read-only permissions: metadata, contents, pull requests, actions. The user picks the repos.
- Proves ownership. Works for private repos.
- Webhooks (`push`, `workflow_run`, `pull_request`) replace polling. Check the webhook signature on every event.
- Rate limit 5,000 requests/hour per installation (free). Install tokens expire after 1 hour; the backend refreshes them.
- Fallback: pasted public link, labelled "Unverified owner".
- Kaggle API is free with an account key.

## Part 4: LLM use and the AI jury

### Where an LLM is used
| Part | LLM? | Job |
|---|---|---|
| GitHub / Kaggle catalog | No | API filters |
| HN project briefs | Yes, narrow | Extract task and skills with quotes; code checks quotes |
| Project ranking (match %) | **No** | Formula |
| "Why this fits you" | Yes | Explanation only |
| Hard checks | No | GitHub API, HTTP |
| Criterion review | **Yes, live jury** | See below |
| Cert catalog and rank | No | Curated list, formula |
| "Why this cert" | Yes | Explanation only |
| Badge check | No | Fetch and compare |
| Service-change wording | Yes | Wording only; code decides the stop |

### A. Live jury (grades each submitted project)
- 3 different models each get the repo files, the CI log and one criterion. Each returns `{vote, reason, file:line}`.
- Code checks each citation: the file and line must exist and contain what the juror claims. A pass without a valid citation counts as a fail.
- 2 of 3 passes the item.
- Models from the current credits (see `plan-credits.md`): Claude Haiku (Replit), `gpt-5.4-mini` and `deepseek-v4-flash` (KrackedDevs). The mock-up shows example names only.
- Cost and time: 3 calls per criterion, about 30–60 s per review. Hard checks run first so failed repos cost nothing.

### B. Offline jury (LLM_JURY_PLAYBOOK method)
- Grades our own LLM parts against a plain baseline: HN brief extraction and the "why" lines.
- The model under test is never a juror. The jury grades; it trains nothing.
- Score with precision@k. The formula stays the default unless the numbers say otherwise.
- Optional: the jury grades whether the cert list fits each role.

## Part 5: Service-change band (re-plans)
- **Trigger (code, not LLM)**: an item fails review → look up the skill it tests → if the route has no stop for that skill, propose one (for example "API testing", 3 tasks, before Project). Certs: syllabus topics not on the route (for example Glue, Kinesis).
- If the stop already exists, or the miss is small, no band. Only the fix note shows.
- **Keep** adds the stop (dashed yellow segment on the line). **Revert** changes nothing.
- Varity never changes the route without asking.

## Part 6: Frontend and UI (Transit Map, per `frontend/DESIGN.md`)

### Line map (Pathway)
- Project and Cert stops are **interchange capsules** with drawn SVG icons (repo, badge, lock).
- Current stop: yellow halo + pulse ring, which moves on progress. Terminus (target role) is the tall capsule.
- Added stops: dashed yellow segment. Hover a stop to light it and dim the rest. Click or Enter opens it.
- Yellow `--signal` only for: re-plans, "You are here", the active tab, selection.

### Platform sign
Black band with a white plate for status: NEXT STOP, IN PROGRESS, REVIEWING, NOT YET, DEPARTED, ARRIVED.

### Project stop
- **"Departures from Project" timetable**: line letter · match % · title · skills · "Why" line · source link. Heading says "Ranked by skill match, a formula. AI writes only the 'why' line."
- Rows expand in place: criteria list, the twist, "Board this project".
- HN briefs show a **FROM HN POSTS** notice: black plate, each quote with "found in HN post · date".
- Submit: Connect GitHub → repo picker. Fallback link field with live validation.
- Reviewing: animated steps (repo found → commits → CI → "3 AI models vote on each item").
- Results: "Not yet (3/5)" or "Project passed" with APPLIED stamp. Per item: evidence `file:line` or a fix note, and "Disagree?".
- **Jury track per item**: 3 station dots on a short line (filled = pass, red ring = fail), "n of 3 pass · majority pass/fail". Opens a juror timetable: tick/cross · letter bullet · model name · one-line comment. Hovering a juror row lights its dot and dims the others. Footnote: "A pass counts only if code finds the cited line. 2 of 3 passes the item."
- Abandon or switch: CANCELLED stamp in `--fall`, title struck through, date.

### Cert stop
- Cert timetable ranked by formula ("Named in n% of posts · cost · prep time · official page").
- "Add to my plan" → service-change band. "I passed" → badge checks one by one → CERTIFIED stamp.

### Other tabs
- **Today**: the boarded project's criteria as tickable items, plus timetable tasks.
- **CV & routes**: each route shows "n Applied · n Certified"; evidence card (repo, CI, jury result) with a share button.
- Skills meter on the line: Learned · Applied · Certified.

### Design rules kept
Schibsted Grotesk, 42px pill buttons with at most one primary per screen, headings on a 3px rule, synthetic chip on every screen, tabular digits, `prefers-reduced-motion` respected, no horizontal page scroll at 375px.

## Build order (when approved)
1. Data model: evidence level per skill; project, criterion, review and vote tables.
2. GitHub App: install flow, webhooks, hard checks. Tests with recorded API responses.
3. Catalog collector + recommender formula + tests.
4. Live jury: prompt, citation check, majority vote. Tests with a fake client (bad citation → fail).
5. Cert catalog, rank formula, Credly check.
6. Service-change trigger (criterion → skill → stop).
7. Frontend from the mock-up, per DESIGN.md.
8. Offline jury eval in `eval/` (reuse sampling, vote parsing, precision@k).
9. Update `docs/architecture.md`, `HANDOFF.md` and the Technical & Tools Declaration.

## Decisions (31 Oct 2026)
- No per-user daily cap on jury reviews (user: "nvm").
- Jurors: Claude Haiku (Replit), `gpt-5.4-mini` and `deepseek-v4-flash` (KrackedDevs). Confirmed.

- Applied and Certified **raise the route match %** (user, 31 Oct 2026). Rule below.
- Credit for Learned (self-reported) skills: **0.5**. Confirmed by the user.

## Scoring rule: evidence credit in the match %
**What the code does today.** `engine/roles.py` `match_roles`: match = weight of the role's skills the user has ÷ total weight. "Has" is yes or no. A skill counts as held when the profile has any evidence for it (`advisor/mapping.py` `map_profile`). Finishing a skill's tasks already adds evidence (`POST /api/profile/learned`, source `pathway`, method `task_done`), so **Learned already counts in full today**. If Applied only adds more evidence, the score does not move.

**Change.** Each held skill gets a credit from its strongest evidence. Match = Σ (weight × credit) ÷ total weight.

| Strongest evidence | Credit |
|---|---|
| CV, stated (work, project, education, certification context) | 1.0 |
| Certified (verified badge) | 1.0 |
| Applied (project passed the jury) | 1.0 |
| Learned (pathway tasks done, self-reported) | 0.5 |
| CV skills list only, or inferred from the skill graph | as today (1.0), unchanged |

- The credits are **assumptions we chose**, not measured values. Label them like `k` on the Method page ("Credit for self-reported learning: 0.5, an assumption").
- Effect: a Learned skill now adds half its weight. Applied or Certified adds the other half. This is the judge's point in numbers: finishing tasks is not the same as proving the skill.
- Users who ticked tasks before this change see their match % drop. Show a one-time "Plan changed" note: "Learned skills now count half until a project or cert proves them."

**New evidence values** (`backend/signals/intake/models.py`):
- `Source` adds `"project"` and `"credly"`. `"github"` already exists and can be used for the project.
- `Method` adds `"jury_pass"` and `"badge_verified"`.
- Applied: `Evidence(source="github", method="jury_pass", context="project", note=<repo + review id>)`.
- Certified: `Evidence(source="credly", method="badge_verified", context="certification", note=<badge URL>)`.
- Schema change: bump `schema_version` or confirm old profiles still load.

**Where it shows.**
- The "Why NN%?" panel lists each skill with its level and credit (for example "SQL · Learned · ½").
- "Top 3 skills that would raise the score" also counts proving a Learned skill as a raise.
- The radar and the skills meter use the same level.

**Code that changes for this.** `engine/roles.py` (`_user_set`, `match_roles`, `top_gaps`), `advisor/mapping.py` (return the credit with the years), `intake/models.py`, `trendsignal/web/roles_api.py` (the Why panel), the frontend Why panel. Tests: credit per level, strongest evidence wins, a Learned → Applied raise, old profiles still load.

**Risk.** Route order can change for current users. The WP2 example (Aina → Backend Engineer 0.759) must be re-run and the HANDOFF numbers updated.

- A passed **Medium** project is enough for Applied. Hard is optional and gives the same credit (user, 31 Oct 2026).

## Open questions
None.

## Review: gaps, affected code, hidden risks

### Gaps in the plan above
1. **Reuse the existing re-plan band.** `frontend/screens.js` (`planBandInner`) already shows "Plan changed" with Keep change / Revert, plus the `.service` style. Part 5 must add a case there, not build a second band.
2. **Skill state model.** Today a skill is held (from the CV) or a task is done (`STATE.done`). The plan does not say where Learned / Applied / Certified is stored, or whether Applied changes the route match % (`held_skills` in `evidence_api.py`, the WP2 "Why NN%?" panel, the radar). Decide this first.
3. **Anonymous users.** Profiles are keyed by `owner_key` ("t:" browser token or "u:" account, `accounts_store.py`). A GitHub install on an anonymous profile is lost when the browser token is cleared. Rule: GitHub connect needs a signed-in account. If not signed in, "Connect GitHub" asks the user to sign in first. The account merge must carry project data.
4. **Retention and privacy.** The daily 365-day purge (`purge_stale_accounts`) must also delete projects, reviews, votes and GitHub install links. `frontend/privacy.html` says only Anthropic sees user data. The jury sends repo code to OpenAI-gateway and DeepSeek models too. Update the page and add a consent tick before the first review. Private repos: send code to the jury only after that tick.
5. **Repo size.** The plan does not say what the jury reads. Rule: only files matched to the criterion (by path and keyword), with a token cap per call. Skip `node_modules`, data and binaries. Otherwise cost and time grow without limit.
6. **Prompt injection from repos.** A README can say "vote pass". The citation check limits this, but also: put repo text in a fenced data block, tell jurors it is data, and fail any vote that cites a line which does not exist.
7. **Juror failure.** If a juror times out or is out of credit, the vote is "no answer". Rule: 2 answers that agree decide the item. Otherwise show "Review delayed, try Re-check". Never pass an item on 1 vote.
8. **Webhook endpoint on Replit.** It needs a public URL and must survive republish. Rate-limit Re-check (one running review per project) like `POST /api/data/refresh`.
9. **Week locks.** Pathway tasks lock by week ("Finish week N first"). A stop added before Project must slot into a week without locking the user out of ticks they already have.
10. **Name clash.** The app already has an **Evidence** area (radar and Method page). Call the new card "Proof", not "Evidence card".
11. **Design source.** `frontend/PRODUCT.md` exists. The mock-up check did not see it because the mock-up is in the scratchpad. Re-run the design check on the real files when building.
12. **Offline jury.** `backend/signals/eval/jury.py` is Sheng Kuan's and calls OpenRouter. Reuse its vote parsing and metrics, but ask him before changing it.
13. **Declaration and Method page.** Add GitHub API, Kaggle API, Credly and the 3 jurors to the Technical & Tools Declaration and the Method screen.

### Code that changes
| Area | Files |
|---|---|
| Storage | `trendsignal/db.py` or a new store next to `web/accounts_store.py` (projects, reviews, votes, certs, GitHub installs) |
| API | new `web/projects_api.py` (catalog, board, submit, review, webhook), wired in `web/app.py` |
| Auth | `web/auth_api.py` (GitHub connect needs sign-in), account merge in `accounts_store.py` |
| Jobs | `trendsignal/scheduler.py` (catalog collector, purge of new tables) |
| LLM | `engine/llm_client.py` (KrackedDevs jurors), Replit Claude path, budget guard per job |
| Pathway | `engine/pathway.py` (new stops, week slots), `advisor/planner.py` if stops come from there |
| Scores | `engine/roles.py`, `advisor/mapping.py`, `intake/models.py`, `roles_api.py` (see Scoring rule) |
| Frontend | `screens.js` (line map, band case), `screens-cv.js` (Applied / Certified counts, Proof card), `app.js` (routes, state), `styles.css` |
| Docs | `docs/architecture.md`, `HANDOFF.md`, `privacy.html`, Declaration |
| Tests | new tests for the citation check, majority vote, failure rules, webhook signature, purge |

### Hidden risks
| Risk | Effect | Guard |
|---|---|---|
| Jurors agree wrongly (shared training) | False "Applied" | Citation check; spot-check a sample by hand before launch |
| Juror credit runs out | Reviews stop mid-demo | Low risk: $100 credit on a teammate's account (user, 31 Oct 2026). Put that key in Replit Secrets (never in the repo), raise `KD_CAP_USD` for the jury job, and still show "Review delayed", never a fake pass |
| Users game it (copy a repo, one big commit) | False proof | Ownership via the App, commit-spread rule, fork detection |
| DeepSeek sees private code | Privacy complaint | Consent tick; option to use only Claude + GPT for private repos |
| GitHub App secret leak | Account access | Replit Secrets only; read-only permissions; rotate on leak |
| Credly page changes layout | Badge checks fail | Fall back to "Self-reported"; never block the user |
| Catalog from HN briefs is thin for some roles | Few projects | Show GitHub and Kaggle first; say "few briefs for this role" |
| Demo time | Review takes 30–60 s on stage | A pre-run demo project with stored votes, labelled synthetic |
| Scope | Too much for the time left | Build order: steps 1, 2, 4, 7 are the core; certs and the offline jury can wait |
