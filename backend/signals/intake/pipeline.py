"""Stages 2 to 7 in one call. The profile page and the tests use this; it saves nothing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from intake.keyword_pass import KeywordPattern, keyword_hits
from intake.llm_extract import LlmUnavailable
from intake.models import Extraction
from intake.normalise import clean_cv_text
from intake.readers import MAX_CHARS, ReadError
from intake.reconcile import Review, build_review
from intake.skills import SkillGraph
from intake.verify import QUOTE_REASONS, Dropped, Verification, verify

# (clean CV text, retry reason codes) -> the model's answer, or LlmUnavailable.
Extractor = Callable[[str, tuple[str, ...]], Extraction]
# Ask once more when at least this share of mentions fail the quote checks.
RETRY_SHARE = 0.25


@dataclass(frozen=True)
class IntakeResult:
    cv_text: str
    review: Review
    dropped: tuple[Dropped, ...]
    llm_status: str  # "llm", "cached", or "off:<reason code>"
    injection_hint: bool
    redactions: dict[str, int] = field(default_factory=dict)


def _quote_failures(verification: Verification) -> list[str]:
    return [item.reason for item in verification.dropped if item.reason in QUOTE_REASONS]


def _kept(verification: Verification) -> int:
    return len(verification.skills) + len(verification.interests)


def _run_llm(extractor: Extractor, cv_text: str, as_of: date) -> Verification:
    """One call, verified. One retry with fixed reason codes if too many quotes fail."""
    extraction = extractor(cv_text, ())
    first = verify(extraction.mentions, cv_text, as_of)
    failures = _quote_failures(first)
    if not extraction.mentions or len(failures) < RETRY_SHARE * len(extraction.mentions):
        return first
    try:
        second = verify(extractor(cv_text, tuple(sorted(set(failures)))).mentions, cv_text, as_of)
    except LlmUnavailable:
        return first
    return second if _kept(second) > _kept(first) else first


def run_intake(
    raw_text: str,
    *,
    graph: SkillGraph,
    patterns: tuple[KeywordPattern, ...],
    extractor: Extractor | None = None,
    llm_label: str = "llm",
    off_reason: str = "SWITCHED_OFF",
    as_of: date | None = None,
    removed_ids: frozenset[str] = frozenset(),
) -> IntakeResult:
    """Clean the text, run the keyword pass and (if given) the LLM, then build review rows."""
    clean = clean_cv_text(raw_text)
    if not clean.text:
        raise ReadError("EMPTY")
    if len(clean.text) > MAX_CHARS:
        raise ReadError("TOO_LONG")
    as_of = as_of or date.today()
    verification: Verification | None = None
    status = f"off:{off_reason}"
    if extractor is not None:
        try:
            verification = _run_llm(extractor, clean.text, as_of)
            status = llm_label
        except LlmUnavailable as exc:
            status = f"off:{exc.code}"
    review = build_review(
        verification,
        keyword_hits(clean.text, patterns),
        graph,
        injection_lines=clean.injection_lines,
        removed_ids=removed_ids,
    )
    return IntakeResult(
        cv_text=clean.text,
        review=review,
        dropped=verification.dropped if verification else (),
        llm_status=status,
        injection_hint=bool(clean.injection_lines),
        redactions=clean.redactions,
    )
