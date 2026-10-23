"""Tests for engine/role_forecast.py and engine/role_backtest.py.

Small synthetic role tables for the rules, the real data files for reproducibility and the schema.
"""
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine import backtest as bt
from engine import forecast as fc
from engine import role_backtest as rb
from engine import role_forecast as rf
from engine import roles as roles_mod

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TODAY = datetime(2026, 10, 23, tzinfo=timezone.utc)
FAKE_BACKTEST = {"generated_at": "2026-10-23T00:00:00Z"}
needs_real_data = pytest.mark.skipif(
    not all((DATA / n).exists() for n in ("role_forecast.json", "role_backtest.json", "role_demand_monthly.csv")),
    reason="role files not generated yet")


def make_roles(n_months=94, start="2019-01", seed=3, means=None):
    """Role table in the shape engine.forecast expects (role id in the `skill` column).

    The months are real hn_threads months (2019-01 on), because role_forecast_for names thread sources.
    """
    means = means or {"data_engineer": 30, "backend_engineer": 45, "mobile_developer": 12, "ml_engineer": 25}
    rng = np.random.default_rng(seed)
    months = [str(p) for p in pd.period_range(start, periods=n_months, freq="M")]
    rows = []
    for rid, mean in means.items():
        counts = rng.poisson(mean, n_months)
        for month, m in zip(months, counts):
            rows.append({"month": month, "skill": rid, "mentions": int(m), "n_posts": 400})
    return pd.DataFrame(rows)


def forecast(demand, as_of=None):
    return rf.role_forecast_for(as_of=as_of, backtest=FAKE_BACKTEST, demand=demand, today=TODAY)


def strip(doc):
    return {k: v for k, v in doc.items() if k != "generated_at"}


# --- no duplicated maths ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["forecast_skill", "band_offsets", "choose_model", "choice_scores",
                                  "build_residual_tables", "has_enough_data", "trend_label", "volatility",
                                  "logit_series", "inv_logit", "wide_tables"])
def test_role_forecast_uses_the_shared_function_objects(name):
    assert getattr(rf, name) is getattr(fc, name)


def test_role_backtest_calls_the_skill_backtest():
    assert rb.run_backtest is bt.run_backtest
    assert rb.month_range is bt.month_range


