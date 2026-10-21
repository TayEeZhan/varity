"""Backfill Hacker News "Ask HN: Who is hiring?" threads from January 2019 to now.

Each top-level comment in a thread is one job post. This script only fetches
and counts. It does not tag skills (another task does that).

Steps
1. List threads with the public Algolia HN search API and keep titles that
   start with "Ask HN: Who is hiring?" and were created on or after 2019-01-01.
2. Fetch each thread with the Algolia items API. Raw JSON goes to
   data/raw/hn/<id>.json (gitignored). An existing file is reused, so re-runs are cheap.
3. Write data/hn_threads.csv (committed), one row per thread, sorted by month.
4. Print a short summary.

Run as a plain script:
    python engine/backfill_hn.py
"""

from __future__ import annotations

import calendar
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "hn"
CSV_PATH = ROOT / "data" / "hn_threads.csv"

LIST_URL = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=1000"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"

TITLE_PREFIX = "Ask HN: Who is hiring?"
START = datetime(2019, 1, 1, tzinfo=timezone.utc)
FIRST_MONTH = "2019-01"

USER_AGENT = "Verity-hackathon-hn-backfill/1.0 (student hackathon project; one request at a time)"
TIMEOUT_S = 60
SLEEP_S = 0.5
MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0

CSV_COLUMNS = ["thread_id", "month", "created_at", "title", "url", "n_top_level"]

MONTH_BY_NAME = {calendar.month_name[i].lower(): i for i in range(1, 13)}
TITLE_MONTH_RE = re.compile(r"\(\s*([A-Za-z]+)\s+(\d{4})\s*\)")


def fetch_json(session: requests.Session, url: str) -> tuple[bytes, object]:
    """GET a URL politely and return (raw bytes, parsed JSON).

    Retries up to MAX_RETRIES times with exponential backoff on network errors,
    HTTP 429, HTTP 5xx and invalid JSON. Other HTTP errors fail at once.
    Every request, successful or not, is followed by SLEEP_S.
    """
    last_err = "no attempt made"
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            delay = BACKOFF_BASE_S * 2 ** (attempt - 1)
            print(f"    retry {attempt}/{MAX_RETRIES} in {delay:.0f}s ({last_err})", flush=True)
            time.sleep(delay)

        status = None
        body = b""
        try:
            resp = session.get(url, timeout=TIMEOUT_S)
            status = resp.status_code
            body = resp.content
        except requests.RequestException as exc:
            last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(SLEEP_S)

        if status is None:
            continue
        if status == 429 or status >= 500:
            last_err = f"HTTP {status}"
            continue
        if not 200 <= status < 300:
            raise RuntimeError(f"HTTP {status} for {url}")
        try:
            return body, json.loads(body)
        except ValueError as exc:
            last_err = f"invalid JSON: {exc}"

    raise RuntimeError(f"gave up after {MAX_RETRIES + 1} attempts for {url} ({last_err})")


def list_threads(session: requests.Session) -> list[dict]:
    """Return matching "Who is hiring?" threads created on or after START, oldest first."""
    found: dict[int, dict] = {}
    page = 0
    while True:
        _, data = fetch_json(session, f"{LIST_URL}&page={page}")
        for hit in data.get("hits", []):
            title = (hit.get("title") or "").strip()
            if not title.startswith(TITLE_PREFIX):
                continue
            try:
                thread_id = int(hit["objectID"])
                created = datetime.fromtimestamp(int(hit["created_at_i"]), tz=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if created < START:
                continue
            found[thread_id] = {"id": thread_id, "title": title, "created": created}
        page += 1
        if page >= int(data.get("nbPages", 0)):
            break
    return sorted(found.values(), key=lambda t: t["created"])


def month_from_title(title: str) -> str | None:
    """Parse "(Month Year)" from a title into "YYYY-MM", or None."""
    match = TITLE_MONTH_RE.search(title)
    if not match:
        return None
    month_num = MONTH_BY_NAME.get(match.group(1).lower())
    if month_num is None:
        return None
    return f"{int(match.group(2)):04d}-{month_num:02d}"


def count_top_level(item: dict) -> int:
    """Count top-level comments that have text and are not deleted."""
    count = 0
    for child in item.get("children") or []:
        if child.get("deleted"):
            continue
        if (child.get("text") or "").strip():
            count += 1
    return count


def load_or_fetch(session: requests.Session, thread_id: int) -> tuple[dict, str]:
    """Return (parsed item, "cached" or "fetched"). Saves raw JSON atomically when fetched."""
    path = RAW_DIR / f"{thread_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "cached"

    raw, data = fetch_json(session, ITEM_URL.format(id=thread_id))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)
    return data, "fetched"


