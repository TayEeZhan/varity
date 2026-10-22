"""Tests for the live refresh pipeline. No network: HTTP is a fake session."""
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import backfill_hn, demand, refresh as refresh_mod  # noqa: E402

TAXONOMY = [
    {"skill": "Python", "pattern": r"\bpython\b", "case_sensitive": False},
    {"skill": "Rust", "pattern": r"\brust\b", "case_sensitive": False},
]
TITLES = {1: "January 2024", 2: "February 2024", 3: "March 2024", 4: "April 2024"}
CREATED = {i: datetime(2024, i, 1, 15, 0, 0, tzinfo=timezone.utc) for i in TITLES}


def _post(text):
    return {"type": "comment", "text": text, "children": []}


def _item(thread_id, posts):
    return {"id": thread_id, "children": [_post(t) for t in posts]}


OLD = {
    1: ["Acme | Python dev", "Beta | Rust dev", "Gamma | Java"],
    2: ["Acme | Python dev", "Beta | Python and Rust", "Gamma | Java", "Delta | Go"],
    3: ["Acme | Python dev", "Beta | Rust dev"],
}
NEW_3 = ["Acme | Python dev", "Beta | Rust dev", "Gamma | Python again", "Delta | Rust again", "Eps | Java"]
NEW_4 = ["Acme | Python dev", "Beta | Go"]


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self.content = json.dumps(payload).encode("utf-8")


class FakeSession:
    """Serves the Algolia list and item endpoints. Records each URL it is asked for."""

    def __init__(self, latest_id, items):
        self.latest_id = latest_id
        self.items = items
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        if "search_by_date" in url:
            n = self.latest_id
            hits = [
                {"objectID": "900", "title": "Ask HN: Freelancer? (April 2024)", "created_at_i": int(CREATED[4].timestamp()) + 5},
                {"objectID": str(n), "title": f"Ask HN: Who is hiring? ({TITLES[n]})", "created_at_i": int(CREATED[n].timestamp())},
                {"objectID": "2", "title": "Ask HN: Who is hiring? (February 2024)", "created_at_i": int(CREATED[2].timestamp())},
            ]
            return FakeResponse({"hits": hits, "nbPages": 1})
        thread_id = int(url.rsplit("/", 1)[1])
        return FakeResponse(self.items[thread_id])

    def item_requests(self):
        return [u for u in self.urls if "/items/" in u]


class DownSession:
    def get(self, url, timeout=None):
        raise requests.ConnectionError("network is down")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(backfill_hn.time, "sleep", lambda s: None)


def make_data_dir(root: Path) -> Path:
    data = root / "data"
    (data / "raw" / "hn").mkdir(parents=True)
    (data / "taxonomy.json").write_text(json.dumps(TAXONOMY), encoding="utf-8")
    rows = []
    for i in (1, 2, 3):
        (data / "raw" / "hn" / f"{i}.json").write_text(json.dumps(_item(i, OLD[i])), encoding="utf-8")
        rows.append(
            {
                "thread_id": i,
                "month": f"2024-{i:02d}",
                "created_at": CREATED[i].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "title": f"Ask HN: Who is hiring? ({TITLES[i]})",
                "url": backfill_hn.HN_ITEM_URL.format(id=i),
                "n_top_level": len(OLD[i]),
            }
        )
    with (data / "hn_threads.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=backfill_hn.CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    demand.build_demand(
        data / "hn_threads.csv", data / "raw" / "hn", data / "demand_monthly.csv", data / "taxonomy.json",
        ai_context_csv=data / "ai_context_monthly.csv",
    )
    return data


