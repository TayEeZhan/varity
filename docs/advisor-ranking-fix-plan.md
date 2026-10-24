# Fix plan: AI role ranking returns `off:INVALID_OUTPUT`

Status: fixed locally (not committed). Diagnosis: the JSON was cut off at ~835 characters because thinking tokens share
`max_tokens`; the fixed call used 1536 output tokens. Fix: `ADVISOR_MAX_TOKENS` and `COACH_MAX_TOKENS` raised to 4000, and a
cut-off answer now reports `TRUNCATED` instead of `INVALID_OUTPUT`. The top-6 and prompt changes were not needed.

## Problem

A local smoke test with a real `ANTHROPIC_API_KEY` and the synthetic sample CV "daniel" showed:

| Feature | Result |
|---|---|
| CV reading | AI on (Claude Haiku 5.5), 19 skills |
| AI role ranking | `rankedBy: formula`, `llmStatus: off:INVALID_OUTPUT` |
| Pathway coach | AI on (`personalisedBy: llm`) |

So the key works and the ranking call reaches Claude, but its answer is rejected and the formula ranking is used instead.

## Where it fails

`call_model` in `backend/signals/advisor/llm.py` (lines 118-129) maps three different failures to the same code:

1. **Answer cut off.** `stop_reason == "max_tokens"`. Ranking has `ADVISOR_MAX_TOKENS = 1200` and must return every role with chips and a summary of up to 240 characters. The coach gets 1500 tokens for fewer items and works. *Top suspect.*
2. **Field limit broken.** pydantic `ValidationError`, for example a summary over 240 characters or more than 3 `chip_ids`.
3. **Request rejected.** HTTP 400 `APIStatusError`, for example a schema feature the model doesn't accept.

## Plan

1. **Diagnose (no code change).** A scratch script makes one ranking call and prints only `stop_reason`, output token usage and the exception type. It costs about one cent from the $1/day cap.
2. **Fix only the cause step 1 finds:**
   - Cause 1: raise `ADVISOR_MAX_TOKENS` to about 3000, and/or send only the top 6 roles to the AI.
   - Cause 2: tighten the prompt (short summary, at most 3 chips). The code's limits stay.
   - Cause 3: change the schema so the API accepts it.
3. **Clearer status.** Add a `TRUNCATED` code next to `INVALID_OUTPUT` (about 3 lines).
4. **Test.** Add a unit test with a fake client returning `max_tokens`. Then smoke-test the 3 sample CVs (aina, daniel, priya) and expect `rankedBy: llm`.
5. **Ship.** Open a small PR into `main`, then republish on Replit.

## What changes

| Fix | Files | Reach |
|---|---|---|
| Raise `ADVISOR_MAX_TOKENS` | `advisor/llm.py` | Role ranking only; the coach has `COACH_MAX_TOKENS` |
| Top 6 roles to the AI | `advisor/service.py` | Role 7 and below stay in formula order (today role 7 could reach 5) |
| Prompt wording | `advisor/llm.py` (`ADVISOR_SYSTEM`) | Ranking text only |
| `TRUNCATED` status | `advisor/llm.py`, `tests/test_advisor.py` | Anything that checks the exact `INVALID_OUTPUT` text |

## Hidden side effects

1. **Daily cap use.** The spend gate reserves the maximum cost before each call, so a higher `max_tokens` reserves more. The real cost is settled afterwards, so the actual spend only rises by the tokens actually used.
2. **Cache.** `advisor_cache` holds old answers. Any prompt change must bump `PROMPT_VERSION` (`advisor-v2` to `v3`). After that, each profile makes one fresh AI call.
3. **Speed.** Longer answers take about 1-3 s more, still under the 45 s timeout.
4. **Replit.** Replit runs the same code, so it gets the fix after a republish. It uses the same key credit.
5. **AI off.** With no key or after a failure, the formula fallback is unchanged.

## Not affected

CV extraction, trend signals, job forecast, the pathway coach, saved profiles, the front end, and the safety checks (chips only from the given list, at most 2 places moved, no money or number claims).

## Out of scope (separate fixes)

- Demo routes (no saved CV) don't change the pathway: a front-end bug.
- ⚡ AI-trend chips are empty: the database has no recent stories, so the trend refresh needs to run.
- "Week 1 · 15 h" grouping and the "Interchange" legend: display bugs.
