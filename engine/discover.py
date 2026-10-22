"""Find candidate new skills in the HN "Who is hiring?" posts. A human approves them.

The taxonomy has a fixed list of skills. A new tool can become popular and
Verity would not see it. This module reads the same raw posts as engine/demand.py
and lists terms that are not in the taxonomy but are used like tech names.
It never edits taxonomy.json. A human reads the evidence and decides.

How a term is found (simple rules, each one can be read and checked):
1. camel_case: mixed case inside the word (FastAPI, LangChain, ClickHouse).
2. tech_style: a tech-style dot or digit (Next.js, k8s, gpt-4o, llama3), or a "++" / "#" ending.
3. all_caps: 2 to 6 capital letters (not in data/discover_stoplist.txt).
4. list: a single word inside a comma/slash-separated list that already holds at
   least 2 different taxonomy skills ("Python, FastAPI, Postgres" -> FastAPI).
   This is the strongest signal, so it has the largest weight in the rank.
Rules 1 to 3 ignore the header cell of a post (the text before the first "|"),
because that cell is the company name.

A term counts in a post when the post contains it as a word (case does not matter,
"nextjs" and "next.js" are one term). A post counts at most once per term.
A term is kept when it has >= 30 posts in the last 12 months and most of those
posts (>= 50%) show it in rule 1 to 4 style. That filter removes ordinary words.

The output holds terms, counts, month names and thread URLs. It never holds
post text, author names or per-post links.

Run: python -m engine.discover --raw-dir <folder with the raw thread JSON files>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from array import array
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.forecast import logit, smoothed_share, trend_label  # noqa: E402
from engine.tagging import clean_text, load_taxonomy  # noqa: E402

THREADS_CSV = ROOT / "data" / "hn_threads.csv"
RAW_DIR = ROOT / "data" / "raw" / "hn"
STOPLIST_PATH = ROOT / "data" / "discover_stoplist.txt"
OUT_JSON = ROOT / "data" / "skill_candidates.json"

WINDOW = 12
MIN_MENTIONS = 30  # posts in the last window
MIN_SIGNAL_RATIO = 0.5  # share of those posts that show the term in rule 1 to 4 style
MIN_LIST_SKILLS = 2  # known skills a list needs before its other words count
MAX_SEGMENT_WORDS = 3  # a list item longer than this is prose, not a tool name
MIN_CO_POSTS = 5  # fewest shared posts before a skill can be called co-occurring
TOP_COOCCUR = 3
KEEP_TOP = 100  # candidates written to the JSON file
BACKTEST_AS_OF = "2023-06"
BACKTEST_TOP = 15
OTHER_ORIGINS = ("2021-06", "2022-06", "2024-06", "2025-06")  # robustness check, same rules
DRAFT_STATUS = "draft, needs review and tests"

RULE_NAMES = ("list", "camel_case", "tech_style", "all_caps")
TECH_DOT_SUFFIX = frozenset({"js", "net"})

RULE_TEXT = [
    "camel_case: mixed case inside the word, e.g. FastAPI, LangChain.",
    "tech_style: dot or digits in tech style (Next.js, k8s, gpt-4o), or ends with ++ or #.",
    "all_caps: 2 to 6 capital letters, unless in data/discover_stoplist.txt.",
    "list: a single word in a comma/slash list with >= 2 different taxonomy skills (strongest signal).",
    "Rules camel_case, tech_style and all_caps ignore the header cell (text before the first '|').",
    "Terms in the taxonomy (pattern, name or synonym) and in the stoplist are dropped.",
    f"A term needs >= {MIN_MENTIONS} posts in the last {WINDOW} months, and >= {int(MIN_SIGNAL_RATIO * 100)}% "
    "of them must show it in rule style.",
    "growth = share_last / max(share_prior, 1 / n_prior_posts). share = posts with the term / all posts "
    "in the 12 months.",
    "score = growth x (0.5 + 0.5 x list_fraction). list_fraction = posts where the term is in a skill list "
    "/ posts with the term. Terms with no posts in the prior 12 months are 'new'.",
    "label = existing Welch test (engine.forecast.trend_label): last 12 months vs the 12 before.",
    "co-occurring skills = top 3 taxonomy skills by lift in the last 12 months (>= "
    f"{MIN_CO_POSTS} shared posts).",
]

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# --------------------------------------------------------------------------------------
# Text rules
# --------------------------------------------------------------------------------------

# A token is a word. ".NET" is a special case. Dotted words stay whole only with a tech suffix.
_TOKEN = re.compile(
    r"(?<![\w@])\.NET(?!\w)"
    r"|(?<![\w@])[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*(?:\+\+|#)?(?:-\d[A-Za-z0-9]*)?"
)
_SINGLE_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)*(?:\+\+|#)?(?:-\d[A-Za-z0-9]*)?")
_LETTER_DIGITS = re.compile(r"[A-Za-z]\d+")  # v2, q3, s3: too short to be a tool name
# Hard separators end a list. Soft separators stay inside it.
_SEP = re.compile(
    r"(?P<hard>\n|:|[!?|•*–—]|\.(?=\s|$)|\s-+\s)"
    r"|(?P<soft>[,;/()\[\]{}\"·]|\s[+&]\s|\s(?:and|or)\s)",
    re.IGNORECASE,
)
_HEADER_LIMIT = 80  # the header cell is the text before a "|" in the first 80 characters


class Hit(NamedTuple):
    """A candidate term in one post: how it was written and which rules found it."""

    surface: str
    rules: frozenset


def normalise(token: str) -> str:
    """One key for simple variants: nextjs, Next.js -> next.js; GPT-4o, gpt4o -> gpt4o."""
    key = token.strip().lower()
    key = re.sub(r"(?<=[a-z0-9])-(?=\d)", "", key)
    if key.endswith("js") and "." not in key and len(key) > 4:
        key = key[:-2] + ".js"
    return key


def _tech_dot(token: str) -> bool:
    return "." in token and token.rsplit(".", 1)[1].lower() in TECH_DOT_SUFFIX


def _split_token(token: str) -> list[str]:
    """Keep ".NET", "Next.js" and "ASP.NET" whole. Split other dotted words at the dots."""
    if "." not in token or token == ".NET" or _tech_dot(token):
        return [token]
    return [p for p in token.split(".") if p and p[0].isalpha()]


def _rules_for(token: str) -> set[str]:
    """Form rules (1 to 3) for one token."""
    rules = set()
    if re.fullmatch(r"[A-Z]{2,6}", token):
        rules.add("all_caps")
    if re.search(r"[a-z][A-Z]", token):
        rules.add("camel_case")
    has_digit = re.search(r"\d", token) is not None
    if (_tech_dot(token) or token == ".NET" or token.endswith(("++", "#"))
            or (has_digit and not _LETTER_DIGITS.fullmatch(token))):
        rules.add("tech_style")
    return rules


@lru_cache(maxsize=500_000)
def _token_parts(token: str) -> tuple[tuple[str, str, frozenset], ...]:
    """(part, key, form rules) for each word inside one token. Cached: words repeat a lot."""
    return tuple((p, normalise(p), frozenset(_rules_for(p))) for p in _split_token(token))


def load_stoplist(path: str | Path | None = None) -> frozenset[str]:
    """Read the stoplist: one term per line, '#' starts a comment. Terms are normalised."""
    file_path = Path(path) if path is not None else STOPLIST_PATH
    if not file_path.exists():
        return frozenset()
    words = set()
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            words.add(normalise(line))
    return frozenset(words)


@lru_cache(maxsize=None)
def _compile(pattern: str, case_sensitive: bool) -> re.Pattern[str]:
    return re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


@dataclass
class _Known:
    """The taxonomy and stoplist, prepared once."""

    taxonomy: list[dict[str, Any]]
    stoplist: frozenset[str]
    names: frozenset[str] = frozenset()
    skills: list[str] = field(default_factory=list)
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    _cache: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.skills = [e["skill"] for e in self.taxonomy]
        self.patterns = [_compile(e["pattern"], bool(e["case_sensitive"])) for e in self.taxonomy]
        names = set()
        for e in self.taxonomy:
            names.add(normalise(e["skill"]))
            names.update(normalise(s) for s in e.get("synonyms") or [])
        self.names = frozenset(names)

    def skills_in(self, text: str) -> set[int]:
        return {i for i, p in enumerate(self.patterns) if p.search(text)}

    def is_known(self, surface: str) -> bool:
        """True when the taxonomy already covers this word, or the stoplist drops it."""
        key = normalise(surface)
        got = self._cache.get(surface)
        if got is None:
            got = (len(key) < 2 or key in self.names or key in self.stoplist
                   or any(p.search(surface) for p in self.patterns))
            self._cache[surface] = got
        return got


def _known_spans(text: str, known: _Known, present: set[int]) -> list[tuple[int, int, int]]:
    """(start, end, skill index) of every taxonomy match in the text."""
    return [(m.start(), m.end(), i) for i in present for m in known.patterns[i].finditer(text)]


def _list_words(text: str, spans: list[tuple[int, int, int]]) -> dict[str, str]:
    """Single words that sit in a list with >= MIN_LIST_SKILLS known skills. Return {key: surface}."""
    found: dict[str, str] = {}
    run: list[tuple[int, int, str]] = []

    def flush() -> None:
        skills = {i for s, e, _ in run for a, b, i in spans if a < e and b > s}
        if len(skills) >= MIN_LIST_SKILLS:
            for s, e, seg in run:
                if len(seg.split()) == 1 and not any(a < e and b > s for a, b, _ in spans):
                    word = seg.strip("'*_`-")
                    if _SINGLE_WORD.fullmatch(word) and ("." not in word or _tech_dot(word)):
                        found.setdefault(normalise(word), word)
        run.clear()

    pos = 0
    for m in list(_SEP.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        raw = text[pos:end]
        seg = raw.strip()
        if seg:
            start = pos + (len(raw) - len(raw.lstrip()))
            if len(seg.split()) > MAX_SEGMENT_WORDS:
                flush()
            else:
                run.append((start, start + len(seg), seg))
        if m is not None:
            if m.group("hard"):
                flush()
            pos = m.end()
    flush()
    return found


def _header_end(text: str) -> int:
    """Index where the header cell ends (first '|' within the first line), else 0."""
    bar = text.find("|")
    newline = text.find("\n")
    if 0 <= bar <= _HEADER_LIMIT and (newline < 0 or bar < newline):
        return bar
    return 0


def _analyse(text: str, known: _Known) -> tuple[set[int], dict[str, tuple[str, set[str]]], set[str]]:
    """Return (skill indexes in the post, {key: (surface, rules)}, every word key in the post).

    Nothing is dropped here: the caller removes known and stoplisted terms.
    """
    present = known.skills_in(text)
    hits: dict[str, tuple[str, set[str]]] = {}
    words: set[str] = set()
    header = _header_end(text)
    for m in _TOKEN.finditer(text):
        for part, key, rules in _token_parts(m.group(0)):
            words.add(key)
            if rules and m.start() >= header:
                surface, old = hits.get(key, (part, set()))
                old |= rules
                hits[key] = (surface, old)
    if len(present) >= MIN_LIST_SKILLS:
        for key, surface in _list_words(text, _known_spans(text, known, present)).items():
            words.add(key)
            old_surface, old = hits.get(key, (surface, set()))
            old.add("list")
            hits[key] = (old_surface, old)
    return present, hits, words


def extract_terms(text: str, taxonomy: list[dict[str, Any]] | None = None,
                  stoplist: frozenset[str] | None = None) -> dict[str, Hit]:
    """Candidate tech terms in one cleaned post. Return {key: Hit(surface, rules)}.

    Terms already covered by the taxonomy (pattern, name or synonym) and terms in
    the stoplist are left out.
    """
    known = _Known(taxonomy if taxonomy is not None else load_taxonomy(),
                   stoplist if stoplist is not None else load_stoplist())
    _, hits, _ = _analyse(text, known)
    return {k: Hit(s, frozenset(r)) for k, (s, r) in hits.items() if not known.is_known(s)}


# --------------------------------------------------------------------------------------
# Draft pattern and history
# --------------------------------------------------------------------------------------

def _flex(key: str) -> str:
    """Escape a key. Allow an optional hyphen where letters meet digits (gpt4o -> gpt-?4o)."""
    out = []
    for i, ch in enumerate(key):
        if i and (ch.isdigit() != key[i - 1].isdigit()) and ch.isalnum() and key[i - 1].isalnum():
            out.append("-?")
        out.append(re.escape(ch))
    return "".join(out)


def draft_pattern(term: str) -> dict[str, Any]:
    """A proposed taxonomy pattern for one term. It is a draft: a human must check it.

    Word boundaries on both sides. A term written in capitals only (RAG, SRE) is
    case sensitive. Every other term ignores case. Variants nextjs / next.js /
    next js and gpt4o / gpt-4o match the same pattern.
    """
    clean = term.strip()
    if not clean:
        raise ValueError("term is empty")
    key = normalise(clean)
    case_sensitive = bool(re.fullmatch(r"[A-Z]{2,6}", clean))
    if case_sensitive:
        body = re.escape(clean)
    elif key == ".net":
        body = r"\.net"
    elif key.endswith(".js"):
        body = _flex(key[:-3]) + r"[ .]?js"
    else:
        body = _flex(key)
    lead = r"(?<![\w@])" if key.startswith(".") else r"(?<![\w.@-])"
    return {
        "term": clean,
        "pattern": f"{lead}{body}(?!\\w)",
        "case_sensitive": case_sensitive,
        "status": DRAFT_STATUS,
    }


def _read_threads(threads_csv: str | Path) -> list[dict]:
    with Path(threads_csv).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: r["month"])
    if len({r["month"] for r in rows}) != len(rows):
        raise ValueError("hn_threads.csv has two threads for one month")
    return rows


def _live_posts(item: dict):
    """Text of each top-level post that is not deleted and not empty (same rule as engine/demand.py)."""
    for child in item.get("children") or []:
        if child.get("deleted"):
            continue
        text = child.get("text") or ""
        if text.strip():
            yield text


def history(term: str, raw_dir: str | Path = RAW_DIR, threads_csv: str | Path = THREADS_CSV,
            pattern: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Monthly share of posts that match the term's pattern, for every month from the first thread.

    This is the count engine/demand.py would write once a human adds the skill, so an
    approved skill gets its whole history at once from the raw posts. The pattern
    is draft_pattern(term) unless a reviewed one is given.
    """
    spec = pattern or draft_pattern(term)
    regex = _compile(spec["pattern"], bool(spec["case_sensitive"]))
    rows = []
    for thread in _read_threads(threads_csv):
        item = json.loads((Path(raw_dir) / f"{thread['thread_id']}.json").read_text(encoding="utf-8"))
        n_posts = mentions = 0
        for text in _live_posts(item):
            n_posts += 1
            if regex.search(clean_text(text)):
                mentions += 1
        rows.append({"month": thread["month"], "mentions": mentions, "n_posts": n_posts,
                     "share": mentions / n_posts if n_posts else 0.0})
    return rows