def read_rows(path: Path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def fake_scores(data_dir):
    """Stand-in for build_scores: share of the latest month per skill."""
    rows = read_rows(Path(data_dir) / "demand_monthly.csv")
    last = max(r["month"] for r in rows)
    return {
        "as_of": last,
        "generated_at": "2026-10-22T00:00:00Z",
        "skills": [{"skill": r["skill"], "demand_share_latest": float(r["share"])} for r in rows if r["month"] == last],
    }


@pytest.fixture
def stub_scores(monkeypatch):
    monkeypatch.setattr(refresh_mod, "_run_build_scores", lambda d: (fake_scores(d), False))


# --- fetch_latest_thread ---------------------------------------------------

def test_force_bypasses_cache_and_not_forced_uses_it(tmp_path):
    data = make_data_dir(tmp_path)
    raw_dir = data / "raw" / "hn"
    server = FakeSession(3, {3: _item(3, NEW_3)})

    # force=False: the cached file (2 posts) is used, no item request is made
    tid, month, n, _ = backfill_hn.fetch_latest_thread(force=False, raw_dir=raw_dir, session=server, csv_path=None)
    assert (tid, month, n) == (3, "2024-03", 2)
    assert server.item_requests() == []

    # force=True: the item is downloaded again, the raw file is replaced
    tid, month, n, fetched_at = backfill_hn.fetch_latest_thread(force=True, raw_dir=raw_dir, session=server, csv_path=None)
    assert (tid, month, n) == (3, "2024-03", 5)
    assert len(server.item_requests()) == 1
    assert backfill_hn.count_top_level(json.loads((raw_dir / "3.json").read_text(encoding="utf-8"))) == 5
    assert datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ")


def test_picks_newest_hiring_thread_and_adds_new_month_row(tmp_path):
    data = make_data_dir(tmp_path)
    server = FakeSession(4, {4: _item(4, NEW_4)})
    tid, month, n, _ = backfill_hn.fetch_latest_thread(
        force=True, raw_dir=data / "raw" / "hn", session=server, csv_path=data / "hn_threads.csv"
    )
    assert (tid, month, n) == (4, "2024-04", 2)  # the newer "Freelancer?" hit is ignored
    rows = read_rows(data / "hn_threads.csv")
    assert [r["month"] for r in rows] == ["2024-01", "2024-02", "2024-03", "2024-04"]
    assert rows[-1]["n_top_level"] == "2"


# --- demand.update_months --------------------------------------------------

def test_month_merge_changes_only_target_month(tmp_path):
    data = make_data_dir(tmp_path)
    demand_before = read_rows(data / "demand_monthly.csv")
    ai_before = read_rows(data / "ai_context_monthly.csv")
    (data / "raw" / "hn" / "3.json").write_text(json.dumps(_item(3, NEW_3)), encoding="utf-8")

    out = demand.update_months(
        ["2024-03"], data / "hn_threads.csv", data / "raw" / "hn", data / "demand_monthly.csv",
        ai_context_csv=data / "ai_context_monthly.csv", taxonomy_path=data / "taxonomy.json",
    )
    after = read_rows(data / "demand_monthly.csv")
    assert len(after) == len(demand_before)
    assert [r for r in after if r["month"] != "2024-03"] == [r for r in demand_before if r["month"] != "2024-03"]
    assert out["rows_changed"] == 2 and out["rows_added"] == 0
    assert {r["n_posts"] for r in after if r["month"] == "2024-03"} == {"5"}

    # same result as the slow full rebuild
    full = demand.build_demand(
        data / "hn_threads.csv", data / "raw" / "hn", out_csv=None, taxonomy_path=data / "taxonomy.json"
    )
    for r_full, r_fast in zip(full, after):
        assert (r_fast["month"], r_fast["skill"]) == (r_full["month"], r_full["skill"])
        assert int(r_fast["mentions"]) == r_full["mentions"]
        assert float(r_fast["share"]) == pytest.approx(r_full["share"], abs=1e-6)
        assert float(r_fast["share_smooth"]) == pytest.approx(r_full["share_smooth"], abs=1e-6)

    ai_after = read_rows(data / "ai_context_monthly.csv")
    assert [r for r in ai_after if r["month"] != "2024-03"] == [r for r in ai_before if r["month"] != "2024-03"]
    assert ai_after[-1]["n_posts"] == "5"


def test_month_merge_adds_a_new_month(tmp_path):
    data = make_data_dir(tmp_path)
    before = read_rows(data / "demand_monthly.csv")
    server = FakeSession(4, {4: _item(4, NEW_4)})
    backfill_hn.fetch_latest_thread(force=True, raw_dir=data / "raw" / "hn", session=server, csv_path=data / "hn_threads.csv")
    out = demand.update_months(
        "2024-04", data / "hn_threads.csv", data / "raw" / "hn", data / "demand_monthly.csv",
        taxonomy_path=data / "taxonomy.json",
    )
    after = read_rows(data / "demand_monthly.csv")
    assert out["rows_added"] == 2 and out["rows_changed"] == 0
    assert after[: len(before)] == before
    assert [r["month"] for r in after[len(before):]] == ["2024-04", "2024-04"]


def test_month_merge_needs_a_thread_row(tmp_path):
    data = make_data_dir(tmp_path)
    with pytest.raises(ValueError):
        demand.update_months("2030-01", data / "hn_threads.csv", data / "raw" / "hn", data / "demand_monthly.csv",
                             taxonomy_path=data / "taxonomy.json")


# --- refresh ---------------------------------------------------------------

def test_refresh_updates_thread_demand_and_reports(tmp_path, stub_scores):
    data = make_data_dir(tmp_path)
    (data / "skill_scores.json").write_text(json.dumps(fake_scores(data)), encoding="utf-8")
    server = FakeSession(3, {3: _item(3, NEW_3)})

    result = refresh_mod.refresh(data, source_dir=data, session=server)

    assert result["ok"] is True
    assert result["data_dir"] == str(data)
    assert result["used_temp_dir"] is False
    assert (result["thread_id"], result["month"]) == (3, "2024-03")
    assert (result["posts_before"], result["posts_after"]) == (2, 5)
    assert result["rows_changed"] == 2
    assert result["skills_changed"]["Python"][0] != result["skills_changed"]["Python"][1]
    assert result["scores_updated"] is True and result["duration_s"] >= 0
    assert read_rows(data / "hn_threads.csv")[-1]["n_top_level"] == "5"


def test_read_only_data_dir_falls_back_to_temp_dir(tmp_path, monkeypatch, stub_scores):
    data = make_data_dir(tmp_path)
    committed = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    tmp_root = tmp_path / "tmp"
    tmp_root.mkdir()
    monkeypatch.setattr(refresh_mod, "is_writable", lambda d: Path(d).resolve() != data.resolve())
    server = FakeSession(3, {3: _item(3, NEW_3)})

    # work_dir and source_dir are the read-only folder: the refresh falls back to the temp folder
    result = refresh_mod.refresh(data, source_dir=data, session=server, tmp_root=tmp_root)

    work = tmp_root / "verity_data"
    assert result["ok"] is True
    assert result["data_dir"] == str(work)
    assert result["used_temp_dir"] is True
    assert (work / "taxonomy.json").exists() and not (work / "raw" / "hn" / "1.json").exists()
    assert (work / "raw" / "hn" / "3.json").exists()  # the fetched thread is saved in the temp dir
    assert read_rows(work / "hn_threads.csv")[-1]["n_top_level"] == "5"
    assert {r["n_posts"] for r in read_rows(work / "demand_monthly.csv") if r["month"] == "2024-03"} == {"5"}
    # the committed folder is untouched
    assert {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()} == committed
    assert len(json.loads((data / "raw" / "hn" / "3.json").read_text(encoding="utf-8"))["children"]) == 2


def test_network_failure_keeps_old_data(tmp_path, stub_scores):
    data = make_data_dir(tmp_path)
    (data / "skill_scores.json").write_text(json.dumps(fake_scores(data)), encoding="utf-8")
    snapshot = {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()}

    result = refresh_mod.refresh(data, source_dir=data, session=DownSession())

    assert result["ok"] is False
    assert "gave up" in result["error"] or "network" in result["error"]
    assert result["fallback"]["as_of"] == "2024-03"
    assert {p.relative_to(data): p.read_bytes() for p in data.rglob("*") if p.is_file()} == snapshot


def test_failure_after_fetch_restores_tables(tmp_path, monkeypatch, stub_scores):
    data = make_data_dir(tmp_path)
    threads_before = (data / "hn_threads.csv").read_bytes()
    demand_before = (data / "demand_monthly.csv").read_bytes()

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(demand, "update_months", boom)
    result = refresh_mod.refresh(data, source_dir=data, session=FakeSession(3, {3: _item(3, NEW_3)}))

    assert result["ok"] is False and "disk full" in result["error"]
    assert (data / "hn_threads.csv").read_bytes() == threads_before
    assert (data / "demand_monthly.csv").read_bytes() == demand_before


def test_scores_error_is_reported_but_demand_stays_updated(tmp_path, monkeypatch):
    data = make_data_dir(tmp_path)

    def bad(_):
        raise KeyError("2024-04")

    monkeypatch.setattr(refresh_mod, "_run_build_scores", bad)
    result = refresh_mod.refresh(data, source_dir=data, session=FakeSession(3, {3: _item(3, NEW_3)}))
    assert result["ok"] is True and result["scores_updated"] is False and "KeyError" in result["scores_error"]
    assert {r["n_posts"] for r in read_rows(data / "demand_monthly.csv") if r["month"] == "2024-03"} == {"5"}


# --- refresh with the real build_scores and a temp copy of the real data -------

REAL_DATA = Path(__file__).resolve().parent.parent / "data"


class LatestThreadSession:
    """Fake Algolia: one newest hiring thread with the given posts."""

    def __init__(self, thread_id, title, created, posts):
        self.hit = {"objectID": str(thread_id), "title": title, "created_at_i": int(created.timestamp())}
        self.item = _item(thread_id, posts)

    def get(self, url, timeout=None):
        if "search_by_date" in url:
            return FakeResponse({"hits": [self.hit], "nbPages": 1})
        return FakeResponse(self.item)


def _real_snapshot():
    return {p.name: p.read_bytes() for p in REAL_DATA.iterdir() if p.is_file()}


def _fake_posts(n):
    words = ["Python", "Rust", "Kubernetes", "SQL", "React", "Java"]
    return [f"Co{i} | {words[i % len(words)]} engineer" for i in range(n)]


def test_refresh_in_a_temp_dir_rebuilds_skill_scores_there_with_the_real_engine(tmp_path):
    work = tmp_path / "work"
    snapshot = _real_snapshot()
    latest = read_rows(REAL_DATA / "hn_threads.csv")[-1]
    created = datetime.strptime(latest["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    session = LatestThreadSession(int(latest["thread_id"]), latest["title"], created, _fake_posts(60))

    result = refresh_mod.refresh(work, source_dir=REAL_DATA, session=session)

    assert result["ok"] is True, result
    assert result["scores_updated"] is True and result["scores_error"] is None
    assert result["build_scores_accepts_data_dir"] is True
    assert result["data_dir"] == str(work) and result["posts_after"] == 60
    new = json.loads((work / "skill_scores.json").read_text(encoding="utf-8"))
    assert new["as_of"] == latest["month"]
    python = next(s for s in new["skills"] if s["skill"] == "Python")
    assert result["skills_changed"]["Python"][1] == round(python["demand_share_latest"], 6)
    # the repo data folder was not touched
    assert _real_snapshot() == snapshot


def test_refresh_adds_a_new_month_in_a_temp_dir_and_scores_follow(tmp_path):
    work = tmp_path / "work"
    created = datetime(2026, 11, 1, 15, 0, 0, tzinfo=timezone.utc)
    session = LatestThreadSession(777, "Ask HN: Who is hiring? (November 2026)", created, _fake_posts(40))

    result = refresh_mod.refresh(work, source_dir=REAL_DATA, session=session)

    assert result["ok"] is True, result
    assert result["new_thread"] is True and result["month"] == "2026-11"
    assert result["scores_updated"] is True, result["scores_error"]
    new = json.loads((work / "skill_scores.json").read_text(encoding="utf-8"))
    assert new["as_of"] == "2026-11"
    assert new["data_window"]["to"] == "2026-11"
    assert new["skills"][0]["sources"][2]["date"] == "2026-11-01"


# --- the default work folder is never the committed data folder ------------------------

def test_default_work_dir_is_a_runtime_folder_not_the_source(tmp_path, stub_scores):
    data = make_data_dir(tmp_path)
    committed = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    tmp_root = tmp_path / "tmp"
    tmp_root.mkdir()
    server = FakeSession(3, {3: _item(3, NEW_3)})

    result = refresh_mod.refresh(None, source_dir=data, session=server, tmp_root=tmp_root)

    assert result["ok"] is True
    assert result["data_dir"] == str(tmp_root / "verity_data")
    assert result["committed_data_untouched"] is True
    assert read_rows(tmp_root / "verity_data" / "hn_threads.csv")[-1]["n_top_level"] == "5"
    assert {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()} == committed


def test_runtime_dir_env_variable_is_used(tmp_path, monkeypatch, stub_scores):
    data = make_data_dir(tmp_path)
    target = tmp_path / "runtime"
    monkeypatch.setenv(refresh_mod.RUNTIME_ENV, str(target))
    assert refresh_mod.runtime_dir() == target
    result = refresh_mod.refresh(None, source_dir=data, session=FakeSession(3, {3: _item(3, NEW_3)}))
    assert result["ok"] is True and result["data_dir"] == str(target)
    assert read_rows(target / "demand_monthly.csv")


def test_runtime_dir_falls_back_to_the_system_temp_folder(monkeypatch):
    monkeypatch.delenv(refresh_mod.RUNTIME_ENV, raising=False)
    import tempfile

    assert refresh_mod.runtime_dir() == Path(tempfile.gettempdir()) / "verity_data"


def test_runtime_dir_equal_to_the_committed_folder_is_refused(tmp_path, monkeypatch, stub_scores):
    data = make_data_dir(tmp_path)
    monkeypatch.setenv(refresh_mod.RUNTIME_ENV, str(data))
    result = refresh_mod.refresh(None, source_dir=data, session=FakeSession(3, {3: _item(3, NEW_3)}))
    assert result["ok"] is False and "committed data folder" in result["error"]


def test_a_second_refresh_while_one_runs_returns_busy(tmp_path):
    assert refresh_mod._LOCK.acquire(blocking=False)
    try:
        result = refresh_mod.refresh(tmp_path)
    finally:
        refresh_mod._LOCK.release()
    assert result == {"ok": False, "busy": True, "error": "a refresh is already running"}
