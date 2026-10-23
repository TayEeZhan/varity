"""Tests for engine.store (snapshot store), engine.live.

No network and no Replit: LocalStore is a folder, and ReplitStore is tested against a
fake `replit.object_storage` package that keeps objects in a dict.
"""
import json
import shutil
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from conftest import write_data_folder

import engine.refresh
from engine import live, store
from engine.store import LocalStore, ReplitStore, StoreError, get_store

ROOT = Path(__file__).resolve().parent.parent
T0 = datetime(2026, 10, 22, 1, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def local(tmp_path) -> LocalStore:
    return LocalStore(tmp_path / "bucket")


# --- LocalStore: save, load, layout -----------------------------------------------------

def test_save_then_load_latest_roundtrip(local, data_folder, tmp_path):
    sid = local.save_snapshot(data_folder, {"fetched_at": "2026-10-22T00:59:00Z", "posts_before": 3,
                                            "posts_after": 5, "thread_id": 42}, now=T0)
    assert sid == "20261022T010000Z"
    target = tmp_path / "out"
    meta = local.load_latest(target)
    for name in ("skill_scores.json", "demand_monthly.csv", "hn_threads.csv", "ai_context_monthly.csv"):
        assert (target / name).read_bytes() == (data_folder / name).read_bytes()
    assert meta["snapshot_id"] == sid
    assert (meta["fetched_at"], meta["posts_before"], meta["posts_after"], meta["thread_id"]) == (
        "2026-10-22T00:59:00Z", 3, 5, 42)
    assert meta["generated_at"] == "2026-10-22T01:00:00Z" and meta["as_of"] == "2026-10"
    assert meta["saved_at"] == "2026-10-22T01:00:00Z"
    assert "commit" in meta  # a hash when git is available, else None
    assert meta["files"] == sorted(["skill_scores.json", "demand_monthly.csv", "hn_threads.csv",
                                    "ai_context_monthly.csv"])


def test_layout_has_snapshot_folder_meta_and_latest_pointer(local, data_folder):
    sid = local.save_snapshot(data_folder, {}, now=T0)
    keys = {p.relative_to(local.root).as_posix() for p in local.root.rglob("*") if p.is_file()}
    assert keys == {f"snapshots/{sid}/{n}" for n in (
        "skill_scores.json", "demand_monthly.csv", "hn_threads.csv", "ai_context_monthly.csv", "meta.json")
    } | {"latest.json"}
    assert json.loads((local.root / "latest.json").read_text())["snapshot_id"] == sid


def test_ai_context_file_is_optional(local, data_folder, tmp_path):
    (data_folder / "ai_context_monthly.csv").unlink()
    local.save_snapshot(data_folder, {}, now=T0)
    meta = local.load_latest(tmp_path / "out")
    assert "ai_context_monthly.csv" not in meta["files"]
    assert not (tmp_path / "out" / "ai_context_monthly.csv").exists()


def test_empty_store_has_no_latest(local, tmp_path):
    assert local.latest_meta() is None
    assert local.load_latest(tmp_path / "out") is None
    assert not (tmp_path / "out").exists()


def test_latest_pointer_moves_to_the_newest_snapshot(local, data_folder, tmp_path):
    first = local.save_snapshot(data_folder, {}, now=T0)
    write_data_folder(data_folder, generated_at="2026-10-23T01:00:00Z", marker="b")
    second = local.save_snapshot(data_folder, {}, now=T0 + timedelta(days=1))
    assert local.latest_meta()["snapshot_id"] == second != first
    assert local.snapshot_ids() == [first, second]
    local.load_latest(tmp_path / "out")
    assert json.loads((tmp_path / "out" / "skill_scores.json").read_text())["marker"] == "b"


def test_two_saves_in_the_same_second_get_different_ids(local, data_folder):
    a = local.save_snapshot(data_folder, {}, now=T0)
    b = local.save_snapshot(data_folder, {}, now=T0)
    assert a != b and local.snapshot_ids() == [a, b]
    assert local.latest_meta()["snapshot_id"] == b


def test_retention_keeps_the_newest_14(local, data_folder):
    ids = [local.save_snapshot(data_folder, {}, now=T0 + timedelta(days=i)) for i in range(17)]
    kept = local.snapshot_ids()
    assert kept == ids[-14:]
    assert local.latest_meta()["snapshot_id"] == ids[-1]
    for old in ids[:3]:
        assert not (local.root / "snapshots" / old).exists()  # files and folder are gone
    assert len(list((local.root / "snapshots").iterdir())) == 14


def test_a_failed_upload_keeps_the_previous_latest(local, data_folder, monkeypatch):
    good = local.save_snapshot(data_folder, {}, now=T0)
    write_data_folder(data_folder, marker="bad")
    real_put = LocalStore._put
    calls = []

    def flaky_put(self, key, data):
        calls.append(key)
        if key.endswith("demand_monthly.csv"):
            raise OSError("disk full")
        real_put(self, key, data)

    monkeypatch.setattr(LocalStore, "_put", flaky_put)
    with pytest.raises(OSError, match="disk full"):
        local.save_snapshot(data_folder, {}, now=T0 + timedelta(days=1))
    assert "latest.json" not in calls[-2:] and local.latest_meta()["snapshot_id"] == good


def test_saving_needs_the_required_files_and_valid_scores(local, data_folder):
    (data_folder / "hn_threads.csv").unlink()
    with pytest.raises(StoreError, match="hn_threads.csv"):
        local.save_snapshot(data_folder, {})
    write_data_folder(data_folder)
    (data_folder / "skill_scores.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError, match="not valid JSON"):
        local.save_snapshot(data_folder, {})
    assert local.latest_meta() is None and local.snapshot_ids() == []


def test_loading_an_incomplete_snapshot_writes_nothing(local, data_folder, tmp_path):
    sid = local.save_snapshot(data_folder, {}, now=T0)
    (local.root / "snapshots" / sid / "demand_monthly.csv").unlink()
    target = tmp_path / "out"
    with pytest.raises(StoreError, match="demand_monthly.csv"):
        local.load_latest(target)
    assert not target.exists()


@pytest.mark.parametrize("bad", ["../escape", "snapshots/x", "", "2026-10-22"])
def test_load_snapshot_rejects_bad_ids(local, tmp_path, bad):
    with pytest.raises(StoreError, match="bad snapshot id"):
        local.load_snapshot(bad, tmp_path / "out")


def test_a_broken_latest_pointer_is_a_store_error(local):
    (local.root).mkdir(parents=True)
    (local.root / "latest.json").write_text("{nope", encoding="utf-8")
    with pytest.raises(StoreError, match="not valid JSON"):
        local.latest_meta()
    (local.root / "latest.json").write_text(json.dumps({"snapshot_id": "../../x"}), encoding="utf-8")
    with pytest.raises(StoreError, match="does not name a snapshot"):
        local.latest_meta()


# --- choosing a backend -----------------------------------------------------------------

def test_get_store_is_local_off_replit(tmp_path):
    s = get_store()
    assert isinstance(s, LocalStore) and s.root == tmp_path / "store" and not s.durable


@pytest.fixture
def no_replit_package(monkeypatch):
    """Make `import replit.object_storage` fail, whatever is installed."""
    monkeypatch.setitem(sys.modules, "replit", None)
    monkeypatch.setitem(sys.modules, "replit.object_storage", None)


@pytest.mark.parametrize("variable, value", [("REPL_ID", "abc"), ("REPLIT_DEPLOYMENT", "1"), ("VERITY_STORE", "replit")])
def test_replit_import_failure_falls_back_to_local_store(monkeypatch, no_replit_package, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(StoreError, match="not installed"):
        ReplitStore()
    assert isinstance(get_store(), LocalStore)


def test_strict_get_store_raises_instead_of_falling_back(monkeypatch, no_replit_package):
    monkeypatch.setenv("REPL_ID", "abc")
    with pytest.raises(StoreError, match="not usable"):
        get_store(strict=True)


def test_verity_store_local_overrides_replit_detection(monkeypatch):
    monkeypatch.setenv("REPL_ID", "abc")
    monkeypatch.setenv("VERITY_STORE", "local")
    assert isinstance(get_store(strict=True), LocalStore)


class _FakeObject:
    def __init__(self, name):
        self.name = name


def _install_fake_replit(monkeypatch, objects: dict, fail_probe: bool = False):
    """A stand-in for the replit-object-storage package that uses the same calls as the real one."""
    class ObjectNotFoundError(Exception):
        pass

    class Client:
        def __init__(self, bucket_id=None):
            self.bucket_id = bucket_id
            Client.last = self

        def list(self, prefix=None, max_results=None, **_):
            if fail_probe:
                raise RuntimeError("no default bucket")
            names = sorted(k for k in objects if k.startswith(prefix or ""))
            return [_FakeObject(n) for n in names[:max_results]]

        def upload_from_bytes(self, name, data):
            objects[name] = bytes(data)

        def download_as_bytes(self, name):
            try:
                return objects[name]
            except KeyError:
                raise ObjectNotFoundError(name) from None

        def delete(self, name, ignore_not_found=False):
            if name not in objects and not ignore_not_found:
                raise ObjectNotFoundError(name)
            objects.pop(name, None)

    pkg, mod, errors = types.ModuleType("replit"), types.ModuleType("replit.object_storage"), types.ModuleType(
        "replit.object_storage.errors")
    mod.Client, errors.ObjectNotFoundError = Client, ObjectNotFoundError
    pkg.object_storage, mod.errors = mod, errors
    monkeypatch.setitem(sys.modules, "replit", pkg)
    monkeypatch.setitem(sys.modules, "replit.object_storage", mod)
    monkeypatch.setitem(sys.modules, "replit.object_storage.errors", errors)
    return Client


def test_replit_store_uses_the_client_api_end_to_end(monkeypatch, data_folder, tmp_path):
    objects: dict = {}
    client_cls = _install_fake_replit(monkeypatch, objects)
    s = ReplitStore("my-bucket")
    assert s.durable and client_cls.last.bucket_id == "my-bucket"
    ids = [s.save_snapshot(data_folder, {"fetched_at": "x"}, now=T0 + timedelta(days=i)) for i in range(16)]
    assert s.snapshot_ids() == ids[-14:]
    assert "latest.json" in objects and not any(ids[0] in k for k in objects)
    meta = s.load_latest(tmp_path / "out")
    assert meta["snapshot_id"] == ids[-1] and (tmp_path / "out" / "skill_scores.json").is_file()


def test_get_store_returns_replit_store_on_replit(monkeypatch):
    _install_fake_replit(monkeypatch, {})
    monkeypatch.setenv("REPL_ID", "abc")
    monkeypatch.setenv("VERITY_BUCKET", "b1")
    s = get_store(strict=True)
    assert isinstance(s, ReplitStore)


def test_replit_store_with_an_unreachable_bucket_falls_back(monkeypatch):
    _install_fake_replit(monkeypatch, {}, fail_probe=True)
    monkeypatch.setenv("REPL_ID", "abc")
    with pytest.raises(StoreError, match="cannot reach the Replit bucket"):
        ReplitStore()
    assert isinstance(get_store(), LocalStore)
    with pytest.raises(StoreError):
        get_store(strict=True)


# --- engine.live ------------------------------------------------------------------------

def test_is_newer_compares_generated_at():
    assert live.is_newer({"generated_at": "2026-10-23T00:00:00Z"}, "2026-10-22T00:00:00Z")
    assert not live.is_newer({"generated_at": "2026-10-22T00:00:00Z"}, "2026-10-22T00:00:00Z")
    assert not live.is_newer({"generated_at": "2026-10-21T00:00:00Z"}, "2026-10-22T00:00:00Z")
    assert live.is_newer({"fetched_at": "2026-10-23T00:00:00Z"}, "2026-10-22T00:00:00Z")  # no generated_at
    assert not live.is_newer({"generated_at": "garbage"}, "2026-10-22T00:00:00Z")
    assert not live.is_newer({}, None)


def _committed_copy(tmp_path) -> Path:
    committed = tmp_path / "committed"
    write_data_folder(committed, generated_at="2026-10-21T00:00:00Z", marker="committed")
    (committed / "taxonomy.json").write_text("{}", encoding="utf-8")
    return committed


def test_load_newer_snapshot_downloads_once_and_seeds_other_files(local, tmp_path, data_folder):
    committed = _committed_copy(tmp_path)
    assert live.load_newer_snapshot(committed, store=local) is None  # empty store
    local.save_snapshot(data_folder, {"fetched_at": "2026-10-22T00:59:00Z"}, now=T0)
    root = tmp_path / "live_root"
    folder = live.load_newer_snapshot(committed, store=local, root=root)
    assert Path(folder).parent == root
    assert json.loads((Path(folder) / "skill_scores.json").read_text())["marker"] == "a"
    assert (Path(folder) / "taxonomy.json").is_file()  # build_scores inputs are copied from the committed data
    assert live.folder_meta(folder)["fetched_at"] == "2026-10-22T00:59:00Z"
    assert live.folder_meta(committed) is None
    calls = []
    real = LocalStore._get
    LocalStore._get = lambda self, key: calls.append(key) or real(self, key)
    try:
        assert live.load_newer_snapshot(committed, store=local, root=root) == folder
    finally:
        LocalStore._get = real
    assert calls == ["latest.json"]  # the second call reads only the pointer


def test_load_newer_snapshot_ignores_an_older_snapshot_and_a_missing_committed_file(local, tmp_path):
    older = write_data_folder(tmp_path / "older", generated_at="2026-10-20T00:00:00Z")
    local.save_snapshot(older, {}, now=T0)
    assert live.load_newer_snapshot(_committed_copy(tmp_path), store=local, root=tmp_path / "r") is None
    assert live.load_newer_snapshot(tmp_path / "nowhere", store=local, root=tmp_path / "r") is None


def test_publish_saves_a_good_refresh_and_never_raises(local, data_folder):
    result = {"ok": True, "data_dir": str(data_folder), "scores_updated": True, "fetched_at": "t",
              "posts_before": 1, "posts_after": 2}
    assert "this machine only" in live.publish(result, store=local)
    assert local.latest_meta()["source"] == "manual" and local.latest_meta()["posts_after"] == 2
    assert live.publish({"ok": False, "error": "x"}, store=local) is None
    assert live.publish({**result, "scores_updated": False}, store=local) is None
    assert live.publish({**result, "data_dir": "/no/such/folder"}, store=local).startswith("Not saved")
