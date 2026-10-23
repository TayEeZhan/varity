"""Stage 5: the verification gates G1 to G5 (doc section 5).

The LLM points, this module proves. A mention is kept only if:
- G1 its quote is in the CV (after the same cleaning on both sides),
- G2 its phrase is inside its own quote, as a whole word,
- G5 it is not a duplicate and the cap is not reached.
G3 sends "interest" mentions to their own list. G4 reads years from a quoted line in the
same block; the model never supplies the number.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from datetime import date

from intake.models import Mention
from intake.normalise import clean_chars, norm

MIN_QUOTE, MAX_QUOTE = 3, 300
MAX_PHRASE = 60
MAX_MENTIONS = 40
YEARS_WINDOW_LINES = 20
MAX_YEARS = 40.0
EARLIEST_YEAR = 1970
# Years only mean experience for jobs and projects, not for a degree's dates.
YEARS_CONTEXTS = {"work", "project"}

QUOTE_REASONS = {"QUOTE_NOT_FOUND", "PHRASE_NOT_IN_QUOTE"}

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_MONTHS = {name: number for number, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_RANGE = re.compile(
    rf"(?:(?P<sm>{_MONTH})\s+)?(?P<sy>(?:19|20)\d\d)\s*(?:-|to|until)\s*"
    rf"(?:(?P<em>{_MONTH})\s+)?(?P<ey>(?:19|20)\d\d|present|current|now|today)\b"
)
# "N years" counts only in an experience phrase. "10 years of daily prices" is not experience.
_STATED_YEARS = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|professional|commercial|hands-on|industry|working)"
    r"|\((\d{1,2})\+?\s*(?:years?|yrs?)\)"
    r"|(?:experience|worked|working)\s+(?:of|for)\s+(\d{1,2})\+?\s*(?:years?|yrs?)"
)


@dataclass(frozen=True)
class VerifiedMention:
    phrase: str
    quote: str
    context: str
    line_no: int
    years: float | None
    years_line: str | None


@dataclass(frozen=True)
class Dropped:
    phrase: str
    reason: str


@dataclass(frozen=True)
class Verification:
    skills: tuple[VerifiedMention, ...]
    interests: tuple[VerifiedMention, ...]
    dropped: tuple[Dropped, ...]


class _Locator:
    """Finds a quote in the CV and says which line it starts on."""

    def __init__(self, cv_text: str):
        parts: list[str] = []
        self._starts: list[int] = []
        self._line_numbers: list[int] = []
        position = 0
        for number, line in enumerate(cv_text.split("\n")):
            cleaned = norm(line)
            if not cleaned:
                continue
            parts.append(cleaned)
            self._starts.append(position)
            self._line_numbers.append(number)
            position += len(cleaned) + 1
        self.flat = " ".join(parts)

    def find(self, text: str) -> int | None:
        target = norm(text)
        index = self.flat.find(target) if target else -1
        if index < 0:
            return None
        return self._line_numbers[bisect.bisect_right(self._starts, index) - 1]


def phrase_regex(phrase: str, flags: int = 0) -> re.Pattern[str]:
    """Whole-word match that treats + and # as part of a word, and a leading dot too.

    So "C" is not found in "C++", "JS" is not found in "Node.js", but "C++", "C#",
    ".NET", "Node.js" and "CI" in "CI/CD" are.
    """
    return re.compile(rf"(?<![\w.+#]){re.escape(phrase)}(?![\w+#])", flags)


def phrase_in_quote(phrase: str, quote: str) -> bool:
    """G2: the phrase is inside its own quote."""
    target = norm(phrase)
    if not target:
        return False
    return phrase_regex(target).search(norm(quote)) is not None


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def years_from_text(text: str, as_of: date) -> float | None:
    """Read years from one line: an experience phrase, or a date range. Otherwise None."""
    cleaned = norm(text)
    stated = _STATED_YEARS.search(cleaned)
    if stated:
        value = float(next(group for group in stated.groups() if group))
        return value if 0 < value <= MAX_YEARS else None
    found = _RANGE.search(cleaned)
    if not found:
        return None
    start_year = int(found["sy"])
    start_month = _MONTHS[found["sm"][:3]] if found["sm"] else 1
    end_text = found["ey"]
    now_index = _month_index(as_of.year, as_of.month)
    if end_text.isdigit():
        end_month = _MONTHS[found["em"][:3]] if found["em"] else 12
        end_index = min(_month_index(int(end_text), end_month), now_index)
    else:
        end_index = now_index
    start_index = _month_index(start_year, start_month)
    if start_year < EARLIEST_YEAR or start_index > now_index or end_index < start_index:
        return None
    years = round((end_index - start_index + 1) / 12, 1)
    return years if years <= MAX_YEARS else None


def _years_for(mention: Mention, quote_line: int, locator: _Locator, as_of: date) -> tuple[float | None, str | None]:
    """G4. The years line must be in the CV and in the same block, at most 20 lines above."""
    if mention.context not in YEARS_CONTEXTS or not mention.years_quote:
        return None, None
    years_line = clean_chars(mention.years_quote).strip()[:MAX_QUOTE]
    line = locator.find(years_line)
    if line is None or not 0 <= quote_line - line <= YEARS_WINDOW_LINES:
        return None, None
    years = years_from_text(years_line, as_of)
    return (years, years_line) if years is not None else (None, None)


def _check(mention: Mention, locator: _Locator) -> tuple[str | None, int | None]:
    """G1 and G2. Returns (reason it fails, line number)."""
    phrase = clean_chars(mention.phrase).strip()
    quote = clean_chars(mention.evidence_quote).strip()
    if not phrase or len(phrase) > MAX_PHRASE:
        return "PHRASE_LENGTH", None
    if not MIN_QUOTE <= len(quote) <= MAX_QUOTE:
        return "QUOTE_LENGTH", None
    line = locator.find(quote)
    if line is None:
        return "QUOTE_NOT_FOUND", None
    if not phrase_in_quote(phrase, quote):
        return "PHRASE_NOT_IN_QUOTE", None
    return None, line


def verify(mentions: list[Mention], cv_text: str, as_of: date) -> Verification:
    """Run G1 to G5 on every mention. Nothing the model said survives without a check."""
    locator = _Locator(cv_text)
    skills: list[VerifiedMention] = []
    interests: list[VerifiedMention] = []
    dropped: list[Dropped] = []
    seen: set[tuple[str, str]] = set()
    for mention in mentions:
        label = clean_chars(mention.phrase).strip()[:MAX_PHRASE]
        reason, line = _check(mention, locator)
        key = (norm(mention.phrase), norm(mention.evidence_quote))
        if reason is None and key in seen:
            reason = "DUPLICATE"
        if reason is None and len(skills) + len(interests) >= MAX_MENTIONS:
            reason = "OVER_LIMIT"
        if reason is not None:
            dropped.append(Dropped(phrase=label, reason=reason))
            continue
        seen.add(key)
        years, years_line = _years_for(mention, line, locator, as_of)
        verified = VerifiedMention(
            phrase=clean_chars(mention.phrase).strip(),
            quote=clean_chars(mention.evidence_quote).strip(),
            context=mention.context,
            line_no=line,
            years=years,
            years_line=years_line,
        )
        (interests if mention.context == "interest" else skills).append(verified)
    return Verification(skills=tuple(skills), interests=tuple(interests), dropped=tuple(dropped))
