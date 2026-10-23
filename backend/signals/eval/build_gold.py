"""Gold-set helpers for ARCHITECTURE_JEV_RANKER.md section 9. People label; this only does the bookkeeping.

    python -m eval.build_gold sheet --ranking data/ranked/latest.csv
        Writes eval/labeling_sheet.csv: the top 40 plus a fixed random sample of the rest (150 by
        default), shuffled, with rank and all scores removed so the labels are not biased by them.

    python -m eval.build_gold gold
        Reads the filled sheet, checks every label, reports how often the two labellers agreed
        (raw agreement and Cohen's kappa), lists rows still needing a decision, and writes
        eval/gold_set.csv (url, gold_tier, labeller, note) for eval.metrics.

A row's gold tier is `final` when filled in; otherwise label_A when both labellers agree.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

TIERS = ("must_know", "worth_a_look", "minor")
SHEET_COLUMNS = ("item", "title", "url", "sources", "label_A", "label_B", "final", "note")
GOLD_COLUMNS = ("url", "gold_tier", "labeller", "note")
EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_SHEET = EVAL_DIR / "labeling_sheet.csv"
DEFAULT_GOLD = EVAL_DIR / "gold_set.csv"
TOP_ALWAYS = 40
DEFAULT_SIZE = 150
SEED = 2026  # fixed so the same ranking always yields the same sample


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sample_for_labelling(ranking: list[dict], size: int = DEFAULT_SIZE, seed: int = SEED) -> list[dict]:
    """Top TOP_ALWAYS by rank plus a random sample of the rest, shuffled, blind to scores."""
    ordered = sorted(ranking, key=lambda r: int(r["rank"]))
    top, rest = ordered[:TOP_ALWAYS], ordered[TOP_ALWAYS:]
    rng = random.Random(seed)
    chosen = top + rng.sample(rest, max(0, min(size - len(top), len(rest))))
    rng.shuffle(chosen)
    return [{"item": i, "title": r["title"], "url": r["url"], "sources": r["sources"],
             "label_A": "", "label_B": "", "final": "", "note": ""} for i, r in enumerate(chosen, start=1)]


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Agreement beyond chance between two labellers (1 = perfect, 0 = chance level)."""
    if not pairs:
        return float("nan")
    observed = sum(1 for a, b in pairs if a == b) / len(pairs)
    count_a, count_b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(count_a[t] * count_b[t] for t in TIERS) / (len(pairs) ** 2)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def build_gold(sheet: list[dict]) -> tuple[list[dict], dict]:
    """Return (gold rows, report). Raises ValueError on labels outside the three tiers."""
    def clean(value: str | None) -> str:
        return (value or "").strip().lower()

    bad = [row["item"] for row in sheet for key in ("label_A", "label_B", "final")
           if clean(row.get(key)) and clean(row.get(key)) not in TIERS]
    if bad:
        raise ValueError(f"items with a label that is not one of {TIERS}: {sorted(set(bad), key=int)}")
    pairs, gold, pending = [], [], []
    for row in sheet:
        a, b, final = clean(row.get("label_A")), clean(row.get("label_B")), clean(row.get("final"))
        if a and b:
            pairs.append((a, b))
        tier = final or (a if a and a == b else "")
        if tier:
            labeller = "A+B agreed" if not final and a == b else "A+B discussed"
            gold.append({"url": row["url"], "gold_tier": tier, "labeller": labeller, "note": row.get("note", "")})
        elif a or b:
            pending.append(row["item"])
    agreed = sum(1 for a, b in pairs if a == b)
    report = {
        "rows": len(sheet), "both_labelled": len(pairs), "agreement": agreed / len(pairs) if pairs else float("nan"),
        "kappa": cohen_kappa(pairs), "gold_rows": len(gold), "needs_decision": pending,
        "tier_counts": dict(Counter(row["gold_tier"] for row in gold)),
    }
    return gold, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the labelling sheet or the gold set")
    sub = parser.add_subparsers(dest="command", required=True)
    sheet = sub.add_parser("sheet", help="make a blind labelling sheet from a ranking CSV")
    sheet.add_argument("--ranking", type=Path, required=True)
    sheet.add_argument("--out", type=Path, default=DEFAULT_SHEET)
    sheet.add_argument("--size", type=int, default=DEFAULT_SIZE)
    gold = sub.add_parser("gold", help="turn the filled sheet into eval/gold_set.csv")
    gold.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    gold.add_argument("--out", type=Path, default=DEFAULT_GOLD)
    args = parser.parse_args(argv)

    if args.command == "sheet":
        rows = sample_for_labelling(read_csv(args.ranking), args.size)
        write_csv(args.out, SHEET_COLUMNS, rows)
        print(f"wrote {len(rows)} stories to {args.out}")
        return 0

    gold_rows, report = build_gold(read_csv(args.sheet))
    write_csv(args.out, GOLD_COLUMNS, gold_rows)
    print(f"{report['both_labelled']} of {report['rows']} rows labelled by both people; "
          f"agreement {report['agreement']:.0%}, Cohen's kappa {report['kappa']:.2f}")
    print(f"wrote {report['gold_rows']} gold rows to {args.out}: {report['tier_counts']}")
    if report["needs_decision"]:
        print(f"still to discuss (labellers disagree, no 'final' yet): items {report['needs_decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
