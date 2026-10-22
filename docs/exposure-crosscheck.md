# Exposure cross-check and measured k (step 9)

Branch `feat/exposure-indices`. Production stance is **not changed**. This step adds a check and a flag.

## 1. Why

The AI stance of a skill (AI-substitutable, neutral, AI-complement) comes from one source: the Anthropic Economic Index (AEI)
automation share. A judge can ask: "Do other measures agree?" This step answers with data, and it shows where they do not.
It also asks what the job-post data say about `k` in `fast = moderate * (1 - k * e_s)`. We assumed k = 2.

## 2. Part A: other exposure indices

Four source families, six indices. Details, URLs, versions and licences: `data/SOURCES.md` sections 4 to 7.

| Index id | Family | What it measures | Licence |
|---|---|---|---|
| `aei_automation` | AEI (production) | share of Claude.ai conversations where the AI did the task | CC BY |
| `gpts_gpt4_beta`, `gpts_human_beta` | GPTs are GPTs | what an LLM could do for the tasks of an occupation (beta = E1 + 0.5 E2) | MIT |
| `aioe`, `aioe_lm` | AIOE (Felten, Raj, Seamans) | match of AI application progress to O*NET abilities; language-modelling variant | no licence file; README asks for citation |
| `msft_applicability` | Microsoft Working with AI | how applicable AI is to an occupation, from Bing Copilot use in 2024 | CC BY 4.0 |

Skipped: the ILO index (ISCO-08 groups only; no usable official crosswalk to SOC). See `data/SOURCES.md`.

### Values for the eight occupations (raw value, then rank; rank 1 = most exposed)

| O*NET-SOC | Occupation | AEI % | GPT-4 beta | Human beta | AIOE | AIOE LM | Microsoft |
|---|---|---|---|---|---|---|---|
| 15-1252.00 | Software Developers | 60.57 (5) | 0.868 (5) | 0.447 (8) | 1.242 (4) | 1.024 (3) | 0.278 (7) |
| 15-1251.00 | Computer Programmers | 63.11 (2) | 0.950 (1) | 0.683 (1) | 1.272 (2) | 1.025 (2) | 0.310 (4) |
| 15-1254.00 | Web Developers | 54.94 (7) | 0.933 (3) | 0.635 (2) | 1.089 (6) | 0.789 (6) | 0.353 (2) |
| 15-1243.00 | Database Architects | 58.27 (6) | 0.878 (4) | 0.598 (3) | 1.259 (3) | 1.020 (4) | 0.312 (3) |
| 15-1242.00 | Database Administrators | 62.76 (3) | 0.935 (2) | 0.597 (4) | 1.285 (1) | 0.996 (5) | 0.297 (6) |
| 15-1244.00 | Network and Computer Systems Administrators | 67.17 (1) | 0.730 (8) | 0.514 (7) | 0.790 (7) | 0.475 (7) | 0.253 (8) |
| 15-1299.08 | Computer Systems Engineers/Architects | 62.59 (4) | 0.768 (6) | 0.571 (6) | 1.233 (5) | 1.044 (1) | 0.298 (5) |
| 15-2051.00 | Data Scientists | 47.41 (8) | 0.750 (7) | 0.594 (5) | no value | no value | 0.357 (1) |

The z-scores and the ranks for every index are in `data/exposure_indices.csv`.

### SOC crosswalk (how the codes were mapped)

- AEI and GPTs-are-GPTs use O*NET-SOC 2019 codes. No mapping.
- Microsoft uses 6-digit SOC 2018. The O*NET "2019 to SOC 2018" table gives the code. `15-1299.08` gets the score of the broad code `15-1299`.
- AIOE uses 6-digit SOC 2010. The official O*NET "2010 to 2019" crosswalk lists which 2010 codes feed each 2019 code.
  AIOE value = unweighted mean over the 6-digit parents that have a value.
  - 15-1252 = mean(15-1132, 15-1133). 15-1251 = 15-1131. 15-1254 = 15-1134. 15-1242 = 15-1141. 15-1244 = 15-1142.
  - 15-1243 = mean(15-1141, 15-1199), because Database Architects came from 15-1141 and from 15-1199.06.
  - 15-1299.08 = 15-1199 (broad "Computer Occupations, All Other").
  - 15-2051 (Data Scientists): its parent 15-2099 is not in the AIOE file. **No value. We did not guess one.**

