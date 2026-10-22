# Reskilling pathway (E8)

Code: `engine/pathway.py`. Tests: `tests/test_pathway.py`. Resources: `data/resources.json`.

The pathway turns the skill gap for a target role into an ordered plan, then into dated daily tasks.
**Code sets the order and the dates. A language model never changes them.**

## Inputs

| Argument | Content |
|---|---|
| `target_role` | Name of the role. Used in text only. |
| `gap` | From role match: `[{skill, weight, status, trend_label, stance}, ...]`, ordered by weight. |
| `role_gaps` | The gap lists of the roles to count for the no-regret stage: the **target role plus every ranked role** (match 20% or more), each once. No cap. The caller passes the target's own gap in this list. An item may also be a role result that has a `gap` key. |
| `skill_scores` | `data/skill_scores.json` (share now, trend counts, sources, SDG). |
| `resources` | `data/resources.json`. |
| `scenario` | `"moderate"` (default) or `"fast"`. |
| `hours_per_week`, `start_date` | Pace and first day. `start_date` defaults to today in **Malaysia time (UTC+8, `today_myt()`)**, so a plan made at 01:00 in Malaysia does not start from yesterday's UTC date. A weekend rolls to Monday. |
| `taxonomy` | Optional. `data/taxonomy.json` is loaded when it is `None` (for `sdg_reason`). |

The engine reads only the keys above, so it does not import the roles module.

## The three stages

Each gap skill goes to the **first** stage it fits (1, then 2, then 3).

| Stage | Name | Rule |
|---|---|---|
| 1 | `no_regret` | The skill is in the gap of **2 or more of the counted roles** (the target role and all ranked roles), its trend label is **not "Falling"**, and its stance is **not "AI-substitutable"**. |
| 2 | `near_term` | `status == "ok"` and the skill's **share now** (`demand_share_latest`) is in the **top half of the gap skills**. Top half = the `ceil(n / 2)` gap skills with the highest share. |

**Near-term is relative.** It means "higher share than the other skills in this gap", not "high demand" in absolute terms. A gap made only of small skills still has a top half. The reason text says so.
| 3 | `future_bet` | Trend label **"Rising"**, or stance **"AI-complement"**. |
| - | `other` | Fits none of the above. Goes **after stage 2 and before stage 3**. |

Order of stages:

- **Moderate:** `no_regret`, `near_term`, `other`, `future_bet`.
- **Fast:** `no_regret`, `future_bet`, `near_term`, `other`. The future-bet stage moves to second place. The Fast scenario is an assumption, labelled as an estimate. It changes the order only.

Inside a stage, skills are sorted by role `weight`, high first. A tie keeps the order of `gap`.

Examples of the reason text (all numbers come from `skill_scores.json`):

- `Needed by 2 of the 7 roles counted (your target and your ranked roles); trend: No clear change, so it is not Falling.`
- `Demand now: 18.8% of recent job posts mention it, in the top half of your gap skills (relative to your gap, not a fixed level).`
- `Rising: 8.1% of posts vs 6.8% in the 12 months before.` (`mentions_last12 / posts_last12` against `mentions_prev12 / posts_prev12`)
- `AI-complement stance (AI exposure 47%): a skill that works with AI tools.`

## Each step

