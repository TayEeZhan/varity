"""Tests for engine.scheduled (the daily job). refresh() is replaced; no network, no Replit."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import write_data_folder

import engine.refresh
from engine import scheduled, store
from engine.store import LocalStore

T0 = datetime(2026, 10, 22, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def local(tmp_path) -> LocalStore:
    return LocalStore(tmp_path / "bucket")


def _good_result(folder) -> dict:
    return {"ok": True, "data_dir": str(folder), "thread_id": 49922569, "month": "2026-10",
            "posts_before": 266, "posts_after": 271, "fetched_at": "2026-10-22T01:00:05Z",
            "scores_updated": True, "scores_error": None}


def test_success_saves_a_snapshot_and_reports_it(monkeypatch, local, data_folder):
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: _good_result(data_folder))
    summary = scheduled.run(store=local)
    assert summary["ok"] is True and summary["store"] == "local"
    assert summary["snapshot_id"] == local.latest_meta()["snapshot_id"]
    assert (summary["fetched_at"], summary["posts_before"], summary["posts_after"], summary["thread_id"]) == (
        "2026-10-22T01:00:05Z", 266, 271, 49922569)
    assert summary["snapshots_kept"] == 1 and summary["duration_s"] >= 0
    meta = local.latest_meta()
    assert meta["source"] == "scheduled" and meta["generated_at"] == "2026-10-22T01:00:00Z"


def test_refresh_arguments_are_passed_on(monkeypatch, local, data_folder):
    seen = {}
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: seen.update(kw) or _good_result(data_folder))
    scheduled.run(store=local, work_dir="somewhere")
    assert seen == {"work_dir": "somewhere", "source_dir": None}  # empty store: start from the committed data


def test_the_job_starts_from_the_last_stored_snapshot(monkeypatch, local, data_folder):
    seen = {}
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: seen.update(kw) or _good_result(data_folder))
    monkeypatch.setattr(scheduled.live, "load_newer_snapshot", lambda committed, store: "/live/snap-1")
    scheduled.run(store=local)
    assert seen["source_dir"] == "/live/snap-1"  # months and ledger rows since the last commit are kept


@pytest.mark.parametrize("bad, stage, text", [
    ({"ok": False, "error": "URLError: network is down"}, "refresh", "network is down"),
    ({"ok": False, "busy": True, "error": "a refresh is already running"}, "refresh", "already running"),
    ({"ok": True, "data_dir": "x", "scores_updated": False, "scores_error": "KeyError: boom"}, "refresh",
     "scores were not rebuilt: KeyError: boom"),
])
def test_a_failed_refresh_keeps_the_previous_latest(monkeypatch, local, data_folder, bad, stage, text):
    previous = local.save_snapshot(data_folder, {}, now=T0)
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: bad)
    summary = scheduled.run(store=local)
    assert summary["ok"] is False and summary["stage"] == stage and text in summary["error"]
    assert local.latest_meta()["snapshot_id"] == previous and local.snapshot_ids() == [previous]


def test_a_refresh_that_raises_is_a_failure_not_a_crash(monkeypatch, local):
    def boom(**kw):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(engine.refresh, "refresh", boom)
    summary = scheduled.run(store=local)
    assert summary == {**summary, "ok": False, "stage": "refresh", "error": "RuntimeError: unexpected"}
    assert local.latest_meta() is None


def test_a_failed_save_keeps_the_previous_latest(monkeypatch, local, data_folder):
    previous = local.save_snapshot(data_folder, {}, now=T0)
    write_data_folder(data_folder, generated_at="2026-10-23T01:00:00Z", marker="new")
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: _good_result(data_folder))
    real_put = LocalStore._put

    def failing_put(self, key, data):
        if key.endswith("hn_threads.csv"):
            raise OSError("bucket unavailable")
        real_put(self, key, data)

    monkeypatch.setattr(LocalStore, "_put", failing_put)
    summary = scheduled.run(store=local)
    assert summary["ok"] is False and summary["stage"] == "save" and "bucket unavailable" in summary["error"]
    assert local.latest_meta()["snapshot_id"] == previous


def test_main_prints_one_json_line_and_exits_0(monkeypatch, capsys, tmp_path, data_folder):
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: _good_result(data_folder))
    assert scheduled.main() == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    summary = json.loads(out[0])
    assert summary["ok"] is True
    assert store.get_store().latest_meta()["snapshot_id"] == summary["snapshot_id"]  # VERITY_STORE_DIR in conftest


def test_main_exits_1_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: {"ok": False, "error": "no network"})
    assert scheduled.main() == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["ok"] is False


def test_on_replit_without_app_storage_the_job_fails_loudly(monkeypatch, capsys):
    """A save to a disk that Replit throws away would look like success, so the job must stop."""
    import sys

    monkeypatch.setenv("REPL_ID", "abc")
    monkeypatch.setitem(sys.modules, "replit", None)
    monkeypatch.setitem(sys.modules, "replit.object_storage", None)
    called = []
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: called.append(1))
    assert scheduled.main() == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["stage"] == "store" and "not usable" in summary["error"]
    assert called == []  # no network work is done when the result could not be saved


def test_retention_applies_to_scheduled_runs(monkeypatch, local, data_folder):
    monkeypatch.setattr(engine.refresh, "refresh", lambda **kw: _good_result(data_folder))
    for i in range(16):
        local.save_snapshot(data_folder, {}, now=T0 + timedelta(days=i))
    assert scheduled.run(store=local)["snapshots_kept"] == 14
