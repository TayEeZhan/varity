"""Code checks that an upload is a CV before its skills are shown. No AI; each check names what it found."""
from __future__ import annotations

import re

MIN_WORDS = 25
HEADINGS = re.compile(r"\b(experience|education|skills|projects?|employment|work history|internships?|"
                      r"certifications?|qualifications|summary|profile|resume|r[ée]sum[ée]|curriculum vitae|"
                      r"university|degree|diploma|bachelor|master'?s)\b", re.I)
SIGNS = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b|[\w.+-]+@[\w-]+\.[\w.]+|linkedin\.com|github\.com", re.I)
AD_PHRASES = re.compile(r"\b(we are looking for|we're looking for|you will|you'll|requirements|"
                        r"responsibilities|apply now|about the role|what we offer|benefits|join our team|"
                        r"the ideal candidate|job description)\b", re.I)
HEADING_LINE = re.compile(r"\b(experience|education|projects?|employment|work history)\b\s*:?\s*$", re.I | re.M)

TRY = " Upload your CV (PDF, Word or text) and try again."
MESSAGES = {
    "TOO_SHORT": f"This is too short to be a CV (under {MIN_WORDS} words)." + TRY,
    "JOB_AD": "This looks like a job ad, not a CV. Paste job ads in the CV builder instead." + TRY,
    "NOT_CV": "This does not look like a CV: it has no CV sections (such as Experience, Education or Skills), "
              "no dates and no contact details." + TRY,
    "NO_SKILLS": "This does not look like a CV: we found no tech skills in it." + TRY,
}


def cv_problem(text: str, has_skills: bool) -> str | None:
    """Return a MESSAGES key when the text is not a CV, else None."""
    if len(text.split()) < MIN_WORDS:
        return "TOO_SHORT"
    if len(set(m.lower() for m in AD_PHRASES.findall(text))) >= 2 and not HEADING_LINE.search(text):
        return "JOB_AD"
    if not HEADINGS.search(text) and not SIGNS.search(text):
        return "NOT_CV"
    if not has_skills:
        return "NO_SKILLS"
    return None
