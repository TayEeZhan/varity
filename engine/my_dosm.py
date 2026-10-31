"""DOSM "Big Data Analytics: Job Market Insights" (online job vacancies, quarterly): a Malaysian cross-check.

Source: the "Data" Excel file of each DOSM release (https://www.dosm.gov.my/portal-main/release-archive/...).
It holds only two tables, by economic activity and by MASCO MAJOR group. There is no job-title or role split,
so these numbers never describe one role. We keep three rows, as written in the file:
  Information and communication (economic activity), Professionals and Technicians and associate professionals.

Every stored number is read from one named cell and checked against it. Code does the percentages.
Run:  python -m engine.my_dosm            (weekly: look for a newer release, keep the old CSV on any failure)
      python -m engine.my_dosm --file data/raw/dosm/q2_2026.xlsx --url <release-document-log URL> --published 2026-08-18
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "my_vacancies_quarterly.csv"
RAW_DIR = DATA_DIR / "raw" / "dosm"
SITE = "https://www.dosm.gov.my"
RELEASE_PAGE = SITE + "/portal-main/release-content/big-data-analytics-job-market-insights-q{q}{year}"
FIELDS = ["quarter", "table", "row_label", "vacancies", "source_url", "sheet", "cell", "published"]
# (table key, title prefix in the sheet, row label as DOSM writes it)
KEEP = [("economic_activity", "Table 1", "Information and communication"),
        ("masco_major", "Table 2", "Professionals"),
        ("masco_major", "Table 2", "Technicians and associate professionals")]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NOTE = "DOSM does not split by job title, so this is not a per-role number."


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n


def read_cells(path: Path) -> tuple[str, dict[str, str]]:
    """(sheet name, {cell ref: text}) of the first sheet. zipfile + XML only: no Excel library is installed."""
    with zipfile.ZipFile(path) as z:
        sheet = re.search(r'<sheet [^>]*name="([^"]+)"', z.read("xl/workbook.xml").decode("utf-8")).group(1)
        strings = ["".join(t.text or "" for t in si.iter("{%s}t" % NS["m"]))
                   for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
        cells = {}
        for c in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter("{%s}c" % NS["m"]):
            v = c.find("m:v", NS)
            if v is not None:
                cells[c.get("r")] = strings[int(v.text)] if c.get("t") == "s" else v.text
    return sheet, cells


def parse(path: Path, source_url: str, published: str) -> list[dict]:
    """The kept rows for every quarter in the file. Raises ValueError when the layout is not what we expect."""
    sheet, cells = read_cells(path)
    by_row: dict[int, dict[int, str]] = {}
    for ref, text in cells.items():
        by_row.setdefault(int(re.search(r"\d+", ref).group()), {})[_col(ref)] = text

    def ref(col: int, row: int) -> str:
        s = ""
        while col:
            col, r = divmod(col - 1, 26)
            s = chr(65 + r) + s
        return f"{s}{row}"

    out = []
    for key, title, label in KEEP:
        trow = next((r for r, c in sorted(by_row.items()) if c.get(2, "").startswith(title + ":")), None)
        if trow is None:
            raise ValueError(f"{title} not found")
        # header rows: years at trow+2, quarters at trow+3; data row = first row below with this label in column B
        years, quarters = by_row.get(trow + 2, {}), by_row.get(trow + 3, {})
        data_row = next((r for r in range(trow + 4, trow + 25) if by_row.get(r, {}).get(2, "").strip().lower() == label.lower()), None)
        if data_row is None:
            raise ValueError(f"row '{label}' not found under {title}")
        first = min((c for c, t in quarters.items() if c > 2 and re.fullmatch(r"Q[1-4]", t) and c in years), default=None)
        if first is None:
            raise ValueError(f"no quarter columns under {title}")
        col, year = first, None
        while re.fullmatch(r"Q[1-4]", quarters.get(col, "")):
            year = years.get(col, year)
            value = by_row[data_row].get(col)
            if value is not None:  # a quarter not yet published has an empty cell
                n = int(value)
                assert str(n) == value or float(value) == n, (ref(col, data_row), value)
                out.append({"quarter": f"{year}-{quarters[col]}", "table": key, "row_label": label, "vacancies": n,
                            "source_url": source_url, "sheet": sheet, "cell": ref(col, data_row), "published": published})
            col += 1
    for row in out:  # the stored number must equal the cell it names
        assert int(cells[row["cell"]]) == row["vacancies"], row
    return out


def write_csv(rows: list[dict], path: Path = CSV_PATH) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def read_csv(path: Path = CSV_PATH) -> list[dict]:
    """[] when the file is missing."""
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return [{**r, "vacancies": int(r["vacancies"])} for r in csv.DictReader(f)]
    except OSError:
        return []


def _pct(now: int, before: int | None) -> float | None:
    return round((now / before - 1) * 100, 1) if before else None


def _prev(quarter: str, back: int) -> str:
    year, q = int(quarter[:4]), int(quarter[-1])
    index = year * 4 + q - 1 - back
    return f"{index // 4}-Q{index % 4 + 1}"


def summary(rows: list[dict]) -> dict | None:
    """The small block the API sends. None when there is no data."""
    def block(label: str) -> dict | None:
        series = {r["quarter"]: r for r in rows if r["row_label"] == label}
        if not series:
            return None
        latest = max(series)
        prev, year_ago = series.get(_prev(latest, 1)), series.get(_prev(latest, 4))
        v = series[latest]["vacancies"]
        return {"label": label, "quarter": latest, "vacancies": v,
                "previousQuarter": prev and prev["quarter"], "previous": prev and prev["vacancies"],
                "vsPreviousQuarterPct": _pct(v, prev and prev["vacancies"]),
                "yearAgoQuarter": year_ago and year_ago["quarter"], "yearAgo": year_ago and year_ago["vacancies"],
                "vsYearAgoPct": _pct(v, year_ago and year_ago["vacancies"]),
                "series": [{"quarter": q, "vacancies": series[q]["vacancies"]} for q in sorted(series)]}
    ict, pro = block("Information and communication"), block("Professionals")
    if not ict:
        return None
    last = next(r for r in rows if r["row_label"] == "Information and communication" and r["quarter"] == ict["quarter"])
    return {"ict": ict, "professionals": pro, "latestQuarter": ict["quarter"], "sourceUrl": last["source_url"],
            "published": last["published"], "provider": "DOSM, Big Data Analytics: Job Market Insights", "note": NOTE}


# ---- weekly check for a newer release -------------------------------------------------------------------

def _get(url: str, timeout: int = 60) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # default Python request, no browser headers
        return resp.read()


def find_release(html: str) -> tuple[str, str]:
    """(Data link, published date ISO) from a release page. Raises ValueError when the page has no Data file yet."""
    m = re.search(r'id="data".*?release_document_id=(\d+)', html, re.S)
    d = re.search(r"Latest Release\s*:\s*(\d{1,2} \w+ \d{4})", html)
    if not (m and d):
        raise ValueError("the release page has no Data link or release date")
    return (f"{SITE}/portal-main/release-document-log?release_document_id={m.group(1)}",
            datetime.strptime(d.group(1), "%d %B %Y").date().isoformat())


def update(path: Path = CSV_PATH, fetch=_get) -> dict:
    """Look for the quarter after the stored one. Never raises. The old CSV stays unless a full new parse succeeds."""
    try:
        have = read_csv(path)
        if not have:
            return {"ok": False, "error": "no CSV yet: run once with --file"}
        year, q = (int(x) for x in _prev(max(r["quarter"] for r in have), -1).split("-Q"))
        page = fetch(RELEASE_PAGE.format(q=q, year=year)).decode("utf-8", "replace")
        url, published = find_release(page)
        with tempfile.TemporaryDirectory() as tmp:
            xlsx = Path(tmp) / "data.xlsx"
            xlsx.write_bytes(fetch(url))
            rows = parse(xlsx, url, published)
        if max(r["quarter"] for r in rows) <= max(r["quarter"] for r in have):
            return {"ok": False, "error": "the new file has no newer quarter"}
        write_csv(rows, path)
        return {"ok": True, "latest": max(r["quarter"] for r in rows), "rows": len(rows)}
    except Exception as exc:  # noqa: BLE001 - a missing page is the normal "no new release yet" case
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"), ap.add_argument("--url"), ap.add_argument("--published")
    a = ap.parse_args()
    if a.file:
        rows = parse(Path(a.file), a.url, a.published)
        write_csv(rows)
        result = {"ok": True, "rows": len(rows), "latest": max(r["quarter"] for r in rows)}
    else:
        result = update()
    print(json.dumps(result))
    return 0  # "no new release yet" is normal; the error text is in the printed result


if __name__ == "__main__":
    sys.exit(main())