# --------------------------------------------------------------------------------------
# Scan: read every post once and keep counts, not text
# --------------------------------------------------------------------------------------

@dataclass
class Scan:
    """What one pass over the raw posts leaves behind. It holds no post text."""

    months: list[str]
    thread_urls: list[str]
    n_posts: np.ndarray  # per month
    skills: list[str]
    categories: list[str]
    signal: list[dict[str, Counter]]  # per month: rule -> Counter(key); rule "any" = any rule
    surfaces: dict[str, Counter]
    post_month: np.ndarray  # month index of every post
    post_skills: np.ndarray  # bit i set when taxonomy skill i is in the post
    flat_post: np.ndarray  # post index of every entry of flat_ids
    flat_ids: np.ndarray
    key_ids: dict[str, int]
    id_keys: list[str]
    known: _Known


@dataclass
class _ThreadScan:
    """Counts from one thread. Keys are local to the thread; scan_posts maps them to global ids."""

    n_posts: int
    signal: dict[str, Counter]
    surfaces: dict[str, Counter]
    post_skills: list[int]
    offsets: list[int]  # post p owns flat[offsets[p]:offsets[p + 1]]
    flat: array
    local_keys: list[str]


def _scan_thread(path: Path, known: _Known) -> _ThreadScan:
    """Read one raw thread. A post counts at most once per term (sets), as in engine/demand.py."""
    item = json.loads(path.read_text(encoding="utf-8"))
    signal = {r: Counter() for r in ("any",) + RULE_NAMES}
    surfaces: dict[str, Counter] = {}
    local: dict[str, int] = {}
    post_skills: list[int] = []
    offsets = [0]
    flat = array("I")
    for text in _live_posts(item):
        present, hits, words = _analyse(clean_text(text), known)
        post_skills.append(sum(1 << i for i in present))
        for key in words:
            flat.append(local.setdefault(key, len(local)))
        offsets.append(len(flat))
        for key, (surface, rules) in hits.items():
            signal["any"][key] += 1
            for r in rules:
                signal[r][key] += 1
            surfaces.setdefault(key, Counter())[surface] += 1
    return _ThreadScan(len(post_skills), signal, surfaces, post_skills, offsets, flat, list(local))