### Results

Rank correlation (Spearman) of each index with the AEI automation share across the occupations. With 8 points, only a very large value counts.

| Index | rho vs AEI | exact permutation p | n |
|---|---|---|---|
| GPTs, GPT-4 beta | +0.10 | 0.84 | 8 |
| GPTs, human beta | -0.12 | 0.79 | 8 |
| AIOE | +0.07 | 0.91 | 7 |
| AIOE, language modelling | -0.04 | 0.96 | 7 |
| Microsoft applicability | **-0.79** | 0.03 | 8 |

**Plain reading:** the AEI automation share does not rank the eight occupations like any capability-based index. It ranks them in nearly
the **reverse** order of the other usage-based index (Microsoft). The two usage measures disagree most on Data Scientists (AEI: least automated; Microsoft: most applicable).
GPTs and AIOE agree with each other a little (GPT-4 beta against AIOE: rho = +0.75) but not with AEI.

### Category view and the `stance_robust` flag

Category score = mean of its occupations' raw values (same map as production). z = deviation from the mean over the 40 skills, divided by the SD over the 40 skills.
Neutral band: the production band (`|e_s| <= 0.02`) is 0.40 SD, so every index uses `|z| <= 0.40`.

| Category (skills) | Our stance | AEI z | GPTs z | AIOE z | Microsoft z | Sources that support | Veto | Result |
|---|---|---|---|---|---|---|---|---|
| language (14) | AI-substitutable | +0.44 | +0.31 | +0.61 | -0.42 | 3 of 4 | none | **robust** |
| framework (5) | neutral | -0.38 | -0.17 | -0.47 | +0.51 | 2 of 4 | n/a | contested |
| data (9) | neutral | +0.17 | +0.85 | +0.61 | +0.04 | 2 of 4 | n/a | contested |
| cloud_devops (6) | AI-substitutable | +1.04 | -1.23 | -2.04 | -1.23 | 1 of 4 | GPTs, AIOE, Microsoft | contested |
| ai_ml (5) | AI-complement | -2.44 | -0.33 | no value | +2.28 | 2 of 3 | Microsoft | contested |
| practice (1) | neutral | +0.18 | -2.03 | +0.53 | -1.10 | 1 of 4 | n/a | contested |

Rule: a family casts one vote (mean z of its variants). Support: AI-substitutable needs z > 0; AI-complement needs z < 0; neutral needs `|z| <= 0.40`.
`stance_robust` = more than half of the voting families support the stance **and** no family reads the opposite side with `|z| > 1` (veto).
Without the veto, `ai_ml` would be robust (2 of 3); with it, the strong Microsoft reading makes it contested. This choice is ours; the numbers for both are in `data/exposure_agreement.json`.

Robust: **language** (14 skills). Contested: framework, data, cloud_devops, ai_ml, practice (26 skills).
**The cloud_devops stance is the weakest:** AEI alone calls it AI-substitutable; all three other families put it below the average.
Direction only (same side of the mean, no neutral test): language, framework, data and ai_ml have a majority on the production side; cloud_devops and practice do not.

Limits: 8 occupations, 4 families. AEI and Microsoft measure chatbot use; GPTs and AIOE rate capability. Different questions, so some disagreement is expected.
The neutral band edge is a hair trigger: AEI's own z for `framework` is -0.378 against a band edge of -0.399.

Files: `data/exposure_indices.csv`, `data/exposure_agreement.json`, `data/exposure_robustness.csv` (one row per skill, `stance_robust`).

## 3. Part B: k from the data

**Question.** If AI exposure changed demand, skills with a higher `e_s` should have lost share since ChatGPT (Nov 2022).

**Design.** For each skill with status `ok` (27 of 40): `d` = mean logit share over the post window minus mean over 2021-11..2022-10.
Post windows: 2023-11..2024-10, 2024-11..2025-10, and the most recent 12 months 2025-11..2026-10 (primary; its last month is partial).
Regression across skills: `d = a + b * e_s`. Weights: mentions (and an unweighted fit).

