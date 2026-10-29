"""Snapshot store: keeps the latest refreshed data where every server can read it.

On Replit Autoscale each instance has its own short-lived disk, so a refresh made
on one instance is lost on restart and never seen by the others. This module saves
a refresh result ("snapshot") in a place that all instances share.

    from engine.store import get_store
    store = get_store()
    sid = store.save_snapshot(data_dir, meta)    # after a good refresh
    meta = store.load_latest(some_folder)        # in the app; None when nothing is stored

Two backends share one interface (SnapshotStore):

* LocalStore(root): a folder on this machine. Tests and local runs.
* ReplitStore(bucket=None): Replit App Storage (Object Storage), through the
  official `replit-object-storage` package. That package is imported only when a
  ReplitStore is created, so local runs and tests need no Replit package.

Layout (the same keys in both backends)

    snapshots/<UTC timestamp>/skill_scores.json
                              demand_monthly.csv
                              hn_threads.csv
                              ai_context_monthly.csv   (only if the file exists)
                              meta.json
    latest.json                  <- meta of the newest snapshot, written LAST

A snapshot is uploaded completely first and latest.json is switched at the end, so
a reader never sees a half-written snapshot. If an upload fails, latest.json still
points to the previous good snapshot. The newest KEEP_SNAPSHOTS snapshots are kept.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("verity.store")

ROOT = Path(__file__).resolve().parent.parent

KEEP_SNAPSHOTS = 14
SNAPSHOT_PREFIX = "snapshots/"
LATEST_KEY = "latest.json"
META_NAME = "meta.json"
REQUIRED_FILES = ("skill_scores.json", "demand_monthly.csv", "hn_threads.csv")
OPTIONAL_FILES = ("ai_context_monthly.csv", "role_demand_monthly.csv", "role_trends.json",
                  "role_backtest.json", "role_forecast.json")
STORE_DIR_ENV = "VERITY_STORE_DIR"
STORE_KIND_ENV = "VERITY_STORE"      # "replit" or "local" forces the choice
BUCKET_ENV = "VERITY_BUCKET"         # optional bucket id; default is the app's default bucket
_SNAPSHOT_ID = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")


class StoreError(Exception):
    """The store is unusable, or a snapshot in it is broken."""


# --------------------------------------------------------------------------------------
# Shared logic
# --------------------------------------------------------------------------------------

class SnapshotStore:
    """Snapshot logic on top of four byte-level operations that a backend supplies."""

    name = "base"
    durable = False  # True when the data outlives this machine (a shared bucket)

    # -- backend operations -----------------------------------------------------------
    def _put(self, key: str, data: bytes) -> None:
        raise NotImplementedError

    def _get(self, key: str) -> bytes | None:
        """The bytes stored under `key`, or None when the key does not exist."""
        raise NotImplementedError

    def _list(self, prefix: str) -> list[str]:
        raise NotImplementedError

    def _delete(self, key: str) -> None:
        raise NotImplementedError

    # -- public API -------------------------------------------------------------------
    def snapshot_ids(self) -> list[str]:
        """Ids of all stored snapshots, oldest first."""
        ids = set()
        for key in self._list(SNAPSHOT_PREFIX):
            parts = key[len(SNAPSHOT_PREFIX):].split("/", 1)
            if len(parts) == 2 and _SNAPSHOT_ID.match(parts[0]):
                ids.add(parts[0])
        return sorted(ids)

    def latest_meta(self) -> dict | None:
        """Meta of the newest snapshot (contains "snapshot_id"), or None when there is none."""
        raw = self._get(LATEST_KEY)
        if raw is None:
            return None
        try:
            meta = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StoreError(f"{LATEST_KEY} is not valid JSON: {exc}") from exc
        if not isinstance(meta, dict) or not _SNAPSHOT_ID.match(str(meta.get("snapshot_id", ""))):
            raise StoreError(f"{LATEST_KEY} does not name a snapshot")
        return meta

    def save_snapshot(self, data_dir: str | Path, meta: dict | None = None, *,
                      now: datetime | None = None, keep: int = KEEP_SNAPSHOTS) -> str:
        """Upload the data files of `data_dir` as a new snapshot and make it the latest.

        `meta` is the caller's facts about the refresh (fetched_at, posts_before,
        posts_after, thread_id, ...). The store adds snapshot_id, saved_at, files,
        generated_at (from skill_scores.json) and the code commit when git can tell.
        Returns the snapshot id. Raises StoreError (or a backend error) on failure;
        then latest.json is unchanged.
        """
        folder = Path(data_dir)
        payload: dict[str, bytes] = {}
        for name in REQUIRED_FILES:
            path = folder / name
            if not path.is_file():
                raise StoreError(f"cannot save a snapshot: {path} is missing")
            payload[name] = path.read_bytes()
        for name in OPTIONAL_FILES:
            if (folder / name).is_file():
                payload[name] = (folder / name).read_bytes()
        try:
            scores = json.loads(payload["skill_scores.json"].decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StoreError(f"cannot save a snapshot: skill_scores.json is not valid JSON ({exc})") from exc

        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        snapshot_id = self._new_id(moment)
        full_meta = {
            **(meta or {}),
            "snapshot_id": snapshot_id,
            "saved_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_at": scores.get("generated_at"),
            "as_of": scores.get("as_of"),
            "commit": _git_commit(),
            "files": sorted(payload),
        }
        base = f"{SNAPSHOT_PREFIX}{snapshot_id}/"
        for name, data in payload.items():
            self._put(base + name, data)
        meta_bytes = json.dumps(full_meta, indent=2, sort_keys=True).encode("utf-8")
        self._put(base + META_NAME, meta_bytes)
        self._put(LATEST_KEY, meta_bytes)  # last: readers switch only to a complete snapshot
        self._prune(keep)
        return snapshot_id

    def load_snapshot(self, snapshot_id: str, into_dir: str | Path) -> dict:
        """Download one snapshot into `into_dir` (created if needed) and return its meta.

        All files are downloaded and checked before any file is written, and each
        file is written atomically, so a failure never leaves a broken scores file.
        """
        if not _SNAPSHOT_ID.match(snapshot_id):
            raise StoreError(f"bad snapshot id: {snapshot_id!r}")
        base = f"{SNAPSHOT_PREFIX}{snapshot_id}/"
        raw_meta = self._get(base + META_NAME)
        if raw_meta is None:
            raise StoreError(f"snapshot {snapshot_id} has no {META_NAME}")
        try:
            meta = json.loads(raw_meta.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StoreError(f"snapshot {snapshot_id}: {META_NAME} is not valid JSON") from exc
        files = {}
        for name in REQUIRED_FILES + OPTIONAL_FILES:
            data = self._get(base + name)
            if data is None and name in REQUIRED_FILES:
                raise StoreError(f"snapshot {snapshot_id} is incomplete: {name} is missing")
            if data is not None:
                files[name] = data
        try:
            json.loads(files["skill_scores.json"].decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise StoreError(f"snapshot {snapshot_id}: skill_scores.json is not valid JSON") from exc
        target = Path(into_dir)
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            _atomic_write(target / name, data)
        return meta

    def load_latest(self, into_dir: str | Path) -> dict | None:
        """Download the latest snapshot into `into_dir`. Return its meta, or None if the store is empty."""
        latest = self.latest_meta()
        if latest is None:
            return None
        return self.load_snapshot(latest["snapshot_id"], into_dir)

    # -- helpers ----------------------------------------------------------------------
    def _new_id(self, moment: datetime) -> str:
        base = moment.strftime("%Y%m%dT%H%M%SZ")
        taken = set(self.snapshot_ids())
        candidate, n = base, 1
        while candidate in taken:  # two saves in the same second
            n += 1
            candidate = f"{base}-{n}"
        return candidate

    def _prune(self, keep: int) -> list[str]:
        """Delete all but the newest `keep` snapshots. A failure here never fails the save."""
        removed: list[str] = []
        try:
            ids = self.snapshot_ids()
            for old in ids[:-keep] if keep > 0 else []:
                for key in self._list(f"{SNAPSHOT_PREFIX}{old}/"):
                    self._delete(key)
                removed.append(old)
        except Exception as exc:  # noqa: BLE001 - retention is housekeeping
            log.warning("could not prune old snapshots: %s", exc)
        return removed


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _git_commit() -> str | None:
    """Short hash of the code this runs from, or None when git is not available."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


