"""Recommendations depend on skills only: name, age, gender, nationality and school must not move the ranking."""

import json

import pytest
from fastapi.testclient import TestClient

from trendsignal.jobs import load_context
from trendsignal.web.app import create_app

SKILLS = "Skills: Python, SQL, PostgreSQL, Docker, AWS"

# Same skills line in every CV. Only the personal details change.
PROFILES = [
    {"name": "Aina Rahman", "age": "27", "pronoun": "She", "title": "Ms", "nationality": "Malaysian",
     "school": "University of Malaya"},
    {"name": "Ben Carter", "age": "52", "pronoun": "He", "title": "Mr", "nationality": "Nigerian",
     "school": "Massachusetts Institute of Technology"},
    {"name": "Chloe Tan", "age": "63", "pronoun": "They", "title": "Mx", "nationality": "French",
     "school": "Sorbonne University"},
]


def cv_text(person: dict) -> str:
    return (
        f"{person['name']}\n"
        f"Age: {person['age']}\n"
        f"{person['title']}. {person['name'].split()[0]} is a {person['nationality']} engineer. "
        f"{person['pronoun']} studied at {person['school']}. {person['pronoun']} built data pipelines.\n"
        f"{SKILLS}\n"
    )


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


def extract(client, token=None, **body):
    headers = {"X-Profile-Token": token} if token else {}
    return client.post("/api/cv/extract", json=body, headers=headers)


def run_one(client, person: dict) -> dict:
    review = extract(client, text=cv_text(person), use_ai=False).json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    saved = client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept,
                                                     "target_role": "data_engineer"}).json()["data"]
    token = saved["token"]
    suggestions = client.get("/api/roles/suggestions", headers={"X-Profile-Token": token}).json()["data"]
    return {"skills": sorted(row["skill_id"] for row in review["rows"]), "kept": sorted(kept),
            "token": token, "profile": saved["profile"], "suggestions": suggestions}


@pytest.fixture
def runs(client):
    return [run_one(client, person) for person in PROFILES]


def test_ranked_roles_and_match_pct_are_identical_across_names_ages_and_genders(runs):
    assert all(run["suggestions"]["roles"] for run in runs)
    assert all(run["suggestions"]["llmStatus"] == "off:SWITCHED_OFF" for run in runs)  # advisor is off
    ranked = [[role["roleId"] for role in run["suggestions"]["roles"]] for run in runs]
    match = [[role["matchPct"] for role in run["suggestions"]["roles"]] for run in runs]
    assert ranked[0] == ranked[1] == ranked[2]
    assert match[0] == match[1] == match[2]


def test_extracted_skill_list_is_identical_across_personal_details(runs):
    assert runs[0]["skills"] == runs[1]["skills"] == runs[2]["skills"]
    assert runs[0]["kept"] == runs[1]["kept"] == runs[2]["kept"]
    assert {"python", "sql", "postgresql", "docker", "aws"} <= set(runs[0]["kept"])


def test_stored_profile_holds_no_name_or_age(client, runs):
    for person, run in zip(PROFILES, runs):
        blob = json.dumps(run["profile"])
        blob += json.dumps(run["suggestions"])
        assert person["name"] not in blob
        assert person["name"].split()[0] not in blob
        assert person["name"].split()[-1] not in blob
        assert f'"{person["age"]}"' not in blob and f": {person['age']}" not in blob
        stored = client.get("/api/profile", headers={"X-Profile-Token": run["token"]}).json()
        assert stored["success"] and person["name"] not in json.dumps(stored)
