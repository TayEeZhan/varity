# Plan: which AI work runs on Replit credits and which on KrackedDevs

Written 1 Nov 2026. **The KrackedDevs side is built (`engine/llm_client.py`) and not yet run against the real gateway. The Replit side waits for credits.**

## What each credit can do
| | Replit ($100) | KrackedDevs ($20 per teammate key; 2 teammates = $40) |
|---|---|---|
| Models | Claude via Replit AI Integrations (`claude-haiku-4-5` default), OpenRouter (Jev) | GPT-5.4 / 5.5 / 5.6, GPT-6, gpt-5.4-mini / nano, DeepSeek V4 Flash / Pro. **No Claude.** |
| API | Anthropic SDK (already wired: `AI_INTEGRATIONS_ANTHROPIC_*`) | OpenAI-compatible, base URL `https://litellm.rapidscreen.io/v1` |
| Limits | Credits also pay hosting | Each key stops at $20; the budget never resets |

## Rule for the split
- **Replit (Claude) = live, user-facing work.** These calls are already built and tested for Claude, so their quality and prompts stay stable in front of judges.
- **KrackedDevs = bulk and background work.** Code checks every output (quotes must be in the source), so a cheaper model is safe there.

## Allocation
| AI job | Code | Runs | Provider | Model | Why |
|---|---|---|---|---|---|
| CV reading | `backend/signals/intake/llm_extract.py` | per CV upload | **Replit** | Claude Haiku | Live and user-facing; built and tested |
| Route advisor (re-order ≤2 places) | `backend/signals/advisor/llm.py` | per routes view (cached) | **Replit** | Claude Haiku | Live |
| Pathway coach | `advisor/` | per plan (cached) | **Replit** | Claude Haiku | Live |
| CV builder and CV agent | `advisor/cv_writer.py` and the CV agent | on request | **Replit** | Claude | Live writing quality matters |
| **One-off relabel of 48,508 HN posts** | `engine/llm_labels.py backfill` | once | **KrackedDevs** | `deepseek-v4-flash` (fall back to `gpt-5.4-nano`) | Bulk; quote check stops invented labels |
| Daily labelling of new posts | `engine/llm_labels.py` (scheduled) | daily, ~15 posts | **KrackedDevs** | same | Small, background |
| New-title review | `engine/role_discover.py` | weekly, few titles | **KrackedDevs** | `gpt-5.4-mini` | Needs a little more reasoning; 3 checked quotes |
| Signals ranker enrich / editor (Sheng Kuan) | `backend/signals/trendsignal/llm.py` | every 15 min | **KrackedDevs** (proposal) | `gpt-5.4-mini` | Runs all day, so it would eat the Replit credit. **Ask SK first:** his eval set (`eval/jury.py`) must pass on the new model |
| Jev scoring | `trendsignal` Jev client | every 15 min | Replit OpenRouter (as now) | `jev-latest` | Already wired; leave it |

## Cost estimates (check before running)
- Relabel: about 48,508 posts × ~850 tokens ≈ 41M tokens. **Step 1 is a 200-post dry run** that prints real tokens and $ from the API `usage` field. Then scale up. If the dry run shows the full run costs more than one key ($20), split the months across two keys or use the cheaper model.
- Daily labelling and title review: well under $1 a month.
- Replit Claude: about $0.008 per CV (Haiku 4.5 list price); the rest of Replit's credit pays hosting.

## Build steps (small)
1. A shared helper `engine/llm_client.py`: `chat(prompt, model)` that uses the OpenAI SDK when `KD_API_KEY` is set (base URL above), else the existing Anthropic path. It logs `usage` tokens to `data/llm_usage.csv` (date, job, model, tokens in/out). No key ever goes in git.
2. `llm_labels.py` and `role_discover.py` call the helper. Quote checks and the drift check stay as they are.
3. A budget guard: stop a run when the logged spend reaches a set cap (for example $15 per key).
4. Tests with a fake client: the quote check still drops unbacked labels; the budget guard stops the run.
5. Declare it: add "KrackedDevs LiteLLM gateway, deepseek-v4-flash / gpt-5.4-mini" to the Technical & Tools Declaration and to the Method screen ("who labels the posts").

## Risks
- A cheaper model labels less well than Claude. The quote check stops invented labels, not missed ones. The drift check (vs regex) catches big drops. We have no human gold set, so we cannot state accuracy; say so if asked.
- DeepSeek models are hosted by a third party via the gateway. Only public HN post text goes there, never CVs.
- If a key runs out mid-run, the job keeps the old files (this already works for the Claude path).

---

## The judges' feedback and what to improve
1. **"HN is not representative of Malaysia."** This is the main gap.
   - Built (WP-MY, `tasks/plan-final-round.md`): a sector-level Malaysia check from DOSM online vacancies, quarterly (`engine/my_dosm.py`, `data/my_vacancies_quarterly.csv`). DOSM has no job-title split, so it is not per role. Code reads each number from a named Excel cell and checks it. No LLM is used.
   - On screen, keep the honest line: "HN = global tech hiring sample; DOSM = Malaysian check."
2. **"Finishing a tutorial doesn't close a skill gap."** Done: the starter-course note, "Starter course done" labels, and the HRD Corp option (multi-day professional courses). Next: add one "practice project" step per skill (for example, "Deploy a small API on AWS"), taken from a sourced list. Code never invents one. Sheng Kuan is building this step.
3. **Strength to keep showing:** the model comparison and the uncertainty bands. Lead the pitch with them.