def test_role_modules_define_no_forecast_maths_of_their_own():
    """No function in the role modules is named like an engine.forecast function, and no log or exp call."""
    forbidden = set(dir(fc)) & {"logit", "inv_logit", "smoothed_share", "forecast_skill", "band_offsets",
                                "trend_label", "volatility", "choose_model", "has_enough_data"}
    for path in (ROOT / "engine" / "role_forecast.py", ROOT / "engine" / "role_backtest.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert not defined & forbidden, (path.name, defined & forbidden)
        assert not re.search(r"\bnp\.(log|exp|quantile|polyfit|std)\b", path.read_text(encoding="utf-8"))


def test_output_equals_the_shared_functions_applied_by_hand():
    demand = make_roles()
    doc = forecast(demand)
    y = fc.logit_series(demand=demand)
    mentions, _ = fc.wide_tables(demand)
    tables = fc.build_residual_tables(demand, fc.PRODUCTION_MODELS)
    model = fc.choose_model(tables, doc["as_of"])
    q = fc.band_offsets(tables[model], doc["as_of"], 12)
    assert doc["interval"]["model"] == model
    assert doc["interval"]["q_h12"] == pytest.approx(q)
    for rid, r in doc["roles"].items():
        ys = y[rid].to_numpy()
        point = fc.forecast_skill(ys, model, 12)[11]
        half = q * fc.volatility(ys)
        f = r["forecast_moderate"]
        assert f["value_12m"] == pytest.approx(float(fc.inv_logit(point)))
        assert f["low"] == pytest.approx(float(fc.inv_logit(point - half)))
        assert f["high"] == pytest.approx(float(fc.inv_logit(point + half)))
        assert r["level_now"] == pytest.approx(float(fc.inv_logit(ys[-3:].mean())))
        label, p = fc.trend_label(ys, mentions[rid].to_numpy())
        assert r["trend"]["label"] == label
        assert r["trend"]["p"] == pytest.approx(p)


def test_model_choice_is_naive_or_naive3_by_the_skill_rule():
    doc = forecast(make_roles())
    assert doc["interval"]["model"] in ("naive", "naive3")
    scores = doc["interval"]["model_scores_h12_pp"]
    assert set(scores) == {"naive", "naive3"}
    assert doc["interval"]["model"] == min(scores, key=scores.get)


# --- band ------------------------------------------------------------------------------

def test_band_contains_the_point_and_is_inside_0_1():
    doc = forecast(make_roles())
    for r in doc["roles"].values():
        f = r["forecast_moderate"]
        assert 0.0 < f["low"] < f["value_12m"] < f["high"] < 1.0
        assert r["band_width_pp"] == pytest.approx((f["high"] - f["low"]) * 100.0)


@needs_real_data
def test_band_contains_the_point_in_the_real_file():
    doc = json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8"))
    ok = [r for r in doc["roles"].values() if r["status"] == "ok"]
    assert ok
    for r in ok:
        f = r["forecast_moderate"]
        assert f["low"] < f["value_12m"] < f["high"]


# --- as_of: no later data --------------------------------------------------------------

def test_as_of_ignores_later_months():
    demand = make_roles()
    as_of = "2025-03"
    base = forecast(demand, as_of)
    scrambled = demand.copy()
    later = scrambled["month"] > as_of
    rng = np.random.default_rng(99)
    scrambled.loc[later, "mentions"] = rng.integers(0, 200, later.sum())
    scrambled.loc[later, "n_posts"] = 900
    assert strip(forecast(scrambled, as_of)) == strip(base)
    assert base["as_of"] == as_of
    assert all(r["as_of"] == as_of for r in base["roles"].values())


def test_as_of_equal_to_truncated_table():
    demand = make_roles()
    cut = demand[demand["month"] <= "2024-06"]
    assert strip(forecast(demand, "2024-06")) == strip(forecast(cut))


def test_as_of_is_validated():
    demand = make_roles()
    with pytest.raises(ValueError, match="too early"):
        forecast(demand, "2023-01")
    with pytest.raises(ValueError, match="after the last month"):
        forecast(demand, "2030-01")
    with pytest.raises(ValueError, match="YYYY-MM"):
        forecast(demand, "2024/06")


def test_partial_month_follows_today():
    demand = make_roles()
    last = demand["month"].max()
    assert forecast(demand)["partial_month"] is (last == TODAY.strftime("%Y-%m"))
    far = rf.role_forecast_for(backtest=FAKE_BACKTEST, demand=demand,
                               today=datetime(2031, 1, 1, tzinfo=timezone.utc))
    assert far["partial_month"] is False


# --- minimum-data rule -----------------------------------------------------------------

def test_low_volume_role_gets_counts_and_no_band():
    demand = make_roles(means={"data_engineer": 30, "backend_engineer": 45, "mobile_developer": 12,
                               "ml_engineer": 25})
    # ml_engineer falls to 3 mentions a month over the last 12 months; the other roles stay as they were
    last12 = demand["month"].isin(sorted(demand["month"].unique())[-12:]) & (demand["skill"] == "ml_engineer")
    demand.loc[last12, "mentions"] = 3
    doc = forecast(demand)
    low = doc["roles"]["ml_engineer"]
    assert low["status"] == "low_volume"
    assert low["forecast_moderate"] == {"value_12m": None, "low": None, "high": None}
    assert low["band_width_pp"] is None
    assert low["note"]
    assert low["share_now"]["mentions"] == 9 and low["share_now"]["posts"] == 1200
    assert low["share_now"]["value"] == pytest.approx(9 / 1200)
    assert low["trend"]["mentions_last12"] == 36
    assert doc["roles"]["data_engineer"]["status"] == "ok"
    assert doc["roles"]["data_engineer"]["forecast_moderate"]["value_12m"] is not None


@pytest.mark.parametrize("per_month, status", [(5, "ok"), (4, "low_volume")])
def test_the_limit_is_a_mean_of_5_mentions_a_month(per_month, status):
    demand = make_roles()
    months = sorted(demand["month"].unique())[-12:]
    mask = demand["month"].isin(months) & (demand["skill"] == "mobile_developer")
    demand.loc[mask, "mentions"] = per_month
    assert forecast(demand)["roles"]["mobile_developer"]["status"] == status


def test_low_volume_role_is_left_out_of_the_pool_at_that_origin():
    """The pooled quantile skips a role below the limit at the origin, as for skills."""
    demand = make_roles()
    months = sorted(demand["month"].unique())[-12:]
    demand.loc[demand["month"].isin(months) & (demand["skill"] == "mobile_developer"), "mentions"] = 0
    table = fc.build_residual_tables(demand, ("naive3",))["naive3"]
    j = table.skills.index("mobile_developer")
    assert not table.eligible[-1, j]
    assert table.eligible[-1, table.skills.index("data_engineer")]
    assert forecast(demand)["roles"]["mobile_developer"]["status"] == "low_volume"


def test_unranked_roles_are_excluded_and_listed():
    roles = roles_mod.load_roles(DATA / "roles.json")
    ids = rf.ranked_role_ids(roles)
    assert "analytics_engineer" not in ids
    assert len(ids) == 8
    frame = rf.role_demand_frame(path=DATA / "role_demand_monthly.csv", role_ids=ids)
    assert set(frame["skill"]) == set(ids)
    assert "role_id" not in frame.columns
    doc = rf.role_forecast_for(backtest=FAKE_BACKTEST, today=TODAY)
    assert set(doc["roles"]) == set(ids)
    assert [e["role_id"] for e in doc["excluded_roles"]] == ["analytics_engineer"]


def test_missing_role_backtest_file_is_a_clear_error(tmp_path):
    for name in ("roles.json", "role_demand_monthly.csv", "hn_threads.csv"):
        (tmp_path / name).write_bytes((DATA / name).read_bytes())
    with pytest.raises(FileNotFoundError, match="engine.role_backtest"):
        rf.role_forecast_for(data_dir=tmp_path)


# --- consistency with the other role files ---------------------------------------------

@needs_real_data
def test_trend_labels_match_role_trends_json():
    doc = json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8"))
    trends = json.loads((DATA / "role_trends.json").read_text(encoding="utf-8"))
    assert doc["as_of"] == trends["as_of"]
    for rid, r in doc["roles"].items():
        t = trends["roles"][rid]
        assert r["trend"]["label"] == t["trend_label"]
        assert r["trend"]["p"] == pytest.approx(t["trend_p"])
        assert r["trend"]["mentions_last12"] == t["mentions_last12"]
        assert r["trend"]["posts_prev12"] == t["posts_prev12"]


@needs_real_data
def test_real_file_is_what_the_engine_builds_from_the_csv():
    stored = json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8"))
    backtest = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    fresh = rf.role_forecast_for(backtest=backtest, today=TODAY)
    assert strip(fresh) == strip(stored)


@needs_real_data
def test_share_now_is_pooled_over_3_months_with_m_over_n():
    doc = json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8"))
    csv = pd.read_csv(DATA / "role_demand_monthly.csv")
    for rid, r in doc["roles"].items():
        last3 = csv[csv["role_id"] == rid].sort_values("month").tail(3)
        assert r["share_now"]["mentions"] == last3["mentions"].sum()
        assert r["share_now"]["posts"] == last3["n_posts"].sum()
        assert r["share_now"]["value"] == pytest.approx(last3["mentions"].sum() / last3["n_posts"].sum())
        assert r["share_now"]["months"] == list(last3["month"])


@needs_real_data
def test_real_file_as_of_slider_matches_the_truncated_csv():
    """role_forecast_for(as_of) equals the forecast built from a CSV cut at as_of (the as-of slider)."""
    backtest = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    as_of = "2024-09"
    doc = rf.role_forecast_for(as_of=as_of, backtest=backtest, today=TODAY)
    cut = rf.role_demand_frame(as_of, path=DATA / "role_demand_monthly.csv",
                               role_ids=rf.ranked_role_ids(roles_mod.load_roles(DATA / "roles.json")))
    assert strip(rf.role_forecast_for(backtest=backtest, demand=cut, today=TODAY)) == strip(doc)
    assert doc["as_of"] == as_of and doc["data_window"]["to"] == as_of


# --- the backtest ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_result():
    return rb.run_role_backtest(make_roles(n_months=96),
                                bt.month_range("2022-01", "2022-06"),
                                bt.month_range("2023-11", "2024-04"),
                                bt.month_range("2021-12", "2022-06"))


def test_backtest_says_roles_not_skills(synthetic_result):
    text = json.dumps(synthetic_result)
    assert "skill" not in text.lower().replace("role_ids", "")
    assert synthetic_result["kind"] == "role"
    assert synthetic_result["n_roles_total"] == 4
    assert synthetic_result["n_role_origin_pairs"]["test"] > 0
    assert "small" in synthetic_result["sample_note"].lower() or "rough" in synthetic_result["sample_note"].lower()


def test_backtest_equals_the_skill_backtest_on_the_same_table(synthetic_result):
    demand = make_roles(n_months=96)
    raw = bt.run_backtest(demand, bt.month_range("2022-01", "2022-06"), bt.month_range("2023-11", "2024-04"),
                          bt.month_range("2021-12", "2022-06"))
    assert synthetic_result["coverage"]["test_h12"] == raw["coverage"]["test_h12"]
    assert synthetic_result["models"]["naive3"]["test_mae_pp"] == raw["models"]["naive3"]["test_mae_pp"]
    assert synthetic_result["trend_label_hit_rate"] == raw["trend_label_hit_rate"]


def test_backtest_is_deterministic(synthetic_result):
    again = rb.run_role_backtest(make_roles(n_months=96), bt.month_range("2022-01", "2022-06"),
                                 bt.month_range("2023-11", "2024-04"), bt.month_range("2021-12", "2022-06"))
    drop = lambda d: {k: v for k, v in d.items() if k != "generated_at"}  # noqa: E731
    assert drop(again) == drop(synthetic_result)


@pytest.fixture(scope="module")
def real_backtest():
    roles = roles_mod.load_roles(DATA / "roles.json")
    demand = rf.role_demand_frame(path=DATA / "role_demand_monthly.csv", role_ids=rf.ranked_role_ids(roles))
    return rb.run_role_backtest(demand, bt.month_range(bt.EARLY_FIRST, bt.EARLY_LAST),
                                bt.month_range(bt.TEST_FIRST, bt.TEST_LAST))


@needs_real_data
def test_real_backtest_numbers_are_reproducible(real_backtest):
    stored = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    drop = lambda d: {k: v for k, v in d.items() if k != "generated_at"}  # noqa: E731
    assert drop(real_backtest) == drop(stored)


@needs_real_data
def test_real_backtest_uses_the_skill_design(real_backtest):
    assert real_backtest["origins"]["early"] == ["2021-12", "2023-10"]
    assert real_backtest["origins"]["test"] == ["2023-11", "2025-10"]
    assert real_backtest["origins"]["n_early"] == 23 and real_backtest["origins"]["n_test"] == 24
    assert real_backtest["interval"]["window_origins"] == 24 and real_backtest["interval"]["level"] == 0.8
    assert real_backtest["min_mean_mentions_last_12m"] == 5
    assert real_backtest["n_roles_total"] == 8
    assert real_backtest["trend_label_backtest"]["origins"] == ["2021-12", "2025-10"]
    assert real_backtest["trend_label_backtest"]["n"] == real_backtest["trend_label_backtest"]["n_rising"] + \
        real_backtest["trend_label_backtest"]["n_falling"]
    assert real_backtest["trend_label_backtest"]["caveat"]
    for m in ("naive", "naive3", "drift", "damped"):
        assert real_backtest["models"][m]["test_mae_pp"]["h12"] > 0


# --- schema ----------------------------------------------------------------------------

def _check(value, spec, path):
    """A tiny schema checker. spec is a type, a tuple of types, a dict (object), or ("list", spec)."""
    if isinstance(spec, dict):
        assert isinstance(value, dict), f"{path} must be an object"
        for key, sub in spec.items():
            assert key in value, f"{path}.{key} is missing"
            _check(value[key], sub, f"{path}.{key}")
    elif isinstance(spec, tuple) and spec and spec[0] == "list":
        assert isinstance(value, list), f"{path} must be a list"
        for i, item in enumerate(value):
            _check(item, spec[1], f"{path}[{i}]")
    else:
        types = spec if isinstance(spec, tuple) else (spec,)
        ok = isinstance(value, types) and not (isinstance(value, bool) and bool not in types)
        assert ok, f"{path} is {type(value).__name__}, expected {types}"


NUM, OPT_NUM, OPT_STR = (int, float), (int, float, type(None)), (str, type(None))
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
ROLE_SCHEMA = {
    "name": str, "status": str, "note": OPT_STR,
    "share_now": {"value": NUM, "mentions": int, "posts": int, "months": ("list", str)},
    "level_now": NUM,
    "forecast_moderate": {"value_12m": OPT_NUM, "low": OPT_NUM, "high": OPT_NUM},
    "band_width_pp": OPT_NUM,
    "trend": {"label": OPT_STR, "p": OPT_NUM, "share_last12": NUM, "share_prev12": NUM,
              "mentions_last12": int, "posts_last12": int, "mentions_prev12": int, "posts_prev12": int},
    "sources": ("list", {"name": str, "url": str, "date": str}),
    "as_of": str, "partial_month": bool,
}
DOC_SCHEMA = {
    "schema_version": int, "generated_at": str, "as_of": str, "partial_month": bool,
    "interval": {"label": str, "level": NUM, "model": str, "window_origins": int, "q_h12": NUM,
                 "model_scores_h12_pp": dict, "n_roles_pooled": int, "earliest_supported_as_of": str},
    "notes": ("list", str),
    "data_window": {"from": str, "to": str},
    "excluded_roles": ("list", {"role_id": str, "name": str, "reason": str}),
    "roles": dict,
}


def validate_role_forecast(doc):
    _check(doc, DOC_SCHEMA, "doc")
    assert MONTH.match(doc["as_of"]) and doc["interval"]["model"] in ("naive", "naive3")
    assert doc["roles"], "no roles"
    for rid, role in doc["roles"].items():
        _check(role, ROLE_SCHEMA, rid)
        assert role["status"] in ("ok", "low_volume"), rid
        assert role["trend"]["label"] in (None, "Rising", "Falling", "No clear change"), rid
        assert MONTH.match(role["as_of"]) and role["as_of"] == doc["as_of"], rid
        assert any("role backtest (data/role_backtest.json)" in s["name"] for s in role["sources"]), rid
        assert len(role["sources"]) == 4, rid  # the last 3 HN threads plus the backtest
        assert 0 < role["share_now"]["value"] < 1 and 0 < role["level_now"] < 1
        f = role["forecast_moderate"]
        if role["status"] == "ok":
            assert all(isinstance(f[k], float) for k in ("value_12m", "low", "high")), rid
            assert 0 < f["low"] < f["value_12m"] < f["high"] < 1, rid
            assert role["band_width_pp"] > 0 and role["note"] is None, rid
        else:
            assert f == {"value_12m": None, "low": None, "high": None} and role["band_width_pp"] is None, rid
            assert role["note"], rid


@needs_real_data
def test_role_forecast_json_validates():
    validate_role_forecast(json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8")))


def test_synthetic_role_forecast_validates_and_bad_docs_fail():
    doc = forecast(make_roles())
    validate_role_forecast(doc)
    bad = json.loads(json.dumps(doc))
    bad["roles"]["data_engineer"]["forecast_moderate"]["low"] = "x"
    with pytest.raises(AssertionError):
        validate_role_forecast(bad)
    bad = json.loads(json.dumps(doc))
    del bad["roles"]["data_engineer"]["trend"]["p"]
    with pytest.raises(AssertionError):
        validate_role_forecast(bad)
    bad = json.loads(json.dumps(doc))
    bad["roles"]["data_engineer"]["status"] = "rare"
    with pytest.raises(AssertionError):
        validate_role_forecast(bad)


@needs_real_data
def test_role_backtest_json_has_what_the_app_and_docs_read():
    b = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    _check(b, {
        "schema_version": int, "kind": str, "generated_at": str, "role_ids": ("list", str),
        "sample_note": str, "caveats": ("list", str),
        "n_role_origin_pairs": {"early": int, "test": int, "excluded": int},
        "models": dict, "chosen_model": str,
        "coverage": {"label": str, "nominal": NUM, "test_h12": NUM, "test_mean_over_h": NUM,
                     "test_mean_band_width_h12_pp": NUM, "n_role_origins": int},
        "trend_label_hit_rate": NUM,
        "trend_label_backtest": {"n": int, "n_rising": int, "n_falling": int, "caveat": str, "definition": str},
    }, "backtest")
    assert b["kind"] == "role" and len(b["role_ids"]) == 8
    assert 0.0 <= b["coverage"]["test_h12"] <= 1.0


# --- the Roles tab line ----------------------------------------------------------------

def _app_texts(at):
    return [c.value for c in at.caption]


def _coverage_tail(past: bool) -> str:
    """The sentence after the estimate: how the band did in the role backtest (numbers from role_backtest.json)."""
    b = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    cov = b["coverage"]
    assert cov["test_h12"] > cov["nominal"]
    text = (f"In the role backtest the band held {cov['test_h12']:.1%} of {cov['n_role_origins']} overlapping "
            f"test outcomes (target {cov['nominal']:.0%}), so it is wider than needed; "
            f"{b['n_roles_used']} roles, a rough guide.")
    return text + (" The backtest uses all data and does not move with the As-of slider." if past else "")


@needs_real_data
def test_role_card_shows_the_forecast_line_from_the_json_files():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception
    doc = json.loads((DATA / "role_forecast.json").read_text(encoding="utf-8"))
    cov = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))["coverage"]["test_h12"]
    lines = [t for t in _app_texts(at) if t.startswith("Share of HN hiring posts now")]
    cards = [m.value for m in at.markdown if m.value.startswith("### #")]
    assert cards and len(lines) == len(cards)  # one line per role card
    sample = doc["roles"]["backend_engineer"]
    f = sample["forecast_moderate"]
    expected = (f"Share of HN hiring posts now {sample['share_now']['value']:.1%} "
                f"({sample['share_now']['mentions']}/{sample['share_now']['posts']}); "
                f"12-month estimate {f['value_12m']:.1%} (80% target band {f['low']:.1%}\u2013{f['high']:.1%}). "
                + _coverage_tail(past=False))
    assert expected in lines


