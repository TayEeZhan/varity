"""Malaysian job-demand snapshots from public job-board result pages.

Why this file exists
- Verity's demand series is Hacker News "Who is hiring?", which is US-heavy.
  This module adds a small Malaysian cross-check: how often each skill shows up
  in the result pages of Malaysian job boards, on one day.

What it is not
- It is NOT a time series. Each run is one dated snapshot. There is no history.
- It is query-dependent: we run 8 fixed tech queries, up to 3 pages each, and
  count what the result pages show (title + short teaser). Not the full ad.

Rules this module enforces in code (see docs/malaysia-data.md for the reasons)
- robots.txt is checked for every URL before it is fetched (RFC 9309 matcher,
  because urllib.robotparser ignores the "*" and "$" wildcards that job sites
  use; tests cross-check the two on plain rules).
- At most 1 request per 3 seconds per host. Timeout 30 s. Retries with backoff.
- One honest User-Agent. No login, no cookies kept across sites, no proxies, no
  headless browser. A challenge page (403, Cloudflare "Just a moment...",
  CAPTCHA) stops that site for the whole run. We never try to pass it.
- No personal data is kept. Emails, phone numbers and "contact ..." lines are
  stripped. We never read recruiter or company-contact fields.
- Raw responses go under data/raw/my_jobs/<site>/<date>/ (gitignored).
  Only aggregates are committed.

Run: python -m engine.my_jobs --sites hiredly,jobstore --permission-confirmed
     python -m engine.my_jobs --compare        (print Malaysia vs HN shares)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.tagging import clean_text, load_taxonomy, tag_text  # noqa: E402

log = logging.getLogger("verity.my_jobs")

USER_AGENT = "Verity hackathon project (XMUM SDC 2026)"
ROBOTS_TOKEN = "verity"  # product token that robots.txt groups may name
MIN_INTERVAL_S = 3.0
TIMEOUT_S = 30
MAX_RETRIES = 3
BACKOFF_BASE_S = 5.0

QUERIES = (
    "software engineer",
    "developer",
    "data engineer",
    "data scientist",
    "devops",
    "machine learning",
    "AI engineer",
    "mobile developer",
)
MAX_PAGES = 3
TEASER_CHARS = 400

RAW_DIR = ROOT / "data" / "raw" / "my_jobs"
SKILLS_CSV = ROOT / "data" / "my_jobs_snapshots.csv"
ROLES_CSV = ROOT / "data" / "my_roles_snapshots.csv"
ROLES_JSON = ROOT / "data" / "roles.json"
HN_DEMAND_CSV = ROOT / "data" / "demand_monthly.csv"
SKILLS_COLUMNS = ["snapshot_date", "site", "skill", "mentions", "n_listings", "share"]
ROLES_COLUMNS = ["snapshot_date", "site", "role_id", "n", "share"]


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class ScrapeStop(Exception):
    """Base class: stop collecting from this site."""


class RobotsDisallowed(ScrapeStop):
    """robots.txt does not allow this URL for us."""


class ChallengeDetected(ScrapeStop):
    """The site answered with a bot challenge or block. We stop. We do not retry."""


class FetchFailed(ScrapeStop):
    """Network error or bad status after all retries."""


# --------------------------------------------------------------------------
# robots.txt (RFC 9309)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """RFC 9309: '*' matches any run of characters, a trailing '$' anchors the end."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(rx + ("$" if anchored else ""))


