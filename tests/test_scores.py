"""Tests for engine/scores.py."""

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from engine import scores as sc
from engine.forecast import (HORIZON, MIN_MEAN_MENTIONS, inv_logit, load_demand, logit_series,
                             skill_status, trend_label, wide_tables)

TOP_KEYS = {"schema_version", "generated_at", "as_of", "partial_month", "nowcast", "scenario_params",
            "interval", "notes", "data_window", "skills"}
SKILL_KEYS = {"skill", "sdg", "demand_share_latest", "mentions_last3", "posts_last3", "level_now",
              "demand_slope", "momentum", "ai_exposure", "stance", "status", "note", "trend_label",
              "trend_p", "mentions_last12", "posts_last12", "mentions_prev12", "posts_prev12",
              "forecast", "scenario_shift_pp", "band_width_pp", "evidence", "sources"}
BAND_KEYS = {"value_12m", "low", "high"}
STATUSES = ("ok", "low_volume", "rare")
LOW_VOLUME_NOTE = "Too few posts to forecast; observed counts shown."

# Only the date of the backtest file is used by build_scores.
FAKE_BACKTEST = {"generated_at": "2026-10-21T20:52:34Z"}
TODAY = datetime(2026, 10, 22, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def demand():
    return load_demand()


@pytest.fixture(scope="module")
def built(demand):
    return sc.build_scores(backtest=FAKE_BACKTEST, demand=demand, today=TODAY)


def by_name(scores, name):
    return next(s for s in scores["skills"] if s["skill"] == name)


def check_contract(scores):
    assert set(scores) == TOP_KEYS
    assert "fixture" not in scores
    assert scores["schema_version"] == 1
    assert isinstance(scores["partial_month"], bool)
    assert set(scores["scenario_params"]) == {"k"}
    assert set(scores["data_window"]) == {"from", "to"}
    assert any("not time-cut" in n for n in scores["notes"])
    assert scores["skills"]
    for s in scores["skills"]:
        assert set(s) == SKILL_KEYS
        assert s["status"] in STATUSES
        assert set(s["forecast"]) == {"moderate", "fast"}
        for scenario in s["forecast"].values():
            assert set(scenario) == BAND_KEYS
            if s["status"] == "ok":
                assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scenario.values())
            else:
                assert all(v is None for v in scenario.values())
        if s["status"] == "ok":
            assert isinstance(s["scenario_shift_pp"], float) and s["band_width_pp"] > 0
            assert s["note"] is None
        else:
            assert s["scenario_shift_pp"] is None and s["band_width_pp"] is None
            assert s["note"]
        assert 0.0 <= s["level_now"] <= 1.0 and 0.0 <= s["demand_share_latest"] <= 1.0
        assert s["trend_label"] in (None, "Rising", "Falling", "No clear change")
        assert (s["trend_label"] is None) == (s["trend_p"] is None)
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


def test_moderate_band_is_point_plus_minus_q_sigma_on_the_logit_scale():
    point = np.full(HORIZON, -1.5)
    band = sc.moderate_band(point, q=1.2, sigma=0.25)
    assert band["value_12m"] == pytest.approx(1 / (1 + np.exp(1.5)))
    assert band["low"] == pytest.approx(inv_logit(-1.5 - 0.3))
    assert band["high"] == pytest.approx(inv_logit(-1.5 + 0.3))
    assert 0.0 < band["low"] < band["value_12m"] < band["high"] < 1.0


# build_scores

def test_build_scores_matches_the_contract(built):
    check_contract(built)
    assert built["as_of"] == "2026-10"
    assert built["scenario_params"] == {"k": 2}
    assert built["data_window"] == {"from": "2019-01", "to": "2026-10"}
    assert built["interval"]["label"] == "80% target band"
    assert built["interval"]["model"] in ("naive", "naive3")


def test_build_scores_covers_every_taxonomy_skill(built):
    taxonomy = json.loads(sc.TAXONOMY_JSON.read_text(encoding="utf-8"))
    assert [s["skill"] for s in built["skills"]] == [t["skill"] for t in taxonomy]
    assert len(built["skills"]) == 40


