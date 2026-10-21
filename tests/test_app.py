"""Smoke tests for the Streamlit front end (app.py), run with Streamlit's AppTest."""

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
# A relative path would be resolved against this test file, so use an absolute path.
APP_PATH = str(ROOT / "app.py")
TIMEOUT = 30
FIXTURE_BANNER = "Prototype: showing sample data, not real forecasts."


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


def test_app_runs_on_fixture_without_exception(fixture_app):
    at = _run_app(fixture_app)
    assert not at.exception


def test_fast_scenario_reruns_without_exception():
    at = _run_app()
    at.sidebar.radio[0].set_value("Fast disruption").run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "Fast disruption"


def test_fixture_banner_is_shown(fixture_app):
    at = _run_app(fixture_app)
    banners = [w.value for w in at.warning]
    assert FIXTURE_BANNER in banners


def test_app_runs_on_real_engine_output_without_banner():
    if not (ROOT / "data" / "skill_scores.json").exists():
        pytest.skip("data/skill_scores.json not generated yet")
    at = _run_app()
    assert not at.exception
    assert FIXTURE_BANNER not in [w.value for w in at.warning]