class RobotsRules:
    """The rules of the one group that applies to us.

    Group choice (RFC 9309): a group that names our product token wins. Otherwise
    the "*" group. Groups with the same name are merged. No matching group means
    everything is allowed. Among matching rules the longest pattern wins; on a
    tie, Allow wins.
    """

    def __init__(self, rules: list[_Rule], group: str | None):
        self.rules = rules
        self.group = group  # our token, "*", or None (no applicable group)

    @classmethod
    def parse(cls, text: str, token: str = ROBOTS_TOKEN) -> "RobotsRules":
        groups: dict[str, list[_Rule]] = {}
        agents: list[str] = []
        last_was_agent = False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field_name, _, value = line.partition(":")
            field_name = field_name.strip().lower()
            value = value.strip()
            if field_name == "user-agent":
                if not last_was_agent:
                    agents = []
                agents.append(value.lower())
                groups.setdefault(value.lower(), [])
                last_was_agent = True
                continue
            last_was_agent = False
            if field_name not in ("allow", "disallow") or not agents:
                continue
            if value == "":
                continue  # "Disallow:" with no value allows everything; no rule needed
            rule = _Rule(field_name == "allow", value, _pattern_to_regex(value))
            for agent in agents:
                groups[agent].append(rule)
        if token.lower() in groups:
            return cls(groups[token.lower()], token.lower())
        if "*" in groups:
            return cls(groups["*"], "*")
        return cls([], None)

    def _best(self, path_and_query_: str) -> _Rule | None:
        best: _Rule | None = None
        for rule in self.rules:
            if not rule.regex.match(path_and_query_):
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow and not best.allow)
            ):
                best = rule
        return best

    def allowed(self, path_and_query_: str) -> bool:
        best = self._best(path_and_query_)
        return True if best is None else best.allow

    def deciding_rule(self, path_and_query_: str) -> str | None:
        """For the docs and the logs: which rule decided. None if no rule matched."""
        best = self._best(path_and_query_)
        return None if best is None else f"{'Allow' if best.allow else 'Disallow'}: {best.pattern}"


def path_and_query(url: str) -> str:
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


# --------------------------------------------------------------------------
# Challenge detection
# --------------------------------------------------------------------------
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "captcha",
    "verify you are human",
    "are you a robot",
    "security check",
)
_BODY_MARKERS = ("_cf_chl_opt", "captcha-delivery.com", "px-captcha")


def is_challenge(status: int, headers: dict[str, str], body: str) -> bool:
    """True if the response is a bot challenge or a block, not a real page.

    Any 401, 403, 429 or 451 on a page we were allowed to fetch counts as a
    block. We stop instead of retrying, so we never hammer a site that said no.
    Cloudflare's passive script (/cdn-cgi/challenge-platform/) also appears on
    normal pages, so it is NOT a marker.
    """
    low = {k.lower(): v for k, v in headers.items()}
    if "cf-mitigated" in low:
        return True
    if status in (401, 403, 429, 451):
        return True
    text = body or ""
    match = _TITLE.search(text[:20000])
    if match and any(marker in match.group(1).lower() for marker in _TITLE_MARKERS):
        return True
    head = text[:30000]
    return any(marker in head for marker in _BODY_MARKERS)


