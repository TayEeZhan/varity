"""Tests for step 9: exposure-index cross-check (engine/exposure_indices.py), the measured k
(engine/k_estimate.py) and how the app shows both."""
from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats
from streamlit.testing.v1 import AppTest

from engine import exposure_indices as ei
from engine import k_estimate as ke
from engine.forecast import inv_logit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
APP_PATH = str(ROOT / "app.py")
TIMEOUT = 60

needs_outputs = pytest.mark.skipif(
    not (DATA / "exposure_agreement.json").exists() or not (DATA / "exposure_robustness.csv").exists()
    or not (DATA / "k_estimate.json").exists(), reason="step 9 outputs not generated yet")
needs_raw = pytest.mark.skipif(
    not all(p.exists() for p in (ei.GPTS_CSV, ei.AIOE_XLSX, ei.AIOE_LM_XLSX, ei.MSFT_CSV,
                                 ei.XWALK_2010_2019, ei.XWALK_2019_SOC)),
    reason="raw files in data/raw/ext are gitignored; download them as in data/SOURCES.md")


# --- SOC crosswalk ----------------------------------------------------------------------

@pytest.fixture
def walk() -> pd.DataFrame:
    """A slice of the official O*NET 2010 -> 2019 crosswalk (shape and values as in the real file)."""
    rows = [
        ("15-1132.00", "15-1252.00"), ("15-1133.00", "15-1252.00"),
        ("15-1132.00", "15-1253.00"), ("15-1131.00", "15-1251.00"),
        ("15-1141.00", "15-1243.00"), ("15-1199.06", "15-1243.00"),
        ("15-1199.02", "15-1299.08"), ("15-2099.00", "15-2051.00"),
    ]
    return pd.DataFrame(rows, columns=["O*NET-SOC 2010 Code", "O*NET-SOC 2019 Code"])


@pytest.mark.parametrize("code,expected", [
    ("15-1299.08", "15-1299"), ("15-1252.00", "15-1252"), ("15-1252", "15-1252"),
])
def test_soc6_drops_the_onet_suffix(code, expected):
    assert ei.soc6(code) == expected


@pytest.mark.parametrize("bad", ["", "15-12", "151252", "abc"])
def test_soc6_rejects_bad_codes(bad):
    with pytest.raises(ValueError):
        ei.soc6(bad)


def test_parents_2010_merge_and_split(walk):
    assert ei.parents_2010("15-1252.00", walk) == ["15-1132", "15-1133"]  # two 2010 codes merged
    assert ei.parents_2010("15-1251.00", walk) == ["15-1131"]  # one to one
    assert ei.parents_2010("15-1243.00", walk) == ["15-1141", "15-1199"]  # 8-digit code rolls up to 15-1199
    assert ei.parents_2010("15-1299.08", walk) == ["15-1199"]
    assert ei.parents_2010("99-9999.00", walk) == []


def test_aioe_mean_of_parents_and_missing_parent(walk):
    aioe = {"15-1132": 1.0, "15-1133": 2.0, "15-1131": 5.0, "15-1141": 1.0, "15-1199": 3.0}
    value, note = ei.aioe_for("15-1252.00", aioe, walk)
    assert value == pytest.approx(1.5) and "15-1132" in note and "15-1133" in note
    value, _ = ei.aioe_for("15-1243.00", aioe, walk)
    assert value == pytest.approx(2.0)  # mean of 15-1141 and 15-1199
    value, note = ei.aioe_for("15-2051.00", aioe, walk)  # its only parent 15-2099 has no AIOE value
    assert value is None and "none has an AIOE value" in note


def test_aioe_uses_the_parents_that_exist_and_says_so(walk):
    value, note = ei.aioe_for("15-1243.00", {"15-1141": 4.0}, walk)
    assert value == pytest.approx(4.0) and "15-1199" in note


def test_msft_maps_through_soc2018_table():
    table = {"15-1252.00": "15-1252", "15-1299.08": "15-1299", "15-2051.00": "15-2051"}
    assert ei.soc2018_of("15-1299.08", table) == "15-1299"
    with pytest.raises(KeyError):
        ei.soc2018_of("00-0000.00", table)


