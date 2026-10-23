"""Bridge between the shared snapshot store (engine.store) and the Streamlit app.

The app calls this module in three places and nothing else:

    live.start_dir(committed_dir)   -> folder with the latest stored data, or None
    live.publish(refresh_result)    -> save a manual refresh so every visitor sees it
    live.banner(folder, committed)  -> the banner text for a folder from start_dir

start_dir() asks the store for latest.json (one small read). If that snapshot is newer
than the committed data/skill_scores.json, it is downloaded once into a runtime folder
<runtime>/verity_live/<snapshot id>/ (the committed files that build_scores also needs,
such as taxonomy.json, are copied there first). The result is cached for 10 minutes, so
the store is not read on every Streamlit rerun. Any store problem returns None, and the
app then shows the committed data.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from engine.store import SnapshotStore, get_store

log = logging.getLogger("verity.live")

ROOT = Path(__file__).resolve().parent.parent
SCORES_NAME = "skill_scores.json"
LIVE_META_NAME = "live_meta.json"     # written into a live folder; marks it as a store snapshot
LIVE_DIR_ENV = "VERITY_LIVE_DIR"
CACHE_SECONDS = 600
KEEP_LOCAL_FOLDERS = 3


def live_root() -> Path:
    """Where downloaded snapshots go: $VERITY_LIVE_DIR, else <tempdir>/verity_live."""
    return Path(os.environ.get(LIVE_DIR_ENV) or Path(tempfile.gettempdir()) / "verity_live")


def _parse(stamp) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def committed_generated_at(committed_dir: str | Path) -> str | None:
    """generated_at of the committed scores file, or None when it is missing or unreadable."""
    try:
        return json.loads((Path(committed_dir) / SCORES_NAME).read_text(encoding="utf-8")).get("generated_at")
    except (OSError, ValueError):
        return None


def is_newer(meta: dict, committed_at: str | None) -> bool:
    """True when the stored snapshot was generated after the committed one."""
    stored = _parse(meta.get("generated_at") or meta.get("fetched_at"))
    if stored is None:
        return False
    committed = _parse(committed_at) if committed_at else None
    return committed is None or stored > committed


def load_newer_snapshot(committed_dir: str | Path, *, store: SnapshotStore | None = None,
                        root: Path | None = None) -> str | None:
    """Folder holding the latest stored snapshot if it is newer than the committed data, else None.

    Raises on store errors; start_dir() is the version that never raises.
    """
    committed = Path(committed_dir)
    committed_at = committed_generated_at(committed)
    if committed_at is None:  # no committed scores: the app shows its sample data, keep it so
        return None
    store = store if store is not None else get_store()
    meta = store.latest_meta()
    if meta is None or not is_newer(meta, committed_at):
        return None
    base = (root if root is not None else live_root())
    target = base / meta["snapshot_id"]
    if not (target / LIVE_META_NAME).is_file():
        from engine.refresh import seed_work_dir

        shutil.rmtree(target, ignore_errors=True)     # an unfinished folder from an earlier crash
        base.mkdir(parents=True, exist_ok=True)
        stage = base / (meta["snapshot_id"] + ".part")
        shutil.rmtree(stage, ignore_errors=True)
        seed_work_dir(committed, stage)               # taxonomy, exposure, backtest ...
        loaded = store.load_snapshot(meta["snapshot_id"], stage)  # ... then the refreshed files
        (stage / LIVE_META_NAME).write_text(json.dumps(loaded, indent=2), encoding="utf-8")
        try:
            os.replace(stage, target)
        except OSError:  # another session finished the same folder first
            shutil.rmtree(stage, ignore_errors=True)
        _prune_folders(base, keep=KEEP_LOCAL_FOLDERS, current=target)
    return str(target)


def _prune_folders(base: Path, keep: int, current: Path) -> None:
    folders = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.endswith(".part"))
    for old in folders[:-keep]:
        if old != current:
            shutil.rmtree(old, ignore_errors=True)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def _cached_start_dir(committed_dir: str) -> str | None:
    try:
        return load_newer_snapshot(committed_dir)
    except Exception as exc:  # noqa: BLE001 - the store must never break the app
        log.warning("could not read the shared store: %s: %s", type(exc).__name__, exc)
        return None


def start_dir(committed_dir: str | Path) -> str | None:
    """Folder with newer stored data (cached for 10 minutes), or None to use the committed data."""
    folder = _cached_start_dir(str(committed_dir))
    if folder is not None and not (Path(folder) / LIVE_META_NAME).is_file():
        _cached_start_dir.clear()  # the folder was cleaned up since it was cached
        folder = _cached_start_dir(str(committed_dir))
    return folder


def reload(committed_dir: str | Path) -> str | None:
    """Forget the cached answer and ask the store again (the "Reload data" button)."""
    _cached_start_dir.clear()
    return start_dir(committed_dir)


def folder_meta(folder: str | Path | None) -> dict | None:
    """Meta of the snapshot in a folder made by start_dir(), or None for any other folder."""
    if not folder:
        return None
    try:
        return json.loads((Path(folder) / LIVE_META_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def banner(meta: dict, committed_at: str | None) -> str:
    who = "scheduled job" if meta.get("source", "scheduled") == "scheduled" else "Refresh click by a visitor"
    return (f"Data refreshed automatically on {meta.get('fetched_at') or 'n/a'} ({who}). "
            f"Committed snapshot: {committed_at or 'n/a'}.")


def publish(result: dict, store: SnapshotStore | None = None) -> str | None:
    """Save the data of a good manual refresh in the store. Return a short note for the UI.

    Never raises. Returns None when there was nothing to save.
    """
    if not (result.get("ok") and result.get("data_dir") and result.get("scores_updated")):
        return None
    meta = {key: result.get(key) for key in ("fetched_at", "posts_before", "posts_after", "thread_id", "month")}
    meta["source"] = "manual"
    try:
        store = store if store is not None else get_store()
        store.save_snapshot(result["data_dir"], meta)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not save the refresh to the store: %s", exc)
        return f"Not saved for other visitors: {type(exc).__name__}: {exc}"
    if not store.durable:
        return "Saved on this machine only (no shared App Storage is set up here)."
    return "Saved to the shared store: every visitor now sees this data."