_WORKER_KNOWN: _Known | None = None


def _init_worker(taxonomy: list[dict[str, Any]], stoplist: frozenset[str]) -> None:
    global _WORKER_KNOWN
    _WORKER_KNOWN = _Known(taxonomy, stoplist)


def _scan_job(path: str) -> _ThreadScan:
    return _scan_thread(Path(path), _WORKER_KNOWN)


def scan_posts(raw_dir: str | Path = RAW_DIR, threads_csv: str | Path = THREADS_CSV,
               taxonomy: list[dict[str, Any]] | None = None,
               stoplist: frozenset[str] | None = None, workers: int = 1) -> Scan:
    """Read all threads and count terms per month. Threads are read in `workers` processes."""
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    stop = stoplist if stoplist is not None else load_stoplist()
    known = _Known(tax, stop)
    threads = _read_threads(threads_csv)
    paths = [str(Path(raw_dir) / f"{t['thread_id']}.json") for t in threads]
    if workers > 1 and len(paths) > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(min(workers, len(paths)), initializer=_init_worker,
                                 initargs=(tax, stop)) as pool:
            parts = list(pool.map(_scan_job, paths))  # map keeps the month order
    else:
        parts = [_scan_thread(Path(p), known) for p in paths]

    key_ids: dict[str, int] = {}
    id_keys: list[str] = []
    surfaces: dict[str, Counter] = {}
    post_month, post_skills, flats, sizes = [], [], [], []
    for mi, part in enumerate(parts):
        remap = np.empty(len(part.local_keys), dtype=np.uint32)
        for local_id, key in enumerate(part.local_keys):
            if key not in key_ids:
                key_ids[key] = len(id_keys)
                id_keys.append(key)
            remap[local_id] = key_ids[key]
        flats.append(remap[np.frombuffer(part.flat, dtype=np.uint32)] if len(part.flat) else remap[:0])
        sizes.append(np.diff(np.array(part.offsets, dtype=np.int64)))
        post_month += [mi] * part.n_posts
        post_skills += part.post_skills
        for key, counter in part.surfaces.items():
            surfaces.setdefault(key, Counter()).update(counter)
    all_sizes = np.concatenate(sizes) if sizes else np.zeros(0, dtype=np.int64)
    return Scan(
        months=[t["month"] for t in threads],
        thread_urls=[t["url"] for t in threads],
        n_posts=np.array([p.n_posts for p in parts]),
        skills=known.skills,
        categories=[e.get("category") or "" for e in tax],
        signal=[p.signal for p in parts],
        surfaces=surfaces,
        post_month=np.array(post_month, dtype=np.int32),
        post_skills=np.array(post_skills, dtype=np.int64),
        flat_post=np.repeat(np.arange(len(post_month), dtype=np.int32), all_sizes),
        flat_ids=np.concatenate(flats) if flats else np.zeros(0, dtype=np.uint32),
        key_ids=key_ids,
        id_keys=id_keys,
        known=known,
    )