def test_msft_values_flag_broad_codes(tmp_path):
    csv_path = tmp_path / "m.csv"
    pd.DataFrame({"SOC Code": ["15-1252", "15-1299"], "title": ["a", "b"],
                  "ai_applicability_score": [0.3, 0.2]}).to_csv(csv_path, index=False)
    table = {"15-1252.00": "15-1252", "15-1299.08": "15-1299", "15-2051.00": "15-2051"}
    out = ei.load_msft_values(["15-1252.00", "15-1299.08", "15-2051.00"], table, csv_path)
    assert out["15-1252.00"][0] == pytest.approx(0.3)
    assert out["15-1299.08"][0] == pytest.approx(0.2) and "shares the broad SOC code" in out["15-1299.08"][1]
    assert out["15-2051.00"][0] is None


def test_xlsx_reader_reads_strings_numbers_and_gaps(tmp_path):
    path = tmp_path / "t.xlsx"
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   f'<workbook {ns} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}><si><t>SOC Code</t></si><si><t>15-1252</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet {ns}><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1"><v>2.5</v></c></row>'
                   '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>1.25</v></c></row>'
                   '</sheetData></worksheet>')
    assert ei.read_xlsx_rows(path, "S") == [["SOC Code", None, 2.5], ["15-1252", 1.25]]
    with pytest.raises(KeyError):
        ei.read_xlsx_rows(path, "missing")


# --- z-scores and ranks -----------------------------------------------------------------

def test_zscores_have_mean_zero_and_unit_population_sd():
    z = ei.zscores([1.0, 2.0, 3.0, 4.0])
    assert z.mean() == pytest.approx(0.0)
    assert z.std(ddof=0) == pytest.approx(1.0)
    assert z[0] < z[1] < z[2] < z[3]


def test_zscores_constant_and_nan():
    assert ei.zscores([5, 5, 5]).tolist() == [0.0, 0.0, 0.0]
    z = ei.zscores([1.0, float("nan"), 3.0])
    assert math.isnan(z[1]) and z[0] == pytest.approx(-1.0) and z[2] == pytest.approx(1.0)


def test_ranks_desc_one_is_most_exposed_with_average_ties():
    assert ei.ranks_desc([10, 30, 20]).tolist() == [3.0, 1.0, 2.0]
    assert ei.ranks_desc([5, 5, 1]).tolist() == [1.5, 1.5, 3.0]
    r = ei.ranks_desc([1.0, float("nan"), 2.0])
    assert math.isnan(r[1]) and r[0] == 2.0 and r[2] == 1.0


def test_indices_table_has_rank_and_z_per_occupation():
    values = {s.id: {"a": (1.0, ""), "b": (3.0, ""), "c": (2.0, "")} for s in ei.INDEX_SPECS}
    values["aioe"]["c"] = (None, "no value")
    table = ei.build_indices_table(values, {"a": "A", "b": "B", "c": "C"})
    assert len(table) == 3 * len(ei.INDEX_SPECS)
    row = table[(table["source"] == "gpts_gpt4_beta") & (table["onet_soc"] == "b")].iloc[0]
    assert row["rank"] == 1.0 and row["z"] > 0 and row["n_occupations"] == 3
    gap = table[(table["source"] == "aioe") & (table["onet_soc"] == "c")].iloc[0]
    assert pd.isna(gap["raw_value"]) and pd.isna(gap["rank"]) and gap["n_occupations"] == 2


# --- Spearman ---------------------------------------------------------------------------

def test_spearman_matches_scipy():
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=8), rng.normal(size=8)
    assert ei.spearman(x, y) == pytest.approx(stats.spearmanr(x, y).statistic)
    assert ei.spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert ei.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


def test_spearman_edge_cases_are_nan():
    assert math.isnan(ei.spearman([1, 2], [1, 2]))  # fewer than 3 pairs
    assert math.isnan(ei.spearman([1, 1, 1], [1, 2, 3]))  # constant
    assert ei.spearman([1, 2, 3, float("nan")], [1, 2, 3, 4]) == pytest.approx(1.0)  # NaN pair dropped