# --------------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------------

class LocalStore(SnapshotStore):
    """A folder on this machine. Same keys as the bucket, as files."""

    name = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise StoreError(f"key escapes the store folder: {key!r}")
        return path

    def _put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, data)

    def _get(self, key: str) -> bytes | None:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            return None

    def _list(self, prefix: str) -> list[str]:
        if not self.root.is_dir():
            return []
        keys = (p.relative_to(self.root).as_posix() for p in self.root.rglob("*") if p.is_file())
        return sorted(k for k in keys if k.startswith(prefix) and not k.endswith(".tmp"))

    def _delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        try:  # remove the snapshot folder when it is empty
            path.parent.rmdir()
        except OSError:
            pass


class ReplitStore(SnapshotStore):
    """Replit App Storage (Object Storage) through the `replit-object-storage` package.

    `bucket` is a bucket id; None means the app's default bucket. Creating the object
    imports the package and checks that the bucket answers, so a wrong setup fails here,
    not in the middle of a save.
    """

    name = "replit"
    durable = True

    def __init__(self, bucket: str | None = None):
        try:
            from replit.object_storage import Client
            from replit.object_storage.errors import ObjectNotFoundError
        except ImportError as exc:
            raise StoreError("the replit-object-storage package is not installed") from exc
        self._not_found = ObjectNotFoundError
        self._client = Client(bucket_id=bucket) if bucket else Client()
        try:
            self._client.list(prefix=SNAPSHOT_PREFIX, max_results=1)  # probe: bucket reachable
        except Exception as exc:
            raise StoreError(f"cannot reach the Replit bucket: {type(exc).__name__}: {exc}") from exc

    def _put(self, key: str, data: bytes) -> None:
        self._client.upload_from_bytes(key, data)

    def _get(self, key: str) -> bytes | None:
        try:
            return self._client.download_as_bytes(key)
        except self._not_found:
            return None

    def _list(self, prefix: str) -> list[str]:
        return sorted(obj.name for obj in self._client.list(prefix=prefix))

    def _delete(self, key: str) -> None:
        self._client.delete(key, ignore_not_found=True)