def _term_matrix(scan: Scan, keys: list[str]) -> np.ndarray:
    """Posts per month that contain each key as a word. Shape (len(keys), n_months)."""
    out = np.zeros((len(keys), len(scan.months)), dtype=np.int64)
    if not keys:
        return out
    row_of = np.full(len(scan.id_keys), -1, dtype=np.int64)
    for r, key in enumerate(keys):
        row_of[scan.key_ids[key]] = r
    rows = row_of[scan.flat_ids]
    sel = rows >= 0
    n_months = len(scan.months)
    cell = rows[sel] * n_months + scan.post_month[scan.flat_post[sel]]
    out[:] = np.bincount(cell, minlength=len(keys) * n_months).reshape(len(keys), n_months)
    return out


# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------

def _check_month(name: str, value: str) -> None:
    if not isinstance(value, str) or not _MONTH_RE.match(value):
        raise ValueError(f"{name} must look like 'YYYY-MM', got {value!r}")


def _as_of_index(scan: Scan, as_of: str | None) -> int:
    if as_of is None:
        return len(scan.months) - 1
    _check_month("as_of", as_of)
    idx = [i for i, m in enumerate(scan.months) if m <= as_of]
    if not idx:
        raise ValueError(f"no data on or before {as_of}")
    return idx[-1]


