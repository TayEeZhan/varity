# Review: branch `AI-trend-signal-layer` (Sheng Kuan)

Reviewed on 23 Oct 2026 at commit `ba86df2`, read-only, by a stronger model (Claude Opus).

## Result
- **It works.** In a clean environment, 211 tests pass with 93% coverage. A live run with HN and OpenAI News (86 items, 71 stories) wrote `data/ranked/latest.json`, the CSV, and per-run JSON. With no key it ranks by the deterministic formula.
- **It merges cleanly.** Everything is inside `ai-trend-signal-layer/`, so it does not touch `app.py`, `engine/` or `data/`.
- **It is not connected to Verity yet,** so judges cannot see it in the app.

## Must fix before merge
1. **Commit history.** 6 commits holding about 7,600 lines were made within 2 seconds (22 Oct, 13:13:42–44). This looks like a dump of work done elsewhere. The final round can disqualify "pre-built repos with one big late commit". From now on make small, dated commits, and be ready to explain how and when the code was written.
2. **Rebase on the current `main`.** The branch is 24 commits behind. Use the GitHub noreply email for commits. The commits currently show a university email.
3. **Add a non-LLM `excerpt` field** to each story in `latest.json` (plain source text, never LLM-written). Verity needs it to tag stories with its 40 skills. Titles alone matched only 12 of 45 stories.
4. **Keep one skill list.** Drop the 10-skill `config/watchlist.yaml` momentum and `skills.json`, or rename them as clearly separate. Verity's `data/taxonomy.json` must stay the only skill list.
5. **Make the README match the code:**
   - Jev is "pinned to jev-1.13.0", but the Replit route defaults to `jev-latest` (`config.py:126`).
   - Rate limits now wait and retry (commit d378d0d).
   - The OpenRouter jury models are not listed.
   - "No LLM in the scoring path" is not true when Jev is a hosted model.
6. **Label every LLM-written field as AI-generated:**
   - The Haiku `why_it_matters` and `tldr` fields have no label (`web/templates/_card.html:14`).
   - Jury votes are labelled `"jury of N models"` in the gold set (`eval/jury.py:163`). They are not human ground truth, so keep them apart from human labels.
7. **No social sources in anything Verity shows** (X, Threads, Bluesky): they hold personal data and come with terms limits. Delete the committed snapshot rows that come from social posts.
8. **Pin the requirements (`==`)** and split them into core and optional extras (web feed, anthropic, typesafe). Do not add them to Verity's root `requirements.txt`.
9. **Write a one-page "how it works"** you can explain without notes: the formula, the guardrails, and Jev's role.

## Good
- No secrets in the history. `.env` is gitignored and `.env.example` is blank. Admin endpoints use `hmac.compare_digest`.
- Every story carries a `url` and its source names.
- Sources are RSS/Atom feeds or official APIs, not HTML scraping, and the user agent is declared.
- Licences are fine: typesafe-sdk MIT, anthropic Apache-2.0, feedparser BSD-2, APScheduler MIT, FastAPI/pydantic MIT, httpx/uvicorn/jinja2 BSD-3.

## Integration plan into Verity
1. Sheng Kuan fixes 1–3, then rebases.
2. Add `engine/ai_news.py` with `load_ranked()`, `tag_stories()` (our `tag_text` on title plus excerpt), `weekly_skill_impact()` and `monthly_ext_momentum()`. Test it with a fixture `latest.json`.
3. Write `data/ai_news_weekly.csv` (week, skill, n_stories, impact_sum from `formula_score/100`, momentum, example_story_ids) and `data/ai_news_stories.json` (tier A/B/C sources only). Document both in `docs/data-contract.md` and `data/SOURCES.md`.
4. In the app, add a "This week in AI for your skills" block: the top 3 stories with links, source names, and "ranked by formula". Hide the block if the file is missing.
5. Update the submission documents: declare Jev (TypeSafe, via Replit AI Integrations / OpenRouter, exact model id), Haiku and Sonnet if enabled, and the jury models. Change every "no LLM" line.
6. Later, only after a historical backfill: feed `monthly_ext_momentum` into `engine/ml_forecast.py` as `ext_momentum`, rerun the backtest, and keep it only if it beats persistence.
