"""Score the ranking against a hand-labelled gold set (ARCHITECTURE_JEV_RANKER.md section 9).

Usage:
    python -m eval.metrics --gold eval/gold_set.csv [--run RUN_ID]

The gold CSV has columns: url, gold_tier (must_know | worth_a_look | minor), labeller, note.
Rows are matched to stories through any item URL in the story (canonicalised).

It compares the formula's ordering with Jev's ordering on the same run (Jev's answers are stored
even when it is only a second opinion), and reports calibration of P(must_know). The promotion
rule: Jev ranks by default only if it beats the formula here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from trendsignal.config import load_settings
from trendsignal.db import connect
from trendsignal.decision.ranker import impact_confidence, jev_final_score
from trendsignal.output import latest_run_id
from trendsignal.pipeline.normalise import canonical_url

GOLD_TIERS = ("must_know", "worth_a_look", "minor")
RELEVANCE = {"must_know": 3, "worth_a_look": 1, "minor": 0}
CALIBRATION_BINS = 5


def load_gold(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    bad = [row for row in rows if row.get("gold_tier") not in GOLD_TIERS]
    if bad:
        raise ValueError(f"{len(bad)} rows have a gold_tier outside {GOLD_TIERS}")
    return {canonical_url(row["url"]): row["gold_tier"] for row in rows if row.get("url")}


def labelled_rows(db_path: Path, gold: dict[str, str], run_id: str) -> list[dict]:
    """One row per labelled story in the run: formula score, Jev score (if answered), gold tier."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT r.story_id, r.formula_score, r.tier_probs_json, r.impact_probs_json, i.canonical_url"
            " FROM rankings r JOIN items i ON i.story_id = r.story_id WHERE r.run_id = ?", (run_id,)).fetchall()
    matched: dict[int, dict] = {}
    for row in rows:
        tier = gold.get(row["canonical_url"])
        if not tier or row["story_id"] in matched:
            continue
        tier_probs = json.loads(row["tier_probs_json"]) if row["tier_probs_json"] else None
        impact = json.loads(row["impact_probs_json"]) if row["impact_probs_json"] else None
        jev_score = None
        if tier_probs and impact:
            jev_score = jev_final_score(tier_probs, impact_confidence({int(k): v for k, v in impact.items()}))
        matched[row["story_id"]] = {"gold": tier, "formula": row["formula_score"], "jev": jev_score,
                                    "p_must_know": tier_probs["must_know"] if tier_probs else None}
    return list(matched.values())


def precision_at_k(ordered: list[dict], k: int) -> float:
    top = ordered[:k]
    return sum(1 for r in top if r["gold"] == "must_know") / len(top) if top else 0.0


def ndcg_at_k(ordered: list[dict], k: int) -> float:
    gains = [RELEVANCE[r["gold"]] for r in ordered]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains[:k]))
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(gains, reverse=True)[:k]))
    return dcg / ideal if ideal else 0.0


def brier_score(rows: list[dict]) -> float:
    pairs = [(r["p_must_know"], 1.0 if r["gold"] == "must_know" else 0.0) for r in rows if r["p_must_know"] is not None]
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs) if pairs else float("nan")


def reliability(rows: list[dict]) -> list[tuple[str, int, float, float]]:
    """(bin, count, mean predicted P(must_know), observed must-know rate) per probability bin."""
    bins: list[list[tuple[float, float]]] = [[] for _ in range(CALIBRATION_BINS)]
    for r in rows:
        if r["p_must_know"] is not None:
            index = min(int(r["p_must_know"] * CALIBRATION_BINS), CALIBRATION_BINS - 1)
            bins[index].append((r["p_must_know"], 1.0 if r["gold"] == "must_know" else 0.0))
    table = []
    for i, members in enumerate(bins):
        if members:
            label = f"{i / CALIBRATION_BINS:.1f}-{(i + 1) / CALIBRATION_BINS:.1f}"
            table.append((label, len(members), sum(p for p, _ in members) / len(members),
                          sum(y for _, y in members) / len(members)))
    return table


def report(rows: list[dict]) -> list[str]:
    lines = []
    by_formula = sorted(rows, key=lambda r: -r["formula"])
    lines.append(f"formula  precision@5 {precision_at_k(by_formula, 5):.2f}  NDCG@10 {ndcg_at_k(by_formula, 10):.2f}")
    answered = [r for r in rows if r["jev"] is not None]
    if not answered:
        lines.append("jev      no Jev answers in this run (set TYPESAFE_API_KEY and re-rank)")
        return lines
    by_jev = sorted(answered, key=lambda r: -r["jev"])
    formula_same = sorted(answered, key=lambda r: -r["formula"])
    lines.append(f"jev      precision@5 {precision_at_k(by_jev, 5):.2f}  NDCG@10 {ndcg_at_k(by_jev, 10):.2f}"
                 f"  (formula on the same {len(answered)} stories: {precision_at_k(formula_same, 5):.2f} /"
                 f" {ndcg_at_k(formula_same, 10):.2f})")
    lines.append(f"calibration  Brier score for P(must_know) {brier_score(answered):.3f} (lower is better)")
    for label, count, predicted, observed in reliability(answered):
        lines.append(f"  P {label}: {count:3} stories, predicted {predicted:.2f}, observed {observed:.2f}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the ranking against a gold set")
    parser.add_argument("--gold", type=Path, default=Path("eval/gold_set.csv"))
    parser.add_argument("--run", help="ranking run id (default: the latest)")
    args = parser.parse_args(argv)
    settings = load_settings()
    gold = load_gold(args.gold)
    run_id = args.run or latest_run_id(settings)
    rows = labelled_rows(settings.db_path, gold, run_id) if run_id else []
    print(f"gold rows: {len(gold)}  run: {run_id}  matched stories: {len(rows)}")
    if not rows:
        print("no labelled story was found in this run; rank the same period first")
        return 1
    print("\n".join(report(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