def _co_occurring(scan: Scan, key: str, lo: int, hi: int) -> tuple[list[dict], str | None]:
    """Top taxonomy skills by lift in months lo..hi (inclusive), and a suggested category."""
    kid = scan.key_ids[key]
    in_window = (scan.post_month >= lo) & (scan.post_month <= hi)
    with_term = np.zeros(len(scan.post_month), dtype=bool)
    with_term[scan.flat_post[scan.flat_ids == kid]] = True
    with_term &= in_window
    n_term, n_all = int(with_term.sum()), int(in_window.sum())
    if not n_term or not n_all:
        return [], None
    rows = []
    for i, skill in enumerate(scan.skills):
        has = (scan.post_skills >> i) & 1 == 1
        co, n_skill = int((has & with_term).sum()), int((has & in_window).sum())
        if co >= MIN_CO_POSTS and n_skill:
            rows.append({"skill": skill, "lift": round((co / n_term) / (n_skill / n_all), 2), "posts": co})
    rows.sort(key=lambda r: (-r["lift"], -r["posts"], r["skill"]))
    top = rows[:TOP_COOCCUR]
    category = None
    if top:
        by_cat = Counter()
        for r in top:
            by_cat[scan.categories[scan.skills.index(r["skill"])]] += r["lift"]
        category = by_cat.most_common(1)[0][0] or None
    return top, category


