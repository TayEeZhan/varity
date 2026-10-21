"""Build the AI-exposure score per skill (task E3 v2).

v1 used the share of Claude.ai traffic on hand-picked O*NET tasks. That measures
traffic volume, not exposure, so it is replaced (data/exposure_map.csv is the v1
file, kept but not used).

Inputs (the raw file is gitignored, see data/SOURCES.md for URL and licence):
- data/raw/ext/aei/release_2026_06_26/data/aei_claude_ai_2026-06-26.csv
  Anthropic Economic Index, Claude.ai.
- data/taxonomy.json (the 40 skills, each with a category)

Outputs:
- data/exposure_occupations.csv  (category -> occupations -> automation_pct)
- data/exposure.csv              (one row per skill)

Every number comes from the AEI file, none from memory:
- Rows are read with geo_id = GLOBAL, category_name = soc_occupation,
  hierarchy_level = 0 (Detailed Occupation), metric_id =
  collaboration_bucket_automation_pct (percent of conversations in the
  "automation" collaboration bucket: the AI did the task rather than helped).
  node_external_id is the O*NET-SOC code, node_name is the occupation title.
- The file has two months (Apr and May 2026). automation_pct of an occupation =
  mean of the two months.
- The category -> occupation map below is team judgement (reviewer suggestion).

Formulas:
- automation_share (percent points) = mean automation_pct of the category's occupations.
- ai_exposure = automation_share / 100 (a 0-1 ratio, not min-max, so it is explainable).
- e_s = automation_share/100 - mean over all 40 skills of automation_share/100.
- stance: AI-complement for category ai_ml; otherwise AI-substitutable if
  e_s > 0.02, neutral if |e_s| <= 0.02, AI-complement if e_s < -0.02.

Run:
    python engine/exposure.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AEI_PATH = ROOT / "data" / "raw" / "ext" / "aei" / "release_2026_06_26" / "data" / "aei_claude_ai_2026-06-26.csv"
TAXONOMY_PATH = ROOT / "data" / "taxonomy.json"
OUT_PATH = ROOT / "data" / "exposure.csv"
OCC_PATH = ROOT / "data" / "exposure_occupations.csv"

GEO = "GLOBAL"
CATEGORY_NAME = "soc_occupation"
HIERARCHY_LEVEL = 0
AUTOMATION_METRIC = "collaboration_bucket_automation_pct"
STANCE_THRESHOLD = 0.02

# Team judgement: taxonomy category -> O*NET-SOC codes as written in the AEI file.
CATEGORY_OCCUPATIONS: dict[str, list[str]] = {
    "language": ["15-1252.00", "15-1251.00"],
    "framework": ["15-1254.00", "15-1252.00"],
    "data": ["15-1243.00", "15-1242.00"],
    "cloud_devops": ["15-1244.00", "15-1299.08"],
    "ai_ml": ["15-2051.00"],
    "practice": ["15-1252.00"],
}

OCC_COLUMNS = ["category", "onet_soc", "occupation_title", "automation_pct", "source_row_note"]
COLUMNS = [
    "skill", "category", "ai_exposure", "automation_share", "e_s", "stance",
    "occupations", "source_note",
]

SOURCE_NOTE = (
    "AEI release_2026_06_26 Claude.ai, geo_id GLOBAL, category_name soc_occupation level 0, "
    "metric collaboration_bucket_automation_pct, mean of Apr+May 2026; "
    "automation_share = mean over the category's occupations; "
    "ai_exposure = automation_share/100; category-to-occupation map is team judgement"
)


def load_occupation_automation(path: Path = AEI_PATH) -> pd.DataFrame:
    """Return one row per (onet_soc, month): onet_soc, title, date_start, value."""
    if not path.exists():
        raise FileNotFoundError(
            f"AEI file not found: {path}. Download it as described in data/SOURCES.md."
        )
    usecols = ["date_start", "geo_id", "category_name", "hierarchy_level",
               "metric_id", "value", "node_name", "node_external_id"]
    parts = []
    for chunk in pd.read_csv(path, usecols=usecols, dtype={"node_external_id": str}, chunksize=500_000):
        keep = (
            (chunk["geo_id"] == GEO)
            & (chunk["category_name"] == CATEGORY_NAME)
            & (chunk["hierarchy_level"] == HIERARCHY_LEVEL)
            & (chunk["metric_id"] == AUTOMATION_METRIC)
        )
        parts.append(chunk.loc[keep, ["date_start", "value", "node_name", "node_external_id"]])
    df = pd.concat(parts, ignore_index=True)
    return df.rename(columns={"node_external_id": "onet_soc", "node_name": "title"})


def build_occupations(aei: pd.DataFrame) -> pd.DataFrame:
    """One row per (category, occupation) with automation_pct = mean over months."""
    months = sorted(aei["date_start"].unique())
    rows = []
    for category, codes in CATEGORY_OCCUPATIONS.items():
        for code in codes:
            sub = aei[aei["onet_soc"] == code].sort_values("date_start")
            if sub.empty:
                raise ValueError(f"SOC code {code} (category {category}) is not in the AEI file")
            titles = sub["title"].unique()
            per_month = "; ".join(f"{d} = {v}" for d, v in zip(sub["date_start"], sub["value"]))
            rows.append({
                "category": category,
                "onet_soc": code,
                "occupation_title": titles[0],
                "automation_pct": float(sub["value"].mean()),
                "source_row_note": (
                    f"geo_id=GLOBAL; category_name={CATEGORY_NAME}; hierarchy_level={HIERARCHY_LEVEL}; "
                    f"metric_id={AUTOMATION_METRIC}; node_external_id={code}; "
                    f"{len(sub)} of {len(months)} months ({per_month}); automation_pct = mean"
                ),
            })
    return pd.DataFrame(rows, columns=OCC_COLUMNS)


def stance_for(category: str, e_s: float) -> str:
    if category == "ai_ml":
        return "AI-complement"
    if e_s > STANCE_THRESHOLD:
        return "AI-substitutable"
    if e_s < -STANCE_THRESHOLD:
        return "AI-complement"
    return "neutral"


def build_exposure(
    aei_path: Path = AEI_PATH,
    taxonomy_path: Path = TAXONOMY_PATH,
    out_path: Path | None = OUT_PATH,
    occ_path: Path | None = OCC_PATH,
) -> pd.DataFrame:
    """Compute data/exposure.csv. Returns the table; writes files when paths are set."""
    taxonomy = json.loads(Path(taxonomy_path).read_text(encoding="utf-8"))
    categories = {t["category"] for t in taxonomy}
    if categories != set(CATEGORY_OCCUPATIONS):
        raise ValueError(
            f"Taxonomy categories {sorted(categories)} do not match the occupation map "
            f"{sorted(CATEGORY_OCCUPATIONS)}"
        )
    occ = build_occupations(load_occupation_automation(aei_path))
    share_by_category = occ.groupby("category")["automation_pct"].mean()

    out = pd.DataFrame({
        "skill": [t["skill"] for t in taxonomy],
        "category": [t["category"] for t in taxonomy],
    })
    out["automation_share"] = out["category"].map(share_by_category)
    ratio = out["automation_share"] / 100.0
    out["e_s"] = ratio - ratio.mean()
    out["ai_exposure"] = ratio
    out["stance"] = [stance_for(c, e) for c, e in zip(out["category"], out["e_s"])]
    out["occupations"] = out["category"].map(
        lambda c: ";".join(CATEGORY_OCCUPATIONS[c])
    )
    out["source_note"] = SOURCE_NOTE
    out = out[COLUMNS].copy()
    out["automation_share"] = out["automation_share"].round(4)
    out["ai_exposure"] = out["ai_exposure"].round(6)
    out["e_s"] = out["e_s"].round(6)

    occ_out = occ.copy()
    occ_out["automation_pct"] = occ_out["automation_pct"].round(4)
    if out_path is not None:
        out.to_csv(out_path, index=False, encoding="utf-8")
    if occ_path is not None:
        occ_out.to_csv(occ_path, index=False, encoding="utf-8")
    return out


if __name__ == "__main__":
    result = build_exposure()
    occ_table = pd.read_csv(OCC_PATH)
    print(occ_table.drop(columns="source_row_note").to_string(index=False))
    print()
    cat = result.groupby("category").agg(
        n_skills=("skill", "size"), automation_share=("automation_share", "first"),
        e_s=("e_s", "first"), stance=("stance", lambda s: "/".join(sorted(set(s)))),
    )
    print(cat.to_string())
    print()
    print(result.drop(columns=["source_note", "occupations"]).to_string(index=False))
    print(f"Wrote {OUT_PATH} ({len(result)} rows) and {OCC_PATH} ({len(occ_table)} rows)")
