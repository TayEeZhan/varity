"""Smoke tests for the Streamlit front end (app.py), run with Streamlit's AppTest."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

# A relative path would be resolved against this test file, so use an absolute path.
APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
TIMEOUT = 30
FIXTURE_BANNER = "Prototype: showing sample data, not real forecasts."


def _run_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()


def test_app_runs_on_fixture_without_exception():
    at = _run_app()
    assert not at.exception


def test_fast_scenario_reruns_without_exception():
    at = _run_app()
    at.sidebar.radio[0].set_value("Fast disruption").run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "Fast disruption"


def test_fixture_banner_is_shown():
    at = _run_app()
    banners = [w.value for w in at.warning]
    assert FIXTURE_BANNER in banners