def test_fast_values_follow_the_formula_for_every_skill(built):
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
            assert m["low"] < m["value_12m"] < m["high"]


def test_scenario_shift_and_band_width_fields(built):
    ok = [s for s in built["skills"] if s["status"] == "ok"]
    assert ok
    for s in ok:
        m, f = s["forecast"]["moderate"], s["forecast"]["fast"]
        assert s["scenario_shift_pp"] == pytest.approx((f["value_12m"] - m["value_12m"]) * 100)
        assert s["band_width_pp"] == pytest.approx((m["high"] - m["low"]) * 100)


# statuses

def test_status_follows_the_rules_on_real_data(built, demand):
    mentions, _ = wide_tables(demand)
    for s in built["skills"]:
        m = mentions[s["skill"]].to_numpy()
        if m[-12:].mean() >= MIN_MEAN_MENTIONS:
            expected = "ok"
        elif m[-24:].sum() >= 30:
            expected = "low_volume"
        else:
            expected = "rare"
        assert s["status"] == expected == skill_status(m)


def test_low_volume_and_rare_skills_get_no_forecast_but_keep_counts():
    d = load_demand()
    last24 = sorted(d["month"].unique())[-24:]
    last12 = last24[-12:]
    # Python: 3 mentions a month for 24 months = 72 mentions, 3/month -> low_volume
    d.loc[(d["skill"] == "Python") & d["month"].isin(last24), "mentions"] = 3
    # Go: 1 mention in 24 months -> rare
    d.loc[(d["skill"] == "Go") & d["month"].isin(last24), "mentions"] = 0
    d.loc[(d["skill"] == "Go") & (d["month"] == last24[-1]), "mentions"] = 1
    out = sc.build_scores(backtest=FAKE_BACKTEST, demand=d, today=TODAY)
    check_contract(out)
    low, rare = by_name(out, "Python"), by_name(out, "Go")
    assert low["status"] == "low_volume" and rare["status"] == "rare"
    assert low["note"] == LOW_VOLUME_NOTE
    assert low["mentions_last12"] == 36 and low["mentions_prev12"] == 36
    assert low["posts_last12"] == int(d[(d["skill"] == "Python") & d["month"].isin(last12)]["n_posts"].sum())
    assert low["trend_label"] in ("Rising", "Falling", "No clear change")  # 72 mentions: labelled
    assert rare["trend_label"] is None and rare["trend_p"] is None
    assert rare["mentions_last12"] == 1


# scale fix

def test_demand_share_latest_is_pooled_last_three_months(built, demand):
    py = demand[demand["skill"] == "Python"].sort_values("month").tail(3)
    s = by_name(built, "Python")
    assert s["mentions_last3"] == int(py["mentions"].sum())
    assert s["posts_last3"] == int(py["n_posts"].sum())
    assert s["demand_share_latest"] == pytest.approx(py["mentions"].sum() / py["n_posts"].sum())


def test_level_now_is_model_scale_and_matches_naive3_forecast(built, demand):
    y = logit_series(demand=demand)
    for s in built["skills"]:
        assert s["level_now"] == pytest.approx(float(inv_logit(y[s["skill"]].to_numpy()[-3:].mean())))
    if built["interval"]["model"] == "naive3":
        for s in built["skills"]:
            if s["status"] == "ok":
                assert s["forecast"]["moderate"]["value_12m"] == pytest.approx(s["level_now"])
    # level_now differs from the raw share (smoothed, mean of logits): the two scales must not mix
    assert any(abs(s["level_now"] - s["demand_share_latest"]) > 1e-4 for s in built["skills"])