@needs_real_data
def test_role_card_line_follows_the_as_of_slider_without_later_data():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    at.sidebar.select_slider[0].set_value("2024-06").run()
    assert not at.exception
    cov = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))["coverage"]["test_h12"]
    backtest = json.loads((DATA / "role_backtest.json").read_text(encoding="utf-8"))
    past = rf.role_forecast_for(as_of="2024-06", backtest=backtest, today=TODAY)["roles"]["backend_engineer"]
    f = past["forecast_moderate"]
    lines = [t for t in _app_texts(at) if t.startswith("Share of HN hiring posts now")]
    assert (f"Share of HN hiring posts now {past['share_now']['value']:.1%} "
            f"({past['share_now']['mentions']}/{past['share_now']['posts']}); "
            f"12-month estimate {f['value_12m']:.1%} (80% target band {f['low']:.1%}\u2013{f['high']:.1%}). "
            + _coverage_tail(past=True)) in lines


@needs_real_data
def test_role_card_line_is_hidden_when_the_role_forecast_file_is_missing(tmp_path):
    import shutil

    from streamlit.testing.v1 import AppTest

    # a copy of the app and data without role_forecast.json: app.py reads data/ next to itself
    shutil.copy(ROOT / "app.py", tmp_path / "app.py")
    shutil.copytree(ROOT / "engine", tmp_path / "engine", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(DATA, tmp_path / "data", ignore=shutil.ignore_patterns("raw", "role_forecast.json"))
    at = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=90).run()
    assert not at.exception
    assert any(t.startswith("Role demand:") or "Role demand:" in t for t in [m.value for m in at.markdown])
    assert not [t for t in _app_texts(at) if t.startswith("Share of HN hiring posts now")]
