"""Evidence area: radar payload, held-skill marking, evidence payload fields, missing files."""

import json
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.web.app import create_app
from trendsignal.web.evidence_api import DATA_DIR, add_evidence_routes


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


@pytest.fixture
def token(client):
    review = client.post("/api/cv/extract", json={"sample": "aina"}).json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    return client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept}).json()["data"]["token"]


def copy_data(tmp_path, *, skip=()):
    for f in DATA_DIR.iterdir():
        if f.is_file() and f.name not in skip:
            shutil.copy(f, tmp_path / f.name)
    return tmp_path


def bare_client(settings, data_dir):
    app = FastAPI()
    add_evidence_routes(app, settings, data_dir)
    return TestClient(app)


def test_radar_payload_shape(client):
    data = client.get("/api/skills/radar").json()["data"]
    scores = json.loads((DATA_DIR / "skill_scores.json").read_text(encoding="utf-8"))
    assert data["asOf"] == scores["as_of"] and data["points"] and data["held"] == []
    p = data["points"][0]
    assert {"skill", "share", "change", "trend_label", "stance", "contested", "mine", "mark", "group", "forecast"} <= set(p)
    assert set(p["forecast"]) == {"moderate", "fast"} and {"value_12m", "low", "high"} <= set(p["forecast"]["moderate"])
    assert len(data["sentences"]) == 3 and data["band"]["label"] and data["contestedKnown"]
    assert not any(q["mine"] for q in data["points"])
    for q in data["points"]:  # only a tested Rising or Falling label gets a colour
        assert (q["mark"] == "grey") == (q["trend_label"] not in ("Rising", "Falling"))


def test_radar_marks_held_skills_from_the_profile(client, token):
    data = client.get("/api/skills/radar", headers={"X-Profile-Token": token}).json()["data"]
    assert data["held"]
    marked = {p["skill"] for p in data["points"] if p["mine"]}
    assert marked and marked <= set(data["held"])
    bad = client.get("/api/skills/radar", headers={"X-Profile-Token": "nope"}).json()["data"]
    assert bad["held"] == []


def test_evidence_payload_fields(client):
    body = client.get("/api/evidence").json()
    assert body["success"]
    data = body["data"]
    bt = json.loads((DATA_DIR / "backtest.json").read_text(encoding="utf-8"))
    skills = data["backtests"]["skills"]
    assert skills["chosenModel"] == bt["chosen_model"]
    assert skills["coverage"]["test_h12"] == bt["coverage"]["test_h12"]
    assert skills["trendLabel"]["n"] == bt["trend_label_backtest"]["n"]
    assert {m["model"] for m in skills["models"]} == set(bt["models"])
    assert data["backtests"]["roles"]["kind"] == "role"
    assert data["exposure"]["occupations"] and data["exposure"]["crossCheck"]
    assert data["exposure"]["contestedCategories"] is not None
    assert data["k"]["label"] == "assumption" and data["k"]["assumedK"] is not None
    assert data["sources"] and data["sourcesChecked"] and data["missing"] == []


def test_missing_required_file_is_a_clear_error(settings, tmp_path):
    c = bare_client(settings, copy_data(tmp_path, skip=("skill_scores.json",)))
    r = c.get("/api/skills/radar")
    assert r.status_code == 500
    assert r.json()["meta"]["code"] == "EVIDENCE_DATA_MISSING" and "skill_scores.json" in r.json()["error"]
    other = tmp_path / "b"
    other.mkdir()
    c = bare_client(settings, copy_data(other, skip=("backtest.json",)))
    assert c.get("/api/evidence").json()["meta"]["file"] == "backtest.json"


def test_missing_optional_files_hide_only_their_section(settings, tmp_path):
    skip = ("role_backtest.json", "k_estimate.json", "exposure_agreement.json", "exposure_robustness.csv", "SOURCES.md")
    c = bare_client(settings, copy_data(tmp_path, skip=skip))
    data = c.get("/api/evidence").json()["data"]
    assert data["backtests"]["roles"] is None and data["k"] is None and data["sources"] == []
    assert set(data["missing"]) == {"role_backtest.json", "k_estimate.json", "exposure_agreement.json", "SOURCES.md"}
    radar = c.get("/api/skills/radar").json()["data"]
    assert radar["points"] and radar["contestedKnown"] is False