def test_counts_and_trend_fields_match_the_data(built, demand):
    mentions, posts = wide_tables(demand)
    y = logit_series(demand=demand)
    for s in built["skills"]:
        name = s["skill"]
        m, p = mentions[name].to_numpy(), posts[name].to_numpy()
        assert (s["mentions_last12"], s["posts_last12"]) == (int(m[-12:].sum()), int(p[-12:].sum()))
        assert (s["mentions_prev12"], s["posts_prev12"]) == (int(m[-24:-12].sum()), int(p[-24:-12].sum()))
        label, p_value = trend_label(y[name].to_numpy(), m)
        assert s["trend_label"] == label
        assert s["trend_p"] == (None if p_value is None else pytest.approx(p_value))
        if s["status"] == "rare":
            assert s["trend_label"] is None
        else:
            assert s["trend_label"] is not None


# sources, partial month, as_of

def test_sources_are_the_last_three_threads_then_aei_then_the_backtest(built):
    s = built["skills"][0]
    assert len(s["evidence"]) == 3
    assert len(s["sources"]) == 5
    assert s["sources"][3]["name"] == "Anthropic Economic Index (release 2026-06-26)"
    assert s["sources"][3]["url"].startswith("https://huggingface.co/datasets/Anthropic/EconomicIndex")
    assert s["sources"][4] == {
        "name": f"Verity backtest (rolling conformal, {built['interval']['model']})",
        "url": "data/backtest.json",
        "date": "2026-10-21",
    }
    for e, src in zip(s["evidence"], s["sources"][:3]):
        assert src["url"].endswith(e.split(":")[1])
    assert s["sources"][2]["date"] == "2026-10-01"


def test_partial_month_is_true_only_when_the_last_month_is_the_current_month(demand):
    assert sc.build_scores(backtest=FAKE_BACKTEST, demand=demand, today=TODAY)["partial_month"] is True
    later = datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert sc.build_scores(backtest=FAKE_BACKTEST, demand=demand, today=later)["partial_month"] is False
    old = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)
    assert old["partial_month"] is False


def test_as_of_cuts_the_window_and_the_evidence(demand):
    out = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)
    check_contract(out)
    assert out["as_of"] == "2024-06"
    assert out["data_window"]["to"] == "2024-06"
    assert out["skills"][0]["sources"][2]["date"].startswith("2024-06")


def test_as_of_never_uses_later_data(demand):
    changed = demand.copy()
    late = changed["month"] > "2024-06"
    changed.loc[late, "mentions"] = 0
    changed.loc[late, "share"] = 0.0
    a = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)
    b = sc.build_scores(as_of="2024-06", backtest=FAKE_BACKTEST, demand=changed, today=TODAY)
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b  # model choice, band, point forecasts, trend labels: everything


def test_earliest_as_of_works_and_earlier_raises_a_clear_error(demand):
    out = sc.build_scores(as_of="2023-11", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)
    check_contract(out)
    assert out["interval"]["earliest_supported_as_of"] == "2023-11"
    with pytest.raises(ValueError, match="Earliest supported as_of is 2023-11"):
        sc.build_scores(as_of="2023-10", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)
    with pytest.raises(ValueError, match="too early"):
        sc.build_scores(as_of="2021-01", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)


def test_as_of_after_the_data_raises(demand):
    with pytest.raises(ValueError):
        sc.build_scores(as_of="2030-01", backtest=FAKE_BACKTEST, demand=demand, today=TODAY)


def test_written_file_matches_the_contract_if_present():
    if not sc.SCORES_JSON.exists():
        pytest.skip("data/skill_scores.json not generated yet")
    check_contract(json.loads(sc.SCORES_JSON.read_text(encoding="utf-8")))


# data_dir

DATA_FILES = ("demand_monthly.csv", "taxonomy.json", "exposure.csv", "backtest.json", "hn_threads.csv")


@pytest.fixture
def data_copy(tmp_path):
    """A copy of the five input files in a temp folder."""
    for name in DATA_FILES:
        shutil.copy(sc.DATA_DIR / name, tmp_path / name)
    return tmp_path


def _without_time(scores):
    scores = dict(scores)
    scores.pop("generated_at")
    return scores


