"""Ranked output (ARCHITECTURE_JEV_RANKER.md section 8): JSON, CSV and a terminal table."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from trendsignal.config import Settings, SourceConfig
from trendsignal.db import connect, loads
from trendsignal.timeutil import now_utc, to_iso

CSV_COLUMNS = ("rank", "tier", "final_score", "ranked_by", "expected_impact", "confidence", "p_must_know",
               "p_worth_a_look", "p_minor", "formula_score", "title", "url", "sources", "top_features")
FORMULA_PREFIXES = ("=", "+", "-", "@")  # spreadsheet formula injection


def latest_run_id(settings: Settings) -> str | None:
    with connect(settings.db_path) as conn:
        row = conn.execute("SELECT run_id FROM rankings ORDER BY computed_at DESC, id DESC LIMIT 1").fetchone()
    return row["run_id"] if row else None


def _story_sources(conn, story_ids: list[int], sources: dict[str, SourceConfig]) -> dict[int, tuple[list[str], dict[int, str]]]:
    if not story_ids:
        return {}
    placeholders = ",".join("?" for _ in story_ids)
    result: dict[int, tuple[list[str], dict[int, str]]] = {}
    for item in conn.execute(f"SELECT id, story_id, source_id, tier, canonical_url FROM items"
                             f" WHERE story_id IN ({placeholders}) ORDER BY tier, published_at", story_ids):
        names, urls = result.setdefault(item["story_id"], ([], {}))
        source = sources.get(item["source_id"])
        name = source.name if source else item["source_id"]
        if name not in names:
            names.append(name)
        urls[item["id"]] = item["canonical_url"]
    return result


def ranking_rows(settings: Settings, sources: dict[str, SourceConfig], run_id: str | None = None, *,
                 hours: int = 72, limit: int | None = None, now: datetime | None = None) -> list[dict]:
    run_id = run_id or latest_run_id(settings)
    if run_id is None:
        return []
    since = to_iso((now or now_utc()) - timedelta(hours=hours))
    with connect(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT r.*, s.title, s.first_seen_at, s.anchor_item_id, s.category FROM rankings r"
            " JOIN stories s ON s.id = r.story_id WHERE r.run_id = ? AND s.first_seen_at >= ? ORDER BY r.rank",
            (run_id, since)).fetchall()
        rows = rows[:limit] if limit else rows
        story_sources = _story_sources(conn, [row["story_id"] for row in rows], sources)
    output = []
    for position, row in enumerate(rows, start=1):
        names, urls = story_sources.get(row["story_id"], ([], {}))
        impact = loads(row["impact_probs_json"], None)
        output.append({
            "rank": position,
            "title": row["title"],
            "url": urls.get(row["anchor_item_id"]) or next(iter(urls.values()), ""),
            "sources": names,
            "tier": row["tier"],
            "tier_probs": loads(row["tier_probs_json"], None),
            "impact_probs": {int(k): v for k, v in impact.items()} if impact else None,
            "expected_impact": row["expected_impact"],
            "confidence": row["confidence"],
            "final_score": row["final_score"],
            "top_features": loads(row["top_features_json"], []),
            "ranked_by": row["ranked_by"],
            "formula_score": row["formula_score"],
            "notes": loads(row["notes_json"], []),
            "category": row["category"],
            "first_seen_at": row["first_seen_at"],
            "story_id": row["story_id"],
            "jev_model": row["jev_model"],
            "jev_error": row["jev_error"],
        })
    return output


def ranking_document(settings: Settings, rows: list[dict], run_id: str | None) -> dict:
    rankers = {row["ranked_by"] for row in rows}
    ranked_by = rankers.pop() if len(rankers) == 1 else ("mixed" if rankers else settings.ranker)
    generated = datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds")
    return {"generated_at": generated, "run_id": run_id, "ranked_by": ranked_by, "stories": rows}


def _safe_cell(value: object) -> object:
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        probs = row["tier_probs"] or {}
        writer.writerow({key: _safe_cell(value) for key, value in {
            "rank": row["rank"], "tier": row["tier"], "final_score": row["final_score"], "ranked_by": row["ranked_by"],
            "expected_impact": row["expected_impact"], "confidence": row["confidence"],
            "p_must_know": probs.get("must_know"), "p_worth_a_look": probs.get("worth_a_look"),
            "p_minor": probs.get("minor"), "formula_score": row["formula_score"], "title": row["title"],
            "url": row["url"], "sources": "; ".join(row["sources"]), "top_features": "; ".join(row["top_features"]),
        }.items()})
    return buffer.getvalue()


def write_ranking(document: dict, out_dir: Path, extras: dict[str, object] | None = None) -> dict[str, Path]:
    """Write latest.json, latest.csv and a per-run JSON. `extras` adds more JSON files (e.g. skills.json)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "latest.json",
        "csv": out_dir / "latest.csv",
        "run": out_dir / f"ranked-{document.get('run_id') or 'none'}.json",
    }
    body = json.dumps(document, ensure_ascii=False, indent=2)
    paths["json"].write_text(body, encoding="utf-8")
    paths["run"].write_text(body, encoding="utf-8")
    paths["csv"].write_text(to_csv(document["stories"]), encoding="utf-8")
    for name, data in (extras or {}).items():
        paths[name] = out_dir / f"{name}.json"
        paths[name].write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def format_table(rows: list[dict], width: int = 70) -> str:
    header = f"{'#':>3}  {'tier':12} {'score':>5}  {'by':7} {'P(must)':>7} {'impact':>6}  title"
    lines = [header, "-" * len(header)]
    for row in rows:
        probs = row["tier_probs"] or {}
        p_must = f"{probs['must_know']:.2f}" if "must_know" in probs else "-"
        impact = f"{row['expected_impact']:.1f}" if row["expected_impact"] is not None else "-"
        lines.append(f"{row['rank']:>3}  {row['tier']:12} {row['final_score']:5.1f}  {row['ranked_by']:7} "
                     f"{p_must:>7} {impact:>6}  {row['title'][:width]}")
        if row["top_features"]:
            lines.append(f"{'':>34}{' · '.join(row['top_features'])}")
    return "\n".join(lines)
