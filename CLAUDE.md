# Verity

Read `HANDOFF.md` first, starting with its newest "Update" section. It has the current state, the decisions and the status of every request.
Plans live in `tasks/plan-*.md`. Feature status is in `docs/architecture.md`.

- Do not commit or push to GitHub unless the user says so in this chat.
- Never invent numbers. LLMs never produce forecast numbers, parameters or rankings. Claude may label posts and review titles only with quotes that code checks.
- Job data is Hacker News only (the Malaysian job boards are dropped).
- Write in Simplified Technical English: short sentences, active voice.
- Tests: `.venv\Scripts\python -m pytest -q` (root, about 8 min) and `pytest -q` in `backend/signals/`.
- When work changes the state, update the newest section of `HANDOFF.md`.
