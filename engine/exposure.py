"""Build the AI-exposure score per skill (task E3).

Inputs (raw files are gitignored, see data/SOURCES.md for URLs and licences):
- data/raw/ext/aei/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv
  Anthropic Economic Index, Claude.ai, global rows, O*NET task level.
- data/exposure_map.csv  (committed; skill -> O*NET task ids; team judgement)
- data/taxonomy.json     (the 40 skills)

Output: data/exposure.csv

Formulas (every number comes from the AEI file, none from memory):
- Per task and month: usage = AEI metric `pct` (percent of Claude.ai conversations).
  A task with no published row in a month counts as 0 for that month.
- Per task: usage = mean over the two published months (Apr and May 2026).
- ai_usage_share = MEAN of task usage over the skill's mapped tasks
  (percent points). We use the mean, not the sum, so a skill with more mapped
  tasks does not score higher only because of the task count.
- automation_share = usage-weighted mean of AEI metric
  `collaboration_bucket_automation_pct` over task-months that have both metrics
  (percent points). Empty when no mapped task has the metric.
- ai_exposure = min-max of ai_usage_share across the skills, 0 to 1.

Run:
    python engine/exposure.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AEI_PATH = ROOT / "data" / "raw" / "ext" / "aei" / "release_2026_06_26" / "data" / "aei_claude_ai_2026-06-26.csv"
MAP_PATH = ROOT / "data" / "exposure_map.csv"
TAXONOMY_PATH = ROOT / "data" / "taxonomy.json"
OUT_PATH = ROOT / "data" / "exposure.csv"

USAGE_METRIC = "pct"
AUTOMATION_METRIC = "collaboration_bucket_automation_pct"

SOURCE_NOTE = (
    "AEI release_2026_06_26 Claude.ai global, O*NET task level, mean of Apr+May 2026; "
    "usage in percent points, mean over mapped tasks, missing task = 0; "
    "automation = usage-weighted mean; task-to-skill map is team judgement"
)

COLUMNS = [
    "skill", "ai_exposure", "ai_usage_share", "automation_share",
    "n_tasks", "n_tasks_found_in_aei", "source_note",
]


def load_aei_tasks(path: Path = AEI_PATH) -> pd.DataFrame:
    """Return one row per (task_id, month) with columns usage and automation."""
    if not path.exists():
        raise FileNotFoundError(
            f"AEI file not found: {path}. Download it as described in data/SOURCES.md."
        )
    parts = []
    usecols = ["date_start", "geo_id", "category_name", "hierarchy_level",
               "metric_id", "value", "node_external_id"]
    for chunk in pd.read_csv(path, usecols=usecols, dtype={"node_external_id": str}, chunksize=500_000):
        keep = (
            (chunk["geo_id"] == "GLOBAL")
            & (chunk["category_name"] == "onet")
            & (chunk["hierarchy_level"] == 0)
            & chunk["metric_id"].isin([USAGE_METRIC, AUTOMATION_METRIC])
        )
        parts.append(chunk.loc[keep, ["date_start", "metric_id", "value", "node_external_id"]])
    df = pd.concat(parts, ignore_index=True)
    wide = df.pivot_table(
        index=["node_external_id", "date_start"], columns="metric_id", values="value", aggfunc="first"
    ).reset_index()
    wide = wide.rename(columns={USAGE_METRIC: "usage", AUTOMATION_METRIC: "automation",
                                "node_external_id": "task_id"})
    if "automation" not in wide.columns:
        wide["automation"] = float("nan")
    return wide


def build_exposure(
    aei_path: Path = AEI_PATH,
    map_path: Path = MAP_PATH,
    taxonomy_path: Path = TAXONOMY_PATH,
    out_path: Path | None = OUT_PATH,
) -> pd.DataFrame:
    """Compute data/exposure.csv. Returns the table; writes it when out_path is set."""
    skills = [t["skill"] for t in json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))]
    mapping = pd.read_csv(map_path, dtype={"task_id": str})
    unknown = set(mapping["skill"]) - set(skills)
    missing = set(skills) - set(mapping["skill"])
    if unknown or missing:
        raise ValueError(f"exposure_map.csv does not match taxonomy. Unknown: {unknown}. Missing: {missing}")

    aei = load_aei_tasks(aei_path)
    months = sorted(aei["date_start"].unique())
    usage_by_month = aei.pivot_table(index="task_id", columns="date_start", values="usage", aggfunc="first")
    usage_by_month = usage_by_month.reindex(columns=months)
    # Task usage = mean over published months, a month with no row counts as 0.
    task_usage = usage_by_month.fillna(0.0).mean(axis=1)
    found_ids = set(aei.loc[aei["usage"].notna(), "task_id"])

    rows = []
    for skill in skills:
        ids = mapping.loc[mapping["skill"] == skill, "task_id"].tolist()
        usage = [float(task_usage.get(t, 0.0)) for t in ids]
        sub = aei[aei["task_id"].isin(ids) & aei["usage"].notna() & aei["automation"].notna()]
        weight = float(sub["usage"].sum())
        if len(sub) and weight > 0:
            automation = float((sub["usage"] * sub["automation"]).sum() / weight)
        else:
            automation = float("nan")
        rows.append({
            "skill": skill,
            "ai_usage_share": sum(usage) / len(ids),
            "automation_share": automation,
            "n_tasks": len(ids),
            "n_tasks_found_in_aei": sum(1 for t in ids if t in found_ids),
            "source_note": SOURCE_NOTE,
        })
    out = pd.DataFrame(rows)
    lo, hi = out["ai_usage_share"].min(), out["ai_usage_share"].max()
    out["ai_exposure"] = (out["ai_usage_share"] - lo) / (hi - lo) if hi > lo else 0.0
    out = out[COLUMNS].copy()
    for col, digits in (("ai_exposure", 4), ("ai_usage_share", 4), ("automation_share", 2)):
        out[col] = out[col].round(digits)
    if out_path is not None:
        out.to_csv(out_path, index=False, encoding="utf-8")
    return out


if __name__ == "__main__":
    result = build_exposure()
    shown = result.sort_values("ai_exposure", ascending=False)
    print(shown.drop(columns="source_note").to_string(index=False))
    print(f"Wrote {OUT_PATH} ({len(result)} rows)")
