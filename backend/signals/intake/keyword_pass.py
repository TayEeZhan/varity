"""Stage 3: find known skills line by line. Free, offline, needs no key.

It runs on every intake. With the LLM down it is the only automatic source, so short or
common words carry context guards in skill_graph.json ("Go to market" is not Go,
"Grade C" is not C, "React Native" is not React).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from intake.skills import SkillGraph, SkillNode

# Lines that talk about learning or wanting a skill, not using it.
LEARNING_CUE = re.compile(
    r"\b(?:currently|now|still)\s+learning\b|\blearning\s+goals?\b|\bwants?\s+to\s+learn\b"
    r"|\bwould\s+like\s+to\s+learn\b|\binterested\s+in\b|\bplan(?:ning)?\s+to\s+(?:learn|study)\b"
    r"|\bhope\s+to\s+learn\b|\bkeen\s+to\s+learn\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class KeywordPattern:
    skill_id: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class KeywordHit:
    skill_id: str
    phrase: str
    line: str
    line_no: int


def _node_pattern(node: SkillNode) -> re.Pattern[str]:
    flags = 0 if node.case_sensitive else re.IGNORECASE
    if node.pattern:
        return re.compile(node.pattern, flags)
    # Longest first, so "Microsoft Excel" wins over "Excel" inside the same alternation.
    terms = sorted({node.name, *node.synonyms}, key=len, reverse=True)
    alternation = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", flags)


def build_patterns(graph: SkillGraph) -> tuple[KeywordPattern, ...]:
    """One compiled pattern per skill. lookup_only names are left out on purpose."""
    return tuple(KeywordPattern(skill_id=node.id, regex=_node_pattern(node)) for node in graph.nodes.values())


def keyword_hits(cv_text: str, patterns: tuple[KeywordPattern, ...]) -> tuple[KeywordHit, ...]:
    """Every (skill, line) pair where a pattern matches. The matched text is the phrase."""
    hits: list[KeywordHit] = []
    for line_no, line in enumerate(cv_text.split("\n")):
        if not line.strip():
            continue
        for pattern in patterns:
            match = pattern.regex.search(line)
            if match:
                hits.append(KeywordHit(skill_id=pattern.skill_id, phrase=match.group(0), line=line, line_no=line_no))
    return tuple(hits)


def has_learning_cue(line: str) -> bool:
    return LEARNING_CUE.search(line) is not None
