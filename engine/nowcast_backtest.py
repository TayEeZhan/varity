"""Backtest for the partial-month nowcast (engine.forecast.nowcast_y): choose k from past threads.

Run: python -m engine.nowcast_backtest   (needs data/raw/hn; writes data/nowcast_backtest.json)

For every past thread that has a month before it, cut the thread at day 1, 3, 7 and 14 (post
timestamps, counted from the thread's own time) and estimate the full-month share of each ranked
role and each skill:
    share = (m_cut + k * s_prev) / (n_cut + k),  s_prev = smoothed share of the month before.
k = 0 is the raw partial share; a very large k is "last month only". The error is |estimate -
full-month share| in percentage points. k is chosen per cut day on months before SPLIT and
reported on the months after it, for roles and skills separately. One k for all days does not
work: after about 2 weeks the open thread is nearly complete, and any blending makes it worse.
The forecast uses the k of the cut day nearest to the days the thread has been open.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.demand import RAW_DIR, _read_threads  # noqa: E402
from engine.forecast import DATA_DIR, NOWCAST_JSON, smoothed_share  # noqa: E402
from engine.role_forecast import ranked_role_ids  # noqa: E402
from engine.roles import compile_patterns, load_roles, matching_roles  # noqa: E402
from engine.tagging import load_taxonomy, tag_text  # noqa: E402

CUT_DAYS = (1, 3, 7, 14)
K_GRID = (0, 10, 25, 50, 100, 200, 400, 800, 1600)
SPLIT = "2024-07"  # k is chosen on months before this, reported on months from it
DAY = 86400


def _posts(item: dict) -> list[tuple[int, str]]:
    """(created_at_i, text) of each live top-level post, as engine.demand counts them."""
    out = []
    for child in item.get("children") or []:
        text = child.get("text") or ""
        if not child.get("deleted") and text.strip():
            out.append((int(child.get("created_at_i") or 0), text))
    return out


def scan(raw_dir: Path, threads: list[dict], roles: list[dict], taxonomy: list[dict]) -> list[dict]:
    """Per thread: month, start time, and per post (time, ids of roles and skills it names)."""
    patterns = compile_patterns([r for r in roles if r["id"] in set(ranked_role_ids(roles))])
    out = []
    for t in threads:
        item = json.loads((raw_dir / f"{t['thread_id']}.json").read_text(encoding="utf-8"))
        posts = [(ts, matching_roles(text, patterns), tag_text(text, taxonomy)) for ts, text in _posts(item)]
        out.append({"month": t["month"], "start": int(item.get("created_at_i") or 0), "posts": posts})
    return out


def _counts(posts: list[tuple], ids: list[str], slot: int) -> tuple[np.ndarray, int]:
    m = np.zeros(len(ids))
    index = {s: i for i, s in enumerate(ids)}
    for p in posts:
        for s in p[slot]:
            if s in index:
                m[index[s]] += 1
    return m, len(posts)


def errors(scanned: list[dict], ids: list[str], slot: int) -> dict[str, dict[int, dict[int, list[float]]]]:
    """{"train"|"test": {k: {day: [abs errors in pp]}}} for one kind (slot 1 roles, 2 skills)."""
    out = {part: {k: {d: [] for d in CUT_DAYS} for k in K_GRID} for part in ("train", "test")}
    for prev, cur in zip(scanned, scanned[1:]):
        m_prev, n_prev = _counts(prev["posts"], ids, slot)
        m_full, n_full = _counts(cur["posts"], ids, slot)
        if not n_prev or not n_full:
            continue
        s_prev = smoothed_share(m_prev, n_prev)
        target = m_full / n_full
        part = "train" if cur["month"] < SPLIT else "test"
        for d in CUT_DAYS:
            cut = [p for p in cur["posts"] if p[0] <= cur["start"] + d * DAY]
            m_cut, n_cut = _counts(cut, ids, slot)
            for k in K_GRID:
                if n_cut + k == 0:
                    continue
                est = (m_cut + k * s_prev) / (n_cut + k)
                out[part][k][d].extend((np.abs(est - target) * 100).tolist())
    return out


def summarise(errs: dict) -> dict:
    """Mean error per k and day, the k per cut day (lowest train error) and its test errors."""
    mean = {part: {k: {d: float(np.mean(v)) for d, v in days.items() if v} for k, days in by_k.items()}
            for part, by_k in errs.items()}
    k_by_day = {d: min(K_GRID, key=lambda k: mean["train"][k].get(d, np.inf)) for d in CUT_DAYS}
    return {
        "k_by_day": {str(d): k for d, k in k_by_day.items()},
        "train_mae_pp": {str(kk): {str(d): round(v, 4) for d, v in days.items()} for kk, days in mean["train"].items()},
        "test_mae_pp": {str(kk): {str(d): round(v, 4) for d, v in days.items()} for kk, days in mean["test"].items()},
        "test_chosen_vs_raw_pp": {str(d): {"raw_partial": round(mean["test"][0][d], 4),
                                           "nowcast": round(mean["test"][k_by_day[d]][d], 4),
                                           "last_month_only": round(mean["test"][K_GRID[-1]][d], 4)}
                                  for d in CUT_DAYS if d in mean["test"][k_by_day[d]]},
    }


def main(data_dir: Path | str | None = None, raw_dir: Path | str | None = None) -> int:
    data_dir = DATA_DIR if data_dir is None else Path(data_dir)
    raw_dir = RAW_DIR if raw_dir is None else Path(raw_dir)
    threads = _read_threads(data_dir / "hn_threads.csv")
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    threads = [t for t in threads if t["month"] < this_month]  # an open thread has no full-month truth
    roles = load_roles(data_dir / "roles.json")
    taxonomy = load_taxonomy(data_dir / "taxonomy.json")
    scanned = scan(raw_dir, threads, roles, taxonomy)
    role_ids = ranked_role_ids(roles)
    skills = [t["skill"] for t in taxonomy]
    doc = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "Past HN threads cut at day 1/3/7/14; share = (m_cut + k*s_prev)/(n_cut + k); "
                  f"k chosen by mean |error| on months before {SPLIT}, reported on months from {SPLIT}.",
        "cut_days": list(CUT_DAYS),
        "k_grid": list(K_GRID),
        "split": SPLIT,
        "months": {"from": threads[1]["month"], "to": threads[-1]["month"]},
        "roles": summarise(errors(scanned, role_ids, 1)),
        "skills": summarise(errors(scanned, skills, 2)),
    }
    out = data_dir / NOWCAST_JSON.name
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    for kind in ("roles", "skills"):
        print(f"{kind}: k by day {doc[kind]['k_by_day']}; test error (pp) by cut day: "
              f"{doc[kind]['test_chosen_vs_raw_pp']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
