"""Tests for the Streamlit front end (app.py), run with Streamlit's AppTest."""

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import engine.refresh

ROOT = Path(__file__).resolve().parent.parent
# A relative path would be resolved against this test file, so use an absolute path.
APP_PATH = str(ROOT / "app.py")
TIMEOUT = 60
FIXTURE_BANNER = "Prototype: showing sample data, not real forecasts."
PARTIAL_NOTE = "The latest month's thread is still open; its numbers can change."
LOW_VOLUME_NOTE = "Too few posts to forecast; observed counts shown."

DATA = ROOT / "data"
needs_real_data = pytest.mark.skipif(
    not (DATA / "skill_scores.json").exists(), reason="data/skill_scores.json not generated yet")
DATA_FILES = ("skill_scores.json", "demand_monthly.csv", "taxonomy.json", "exposure.csv",
              "backtest.json", "hn_threads.csv", "ai_context_monthly.csv", "SOURCES.md")
FORECAST_PREFIX = "12-month forecast"


def _run_app(path: str = APP_PATH) -> AppTest:
    return AppTest.from_file(path, default_timeout=TIMEOUT).run()


@pytest.fixture
def fixture_app(tmp_path) -> str:
    """A copy of app.py in a folder that holds only the fixture file.

    app.py looks for data/skill_scores.json next to itself. The copy has none, so it
    falls back to data/fixtures/skill_scores.json, whatever the real engine output is.
    """
    shutil.copy(APP_PATH, tmp_path / "app.py")
    fixtures = tmp_path / "data" / "fixtures"
    fixtures.mkdir(parents=True)
    shutil.copy(ROOT / "data" / "fixtures" / "skill_scores.json", fixtures / "skill_scores.json")
    return str(tmp_path / "app.py")


# --- helpers -------------------------------------------------------------------------

def _joined(at: AppTest) -> str:
    """All text elements on the page, one per line."""
    elements = [at.markdown, at.caption, at.info, at.success, at.warning, at.error,
                at.subheader, at.header, at.title]
    return "\n".join(e.value for group in elements for e in group)


def _skills_table(at: AppTest):
    return at.dataframe[0].value


def _forecast_of(at: AppTest, skill: str) -> str:
    """The text in the forecast column of the skills table for one skill."""
    table = _skills_table(at).set_index("Skill")
    column = next(c for c in table.columns if c.startswith(FORECAST_PREFIX))
    return table.loc[skill, column]


def _scores() -> dict:
    return json.loads((DATA / "skill_scores.json").read_text(encoding="utf-8"))


def _pick_skill(at: AppTest, name: str) -> AppTest:
    return at.selectbox(key="detail_skill").set_value(name).run()


def _data_snapshot() -> dict:
    return {p.name: p.read_bytes() for p in DATA.iterdir() if p.is_file()}


@pytest.fixture
def data_copy(tmp_path) -> Path:
    """A copy of the data files, to stand in for the folder a refresh worked in."""
    folder = tmp_path / "refreshed"
    folder.mkdir()
    for name in DATA_FILES:
        shutil.copy(DATA / name, folder / name)
    return folder


# --- fixture (sample data) -----------------------------------------------------------

