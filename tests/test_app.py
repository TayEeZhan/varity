"""Tests for the Streamlit front end (app.py), run with Streamlit's AppTest."""

import json
import re
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
# The journey layout: the step tabs come first, then the Evidence tab with three nested tabs.
JOURNEY_TABS = ["1 You", "2 Skills radar", "3 Future roles", "4 Your plan", "Evidence"]
EVIDENCE_TABS = ["Skills", "Skill detail", "Method"]


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
    assert [t.label for t in at.tabs] == JOURNEY_TABS + EVIDENCE_TABS  # layout move: Roles/Pathway are steps 3/4
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
    next(m for m in at.multiselect if m.label == "Status").set_value(["low_volume"]).run()
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
            if "series" not in df.columns:  # the radar chart (step 2) has its own test in this file
                continue
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


# --- Roles tab -----------------------------------------------------------------------

needs_role_files = pytest.mark.skipif(
    not all((DATA / n).exists() for n in ("role_profiles.json", "role_demand_monthly.csv", "roles.json",
                                          "exposure.csv", "skill_scores.json")),
    reason="role files not generated yet")
PERSONA_LABELS = ["Aina, junior Python dev (synthetic)", "Ben, frontend dev (synthetic)",
                  "Chloe, data analyst (synthetic)"]


def _cards(at: AppTest) -> list[str]:
    """Card titles in order, e.g. '#1 Backend Engineer'."""
    return [m.value.removeprefix("### ") for m in at.markdown if m.value.startswith("### #")]


def _matches(at: AppTest) -> list[int]:
    return [int(p.text.removeprefix("Match ").removesuffix("%")) for p in at.progress if p.text.startswith("Match ")]


def _low(at: AppTest) -> dict[str, int]:
    """Roles listed under 'Not a fit yet' with their match percent: '**Name**: match 12%'."""
    found = {}
    for m in at.markdown:
        hit = re.fullmatch(r"\*\*(.+)\*\*: match (\d+)%", m.value)
        if hit:
            found[hit.group(1)] = int(hit.group(2))
    return found


def _all_matches(at: AppTest) -> dict[str, int]:
    """Match percent of every role on screen: ranked cards and the low-match list."""
    ranked = {_role_name(c): m for c, m in zip(_cards(at), _matches(at))}
    return {**_low(at), **ranked}


def _captions(at: AppTest) -> str:
    return "\n".join(c.value for c in at.caption)


def _role_name(card: str) -> str:
    return card.split(" ", 1)[1].split(" (rank")[0]


