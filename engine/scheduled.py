"""Daily refresh job for a Replit Scheduled Deployment.

    python -m engine.scheduled

Steps
1. engine.refresh.refresh() into a runtime folder (never the committed data/ folder).
2. If the refresh is ok and the scores were rebuilt, engine.store save_snapshot(): the
   data goes to Replit App Storage and latest.json is switched to it.
3. Print ONE line of JSON (the summary) on stdout. Exit code 0 on success, 1 on failure.

On any failure nothing is switched: latest.json keeps pointing to the previous good
snapshot, so visitors keep seeing the last good data. Progress and errors go to stderr.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import live  # noqa: E402
from engine import refresh as refresh_mod  # noqa: E402
from engine import store as store_mod  # noqa: E402

log = logging.getLogger("verity.scheduled")

META_KEYS = ("fetched_at", "posts_before", "posts_after", "thread_id", "month", "roles_updated", "roles_error")


def run(store: store_mod.SnapshotStore | None = None, **refresh_kwargs) -> dict:
    """Refresh, then save. Return the summary dict (never raises). `refresh_kwargs` go to refresh()."""
    started = time.monotonic()

    def done(summary: dict) -> dict:
        summary["duration_s"] = round(time.monotonic() - started, 2)
        return summary

    try:
        store = store if store is not None else store_mod.get_store(strict=True)
    except Exception as exc:  # noqa: BLE001
        return done({"ok": False, "stage": "store", "error": f"{type(exc).__name__}: {exc}"})
    if not store.durable:
        log.warning("the snapshot will be saved to a folder on THIS machine, not to Replit App Storage. "
                    "On Replit this is lost when the job ends: set the secret VERITY_STORE=replit.")

    if "source_dir" not in refresh_kwargs:
        # Start from the last stored snapshot, not the committed data: a fresh container would
        # otherwise lose every month and every ledger row added since the last commit.
        try:
            refresh_kwargs["source_dir"] = live.load_newer_snapshot(refresh_mod.DATA_DIR, store=store)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not read the last snapshot, starting from the committed data: %s", exc)
    try:
        result = refresh_mod.refresh(**refresh_kwargs)
    except Exception as exc:  # noqa: BLE001 - refresh() should not raise, but a job must not crash silently
        return done({"ok": False, "stage": "refresh", "error": f"{type(exc).__name__}: {exc}"})
    if not result.get("ok"):
        return done({"ok": False, "stage": "refresh", "error": result.get("error") or "refresh failed"})
    if not result.get("scores_updated"):
        # Demand data changed but the scores file is the old one: do not publish a mismatched pair.
        return done({"ok": False, "stage": "refresh",
                     "error": f"scores were not rebuilt: {result.get('scores_error') or 'unknown error'}"})

    meta = {key: result.get(key) for key in META_KEYS}
    meta["source"] = "scheduled"
    try:
        snapshot_id = store.save_snapshot(result["data_dir"], meta)
    except Exception as exc:  # noqa: BLE001
        return done({"ok": False, "stage": "save", "error": f"{type(exc).__name__}: {exc}"})
    return done({"ok": True, "snapshot_id": snapshot_id, "store": store.name, **meta,
                 "snapshots_kept": len(store.snapshot_ids())})


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    summary = run()
    if datetime.now(timezone.utc).weekday() == 0:  # weekly: a new DOSM quarter? my_dosm.update never raises and keeps the old CSV on failure
        from engine import my_dosm
        log.info("DOSM check: %s", my_dosm.update())
    if not summary["ok"]:
        log.error("scheduled refresh failed at %s: %s", summary.get("stage"), summary.get("error"))
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