def test_data_dir_copy_gives_the_same_scores_as_the_repo_folder(data_copy):
    default = sc.build_scores(as_of="2025-06", today=TODAY)
    copied = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)
    assert _without_time(copied) == _without_time(default)
    check_contract(copied)


def test_every_input_comes_from_data_dir(data_copy):
    """Change each input in the copy: the result must change; the repo folder is not read."""
    base = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)

    exposure = pd.read_csv(data_copy / "exposure.csv")
    exposure.loc[exposure["skill"] == "Python", "ai_exposure"] = 0.123
    exposure.to_csv(data_copy / "exposure.csv", index=False)
    changed = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)
    assert by_name(changed, "Python")["ai_exposure"] == pytest.approx(0.123)

    threads = pd.read_csv(data_copy / "hn_threads.csv")
    threads.loc[threads["month"] == "2025-06", "title"] = "Changed title"
    threads.to_csv(data_copy / "hn_threads.csv", index=False)
    changed = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)
    assert by_name(changed, "Python")["sources"][2]["name"] == "Changed title"

    backtest = json.loads((data_copy / "backtest.json").read_text(encoding="utf-8"))
    backtest["generated_at"] = "2001-02-03T00:00:00Z"
    (data_copy / "backtest.json").write_text(json.dumps(backtest), encoding="utf-8")
    changed = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)
    assert by_name(changed, "Python")["sources"][-1]["date"] == "2001-02-03"

    taxonomy = json.loads((data_copy / "taxonomy.json").read_text(encoding="utf-8"))
    (data_copy / "taxonomy.json").write_text(json.dumps(taxonomy[:5]), encoding="utf-8")
    assert len(sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)["skills"]) == 5

    demand = pd.read_csv(data_copy / "demand_monthly.csv")
    demand[demand["month"] <= "2025-03"].to_csv(data_copy / "demand_monthly.csv", index=False)
    assert sc.build_scores(today=TODAY, data_dir=data_copy)["as_of"] == "2025-03"
    assert base["as_of"] == "2025-06"


def test_missing_thread_month_skips_the_source_and_does_not_raise(data_copy):
    threads = pd.read_csv(data_copy / "hn_threads.csv")
    threads[threads["month"] != "2025-06"].to_csv(data_copy / "hn_threads.csv", index=False)
    out = sc.build_scores(as_of="2025-06", today=TODAY, data_dir=data_copy)
    check_contract(out)
    names = [s["name"] for s in by_name(out, "Python")["sources"]]
    assert len(names) == 4  # two threads, AEI, backtest
    assert not any("June 2025" in n for n in names)


def test_thread_sources_skips_unknown_months():
    threads = pd.DataFrame({"month": ["2025-01"], "title": ["t"], "url": ["u"],
                            "created_at": ["2025-01-02T00:00:00Z"]})
    assert sc._thread_sources(threads, ["2024-12", "2025-01"]) == [
        {"name": "t", "url": "u", "date": "2025-01-02"}]


def test_build_scores_writes_no_file(data_copy):
    before = {p.name: p.read_bytes() for p in data_copy.iterdir()}
    sc.build_scores(as_of="2024-06", today=TODAY, data_dir=data_copy)
    assert {p.name: p.read_bytes() for p in data_copy.iterdir()} == before


def test_main_writes_into_data_dir(data_copy):
    repo_file = sc.SCORES_JSON.read_bytes() if sc.SCORES_JSON.exists() else None
    assert sc.main(data_copy) == 0
    check_contract(json.loads((data_copy / "skill_scores.json").read_text(encoding="utf-8")))
    assert (sc.SCORES_JSON.read_bytes() if sc.SCORES_JSON.exists() else None) == repo_file


def test_missing_backtest_in_data_dir_raises_a_clear_error(data_copy):
    (data_copy / "backtest.json").unlink()
    with pytest.raises(FileNotFoundError, match="backtest.json"):
        sc.build_scores(today=TODAY, data_dir=data_copy)