def test_roles_tab_is_first_and_degrades_on_the_fixture(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception
    assert [t.label for t in at.tabs][0] == "1 You"  # layout move: the journey starts with "1 You"
    assert any("Role match needs the real data files" in i.value for i in at.info)
    assert _cards(at) == []


@needs_real_data
@needs_role_files
@pytest.mark.parametrize("label", PERSONA_LABELS)
def test_roles_tab_renders_for_each_persona(label):
    at = _run_app()
    at.selectbox(key="role_persona").set_value(label).run()
    assert not at.exception
    cards = _cards(at)
    assert cards and cards[0].startswith("#1 ")
    assert len(cards) + len(_low(at)) == 8  # every ranked role has a card, the rest sit under "Not a fit yet"
    assert "Analytics Engineer" not in " ".join(cards)
    assert len(at.progress) == len(cards) and all(0 <= m <= 100 for m in _matches(at))
    assert all(m >= 20 for m in _matches(at)) and all(m < 20 for m in _low(at).values())
    text = _joined(at) + "\n" + _captions(at)
    for needle in ("You have", "Gaps", "Role demand:", "% of posts", "Confidence:", "SDG:",
                   "Analytics Engineer: Not ranked: too few posts to learn a profile",
                   "Target role:"):
        assert needle in text, needle
    assert len(at.button(key="target_data_engineer").label) > 0
    assert "Choose this as my target role" in {b.label for b in at.button}
    assert at.multiselect(key="role_skills").value  # prefilled from the persona
    assert any("How the rank is computed" in e.label for e in at.expander)


@needs_real_data
@needs_role_files
def test_persona_prefills_the_skill_picker_and_all_taxonomy_skills_are_options():
    at = _run_app()
    picker = at.multiselect(key="role_skills")
    assert set(picker.value) == {"Python", "SQL", "PostgreSQL", "Docker", "AWS"}
    taxonomy = json.loads((DATA / "taxonomy.json").read_text(encoding="utf-8"))
    assert len(picker.options) == len(taxonomy) == 40
    at.selectbox(key="role_persona").set_value(PERSONA_LABELS[1]).run()
    assert set(at.multiselect(key="role_skills").value) == {"JavaScript / TypeScript", "TypeScript", "React",
                                                            "Node.js"}


@needs_real_data
@needs_role_files
def test_editing_skills_changes_the_match_percent():
    at = _run_app()
    before = _all_matches(at)
    assert len(before) == 8
    at.multiselect(key="role_skills").set_value(["Python"]).run()
    assert not at.exception
    few = _all_matches(at)
    assert few != before and len(few) == 8
    assert all(few[name] <= before[name] for name in before)  # removing skills never raises a match
    at.multiselect(key="role_skills").set_value([]).run()
    assert set(_all_matches(at).values()) == {0}
    at.multiselect(key="role_skills").set_value(["Python", "SQL", "PostgreSQL", "Docker", "AWS", "Go",
                                                 "Kubernetes", "Terraform"]).run()
    more = _all_matches(at)
    assert more["Backend Engineer"] > before["Backend Engineer"]


@needs_real_data
@needs_role_files
def test_fast_scenario_keeps_the_order_and_shows_the_estimate_line():
    at = _run_app()
    moderate_cards = _cards(at)
    assert "Fast AI scenario (estimate)" not in _captions(at)
    at.sidebar.radio[0].set_value("fast").run()
    assert not at.exception
    assert _cards(at) == moderate_cards
    lines = [c.value for c in at.caption if c.value.startswith("Fast AI scenario (estimate): about ")]
    assert len(lines) == len(moderate_cards) >= 1
    assert all(line.endswith("role demand vs moderate. Does not change the ranking.") for line in lines)
    assert all("%" in line for line in lines)


@needs_real_data
@needs_role_files
def test_sort_by_match_only_reorders_by_match():
    at = _run_app()
    ranked = _cards(at)
    at.toggle(key="roles_sort_match").set_value(True).run()
    assert not at.exception
    cards, matches = _cards(at), _matches(at)
    assert matches == sorted(matches, reverse=True)
    assert all("by rank score" in c for c in cards)
    assert sorted(_role_name(c) for c in cards) == sorted(_role_name(c) for c in ranked)


@needs_real_data
@needs_role_files
def test_as_of_slider_reruns_the_ranking_with_the_older_profile():
    at = _run_app()
    now_text = _captions(at)
    now_cards = _cards(at)
    assert "single-role HN 'Who is hiring?' posts, 2024-11 to 2026-10." in now_text
    assert "Role demand from monthly shares to 2026-10." in now_text
    at.sidebar.select_slider[0].set_value("2023-12").run()
    assert not at.exception
    old_text = _captions(at)
    assert "posts, 2022-01 to 2023-12." in old_text
    assert "Role demand from monthly shares to 2023-12." in old_text
    assert "2024-11 to 2026-10" not in old_text
    # Roles with too few single-role posts in the older window drop out of the ranking and are listed instead.
    assert 3 <= len(_cards(at)) <= 8
    assert _cards(at) != now_cards
    profile = json.loads((DATA / "role_profiles.json").read_text(encoding="utf-8"))["profiles"]["2023-12"]
    assert old_text.count("Not ranked:") == sum(1 for r in profile["roles"] if not r["ranked"])
    assert len(_cards(at)) + len(_low(at)) == sum(1 for r in profile["roles"] if r["ranked"])


@needs_real_data
@needs_role_files
def test_as_of_before_the_first_profile_says_so():
    scores = _scores()
    earliest = scores["interval"]["earliest_supported_as_of"]
    if earliest >= "2023-12":
        pytest.skip("the earliest as-of already has a profile")
    at = _run_app()
    at.sidebar.select_slider[0].set_value(earliest).run()
    assert not at.exception
    assert any("No role profile for" in i.value for i in at.info)


@needs_real_data
@needs_role_files
def test_choosing_a_target_role_sets_session_state():
    at = _run_app()
    assert "**Target role:** none chosen yet" in _joined(at)
    at.button(key="target_ml_engineer").click().run()
    assert not at.exception
    assert at.session_state["target_role"] == "ML Engineer"
    assert "**Target role:** ML Engineer" in _joined(at)
    at.button(key="target_backend_engineer").click().run()
    assert at.session_state["target_role"] == "Backend Engineer"


@needs_real_data
@needs_role_files
def test_source_line_names_the_post_count_and_window():
    at = _run_app()
    profile = json.loads((DATA / "role_profiles.json").read_text(encoding="utf-8"))["profiles"]["2026-10"]
    n = sum(r["n_single_role_posts"] for r in profile["roles"] if r["ranked"])
    assert f"Role skill weights learned from {n:,} single-role HN 'Who is hiring?' posts, 2024-11 to 2026-10."         in _captions(at)


LOW_MATCH_LABEL = "Not a fit yet (under 20% match)"
EMPTY_MESSAGE = "None of the roles match well yet; pick a target to see the gap"


@needs_real_data
@needs_role_files
def test_low_match_roles_sit_in_a_collapsed_expander_with_match_and_gaps():
    at = _run_app()
    at.selectbox(key="role_persona").set_value(PERSONA_LABELS[1]).run()  # Ben: few roles reach 20%
    assert not at.exception
    low = _low(at)
    assert low, "Ben should have roles under 20%"
    expander = next(e for e in at.expander if e.label == LOW_MATCH_LABEL)
    assert not expander.proto.expanded  # collapsed by default
    assert all(name not in " ".join(_cards(at)) for name in low)  # not ranked, so no card
    text = " ".join(m.value for m in expander.markdown)
    assert all(f"**{name}**: match {pct}%" in text for name, pct in low.items())
    assert "(weight " in text and "status " in text and "trend " in text  # gaps with skill status and trend
    assert EMPTY_MESSAGE not in " ".join(i.value for i in at.info)
    # a low-match role can still be chosen as the target
    name_to_key = {"Backend Engineer": "backend_engineer", "Data Scientist": "data_scientist",
                   "AI/LLM Application Engineer": "ai_app_engineer", "Data Engineer": "data_engineer",
                   "ML Engineer": "ml_engineer", "Platform/DevOps Engineer": "platform_devops_engineer",
                   "Mobile Developer": "mobile_developer", "Full-stack Web Developer": "fullstack_developer"}
    first = next(iter(low))
    at.button(key=f"target_{name_to_key[first]}").click().run()
    assert at.session_state["target_role"] == first


@needs_real_data
@needs_role_files
def test_when_no_role_matches_the_page_says_so_and_still_lists_them_by_match():
    at = _run_app()
    at.multiselect(key="role_skills").set_value([]).run()
    assert not at.exception
    assert EMPTY_MESSAGE in [i.value for i in at.info]
    cards = _cards(at)
    assert len(cards) == 8 and _low(at) == {}
    assert not any(e.label == LOW_MATCH_LABEL for e in at.expander)
    matches = _matches(at)
    assert matches == sorted(matches, reverse=True) == [0] * 8
    at.multiselect(key="role_skills").set_value(["Swift"]).run()  # only Mobile Developer reaches 20%
    assert _cards(at) == ["#1 Mobile Developer"]
    assert EMPTY_MESSAGE not in [i.value for i in at.info]
    assert len(_low(at)) == 7


@needs_real_data
@needs_role_files
def test_the_rank_formula_text_mentions_the_low_match_limit():
    at = _run_app()
    text = " ".join(m.value for e in at.expander if "How the rank" in e.label for m in e.markdown)
    assert "under 20% match is not ranked (team judgement)" in text
    assert "0.7 / 0.3 are team judgement" in text


# --- Pathway tab ---------------------------------------------------------------------

import datetime as dt

from streamlit.delta_generator import DeltaGenerator

from engine import pathway as pathway_mod
from engine import roles as roles_mod

NO_TARGET_PROMPT = "Choose a target role in step 3, Future roles, first"  # layout move: no Roles tab any more
FAST_NOTE_START = "Fast AI scenario (an assumption, not a forecast): future bets (Stage 3) are moved earlier"
STAGE_HEADINGS = ["### Stage 1: no-regret", "### Stage 2: near-term demand", "### Also in the gap",
                  "### Stage 3: future bet"]
PERSONA_SKILLS = ["Python", "SQL", "PostgreSQL", "Docker", "AWS"]  # Aina, the default profile
ROLE_KEYS = {"Backend Engineer": "backend_engineer", "Data Scientist": "data_scientist",
             "AI/LLM Application Engineer": "ai_app_engineer", "Data Engineer": "data_engineer",
             "ML Engineer": "ml_engineer", "Platform/DevOps Engineer": "platform_devops_engineer",
             "Mobile Developer": "mobile_developer", "Full-stack Web Developer": "fullstack_developer"}
needs_pathway_files = pytest.mark.skipif(
    not all((DATA / n).exists() for n in ("resources.json", "taxonomy.json", "role_profiles.json",
                                          "role_demand_monthly.csv", "roles.json", "exposure.csv",
                                          "skill_scores.json")),
    reason="pathway files not generated yet")


def _tree_snapshot() -> dict:
    """Every file under data/ (all folders) with its bytes."""
    return {str(p.relative_to(DATA)): p.read_bytes() for p in DATA.rglob("*") if p.is_file()}


def _next_monday() -> dt.date:
    today = pathway_mod.today_myt()  # the app plans in Malaysia time
    return today + dt.timedelta(days=7 - today.weekday())


def _pathway_app(scenario: str | None = None, target: str | None = None) -> tuple[AppTest, str]:
    """The app with a target role set (default: the top role of the default profile, Aina)."""
    at = _run_app()
    name = target or _role_name(_cards(at)[0])
    at.session_state["target_role"] = name
    if scenario:
        at.sidebar.radio[0].set_value(scenario)
    return at.run(), name


def _expected_plan(role_name: str, scenario: str = "moderate", hours: float = 5,
                   start: dt.date | None = None, skills: list[str] | None = None) -> dict:
    """The same plan, built straight from the engines for a profile (default: Aina; no app code)."""
    scores = _scores()
    profiles = json.loads((DATA / "role_profiles.json").read_text(encoding="utf-8"))
    profile = roles_mod.profile_for(scores["as_of"], profiles)
    trends = roles_mod.build_role_trends(roles_mod.read_demand_rows(DATA / "role_demand_monthly.csv"),
                                         roles_mod.load_roles(DATA / "roles.json"), as_of=scores["as_of"])
    out = roles_mod.match_roles(set(skills or PERSONA_SKILLS), profile, scores, trends, scenario,
                                exposure=roles_mod.load_exposure(DATA / "exposure.csv"))
    gap = next(r for r in out["roles"] + out["low_match"] if r["name"] == role_name)["gap"]
    role_gaps = [gap] + [r["gap"] for r in out["roles"] if r["name"] != role_name]  # target + all ranked
    resources = json.loads((DATA / "resources.json").read_text(encoding="utf-8"))
    return pathway_mod.build_pathway(role_name, gap, role_gaps, scores, resources,
                                     scenario=scenario, hours_per_week=hours,
                                     start_date=start or _next_monday())


def _done_boxes(at: AppTest) -> list:
    return [c for c in at.checkbox if c.key.startswith("done_")]


def _progress_text(at: AppTest) -> str:
    return next(p.text for p in at.progress if "% done" in p.text)


def _stage_headings(at: AppTest) -> list[str]:
    return [m.value.split(" (")[0] for m in at.markdown if m.value.startswith(("### Stage", "### Also"))]


def test_pathway_tab_follows_roles_and_asks_for_a_target(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception
    assert [t.label for t in at.tabs][:4] == JOURNEY_TABS[:4]  # layout move
    assert NO_TARGET_PROMPT in [i.value for i in at.info]
    assert not _done_boxes(at) and not at.get("download_button")


@needs_real_data
@needs_pathway_files
def test_pathway_tab_without_a_target_shows_the_prompt_only():
    at = _run_app()
    assert not at.exception
    assert [t.label for t in at.tabs] == JOURNEY_TABS + EVIDENCE_TABS  # layout move
    assert NO_TARGET_PROMPT in [i.value for i in at.info]
    assert not _done_boxes(at) and not at.get("download_button")
    assert not any(b.key == "change_target_role" for b in at.button)


@needs_real_data
@needs_pathway_files
def test_pathway_renders_every_stage_and_every_step_field_from_the_engine():
    at, name = _pathway_app()
    assert not at.exception
    plan = _expected_plan(name)
    assert plan["steps"] and plan["tasks"]
    text = _joined(at)
    assert _stage_headings(at) == STAGE_HEADINGS
    headings = [m.value for m in at.markdown if m.value.startswith("### ") and not m.value.startswith("### #")]
    assert headings[4:] == ["### Daily to-do list", "### Export", "### SDG links"]
    assert f"Pathway to {name}" in [s.value for s in at.subheader]
    for step in plan["steps"]:
        res = step["resource"]
        assert f"**{step['order']}. {step['skill']}**" in text
        assert f"Why: {step['reason']}" in text
        assert (f"Resource: [{res['title']}]({res['url']}) | {res['provider']} | cost: {res['cost']} | "
                f"about {step['minutes']} minutes (estimate)") in text
        assert f"Step deadline: {step['deadline']}" in text
        assert f"Source: {step['source']}" in text


@needs_real_data
@needs_pathway_files
def test_pathway_uses_the_roles_tab_gap_and_the_default_pace():
    at, name = _pathway_app()
    hours, start = at.number_input(key="pathway_hours"), at.date_input(key="pathway_start")
    assert (hours.value, hours.min, hours.max) == (5, 1, 40)
    assert start.value == _next_monday() and start.value.weekday() == 0
    plan = _expected_plan(name)
    text = _joined(at)
    assert f"Plan finishes on {plan['finish_date']}" in text
    assert len(_done_boxes(at)) == len(plan["tasks"])
    assert f"{plan['totals']['steps']} skills, {plan['totals']['tasks']} daily tasks" in text
    first = plan["tasks"][0]
    assert f"Next task: {first['title']} ({first['minutes']} min, {first['date']})" in text
    # a faster pace finishes earlier
    at.number_input(key="pathway_hours").set_value(40).run()
    assert not at.exception
    fast_pace = _expected_plan(name, hours=40)
    assert f"Plan finishes on {fast_pace['finish_date']}" in _joined(at)
    assert fast_pace["finish_date"] < plan["finish_date"]


@needs_real_data
@needs_pathway_files
def test_pathway_skill_without_a_verified_resource_shows_the_placeholder_and_no_task(monkeypatch):
    _, name = _pathway_app()
    skill = _expected_plan(name)["steps"][0]["skill"]
    original = pathway_mod._resource_index

    def without_skill(resources):
        index = original(resources)
        index.pop(skill, None)
        return index

    monkeypatch.setattr(pathway_mod, "_resource_index", without_skill)
    at, _ = _pathway_app(target=name)
    assert not at.exception
    text = _joined(at)
    assert f"Resource: {pathway_mod.PLACEHOLDER_RESOURCE}" in text
    assert f"{pathway_mod.PLACEHOLDER_RESOURCE}: {skill}." in text
    assert not any(c.label.startswith(f"Done: {skill}:") for c in _done_boxes(at))


@needs_real_data
@needs_pathway_files
def test_fast_scenario_shows_the_note_and_moves_future_bets_earlier():
    at, name = _pathway_app()
    assert not any(i.value.startswith(FAST_NOTE_START) for i in at.info)
    assert _stage_headings(at) == STAGE_HEADINGS
    at.sidebar.radio[0].set_value("fast").run()
    assert not at.exception
    assert any(i.value.startswith(FAST_NOTE_START) for i in at.info)
    assert _stage_headings(at) == [STAGE_HEADINGS[0], STAGE_HEADINGS[3], STAGE_HEADINGS[1], STAGE_HEADINGS[2]]
    plan = _expected_plan(name, "fast")
    assert f"Plan finishes on {plan['finish_date']}" in _joined(at)
    assert "Scenario: Fast AI disruption (estimate)" in _joined(at)


@needs_real_data
@needs_pathway_files
def test_ticking_a_task_updates_progress_next_task_and_done_tasks():
    at, name = _pathway_app()
    plan = _expected_plan(name)
    total = plan["totals"]["tasks"]
    assert _progress_text(at).startswith(f"0% done (0 of {total} tasks")
    assert at.session_state["done_tasks"] == []
    _done_boxes(at)[0].check().run()
    assert not at.exception
    first, second = plan["tasks"][0], plan["tasks"][1]
    percent = 100 * first["minutes"] / plan["totals"]["minutes"]
    assert _progress_text(at).startswith(f"{percent:.0f}% done (1 of {total} tasks, {first['minutes']} of ")
    assert at.session_state["done_tasks"] == [first["id"]]
    assert f"Next task: {second['title']} ({second['minutes']} min, {second['date']})" in _joined(at)
    assert f"~~{first['title']}~~" in _joined(at)
    for box in _done_boxes(at)[1:]:
        box.check()
    at.run()
    assert _progress_text(at).startswith(f"100% done ({total} of {total} tasks")
    assert "Next task: none left" in _joined(at)
    completed = next(m.value for m in at.markdown if m.value.startswith("Skills completed: "))
    assert all(skill in completed for skill in dict.fromkeys(t["skill"] for t in plan["tasks"]))
    # a new plan (other pace) starts with nothing ticked
    at.number_input(key="pathway_hours").set_value(10).run()
    assert at.session_state["done_tasks"] == []
    assert _progress_text(at).startswith("0% done")


@needs_real_data
@needs_pathway_files
def test_pathway_counts_overdue_tasks_against_today():
    today = pathway_mod.today_myt()
    start = today - dt.timedelta(days=21)  # a plan that began three weeks ago
    at, name = _pathway_app()
    at.date_input(key="pathway_start").set_value(start).run()
    assert not at.exception
    plan = _expected_plan(name, start=start)
    overdue = [t for t in plan["tasks"] if dt.date.fromisoformat(t["deadline"]) < today]
    assert overdue
    assert f"Overdue as of {today.isoformat()}: {len(overdue)} task" in _joined(at)
    assert sum(m.value.endswith("(overdue)") for m in at.markdown) == len(overdue)
    _done_boxes(at)[0].check().run()  # a done task is no longer overdue
    assert f"Overdue as of {today.isoformat()}: {len(overdue) - 1} task" in _joined(at)


@needs_real_data
@needs_pathway_files
def test_pathway_download_buttons_carry_markdown_and_calendar_text(monkeypatch):
    captured = {}
    original = DeltaGenerator.download_button

    def spy(self, label, data=None, *args, **kwargs):
        captured[kwargs.get("file_name")] = data
        return original(self, label, data, *args, **kwargs)

    monkeypatch.setattr(DeltaGenerator, "download_button", spy)
    at, name = _pathway_app()
    assert not at.exception
    assert [b.label for b in at.get("download_button")] == ["Download plan (Markdown)", "Download calendar (.ics)"]
    assert set(captured) == {"verity_plan.md", "verity_plan.ics"}
    assert captured["verity_plan.md"].startswith("# ")
    assert captured["verity_plan.md"].startswith(f"# Reskilling pathway: {name}")
    assert captured["verity_plan.ics"].startswith("BEGIN:VCALENDAR")
    assert captured["verity_plan.ics"].count("BEGIN:VEVENT") == len(_expected_plan(name)["tasks"])


@needs_real_data
@needs_pathway_files
def test_hrd_note_is_shown_once_and_comes_from_resources_json():
    at, _ = _pathway_app()
    note = json.loads((DATA / "resources.json").read_text(encoding="utf-8"))["hrd_corp_note"]
    assert [i.value for i in at.info if note in i.value] == [f"HRD Corp: {note}"]
    assert _joined(at).count(note) == 1


@needs_real_data
@needs_pathway_files
def test_sdg_section_leads_with_plan_level_sentences_and_keeps_tags_in_an_expander():
    at, name = _pathway_app()
    plan = _expected_plan(name)
    n_skills = sum(1 for st_ in plan["steps"] if st_["resource"])
    assert all(st_["resource"]["cost"] == "free" for st_ in plan["steps"] if st_["resource"])
    markdown = [m.value for m in at.markdown]
    assert (f"SDG 4.4 (indicator 4.4.1, ICT skills for employment): this plan adds {n_skills} job-listed skills "
            f"in {plan['totals']['hours']} hours (estimate) at RM0 cost using free resources.") in markdown
    role = next(r for r in roles_mod.match_roles(
        set(PERSONA_SKILLS), roles_mod.profile_for(_scores()["as_of"], json.loads(
            (DATA / "role_profiles.json").read_text(encoding="utf-8"))), _scores(),
        roles_mod.build_role_trends(roles_mod.read_demand_rows(DATA / "role_demand_monthly.csv"),
                                    roles_mod.load_roles(DATA / "roles.json"), as_of=_scores()["as_of"]),
        "moderate", exposure=roles_mod.load_exposure(DATA / "exposure.csv"))["roles"] if r["name"] == name)
    out = role["outlook"]
    if out["trend_label"]:
        demand = (f"{out['trend_label']}, {100 * out['share_last12']:.1f}% of posts in the last 12 months vs "
                  f"{100 * out['share_prev12']:.1f}% the 12 months before")
    else:
        demand = "no trend label: too few posts"
    assert f"SDG 8.5 (full and productive employment): moves you toward {name} (role demand: {demand})." in markdown
    assert not any(m.startswith("- SDG ") for m in markdown)         # the step-counting line is gone
    assert not any(m.startswith("How this plan contributes") for m in markdown)
    expander = next(e for e in at.expander if e.label == "SDG tags per skill")
    tags = " ".join(m.value for m in expander.markdown)
    for step in plan["steps"]:
        assert f"- {step['skill']}: SDG {', '.join(step['sdg'])}. {step['sdg_reason']}" in tags


@needs_real_data
@needs_pathway_files
def test_change_target_role_clears_the_target_and_only_the_roles_tab_sets_it():
    at, name = _pathway_app()
    assert f"**Target role:** {name}" in _joined(at)
    at.button(key="change_target_role").click().run()
    assert not at.exception
    assert "target_role" not in at.session_state
    assert NO_TARGET_PROMPT in [i.value for i in at.info]
    assert "**Target role:** none chosen yet" in _joined(at)
    assert not any(b.key == "change_target_role" for b in at.button)
    at.button(key="target_ml_engineer").click().run()
    assert at.session_state["target_role"] == "ML Engineer"
    assert [s.value for s in at.subheader if s.value.startswith("Pathway to")] == ["Pathway to ML Engineer"]


@needs_real_data
@needs_pathway_files
def test_a_low_match_role_can_be_the_target_and_gets_a_plan():
    at = _run_app()
    at.selectbox(key="role_persona").set_value(PERSONA_LABELS[1]).run()  # Ben: some roles are under 20%
    low = next(iter(_low(at)))
    at.button(key=f"target_{ROLE_KEYS[low]}").click().run()
    assert not at.exception
    assert _done_boxes(at) and f"Pathway to {low}" in [s.value for s in at.subheader]


@needs_real_data
@needs_pathway_files
def test_pathway_tab_writes_no_file_under_data():
    before = _tree_snapshot()
    at, _ = _pathway_app()
    _done_boxes(at)[0].check().run()
    at.sidebar.radio[0].set_value("fast").run()
    at.number_input(key="pathway_hours").set_value(12).run()
    assert not at.exception
    assert _tree_snapshot() == before


# --- review fixes: no-regret rule, tick signature, Malaysia time --------------------------

PERSONA_LABEL_SKILLS = {
    PERSONA_LABELS[0]: PERSONA_SKILLS,
    PERSONA_LABELS[1]: ["JavaScript / TypeScript", "TypeScript", "React", "Node.js"],
    PERSONA_LABELS[2]: ["SQL", "Python", "Snowflake", "dbt"],
}


def _no_regret(plan: dict) -> list[str]:
    return [s["skill"] for s in plan["steps"] if s["stage"] == "no_regret"]


@needs_real_data
@needs_pathway_files
def test_no_regret_stage_counts_the_target_and_all_ranked_roles_on_real_data():
    shown = {}
    for label, skills in PERSONA_LABEL_SKILLS.items():
        at = _run_app()
        at.selectbox(key="role_persona").set_value(label).run()
        top = _role_name(_cards(at)[0])
        at.session_state["target_role"] = top
        at.run()
        assert not at.exception
        expected = _no_regret(_expected_plan(top, skills=skills))
        page = [m.value for m in at.markdown if m.value.startswith("Why: Needed by")]
        assert len(page) == len(expected)                      # the page shows the same no-regret steps
        shown[label] = expected
    assert any(shown.values())                                  # at least one persona has a Stage 1
    assert shown[PERSONA_LABELS[2]] == ["LLM / GenAI"]          # Chloe: top role AI/LLM Application Engineer
    assert shown[PERSONA_LABELS[1]] == []                       # Ben: only one ranked role
    # Aina (target Backend Engineer, 7 ranked roles) gets Node.js; the other examples from the review:
    assert _no_regret(_expected_plan("Backend Engineer")) == ["Node.js"]
    assert _no_regret(_expected_plan("AI/LLM Application Engineer")) == ["LLM / GenAI"]
    assert _no_regret(_expected_plan("Data Engineer")) == ["Machine Learning"]
    chloe = PERSONA_LABEL_SKILLS[PERSONA_LABELS[2]]
    assert _no_regret(_expected_plan("Data Scientist", skills=chloe)) == ["Machine Learning", "LLM / GenAI"]


@needs_real_data
@needs_pathway_files
def test_stage_one_section_is_filled_on_the_page_for_aina_and_backend_engineer():
    at, name = _pathway_app(target="Backend Engineer")
    assert name == "Backend Engineer"
    why = [m.value for m in at.markdown if m.value.startswith("Why: Needed by")]
    assert len(why) == 1 and "of the 7 roles counted (your target and your ranked roles)" in why[0]
    assert "**1. Node.js**" in [m.value for m in at.markdown]


@needs_real_data
@needs_pathway_files
def test_a_tick_never_moves_to_another_task_when_the_plan_changes():
    at, name = _pathway_app(target="Backend Engineer")
    first = _expected_plan(name)["tasks"][0]
    assert first["skill"] != "Kubernetes"
    _done_boxes(at)[0].check().run()
    assert at.session_state["done_tasks"] == [first["id"]]
    skills = list(at.multiselect(key="role_skills").value)
    at.multiselect(key="role_skills").set_value(skills + [first["skill"]]).run()   # add the first skill
    assert not at.exception
    changed = _expected_plan(name, skills=PERSONA_SKILLS + [first["skill"]])
    assert changed["tasks"][0]["title"] != first["title"]       # the plan changed (T001 is another task)
    assert at.session_state["done_tasks"] == []
    assert not any(box.value for box in _done_boxes(at))
    assert _progress_text(at).startswith("0% done")


@needs_real_data
@needs_pathway_files
def test_plan_uses_malaysia_time_when_it_is_still_yesterday_in_utc(monkeypatch):
    class Clock(dt.datetime):
        @classmethod
        def now(cls, tz=None):                      # 01:00 on Monday 2026-10-26 in Malaysia
            return dt.datetime(2026, 10, 26, 1, 0, tzinfo=tz)

    monkeypatch.setattr(pathway_mod, "datetime", Clock)
    assert dt.datetime(2026, 10, 26, 1, 0, tzinfo=pathway_mod.MYT).astimezone(dt.timezone.utc).date() \
        == dt.date(2026, 10, 25)                    # still Sunday in UTC
    at, name = _pathway_app()
    assert not at.exception
    assert at.date_input(key="pathway_start").value == dt.date(2026, 11, 2)   # the Monday after the MYT Monday
    assert "Overdue as of 2026-10-26:" in _joined(at)


# --- the four-step journey, the Future Skills Radar and the Evidence section -------------------------

import ast
import statistics

JOURNEY_STEPS = ["1 You", "2 Skills radar", "3 Future roles", "4 Your plan"]


def _expected_radar(skills_list: list[dict]) -> tuple[list[dict], float]:
    """The plotted skills (ok or low_volume, a positive share and prior mentions) and the median share,
    worked out here from the file with its own code, not with engine.radar."""
    plotted = [s for s in skills_list if s["status"] in ("ok", "low_volume")
               and s["demand_share_latest"] and s["demand_share_latest"] > 0 and s["mentions_prev12"] > 0]
    return plotted, statistics.median(s["demand_share_latest"] for s in plotted)


def _expected_user_counts(my_skills: list[str], skills_list: list[dict]) -> dict:
    plotted, cut = _expected_radar(skills_list)
    mine = [s for s in plotted if s["skill"] in my_skills]
    steady = [s for s in mine if s["trend_label"] not in ("Rising", "Falling")]
    return {"on_chart": len(mine),
            "rising": sorted(s["skill"] for s in mine if s["trend_label"] == "Rising"),
            "falling": sorted(s["skill"] for s in mine if s["trend_label"] == "Falling"),
            "strong": sum(s["demand_share_latest"] >= cut for s in steady),
            "small": sum(s["demand_share_latest"] < cut for s in steady)}


def _sentence(at: AppTest, start: str) -> str:
    return next(m.value for m in at.markdown if m.value.startswith(start))


def _radar_points(at: AppTest) -> pd.DataFrame:
    """The radar's rows, one per skill, read back from the chart data on the page."""
    frames = [f for f in _chart_frames(at) if {"mark", "mine", "quadrant"} <= set(f.columns)]
    assert frames, "no radar chart on the page"
    return pd.concat(frames).drop_duplicates("skill").reset_index(drop=True)


def _parse_your_skills(sentence: str) -> dict:
    """'Your skills: 4 strong and steady, [1 small and steady,] 1 rising (A, B), 0 falling.'"""
    def names(word):
        hit = re.search(rf"\d+ {word}(?: \(([^)]*)\))?", sentence)
        return sorted(hit.group(1).split(", ")) if hit and hit.group(1) else []
    small = re.search(r"(\d+) small and steady", sentence)
    return {"strong": int(re.search(r"(\d+) strong and steady", sentence).group(1)),
            "small": int(small.group(1)) if small else 0,
            "rising": names("rising"), "falling": names("falling")}


@needs_real_data
@needs_role_files
@pytest.mark.parametrize("label", PERSONA_LABELS)
def test_the_journey_renders_for_each_persona(label):
    at = _run_app()
    at.selectbox(key="role_persona").set_value(label).run()
    assert not at.exception
    assert [t.label for t in at.tabs][:5] == JOURNEY_STEPS + ["Evidence"]
    text = _joined(at)
    assert "Tell us your skills. A CV upload is coming." in text            # step 1
    assert "**Next:** see how your skills are trending." in text
    assert "Future Skills Radar" in [s.value for s in at.subheader]          # step 2
    assert len(at.get("arrow_vega_lite_chart")) + len(at.get("vega_lite_chart")) >= 1
    assert any(m.value.startswith("**Best fit now: ") for m in at.markdown)   # step 3
    assert _cards(at)
    assert NO_TARGET_PROMPT in [i.value for i in at.info]                     # step 4 waits for a target
    assert "Estimates, not facts. You decide." in text
    assert any(e.label == "About the data" for e in at.expander)


@needs_real_data
@needs_role_files
def test_step_1_has_a_cv_slot_that_shows_nothing_yet():
    at = _run_app()
    assert not at.exception
    assert len(at.get("file_uploader")) == 0
    assert [b.label for b in at.button if b.key == "next_to_radar"] == ["See the skills radar"]


def test_the_cv_slot_and_the_sdg_sector_hook_exist_and_show_nothing(tmp_path):
    """Both hooks are plain functions in app.py. Run them alone, so the app does not have to start.

    sdg_sector_block draws only when the role carries a goal view ("sdg_goal"); a role without one shows nothing.
    """
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    wanted = {"cv_intake_slot", "sdg_sector_block"}
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {f.name for f in funcs} == wanted
    namespace = {"DEFAULT_DATA_DIR": tmp_path}  # an empty folder: data/role_sdg.json is missing
    exec(compile(ast.Module(body=funcs, type_ignores=[]), "app.py", "exec"), namespace)
    assert namespace["cv_intake_slot"]() is None
    assert namespace["sdg_sector_block"]({"name": "Backend Engineer"}) is None


@needs_real_data
@needs_role_files
def test_the_radar_plots_every_ok_or_low_volume_skill_and_rings_the_users_skills():
    scores = _scores()
    plotted, cut = _expected_radar(scores["skills"])
    at = _run_app()
    assert not at.exception
    points = _radar_points(at)
    assert len(points) == len(plotted) and set(points["skill"]) == {s["skill"] for s in plotted}
    assert not (set(points["skill"]) & {s["skill"] for s in scores["skills"] if s["status"] == "rare"})
    assert set(points.loc[points["mine"], "skill"]) == set(PERSONA_SKILLS)     # Aina's five skills
    assert len(points[points["mine"]]) == 5
    # a colour mark only for a tested Rising or Falling label; every other skill is grey
    label_of = {s["skill"]: s["trend_label"] for s in scores["skills"]}
    for row in points.itertuples():
        tested = label_of[row.skill] in ("Rising", "Falling")
        assert (row.mark != "grey") == tested, row.skill
        assert (row.group == "No clear change") == (not tested), row.skill
    robust = pd.read_csv(DATA / "exposure_robustness.csv")
    contested = set(robust.loc[robust["stance_robust"].astype(str).str.lower() == "false", "skill"])
    assert all(row.contested == (row.skill in contested) for row in points.itertuples())
    assert all(row.mark == "hollow" for row in points.itertuples() if row.contested and row.mark != "grey")
    # x is the latest share, y the change in share, both from the file
    by_skill = {s["skill"]: s for s in plotted}
    for row in points.itertuples():
        s = by_skill[row.skill]
        assert row.share == pytest.approx(s["demand_share_latest"])
        change = (s["mentions_last12"] / s["posts_last12"]) / (s["mentions_prev12"] / s["posts_prev12"]) - 1
        assert row.change == pytest.approx(change)


@needs_real_data
@needs_role_files
@pytest.mark.parametrize("label", PERSONA_LABELS)
def test_the_quadrant_counts_in_the_summary_sentences_match_the_data(label):
    scores = _scores()
    my = PERSONA_LABEL_SKILLS[label]
    plotted, _ = _expected_radar(scores["skills"])
    at = _run_app()
    at.selectbox(key="role_persona").set_value(label).run()
    assert not at.exception
    want = _expected_user_counts(my, scores["skills"])
    got = _parse_your_skills(_sentence(at, "Your skills: "))
    assert got == {"strong": want["strong"], "small": want["small"],
                   "rising": want["rising"], "falling": want["falling"]}
    assert want["on_chart"] == want["strong"] + want["small"] + len(want["rising"]) + len(want["falling"])
    n_rising = sum(s["trend_label"] == "Rising" for s in plotted)
    n_falling = sum(s["trend_label"] == "Falling" for s in plotted)
    assert _sentence(at, "Across all ") == (
        f"Across all {len(plotted)} skills on the chart: {n_rising} rising, {n_falling} falling and "
        f"{len(plotted) - n_rising - n_falling} with no clear change over the last 12 months.")
    movers = _sentence(at, "Tested movers")
    assert all(s["skill"] in movers for s in plotted if s["trend_label"] in ("Rising", "Falling"))


@needs_real_data
@needs_role_files
def test_the_radar_caption_gives_the_backtest_hit_rate_and_how_to_read_it():
    bt = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))["trend_label_backtest"]
    at = _run_app()
    caption = next(c.value for c in at.caption if c.value.startswith("How to read it"))
    assert f"{bt['trend_label_hit_rate']:.0%} of the time" in caption and f"n = {bt['n']}" in caption
    for needle in ("log scale", "Hacker News", "hollow", "Grey", "black ring"):
        assert needle in caption