def test_app_runs_on_fixture_without_exception(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception


def test_fixture_banner_is_shown(fixture_app):
    at = _run_app(fixture_app)
    banners = [w.value for w in at.warning]
    assert FIXTURE_BANNER in banners


def test_fixture_scenario_switch_reruns_without_exception(fixture_app):
    at = _run_app(fixture_app)
    at.sidebar.radio[0].set_value("fast").run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "fast"
    assert at.sidebar.radio[0].options[1] == "Fast AI disruption (k = 0.5, an assumption)"


def test_fixture_app_hides_refresh_and_as_of_and_has_no_history(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception
    assert len(at.sidebar.button) == 0 and len(at.sidebar.select_slider) == 0
    text = _joined(at)
    assert "The monthly history is not available for the sample data." in text
    assert "data/backtest.json was not found" in text


# --- real engine output --------------------------------------------------------------

def test_app_runs_on_real_engine_output_without_banner():
    if not (DATA / "skill_scores.json").exists():
        pytest.skip("data/skill_scores.json not generated yet")
    at = _run_app()
    assert not at.exception
    assert FIXTURE_BANNER not in [w.value for w in at.warning]


@needs_real_data
def test_real_data_shows_the_header_and_the_fixed_lines():
    scores = _scores()
    at = _run_app()
    assert not at.exception
    text = _joined(at)
    assert "Future-ready skills for tech developers" in text
    assert f"**Data as of:** {scores['as_of']} | generated {scores['generated_at']}" in text
    assert "Estimates, not facts. You decide." in text
    assert "No LLM is used in this view." in text
    assert (PARTIAL_NOTE in text) == bool(scores["partial_month"])
    assert [t.label for t in at.tabs] == ["Skills", "Skill detail", "Method"]
    assert len(_skills_table(at)) == len(scores["skills"])


@needs_real_data
def test_scenario_switch_changes_the_forecast_column_and_the_label():
    scores = _scores()
    python = next(s for s in scores["skills"] if s["skill"] == "Python")
    at = _run_app()
    radio = at.sidebar.radio[0]
    k = scores["scenario_params"]["k"]
    assert radio.options == ["Moderate", f"Fast AI disruption (k = {k}, an assumption)"]
    before = _forecast_of(at, "Python")
    radio.set_value("fast").run()
    assert not at.exception
    after = _forecast_of(at, "Python")
    fast = python["forecast"]["fast"]
    assert after == f"{fast['value_12m']:.1%} ({fast['low']:.1%} to {fast['high']:.1%})"
    assert before != after
    assert any(c.startswith(FORECAST_PREFIX) and "Fast AI disruption" in c
               for c in _skills_table(at).columns)
    assert "an assumption" in _joined(at)


@needs_real_data
def test_low_volume_skill_shows_na_forecast_and_the_note():
    low = next(s for s in _scores()["skills"] if s["status"] == "low_volume")
    at = _run_app()
    row = _skills_table(at).set_index("Skill").loc[low["skill"]]
    assert row["Status"] == "low_volume"
    assert _forecast_of(at, low["skill"]) == "n/a"
    assert row["Note"] == LOW_VOLUME_NOTE
    assert f"({low['mentions_last3']}/{low['posts_last3']} posts)" in row["Share now"]
    at.sidebar.radio[0].set_value("fast").run()
    assert _forecast_of(at, low["skill"]) == "n/a"
    _pick_skill(at, low["skill"])
    assert not at.exception
    assert LOW_VOLUME_NOTE in _joined(at)


@needs_real_data
def test_table_filters_narrow_the_rows():
    scores = _scores()
    at = _run_app()
    at.multiselect[0].set_value(["low_volume"]).run()
    assert not at.exception
    n_low = sum(s["status"] == "low_volume" for s in scores["skills"])
    assert len(_skills_table(at)) == n_low
    assert set(_skills_table(at)["Status"]) == {"low_volume"}


@needs_real_data
def test_skill_detail_shows_trend_shift_band_sources_and_a_chart():
    skill = next(s for s in _scores()["skills"]
                 if s["status"] == "ok" and s["trend_label"] == "Rising")
    at = _run_app()
    _pick_skill(at, skill["skill"])
    assert not at.exception
    text = _joined(at)
    assert "Trend label: Rising." in text
    assert f"{skill['mentions_last12']} mentions in {skill['posts_last12']} posts" in text
    assert f"p = {skill['trend_p']:.3f}" in text
    assert f"band width of {skill['band_width_pp']:.1f} pp" in text
    band, fast = skill["forecast"]["moderate"], skill["forecast"]["fast"]["value_12m"]
    inside = band["low"] <= fast <= band["high"]  # the band is asymmetric: no half-width rule
    assert ("The Fast forecast is inside the Moderate band" in text) == inside
    assert ("The Fast forecast is outside the Moderate band" in text) == (not inside)
    assert "What happened" not in text  # only in an as-of view
    for src in skill["sources"]:
        if src["url"].startswith("http"):
            assert f"[{src['name']}]({src['url']}), {src['date']}" in text
    assert len(at.get("arrow_vega_lite_chart")) + len(at.get("vega_lite_chart")) >= 1


@needs_real_data
def test_as_of_2023_12_shows_what_happened_for_a_skill_with_data():
    scores = _scores()
    at = _run_app()
    slider = at.sidebar.select_slider[0]
    assert slider.value == scores["as_of"]
    assert slider.options[0] == scores["interval"]["earliest_supported_as_of"]
    snapshot = _data_snapshot()
    slider.set_value("2023-12").run()
    assert not at.exception
    assert "What happened" in [s.value for s in at.subheader]
    text = _joined(at)
    assert "Looking back: this view uses only data up to 2023-12." in text
    assert "Graded against the Moderate band (the calibrated one)" in text
    assert "The actual value was" in text
    assert "For reference only: 2024-12 raw share" in text
    assert "**Data as of:** 2023-12 |" in text
    assert len(_skills_table(at)) == len(scores["skills"])
    assert _data_snapshot() == snapshot  # an as-of view writes no file
    # back to the newest month: the section is gone
    at.sidebar.select_slider[0].set_value(scores["as_of"]).run()
    assert "What happened" not in [s.value for s in at.subheader]


@needs_real_data
def test_as_of_view_whose_outcome_month_is_not_in_the_data_says_so():
    last = _scores()["data_window"]["to"]
    at = _run_app()
    one_short = str(pd.Period(last, freq="M") - 11)  # its outcome month is one past the data
    at.sidebar.select_slider[0].set_value(one_short).run()
    assert not at.exception
    assert "is not in the data yet" in _joined(at)


@needs_real_data
def test_refresh_success_shows_posts_fetched_at_and_changed_skills(monkeypatch, data_copy):
    scores = json.loads((data_copy / "skill_scores.json").read_text(encoding="utf-8"))
    scores["generated_at"] = "2026-10-30T00:00:00Z"
    (data_copy / "skill_scores.json").write_text(json.dumps(scores), encoding="utf-8")
    calls = []

    def fake_refresh(*args, **kwargs):
        calls.append(1)
        return {"ok": True, "data_dir": str(data_copy), "month": "2026-10", "posts_before": 266,
                "posts_after": 271, "fetched_at": "2026-10-22T09:00:00Z", "scores_updated": True,
                "scores_error": None, "skills_changed": {"Python": [0.25, 0.26]}}

    monkeypatch.setattr(engine.refresh, "refresh", fake_refresh)
    at = _run_app()
    assert at.sidebar.button[0].label == "Refresh live data"
    at.sidebar.button[0].click().run()

    assert calls == [1] and not at.exception
    text = _joined(at)
    assert "Refreshed 2026-10: posts 266 -> 271." in text
    assert "Fetched at 2026-10-22T09:00:00Z." in text
    assert "Python: 25.0% -> 26.0%" in text
    assert "generated 2026-10-30T00:00:00Z" in text  # scores come from the returned data_dir
    committed = _scores()["generated_at"]
    assert ("Live refresh at 2026-10-22T09:00:00Z. Held only on this server until it restarts; "
            f"the committed snapshot is dated {committed}.") in text
    at.run()  # the new folder stays in use on the next rerun
    assert "generated 2026-10-30T00:00:00Z" in _joined(at)
    assert calls == [1]  # a rerun does not refresh again

    labels = [b.label for b in at.sidebar.button]
    assert labels == ["Refresh live data", "Back to committed snapshot"]
    at.sidebar.button[1].click().run()
    assert not at.exception
    text = _joined(at)
    assert f"generated {committed}" in text and "Live refresh at" not in text
    assert [b.label for b in at.sidebar.button] == ["Refresh live data"]


@needs_real_data
def test_refresh_busy_is_an_info_not_an_error(monkeypatch):
    busy = {"ok": False, "busy": True, "error": "a refresh is already running"}
    monkeypatch.setattr(engine.refresh, "refresh", lambda *a, **k: busy)
    at = _run_app()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert "A refresh is already running; try again in a few seconds." in [i.value for i in at.info]
    assert not [e.value for e in at.error if "Refresh failed" in e.value]


@needs_real_data
def test_refresh_failure_shows_the_error_and_keeps_the_old_data(monkeypatch):
    scores = _scores()
    failure = {"ok": False, "error": "RuntimeError: network is down", "data_dir": None,
               "fallback": {"as_of": scores["as_of"], "generated_at": scores["generated_at"]}}
    monkeypatch.setattr(engine.refresh, "refresh", lambda *a, **k: failure)

    at = _run_app()
    at.sidebar.button[0].click().run()

    assert not at.exception
    text = _joined(at)
    assert "Refresh failed: RuntimeError: network is down" in text
    assert (f"The last good data is shown: data as of {scores['as_of']}, "
            f"generated {scores['generated_at']}.") in text
    assert f"**Data as of:** {scores['as_of']} | generated {scores['generated_at']}" in text
    assert len(_skills_table(at)) == len(scores["skills"])


@needs_real_data
def test_refresh_that_raises_is_shown_as_an_error(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk is read-only")

    monkeypatch.setattr(engine.refresh, "refresh", boom)
    at = _run_app()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert "disk is read-only" in _joined(at)


@needs_real_data
def test_method_tab_renders_the_backtest_numbers_from_the_file():
    bt = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))
    at = _run_app()
    assert not at.exception
    text = _joined(at)
    assert "How good is the forecast?" in text
    assert f"Chosen model: {bt['chosen_model']}" in text
    assert bt["chosen_because"] in text
    assert f"covered {bt['coverage']['test_h12']:.1%} of real values at h=12" in text
    assert f"{bt['trend_label_backtest']['trend_label_hit_rate']:.1%} of the time" in text
    assert f"n = {bt['trend_label_backtest']['n']}" in text
    for caveat in bt["caveats"]:
        assert caveat in text
    mae = next(d.value for d in at.dataframe if "Test h=12" in d.value.columns)
    assert list(mae["Model"]) == list(bt["models"])
    assert mae.set_index("Model").loc["naive3", "Test h=12"] == bt["models"]["naive3"]["test_mae_pp"]["h12"]
    groups = next(d.value for d in at.dataframe if "Share group" in d.value.columns)
    assert len(groups) == len(bt["coverage"]["by_share_group"])
    assert "Share of job posts that mention AI at all (company context, not a skill)" in text
    assert any("huggingface.co" in m.value and m.value.startswith("- [") for m in at.markdown)


# --- header, method caption, calibration, no look-ahead -------------------------------------

@needs_real_data
def test_header_names_the_forecast_model_and_the_band():
    scores = _scores()
    at = _run_app()
    assert scores["interval"]["model"] == "naive3"
    assert f"Forecast model: naive3 (mean of last 3 months), {scores['interval']['label']}" in _joined(at)


@needs_real_data
def test_method_tab_says_the_backtest_does_not_move_with_the_slider():
    bt = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))
    at = _run_app()
    at.sidebar.select_slider[0].set_value("2024-06").run()
    assert (f"Backtest numbers are computed on all data up to {bt['data_window']['to']}; "
            "they do not change with the As-of slider.") in _joined(at)


