# Reskilling pathway (E8)

Code: `engine/pathway.py`. Tests: `tests/test_pathway.py`. Resources: `data/resources.json`.

The pathway turns the skill gap for a target role into an ordered plan, then into dated daily tasks.
**Code sets the order and the dates. A language model never changes them.**

## Inputs

| Argument | Content |
|---|---|
| `target_role` | Name of the role. Used in text only. |
| `gap` | From role match: `[{skill, weight, status, trend_label, stance}, ...]`, ordered by weight. |
| `top_roles_gaps` | The gap lists of the user's top roles. Only the first 3 are used. An item may also be a role result that has a `gap` key. |
| `skill_scores` | `data/skill_scores.json` (share now, trend counts, sources, SDG). |
| `resources` | `data/resources.json`. |
| `scenario` | `"moderate"` (default) or `"fast"`. |
| `hours_per_week`, `start_date` | Pace and first day. `start_date` defaults to today. A weekend rolls to Monday. |
| `taxonomy` | Optional. `data/taxonomy.json` is loaded when it is `None` (for `sdg_reason`). |

The engine reads only the keys above, so it does not import the roles module.

## The three stages

Each gap skill goes to the **first** stage it fits (1, then 2, then 3).

| Stage | Name | Rule |
|---|---|---|
| 1 | `no_regret` | The skill is in the gap of **2 or more of the user's top 3 roles**, and its trend label is **not "Falling"**. |
| 2 | `near_term` | `status == "ok"` and the skill's **share now** (`demand_share_latest`) is in the **top half of the gap skills**. Top half = the `ceil(n / 2)` gap skills with the highest share. |
| 3 | `future_bet` | Trend label **"Rising"**, or stance **"AI-complement"**. |
| - | `other` | Fits none of the above. Goes **after stage 2 and before stage 3**. |

Order of stages:

- **Moderate:** `no_regret`, `near_term`, `other`, `future_bet`.
- **Fast:** `no_regret`, `future_bet`, `near_term`, `other`. The future-bet stage moves to second place. The Fast scenario is an assumption, labelled as an estimate. It changes the order only.

Inside a stage, skills are sorted by role `weight`, high first. A tie keeps the order of `gap`.

Examples of the reason text (all numbers come from `skill_scores.json`):

- `Needed by 2 of your top 3 roles; trend: No clear change, so it is not Falling.`
- `Demand now: 18.8% of recent job posts mention it, in the top half of your gap skills.`
- `Rising: 8.1% of posts vs 6.8% in the 12 months before.` (`mentions_last12 / posts_last12` against `mentions_prev12 / posts_prev12`)
- `AI-complement stance (AI exposure 47%): a skill that works with AI tools.`

## Each step

