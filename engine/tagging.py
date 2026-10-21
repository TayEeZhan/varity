"""Tag job-post text with canonical skill names.

Input is HN comment text. It is HTML, so we clean it first.
Each taxonomy entry has a regex. We compile each regex once.

Counting rules (kept simple on purpose):
- We count what the post says. We never infer a skill from another skill.
  Example: "PostgreSQL" counts as PostgreSQL only, not as SQL.
- "React Native" counts as React Native only, not as React.
- "Generative AI" counts as LLM / GenAI only, not as Machine Learning.
- A bare "AI" ("we are an AI startup") is not a skill. "ML", "AI engineer",
  "machine learning" and similar phrases count as Machine Learning.
- "TypeScript" counts in both "JavaScript / TypeScript" and "TypeScript".
- "NoSQL", "MySQL" and "SQLite" do not count as SQL.
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Default location: <repo>/data/taxonomy.json
DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "data" / "taxonomy.json"

# Every taxonomy entry must have these keys.
REQUIRED_KEYS = ("skill", "pattern", "case_sensitive")

# Block tags become a newline. This keeps "Spark<p>Our team" as two lines.
_BLOCK_TAG = re.compile(r"</?(?:p|br|li|ul|ol|pre|div|h[1-6]|tr|td)\b[^<>]*>", re.IGNORECASE)
# Any other tag becomes a space. A tag must start with a letter or "/",
# so plain text like "C++ <3 Rust" is not treated as a tag.
_ANY_TAG = re.compile(r"</?[A-Za-z][^<>]*>")
# URLs add noise, for example "github.com/rust-lang". We remove them.
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def load_taxonomy(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read the taxonomy JSON file and check that each entry has the needed keys."""
    file_path = Path(path) if path is not None else DEFAULT_TAXONOMY_PATH
    with file_path.open(encoding="utf-8") as f:
        taxonomy = json.load(f)
    if not isinstance(taxonomy, list):
        raise ValueError(f"Taxonomy must be a JSON list: {file_path}")
    for entry in taxonomy:
        missing = [key for key in REQUIRED_KEYS if key not in entry]
        if missing:
            raise ValueError(f"Taxonomy entry {entry.get('skill')!r} is missing {missing}")
    return taxonomy


def clean_text(text: str) -> str:
    """Turn HN comment HTML into plain text.

    Order matters. We strip tags first, then decode entities. If we decoded
    first, an encoded "&lt;" in the text could look like a tag start.
    """
    text = _BLOCK_TAG.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html.unescape(text)
    return _URL.sub(" ", text)


@lru_cache(maxsize=None)
def _compile(pattern: str, case_sensitive: bool) -> re.Pattern[str]:
    """Compile a pattern once. The cache means later calls cost almost nothing."""
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def tag_text(text: str, taxonomy: list[dict[str, Any]]) -> set[str]:
    """Return the canonical names of all skills mentioned in the text."""
    if not text:
        return set()
    clean = clean_text(text)
    return {
        entry["skill"]
        for entry in taxonomy
        if _compile(entry["pattern"], bool(entry["case_sensitive"])).search(clean)
    }
