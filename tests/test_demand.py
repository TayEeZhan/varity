"""Tests for engine.demand. Uses tiny synthetic threads in tmp_path, never data/raw."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.demand import COLUMNS, build_demand  # noqa: E402

TAXONOMY = [
    {"skill": "Python", "pattern": r"\bpython\b", "case_sensitive": False},
    {"skill": "Rust", "pattern": r"\brust\b", "case_sensitive": False},
    {"skill": "Kubernetes", "pattern": r"\b(kubernetes|k8s)\b", "case_sensitive": False},
]


def _post(text=None, deleted=False):
    child = {"type": "comment", "children": []}
    if text is not None:
        child["text"] = text
    if deleted:
        child["deleted"] = True
    return child


@pytest.fixture
def setup(tmp_path):
    """Thread 1 (2024-01): 4 live posts, 2 skipped. Thread 2 (2024-02): 2 live posts. Thread 3 (2024-03): 1 post."""
    raw = tmp_path / "raw"
    raw.mkdir()
    t1 = {"children": [
        _post("Acme | Python, Python and more Python. <p>Also Rust"),  # once per skill
        _post("Beta | We use python and k8s"),
        _post("Gamma | Java shop"),
        _post("Delta | Rust only"),
        _post("", ),                       # empty
        _post("   "),                      # blank
        _post(None, deleted=True),         # deleted, no text
        _post("Python everywhere", deleted=True),  # deleted with text
    ]}
    t2 = {"children": [_post("Python again"), _post("nothing relevant")]}
    t3 = {"children": [_post("Rust and Kubernetes")]}
    for tid, item in ((1, t1), (2, t2), (3, t3)):
        (raw / f"{tid}.json").write_text(json.dumps(item), encoding="utf-8")
    threads = tmp_path / "threads.csv"
    with threads.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["thread_id", "month", "created_at", "title", "url", "n_top_level"])
        # written out of order on purpose
        w.writerow([2, "2024-02", "x", "t", "https://example.test/item?id=2", 2])
        w.writerow([1, "2024-01", "x", "t", "https://example.test/item?id=1", 4])
        w.writerow([3, "2024-03", "x", "t", "https://example.test/item?id=3", 1])
    tax = tmp_path / "tax.json"
    tax.write_text(json.dumps(TAXONOMY), encoding="utf-8")
    out = tmp_path / "out" / "demand.csv"
    rows = build_demand(threads, raw, out, tax)
    return rows, out


def _get(rows, month, skill):
    (row,) = [r for r in rows if r["month"] == month and r["skill"] == skill]
    return row


def test_counts_once_per_post_and_skips_deleted_or_empty(setup):
    rows, _ = setup
    assert _get(rows, "2024-01", "Python")["mentions"] == 2  # not 4, not 3
    assert _get(rows, "2024-01", "Rust")["mentions"] == 2
    assert _get(rows, "2024-01", "Kubernetes")["mentions"] == 1
    assert {r["n_posts"] for r in rows if r["month"] == "2024-01"} == {4}


def test_share_math(setup):
    rows, _ = setup
    assert _get(rows, "2024-01", "Python")["share"] == pytest.approx(2 / 4)
    assert _get(rows, "2024-02", "Python")["share"] == pytest.approx(1 / 2)
    assert _get(rows, "2024-03", "Rust")["share"] == pytest.approx(1.0)


def test_zero_rows_exist_for_every_month_and_skill(setup):
    rows, out = setup
    assert len(rows) == 3 * len(TAXONOMY)
    assert {(r["month"], r["skill"]) for r in rows} == {
        (m, t["skill"]) for m in ("2024-01", "2024-02", "2024-03") for t in TAXONOMY
    }
    zero = _get(rows, "2024-02", "Kubernetes")
    assert zero["mentions"] == 0 and zero["share"] == 0.0
    with out.open(encoding="utf-8", newline="") as fh:
        written = list(csv.DictReader(fh))
    assert list(written[0].keys()) == COLUMNS
    assert len(written) == len(rows)


def test_trailing_smoothing_has_no_lookahead(setup):
    rows, _ = setup
    # Python shares: 0.5, 0.5, 0.0
    assert _get(rows, "2024-01", "Python")["share_smooth"] == pytest.approx(0.5)  # only itself
    assert _get(rows, "2024-02", "Python")["share_smooth"] == pytest.approx(0.5)
    assert _get(rows, "2024-03", "Python")["share_smooth"] == pytest.approx((0.5 + 0.5 + 0.0) / 3)
    # Rust shares: 0.5, 0.0, 1.0. Month 2 must not see month 3.
    assert _get(rows, "2024-02", "Rust")["share_smooth"] == pytest.approx(0.25)
    assert _get(rows, "2024-03", "Rust")["share_smooth"] == pytest.approx(0.5)


def test_smoothing_ignores_future_changes(tmp_path, setup):
    """Changing the last month must not change any earlier smoothed value."""
    rows, out = setup
    raw = out.parent.parent / "raw"
    (raw / "3.json").write_text(json.dumps({"children": [_post("Python Python")]}), encoding="utf-8")
    rows2 = build_demand(out.parent.parent / "threads.csv", raw, None, out.parent.parent / "tax.json")
    for r, r2 in zip(rows, rows2):
        if r["month"] < "2024-03":
            assert r["share_smooth"] == r2["share_smooth"]


def test_output_has_no_post_text_or_post_urls(setup):
    _, out = setup
    content = out.read_text(encoding="utf-8")
    assert "Acme" not in content and "Java shop" not in content
    assert "https://example.test/item?id=1" in content  # thread URL only


def test_two_threads_for_one_month_is_an_error(tmp_path):
    threads = tmp_path / "t.csv"
    threads.write_text(
        "thread_id,month,created_at,title,url,n_top_level\n1,2024-01,x,t,u1,0\n2,2024-01,x,t,u2,0\n",
        encoding="utf-8",
    )
    tax = tmp_path / "tax.json"
    tax.write_text(json.dumps(TAXONOMY), encoding="utf-8")
    with pytest.raises(ValueError):
        build_demand(threads, tmp_path, None, tax)