`skill`, `stage`, `reason`, `weight`, `resource` (or the placeholder), `minutes`, `sdg` and `sdg_reason` (from `taxonomy.json`), `source` (the dated sources of the skill's numbers), and the dates of its tasks.

## Daily to-do list (fixed timeline)

- Daily budget = `hours_per_week * 60 / 5` minutes, on **Monday to Friday**. Example: 5 hours a week = 60 minutes a day.
- A step is cut into tasks of **at most 45 minutes**: `chunk = min(45, minutes left today, minutes left in the step)`. A day with less than 10 minutes left is closed. So a 60-minute day can hold a 45-minute task and a 15-minute task. The weekly time never goes above `hours_per_week`.
- Each task has an `id` (`T001`, `T002`, ...), a planned `date`, and a `deadline` (the end of that day). The step also has a `step_deadline` (the date of its last task) and the plan has a `finish_date`. This fixed timeline is the accountability part.
- A step with no verified resource has **no tasks** (see the rule below).
- `tasks_signature(tasks)` is a short hash of every task's id, title and date. The app keys the ticks on it, so a tick belongs to that exact task list: when the plan changes (for example a skill leaves the gap) the ticks are cleared and never move to another task. `to_ics` puts the same hash in each UID (`<hash>-T001-<date>@verity.pathway`), so two plans never share a UID.

## Progress

`progress(tasks, done_ids, as_of=None)` returns:

- `percent_done`: done minutes / all minutes (so a long task counts more), plus task counts.
- `overdue`: tasks that are not done and whose `deadline` is **before** `as_of` (a task due today is not overdue yet).
- `next_task`: the first task that is not done, in plan order.
- `completed_skills`: skills whose tasks are **all** done.
- `unknown_ids`: ids in `done_ids` that match no task. They are reported and not counted.

## Exports

- `to_markdown(pathway)`: summary, steps with reason, resource, SDG and source, the daily table, SDG links, notes.
- `to_ics(tasks)`: an RFC 5545 calendar written by hand (no dependency). One all-day `VEVENT` per task: `UID` (with the plan hash), `DTSTAMP`, `DTSTART;VALUE=DATE`, `DTEND` (next day), `SUMMARY`, `DESCRIPTION` (minutes, resource title and URL, reason, deadline), `URL`. Lines end with CRLF, are folded at 75 octets (never inside a UTF-8 character), and text is escaped (`\`, `;`, `,`, newline).

## SDG summary

In the app, the SDG section leads with two plan-level sentences from `sdg_headline(pathway, role_outlook)`. Every number comes from the plan or from the role's own trend numbers:

- `SDG 4.4 (indicator 4.4.1, ICT skills for employment): this plan adds N job-listed skills in H hours (estimate) at RM0 cost using free resources.` N = steps with a verified resource, H = total hours. "RM0 ... free resources" appears only when every chosen resource has cost `free`; otherwise the text says "mostly free resources".
- `SDG 8.5 (full and productive employment): moves you toward <role> (role demand: <trend label>, x% of posts in the last 12 months vs y% the 12 months before).` With no trend label it says "no trend label: too few posts".

The per-skill tags (`sdg`, `sdg_reason` from `taxonomy.json`) sit second, in an expander. The step-counting line was dropped. The data below is still in `pathway["sdg_summary"]` and in the Markdown export.

`pathway["sdg_summary"]` has:

- `counts`: the number of steps for each SDG target, most steps first.
- `skills_by_target`: which skills carry each target.
- `line`: one line, "How this plan contributes: SDG 8.2 (7), SDG 4.4 (2), ... " followed by up to 3 `sdg_reason` texts. Each text is the **first** step's `sdg_reason` for one of the top targets. The sentences are copied from `taxonomy.json`. The engine writes no other claims.

## The "no invented courses" rule

1. A resource can come **only** from `data/resources.json`.
2. An entry is used only if it has an `https` URL, `check_status == 200` and a positive `minutes`. Others are ignored.
3. When a skill has several usable entries, the engine picks a verified HRD Corp course first, then a **beginner** resource, then the first listed. The others are kept as `alternatives`. (For RAG, "Simple RAG" is listed before "Advanced RAG".)
4. A skill with no usable entry gets `resource = None`, `resource_note = "No verified free resource yet"`, 0 minutes and no tasks. It is listed in `pathway["unresolved"]` and in the Markdown notes. The engine never fills the gap with a guess.
5. A test checks that every chosen resource URL exists in the resource list, and that every entry in the real file has the required fields, an `https` URL and `check_status` 200.

### How `resources.json` was made

- 77 resources for the 40 taxonomy skills (2 per skill, 1 for C++, AngularJS and jQuery). They are official documentation, official tutorials and well-known free courses (for example python.org, Kubernetes, HashiCorp Developer, Hugging Face, PyTorch, dbt Learn, freeCodeCamp, MDN, Microsoft Learn).
- On 2026-10-22 every URL was fetched with HTTP GET (redirects followed, 15 second timeout, a browser User-Agent). Only HTTP 200 entries were kept. Where a link redirected to a new address, the **final** address is stored. Four candidates were dropped or replaced because they failed or redirected to a different page (an AWS Skill Builder deep link, a Qdrant page, a LangChain RAG page and an Azure learning path that had moved). On the PR review pass, three more entries were replaced after a re-check, each stored with its final HTTP 200 address: Google Cloud Skills Boost (labs use credits) by the Google Cloud overview documentation, the MongoDB University catalog by "Get Started with PyMongo", and the Snowflake guide index by "Getting Started with Snowflake" (cost `free trial`: it needs a 30-day trial account).
- `minutes` is a Verity team **estimate** of study time (`minutes_is_estimate: true`). It is not a provider figure. Most providers publish no length; the long self-paced courses are rough: freeCodeCamp Scientific Computing with Python 2400, Learn C++ 3600, the Rust Book 1800. The React Quick Start is a one-hour page (60).
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