def write_csv(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def missing_months(months: set[str], latest: str) -> list[str]:
    """Months from FIRST_MONTH to latest (inclusive) that have no thread."""
    y, m = map(int, FIRST_MONTH.split("-"))
    last_y, last_m = map(int, latest.split("-"))
    out = []
    while (y, m) <= (last_y, last_m):
        key = f"{y:04d}-{m:02d}"
        if key not in months:
            out.append(key)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


# ---------------------------------------------------------------------------
# Live refresh: newest thread only. The full backfill above does not use this.
# ---------------------------------------------------------------------------

# Newest first. The author "whoishiring" posts 3 threads a month (hiring,
# freelancer, seeking freelancer), so 30 hits cover the last ~10 months.
LATEST_URL = "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=30"


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def find_latest_thread(session: requests.Session) -> dict:
    """Return {"id", "title", "created"} for the newest "Who is hiring?" thread."""
    _, data = fetch_json(session, LATEST_URL)
    best = None
    for hit in (data.get("hits") or []) if isinstance(data, dict) else []:
        title = (hit.get("title") or "").strip()
        if not title.startswith(TITLE_PREFIX):
            continue
        try:
            thread_id = int(hit["objectID"])
            created = datetime.fromtimestamp(int(hit["created_at_i"]), tz=timezone.utc)
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or created > best["created"]:
            best = {"id": thread_id, "title": title, "created": created}
    if best is None:
        raise RuntimeError("no 'Ask HN: Who is hiring?' thread in the Algolia result")
    return best


def upsert_thread_row(csv_path: Path, row: dict) -> str:
    """Add or update one row of hn_threads.csv. Return "added", "updated" or "unchanged".

    Rows are matched by thread_id. A different thread for a month that already
    has one raises RuntimeError: demand.py allows one thread per month.
    """
    csv_path = Path(csv_path)
    rows: list[dict] = []
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    new = {k: str(row[k]) for k in CSV_COLUMNS}
    result = "added"
    out = []
    for r in rows:
        if r["thread_id"] == new["thread_id"]:
            result = "unchanged" if r == new else "updated"
            continue
        if r["month"] == new["month"]:
            raise RuntimeError(f"month {new['month']} already has thread {r['thread_id']}, not {new['thread_id']}")
        out.append(r)
    if result == "unchanged":
        return result
    out.append(new)
    out.sort(key=lambda r: (r["month"], int(r["thread_id"])))
    tmp = csv_path.with_name(csv_path.name + ".tmp")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(out)
    os.replace(tmp, csv_path)
    return result


def fetch_latest_thread(
    force: bool = True,
    raw_dir: str | Path = RAW_DIR,
    session: requests.Session | None = None,
    csv_path: str | Path | None = CSV_PATH,
) -> tuple[int, str, int, str]:
    """Fetch the newest "Ask HN: Who is hiring?" thread and return
    (thread_id, month, n_top_level, fetched_at).

    force=True ignores any cached raw JSON and downloads the thread again.
    force=False reuses <raw_dir>/<id>.json when it exists (fetched_at is then
    the file's modified time). The raw JSON is saved atomically, and only after
    it passes a basic check. Pass csv_path=None to leave hn_threads.csv alone;
    otherwise the thread's row is added or updated there (a new month adds a row).
    Raises RuntimeError (or OSError) on failure. Nothing is written before the
    download has succeeded.
    """
    raw_dir = Path(raw_dir)
    session = session or make_session()
    thread = find_latest_thread(session)
    thread_id = thread["id"]
    path = raw_dir / f"{thread_id}.json"

    if path.exists() and not force:
        item = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    else:
        raw, item = fetch_json(session, ITEM_URL.format(id=thread_id))
        if not isinstance(item, dict) or not isinstance(item.get("children"), list):
            raise RuntimeError(f"unexpected item JSON for thread {thread_id}")
        fetched_at = datetime.now(timezone.utc)
        _atomic_write_bytes(path, raw)

    created = thread["created"]
    month = month_from_title(thread["title"]) or created.strftime("%Y-%m")
    n_top_level = count_top_level(item)
    if csv_path is not None:
        upsert_thread_row(
            Path(csv_path),
            {
                "thread_id": thread_id,
                "month": month,
                "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "title": thread["title"],
                "url": HN_ITEM_URL.format(id=thread_id),
                "n_top_level": n_top_level,
            },
        )
    return thread_id, month, n_top_level, fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    print("Listing threads from Algolia HN search...", flush=True)
    threads = list_threads(session)
    print(f"  {len(threads)} matching threads since 2019-01-01", flush=True)

    rows: list[dict] = []
    failed: list[tuple[int, str]] = []
    n_fetched = n_cached = n_title_mismatch = 0

    for i, thread in enumerate(threads, 1):
        thread_id = thread["id"]
        try:
            item, status = load_or_fetch(session, thread_id)
        except (RuntimeError, OSError, ValueError) as exc:
            failed.append((thread_id, str(exc)))
            print(f"  [{i}/{len(threads)}] {thread_id} FAILED: {exc}", flush=True)
            continue

        if status == "fetched":
            n_fetched += 1
        else:
            n_cached += 1
        print(f"  [{i}/{len(threads)}] {thread_id} {status}", flush=True)

        created = thread["created"]
        month = month_from_title(thread["title"])
        if month is None:
            month = created.strftime("%Y-%m")
        elif month != created.strftime("%Y-%m"):
            n_title_mismatch += 1

        rows.append(
            {
                "thread_id": thread_id,
                "month": month,
                "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "title": thread["title"],
                "url": HN_ITEM_URL.format(id=thread_id),
                "n_top_level": count_top_level(item),
            }
        )

    rows.sort(key=lambda r: (r["month"], r["thread_id"]))
    write_csv(rows)

    months = {r["month"] for r in rows}
    per_month: dict[str, int] = {}
    for r in rows:
        per_month[r["month"]] = per_month.get(r["month"], 0) + 1
    duplicates = sorted(m for m, c in per_month.items() if c > 1)

    print()
    print("Summary")
    print(f"  threads written:      {len(rows)}")
    print(f"  fetched / cached:     {n_fetched} / {n_cached}")
    if rows:
        print(f"  first month:          {rows[0]['month']}")
        print(f"  last month:           {rows[-1]['month']}")
    print(f"  top-level posts:      {sum(r['n_top_level'] for r in rows)}")
    if rows:
        gaps = missing_months(months, rows[-1]["month"])
        print(f"  missing months:       {', '.join(gaps) if gaps else 'none'}")
    if duplicates:
        print(f"  months with 2+ threads: {', '.join(duplicates)}")
    if n_title_mismatch:
        print(f"  title month != created month: {n_title_mismatch} (title month used)")
    if failed:
        print(f"  FAILED threads: {len(failed)}")
        for thread_id, err in failed:
            print(f"    {thread_id}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
