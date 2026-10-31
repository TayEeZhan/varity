"""Live "Refresh" pipeline: newest HN thread -> demand tables -> skill scores.

    from engine.refresh import refresh
    result = refresh()          # dict, never raises for network or file errors

Steps
1. Pick a runtime data directory. refresh() NEVER writes into the committed repo
   data/ folder (an accidental commit of refreshed files is a risk, and on Replit
   Autoscale the disk belongs to one instance and is lost on restart). The folder
   is $VERITY_RUNTIME_DIR if that variable is set, else <tempdir>/verity_data. The
   committed data/*.csv and data/*.json files (not data/raw) are copied there first.
   A work_dir argument (used by tests) replaces it. If the chosen folder is not
   writable, <tempdir>/verity_data is used instead.
2. Fetch the newest "Ask HN: Who is hiring?" thread, bypassing the raw cache.
3. Update hn_threads.csv, then recompute only that month in demand_monthly.csv
   (and ai_context_monthly.csv). No other month is read or changed.
4. Call engine.scores.build_scores(data_dir=<working directory>) and write
   skill_scores.json into the same directory. Every input of build_scores
   (demand, taxonomy, exposure, backtest, thread titles) is read from there.
5. Roles, in the same directory: recompute that month in role_demand_monthly.csv,
   then role_trends.json, role_backtest.json and role_forecast.json. A failure here
   puts the old role files back and is reported as roles_error; skills are kept.

The app must read skill_scores.json from result["data_dir"], not always from
the repo data/ folder.

On failure the result is {"ok": False, "error": ...}. The files in the data
directory are restored, so the last good snapshot stays in use.
HN post text is never written to a committed file. Raw JSON stays in
<data_dir>/raw/hn/.
"""
from __future__ import annotations

import contextlib
import csv
import inspect
import json
import os
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timezone
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import backfill_hn, demand  # noqa: E402

DATA_DIR = ROOT / "data"
TMP_DIR_NAME = "verity_data"
RUNTIME_ENV = "VERITY_RUNTIME_DIR"
SCORES_NAME = "skill_scores.json"
# Argument names that would mean build_scores takes a data directory.
# build_scores has had "data_dir" since step A1; the other names are older guesses.
DIR_PARAM_NAMES = ("data_dir", "work_dir", "base_dir", "root", "data_path")
ROLE_FILES = ("role_demand_monthly.csv", "role_trends.json", "role_backtest.json", "role_forecast.json",
              "forecast_ledger.csv", "llm_role_labels.csv", "roles.json", "title_counts_monthly.csv",
              "role_reviews.json", "role_candidates.json")

_LOCK = threading.Lock()


def runtime_dir(tmp_root: Path | None = None) -> Path:
    """Where refresh() works by default: $VERITY_RUNTIME_DIR, else <tempdir>/verity_data.

    tmp_root replaces the system temp folder (for tests); the variable still wins over it
    only when tmp_root is not given.
    """
    if tmp_root is None and os.environ.get(RUNTIME_ENV):
        return Path(os.environ[RUNTIME_ENV])
    return (Path(tmp_root) if tmp_root is not None else Path(tempfile.gettempdir())) / TMP_DIR_NAME