def test_permutation_p_value_is_exact():
    # perfect rank agreement of 5 points: only 1 of 120 orderings is as extreme, plus its mirror image
    assert ei.spearman_perm_p([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(2 / 120)
    p = ei.spearman_perm_p([1, 2, 3, 4, 5, 6], [2, 1, 4, 3, 6, 5])
    assert 0 < p < 0.1
    assert ei.spearman_perm_p([1, 2, 3, 4, 5, 6, 7, 8], [3, 1, 4, 8, 2, 7, 5, 6]) > 0.1


def test_permutation_p_is_seeded_above_the_exact_limit():
    x = np.arange(10.0)
    y = np.array([3, 1, 4, 9, 2, 8, 5, 7, 0, 6], dtype=float)
    assert ei.spearman_perm_p(x, y, seed=3) == ei.spearman_perm_p(x, y, seed=3)


# --- Category views and the agreement logic ---------------------------------------------

def test_category_raw_means_and_skips_missing():
    raw = {"15-1252.00": 1.0, "15-1251.00": 3.0, "15-1254.00": None, "15-1243.00": 2.0,
           "15-1242.00": None, "15-1244.00": 4.0, "15-1299.08": 6.0, "15-2051.00": None}
    cat = ei.category_raw(raw)
    assert cat["language"] == pytest.approx(2.0)
    assert cat["framework"] == pytest.approx(1.0)  # only 15-1252 has a value
    assert cat["data"] == pytest.approx(2.0)
    assert cat["cloud_devops"] == pytest.approx(5.0)
    assert math.isnan(cat["ai_ml"])


def test_skill_weighted_z_counts_every_skill_once():
    scores = {"a": 1.0, "b": 3.0, "c": float("nan")}
    dev, z, sd = ei.skill_weighted_z(scores, {"a": 3, "b": 1, "c": 5})
    # mean over 4 skills (3 of a, 1 of b) = 1.5
    assert dev["a"] == pytest.approx(-0.5) and dev["b"] == pytest.approx(1.5)
    assert sd == pytest.approx(math.sqrt((3 * 0.25 + 1 * 2.25) / 4))
    assert z["b"] == pytest.approx(1.5 / sd)
    assert math.isnan(dev["c"]) and math.isnan(z["c"])


@pytest.mark.parametrize("z,expected", [
    (0.5, ei.SUBSTITUTABLE), (-0.5, ei.COMPLEMENT), (0.2, ei.NEUTRAL), (-0.4, ei.NEUTRAL), (0.4, ei.NEUTRAL),
])
def test_label_for_uses_the_neutral_band(z, expected):
    assert ei.label_for(z, 0.4) == expected


def test_label_for_nan_is_none():
    assert ei.label_for(float("nan"), 0.4) is None


@pytest.mark.parametrize("label,z,expected", [
    (ei.SUBSTITUTABLE, 0.1, True), (ei.SUBSTITUTABLE, -0.1, False),
    (ei.COMPLEMENT, -2.0, True), (ei.COMPLEMENT, 0.3, False),
    (ei.NEUTRAL, 0.39, True), (ei.NEUTRAL, -0.39, True), (ei.NEUTRAL, 0.41, False),
])
def test_supports_polar_by_side_and_neutral_by_band(label, z, expected):
    assert ei.supports(label, z, 0.4) is expected


def test_supports_abstains_on_nan():
    assert ei.supports(ei.COMPLEMENT, float("nan"), 0.4) is None


def test_agreement_robust_when_most_families_support():
    out = ei.agreement_for_category(ei.SUBSTITUTABLE, "above",
                                    {"aei": 1.0, "gpts": 0.5, "aioe": 0.2, "msft": -1.0}, 0.4)
    assert out["n_voting"] == 4 and out["n_support"] == 3 and out["stance_robust"] is True
    assert out["families_supporting"] == ["aei", "gpts", "aioe"]
    assert out["n_exact_label"] == 2  # aei and gpts are polar-substitutable; aioe is neutral


def test_agreement_contested_on_a_tie_or_less():
    out = ei.agreement_for_category(ei.SUBSTITUTABLE, "above",
                                    {"aei": 1.0, "gpts": 0.5, "aioe": -0.5, "msft": -1.0}, 0.4)
    assert out["n_support"] == 2 and out["stance_robust"] is False  # 2 of 4 is not more than half


def test_agreement_family_without_value_abstains():
    out = ei.agreement_for_category(ei.COMPLEMENT, "below",
                                    {"aei": -2.0, "gpts": -0.1, "aioe": float("nan"), "msft": 0.5}, 0.4)
    assert out["n_voting"] == 3 and out["n_support"] == 2 and out["stance_robust"] is True


def test_strong_opposite_reading_vetoes_a_majority():
    out = ei.agreement_for_category(ei.COMPLEMENT, "below",
                                    {"aei": -2.0, "gpts": -0.1, "aioe": float("nan"), "msft": 2.0}, 0.4)
    assert out["majority_supports"] is True and out["families_vetoing"] == ["msft"]
    assert out["stance_robust"] is False


def test_a_mild_opposite_reading_does_not_veto():
    out = ei.agreement_for_category(ei.SUBSTITUTABLE, "above",
                                    {"aei": 1.0, "gpts": 0.5, "aioe": 0.2, "msft": -1.0}, 0.4)  # -1.0 is not beyond 1
    assert out["families_vetoing"] == [] and out["stance_robust"] is True


@pytest.mark.parametrize("label,z,expected", [
    (ei.SUBSTITUTABLE, -1.5, True), (ei.SUBSTITUTABLE, 1.5, False), (ei.SUBSTITUTABLE, -1.0, False),
    (ei.COMPLEMENT, 1.5, True), (ei.COMPLEMENT, -1.5, False), (ei.NEUTRAL, 3.0, False),
    (ei.COMPLEMENT, float("nan"), False),
])
def test_contradicts_needs_a_strong_opposite_reading(label, z, expected):
    assert ei.contradicts(label, z) is expected


def test_agreement_with_no_voters_is_not_robust():
    out = ei.agreement_for_category(ei.NEUTRAL, "above", {"aei": float("nan")}, 0.4)
    assert out["n_voting"] == 0 and out["stance_robust"] is False


def test_neutral_stance_is_tested_by_the_band_not_the_side():
    out = ei.agreement_for_category(ei.NEUTRAL, "below", {"aei": -0.3, "gpts": 0.3, "aioe": 0.1, "msft": 2.0}, 0.4)
    assert out["n_support"] == 3 and out["stance_robust"] is True


def _fake_world():
    """All four families with fixed raw values for the 8 occupations, plus production tables."""
    codes = ei.occupations()
    pattern = {  # raw value per occupation; msft is the mirror image of aei
        "aei_automation": [60, 63, 55, 58, 63, 67, 62, 47],
        "gpts_gpt4_beta": [61, 64, 56, 59, 62, 66, 61, 48],
        "gpts_human_beta": [60, 62, 57, 58, 61, 65, 60, 49],
        "aioe": [62, 64, 54, 57, 63, 68, 63, None],
        "aioe_lm": [61, 63, 55, 58, 62, 67, 62, None],
        "msft_applicability": [40, 37, 45, 42, 37, 33, 38, 53],
    }
    order = ["15-1252.00", "15-1251.00", "15-1254.00", "15-1243.00", "15-1242.00", "15-1244.00",
             "15-1299.08", "15-2051.00"]
    assert sorted(order) == sorted(codes)
    values = {i: {c: (None if v is None else float(v), "") for c, v in zip(order, vals)}
              for i, vals in pattern.items()}
    taxonomy = [{"skill": f"{cat}-{n}", "category": cat}
                for cat, n in [("language", 3), ("framework", 2), ("data", 2), ("cloud_devops", 2),
                               ("ai_ml", 1), ("practice", 1)] for n in range(n)]
    e = {"language": 0.02, "framework": -0.02, "data": 0.0, "cloud_devops": 0.05, "ai_ml": -0.1, "practice": 0.01}
    stance = {"language": ei.SUBSTITUTABLE, "framework": ei.NEUTRAL, "data": ei.NEUTRAL,
              "cloud_devops": ei.SUBSTITUTABLE, "ai_ml": ei.COMPLEMENT, "practice": ei.NEUTRAL}
    production = pd.DataFrame([{"skill": t["skill"], "category": t["category"], "e_s": e[t["category"]],
                                "stance": stance[t["category"]]} for t in taxonomy])
    return values, production, taxonomy


def test_build_agreement_writes_a_flag_per_skill_and_lists_both_groups():
    values, production, taxonomy = _fake_world()
    agreement, robustness = ei.build_agreement(values, production, taxonomy)
    assert agreement["production_stance_changed"] is False
    assert set(robustness["skill"]) == {t["skill"] for t in taxonomy}
    assert set(robustness["stance_robust"]) <= {"true", "false"}
    flags = robustness.groupby("category")["stance_robust"].nunique()
    assert (flags == 1).all()  # a flag belongs to the category: all its skills share it
    robust, contested = agreement["robust_categories"], agreement["contested_categories"]
    assert set(robust) | set(contested) == set(ei.CATEGORY_OCCUPATIONS) and not set(robust) & set(contested)
    corr = agreement["occupation_level"]["spearman_vs_aei"]
    assert corr["msft_applicability"]["spearman_vs_aei"] < -0.9  # built as a mirror image
    assert corr["gpts_gpt4_beta"]["spearman_vs_aei"] > 0.8
    assert corr["aioe"]["n_occupations"] == 7
    ai_ml = agreement["category_level"]["categories"]["ai_ml"]
    assert ai_ml["family_z"]["aioe"] is None and ai_ml["n_voting"] == 3  # no AIOE value: abstains
    assert len(agreement["category_level"]["categories"]["language"]["index_z"]) == len(ei.INDEX_SPECS)


def test_flipping_one_family_negates_its_z_and_changes_the_views():
    values, production, taxonomy = _fake_world()
    base, _ = ei.build_agreement(values, production, taxonomy)
    flipped = {k: dict(v) for k, v in values.items()}
    flipped["msft_applicability"] = {c: (-v[0], v[1]) for c, v in values["msft_applicability"].items()}
    after, _ = ei.build_agreement(flipped, production, taxonomy)
    for cat in ei.CATEGORY_OCCUPATIONS:
        b = base["category_level"]["categories"][cat]["family_z"]["msft"]
        a = after["category_level"]["categories"][cat]["family_z"]["msft"]
        assert a == pytest.approx(-b, abs=1e-5)
    assert base["category_level"]["categories"] != after["category_level"]["categories"]


@needs_outputs
def test_committed_outputs_agree_with_each_other_and_leave_the_stance_alone():
    agreement = json.loads((DATA / "exposure_agreement.json").read_text(encoding="utf-8"))
    robustness = pd.read_csv(DATA / "exposure_robustness.csv")
    production = pd.read_csv(DATA / "exposure.csv")
    assert len(robustness) == len(production) == 40
    merged = robustness.merge(production[["skill", "stance"]], on="skill")
    assert (merged["production_stance"] == merged["stance"]).all()  # production stance untouched
    assert set(robustness.loc[robustness["stance_robust"], "category"]) == set(agreement["robust_categories"])
    assert set(robustness.loc[~robustness["stance_robust"], "category"]) == set(agreement["contested_categories"])
    assert agreement["baseline_index"] == "aei_automation"
    table = pd.read_csv(DATA / "exposure_indices.csv")
    assert set(table["source"]) == {s.id for s in ei.INDEX_SPECS}
    assert table["onet_soc"].nunique() == 8


@needs_outputs
@needs_raw
def test_outputs_can_be_rebuilt_from_the_raw_files():
    table, agreement, robustness = ei.build_all(write=False)
    committed = pd.read_csv(DATA / "exposure_indices.csv")
    pd.testing.assert_frame_equal(
        table.drop(columns=["mapping_note"]).reset_index(drop=True),
        committed.drop(columns=["mapping_note"]).reset_index(drop=True), check_dtype=False)
    stored = json.loads((DATA / "exposure_agreement.json").read_text(encoding="utf-8"))
    assert agreement["robust_categories"] == stored["robust_categories"]
    assert agreement["occupation_level"] == stored["occupation_level"]
    stored_flags = pd.read_csv(DATA / "exposure_robustness.csv")["stance_robust"].astype(str).str.lower()
    assert robustness["stance_robust"].tolist() == stored_flags.tolist()


# --- k regression -----------------------------------------------------------------------

def test_wls_recovers_a_known_slope_exactly_without_noise():
    x = np.array([-0.1, -0.02, 0.0, 0.02, 0.05])
    a, b = ke.wls(x, 0.3 - 6.0 * x)
    assert b == pytest.approx(-6.0) and a == pytest.approx(0.3)


def test_wls_recovers_a_known_slope_with_noise_within_tolerance():
    rng = np.random.default_rng(7)
    x = rng.choice([-0.12, -0.02, 0.01, 0.02, 0.05], size=400)
    y = 0.2 + 5.0 * x + rng.normal(0, 0.05, size=x.size)
    for weights in (None, rng.integers(10, 500, size=x.size)):
        assert ke.wls(x, y, weights)[1] == pytest.approx(5.0, abs=0.25)


def test_wls_weights_move_the_fit_toward_heavy_points():
    x = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.0, 1.0, 2.0, 10.0])
    unweighted = ke.wls(x, y)[1]
    heavy_tail = ke.wls(x, y, [1, 1, 1, 100])[1]
    light_tail = ke.wls(x, y, [100, 100, 100, 1])[1]
    assert light_tail < unweighted < heavy_tail