def _examples(scan: Scan, counts: np.ndarray, lo: int, hi: int) -> list[dict[str, str]]:
    """Two thread URLs: the month with the most posts in the window, then the latest other month with the term."""
    seen = [m for m in range(lo, hi + 1) if counts[m] > 0]
    if not seen:
        return []
    best = max(seen, key=lambda m: (counts[m], m))
    picks = [best] + [m for m in sorted(seen, reverse=True) if m != best][:1]
    return [{"month": scan.months[m], "thread_url": scan.thread_urls[m]} for m in picks]


def _best_surface(scan: Scan, key: str) -> str:
    surfaces = scan.surfaces.get(key)
    return surfaces.most_common(1)[0][0] if surfaces else key


def discover(raw_dir: str | Path = RAW_DIR, threads_csv: str | Path = THREADS_CSV,
             taxonomy: list[dict[str, Any]] | None = None, as_of: str | None = None,
             window: int = WINDOW, scan: Scan | None = None,
             min_mentions: int = MIN_MENTIONS) -> dict[str, Any]:
    """List candidate new skills using only months <= as_of. Return a dict with a ranked `candidates` list.

    Pass `scan` to reuse one read of the raw posts (for the backtest).
    """
    if window != WINDOW:
        raise ValueError(f"window must be {WINDOW}: trend_label compares 12 months with the 12 before")
    if scan is None:
        scan = scan_posts(raw_dir, threads_csv, taxonomy)
    end = _as_of_index(scan, as_of)
    if end + 1 < 2 * window:
        raise ValueError(f"need {2 * window} months up to as_of, have {end + 1}")
    last_lo, prior_lo = end - window + 1, end - 2 * window + 1
    n_last = int(scan.n_posts[last_lo:end + 1].sum())
    n_prior = int(scan.n_posts[prior_lo:last_lo].sum())

    def total(rule: str, key: str) -> int:
        return sum(scan.signal[m][rule][key] for m in range(last_lo, end + 1))

    signal_last: Counter = Counter()
    for m in range(last_lo, end + 1):
        signal_last.update(scan.signal[m]["any"])
    pool = [k for k, v in signal_last.items()
            if v >= min_mentions * MIN_SIGNAL_RATIO and k in scan.key_ids
            and not scan.known.is_known(_best_surface(scan, k))]
    matrix = _term_matrix(scan, pool)

    candidates = []
    for row, key in enumerate(pool):
        counts = matrix[row]
        m_last, m_prior = int(counts[last_lo:end + 1].sum()), int(counts[prior_lo:last_lo].sum())
        n_signal = signal_last[key]
        if m_last < min_mentions or n_signal / m_last < MIN_SIGNAL_RATIO:
            continue
        share_last, share_prior = m_last / n_last, m_prior / n_prior
        growth = share_last / max(share_prior, 1.0 / n_prior)
        list_fraction = min(1.0, total("list", key) / m_last)
        series = counts[end - 23:end + 1]
        y = logit(smoothed_share(series, scan.n_posts[end - 23:end + 1]))
        label, p_value = trend_label(y, series)
        first = int(np.argmax(counts[:end + 1] > 0))
        new_since = None
        if m_prior == 0:
            new_since = scan.months[last_lo + int(np.argmax(counts[last_lo:end + 1] > 0))]
        co_skills, category = _co_occurring(scan, key, last_lo, end)
        candidates.append({
            "term": _best_surface(scan, key),
            "key": key,
            "mentions_last": m_last,
            "mentions_prior": m_prior,
            "share_last": round(share_last, 6),
            "share_prior": round(share_prior, 6),
            "growth": round(growth, 2),
            "kind": "new" if new_since else "growth",
            "new_since": new_since,
            "score": round(growth * (0.5 + 0.5 * list_fraction), 2),
            "label": label,
            "p_value": None if p_value is None else round(p_value, 4),
            "first_seen": scan.months[first],
            "evidence": {
                "list_fraction": round(list_fraction, 2),
                "rule_posts_last": {r: total(r, key) for r in RULE_NAMES},
                "signal_ratio": round(n_signal / m_last, 2),
            },
            "co_occurring_skills": co_skills,
            "suggested_category": category,
            "examples": _examples(scan, counts, last_lo, end),
            "draft_pattern": draft_pattern(_best_surface(scan, key)),
        })
    candidates.sort(key=lambda c: (-c["score"], -c["mentions_last"], c["key"]))
    for rank, c in enumerate(candidates, 1):
        c["rank"] = rank
    return {
        "as_of": scan.months[end],
        "window": window,
        "window_months": {"last": [scan.months[last_lo], scan.months[end]],
                          "prior": [scan.months[prior_lo], scan.months[last_lo - 1]]},
        "n_posts": {"last": n_last, "prior": n_prior},
        "n_candidates_total": len(candidates),
        "candidates": candidates,
    }


