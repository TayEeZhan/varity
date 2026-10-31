"""Tests for engine.my_dosm: a tiny file in the DOSM layout (made-up numbers, for tests only). No network."""
from pathlib import Path

import pytest

from engine import my_dosm

FIXTURE = Path(__file__).parent / "fixtures" / "my_dosm_mini.xlsx"
URL = "https://example.test/release-document-log?release_document_id=1"


def test_parse_reads_named_cells():
    rows = my_dosm.parse(FIXTURE, URL, "2026-08-18")
    assert len(rows) == 12  # 3 rows x 4 quarters
    ict = {r["quarter"]: r for r in rows if r["row_label"] == "Information and communication"}
    assert [ict[q]["vacancies"] for q in sorted(ict)] == [100, 200, 300, 150]
    assert ict["2026-Q1"]["cell"] == "M15" and ict["2026-Q1"]["table"] == "economic_activity"
    assert {r["table"] for r in rows if r["row_label"] == "Professionals"} == {"masco_major"}


def test_summary_percentages_are_computed_by_code(tmp_path):
    path = tmp_path / "v.csv"
    my_dosm.write_csv(my_dosm.parse(FIXTURE, URL, "2026-08-18"), path)
    s = my_dosm.summary(my_dosm.read_csv(path))
    ict = s["ict"]
    assert (ict["quarter"], ict["vacancies"], ict["previous"], ict["vsPreviousQuarterPct"]) == ("2026-Q2", 150, 300, -50.0)
    assert ict["yearAgo"] is None and ict["vsYearAgoPct"] is None  # 2025-Q2 is not in the file: no invented value
    assert s["professionals"]["vsPreviousQuarterPct"] == 33.3 and s["sourceUrl"] == URL
    assert my_dosm.summary(my_dosm.read_csv(tmp_path / "missing.csv")) is None


def test_bad_layout_raises(tmp_path):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(Exception):
        my_dosm.parse(bad, URL, "2026-08-18")


def test_update_keeps_old_csv_on_failure_and_replaces_on_success(tmp_path):
    path = tmp_path / "v.csv"
    my_dosm.write_csv(my_dosm.parse(FIXTURE, URL, "2026-08-18"), path)  # latest 2026-Q2: next is q32026
    before = path.read_bytes()
    asked = []

    def no_page(url):
        asked.append(url)
        raise OSError("404")

    assert my_dosm.update(path, fetch=no_page)["ok"] is False and asked[0].endswith("-q32026")
    assert path.read_bytes() == before
    html = '<div id="data"><a href="x?release_document_id=777">Data</a></div> Latest Release : 18 November 2026'
    assert my_dosm.find_release(html)[1] == "2026-11-18"
    with pytest.raises(ValueError):
        my_dosm.find_release("<html>nothing yet</html>")

    def page_then_same_file(url):  # the file has no newer quarter: still keep the old CSV
        return html.encode() if "release-content" in url else FIXTURE.read_bytes()

    assert my_dosm.update(path, fetch=page_then_same_file)["ok"] is False and path.read_bytes() == before