def test_wls_needs_spread_in_x():
    with pytest.raises(ValueError):
        ke.wls([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])


def test_wls_two_regressors_recovers_both_coefficients():
    rng = np.random.default_rng(3)
    x, z = rng.normal(size=200), rng.normal(size=200)
    y = 1.0 + 2.0 * x - 3.0 * z
    b, c = ke.wls_two(x, z, y)
    assert b == pytest.approx(2.0) and c == pytest.approx(-3.0)


def test_k_from_b_follows_the_linearisation():
    # a skill at share 0.1 with b = -8 logit per unit e
    s_bar, b = 0.1, -8.0
    k = ke.k_from_b(b, s_bar)
    assert k == pytest.approx(0.9 * 8.0)
    # small exposure: the scenario shift -k * e matches the exact logistic change
    e = 0.01
    exact = inv_logit(np.log(0.1 / 0.9) + b * e) / 0.1 - 1
    assert -k * e == pytest.approx(exact, abs=0.005)
    # a large shift: the linearisation overstates the fall (it is first order only)
    e = 0.05
    exact = inv_logit(np.log(0.1 / 0.9) + b * e) / 0.1 - 1
    assert exact < 0 and -k * e < exact
    # a positive slope (exposed skills rose) gives a negative k
    assert ke.k_from_b(2.0, 0.1) < 0


