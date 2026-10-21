"""Build the monthly skill-demand series from raw HN "Who is hiring?" threads.

Input
- data/hn_threads.csv: one row per thread (thread_id, month, url, ...).
- data/raw/hn/<thread_id>.json: raw Algolia item tree (local only, gitignored).

Output (committed): data/demand_monthly.csv, one row per month x skill.
Columns: month, skill, mentions, n_posts, share, share_smooth, thread_id, thread_url.
- mentions: posts in that month that mention the skill. A post counts at most once per skill.
- n_posts: top-level posts with non-empty text, not deleted.
- share = mentions / n_posts.
- share_smooth = mean of share over this month and the 2 months before it.
  It is trailing, so no future month changes a past value. The first two months
  use the months that exist (1 or 2 values).

The output holds only aggregates and thread URLs. No post text, author name,
or per-post URL is ever written.

A second file, data/ai_context_monthly.csv, holds one row per month with the share of
posts that mention AI at all. Columns: month, mentions, n_posts, share, share_smooth,
thread_id, thread_url. See AI_CONTEXT_PATTERN for why this is not a skill.

Run: python engine/demand.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.tagging import clean_text, load_taxonomy, tag_text  # noqa: E402

THREADS_CSV = ROOT / "data" / "hn_threads.csv"
RAW_DIR = ROOT / "data" / "raw" / "hn"
OUT_CSV = ROOT / "data" / "demand_monthly.csv"
AI_CONTEXT_CSV = ROOT / "data" / "ai_context_monthly.csv"

SMOOTH_WINDOW = 3
SMALL_SAMPLE = 150
COLUMNS = ["month", "skill", "mentions", "n_posts", "share", "share_smooth", "thread_id", "thread_url"]
AI_CONTEXT_COLUMNS = ["month", "mentions", "n_posts", "share", "share_smooth", "thread_id", "thread_url"]

# Context series: posts that mention AI at all (company context), not a skill.
# A bare "AI" in a blurb ("we are an AI startup") says what the company sells.
# It does not say the job needs machine learning, so it is not in the taxonomy.
# Same rule as the old "Machine Learning / AI" pattern: case-sensitive, word
# boundaries, and "Generative AI" / "Gen AI" stay with LLM / GenAI.
AI_CONTEXT_PATTERN = re.compile(r"(?<![\w-])(?<!Generative )(?<!generative )(?<!Gen )AI(?!\w)")


def _read_threads(threads_csv: Path) -> list[dict]:
    with Path(threads_csv).open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    rows.sort(key=lambda r: (r["month"], int(r["thread_id"])))
    months = [r["month"] for r in rows]
    if len(set(months)) != len(months):
        raise ValueError("hn_threads.csv has two threads for one month; decide how to merge them first")
    return rows


def _live_posts(item: dict):
    """Yield the text of each top-level post that is not deleted and not empty."""
    for child in item.get("children") or []:
        if child.get("deleted"):
            continue
        text = child.get("text") or ""
        if text.strip():
            yield text


def build_demand(
    threads_csv: str | Path = THREADS_CSV,
    raw_dir: str | Path = RAW_DIR,
    out_csv: str | Path | None = OUT_CSV,
    taxonomy_path: str | Path | None = None,
    ai_context_csv: str | Path | None = None,
) -> list[dict]:
    """Count skill mentions per month, write the CSV, and return the rows.

    Pass out_csv=None to skip writing. The AI context series is written only
    when ai_context_csv is given. It is not part of the returned skill rows.
    """
    return build_all(threads_csv, raw_dir, out_csv, taxonomy_path, ai_context_csv)[0]


def build_all(
    threads_csv: str | Path = THREADS_CSV,
    raw_dir: str | Path = RAW_DIR,
    out_csv: str | Path | None = OUT_CSV,
    taxonomy_path: str | Path | None = None,
    ai_context_csv: str | Path | None = None,
) -> tuple[list[dict], list[dict]]:
    """Like build_demand, but also return the AI context rows."""
    taxonomy = load_taxonomy(taxonomy_path)
    skills = [e["skill"] for e in taxonomy]
    raw_dir = Path(raw_dir)

    rows: list[dict] = []
    ai_rows: list[dict] = []
    for thread in _read_threads(Path(threads_csv)):
        thread_id = thread["thread_id"]
        item = json.loads((raw_dir / f"{thread_id}.json").read_text(encoding="utf-8"))
        counts = dict.fromkeys(skills, 0)
        n_posts = 0
        ai_mentions = 0
        for text in _live_posts(item):
            n_posts += 1
            for skill in tag_text(text, taxonomy):  # a set: once per post per skill
                counts[skill] += 1
            if AI_CONTEXT_PATTERN.search(clean_text(text)):  # posts that mention AI at all, not a skill
                ai_mentions += 1
        ai_rows.append(
            {
                "month": thread["month"],
                "skill": "AI context",  # internal key so the shared smoothing helper works
                "mentions": ai_mentions,
                "n_posts": n_posts,
                "share": ai_mentions / n_posts if n_posts else 0.0,
                "share_smooth": 0.0,
                "thread_id": thread_id,
                "thread_url": thread["url"],
            }
        )
        for skill in skills:
            rows.append(
                {
                    "month": thread["month"],
                    "skill": skill,
                    "mentions": counts[skill],
                    "n_posts": n_posts,
                    "share": counts[skill] / n_posts if n_posts else 0.0,
                    "share_smooth": 0.0,
                    "thread_id": thread_id,
                    "thread_url": thread["url"],
                }
            )

    _add_trailing_mean(rows, skills)
    _add_trailing_mean(ai_rows, ["AI context"])

    if out_csv is not None:
        _write_csv(Path(out_csv), COLUMNS, rows)
    if ai_context_csv is not None:
        _write_csv(Path(ai_context_csv), AI_CONTEXT_COLUMNS, ai_rows)
    return rows, ai_rows


def _write_csv(out: Path, columns: list[str], rows: list[dict]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "share": f"{r['share']:.6f}", "share_smooth": f"{r['share_smooth']:.6f}"})


def _add_trailing_mean(rows: list[dict], skills: list[str]) -> None:
    """Set share_smooth to the mean of the last SMOOTH_WINDOW shares (this month included)."""
    by_skill: dict[str, list[dict]] = {s: [] for s in skills}
    for r in rows:
        by_skill[r["skill"]].append(r)  # rows are already in month order
    for series in by_skill.values():
        for i, r in enumerate(series):
            window = series[max(0, i - SMOOTH_WINDOW + 1) : i + 1]
            r["share_smooth"] = sum(w["share"] for w in window) / len(window)


def summarise(rows: list[dict]) -> None:
    months = sorted({r["month"] for r in rows})
    skills = list(dict.fromkeys(r["skill"] for r in rows))
    share = {(r["month"], r["skill"]): r["share"] for r in rows}
    n_posts = {r["month"]: r["n_posts"] for r in rows}

    first_year = months[0][:4]
    base_months = [m for m in months if m.startswith(first_year)][:12]
    last_months = months[-12:]

    def mean(skill: str, ms: list[str]) -> float:
        return sum(share[(m, skill)] for m in ms) / len(ms)

    stats = []
    for s in skills:
        a, b = mean(s, base_months), mean(s, last_months)
        stats.append((s, a, b, b - a))

    print(f"Rows written: {len(rows)} ({len(months)} months x {len(skills)} skills)")
    print(f"Window: {months[0]} to {months[-1]}")
    print(f"Base = mean share over {base_months[0]}..{base_months[-1]}; Recent = mean over {last_months[0]}..{last_months[-1]}")
    print()
    print(f"{'skill':<24}{'base %':>9}{'recent %':>10}{'change pp':>11}")
    for s, a, b, d in sorted(stats, key=lambda x: -x[2]):
        print(f"{s:<24}{a * 100:>9.1f}{b * 100:>10.1f}{d * 100:>+11.1f}")
    ranked = sorted(stats, key=lambda x: x[3])
    print()
    print("5 biggest risers (pp):")
    for s, a, b, d in reversed(ranked[-5:]):
        print(f"  {s:<24}{a * 100:>6.1f} -> {b * 100:>5.1f}  ({d * 100:+.1f})")
    print("5 biggest fallers (pp):")
    for s, a, b, d in ranked[:5]:
        print(f"  {s:<24}{a * 100:>6.1f} -> {b * 100:>5.1f}  ({d * 100:+.1f})")
    small = [(m, n_posts[m]) for m in months if n_posts[m] < SMALL_SAMPLE]
    print()
    print(f"Small-sample warning: months with n_posts < {SMALL_SAMPLE}:")
    if small:
        for m, n in small:
            print(f"  {m}: {n}")
    else:
        print("  none")


def summarise_ai_context(ai_rows: list[dict]) -> None:
    months = [r["month"] for r in ai_rows]
    first_year = months[0][:4]
    base = [r["share"] for r in ai_rows if r["month"].startswith(first_year)][:12]
    recent = [r["share"] for r in ai_rows[-12:]]
    print()
    print("AI context series (posts that mention AI at all, not a skill):")
    print(f"  {sum(base) / len(base) * 100:.1f}% -> {sum(recent) / len(recent) * 100:.1f}%")


def main() -> int:
    rows, ai_rows = build_all(ai_context_csv=AI_CONTEXT_CSV)
    summarise(rows)
    summarise_ai_context(ai_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