def _chart_frames(at: AppTest) -> list:
    """The data frame behind every layer of every Altair chart on the page."""
    import pyarrow as pa

    frames = []
    for chart in at.get("vega_lite_chart") + at.get("arrow_vega_lite_chart"):
        for dataset in chart.proto.datasets:
            frames.append(pa.ipc.open_stream(dataset.data.data).read_all().to_pandas())
    return frames


@needs_real_data
def test_no_as_of_view_draws_months_after_as_of_except_the_outcome_point():
    import pandas as pd

    at = _run_app()
    for as_of in ("2023-12", "2024-06"):
        at.sidebar.select_slider[0].set_value(as_of).run()
        assert not at.exception
        frames = _chart_frames(at)
        assert frames
        last_allowed = pd.Timestamp(as_of + "-01")
        target = pd.Timestamp(str(pd.Period(as_of, freq="M") + 12) + "-01")
        outcome_seen = False
        for df in frames:
            for series, rows in df.groupby("series"):
                if series.startswith("Forecast") or series == "What happened":
                    assert (rows["date"] == target).all()  # only the target month
                    outcome_seen |= series == "What happened"
                else:
                    assert rows["date"].max() <= last_allowed, (as_of, series)
        assert outcome_seen


@needs_real_data
def test_what_happened_is_graded_against_the_moderate_band_whatever_the_scenario():
    at = _run_app()
    at.sidebar.select_slider[0].set_value("2023-12").run()

    def verdicts():
        return [m.value for m in at.markdown if m.value.startswith("Graded against the Moderate band")]

    names = at.selectbox(key="detail_skill").options
    for name in names[:6]:
        _pick_skill(at, name)
        moderate_view = verdicts()
        at.sidebar.radio[0].set_value("fast").run()
        fast_view = verdicts()
        at.sidebar.radio[0].set_value("moderate").run()
        assert moderate_view == fast_view, name  # the Fast toggle never changes the verdict