def test_k_interval_swaps_the_ends_and_keeps_order():
    lo, hi = ke.k_interval(-12.0, 4.0, 0.15)
    assert lo == pytest.approx(-0.85 * 4.0) and hi == pytest.approx(0.85 * 12.0) and lo < hi


def test_years_since_release_uses_the_middle_of_the_window():
    assert ke.years_since_release(("2023-11", "2024-10")) == pytest.approx(1.5)
    assert ke.years_since_release(("2025-11", "2026-10")) == pytest.approx(3.5)


# --- bootstrap --------------------------------------------------------------------------

def _clustered_data():
    rng = np.random.default_rng(11)
    cats = np.repeat(["a", "b", "c", "d", "e"], 6)
    e_by_cat = {"a": -0.1, "b": -0.02, "c": 0.01, "d": 0.02, "e": 0.05}
    x = np.array([e_by_cat[c] for c in cats])
    y = 0.1 - 6.0 * x + rng.normal(0, 0.15, size=x.size)
    return x, y, np.arange(10, 40), cats


def test_bootstrap_is_deterministic_with_a_seed_and_changes_with_another():
    x, y, w, _ = _clustered_data()
    a = ke.bootstrap_slope(x, y, w, n_boot=300, seed=5)
    b = ke.bootstrap_slope(x, y, w, n_boot=300, seed=5)
    c = ke.bootstrap_slope(x, y, w, n_boot=300, seed=6)
    assert a == b
    assert (a["ci_low"], a["ci_high"]) != (c["ci_low"], c["ci_high"])


