"""Clean CV text before anything reads it.

The same cleaning runs on the CV and on every quote the LLM returns, so the quote check
(intake.verify, G1) compares like with like. Order matters:
1. NFKC first, so fullwidth "＜" becomes "<" before step 3 replaces it.
2. Drop invisible characters (Unicode tag characters, zero-width spaces, bidi overrides).
   They can hide instructions from the reader and spoof the quote shown on screen.
3. Replace "<" and ">" so the CV can never close the <cv_document> tag around it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Format, control, private-use and unassigned code points. Newlines are kept.
_INVISIBLE = {"Cf", "Cc", "Co", "Cn"}
_KEEP = {"\n"}
_CHAR_MAP = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "\t": " ",
    "<": "‹", ">": "›",
})
# A word split by a line-end hyphen in PDF text: "develop-\nment".
_LINE_HYPHEN = re.compile(r"([a-z])-\n([a-z])")
_SPACES = re.compile(r"[ ]{2,}")
_MANY_NEWLINES = re.compile(r"\n{3,}")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(
    r"(?:https?://|www\.)\S+|\b(?:github\.com|gitlab\.com|linkedin\.com|bitbucket\.org)/\S*",
    re.IGNORECASE,
)
_NRIC = re.compile(r"(?<!\d)\d{6}-\d{2}-\d{4}(?!\d)")
_PHONE_CANDIDATE = re.compile(r"(?<!\w)\+?\d[\d ().-]{6,}\d(?!\w)")
_YEAR = re.compile(r"(?:19|20)\d\d")
MIN_PHONE_DIGITS = 9

# A hint only, never a control: it is easy to get around. See the doc, section 7.
_INJECTION = re.compile(
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)"
    r"|system prompt|you are now|^\W*(?:system|assistant)\s*:|‹/?cv_document",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class CleanText:
    text: str
    redactions: dict[str, int] = field(default_factory=dict)
    injection_lines: frozenset[int] = frozenset()


def clean_chars(text: str) -> str:
    """Character-level cleaning shared by the CV and the quotes. No redaction here."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in _KEEP or unicodedata.category(ch) not in _INVISIBLE)
    text = text.translate(_CHAR_MAP)
    return _LINE_HYPHEN.sub(r"\1\2", text)


def norm(text: str) -> str:
    """Comparison form: cleaned, casefolded, every run of whitespace (newlines too) is one space."""
    return re.sub(r"\s+", " ", clean_chars(text).casefold()).strip()


def _redact_phone(match: re.Match[str]) -> str:
    candidate = match.group(0)
    digits = re.sub(r"\D", "", candidate)
    if len(digits) < MIN_PHONE_DIGITS:
        return candidate
    # "2019 - 2023 2023 - 2024" is a list of years, not a phone number.
    if all(_YEAR.fullmatch(group) for group in re.findall(r"\d+", candidate)):
        return candidate
    return "[phone]"


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Replace contact details and IDs. The LLM never needs them (data minimisation)."""
    counts: dict[str, int] = {}
    text, counts["email"] = _EMAIL.subn("[email]", text)
    text, counts["link"] = _URL.subn("[link]", text)
    text, counts["id"] = _NRIC.subn("[id]", text)
    phones_before = text.count("[phone]")
    text = _PHONE_CANDIDATE.sub(_redact_phone, text)
    counts["phone"] = text.count("[phone]") - phones_before
    return text, {kind: count for kind, count in counts.items() if count}


def tidy_lines(text: str) -> str:
    """Collapse runs of spaces inside lines and runs of blank lines."""
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def injection_lines(text: str) -> frozenset[int]:
    """Line numbers (0-based) that look like instructions to a model."""
    return frozenset(
        number for number, line in enumerate(text.split("\n")) if _INJECTION.search(line)
    )


def clean_cv_text(raw: str) -> CleanText:
    """The full stage-2 normaliser. Its output is the only text quotes are checked against."""
    text = tidy_lines(clean_chars(raw))
    text, counts = redact(text)
    return CleanText(text=text, redactions=counts, injection_lines=injection_lines(text))