# --------------------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------------------

def _wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if not n:
        return [0.0, 0.0]
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 2), round(min(1.0, centre + half), 2)]


def backtest_origin(scan: Scan, as_of: str, top_n: int = BACKTEST_TOP) -> dict[str, Any]:
    """Pick the top candidates with data up to as_of only. Then check the next 12 months.

    A candidate is a hit when its share in the 12 months after as_of is above its
    share in the 12 months up to as_of. The future months are read only here.
    """
    found = discover(as_of=as_of, scan=scan)
    end = _as_of_index(scan, as_of)
    if end + WINDOW >= len(scan.months):
        raise ValueError(f"fewer than {WINDOW} months after {as_of}")
    before = slice(end - WINDOW + 1, end + 1)
    after = slice(end + 1, end + WINDOW + 1)
    n_before, n_after = int(scan.n_posts[before].sum()), int(scan.n_posts[after].sum())
    keys = [c["key"] for c in found["candidates"]]
    matrix = _term_matrix(scan, keys)
    rows = []
    for c, counts in zip(found["candidates"], matrix):
        s_before, s_after = counts[before].sum() / n_before, counts[after].sum() / n_after
        rows.append({"term": c["term"], "rank": c["rank"], "label": c["label"], "growth": c["growth"],
                     "share_before": round(float(s_before), 6), "share_after": round(float(s_after), 6),
                     "rose": bool(s_after > s_before)})
    top = rows[:top_n]
    hits = sum(r["rose"] for r in top)
    rising = [r for r in rows if r["label"] == "Rising"]
    return {
        "as_of": scan.months[end],
        "after_months": [scan.months[end + 1], scan.months[end + WINDOW]],
        "top_n": len(top),
        "hits": hits,
        "precision_top": round(hits / len(top), 2) if top else None,
        "precision_ci95_wilson": _wilson(hits, len(top)),
        "n_all_candidates": len(rows),
        "base_rate_all_candidates": round(sum(r["rose"] for r in rows) / len(rows), 2) if rows else None,
        "n_labelled_rising": len(rising),
        "precision_labelled_rising": (round(sum(r["rose"] for r in rising) / len(rising), 2) if rising else None),
        "top": top,
    }


def backtest(scan: Scan, as_of: str = BACKTEST_AS_OF, top_n: int = BACKTEST_TOP,
             other_origins: tuple[str, ...] = OTHER_ORIGINS) -> dict[str, Any]:
    """Main backtest at `as_of`, plus the same test at other origins as a robustness check."""
    main = backtest_origin(scan, as_of, top_n)
    others = []
    for origin in other_origins:
        try:
            r = backtest_origin(scan, origin, top_n)
        except ValueError:
            continue
        others.append({k: r[k] for k in ("as_of", "top_n", "hits", "precision_top", "n_all_candidates",
                                           "base_rate_all_candidates")})
    p = main["precision_top"]
    verdict = ("Weak: at most half of the top candidates grew." if p is not None and p <= 0.5 else
               "Moderate: more than half of the top candidates grew.")
    return {
        "definition": (f"Run discover with data up to {as_of}. Take the top {top_n}. A hit is a term whose share "
                       f"of posts in the next 12 months is above its share in the 12 months up to {as_of}. "
                       "No month after as_of is used to choose the terms. The taxonomy and stoplist are today's files."),
        "main": main,
        "other_origins": others,
        "verdict": verdict,
        "caveats": [
            "Small sample: 15 terms. The interval is wide.",
            "Compare with base_rate_all_candidates: a high precision is only informative if it beats the base rate.",
            "The stoplist was written by reading today's candidates, not the 2023 ones, but it is human judgement.",
        ],
    }