def test_cluster_bootstrap_is_deterministic_and_brackets_the_estimate():
    x, y, w, cats = _clustered_data()
    one = ke.bootstrap_slope(x, y, w, cats, n_boot=400, seed=9)
    two = ke.bootstrap_slope(x, y, w, cats, n_boot=400, seed=9)
    assert one == two
    assert one["ci_low"] < ke.wls(x, y, w)[1] < one["ci_high"]  # the estimate is inside


def test_bootstrap_ci_brackets_the_estimate_and_orders_its_ends():
    x, y, w, _ = _clustered_data()
    ci = ke.bootstrap_slope(x, y, w, n_boot=500, seed=1)
    estimate = ke.wls(x, y, w)[1]
    assert ci["ci_low"] < estimate < ci["ci_high"] and estimate == pytest.approx(-6.0, abs=2.0)
    assert ci["n_valid"] == 500


def test_bootstrap_with_no_spread_returns_no_ci():
    out = ke.bootstrap_slope([0.1] * 5, [1, 2, 3, 4, 5], n_boot=20, seed=1)
    assert out["ci_low"] is None and out["n_valid"] == 0


def test_category_regression_has_five_points_and_a_permutation_p():
    df = pd.DataFrame({
        "category": ["a", "a", "b", "c", "d", "e"], "e_s": [-0.1, -0.1, -0.02, 0.01, 0.02, 0.05],
        "d": [0.7, 0.5, 0.2, 0.0, -0.1, -0.3], "w": [10, 20, 30, 40, 50, 60],
    })
    out = ke.category_regression(df)
    assert out["n_categories"] == 5 and out["b_unweighted"] < 0
    assert out["p_permutation_unweighted"] == pytest.approx(1 / 120)  # only the observed ordering is as steep
    assert out["t_df"] == 3 and out["b_unweighted_t_ci"][0] < out["b_unweighted"] < out["b_unweighted_t_ci"][1]
    assert set(out["leave_one_category_out_b_unweighted"]) == set("abcde")


