"""Lexical similarity (TF-IDF cosine) and key-term extraction.

The plan named a small embedding model; on Python 3.14 / Replit a pure-Python TF-IDF keeps
the install light and runs in milliseconds for a few thousand stories. Key terms (model
names, version numbers) make up for TF-IDF missing paraphrases of the same announcement.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#-]*[a-z0-9+#]|[a-z0-9]")
WORD_RE = re.compile(r"[A-Za-z0-9][\w.+#-]*")
VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)+[a-z0-9-]*$")

STOPWORDS = frozenset(
    """a an and are as at be by for from has have how in into is it its of on or our that the their this
    to was we what when which who why will with you your new now just more most can not no all about after
    over than then there these they those via vs using use used one two get gets got make makes made""".split()
)
GENERIC_CAPS = frozenset(
    """the a an new how why what when show ask tell hn introducing announcing announces announced release
    released releases launch launches launched today update updates we our i my is are this that""".split()
)


def tokenize(text: str) -> list[str]:
    return [tok for tok in TOKEN_RE.findall(text.lower()) if tok not in STOPWORDS and len(tok) > 1]


def key_terms(title: str) -> frozenset[str]:
    """Distinctive title terms: names (capitalised, not generic) and tokens mixing letters and digits."""
    terms = set()
    for raw in WORD_RE.findall(title):
        token = raw.strip(".-").lower()
        if len(token) < 2 or token in STOPWORDS:
            continue
        has_digit = any(ch.isdigit() for ch in token)
        has_alpha = any(ch.isalpha() for ch in token)
        if (has_digit and has_alpha) or VERSION_RE.match(token):
            terms.add(token)
        elif raw[0].isupper() and token not in GENERIC_CAPS and len(token) > 2:
            terms.add(token)
    return frozenset(terms)


def version_terms(terms: Iterable[str]) -> frozenset[str]:
    return frozenset(term.lstrip("v") for term in terms if VERSION_RE.match(term))


def versions_conflict(a: frozenset[str], b: frozenset[str]) -> bool:
    """Two release notes for different versions of the same tool are different stories."""
    va, vb = version_terms(a), version_terms(b)
    return bool(va and vb and not (va & vb))


class TfidfIndex:
    """IDF from a corpus of documents; vectors are L2-normalised sparse dicts."""

    def __init__(self, documents: Iterable[str]):
        doc_tokens = [set(tokenize(doc)) for doc in documents]
        self._n_docs = max(1, len(doc_tokens))
        self._df = Counter(token for tokens in doc_tokens for token in tokens)

    def document_frequency(self, token: str) -> int:
        return self._df.get(token, 0)

    def is_distinctive(self, term: str) -> bool:
        """A name with digits (gpt-5, cve-2026-1234) or one that few documents mention."""
        if any(ch.isdigit() for ch in term) and any(ch.isalpha() for ch in term):
            return True
        return self.document_frequency(term) <= max(3, int(self._n_docs * 0.01))

    def idf(self, token: str) -> float:
        return math.log((1 + self._n_docs) / (1 + self._df.get(token, 0))) + 1.0

    def vector(self, text: str) -> dict[str, float]:
        counts = Counter(tokenize(text))
        weights = {token: (1 + math.log(count)) * self.idf(token) for token, count in counts.items()}
        norm = math.sqrt(sum(w * w for w in weights.values())) or 1.0
        return {token: w / norm for token, w in weights.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(weight * b.get(token, 0.0) for token, weight in a.items())


def doc_text(title: str, text: str, lead_chars: int = 400) -> str:
    """Title counts twice: it carries most of the signal for short feed items."""
    return f"{title} {title} {text[:lead_chars]}"