@needs_real_data
def test_app_verdict_text_matches_band_verdict_for_a_skill():
    import pandas as pd
    from engine.outcome import band_verdict
    from engine.scores import build_scores

    demand = pd.read_csv(DATA / "demand_monthly.csv").set_index(["skill", "month"])
    view = build_scores(as_of="2023-12")
    at = _run_app()
    at.sidebar.select_slider[0].set_value("2023-12").run()
    for skill in [s for s in view["skills"] if s["status"] == "ok"][:5]:
        _pick_skill(at, skill["skill"])
        row = demand.loc[(skill["skill"], "2024-12")]
        verdict = band_verdict(skill["forecast"]["moderate"], row["mentions"], row["n_posts"])
        text = " ".join(m.value for m in at.markdown if m.value.startswith("Graded against"))
        assert f"The actual value was {verdict['place']} the band." in text
        assert f"was {verdict['actual']:.1%}." in text


@needs_real_data
def test_what_happened_reproduces_the_backtest_band_coverage():
    """Grade every ok skill at every as-of month the backtest tested. The share graded
    "inside" must equal coverage.test_h12 in backtest.json (the band is calibrated on the
    single target month, not on a pooled 3-month share)."""
    import pandas as pd
    from engine.outcome import band_verdict
    from engine.scores import build_scores

    bt = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))
    demand = pd.read_csv(DATA / "demand_monthly.csv").set_index(["skill", "month"])
    first = _scores()["interval"]["earliest_supported_as_of"]
    last_test = bt["origins"]["test"][1]
    inside = total = 0
    for as_of in pd.period_range(first, last_test, freq="M"):
        as_of = str(as_of)
        target = str(pd.Period(as_of, freq="M") + 12)
        for skill in build_scores(as_of=as_of)["skills"]:
            if skill["status"] != "ok":
                continue
            row = demand.loc[(skill["skill"], target)]
            inside += band_verdict(skill["forecast"]["moderate"], row["mentions"], row["n_posts"])["inside"]
            total += 1
    assert total == bt["coverage"]["n_skill_origins"]
    assert abs(inside / total - bt["coverage"]["test_h12"]) < 0.005