# --------------------------------------------------------------------------
# Polite fetcher
# --------------------------------------------------------------------------
@dataclass
class Page:
    url: str
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class PoliteFetcher:
    """One instance per run. Enforces robots.txt, pacing, timeout, retry, challenge stop.

    `session`, `sleep` and `clock` can be replaced in tests.
    """

    def __init__(
        self,
        session=None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = MIN_INTERVAL_S,
        raw_dir: Path | None = RAW_DIR,
        today: str | None = None,
    ):
        if session is None:
            import requests  # local import: tests that inject a session do not need it

            session = requests.Session()
        self.session = session
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
        self._sleep = sleep
        self._clock = clock
        self.min_interval = min_interval
        self.raw_dir = raw_dir
        self.today = today or date.today().isoformat()
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, RobotsRules] = {}
        self.blocked_hosts: dict[str, str] = {}
        self.request_count = 0

    # -- pacing -----------------------------------------------------------
    def _pace(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            wait = self.min_interval - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = self._clock()

    def _request(self, url: str) -> Page:
        host = urlsplit(url).netloc
        last_error = "unknown"
        for attempt in range(MAX_RETRIES + 1):
            self._pace(host)
            self.request_count += 1
            try:
                resp = self.session.get(url, timeout=TIMEOUT_S, allow_redirects=True)
            except OSError as exc:  # requests.RequestException subclasses OSError
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if "charset" not in str(resp.headers.get("content-type", "")).lower():
                    resp.encoding = "utf-8"  # requests would guess ISO-8859-1 for text/* without a charset
                page = Page(resp.url, resp.status_code, resp.text, dict(resp.headers))
                if page.status < 500 and page.status != 408:
                    return page
                last_error = f"HTTP {page.status}"
            if attempt < MAX_RETRIES:
                self._sleep(BACKOFF_BASE_S * (2**attempt))
        raise FetchFailed(f"{url}: {last_error} after {MAX_RETRIES + 1} tries")

    # -- robots -----------------------------------------------------------
    def robots_for(self, url: str) -> RobotsRules:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            page = self._request(robots_url)
            if page.status == 200:
                rules = RobotsRules.parse(page.text)
            elif 400 <= page.status < 500 and page.status not in (401, 403, 429):
                rules = RobotsRules([], None)  # no robots.txt: RFC 9309 says allowed
            else:
                # 401/403/429/5xx on robots.txt: treat the site as off limits
                raise ChallengeDetected(f"{robots_url} answered {page.status}; skipping {host}")
            self._robots[host] = rules
        return self._robots[host]

    def check_allowed(self, url: str) -> None:
        rules = self.robots_for(url)
        pq = path_and_query(url)
        if not rules.allowed(pq):
            raise RobotsDisallowed(f"robots.txt disallows {pq} ({rules.deciding_rule(pq)})")

    # -- public -----------------------------------------------------------
    def get(self, url: str, raw_name: str | None = None) -> Page:
        host = urlsplit(url).netloc
        if host in self.blocked_hosts:
            raise ChallengeDetected(self.blocked_hosts[host])
        try:
            self.check_allowed(url)
            page = self._request(url)
            if is_challenge(page.status, page.headers, page.text):
                raise ChallengeDetected(
                    f"{url}: HTTP {page.status}, cf-mitigated={page.headers.get('cf-mitigated') or page.headers.get('Cf-Mitigated')}"
                )
        except ScrapeStop as exc:
            self.blocked_hosts[host] = str(exc)
            raise
        if page.status != 200:
            raise FetchFailed(f"{url}: HTTP {page.status}")
        if raw_name and self.raw_dir is not None:
            out = Path(self.raw_dir) / _slug(host) / self.today
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{raw_name}.html").write_text(page.text, encoding="utf-8")
        return page


# --------------------------------------------------------------------------
# Personal-data stripping
# --------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Malaysian numbers (+60..., 01x-xxx xxxx, 03-xxxx xxxx) and generic long digit runs.
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
_MESSAGING = re.compile(r"(?:wa\.me|whatsapp\.com|t\.me)/\S+", re.IGNORECASE)
# "Contact: Ms Tan", "Attn - John", "PIC: Aina", "send your CV to Ms Lim" (name part only).
_CONTACT = re.compile(
    r"\b(?:contact(?:\s+person)?|attn|attention|pic|person\s+in\s+charge|whatsapp|call|e-?mail|"
    r"hr\s+manager|recruiter)\s*[:\-]\s*[^\n.;|]{0,60}"
    r"|\bsend\s+(?:your\s+)?(?:cv|resume|résumé)\s+to\s+(?:\S+\s+){0,3}\S+",
    re.IGNORECASE,
)


def strip_pii(text: str) -> str:
    """Remove emails, phone numbers, messaging links and 'contact ...' phrases."""
    if not text:
        return ""
    out = _MESSAGING.sub(" ", text)
    out = _EMAIL.sub(" ", out)
    out = _CONTACT.sub(" ", out)
    out = _PHONE.sub(" ", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def plain(text: str) -> str:
    """HTML or text -> single-line plain text, PII removed."""
    cleaned = strip_pii(clean_text(text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


# --------------------------------------------------------------------------
# Listings and collectors
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Listing:
    """What we keep per listing. Nothing about the employer or any person."""

    site: str
    listing_id: str
    title: str
    posted: str | None
    location: str | None
    teaser: str


def query_slug(query: str) -> str:
    return _slug(query)


class Hiredly:
    """my.hiredly.com keyword pages: /jobs-in-<query-slug>?page=N.

    The page is server-rendered by Next.js. The listings sit in the
    <script id="__NEXT_DATA__"> JSON block of the HTML that the page itself
    returns (props.pageProps.jobs, 30 per page). We call no other endpoint.
    The teaser is the site's own short summary plus the skill chips of the card.
    """

    name = "hiredly"
    base = "https://my.hiredly.com"
    # "unverified": the terms page is rendered by JavaScript, its text is not in the HTML.
    terms_status = "unverified"
    _NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)

    @classmethod
    def build_url(cls, query: str, page: int) -> str:
        url = f"{cls.base}/jobs-in-{query_slug(query)}"
        return url if page <= 1 else f"{url}?page={page}"

    @classmethod
    def parse(cls, html_text: str) -> list[Listing]:
        match = cls._NEXT_DATA.search(html_text or "")
        if not match:
            return []
        try:
            jobs = json.loads(match.group(1))["props"]["pageProps"]["jobs"]
        except (ValueError, KeyError, TypeError):
            return []
        listings: list[Listing] = []
        for job in jobs or []:
            if not isinstance(job, dict) or not job.get("id") or not job.get("title"):
                continue
            chips = [s.get("name", "") if isinstance(s, dict) else str(s) for s in job.get("skills") or []]
            teaser = plain(" ".join([str(job.get("gptSummary") or ""), *chips]))[:TEASER_CHARS]
            listings.append(
                Listing(
                    site=cls.name,
                    listing_id=str(job["id"]),
                    title=plain(str(job["title"])),
                    posted=(str(job.get("activeAt") or "")[:10] or None),
                    location=plain(str(job.get("location") or "")) or None,
                    teaser=teaser,
                )
            )
        return listings


class JobStore:
    """www.jobstore.com/my keyword pages: /my/jobs/q-<query-slug>.html?page=N.

    Server-rendered HTML. Each card is <a id="post-card-N" data-id="...">. The
    card also carries its own description in a data-full JSON attribute of the
    same page; we read only its first 400 characters as the teaser. We never
    read the company, website or logo fields of that JSON.
    """

    name = "jobstore"
    base = "https://www.jobstore.com"
    terms_status = "forbids_without_written_permission"
    _CARD = re.compile(r'(?=<a id="post-card-)')
    _ID = re.compile(r'data-id="([^"]+)"')
    _TITLE = re.compile(r"<h3[^>]*>\s*(.*?)\s*</h3>", re.DOTALL)
    _LOC = re.compile(r'subtitle-loc">\s*(.*?)\s*</span>', re.DOTALL)
    _FULL = re.compile(r"data-full='(.*?)'\s*>", re.DOTALL)

    @classmethod
    def build_url(cls, query: str, page: int) -> str:
        url = f"{cls.base}/my/jobs/q-{query_slug(query)}.html"
        return url if page <= 1 else f"{url}?page={page}"

    @classmethod
    def parse(cls, html_text: str) -> list[Listing]:
        listings: list[Listing] = []
        for block in cls._CARD.split(html_text or "")[1:]:
            id_m, title_m = cls._ID.search(block), cls._TITLE.search(block)
            if not id_m or not title_m:
                continue
            loc_m, full_m = cls._LOC.search(block), cls._FULL.search(block)
            description = ""
            if full_m:
                try:
                    description = str(json.loads(full_m.group(1)).get("description") or "")
                except ValueError:
                    description = ""
            listings.append(
                Listing(
                    site=cls.name,
                    listing_id=id_m.group(1),
                    title=plain(unescape(title_m.group(1))),
                    posted=None,  # JobStore result cards show no posting date
                    location=plain(loc_m.group(1)) if loc_m else None,
                    teaser=plain(description)[:TEASER_CHARS],
                )
            )
        return listings


COLLECTORS = {Hiredly.name: Hiredly, JobStore.name: JobStore}


@dataclass
class SiteResult:
    site: str
    listings: dict[str, Listing] = field(default_factory=dict)
    stopped: str | None = None  # why we stopped early, or None if the run completed
    requests: int = 0
    pages_fetched: int = 0


def collect_site(
    fetcher: PoliteFetcher,
    collector,
    queries: Iterable[str] = QUERIES,
    max_pages: int = MAX_PAGES,
) -> SiteResult:
    """Run every query, page by page. Stop the whole site on any ScrapeStop."""
    result = SiteResult(site=collector.name)
    start = fetcher.request_count
    try:
        for query in queries:
            for page_no in range(1, max_pages + 1):
                url = collector.build_url(query, page_no)
                page = fetcher.get(url, raw_name=f"{query_slug(query)}_p{page_no}")
                result.pages_fetched += 1
                found = collector.parse(page.text)
                new = [x for x in found if x.listing_id not in result.listings]
                for item in found:
                    result.listings.setdefault(item.listing_id, item)
                log.info("%s %r p%d: %d listings, %d new", collector.name, query, page_no, len(found), len(new))
                if not found or not new:
                    break  # empty or repeated page: no point asking for the next one
    except ScrapeStop as exc:
        result.stopped = f"{type(exc).__name__}: {exc}"
        log.warning("%s stopped: %s", collector.name, result.stopped)
    result.requests = fetcher.request_count - start
    return result


# --------------------------------------------------------------------------
# Aggregation and snapshot files
# --------------------------------------------------------------------------
def load_roles(path: Path = ROLES_JSON) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def aggregate(
    listings: Iterable[Listing],
    taxonomy: list[dict],
    roles: list[dict],
    snapshot_date: str,
    site: str,
) -> tuple[list[dict], list[dict]]:
    """Listings -> (skill rows, role rows).

    Skills: a listing counts once per skill if title + teaser mention it (tag_text).
    Only skills with at least one mention get a row.
    Roles: roles.json title_pattern against the TITLE only. A title can match two
    roles. Every role gets a row, also with n = 0.
    """
    items = list(listings)
    n = len(items)
    skill_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    role_rx = [(r["id"], re.compile(r["title_pattern"], re.IGNORECASE)) for r in roles]
    for item in items:
        skill_counts.update(tag_text(f"{item.title}. {item.teaser}", taxonomy))
        for role_id, rx in role_rx:
            if rx.search(item.title):
                role_counts[role_id] += 1
    skill_rows = [
        {
            "snapshot_date": snapshot_date,
            "site": site,
            "skill": skill,
            "mentions": count,
            "n_listings": n,
            "share": round(count / n, 6),
        }
        for skill, count in sorted(skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    role_rows = [
        {
            "snapshot_date": snapshot_date,
            "site": site,
            "role_id": role_id,
            "n": role_counts[role_id],
            "share": round(role_counts[role_id] / n, 6) if n else 0.0,
        }
        for role_id, _ in role_rx
    ]
    return skill_rows, role_rows


def append_snapshot(path: Path, columns: list[str], rows: list[dict], snapshot_date: str, site: str) -> None:
    """Append rows. A re-run on the same day for the same site replaces its rows."""
    path = Path(path)
    kept: list[dict] = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            kept = [r for r in csv.DictReader(fh) if not (r["snapshot_date"] == snapshot_date and r["site"] == site)]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(kept)
        writer.writerows(rows)


# --------------------------------------------------------------------------
# Comparison with Hacker News
# --------------------------------------------------------------------------
def hn_share_last_months(demand_csv: Path = HN_DEMAND_CSV, months: int = 3) -> dict[str, float]:
    """Pooled HN share over the last `months` months: sum(mentions) / sum(n_posts)."""
    with Path(demand_csv).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    last = sorted({r["month"] for r in rows})[-months:]
    posts = {r["month"]: int(r["n_posts"]) for r in rows if r["month"] in last}
    total_posts = sum(posts.values())
    mentions: Counter[str] = Counter()
    for r in rows:
        if r["month"] in last:
            mentions[r["skill"]] += int(r["mentions"])
    return {skill: count / total_posts for skill, count in mentions.items()}


def compare_with_hn(
    skills_csv: Path = SKILLS_CSV,
    demand_csv: Path = HN_DEMAND_CSV,
    snapshot_date: str | None = None,
    top: int = 10,
) -> list[dict]:
    """Top skills of the latest Malaysia snapshot (all sites pooled), next to the HN share."""
    with Path(skills_csv).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    snapshot_date = snapshot_date or max(r["snapshot_date"] for r in rows)
    rows = [r for r in rows if r["snapshot_date"] == snapshot_date]
    n_total = sum({r["site"]: int(r["n_listings"]) for r in rows}.values())
    mentions: Counter[str] = Counter()
    for r in rows:
        mentions[r["skill"]] += int(r["mentions"])
    hn = hn_share_last_months(demand_csv)
    out = []
    for skill, count in mentions.most_common(top):
        out.append(
            {"skill": skill, "my_mentions": count, "my_n": n_total, "my_share": count / n_total, "hn_share": hn.get(skill)}
        )
    return out


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
def run(
    sites: list[str],
    max_pages: int = MAX_PAGES,
    queries: Iterable[str] = QUERIES,
    write: bool = True,
    fetcher: PoliteFetcher | None = None,
    snapshot_date: str | None = None,
) -> list[SiteResult]:
    snapshot_date = snapshot_date or date.today().isoformat()
    fetcher = fetcher or PoliteFetcher(today=snapshot_date)
    taxonomy, roles = load_taxonomy(), load_roles()
    results = []
    for name in sites:
        result = collect_site(fetcher, COLLECTORS[name], queries=queries, max_pages=max_pages)
        results.append(result)
        if result.stopped or not result.listings:
            log.warning("%s: nothing written (%s)", name, result.stopped or "no listings")
            continue
        skill_rows, role_rows = aggregate(result.listings.values(), taxonomy, roles, snapshot_date, name)
        if write:
            append_snapshot(SKILLS_CSV, SKILLS_COLUMNS, skill_rows, snapshot_date, name)
            append_snapshot(ROLES_CSV, ROLES_COLUMNS, role_rows, snapshot_date, name)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sites", default="", help=f"comma list of: {', '.join(COLLECTORS)}")
    parser.add_argument("--pages", type=int, default=MAX_PAGES, help="result pages per query (max 3)")
    parser.add_argument("--dry-run", action="store_true", help="fetch and count, but write no CSV")
    parser.add_argument("--compare", action="store_true", help="print the latest Malaysia top skills next to HN")
    parser.add_argument(
        "--permission-confirmed",
        action="store_true",
        help="needed for sites whose terms forbid or do not clearly allow automated access: "
        "you confirm that the written permission is on file",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.compare:
        for row in compare_with_hn():
            hn = "n/a" if row["hn_share"] is None else f"{row['hn_share']:.1%}"
            print(f"{row['skill']:<28} MY {row['my_share']:.1%} ({row['my_mentions']}/{row['my_n']})  HN {hn}")
        return 0
    sites = [s.strip() for s in args.sites.split(",") if s.strip()]
    unknown = [s for s in sites if s not in COLLECTORS]
    if not sites or unknown:
        parser.error(f"--sites needs one or more of {sorted(COLLECTORS)}; got {unknown or 'nothing'}")
    needs_permission = [s for s in sites if COLLECTORS[s].terms_status != "no_clause_found"]
    if needs_permission and not args.permission_confirmed:
        parser.error(f"terms of {needs_permission} need written permission; pass --permission-confirmed only if it is on file")
    results = run(sites, max_pages=min(args.pages, MAX_PAGES), write=not args.dry_run)
    for r in results:
        print(f"{r.site}: {len(r.listings)} listings, {r.pages_fetched} pages, {r.requests} requests, stopped={r.stopped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
