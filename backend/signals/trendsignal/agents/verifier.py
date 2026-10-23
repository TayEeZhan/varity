"""Claim verifier: a code gate between the Editor agent and the reader.

Checks per content line: it cites [S<id>] stories from this brief; it has no raw HTML or
reference-style link definitions; every link is a cited story's source URL; every number,
and every capitalised name, appears in the cited stories' stored data; and most of its
content words come from those stories. Headings must be the title or a known section.
Failing lines are stripped. The brief also fails if a required (Must-know) story is missing
or if too many lines fail; the caller then publishes the template instead.

This is a lexical check, not proof: it catches invented names, numbers and links, and lines
about the wrong story, but a reworded claim using the story's own words can still pass.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

CITATION_RE = re.compile(r"\[S(\d+)\]")
URL_RE = re.compile(r"https?://[^\s)\]>]+")
MD_LINK_TARGET_RE = re.compile(r"\]\(\s*([^)\s]+)")
REF_DEFINITION_RE = re.compile(r"^\s*\[[^\]]+\]:")
RAW_HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
LIST_MARKER_RE = re.compile(r"^\s*(?:\d+\.|[-*•])\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9.+#'-]*[A-Za-z0-9+#]|[A-Za-z]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?:])\s+")
UNSAFE_HEADING_RE = re.compile(r"[\[\]()<>]|https?:|javascript:", re.IGNORECASE)
SECTION_PREFIXES = ("🔴 Must-know", "🟠 Worth a look", "🟡 Emerging", "⚪ Minor", "🗓️ The week")
MIN_CONTENT_OVERLAP = 0.4
DEFAULT_MAX_FAILURE_RATIO = 0.3

# Words an editor may use freely: they frame a story rather than state facts about it.
EDITORIAL_WORDS = frozenset("""
    about after also another because been before being both brief check could does done each even every
    from further have here into just know latest look make matters might more most much must need needs
    news only other over read really same should since some source sources still such than that their
    them then there these they this those through today very want week were what when where which while
    will with within worth would your you're yours update updates upgrade upgrading using worth-a-look
    developers developer students student users team teams people anyone everyone work working build
    building ship shipping keep watch try trying time minutes min ranked here why matters must-know
    emerging confirmed unconfirmed social posts official report reports story stories summary details
    worth look minor section daily weekly brief nothing cleared today's this-week
""".split())


@dataclass(frozen=True)
class StoryFacts:
    id: int
    urls: frozenset[str]
    text: str  # every stored field the brief may quote: title, TL;DR, reasons, minutes, scores

    @property
    def numbers(self) -> frozenset[str]:
        return frozenset(_normalise_number(n) for n in NUMBER_RE.findall(self.text))

    @property
    def words(self) -> frozenset[str]:
        return frozenset(w.lower().strip("'") for w in WORD_RE.findall(self.text))


@dataclass(frozen=True)
class Verification:
    body: str
    checked_lines: int
    failed_lines: int
    problems: tuple[str, ...] = field(default_factory=tuple)
    missing_required: tuple[int, ...] = ()

    @property
    def failure_ratio(self) -> float:
        return self.failed_lines / self.checked_lines if self.checked_lines else 1.0

    def passed(self, max_failure_ratio: float = DEFAULT_MAX_FAILURE_RATIO) -> bool:
        return self.checked_lines > 0 and not self.missing_required and self.failure_ratio <= max_failure_ratio

    def as_dict(self) -> dict:
        return {"checked_lines": self.checked_lines, "failed_lines": self.failed_lines,
                "failure_ratio": round(self.failure_ratio, 3), "missing_required": list(self.missing_required),
                "problems": list(self.problems[:20])}


def _normalise_number(text: str) -> str:
    return text.rstrip("0").rstrip(".") if "." in text else text.lstrip("0") or "0"


def heading_problem(line: str, title: str | None) -> str | None:
    if UNSAFE_HEADING_RE.search(line):
        return "heading contains a link or markup"
    text = line.lstrip("#").strip()
    if line.startswith("# ") and title is not None and text == title:
        return None
    if line.startswith("## ") and text.startswith(SECTION_PREFIXES):
        return None
    return "heading is not the title or a known section"


def _content_words(line: str) -> list[str]:
    words = [w.lower().strip("'") for w in WORD_RE.findall(line)]
    return [w for w in words if len(w) >= 4 and w not in EDITORIAL_WORDS]


def _unknown_names(line: str, known: frozenset[str]) -> list[str]:
    """Capitalised words that do not start a sentence must be names found in the cited stories."""
    unknown = []
    for sentence in SENTENCE_SPLIT_RE.split(line):
        for word in WORD_RE.findall(sentence.strip(" *_-"))[1:]:
            lowered = word.lower().strip("'")
            if word[0].isupper() and lowered not in known and lowered not in EDITORIAL_WORDS:
                unknown.append(word)
    return unknown


def check_line(line: str, facts: dict[int, StoryFacts]) -> str | None:
    """Return a problem description, or None if the line passes."""
    if REF_DEFINITION_RE.match(line):
        return "reference-style link definitions are not allowed"
    ids = [int(x) for x in CITATION_RE.findall(line)]
    if not ids:
        return "no citation"
    unknown = [i for i in ids if i not in facts]
    if unknown:
        return f"cites stories outside this brief: {unknown}"
    if RAW_HTML_RE.search(line):
        return "raw HTML is not allowed"
    cited = [facts[i] for i in ids]
    allowed_urls = frozenset().union(*(f.urls for f in cited))
    link_targets = MD_LINK_TARGET_RE.findall(line)
    bad_urls = [u for u in [*URL_RE.findall(line), *link_targets] if u.rstrip(".,") not in allowed_urls]
    if bad_urls:
        return f"link not from a cited source: {bad_urls[0]}"

    prose = LIST_MARKER_RE.sub("", URL_RE.sub(" ", CITATION_RE.sub(" ", re.sub(r"\]\([^)]*\)", "]", line))))
    allowed_numbers = frozenset().union(*(f.numbers for f in cited))
    bad_numbers = [n for n in NUMBER_RE.findall(prose) if _normalise_number(n) not in allowed_numbers]
    if bad_numbers:
        return f"number not in the cited story: {bad_numbers[0]}"
    known_words = frozenset().union(*(f.words for f in cited))
    names = _unknown_names(prose, known_words)
    if names:
        return f"name not in the cited story: {names[0]}"
    content = _content_words(prose)
    if len(content) >= 3 and sum(1 for w in content if w in known_words) / len(content) < MIN_CONTENT_OVERLAP:
        return "line is mostly about things the cited story does not mention"
    return None


def verify_brief(markdown: str, facts: dict[int, StoryFacts], *, title: str | None = None,
                 required_ids: Iterable[int] = ()) -> Verification:
    kept, problems = [], []
    checked = failed = 0
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or stripped in ("---", "***"):
            kept.append(line)
            continue
        checked += 1
        problem = heading_problem(stripped, title) if stripped.startswith("#") else check_line(stripped, facts)
        if problem is None:
            kept.append(line)
        else:
            failed += 1
            problems.append(f"{problem} :: {stripped[:120]}")
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() + "\n"
    cited_in_body = {int(x) for x in CITATION_RE.findall(body)}
    missing = tuple(sorted(set(required_ids) - cited_in_body))
    if missing:
        problems.append(f"required Must-know stories missing: {list(missing)}")
    return Verification(body, checked, failed, tuple(problems), missing)