# --------------------------------------------------------------------------------------
# Report and command line
# --------------------------------------------------------------------------------------

def build_report(raw_dir: str | Path = RAW_DIR, threads_csv: str | Path = THREADS_CSV,
                 taxonomy: list[dict[str, Any]] | None = None, as_of: str | None = None,
                 keep: int = KEEP_TOP, with_backtest: bool = True, workers: int = 1) -> dict[str, Any]:
    """The full JSON document for data/skill_candidates.json."""
    scan = scan_posts(raw_dir, threads_csv, taxonomy, workers=workers)
    found = discover(as_of=as_of, scan=scan)
    candidates = found["candidates"][:keep]
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "Candidates for human review. Nothing here is in data/taxonomy.json.",
        "as_of": found["as_of"],
        "window": found["window"],
        "window_months": found["window_months"],
        "n_posts": found["n_posts"],
        "rules": RULE_TEXT,
        "n_candidates_total": found["n_candidates_total"],
        "candidates": candidates,
    }
    if candidates:
        top = candidates[0]
        rows = history(top["term"], raw_dir, threads_csv, top["draft_pattern"])
        report["backfill_demo"] = {
            "term": top["term"],
            "pattern": top["draft_pattern"]["pattern"],
            "note": "Monthly share from the raw posts with the draft pattern: the history an approved skill gets at once.",
            "months": [r["month"] for r in rows],
            "share": [round(r["share"], 6) for r in rows],
        }
    if with_backtest:
        report["backtest"] = backtest(scan)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find candidate new skills in the HN hiring posts.")
    parser.add_argument("--raw-dir", default=str(RAW_DIR), help="folder with <thread_id>.json files")
    parser.add_argument("--threads-csv", default=str(THREADS_CSV))
    parser.add_argument("--out", default=str(OUT_JSON))
    parser.add_argument("--as-of", default=None, help="YYYY-MM; default is the latest month")
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1),
                        help="processes that read the threads (1 = no extra processes)")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    report = build_report(args.raw_dir, args.threads_csv, as_of=args.as_of, workers=args.workers)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elapsed = time.perf_counter() - started

    print(f"as_of {report['as_of']}: {report['n_candidates_total']} candidates, {len(report['candidates'])} written to {out}")
    print(f"{'rank':<5}{'term':<18}{'last %':>8}{'prior %':>9}{'growth':>8}  {'label':<16}{'first':<9}co-occurring")
    for c in report["candidates"][:15]:
        label = c["label"] or "-"
        growth = f"new {c['new_since']}" if c["kind"] == "new" else f"x{c['growth']}"
        co = ", ".join(r["skill"] for r in c["co_occurring_skills"])
        print(f"{c['rank']:<5}{c['term']:<18}{c['share_last'] * 100:>8.2f}{c['share_prior'] * 100:>9.2f}"
              f"{growth:>8}  {label:<16}{c['first_seen']:<9}{co}")
    bt = report.get("backtest")
    if bt:
        m = bt["main"]
        print(f"\nBacktest {m['as_of']}: precision {m['hits']}/{m['top_n']} = {m['precision_top']} "
              f"(95% CI {m['precision_ci95_wilson']}), base rate {m['base_rate_all_candidates']} "
              f"over {m['n_all_candidates']} candidates. {bt['verdict']}")
        print("  top: " + ", ".join(f"{r['term']}({'+' if r['rose'] else '-'})" for r in m["top"]))
        for o in bt["other_origins"]:
            print(f"  origin {o['as_of']}: {o['hits']}/{o['top_n']} = {o['precision_top']} "
                  f"(base rate {o['base_rate_all_candidates']}, n={o['n_all_candidates']})")
    print(f"\nRuntime: {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