def test_category_regression_with_too_few_points_says_so():
    df = pd.DataFrame({"category": ["a", "b"], "e_s": [0.0, 0.1], "d": [0.0, 1.0], "w": [1, 1]})
    assert "no regression" in ke.category_regression(df)["note"]


# --- verdict and end-to-end on synthetic demand -----------------------------------------

def test_verdict_says_cannot_pin_down_when_ci_includes_zero():
    v = ke.verdict_from([-1.0, 3.0], {"a": -5.0, "b": -4.0})
    assert v["pins_k_down"] is False and "includes 0" in v["verdict"]


def test_verdict_says_cannot_pin_down_when_the_sign_flips():
    v = ke.verdict_from([1.0, 3.0], {"a": -5.0, "b": 2.0})
    assert v["pins_k_down"] is False and "sign" in v["verdict"]


def test_verdict_pins_k_down_only_when_ci_excludes_zero_and_signs_agree():
    v = ke.verdict_from([1.0, 3.0], {"a": -5.0, "b": -2.0})
    assert v["pins_k_down"] is True


def test_k_line_wording():
    base = {"assumed_k_in_production": 2.0,
            "headline": {"k_per_12m": 1.8, "k_per_12m_ci_cluster_bootstrap": [-1.0, 2.9]}}
    cannot = ke.k_line({**base, "verdict": {"pins_k_down": False}})
    assert cannot.startswith("The data cannot pin k down") and "k = 2" in cannot and "-1.0 to 2.9" in cannot
    pinned = ke.k_line({**base, "verdict": {"pins_k_down": True}})
    assert pinned == "Data-implied k: 1.8 (95% CI -1.0 to 2.9); we use k = 2 as a labelled assumption."
    assert "cannot pin" in ke.k_line({"verdict": {"pins_k_down": False}, "headline": {}})


def _synthetic_demand(true_b: float, months=94):
    """Posts and mentions per skill-month where the logit share drifts after 2022-10 by true_b * e."""
    period = pd.period_range("2019-01", periods=months, freq="M")
    e = {"s1": -0.1, "s2": -0.1, "s3": -0.02, "s4": -0.02, "s5": 0.01, "s6": 0.02, "s7": 0.05, "s8": 0.05}
    rows = []
    for t, month in enumerate(period):
        post = max(0, (month - pd.Period("2022-10", "M")).n)  # months since ChatGPT
        for skill, es in e.items():
            logit = -2.0 + true_b * es * min(post, 36) / 36.0 * 1.0
            rows.append({"month": str(month), "skill": skill, "n_posts": 200_000,
                         "mentions": int(round(200_000 * float(inv_logit(logit)))),
                         "share": 0.0, "share_smooth": 0.0, "thread_id": 1, "thread_url": ""})
    exposure = pd.DataFrame({"skill": list(e), "category": ["c1", "c1", "c2", "c2", "c3", "c4", "c5", "c5"],
                             "e_s": list(e.values())})
    return pd.DataFrame(rows), exposure


def test_estimate_recovers_the_slope_from_synthetic_demand():
    demand, exposure = _synthetic_demand(true_b=-6.0)
    out = ke.estimate(demand, exposure, n_boot=200, seed=4)
    head = out["headline"]
    # logit change after 36 months of drift = true_b * e; the recent window sits at full drift
    assert head["b"] == pytest.approx(-6.0, abs=0.3)
    s_bar = head["s_bar"]
    assert head["k_total"] == pytest.approx((1 - s_bar) * 6.0, abs=0.3)
    assert out["placebo_pre_trend"]["all_ok_skills_weighted"]["slope_b"] == pytest.approx(0.0, abs=0.05)
    assert out["method"]["n_skills_ok"] == 8


def test_estimate_is_reproducible_for_a_seed():
    demand, exposure = _synthetic_demand(true_b=4.0)
    one = ke.estimate(demand, exposure, n_boot=100, seed=2)
    two = ke.estimate(demand, exposure, n_boot=100, seed=2)
    for out in (one, two):
        out.pop("generated_at")
    assert one == two


