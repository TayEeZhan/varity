# Verity: build plan (preliminary round)

Deadline: **Sun 25 Oct 2026, 07:59:59 MYT**. Our own target: submitted by **Sat 24 Oct, 21:00**.
Domain 1: Aiversecity Future-Ready Workforce. Team: Ee Zhan (EZ) + Sheng Kuan (SK).
Brief: `C:\Users\eezha\sdc-hackathon\BRIEF.md`. Idea doc: `SKidea.md` (SK).
Plan v2, 22 Oct. Reviewed by a second model; changes from v1 are folded in.

## Product in one line
Verity reads a tech developer's CV, forecasts which skills are rising or falling from dated public data, and gives ranked future roles plus a daily learning plan. Every claim shows its source and date. The plan changes when the data changes.

## Decisions (fixed)
- **ML level: light, CPU only, no GPU.** Trend model plus calibrated intervals plus backtest. No local LLM, no fine-tuning, no self-hosted model: those force RunPod proof.
- **UI: Streamlit**, one Python app that imports the engine. No separate API. Deploy on Replit.
- **LLM: one hosted model** (choose today, name it in the UI and in the declaration). Use it only for CV extraction and for wording explanations. Code makes every number and every ranking.
- **No embedding model.** A regex synonym table is enough and keeps torch off Replit.
- **Data: official APIs, RSS, and open datasets only.** No X, LinkedIn, JobStreet, or Bluesky scraping (terms of service and personal data).
- **Commit aggregates, not raw text.** Raw post text stays local (personal data in posts, GitHub 100 MB file limit).

## Who does what
| Area | Owner |
|---|---|
| HN "Who is hiring" backfill = the demand series the forecast trains on | **EZ** |
| Skill engine: taxonomy, tagging, forecast, intervals, backtest, scenarios, role match, pathway order, "what changed" diff | **EZ** |
| Live signal fetchers: AI news (lab blogs RSS), GitHub repos, arXiv, Hugging Face snapshot | **SK** |
| Momentum feature: weekly mentions per skill from SK's rows, z-score against the skill's own 90-day baseline, feeds the fast scenario | EZ (code), SK (data) |
| CV intake: LLM returns `{skill, evidence_quote, years}` with canonical names from `taxonomy.json`. Code rejects a skill if its quote is not in the CV. 3 synthetic CVs | **SK** |
| Streamlit UI pages | SK builds, EZ wires engine |
| Verified resource list (free + HRD Corp) per skill | SK |
| Proposal PDF draft, SDG impact table, deck | SK drafts Fri, EZ writes method section |
| Tech declaration, Replit proof | SK |
| Pitch video | Both, Sat 14:00 |

## Engine tasks (EZ)
- [ ] E1. `data/taxonomy.json`: 40 tech skills, synonyms, word-boundary regex, SDG tag. Handle ambiguous names (Go, R, C, Swift, Spark, React vs React Native).
- [ ] E2. HN backfill: list threads with `search_by_date?tags=story,author_whoishiring`, then fetch each with `/api/v1/items/<id>`. Use top-level comments only. Output `data/demand_monthly.csv` = month, skill, share, n. Use share, not count. 3-month smoothing. Strip names and emails.
- [ ] E3. `data/exposure.csv`: hand-map the 40 skills to O*NET tasks / Anthropic Economic Index. Label it "team judgement, sources cited". Record licences (O*NET CC BY 4.0, AEI CC BY).
- [ ] E4. Forecast on logit(share): damped trend vs naive vs drift. Pick the model by backtest MAE. 80% intervals by split-conformal from backtest residuals.
- [ ] E5. Backtest: fit to Dec 2023, predict 2024 to 2025. Report MAE vs naive and band coverage ("our band covered X% of actuals"). If the model does not beat naive, say so and ship naive with bands.
- [ ] E6. Scenarios as one stated formula: `fast = forecast * (1 - k * exposure_z) + momentum bump`. Show k as an assumption.
- [ ] E7. `data/roles.json`: 8 future tech roles as weighted skill lists. Match score = weighted coverage x forecast demand. Output gap list and reason.
- [ ] E8. Pathway order: no-regret skills first, then near-term demand, then future bet. Scenario toggle reorders. Each step: minutes, one real resource from `resources.json`, source, SDG tag.
- [ ] E9. "What changed and why" diff between two runs. "As-of month" slider: rerun the engine on data up to a chosen month (cached).
- [ ] E10. pytest: tagging (ambiguous names), forecast shape, match ranking.
- [ ] Stretch only: GitHub momentum as a lead indicator for HN demand. Show it only if the backtest supports it. GitHub Innovation Graph (CC0, has Malaysia) for local context.

## Signal and intake tasks (SK)
- [ ] S1. Fetchers for lab-blog RSS, GitHub Search API, arXiv API, HF trending (label as snapshot). Rows follow `docs/data-contract.md`.
- [ ] S2. Cache a dated snapshot so the demo runs when a source is down.
- [ ] S3. CV extractor using canonical names from `taxonomy.json`. User can edit extracted skills and override the target role (human stays in control).
- [ ] S4. 3 synthetic CVs (for example "Aina, junior Python dev").

## 60-second live demo (the feature judges score)
1. Load Aina's CV. Skills appear with evidence quotes. She removes one.
2. Press Refresh. New dated rows appear with links and a "last updated" time.
3. Open the Kubernetes chart: history, forecast band, sources.
4. Roles: "Data Engineer 74%" with gap and reason. Toggle Moderate to Fast: ranking reorders, "What changed and why" appears.
5. Move "as-of" to Dec 2023: "we forecast X, actual was Y".
6. Pathway days 1 to 3: minutes, free or HRD Corp resource, SDG tag. Label: "Estimate. You decide." Model name visible.

## Timeline
| Day | EZ | SK | Gate |
|---|---|---|---|
| Thu 22 | Commit plan and contract. E1, E2, E3. Fixture `skill_scores.json`. Streamlit hello-world deployed on Replit | S1, S4, CV extractor start. Ask Discord the open questions | Real rows and fixtures pushed. Replit URL live |
| Fri 23 | AM: E4, E5. PM: E6, E7, E8, E9, E10 | S2, S3, UI on real data, resource list, draft proposal and declaration, mentor session | End-to-end on Replit: CV to roles to plan |
| Sat 24 | 12:00 feature freeze. Fixes. Method section, diagram, backtest chart | SDG table, deck | 14:00 record video. 18:00 upload. 21:00 submit |
| Sun 25 | Buffer only. No commits after 07:59 | | |

## Open questions (ask on Discord today)
- [ ] Does a team with zero GPU use still need RunPod proof?
- [ ] Mandatory GenAI / Database / Cloud workshops: dates, and are they done?
- [ ] Committee GitHub accounts to add (video #3)
- [ ] Mentor booking method (video #6)
- [ ] Team name for the file names

## Before submit (checklist)
- [ ] Repo private while building, public at submission. Apache 2.0 LICENSE. Committee accounts added
- [ ] No API keys in the repo (`.env` in `.gitignore`). LLM key has a spend cap
- [ ] Small commits from both members every day
- [ ] Replit Deployment URL (not the dev URL) works logged out. Keep it up and unchanged until 28 Oct
- [ ] Every number in the app and the docs has a source. Check SKidea's "about 19%" Canaries figure against the paper before using it
- [ ] Both members can explain the forecast, the intervals, and the match score
- [ ] Declaration lists every tool, model, API, dataset with licence, including Claude Code (extent: major) and how we reviewed its output

## Review
(Fill in after each day.)