@needs_real_data
@needs_role_files
def test_the_radar_follows_the_as_of_slider():
    from engine.scores import build_scores

    at = _run_app()
    now = _radar_points(at).set_index("skill")
    at.sidebar.select_slider[0].set_value("2023-12").run()
    assert not at.exception
    old = build_scores(as_of="2023-12")["skills"]
    plotted, _ = _expected_radar(old)
    points = _radar_points(at).set_index("skill")
    assert set(points.index) == {s["skill"] for s in plotted}
    for s in plotted:
        assert points.loc[s["skill"], "share"] == pytest.approx(s["demand_share_latest"])
    assert not points["share"].equals(now["share"].reindex(points.index))   # a different month, other shares


@needs_real_data
@needs_role_files
def test_the_radar_survives_a_fixture_without_history(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception
    assert "Future Skills Radar" in [s.value for s in at.subheader]


@needs_real_data
@needs_pathway_files
def test_step_3_best_fit_line_and_the_next_buttons_move_the_journey():
    at = _run_app()
    top = _cards(at)[0]
    name, match = _role_name(top), _matches(at)[0]
    outlook = next(m for m in at.markdown if m.value.startswith("Role demand:") and "badge" in m.value).value
    label = re.search(r":\w+-badge\[([^\]]+)\]", outlook).group(1)
    assert f"**Best fit now: {name} ({match}% match, demand {label})**" in [m.value for m in at.markdown]
    at.button(key="next_to_radar").click().run()
    assert at.session_state["journey_step"] == "2 Skills radar"
    at.button(key="next_to_roles").click().run()
    assert at.session_state["journey_step"] == "3 Future roles"
    assert not any(b.key == "next_to_plan" for b in at.button)    # only after a target is chosen
    at.button(key=f"target_{ROLE_KEYS[name]}").click().run()
    assert at.session_state["target_role"] == name
    at.button(key="next_to_plan").click().run()
    assert at.session_state["journey_step"] == "4 Your plan" and not at.exception
    at.button(key="change_target_role").click().run()              # clearing the target returns to step 3
    assert "target_role" not in at.session_state and at.session_state["journey_step"] == "3 Future roles"


@needs_real_data
@needs_pathway_files
def test_step_4_leads_with_a_summary_card_and_the_no_regret_skills():
    at, name = _pathway_app(target="Backend Engineer")
    plan = _expected_plan(name)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics == {"Skills to learn": str(plan["totals"]["steps"]),
                       "Hours (estimate)": f"{plan['totals']['hours']:g}",
                       "Finish date": plan["finish_date"]}
    markdown = [m.value for m in at.markdown]
    assert f"**Your plan in short:** become a {name}." in markdown
    assert _no_regret(plan) == ["Node.js"]
    assert "No-regret skills (useful for several of your roles): Node.js." in markdown
    assert ("This plan still works if the forecast is wrong: it starts with skills useful for several of "
            "your roles.") in markdown
    # the card comes before the plan's stages
    first_stage = next(i for i, v in enumerate(markdown) if v.startswith("### Stage 1"))
    assert markdown.index(f"**Your plan in short:** become a {name}.") < first_stage


@needs_real_data
@needs_pathway_files
def test_step_4_does_not_claim_a_no_regret_start_when_there_is_none():
    at = _run_app()
    at.selectbox(key="role_persona").set_value(PERSONA_LABELS[1]).run()      # Ben: no no-regret skills
    target = _role_name(_cards(at)[0])
    at.session_state["target_role"] = target
    at.run()
    assert not at.exception
    assert _no_regret(_expected_plan(target, skills=PERSONA_LABEL_SKILLS[PERSONA_LABELS[1]])) == []
    text = _joined(at)
    assert "No-regret skills (useful for several of your roles)" not in text
    assert "it starts with skills useful for several of your roles" not in text
    assert "so this plan follows what employers ask for now, not the forecast" in text


@needs_real_data
def test_the_evidence_section_still_renders_skills_detail_and_method():
    scores = _scores()
    at = _run_app()
    assert not at.exception
    assert [t.label for t in at.tabs][-3:] == EVIDENCE_TABS
    assert len(_skills_table(at)) == len(scores["skills"])                      # Skills
    _pick_skill(at, "Python")                                                    # Skill detail
    assert not at.exception and "Python" in [s.value for s in at.subheader]
    assert "Trend label:" in _joined(at)
    assert "How good is the forecast?" in _joined(at)                            # Method


@needs_real_data
def test_the_header_is_short_and_the_long_notes_sit_in_about_the_data():
    at = _run_app()
    about = next(e for e in at.expander if e.label == "About the data")
    inside = " ".join(m.value for m in about.markdown) + " " + " ".join(c.value for c in about.caption)
    assert "Forecast model: naive3 (mean of last 3 months)" in inside
    assert "No LLM is used in this view." in inside
    assert "File: data/skill_scores.json" in inside
    assert "honest ranges, not with forecast numbers" in inside               # the finding that frames the product
    top_level = [m.value for m in at.markdown]
    assert ("Decision support under uncertainty: tested trend labels, honest ranges, and a plan that still "
            "works if the forecast is wrong.") in top_level
    assert "Estimates, not facts. You decide." in top_level
    assert not about.proto.expanded                                            # collapsed by default


# --- Integration: SDG goal, MyCOL badges, Method subsections --------------------------
# The goal selector and the order radio sit in step 3, the plan SDG lines in step 4, the badges on the role
# cards. Expected values are worked out here from the data files and the engine functions, not from app.py.

from engine import sdg as sdg_mod

NO_GOAL = "No preference"
GOAL_KEY, ORDER_KEY = "sdg_goal", "roles_order_by"
ORDER_BEST, ORDER_GOAL = "Best fit", "Fit for my goal"
MYCOL_MARK = "Critical Occupations List"
MYCOL_CAPTION = ("MyCOL is TalentCorp's list of occupations in short supply in Malaysia; the mapping to our "
                 "roles is team judgement.")
NO_SNAPSHOT = "No Malaysian job-site snapshot yet: collectors need written permission from each site."
PRECISION_COLUMN = "Precision (hand check, docs/sdg-links.md)"
needs_integration_files = pytest.mark.skipif(
    not all((DATA / n).exists() for n in (
        "role_sdg.json", "sdg_sectors.json", "mycol.json", "mycol_role_map.json", "role_forecast.json",
        "role_backtest.json", "resources.json", "taxonomy.json", "role_profiles.json", "role_demand_monthly.csv",
        "roles.json", "exposure.csv", "skill_scores.json")),
    reason="integration data files not generated yet")


def _data_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _goal_label(sector_id: str) -> str:
    sector = next(s for s in _data_json("sdg_sectors.json")["sectors"] if s["id"] == sector_id)
    return f"{sector['name']} (SDG {' / '.join(sector['sdg'])})"


def _expected_match(skills: list[str] | None = None, scenario: str = "moderate") -> dict:
    """match_roles output straight from the engines for a profile (default: Aina)."""
    scores = _scores()
    profile = roles_mod.profile_for(scores["as_of"], _data_json("role_profiles.json"))
    trends = roles_mod.build_role_trends(roles_mod.read_demand_rows(DATA / "role_demand_monthly.csv"),
                                         roles_mod.load_roles(DATA / "roles.json"), as_of=scores["as_of"])
    return roles_mod.match_roles(set(skills or PERSONA_SKILLS), profile, scores, trends, scenario,
                                 exposure=roles_mod.load_exposure(DATA / "exposure.csv"))


def _pick_goal(at: AppTest, sector_id: str) -> AppTest:
    return at.selectbox(key=GOAL_KEY).set_value(_goal_label(sector_id)).run()


def _card_names(at: AppTest) -> list[str]:
    return [_role_name(c) for c in _cards(at)]


def _walk(node):
    for child in node.children.values():
        yield child
        if hasattr(child, "children"):
            yield from _walk(child)


def _card_texts(at: AppTest) -> dict[str, list[str]]:
    """Role name -> every markdown and caption text inside that role's bordered card, in order."""
    found = {}

    def visit(node):
        for child in node.children.values():
            if not hasattr(child, "children"):
                continue
            head = next((c.value for c in child.children.values()
                         if getattr(c, "type", "") == "markdown" and c.value.startswith("### #")), None)
            if head:
                found[_role_name(head.removeprefix("### "))] = [
                    c.value for c in _walk(child) if getattr(c, "type", "") in ("markdown", "caption")]
            else:
                visit(child)

    visit(at.main)
    return found


def _app_copy(tmp_path: Path, drop: tuple[str, ...] = (), write: dict[str, str] | None = None) -> AppTest:
    """The app run from a copy of app.py, engine/ and data/ (no raw folder, no docs/) in `tmp_path`.

    `drop` names data files to leave out. `write` maps a data file name to the text it gets (after the drop).
    """
    shutil.copy(APP_PATH, tmp_path / "app.py")
    shutil.copytree(ROOT / "engine", tmp_path / "engine", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(DATA, tmp_path / "data", ignore=shutil.ignore_patterns("raw", *drop))
    for name, text in (write or {}).items():
        (tmp_path / "data" / name).write_text(text, encoding="utf-8")
    return AppTest.from_file(str(tmp_path / "app.py"), default_timeout=90).run()


# -- the goal selector ------------------------------------------------------------------

@needs_real_data
@needs_integration_files
def test_goal_selector_offers_no_preference_and_every_sector_with_its_sdg_targets():
    at = _run_app()
    assert not at.exception
    box = at.selectbox(key=GOAL_KEY)
    sectors = _data_json("sdg_sectors.json")["sectors"]
    assert box.label == "What do you want your work to help with? (optional)"
    assert box.options == [NO_GOAL] + [_goal_label(s["id"]) for s in sectors]
    assert box.value == NO_GOAL
    assert any(o.startswith("Health and life sciences (SDG 3.8") for o in box.options)
    order = at.radio(key=ORDER_KEY)
    assert order.label == "Order roles by:" and order.options == [ORDER_BEST, ORDER_GOAL]
    assert order.value == ORDER_BEST
    assert order.proto.disabled                                           # nothing to order by yet
    captions = _captions(at)
    assert "Evidence > Method > SDG sector links" in captions               # method and limits, one sentence
    assert "it shows who hires, not what the work achieves" in captions
    assert not any(c.value.startswith("For your goal") for c in at.caption)


@needs_real_data
@needs_integration_files
@pytest.mark.parametrize("sector", ["health", "climate_energy"])
def test_the_goal_reorders_only_in_fit_for_my_goal_mode_and_never_hides_a_role(sector):
    out = _expected_match()
    best = [r["name"] for r in out["roles"]]
    low = {r["name"] for r in out["low_match"]}
    fit = [r["name"] for r in sdg_mod.rerank_for_goal(out, _data_json("role_sdg.json"), sector)["by_goal_fit"]]
    assert sorted(fit) == sorted(best)                                        # the engine itself drops nobody

    at = _run_app()
    assert _card_names(at) == best
    _pick_goal(at, sector)
    assert not at.exception
    assert _card_names(at) == best                                            # Best fit: the same order as before
    assert not any("by rank score" in c for c in _cards(at))
    assert not at.radio(key=ORDER_KEY).proto.disabled

    at.radio(key=ORDER_KEY).set_value(ORDER_GOAL).run()
    assert not at.exception
    assert _card_names(at) == fit                                             # the engine's goal order
    assert set(_low(at)) == low                                               # "Not a fit yet" roles stay listed
    if sector == "climate_energy":
        assert fit != best                                                    # for Aina this goal moves a role
        assert all("by rank score" in c for c in _cards(at))                  # a re-ordered list shows old ranks

    at.radio(key=ORDER_KEY).set_value(ORDER_BEST).run()
    assert _card_names(at) == best                                            # and back
    at.selectbox(key=GOAL_KEY).set_value(NO_GOAL).run()
    assert _card_names(at) == best and not at.exception


@needs_real_data
@needs_integration_files
def test_goal_order_replaces_the_sort_by_match_toggle_and_keeps_every_card():
    at = _run_app()
    n_cards = len(_cards(at))
    at.toggle(key="roles_sort_match").set_value(True).run()
    _pick_goal(at, "climate_energy")
    assert not at.toggle(key="roles_sort_match").proto.disabled               # still usable in Best fit mode
    assert _matches(at) == sorted(_matches(at), reverse=True)
    at.radio(key=ORDER_KEY).set_value(ORDER_GOAL).run()
    assert not at.exception and len(_cards(at)) == n_cards
    assert at.toggle(key="roles_sort_match").proto.disabled                   # one order at a time


# -- the goal sentence in the cards --------------------------------------------------------

@needs_real_data
@needs_integration_files
@pytest.mark.parametrize("sector", ["health", "climate_energy"])
def test_every_role_card_shows_its_goal_sentence_from_the_rerank_output(sector):
    out = _expected_match()
    goal_out = sdg_mod.rerank_for_goal(out, _data_json("role_sdg.json"), sector)
    at = _pick_goal(_run_app(), sector)
    assert not at.exception
    texts = _card_texts(at)
    assert set(texts) == {r["name"] for r in out["roles"]}
    reliable_seen = 0
    for role in goal_out["roles"]:
        goal = role["sdg_goal"]
        if goal["share"] is not None and not goal["reliable"]:
            expected = f"For your goal (rough, not used to re-order): {goal['sentence']}"
        else:
            expected = f"For your goal: {goal['sentence']}"
            reliable_seen += 1
        assert expected in texts[role["name"]], role["name"]
    assert reliable_seen
    captions = [c.value for c in at.caption]
    for role in goal_out["low_match"]:                                        # "Not a fit yet" roles carry it too
        assert any(role["sdg_goal"]["sentence"] in c for c in captions)


@needs_real_data
@needs_integration_files
def test_an_unreliable_cell_is_called_rough_and_a_reliable_one_is_not():
    out = _expected_match()
    goal_out = sdg_mod.rerank_for_goal(out, _data_json("role_sdg.json"), "health")
    rough = [r for r in goal_out["roles"] if not r["sdg_goal"]["reliable"] and r["sdg_goal"]["share"] is not None]
    assert rough, "the committed data should have a thin Health cell for one of Aina's roles"
    texts = _card_texts(_pick_goal(_run_app(), "health"))
    for role in rough:
        assert any(t.startswith("For your goal (rough") for t in texts[role["name"]])
    for role in goal_out["roles"]:
        if role["sdg_goal"]["reliable"]:
            assert not any("rough" in t for t in texts[role["name"]] if t.startswith("For your goal"))


@needs_real_data
@needs_integration_files
def test_the_role_forecast_line_still_shows_in_every_card_with_a_goal():
    at = _run_app()
    _pick_goal(at, "climate_energy")
    at.radio(key=ORDER_KEY).set_value(ORDER_GOAL).run()
    texts = _card_texts(at)
    assert texts
    for name, lines in texts.items():
        assert sum(t.startswith("Share of HN hiring posts now") for t in lines) == 1, name


@needs_real_data
@needs_integration_files
def test_a_past_as_of_month_says_the_sector_shares_do_not_move():
    at = _run_app()
    assert not any("do not move with the As-of slider" in c.value for c in at.caption)
    at.sidebar.select_slider[0].set_value("2024-06").run()
    assert not at.exception
    assert any("do not move with the As-of slider" in c.value for c in at.caption)


# -- the MyCOL badges ------------------------------------------------------------------------

@needs_real_data
@needs_integration_files
def test_mycol_badges_appear_only_on_roles_the_map_links_to_an_occupation():
    mapping = _data_json("mycol_role_map.json")["mappings"]
    occupations = {o["masco_code"]: o for o in _data_json("mycol.json")["occupations"]}
    texts = _card_texts(_run_app())
    mapped_seen = unmapped_seen = 0
    for name, lines in texts.items():
        role_id = ROLE_KEYS[name]
        badges = [t for t in lines if MYCOL_MARK in t]
        links = [m for m in mapping if m["role_id"] == role_id]
        assert len(badges) == len(links), name
        if not links:
            unmapped_seen += 1
            continue
        mapped_seen += 1
        for link in links:
            occ = occupations[link["masco_code"]]
            badge = next(b for b in badges if f"{link['occupation']} (MASCO {link['masco_code']})" in b)
            assert f"On Malaysia's Critical Occupations List {occ['year']}: " in badge
            assert f"{link['strength']} match" in badge
            assert f"({occ['source_url']})" in badge                           # the source link
    assert mapped_seen and unmapped_seen                                        # Aina sees both kinds of role


@needs_real_data
@needs_integration_files
def test_one_mycol_caption_gives_the_plain_meaning_and_the_team_judgement_note():
    captions = [c.value for c in _run_app().caption]
    assert captions.count(MYCOL_CAPTION) == 1


@needs_real_data
@needs_integration_files
def test_a_direct_mycol_match_is_marked_direct_and_comes_before_the_partial_ones():
    backend = [t for t in _card_texts(_run_app())["Backend Engineer"] if MYCOL_MARK in t]
    assert "Software Developers (MASCO 2512)" in backend[0] and "direct match" in backend[0]
    assert len(backend) > 1 and all("partial match" in t for t in backend[1:])


# -- step 3 summary line and step 4 SDG lines --------------------------------------------------

@needs_real_data
@needs_integration_files
def test_the_step_3_summary_line_adds_the_target_roles_12_month_estimate_and_band():
    forecast = _data_json("role_forecast.json")
    item = forecast["roles"]["backend_engineer"]["forecast_moderate"]
    at = _run_app()
    assert "**Target role:** none chosen yet" in [m.value for m in at.markdown]
    at.button(key="target_backend_engineer").click().run()
    label = forecast["interval"]["label"]
    assert (f"**Target role:** Backend Engineer. 12-month estimate {item['value_12m']:.1%} of HN hiring posts "
            f"({label} {item['low']:.1%}–{item['high']:.1%}).") in [m.value for m in at.markdown]


@needs_real_data
@needs_integration_files
def test_the_step_3_summary_line_has_no_estimate_when_the_role_forecast_file_is_missing(tmp_path):
    at = _app_copy(tmp_path, drop=("role_forecast.json",))
    at.button(key="target_backend_engineer").click().run()
    assert not at.exception
    assert "**Target role:** Backend Engineer" in [m.value for m in at.markdown]


@needs_real_data
@needs_integration_files
@pytest.mark.parametrize("goal", [None, "health", "climate_energy"])
def test_the_plan_sdg_lines_come_from_plan_sdg_summary_with_the_goal_from_step_3(goal):
    target = "Backend Engineer"
    at = _run_app()
    if goal:
        _pick_goal(at, goal)
    at.session_state["target_role"] = target
    at.run()
    assert not at.exception
    role = next(r for r in _expected_match()["roles"] if r["name"] == target)
    lines = sdg_mod.plan_sdg_summary(_expected_plan(target), role, _data_json("role_sdg.json"), goal)["lines"]
    assert len(lines) == (3 if goal else 2)
    markdown = [m.value for m in at.markdown]
    start = markdown.index("### SDG links")
    assert markdown[start + 1:start + 1 + len(lines)] == lines                 # in this order, right under the heading
    if goal:
        assert "employers (SDG" in lines[-1] and "of all posts" in lines[-1]
    assert any(e.label == "SDG tags per skill" for e in at.expander)           # per-skill tags stay in their expander


# -- Evidence > Method ------------------------------------------------------------------------

def _doc_precision() -> dict[str, str]:
    """Sector -> precision cell, read from docs/sdg-links.md with a different parser from app.py."""
    text = (ROOT / "docs" / "sdg-links.md").read_text(encoding="utf-8")
    block = text.split("## Precision (hand check)")[1].split("\n## ")[0]
    rows = [line for line in block.splitlines() if line.startswith("|")][2:]
    return {cells[0]: cells[1] for cells in ([c.strip() for c in row.strip("|").split("|")] for row in rows)}


@needs_real_data
@needs_integration_files
def test_method_tab_renders_the_sdg_sector_links_subsection_from_the_files():
    role_sdg = _data_json("role_sdg.json")
    at = _run_app()
    assert not at.exception
    assert "SDG sector links" in [h.value for h in at.header]
    text = _joined(at)
    assert role_sdg["method"] in text
    window = role_sdg["window"]["recent"]
    assert f"{window['from']} to {window['to']} ({window['n_posts']} posts)" in text
    assert f"at least {sdg_mod.MIN_N} role posts and {sdg_mod.MIN_EMPLOYERS} different employers" in text
    assert f"1 + {sdg_mod.GOAL_WEIGHT} x min(max(lift - 1, 0), {sdg_mod.MAX_EXCESS:g})" in text
    for limit in ("US start-ups", "association, not impact", "do not move with the As-of slider"):
        assert limit in text
    table = next(d.value for d in at.dataframe if PRECISION_COLUMN in d.value.columns)
    precision = _doc_precision()
    assert len(table) == len(role_sdg["sectors"])
    for _, row in table.iterrows():
        sector = next(s for s in role_sdg["sectors"] if s["name"] == row["Sector"])
        base = role_sdg["baseline"]["sectors"][sector["id"]]
        assert row[PRECISION_COLUMN] == precision[sector["name"]]
        assert row["Tagged posts, last window"] == base["count_recent"]
        assert row["Different employers"] == base["employers_recent"]
        assert row["SDG"] == " / ".join(sector["sdg"])


@needs_real_data
@needs_integration_files
def test_method_tab_renders_the_malaysia_data_subsection_from_the_files():
    mycol = _data_json("mycol.json")["source"]
    links = _data_json("mycol_role_map.json")["mappings"]
    at = _run_app()
    assert "Malaysia data" in [h.value for h in at.header]
    text = _joined(at)
    assert f"**MyCOL {mycol['year']}** ({mycol['name']}), published by {mycol['publisher']}" in text
    assert f"Retrieved {mycol['retrieved']}" in text
    assert f"[{mycol['landing_page']}]({mycol['landing_page']})" in text
    assert (f"{len(links)} links, {sum(m['strength'] == 'direct' for m in links)} direct and "
            f"{sum(m['strength'] == 'partial' for m in links)} partial") in text
    assert "MyCOL is a shortage list, not a vacancy count" in text
    snapshots = pd.read_csv(DATA / "my_jobs_snapshots.csv")
    if snapshots.empty:
        assert NO_SNAPSHOT in text
    else:
        assert NO_SNAPSHOT not in text
        assert f"snapshot of {snapshots['snapshot_date'].max()}" in text


@needs_real_data
@needs_integration_files
def test_a_job_site_snapshot_in_the_csv_is_shown_with_its_date_and_listing_count(tmp_path):
    csv = ("snapshot_date,site,skill,mentions,n_listings,share\n"
           "2026-10-24,hiredly,Python,6,30,0.2\n2026-10-24,hiredly,SQL,3,30,0.1\n")
    at = _app_copy(tmp_path, write={"my_jobs_snapshots.csv": csv})
    assert not at.exception
    text = _joined(at)
    assert "**hiredly**: snapshot of 2026-10-24, 30 listings." in text
    assert NO_SNAPSHOT not in text
    table = next(d.value for d in at.dataframe if "Share of listings" in d.value.columns)
    assert list(table["Skill"]) == ["Python", "SQL"] and list(table["Share of listings"]) == ["20.0%", "10.0%"]


@needs_real_data
@needs_integration_files
def test_the_precision_column_says_n_a_when_the_docs_are_not_shipped(tmp_path):
    at = _app_copy(tmp_path)                      # the copy has no docs/ folder
    assert not at.exception
    table = next(d.value for d in at.dataframe if PRECISION_COLUMN in d.value.columns)
    assert set(table[PRECISION_COLUMN]) == {"n/a"}


# -- missing or broken optional files ----------------------------------------------------------

@needs_real_data
@needs_integration_files
@pytest.mark.parametrize("drop,write", [
    (("role_sdg.json",), None),
    (("mycol.json",), None),
    (("mycol_role_map.json",), None),
    (("role_sdg.json", "sdg_sectors.json", "mycol.json", "mycol_role_map.json", "my_jobs_snapshots.csv"), None),
    ((), {"role_sdg.json": "{not json"}),
    ((), {"role_sdg.json": "[]"}),
    ((), {"role_sdg.json": json.dumps({"sectors": [], "roles": {}, "baseline": {}})}),
    ((), {"mycol.json": "{not json"}),
    ((), {"mycol_role_map.json": json.dumps({"mappings": "oops"})}),
], ids=["no-role-sdg", "no-mycol", "no-mycol-map", "none-of-them", "role-sdg-bad-json", "role-sdg-list",
        "role-sdg-empty", "mycol-bad-json", "map-bad-shape"])
def test_the_app_runs_when_the_sdg_or_mycol_files_are_missing_or_broken(tmp_path, drop, write):
    at = _app_copy(tmp_path, drop=drop, write=write)
    assert not at.exception
    files = set(drop) | set(write or {})
    gone_sdg = "role_sdg.json" in files
    gone_mycol = bool(files & {"mycol.json", "mycol_role_map.json"})
    texts = _card_texts(at)
    assert len(texts) == len(_expected_match()["roles"])                        # every role card is still there
    headers = [h.value for h in at.header]
    assert ("SDG sector links" in headers) is not gone_sdg
    assert "Malaysia data" in headers
    all_lines = [t for lines in texts.values() for t in lines]
    page = _joined(at) + "\n" + _captions(at)
    if gone_sdg:
        assert not [s for s in at.selectbox if s.key == GOAL_KEY]
        assert not [r for r in at.radio if r.key == ORDER_KEY]
        assert not any(t.startswith("For your goal") for t in all_lines)
        assert "Evidence > Method > SDG sector links" not in page
    else:
        assert at.selectbox(key=GOAL_KEY).value == NO_GOAL
    if gone_mycol:
        assert not any(MYCOL_MARK in t for t in all_lines)
        assert MYCOL_CAPTION not in page
        assert ("MyCOL is a shortage list" not in page) is ("mycol.json" in files)   # the source note needs mycol.json
    else:
        assert any(MYCOL_MARK in t for t in all_lines) and MYCOL_CAPTION in page
    if pd.read_csv(DATA / "my_jobs_snapshots.csv").empty or "my_jobs_snapshots.csv" in files:
        assert NO_SNAPSHOT in page
    at.session_state["target_role"] = "Backend Engineer"                         # step 4 still has SDG 4.4 and 8.5
    at.run()
    assert not at.exception
    markdown = [m.value for m in at.markdown]
    start = markdown.index("### SDG links")
    assert markdown[start + 1].startswith("SDG 4.4") and markdown[start + 2].startswith("SDG 8.5")


@needs_real_data
@needs_integration_files
def test_a_missing_sectors_file_falls_back_to_the_sectors_in_role_sdg_json(tmp_path):
    at = _app_copy(tmp_path, drop=("sdg_sectors.json",))
    assert not at.exception
    options = at.selectbox(key=GOAL_KEY).options
    assert options[0] == NO_GOAL and len(options) == 1 + len(_data_json("role_sdg.json")["sectors"])


@needs_real_data
@needs_integration_files
def test_a_role_sdg_file_the_engine_cannot_use_gives_a_note_and_no_crash(tmp_path):
    doc = _data_json("role_sdg.json")
    doc["roles"] = {rid: {"name": r["name"]} for rid, r in doc["roles"].items()}      # no "sectors" in any role
    at = _app_copy(tmp_path, write={"role_sdg.json": json.dumps(doc)})
    assert not at.exception
    at.selectbox(key=GOAL_KEY).set_value(at.selectbox(key=GOAL_KEY).options[1]).run()
    assert not at.exception
    assert any(c.value.startswith("The goal view is not available") for c in at.caption)
    assert len(_card_names(at)) == len(_expected_match()["roles"])                 # no role is hidden
    at.session_state["target_role"] = "Backend Engineer"
    at.run()
    assert not at.exception                                                        # step 4 falls back to the plan lines
