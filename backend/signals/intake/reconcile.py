"""Stage 7 and the Save step: review rows in, profile out.

build_review() joins verified LLM mentions, keyword hits and graph rules into one row per
skill. Nothing is saved there. apply_review() writes only the rows the user kept, through
intake.ledger, after the user presses Save.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Iterable

from intake import ledger
from intake.keyword_pass import KeywordHit, has_learning_cue
from intake.models import Basis, Evidence, Interest, Profile
from intake.skills import SkillGraph, canonicalise, expand
from intake.verify import MAX_QUOTE, Verification, phrase_regex

NOTE_INJECTION = "This line looks like an instruction to an AI, so it is not ticked."
NOTE_REMOVED = "You removed this skill before."
_METHOD = {("llm",): "llm", ("keyword",): "keyword", ("keyword", "llm"): "llm+keyword"}
_WINDOW_SIDE = 140


@dataclass(frozen=True)
class ReviewRow:
    skill_id: str
    name: str
    category: str | None
    basis: Basis
    why: str
    quote: str | None = None
    rule: str | None = None
    from_skill: str | None = None
    context: str | None = None
    years: float | None = None
    years_line: str | None = None
    methods: tuple[str, ...] = ()
    default_keep: bool = True
    note: str | None = None


@dataclass(frozen=True)
class ReviewInterest:
    skill_id: str
    name: str
    phrase: str
    quote: str | None


@dataclass(frozen=True)
class Review:
    rows: tuple[ReviewRow, ...]
    interests: tuple[ReviewInterest, ...] = field(default=())


def highlight(quote: str, phrase: str) -> str:
    """Mark the phrase inside its quote with «». Plain text only, never Markdown."""
    match = phrase_regex(phrase, re.IGNORECASE).search(quote)
    if not match:
        return quote
    return f"{quote[:match.start()]}«{match.group(0)}»{quote[match.end():]}"


def _window(line: str, phrase: str) -> str:
    """A long CV line is cut to the part around the phrase, so it fits the quote limit."""
    if len(line) <= MAX_QUOTE:
        return line
    start = max(line.find(phrase), 0)
    left = max(start - _WINDOW_SIDE, 0)
    return line[left:left + MAX_QUOTE].strip()


def _from_llm(verification: Verification, graph: SkillGraph, injection_lines: frozenset[int]) -> dict[str, ReviewRow]:
    rows: dict[str, ReviewRow] = {}
    for mention in verification.skills:
        named = canonicalise(mention.phrase, graph)
        current = rows.get(named.skill_id)
        # Keep the first quote, but take years from a later mention if the first had none.
        if current is not None:
            if current.years is None and mention.years is not None:
                rows[named.skill_id] = replace(current, years=mention.years, years_line=mention.years_line)
            continue
        suspicious = mention.line_no in injection_lines
        rows[named.skill_id] = ReviewRow(
            skill_id=named.skill_id, name=named.name, category=named.category, basis="stated",
            why=highlight(mention.quote, mention.phrase), quote=mention.quote,
            context=mention.context, years=mention.years, years_line=mention.years_line,
            methods=("llm",), default_keep=not suspicious,
            note=NOTE_INJECTION if suspicious else None,
        )
    return rows


def _add_keyword_hits(
    rows: dict[str, ReviewRow],
    interests: dict[str, ReviewInterest],
    hits: Iterable[KeywordHit],
    graph: SkillGraph,
    *,
    llm_ran: bool,
    interest_lines: set[int],
    injection_lines: frozenset[int],
) -> None:
    for hit in hits:
        if hit.skill_id in rows:
            row = rows[hit.skill_id]
            if "keyword" not in row.methods:
                rows[hit.skill_id] = replace(row, methods=tuple(sorted({*row.methods, "keyword"})))
            continue
        node = graph.nodes[hit.skill_id]
        quote = _window(hit.line, hit.phrase)
        if hit.line_no in interest_lines or has_learning_cue(hit.line):
            interests.setdefault(hit.skill_id, ReviewInterest(hit.skill_id, node.name, hit.phrase, quote))
            continue
        suspicious = hit.line_no in injection_lines
        # With the LLM up, a skill it did not confirm needs a tick. With it down, the keyword pass is all we have.
        rows[hit.skill_id] = ReviewRow(
            skill_id=hit.skill_id, name=node.name, category=node.category, basis="stated",
            why=highlight(quote, hit.phrase), quote=quote, methods=("keyword",),
            default_keep=not llm_ran and not suspicious,
            note=NOTE_INJECTION if suspicious else None,
        )


def _inferred_rows(rows: dict[str, ReviewRow], graph: SkillGraph) -> list[ReviewRow]:
    keep_by_id = {row.skill_id: row.default_keep for row in rows.values()}
    inferred = []
    for item in expand(rows.keys(), graph):
        implied = item.kind != "often_uses"
        inferred.append(ReviewRow(
            skill_id=item.skill_id, name=item.name, category=item.category,
            basis="implied" if implied else "suggested", why=item.rule, rule=item.rule,
            from_skill=item.from_skill, methods=("graph",),
            default_keep=implied and keep_by_id.get(item.from_skill, False),
        ))
    return inferred


def build_review(
    verification: Verification | None,
    hits: Iterable[KeywordHit],
    graph: SkillGraph,
    *,
    injection_lines: frozenset[int] = frozenset(),
    removed_ids: frozenset[str] = frozenset(),
) -> Review:
    """One row per skill: stated (LLM and/or keyword), then implied, then suggested."""
    llm_ran = verification is not None
    rows = _from_llm(verification, graph, injection_lines) if verification else {}
    interests: dict[str, ReviewInterest] = {}
    interest_lines: set[int] = set()
    for mention in verification.interests if verification else ():
        named = canonicalise(mention.phrase, graph)
        interests.setdefault(named.skill_id, ReviewInterest(named.skill_id, named.name, mention.phrase, mention.quote))
        interest_lines.add(mention.line_no)
    _add_keyword_hits(rows, interests, hits, graph, llm_ran=llm_ran,
                      interest_lines=interest_lines, injection_lines=injection_lines)
    # A skill counts if any non-interest line supports it.
    kept_interests = tuple(item for skill_id, item in interests.items() if skill_id not in rows)
    ordered = [
        replace(row, default_keep=False, note=NOTE_REMOVED) if row.skill_id in removed_ids else row
        for row in list(rows.values()) + _inferred_rows(rows, graph)
    ]
    return Review(rows=tuple(ordered), interests=kept_interests)


def _evidence_for(row: ReviewRow, now: str) -> Evidence:
    if row.basis == "stated":
        return Evidence(
            source="cv", method=_METHOD[tuple(sorted(row.methods))], context=row.context,
            quote=row.quote, years=row.years, years_line=row.years_line, added_at=now, added_by="intake",
        )
    if row.basis == "suggested":
        method = "graph:often_uses"
    else:
        method = "graph:requires" if " requires " in (row.rule or "") else "graph:part_of"
    return Evidence(source="inferred", method=method, context="inferred", rule=row.rule,
                    from_skill=row.from_skill, added_at=now, added_by="intake")


def apply_review(
    profile: Profile,
    review: Review,
    kept_ids: Iterable[str],
    *,
    edited_years: dict[str, float | None] | None = None,
    now: str | None = None,
    as_of: str | None = None,
) -> Profile:
    """Write the rows the user kept. A rule-based row only counts if the skill it comes from is kept."""
    kept = set(kept_ids)
    stamp = now or ledger.now_iso()
    stated_kept = {row.skill_id for row in review.rows if row.basis == "stated" and row.skill_id in kept}
    have = stated_kept | {entry.skill_id for entry in profile.skills}
    for row in review.rows:
        if row.skill_id not in kept:
            continue
        if row.from_skill is not None and row.from_skill not in have:
            continue
        if ledger.is_removed(profile, row.skill_id):
            profile = ledger.restore_skill(profile, row.skill_id, now=stamp, as_of=as_of)
        profile = ledger.add_evidence(profile, row.skill_id, row.name, _evidence_for(row, stamp),
                                      caller="intake", category=row.category, now=stamp, as_of=as_of)
        years = (edited_years or {}).get(row.skill_id)
        if years is not None and years != row.years:
            # A number the user typed is their own claim, so it is stored as self-reported.
            profile = ledger.add_evidence(
                profile, row.skill_id, row.name,
                Evidence(source="form", method="user_entry", context="user", years=years,
                         note="Years entered by the user", added_at=stamp, added_by="user"),
                caller="user", category=row.category, now=stamp, as_of=as_of)
    for item in review.interests:
        quote = item.quote[:MAX_QUOTE] if item.quote else None
        profile = ledger.add_interest(profile, Interest(phrase=item.phrase[:60], skill_id=item.skill_id, quote=quote), now=stamp)
    return profile
