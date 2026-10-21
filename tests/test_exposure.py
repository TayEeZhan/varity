"""Tests for engine.exposure and the committed data/exposure.csv (task E3 v2).

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
OCC_CSV = ROOT / "data" / "exposure_occupations.csv"
VALID_STANCES = {"AI-complement", "AI-substitutable", "neutral"}


@pytest.fixture(scope="module")
def table():
    return pd.read_csv(EXPOSURE_CSV)


@pytest.fixture(scope="module")
def occ():
    return pd.read_csv(OCC_CSV, dtype={"onet_soc": str})


@pytest.fixture(scope="module")
def taxonomy():
    return json.loads((ROOT / "data" / "taxonomy.json").read_text(encoding="utf-8"))


def test_has_40_rows_and_columns(table):
    assert len(table) == 40
    assert list(table.columns) == exposure.COLUMNS


def test_every_taxonomy_skill_present_once(table, taxonomy):
    assert sorted(table["skill"]) == sorted(t["skill"] for t in taxonomy)


def test_category_matches_taxonomy(table, taxonomy):
    cat = {t["skill"]: t["category"] for t in taxonomy}
    assert {r.skill: r.category for r in table.itertuples()} == cat


def test_no_nan(table):
    assert not table.isna().any().any()


def test_ai_exposure_is_unit_ratio_of_automation_share(table):
    assert table["ai_exposure"].between(0, 1).all()
    assert table["automation_share"].between(0, 100).all()
    assert ((table["automation_share"] / 100) - table["ai_exposure"]).abs().max() < 1e-5


def test_stance_values_valid(table):
    assert set(table["stance"]) <= VALID_STANCES


def test_ai_ml_skills_are_ai_complement(table):
    ai = table[table["category"] == "ai_ml"]
    assert len(ai) > 0
    assert (ai["stance"] == "AI-complement").all()


def test_stance_follows_threshold_outside_ai_ml(table):
    rest = table[table["category"] != "ai_ml"]
    for r in rest.itertuples():
        if r.e_s > 0.02:
            assert r.stance == "AI-substitutable"
        elif r.e_s < -0.02:
            assert r.stance == "AI-complement"
        else:
            assert r.stance == "neutral"


def test_e_s_mean_is_about_zero(table):
    assert abs(table["e_s"].mean()) < 1e-4


def test_every_category_has_at_least_one_occupation(table, occ):
    assert set(table["category"]) <= set(occ["category"])
    per_cat = occ.groupby("category")["onet_soc"].nunique()
    assert (per_cat >= 1).all()
    assert not occ.isna().any().any()
    assert list(occ.columns) == exposure.OCC_COLUMNS
    assert occ["automation_pct"].between(0, 100).all()


def test_skill_occupations_match_occupation_table(table, occ):
    for r in table.itertuples():
        listed = set(r.occupations.split(";"))
        expected = set(occ.loc[occ["category"] == r.category, "onet_soc"])
        assert listed == expected


def test_automation_share_is_mean_of_category_occupations(table, occ):
    means = occ.groupby("category")["automation_pct"].mean()
    for r in table.itertuples():
        assert r.automation_share == pytest.approx(means[r.category], abs=1e-3)


def test_rebuild_matches_committed_files(table, occ):
    if not exposure.AEI_PATH.exists():
        pytest.skip("raw AEI file not downloaded")
    rebuilt = exposure.build_exposure(out_path=None, occ_path=None)
    pd.testing.assert_frame_equal(
        rebuilt.reset_index(drop=True), table.reset_index(drop=True), check_dtype=False
    )
    rebuilt_occ = exposure.build_occupations(exposure.load_occupation_automation()).round({"automation_pct": 4})
    pd.testing.assert_frame_equal(
        rebuilt_occ.reset_index(drop=True), occ.reset_index(drop=True), check_dtype=False
    )
