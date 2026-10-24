# Varity follow-ups: plans (no code changed)

Written 24 Oct 2026 against `main` @ PR #25. Covers: real re-plan, unused APIs, X and Threads collectors.

---

## A. Real re-plan when signals or the forecast change

### How it works today
- `GET /api/pathway` (`web/roles_api.py:96`) **rebuilds the plan on every request** from the latest signal run (`run_id`), `data/*.json` and the profile (`advisor/service.py::pathway`).
- The frontend keys ticks by `STATE.sig` = a hash of every task's `id|title|date` (`frontend/app.js:293`). `POST /api/profile/progress` stores ticks under that `signature`.
- So when the data changes, the plan **silently** changes. The signature changes, the old ticks no longer match, and **progress looks lost**. The user is never told what changed or why. The canned "Keep change / Revert" banner was removed, so nothing replaced it.

**Worse than it looks (checked in code):** `advisor/service.py:287` passes `start_date = today_myt()` on every request, so **every task date moves forward each new day**. The tick key hashes `id|title|date`, so it changes **every day even when no data changed**. Ticks from yesterday vanish today. Task ids are positional (`T001`, `T002`… in `engine/pathway.py:279`), so one added skill renumbers every task after it. And the plan never reads `progress`, so finished work is scheduled again from today.

The engine part (rebuilding) already works. What's missing is **noticing the change, explaining it, carrying the ticks over, and letting the user accept or decline it**.

### Design
```
signal run / forecast refresh ─► data changes
                                   │
GET /api/pathway ─► build new plan ─► compare with the user's last ACCEPTED plan (stored)
                                   │ same → return plan
                                   │ different → return plan + "change" {added, removed, moved, reasons}
Frontend ─► banner "Your plan changed: +RAG eval, −Docker (demand ▼). Keep / Revert"
Keep   → POST /api/pathway/accept  (store new plan as accepted; move ticks by task id)
Revert → keep serving the stored accepted plan until the next change
```