@needs_real_data
def test_method_tab_shows_na_for_missing_backtest_numbers(monkeypatch, data_copy):
    bt = json.loads((data_copy / "backtest.json").read_text(encoding="utf-8"))
    bt["models"]["naive3"]["test_h12_vs_naive"]["ci95_skill_bootstrap"] = None
    bt["coverage"]["test_mean_band_width_h12_pp"] = None
    for group in bt["coverage"]["by_share_group"].values():
        group["mean_band_width_h12_pp"] = None
    (data_copy / "backtest.json").write_text(json.dumps(bt), encoding="utf-8")
    result = {"ok": True, "data_dir": str(data_copy), "month": "2026-10", "posts_before": 1,
              "posts_after": 2, "fetched_at": "x", "scores_updated": True, "skills_changed": {}}
    monkeypatch.setattr(engine.refresh, "refresh", lambda *a, **k: result)
    at = _run_app()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert "with a mean band width of n/a." in _joined(at)
    mae = next(d.value for d in at.dataframe if "Test h=12" in d.value.columns)
    assert mae.set_index("Model").loc["naive3", "Test h=12 gain vs naive (bootstrap CI)"].endswith("(n/a to n/a)")
    groups = next(d.value for d in at.dataframe if "Share group" in d.value.columns)
    assert set(groups["Mean band width at h=12 (pp)"]) == {"n/a"}