# --------------------------------------------------------------------------------------
# Choosing a backend
# --------------------------------------------------------------------------------------

def on_replit() -> bool:
    """True when the Replit environment variables say this process runs on Replit."""
    kind = os.environ.get(STORE_KIND_ENV, "").strip().lower()
    if kind:
        return kind == "replit"
    return bool(os.environ.get("REPL_ID") or os.environ.get("REPLIT_DEPLOYMENT"))


def local_store_dir() -> Path:
    return Path(os.environ.get(STORE_DIR_ENV) or Path(tempfile.gettempdir()) / "verity_store")


def get_store(strict: bool = False) -> SnapshotStore:
    """ReplitStore on Replit, else LocalStore(VERITY_STORE_DIR or <tempdir>/verity_store).

    If Replit is detected but the bucket cannot be used (package missing, no bucket
    attached), a LocalStore is returned and a warning is logged. With strict=True a
    StoreError is raised instead: the scheduled job uses this, because a "successful"
    save to a disk that is thrown away would hide the problem.
    """
    if on_replit():
        try:
            return ReplitStore(os.environ.get(BUCKET_ENV) or None)
        except Exception as exc:  # noqa: BLE001 - any setup problem means "no bucket"
            if strict:
                raise StoreError(f"Replit App Storage is not usable: {exc}") from exc
            log.warning("Replit App Storage is not usable (%s); using a local folder", exc)
    return LocalStore(local_store_dir())