### Steps
1. **Store the accepted plan.** Add `accepted_plan` (JSON: task ids, skills, dates, `run_id`, `forecast_as_of`) next to `Progress` in the profile store (SQLite locally, Postgres on Replit, the same as PR #24 ticks).
2. **A stable task id.** Make the tick key `skill + step`, not the date. Today's signature includes `date`, so re-scheduling alone wipes ticks. Change `STATE.sig` to the plan id, and match ticks by task id.
3. **Diff function** (pure, in `advisor/service.py` or `engine/pathway.py`): `plan_diff(old, new) → {added, removed, reordered, reasons}`. Reasons come from data the plan already has: the skill's trend label changed, the role forecast changed, the resource link failed, or the target role changed. No LLM is needed. The Claude coach can optionally rewrite the reason in plain words (it has a budget and falls back to the code reasons).
4. **API.** `GET /api/pathway` adds `change` when the new plan differs from the accepted one. A new `POST /api/pathway/accept {planId}` stores it. Revert just means not accepting; the server keeps serving the accepted plan, flagged `stale: true`.
5. **Frontend.** Bring back the service-change banner on Today, filled from `change` (the old CSS and markup still exist). Ticks on tasks that survive are kept, and removed tasks are listed as "dropped".
6. **Trigger.** Nothing new is needed: the scheduler pipeline (`scheduler.py`) already refreshes the signals. The check happens the next time the user opens the page. Optional: show a "plan changed" dot in the nav.
7. **Tests.** Diff with no change, an added skill, a removed skill and a date-only shift (the date-only shift must keep ticks). Plus an API test for accept and revert.

**Size:** medium (about 1 day). **Risk:** migrating the tick key; keep reading old signature keys once and convert them.

---

## B. Unused APIs: why, and who should use them

### Why they're unused
They come from the **original TrendSignal app** (`backend/signals`), which had its own server-rendered pages: `/feed`, `/story/{id}`, `/brief/{kind}`, `/sources` and `/rss.xml`. Those pages read the same data directly. The JSON APIs were added for other clients. Varity's frontend was built later and only uses `/api/signals`, which bundles the top 10 stories and momentum. So the APIs work; no Varity screen calls them.

| API | Does | Who should use it | Plan |
|---|---|---|---|
| `POST /api/feedback` `{story_id, signal}` | Records 👍/👎 on a story (rate-limited) | **Signals screen**: a useful / not useful button on each story card | Add 2 buttons per card. The feedback becomes labels for the ranker eval (`eval/`), which closes the loop the judges ask about ("how do you know the ranking is good?"). Small. |
| `GET /api/stories` (+ `/{id}`) | Paged, filterable stories beyond the top 10 | **Signals screen**: "Show more" + a story detail drawer; a **pathway task's "why"** links to the story that caused it | Add "Show more" (calls `/api/stories?offset=`). Make the evidence chips on Pathway/Today clickable to `/api/stories/{id}`. Small to medium. |
| `GET /api/trends` | Story counts per trend or topic | **Market (Signals) screen**: a small trend bar chart, which fits the mentor's "more visuals" | One chart. Small. |
| `GET /api/digest/{kind}/latest` | The latest daily or weekly brief (the scheduler writes it at 08:00 and on Mondays) | **Today screen**: "This week in AI for your route" card; or the Telegram delivery that already exists (`delivery.py`) | Show the weekly digest as a collapsible card on Today. Small. |

If there's no time, **mark them as internal** in the README. Don't delete them: the TrendSignal HTML pages and the tests use the same functions.

**Priority:** feedback buttons (an eval story for judges) → trend chart (visuals) → digest card → show more.

---

## C. X and Threads collectors

### Why they collect nothing
Both are **off on purpose** in `backend/signals/config/sources.yaml`:
- `x_curated` `enabled: false`: needs `X_BEARER_TOKEN`, and the X API is **pay-per-use** (budget `daily_budget_usd: 1.50`; the collector prices each call and stops before going over).
- `threads_search` `enabled: false`: needs `THREADS_ACCESS_TOKEN` **and** Meta's `threads_keyword_search` permission (App Review). Without that permission the API returns only the token owner's own posts.

The code is built and tested. What's missing is accounts, keys and approval. This isn't a bug.

### Fix options
| Source | Steps | Cost / time | Recommendation |
|---|---|---|---|
| **X** | 1. Create an X developer account + app. 2. Buy pay-per-use credit. 3. Put `X_BEARER_TOKEN` in `.env` / Replit Secrets. 4. Set `enabled: true`. 5. Check `config/x_accounts.txt`. 6. Run one collect and check the spend log. | Paid; minutes to set up | Only if the team agrees to the spend. The $1.50/day cap is already enforced. |
| **Threads** | 1. Meta developer app. 2. Request `threads_keyword_search`, which needs **App Review** (privacy policy, screencast, business verification). 3. Get a long-lived token. 4. Put `THREADS_ACCESS_TOKEN` in Secrets. 5. Enable it. | Free; **days to weeks** of review | Not before the hackathon. List it as roadmap. |
| **Bluesky (already on)** | Add more handles to `bluesky_curated.params.handles` (only `simonwillison.net` now) | Free, no key | **Do this now.** It's the cheapest way to get more social signal. |

For the demo, say: "Social sources: Bluesky live; X and Threads adapters built and budget-capped, switched off until keys and approval." That's honest, and it shows the work.

---

## D. Order
1. C: add Bluesky handles (minutes).
2. B: feedback buttons + trend chart (small, helps judging).
3. A: re-plan (medium; fixes a real bug where ticks are lost when the plan changes).
4. B: digest card, show more.
5. C: X (if budget is approved), Threads (roadmap).

---

## E. Learning memory and trend-driven new skills

### Goal
The user keeps learning, the app remembers what was learned, and a new skill that the AI trend signal layer finds worth learning is offered into the pathway.

### Pieces
1. **Stable plan** (fixes the daily tick loss): task ids are `skill-slug-part` (not `T001`); the plan start date is fixed when the plan is first accepted; ticks are keyed by the plan (role id), not by a hash with dates.
2. **Skill ledger**: when every task of a skill is ticked, "Mark as learned" adds the skill to the profile (`source: pathway`, `method: task_done`). It then leaves the gap, and the match % rises.
3. **Re-plan banner**: the accepted plan's skill list is stored. If a rebuild adds or drops skills, Today shows what changed and why, with Keep / Revert. Skills dropped because the user learned them are accepted silently.
4. **Trend-gated new skill**: offered only if all of these hold:
   - the news signal is rising (`momentum >= 0.5`, at least 3 stories this week, not falling over the last 3 weeks)
   - job posts show it Rising (`skill_scores` trend label)
   - it's in the gap of another ranked role near the user
   - it's not held, not already in the plan, and not declined
   - it has a checked resource
   The user chooses Add / Not now.

### Risk controls
| Risk | Control |
|---|---|
| Too many changes | At most 1 new-skill offer per 7 days; changes batched into one banner; "Not now" hides a skill for 30 days; a setting turns offers off |
| Stale or false trends | Two independent sources must agree (news momentum + job-post trend) and the news rise must hold for 3 weeks; a pushed skill whose job trend turns Falling is dropped with a reason |
| Time | Built in slices 1 → 4, each usable alone; no new tables (all in the profile JSON); no LLM in any decision |