**From b to k (linearisation at the mean share).**

1. Scenario: `fast / moderate - 1 = -k * e`.
2. Data: `d logit = b * e`. For a small change, `d share / share = (1 - s) * d logit` (because `d share / d logit = s (1 - s)`).
3. So `d share / share = (1 - s_bar) * b * e`, and `k = -(1 - s_bar) * b`. Here `s_bar` = weighted mean pre-window share = 0.159.
4. A CI of `b` maps to a CI of `k` by the same linear map. The ends swap because of the minus sign.
5. `k` is cumulative over the window. The scenario horizon is 12 months, so `k_per_12m = k / years` (3.5 years for the primary window). This assumes an even build-up. It is an assumption.

The linearisation is first order. For a large shift it overstates the fall a little (tested in `test_k_from_b_follows_the_linearisation`).

**Uncertainty.** 95% percentile bootstrap, 5000 resamples, seed 20261022. Two versions:
- skill bootstrap: resamples skills. Too optimistic, because skills in one category share `e_s` and move together.
- cluster bootstrap: resamples categories. **Headline.**

**Results (primary window, all ok skills, weighted).**

| | b (logit per unit e_s) | k, cumulative | k per 12 months |
|---|---|---|---|
| estimate | -7.5 | 6.3 | 1.8 |
| 95% CI, cluster bootstrap | -12.1 to +4.3 | -3.6 to 10.2 | -1.0 to 2.9 |
| 95% CI, skill bootstrap (too narrow) | -22.5 to -0.3 | 0.3 to 18.9 | 0.1 to 5.4 |

**Why the data cannot pin k down.**
- The cluster CI includes 0.
- The slope changes sign when the `ai_ml` category is left out: b = +1.2 weighted (cluster CI -22.2 to +17.1, 2025-11..2026-10), and the same happens in all three windows.
  The negative slope in the full sample comes from LLM / GenAI, RAG, Machine Learning and PyTorch. They rose because they are AI skills, and `ai_ml` has the lowest `e_s` by far.
- Category level: 5 points (category `practice` has no ok skill). Unweighted slope -8.2 (exact permutation p = 0.12); without `ai_ml`, 4 points and slope +1.1 (p = 0.92). Leave-one-out: dropping `ai_ml` flips the sign.
- Pre-trend placebo (2019-11..2020-10 to 2021-11..2022-10, before ChatGPT): b = +0.6 (cluster CI -2.2 to +4.6). No sign of an older exposure trend, but the COVID swing is in these windows.
- Controlling for the pre-window level gives b = -6.0: same sign as the full sample, so mean reversion does not explain it. This does not fix the `ai_ml` problem.

**Verdict.** The data cannot pin k down. Together with the sign flip, `k = 2` stays a **labelled assumption**.
The implied range that is consistent with the data is wide: k per 12 months from -1.0 to 2.9 (cluster CI), so k = 2 is inside it, and so is k = 0.
We do not claim the data support 2; we claim they do not reject it.

**Confounders (not controlled):** the 2023 tech layoffs; interest-rate rises; shifts in who posts on Hacker News (posts per month fell from about 700 to about 310);
`e_s` is a 2026 usage measure and is not time-cut; categories are coarse (6 values for 40 skills); the latest window includes a partial month. This is an association across skills, not a causal estimate.

Files: `engine/k_estimate.py`, `data/k_estimate.json` (all windows, weights, samples, category fits, placebo, leave-one-out).

## 4. App

- Method tab, section "Exposure cross-check": the table above, the rank correlations, the robust and contested lists, and the "k from data" line.
- Skill detail: "(contested across indices)" after the AI stance when `stance_robust` is false.
- The files are optional. If they are missing, the section and the flag do not show.

## 5. Open points for review

1. AIOE has no licence file. We use it with citation (the README asks for it) and do not redistribute the files. Remove the two AIOE indices if you do not accept this: the rest still works.
2. The veto threshold (`|z| > 1`) and the neutral band are our choices. They change which categories are contested (see `ai_ml`).
3. Should the production stance for `cloud_devops` be softened to "neutral" in a later step? This step does not do it.
