"""Tests for engine/scores.py."""

import json

import numpy as np
import pytest

from engine import scores as sc
from engine.forecast import HORIZON, MIN_MEAN_MENTIONS, load_demand

TOP_KEYS = {"schema_version", "generated_at", "as_of", "scenario_params", "data_window", "skills"}
SKILL_KEYS = {"skill", "sdg", "demand_share_latest", "demand_slope", "momentum", "ai_exposure",
              "stance", "status", "forecast", "evidence", "sources"}
BAND_KEYS = {"value_12m", "low", "high"}

# A fixed backtest result, so these tests do not depend on data/backtest.json.
FAKE_BACKTEST = {
    "chosen_model": "naive",
    "conformal": {"q10_by_h": [-0.3] * HORIZON, "q90_by_h": [0.2] * HORIZON},
}


@pytest.fixture(scope="module")
def demand():
    return load_demand()


@pytest.fixture(scope="module")
def built(demand):
    return sc.build_scores(backtest=FAKE_BACKTEST, demand=demand)


def check_contract(scores):
    assert set(scores) == TOP_KEYS
    assert "fixture" not in scores
    assert scores["schema_version"] == 1
    assert set(scores["scenario_params"]) == {"k"}
    assert set(scores["data_window"]) == {"from", "to"}
    assert scores["skills"]
    for s in scores["skills"]:
        assert set(s) == SKILL_KEYS
        assert s["status"] in ("ok", "insufficient_data")
        assert set(s["forecast"]) == {"moderate", "fast"}
        for scenario in s["forecast"].values():
            assert set(scenario) == BAND_KEYS
            if s["status"] == "insufficient_data":
                assert all(v is None for v in scenario.values())
            else:
                assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scenario.values())
        assert s["evidence"] and all(e.startswith("hn:") for e in s["evidence"])
        assert all(set(src) == {"name", "url", "date"} for src in s["sources"])


# fast scenario

def test_fast_scenario_formula():
    assert sc.fast_scenario(0.5, 0.1, k=2) == pytest.approx(0.4)
    assert sc.fast_scenario(0.2, -0.05, k=2) == pytest.approx(0.22)
    assert sc.fast_scenario(0.2, 0.0) == pytest.approx(0.2)


def test_fast_scenario_is_clipped_to_0_and_1():
    assert sc.fast_scenario(0.3, 0.9, k=2) == 0.0  # 1 - 1.8 < 0
    assert sc.fast_scenario(0.7, -0.5, k=2) == 1.0  # 0.7 * 2 > 1
    assert sc.fast_scenario(None, 0.1) is None


def test_default_k_is_2():
    assert sc.K == 2


# helpers

def test_slope_is_in_pp_per_year():
    share = 0.10 + 0.001 * np.arange(30)  # +0.1 pp per month
    assert sc.slope_pp_per_year(share) == pytest.approx(1.2)
    assert sc.slope_pp_per_year([0.1, 0.1, 0.1]) == pytest.approx(0.0)


def test_slope_uses_only_the_last_24_months():
    share = np.concatenate([np.linspace(0.5, 0.0, 30), np.full(24, 0.1)])
    assert sc.slope_pp_per_year(share) == pytest.approx(0.0, abs=1e-9)


def test_moderate_band_contains_the_point_and_stays_in_0_1():
    point = np.full(HORIZON, -1.5)
    band = sc.moderate_band(point, np.full(HORIZON, -0.4), np.full(HORIZON, 0.3))
    assert 0.0 < band["low"] < band["value_12m"] < band["high"] < 1.0
    assert band["value_12m"] == pytest.approx(1 / (1 + np.exp(1.5)))


# build_scores

def test_build_scores_matches_the_contract(built):
    check_contract(built)
    assert built["as_of"] == "2026-10"
    assert built["scenario_params"] == {"k": 2}
    assert built["data_window"] == {"from": "2019-01", "to": "2026-10"}


def test_build_scores_covers_every_taxonomy_skill(built):
    taxonomy = json.loads(sc.TAXONOMY_JSON.read_text(encoding="utf-8"))
    assert [s["skill"] for s in built["skills"]] == [t["skill"] for t in taxonomy]
    assert len(built["skills"]) == 40


def test_fast_values_follow_the_formula_for_every_skill(built):
    import pandas as pd
    exposure = pd.read_csv(sc.EXPOSURE_CSV).set_index("skill")
    for s in built["skills"]:
        if s["status"] != "ok":
            continue
        e_s = exposure.loc[s["skill"], "e_s"]
        for key in BAND_KEYS:
            expected = float(np.clip(s["forecast"]["moderate"][key] * (1 - 2 * e_s), 0, 1))
            assert s["forecast"]["fast"][key] == pytest.approx(expected)


def test_moderate_band_brackets_the_value_for_every_skill(built):
    for s in built["skills"]:
        if s["status"] == "ok":
            m = s["forecast"]["moderate"]
            assert m["low"] <= m["value_12m"] <= m["high"]


def test_status_follows_the_minimum_mentions_rule(built, demand):
    last12 = sorted(demand["month"].unique())[-12:]
    recent = demand[demand["month"].isin(last12)].groupby("skill")["mentions"].mean()
    for s in built["skills"]:
        expected = "ok" if recent[s["skill"]] >= MIN_MEAN_MENTIONS else "insufficient_data"
        assert s["status"] == expected


def test_sources_and_evidence_are_the_last_three_threads_plus_aei(built):
    s = built["skills"][0]
    assert len(s["evidence"]) == 3
    assert len(s["sources"]) == 4
    assert s["sources"][-1]["name"] == "Anthropic Economic Index (release 2026-06-26)"
    assert s["sources"][-1]["url"].startswith("https://huggingface.co/datasets/Anthropic/EconomicIndex")
    for e, src in zip(s["evidence"], s["sources"][:3]):
        assert src["url"].endswith(e.split(":")[1])
    assert s["sources"][2]["date"] == "2026-10-01"


def test_demand_share_latest_is_mean_of_last_three_months(built, demand):
    python = demand[demand["skill"] == "Python"].sort_values("month")["share"].to_numpy()[-3:]
    got = next(s for s in built["skills"] if s["skill"] == "Python")["demand_share_latest"]
    assert got == pytest.approx(python.mean())


def test_as_of_cuts_the_window_and_the_evidence(demand):
    out = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=demand)
    check_contract(out)
    assert out["as_of"] == "2024-06"
    assert out["data_window"]["to"] == "2024-06"
    assert out["skills"][0]["sources"][-2]["date"].startswith("2024-06")


def test_as_of_never_uses_later_data(demand):
    changed = demand.copy()
    late = changed["month"] > "2024-06"
    changed.loc[late, "mentions"] = 0
    changed.loc[late, "share"] = 0.0
    a = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=demand)
    b = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=changed)
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


def test_as_of_after_the_data_raises(demand):
    with pytest.raises(ValueError):
        sc.build_scores(as_of="2030-01", backtest=FAKE_BACKTEST, demand=demand)


def test_written_file_matches_the_contract_if_present():
    if not sc.SCORES_JSON.exists():
        pytest.skip("data/skill_scores.json not generated yet")
    check_contract(json.loads(sc.SCORES_JSON.read_text(encoding="utf-8")))