`skill`, `stage`, `reason`, `weight`, `resource` (or the placeholder), `minutes`, `sdg` and `sdg_reason` (from `taxonomy.json`), `source` (the dated sources of the skill's numbers), and the dates of its tasks.

## Daily to-do list (fixed timeline)

- Daily budget = `hours_per_week * 60 / 5` minutes, on **Monday to Friday**. Example: 5 hours a week = 60 minutes a day.
- A step is cut into tasks of **at most 45 minutes**: `chunk = min(45, minutes left today, minutes left in the step)`. A day with less than 10 minutes left is closed. So a 60-minute day can hold a 45-minute task and a 15-minute task. The weekly time never goes above `hours_per_week`.
- Each task has an `id` (`T001`, `T002`, ...), a planned `date`, and a `deadline` (the end of that day). The step also has a `step_deadline` (the date of its last task) and the plan has a `finish_date`. This fixed timeline is the accountability part.
- A step with no verified resource has **no tasks** (see the rule below).

## Progress

`progress(tasks, done_ids, as_of=None)` returns:

- `percent_done`: done minutes / all minutes (so a long task counts more), plus task counts.
- `overdue`: tasks that are not done and whose `deadline` is **before** `as_of` (a task due today is not overdue yet).
- `next_task`: the first task that is not done, in plan order.
- `completed_skills`: skills whose tasks are **all** done.
- `unknown_ids`: ids in `done_ids` that match no task. They are reported and not counted.

## Exports

- `to_markdown(pathway)`: summary, steps with reason, resource, SDG and source, the daily table, SDG links, notes.
- `to_ics(tasks)`: an RFC 5545 calendar written by hand (no dependency). One all-day `VEVENT` per task: `UID`, `DTSTAMP`, `DTSTART;VALUE=DATE`, `DTEND` (next day), `SUMMARY`, `DESCRIPTION` (minutes, resource title and URL, reason, deadline), `URL`. Lines end with CRLF, are folded at 75 octets (never inside a UTF-8 character), and text is escaped (`\`, `;`, `,`, newline).

## SDG summary

`pathway["sdg_summary"]` has:

- `counts`: the number of steps for each SDG target, most steps first.
- `skills_by_target`: which skills carry each target.
- `line`: one line, "How this plan contributes: SDG 8.2 (7), SDG 4.4 (2), ... " followed by up to 3 `sdg_reason` texts. Each text is the **first** step's `sdg_reason` for one of the top targets. The sentences are copied from `taxonomy.json`. The engine writes no other claims.

## The "no invented courses" rule

1. A resource can come **only** from `data/resources.json`.
2. An entry is used only if it has an `https` URL, `check_status == 200` and a positive `minutes`. Others are ignored.
3. A skill with no usable entry gets `resource = None`, `resource_note = "No verified free resource yet"`, 0 minutes and no tasks. It is listed in `pathway["unresolved"]` and in the Markdown notes. The engine never fills the gap with a guess.
4. A test checks that every chosen resource URL exists in the resource list, and that every entry in the real file has the required fields, an `https` URL and `check_status` 200.

### How `resources.json` was made

- 77 resources for the 40 taxonomy skills (2 per skill, 1 for C++, AngularJS and jQuery). They are official documentation, official tutorials and well-known free courses (for example python.org, Kubernetes, HashiCorp Developer, Hugging Face, PyTorch, dbt Learn, freeCodeCamp, MDN, Microsoft Learn).
- On 2026-10-22 every URL was fetched with HTTP GET (redirects followed, 15 second timeout, a browser User-Agent). Only HTTP 200 entries were kept. Where a link redirected to a new address, the **final** address is stored. Four candidates were dropped or replaced because they failed or redirected to a different page (an AWS Skill Builder deep link, a Qdrant page, a LangChain RAG page and an Azure learning path that had moved).
- `minutes` is a Verity team **estimate** of study time (`minutes_is_estimate: true`). It is not a provider figure.
- Page contents were not copied. The titles are ours and the links point to the provider.
- File layout: an object with `schema_version`, `hrd_corp_note`, `minutes_note`, `check_method` and a `resources` list. (`docs/data-contract.md` shows a bare list. The loader accepts both.)
- To refresh: fetch every URL again and update `checked` and `check_status`. A URL that no longer returns 200 must be removed or replaced.

## HRD Corp note

Every entry has `hrd_corp: false`. **No official HRD Corp page listing any of these courses was found**, so no claim is made. The file carries this note at the top level, and the Markdown export repeats it:

> HRD Corp-claimable status not verified for these resources; check https://hrdcorp.gov.my before claiming.

(`https://hrdcorp.gov.my` loads with HTTP 200 on 2026-10-22.) If a team member finds an official HRD Corp page for a course, set `hrd_corp: true` and add `hrd_corp_source` with that page's `https://hrdcorp.gov.my/...` URL. A test fails if `hrd_corp` is true without such a source. The engine then prefers that course over the others for the skill.

## Limits

- Time estimates are rough. Learners differ.
- Share, trend and stance come from Hacker News "Who is hiring?" posts and the Anthropic Economic Index. They are US- and startup-heavy. See `data/SOURCES.md`.
- The stage rules are simple on purpose, so a user can read why a skill is where it is. The user decides what to follow.
