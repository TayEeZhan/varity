"""The "why" sentence on each project row: a cheap model writes it from the formula's facts, code checks it.

The facts come from catalog.rank_projects (no LLM). The sentence is shown only when every number in it is one of
the facts' numbers and it names every skill the project closes. Otherwise, or while the model has not answered yet,
the row keeps catalog.why_line (the template). One call per project, role and week; the page polls, so the
sentence appears on a later load.
"""

from __future__ import annotations

import re
import threading
from datetime import date
from typing import Callable, Mapping

MAX_CHARS = 220
NUMBER = re.compile(r"\d+(?:\.\d+)?")
SYSTEM = (
    "Write ONE plain sentence (at most 30 words) that tells a job seeker why this project is worth doing.\n"
    "Use only the facts given. Name every skill in 'closes'. Do not add any number that is not in the facts.\n"
    "No quotes, no lists, no emoji. Answer with the sentence only."
)

# shortcut: the cache is per server process and lost on restart; move it to the database if calls repeat too often.
_cache: dict[tuple, str | None] = {}  # None: checked and failed, keep the template this week
_pending: set[tuple] = set()
_lock = threading.Lock()


def facts(row: Mapping, role_name: str) -> dict:
    """The only things the model may say. Gain is in match-score points (0..100), rounded."""
    return {"project": row["title"], "role": role_name, "closes": list(row["closes"]),
            "already_have": [s for s in row["skills"] if s not in row["closes"]],
            "match_points_gained": round(row["gain"] * 100), "level": row["level"]}


def checked(sentence: str, fact: Mapping) -> str | None:
    """The sentence when it passes the checks, else None."""
    text = " ".join((sentence or "").split()).strip().strip('"')
    if not text or len(text) > MAX_CHARS:
        return None
    if any(n != str(fact["match_points_gained"]) for n in NUMBER.findall(text)):
        return None
    low = text.lower()
    if any(s.lower() not in low for s in fact["closes"]):
        return None
    return text


def _key(row: Mapping, role_name: str, week: str) -> tuple:
    return (row["id"], role_name, tuple(row["closes"]), round(row["gain"] * 100), week)


def default_call() -> Callable[[str, str], str] | None:
    """DeepSeek V4 Flash on KrackedDevs, else Claude (Replit, then ANTHROPIC_API_KEY). None: no model, template only."""
    from advisor import service  # noqa: F401  puts the verity root (engine/) on sys.path
    from engine import llm_client

    if llm_client.kd_configured():
        return llm_client.kd_call("deepseek-v4-flash", "why")
    try:
        from engine.llm_labels import claude_call
        return claude_call()
    except Exception:  # noqa: BLE001 - no Claude credentials: keep the template
        return None


def _write(items: list[tuple[tuple, dict]], call: Callable[[str, str], str]) -> None:
    for key, fact in items:
        try:
            text = checked(call(SYSTEM, repr(fact)), fact)
        except Exception:  # noqa: BLE001 - a model failure keeps the template
            text = None
        with _lock:
            _pending.discard(key)
            _cache[key] = text


def _spawn(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True).start()


def apply(rows: list[dict], role_name: str, today: date | None = None,
          call_factory: Callable[[], Callable | None] | None = None, spawn=_spawn) -> list[dict]:
    """Rows with the checked model sentence where one is ready; asks for the missing ones in the background."""
    year, week, _ = (today or date.today()).isocalendar()
    out, todo = [], []
    with _lock:
        for row in rows:
            key = _key(row, role_name, f"{year}-W{week}")
            if key in _cache:
                out.append({**row, "why": _cache[key], "whyBy": "model"} if _cache[key] else row)
                continue
            out.append(row)
            if key not in _pending:
                _pending.add(key)
                todo.append((key, facts(row, role_name)))
    if todo:
        call = (call_factory or default_call)()
        if call is None:
            with _lock:
                _pending.difference_update(k for k, _ in todo)
        else:
            spawn(_write, todo, call)
    return out
