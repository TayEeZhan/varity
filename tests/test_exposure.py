"""Tests for engine.exposure and the committed data/exposure.csv.

The checks read committed files only. The rebuild test needs the raw AEI file,
which is gitignored, so it is skipped when the file is missing.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import exposure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXPOSURE_CSV = ROOT / "data" / "exposure.csv"
MAP_CSV = ROOT / "data" / "exposure_map.csv"


@pytest.fixture(scope="module")
def table():
    return pd.read_csv(EXPOSURE_CSV)


@pytest.fixture(scope="module")
def skills():
    return [t["skill"] for t in json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf-8"))]


def test_has_40_rows_and_columns(table):
    assert len(table) == 40
    assert list(table.columns) == exposure.COLUMNS


def test_every_taxonomy_skill_present_once(table, skills):
    assert sorted(table["skill"]) == sorted(skills)


def test_scores_in_unit_interval_and_span_zero_to_one(table):
    assert table["ai_exposure"].between(0, 1).all()
    assert table["ai_exposure"].min() == 0
    assert table["ai_exposure"].max() == 1


def test_no_nan(table):
    assert not table.isna().any().any()


def test_task_counts_consistent(table):
    assert (table["n_tasks"].between(3, 8)).all()
    assert (table["n_tasks_found_in_aei"] <= table["n_tasks"]).all()
    assert (table["n_tasks_found_in_aei"] >= 0).all()
    assert (table["ai_usage_share"] >= 0).all()
    assert table["automation_share"].between(0, 100).all()


def test_map_covers_every_skill_with_3_to_8_unique_tasks(skills):
    m = pd.read_csv(MAP_CSV, dtype={"task_id": str})
    assert list(m.columns) == ["skill", "onet_soc", "task_id", "task_text", "rationale"]
    assert set(m["skill"]) == set(skills)
    counts = m.groupby("skill")["task_id"].agg(["size", "nunique"])
    assert counts["size"].between(3, 8).all()
    assert (counts["size"] == counts["nunique"]).all()
    assert not m.isna().any().any()


def test_rebuild_matches_committed_file(table):
    if not exposure.AEI_PATH.exists():
        pytest.skip("raw AEI file not downloaded")
    rebuilt = exposure.build_exposure(out_path=None)
    pd.testing.assert_frame_equal(
        rebuilt.reset_index(drop=True), table.reset_index(drop=True), check_dtype=False
    )
