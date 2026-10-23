# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS, no build step (user's choice, 23 Oct 2026). Lives in `frontend/` of the verity repo, served by `backend/signals` at `/`; meant to be ported to React later. The Signals page loads live data from `GET /api/signals` and falls back to the snapshot in `data.js`. This is a separate visual style from the other UI folders; do not inherit their look.

## Users

CS and tech workers: working developers, fresh grads and CS students. They have little time and too much AI news, and they fear falling behind as AI shifts which skills and roles pay off. Their job: decide what to learn next, and actually do a little of it each day.

## Product Purpose

Varity reads a user's CV, tracks daily AI and tech advancement (the AI Trend Signal Layer), forecasts which tech roles are emerging or declining, and combines the three into a personalised reskilling pathway: an ordered learning plan plus a daily to-do list that can be pushed to Google Tasks. Success means a user returns daily, finishes tasks, and their skill profile moves toward a rising role before the market moves past them.

## Positioning

Every recommendation is traceable to a dated, cited signal. The ranking is a deterministic formula (LLMs handle language, code handles numbers), so Varity can always show *why* an update ranks where it does and *why* a task is on today's list. It turns a report you read once into a daily habit, and re-plans visibly ("what changed and why") when signals move.

## Operating Context

- Primary device: desktop-first (onboarding, CV analysis and the plan are read on a laptop); the daily to-do list must also work on a phone.
- Prototype scope (user, 23 Oct 2026): keep it simple. A user-flow map plus five screens: CV analysis, Today (daily tasks + Google Tasks push), Pathway, Signals, Job forecast.

- Hackathon: XMUM SDC Hackathon 2026, Domain 1 (Aiversecity Future-Ready Workforce). Judges see a live demo where the trend-signal layer feeds matching live.
- Signal sources: official lab blogs and changelogs (RSS), arXiv, Hugging Face Daily Papers, Hacker News, Bluesky; X and Threads via official APIs only. Stories are tiered Must-know / Worth a look / Emerging (social-only, unconfirmed) / Minor.
- Daily tasks sync to Google Tasks via Google sign-in; fallback is the in-app list plus `.ics` / Markdown export.

## Capabilities and Constraints

- Must have (brief): profile intake (CV or form); trend-signal layer from at least one updatable, dated source; explainable role matching with match score and skills gap; ordered reskilling pathway with time estimates and free or low-cost resources (HRD Corp where possible); SDG tags (4.3, 4.4, 8.2, 8.5); at least two scenarios (moderate vs fast disruption), labelled as estimates.
- Public, open or synthetic data only; no real CVs. Name the LLM used. Cite a source for every recommendation. Never invent jobs, courses or statistics. Support human judgement, do not replace it.
- Current build: signals and skill momentum are real pipeline output; CV parsing, job forecast and pathway are synthetic for now and must be labelled as such in the UI.
- Terminology: story, signal, tier, momentum, role, skills gap, pathway, task, scenario.

## Brand Commitments

Name: **Varity** (spelled exactly so; confirmed by the user).

App frontend: the Transit Map design in `frontend/` (DESIGN.md) is the adopted frontend for Varity (user, 23 Oct 2026). Other UI folders are superseded.

## Evidence on Hand

- Real ranked stories and weekly skill momentum: `GET /api/signals` from `backend/signals` (`run`, top 10 `stories`, `skills`), same shape as `data.js`.
- Stanford ADP payroll study ("Canaries in the Coal Mine") cited in `../SKidea.md`.
- No users, testimonials, partner logos or outcome metrics exist. Do not fabricate them.

## Product Principles

1. Explain every rank and every task: show the signal, the source and the date behind it.
2. Estimates look like estimates: forecasts and scenarios are always labelled and carry uncertainty.
3. The daily to-do list is the product; every other screen feeds or explains it.
4. Respect the user's time: the 3 to 5 things worth learning today, and what is safe to skip.
5. Human in control: the user can accept, reorder or reject any recommendation.