def test_build_sample_matches_a_hand_computation():
    demand, exposure = _synthetic_demand(true_b=0.0)
    ok = ["s1", "s7"]
    df = ke.build_sample(demand, exposure, ke.PRE, ke.POST_WINDOWS["2025-11..2026-10"], ok)
    assert df["d"].abs().max() < 1e-3  # no drift: no change
    assert df.loc[df["skill"] == "s7", "e_s"].iloc[0] == 0.05
    pre_mentions = demand[(demand["skill"] == "s1") & demand["month"].between("2021-11", "2022-10")]["mentions"].sum()
    post_mentions = demand[(demand["skill"] == "s1") & demand["month"].between("2025-11", "2026-10")]["mentions"].sum()
    assert df.loc[df["skill"] == "s1", "w"].iloc[0] == pre_mentions + post_mentions


def test_window_mean_raises_on_a_missing_month():
    y = pd.DataFrame({"a": [1.0, 2.0]}, index=["2021-11", "2021-12"])
    with pytest.raises(ValueError):
        ke.window_mean(y, "2021-11", "2022-01")


@needs_outputs
def test_k_estimate_file_is_strict_json_and_states_the_verdict():
    text = (DATA / "k_estimate.json").read_text(encoding="utf-8")
    assert "NaN" not in text and "Infinity" not in text
    out = json.loads(text)
    assert out["assumed_k_in_production"] == 2.0
    assert out["verdict"]["verdict"] and isinstance(out["verdict"]["pins_k_down"], bool)
    assert out["method"]["n_skills_ok"] == 27
    assert out["headline"]["window"] == ke.PRIMARY_WINDOW
    # the same sign rule the verdict uses
    assert out["verdict"]["pins_k_down"] == (
        out["verdict"]["ci_excludes_zero"] and out["verdict"]["same_sign_in_all_specs"])


# --- the app ----------------------------------------------------------------------------

def _joined(at: AppTest) -> str:
    groups = [at.markdown, at.caption, at.info, at.success, at.warning, at.error,
              at.subheader, at.header, at.title]
    return "\n".join(e.value for group in groups for e in group)


@pytest.fixture(scope="module")
def app_run():
    return AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()


@needs_outputs
def test_app_shows_contested_flag_only_for_contested_skills(app_run):
    robustness = pd.read_csv(DATA / "exposure_robustness.csv")
    contested = robustness.loc[~robustness["stance_robust"], "skill"].iloc[0]
    robust = robustness.loc[robustness["stance_robust"], "skill"].iloc[0]

    at = app_run.selectbox(key="detail_skill").set_value(contested).run()
    stance_lines = [m.value for m in at.markdown if m.value.startswith("**AI stance:**")]
    assert len(stance_lines) == 1 and "(contested across indices)" in stance_lines[0]

    at = at.selectbox(key="detail_skill").set_value(robust).run()
    stance_lines = [m.value for m in at.markdown if m.value.startswith("**AI stance:**")]
    assert len(stance_lines) == 1 and "contested" not in stance_lines[0]


@needs_outputs
def test_method_tab_has_the_cross_check_and_the_k_line(app_run):
    assert not app_run.exception
    text = _joined(app_run)
    assert "Exposure cross-check" in text
    assert "**Contested:**" in text
    assert "k from data:" in text and "labelled assumption" in text
    frames = [d.value for d in app_run.dataframe]
    cross = [f for f in frames if "Contested?" in f.columns]
    assert len(cross) == 1 and len(cross[0]) == 6
    assert {"Category", "Our stance", "Anthropic Economic Index"} <= set(cross[0].columns)


@needs_outputs
def test_app_without_the_new_files_still_runs(tmp_path):
    """Hide the step 9 files: no cross-check section, no contested flag, no error."""
    import shutil

    shutil.copy(APP_PATH, tmp_path / "app.py")
    shutil.copytree(ROOT / "engine", tmp_path / "engine")
    data = tmp_path / "data"
    shutil.copytree(DATA, data, ignore=shutil.ignore_patterns(
        "raw", "exposure_agreement.json", "exposure_robustness.csv", "k_estimate.json"))
    at = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=TIMEOUT).run()
    assert not at.exception
    assert "Exposure cross-check" not in _joined(at)
    at = at.selectbox(key="detail_skill").set_value("AWS").run()
    assert "contested across indices" not in _joined(at)