def is_writable(directory: Path) -> bool:
    """True if a file can be created in `directory` (it is created if missing)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=directory, prefix=".verity_probe_")
        os.close(fd)
        os.unlink(name)
        return True
    except OSError:
        return False


def seed_work_dir(source: Path, dest: Path) -> None:
    """Copy data/*.csv and data/*.json (not data/raw, not sub-folders) from source to dest.

    A file in dest is kept when it is newer than the source: it is an earlier
    refresh result. A file that is missing or older is copied.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for pattern in ("*.csv", "*.json"):
        for src in source.glob(pattern):
            dst = dest / src.name
            if src.is_file() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
                shutil.copy2(src, dst)


def choose_work_dir(work_dir: str | Path | None, source_dir: Path, tmp_root: Path | None = None) -> Path:
    """Return a writable data directory with the needed files in it."""
    wanted = Path(work_dir) if work_dir is not None else source_dir
    if is_writable(wanted):
        chosen = wanted
    else:
        chosen = (Path(tmp_root) if tmp_root is not None else Path(tempfile.gettempdir())) / TMP_DIR_NAME
        chosen.mkdir(parents=True, exist_ok=True)
    if chosen.resolve() != source_dir.resolve():
        seed_work_dir(source_dir, chosen)
    return chosen


def _build_scores_accepts_dir() -> str | None:
    """Name of the build_scores parameter that takes a data directory, or None."""
    from engine import scores

    params = inspect.signature(scores.build_scores).parameters
    return next((n for n in DIR_PARAM_NAMES if n in params), None)


def _run_build_scores(data_dir: Path) -> tuple[dict, bool]:
    """Call engine.scores.build_scores. Return (scores, data_dir_accepted)."""
    from engine import scores
    from engine.forecast import load_demand

    dir_param = _build_scores_accepts_dir()
    if dir_param is not None:
        return scores.build_scores(**{dir_param: data_dir}), True
    # Old build_scores without a directory argument (kept for safety). It does
    # accept the demand table, so pass ours. Its other inputs still come from
    # the repo data/ folder.
    return scores.build_scores(demand=load_demand(path=data_dir / "demand_monthly.csv")), False


def _read_scores(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _share_map(scores: dict) -> dict[str, float]:
    return {s["skill"]: s.get("demand_share_latest") for s in scores.get("skills") or []}


def _changed_shares(old: dict[str, float], new: dict[str, float]) -> dict[str, list]:
    out = {}
    for skill, new_v in new.items():
        old_v = old.get(skill)
        if old_v is None or new_v is None or abs(new_v - old_v) > 1e-9:
            out[skill] = [None if old_v is None else round(old_v, 6), None if new_v is None else round(new_v, 6)]
    return out


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _restore(backups: dict[Path, bytes | None]) -> None:
    for p, data in backups.items():
        if data is None:
            p.unlink(missing_ok=True)
        else:
            p.write_bytes(data)


def _update_roles(data_dir: Path, raw_dir: Path, threads_csv: Path, month: str) -> None:
    """Recompute role demand for `month` only, then role trends, backtest and forecast, all in data_dir.

    With the AI labeller switched on (role_labeller.json), the month's new posts are labelled by
    Claude first; without it, the title regex counts. Then the forecast is written to the ledger,
    and the ledger summary (track record, change since the last run) goes into role_forecast.json.
    """
    from engine import ledger, llm_labels, role_backtest, role_discover, role_forecast
    from engine import roles as roles_mod

    threads = [t for t in roles_mod._read_threads(threads_csv) if t["month"] == month]
    discovered = role_discover.daily(data_dir, raw_dir, threads[0]) if threads else None  # may add a role
    roles = roles_mod.load_roles(data_dir / "roles.json")
    labels, label_check, labeller = None, None, "title regex"
    if llm_labels.uses_llm(data_dir) and threads:
        config = llm_labels.read_config(data_dir)
        result = llm_labels.label_thread(data_dir, raw_dir, threads[0], roles)  # one thread per month
        label_check = {k: result[k] for k in ("claude_posts", "regex_posts", "dropped_quotes", "disagree", "error")}
        label_check["baseline_disagree"] = config.get("baseline_disagree")
        if llm_labels.drifted(result, config):
            labeller = "title regex (Claude's labels drifted from the usual today)"
        else:
            labels = result["labels"]
            labeller = llm_labels.labeller_name() + (f", title regex for {result['regex_posts']} posts Claude did not label"
                                   if result["regex_posts"] else "")
    scan = roles_mod.scan_threads(raw_dir, threads, roles, labels=labels)
    fresh = roles_mod.role_demand(raw_dir, threads_csv, roles, scan=scan)
    demand_csv = data_dir / ROLE_FILES[0]
    rows = [r for r in roles_mod.read_demand_rows(demand_csv) if r["month"] != month] + fresh
    rows.sort(key=lambda r: r["month"])  # stable sort keeps the roles.json order inside a month
    with demand_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=roles_mod.DEMAND_COLUMNS)
        writer.writeheader()
        writer.writerows({**r, "share": f"{r['share']:.6f}"} for r in rows)
    trends = roles_mod.build_role_trends(rows, roles)
    _atomic_write_text(data_dir / ROLE_FILES[1], json.dumps(trends, indent=2) + "\n")
    with contextlib.redirect_stdout(sys.stderr):  # engine.scheduled prints one JSON line on stdout
        role_backtest.main(data_dir)  # before role_forecast: it dates the forecast's band
        role_forecast.main(data_dir)
    forecast_path = data_dir / ROLE_FILES[3]
    doc = json.loads(forecast_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    rows_ledger = ledger.record(data_dir, doc, rows, now.strftime("%Y-%m-%d"), now.strftime("%Y-%m"))
    doc["track_record"] = ledger.summary(rows_ledger)
    doc["labeller"] = labeller
    doc["label_check"] = label_check
    doc["new_roles"] = None if discovered is None else {
        "added": discovered["added"], "waiting_for_review": len(discovered["waiting_for_review"]), "error": discovered["error"]}
    _atomic_write_text(forecast_path, json.dumps(doc, indent=2) + "\n")


def refresh(
    work_dir: str | Path | None = None,
    *,
    source_dir: str | Path | None = None,
    session=None,
    tmp_root: str | Path | None = None,
) -> dict:
    """Run the live refresh. Return a summary dict, or {"ok": False, "error": ...}.

    work_dir: where to work. Default is runtime_dir() ($VERITY_RUNTIME_DIR or
    <tempdir>/verity_data), never the repo data/ folder. source_dir: where the
    committed files are copied from (default repo data/). session and tmp_root are
    for tests. If another refresh is running the result has "busy": True.
    """
    started = time.monotonic()
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True, "error": "a refresh is already running"}
    data_dir: Path | None = None
    backups: dict[Path, bytes | None] = {}
    try:
        source = Path(source_dir) if source_dir is not None else DATA_DIR
        tmp_root_path = Path(tmp_root) if tmp_root is not None else None
        if work_dir is None:
            work_dir = runtime_dir(tmp_root_path)
            if work_dir.resolve() == source.resolve():
                raise ValueError(f"the runtime folder must not be the committed data folder ({source})")
        data_dir = choose_work_dir(work_dir, source, tmp_root_path)
        threads_csv = data_dir / "hn_threads.csv"
        demand_csv = data_dir / "demand_monthly.csv"
        ai_csv = data_dir / "ai_context_monthly.csv"
        scores_json = data_dir / SCORES_NAME
        raw_dir = data_dir / "raw" / "hn"

        old_scores = _read_scores(scores_json)
        posts_by_thread = demand._read_threads(threads_csv) if threads_csv.exists() else []
        posts_by_thread = {int(r["thread_id"]): int(r["n_top_level"]) for r in posts_by_thread}

        for p in (threads_csv, demand_csv, ai_csv, scores_json, *(data_dir / n for n in ROLE_FILES)):
            backups[p] = p.read_bytes() if p.exists() else None

        try:
            thread_id, month, n_top_level, fetched_at = backfill_hn.fetch_latest_thread(
                force=True, raw_dir=raw_dir, session=session, csv_path=threads_csv
            )
            merged = demand.update_months(
                [month],
                threads_csv=threads_csv,
                raw_dir=raw_dir,
                out_csv=demand_csv,
                ai_context_csv=ai_csv if ai_csv.exists() else None,
                taxonomy_path=data_dir / "taxonomy.json",
            )
            scores_error = None
            scores_updated = False
            dir_accepted = _build_scores_accepts_dir() is not None
            try:
                new_scores, dir_accepted = _run_build_scores(data_dir)
                _atomic_write_text(scores_json, json.dumps(new_scores, indent=2) + "\n")
                scores_updated = True
            except Exception as exc:  # scores are another module; keep demand data, report it
                new_scores = old_scores
                scores_error = f"{type(exc).__name__}: {exc}"
            roles_error = None
            roles_updated = False
            if (data_dir / "roles.json").is_file() and (data_dir / ROLE_FILES[0]).is_file():
                try:
                    _update_roles(data_dir, raw_dir, threads_csv, month)
                    roles_updated = True
                except Exception as exc:  # roles are another module; keep skills, put the old role files back
                    _restore({data_dir / n: backups[data_dir / n] for n in ROLE_FILES})
                    roles_error = f"{type(exc).__name__}: {exc}"
        except BaseException:
            _restore(backups)  # keep the last good data
            raise

        before = posts_by_thread.get(thread_id)
        return {
            "ok": True,
            "data_dir": str(data_dir),
            "used_temp_dir": data_dir.resolve() != Path(work_dir).resolve(),
            "committed_data_untouched": data_dir.resolve() != source.resolve(),
            "thread_id": thread_id,
            "month": month,
            "posts_before": before,
            "posts_after": n_top_level,
            "new_thread": before is None,
            "fetched_at": fetched_at,
            "rows_changed": merged["rows_changed"] + merged["rows_added"],
            "rows_added": merged["rows_added"],
            "ai_rows_changed": merged["ai_rows_changed"] + merged["ai_rows_added"],
            "skills_changed": _changed_shares(_share_map(old_scores), _share_map(new_scores)) if scores_updated else {},
            "scores_updated": scores_updated,
            "scores_error": scores_error,
            "scores_json": str(scores_json),
            "build_scores_accepts_data_dir": dir_accepted,
            "roles_updated": roles_updated,
            "roles_error": roles_error,
            "duration_s": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "data_dir": str(data_dir) if data_dir else None,
            "duration_s": round(time.monotonic() - started, 2),
        }
        if data_dir is not None:
            last = _read_scores(data_dir / SCORES_NAME)
            result["fallback"] = {"as_of": last.get("as_of"), "generated_at": last.get("generated_at")}
        return result
    finally:
        _LOCK.release()


def main() -> int:
    result = refresh()
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
