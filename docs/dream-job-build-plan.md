# Dream-job build plan (no code changed yet)

Revised 24 Oct against branch `fix/advisor-ranking-truncated` (after PR #21). The first draft of this plan predated the advisor work; most of its backend is **already built**, so the scope is now small.

Feature: on the CV screen the user picks a **destination** (dream job) from the roles we have data for, or "Not sure yet". After analysis the journey planner shows that role pinned on top as **Your destination**, with its own pathway. The user can switch to a suggested route at any time.

Pitch line: *"Tell us the job you want. We'll show how close you are and the fastest way to get there."*

## 1. What already exists (do not rebuild)

| Piece | Where |
|---|---|
| Intake skill → taxonomy mapping | `backend/signals/advisor/mapping.py` |
| Ranked routes, low-match list, unmapped skills, `targetRoleId` | `GET /api/roles/suggestions` (`roles_api.py:69`, `advisor/service.py`) |
| Save the chosen route | `POST /api/profile/target-role` (`roles_api.py:82`) |
| Pathway for any route | `GET /api/pathway?roleId=` (`roles_api.py:95`) |
| `target_role` accepted on save and checked against the user's routes | `POST /api/profile/apply` (`cv_api.py:237`) |
| Switching routes → rebuilds the pathway → jumps to Pathway | `data-act="route"` handler (`frontend/screens.js` ~line 397) |
| Current route row style | `.route.is-current` + "Your current route" tag |

## 2. What is left to build

| # | Change | Where | Size |
|---|---|---|---|
| 1 | **Destination select** on the CV review step; sends `target_role` with the existing apply call | `frontend/screens.js` (CV panel), `frontend/app.js` | Small |
| 2 | **Role list for the select** before suggestions exist: reuse `GET /api/roles/forecast` (ranked roles), no new endpoint | `frontend/app.js` | Small |
| 3 | **Pin the destination first** in `liveRoutes()`, with the destination plate | `frontend/screens.js` | Small |
| 4 | **Low-match destination gets a full row.** Today a low-match role only appears in the one-line "Low match, not ranked" note (name + %). The destination needs its gap and outlook, so `advisor/service.py` returns the full role row for `targetRoleId` when it sits in `low_match`. | `backend/signals/advisor/service.py` + test in `tests/test_advisor.py` | Small |
| 5 | Styles for the select and the plate | `frontend/styles.css` | Small |
| 6 | Pitch copy: "destination" story | `docs/submission/pitch-script.md` | Small |

Not touched: engine modules, `data/`, mapping, the pathway engine, Signals, Job forecast, Today.

## 3. Frontend spec (matches `frontend/DESIGN.md`)

The design is a **transit map**: a pathway is a line, skills are stations, the **future role is the terminus**. So the dream job is the user's **destination**. Use that word, not "dream job" or a ★, in the UI.

### 3.1 Destination select (CV screen)
- Sits under the kept-skills review, above the existing save action. Label: **"Destination (optional)"**, with helper text in `--ink-3`, `--t-xs`: "Pick the role you want. We'll still show other routes."
- A native `<select>` styled like a `.btn`: **42px tall, 2px `--ink` border, pill radius**, Schibsted Grotesk, `--paper` ground. Options: ranked role names, then **"Not sure yet"** (the default).
- **Not a primary button.** The screen keeps its one primary action (save). The select is a plain control.
- Focus: the same visible focus ring as `.btn`. Full width at ≤640px.
- If the role list fails to load, hide the select. Saving still works without a destination.

### 3.2 Destination plate (journey planner)
- The destination row is rendered **first** with the existing `liveRouteRow` markup, so match %, facts, outlook, gap chips and reasons all look the same as other routes.
- Next to the role name: a **sign plate**, the same grammar as the black "Service change" plate. Black `--ink` ground, white text, 800 weight, `--t-xs`, uppercase, square corners (never rounded): **DESTINATION**.
- Under the suggested routes, a section heading on the 3px black rule: **"Other routes"**, so the pinned row reads as separate.
- When the destination is also the current route, the row keeps `.is-current` (`--paper-2`) **and** the plate. They are different facts: chosen goal vs route being ridden.
- **Colour rules:** no new tokens. `--signal` yellow is reserved (service changes, "You are here", active tab), so the plate must **not** be yellow. Line colours (`--apps`, `--guard`, `--serve`) are not used for the plate.

### 3.3 Low-match destination
- Shown pinned like any destination, with the match % in `--ink-3` and a route note: **"Long ride: this role needs most of its skills still. Other routes below are closer."**
- It must not move into the ranked list: the ranking formula stays as it is. Pinning is display order only, and the note says so.

### 3.4 Labels, motion, layout
- The planner already carries the **solid "real" chip** ("Match scores computed from your skills"). No new chip is needed.
- Motion: no new animation. Only the existing 150–300ms `cubic-bezier(0.16,1,0.3,1)` transitions; nothing new under `prefers-reduced-motion`.
- Layout: the pinned row uses the existing `.route__row` grid and its 960 / 640 px breakpoints.

### 3.5 Copy (short, per mentor "less text")
| Place | Text |
|---|---|
| Select label | Destination (optional) |
| Default option | Not sure yet |
| Plate | DESTINATION |
| Section | Other routes |
| Toast after save with a destination | "Destination set: <role>. Your pathway leads there." |

## Progress (24 Oct, branch `feat/dream-job-destination`)
- Done: step 1 (`lowMatchTarget`, commit `00c8edd`), steps 2-5 (select, pinning, plate, styles, checked at desktop and 375px; all backend tests pass; commits `00c8edd`, `ec05f84`).
- Step 6: added as open item 7 in `docs/submission/pitch-script.md`, not into the timed rows ("Try an example" skips the review step where the select lives).
- Known limit: the destination and the current route are the same profile field (`target_role`), so "Switch to this route" also moves the destination.

## 4. Build steps
1. `advisor/service.py`: full row for a low-match destination + test.
2. Destination select on the CV screen; role list from `/api/roles/forecast`; send `target_role` on apply.
3. Pin the destination in `liveRoutes()`, add the plate and the "Other routes" heading.
4. Styles in `styles.css` using only existing tokens.
5. Check at 1280 / 960 / 640 px and with keyboard only; run `backend/signals/tests` (incl. `test_varity_screens.py`).
6. Pitch copy.

## 5. Risks
| Risk | Mitigation |
|---|---|
| The apply call rejects a destination with no pathway (`unknown route`) | Only offer roles from the ranked list; on that error, save without a destination and show a toast |
| Profiles saved before this have no destination | Same as "Not sure yet": the current behaviour |
| `test_varity_screens.py` may check planner markup | Run it after step 3; update only the assertions that cover the new row order |
| A roles-forecast role can have no pathway for this user | The apply check catches it (row 1 above) |

## 6. Later
- Free text that filters the select with the `title_pattern` regexes in `data/roles.json`.
- The Jobs list from `docs/job-first-flow-plan.md`.
