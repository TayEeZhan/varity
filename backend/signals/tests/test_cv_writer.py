"""Generate CV (advisor/cv_writer.py): the checker drops invented claims; no model or no saved CV still gives a CV."""
from fastapi.testclient import TestClient
import pytest

from advisor import cv_writer
from advisor.cv_writer import CvDraft, Education, Job
from intake.llm_extract import LlmUnavailable
from trendsignal.jobs import load_context
from trendsignal.web import accounts_store
from trendsignal.web.accounts_store import token_owner
from trendsignal.web.app import create_app

CV = """Aina Rahman
[email] | [phone]
Data Analyst, Petronas  2021 - 2024
- Built dashboards in Power BI for 12 teams
BSc Computer Science, Universiti Malaya 2017 - 2021"""


def draft(**kw):
    base = dict(name="Aina Rahman", contact="[email] | [phone]", summary="Analyst moving into data engineering.",
                jobs=[Job(title="Data Analyst", employer="Petronas", dates="2021 - 2024",
                          bullets=["Built Power BI dashboards for 12 teams"])],
                education=[Education(qualification="BSc Computer Science", school="Universiti Malaya", dates="2017 - 2021")],
                skills=["SQL", "Python"])
    return CvDraft(**{**base, **kw})


def test_checker_keeps_what_the_cv_backs():
    cleaned, dropped = cv_writer.check(draft(), CV, ["SQL", "Python", "Docker"])
    assert dropped == [] and cleaned.jobs[0].employer == "Petronas" and cleaned.education
    assert cleaned.skills == ["SQL", "Python", "Docker"]  # a held skill the model left out is put back


def test_checker_drops_invented_claims():
    fake = draft(jobs=[Job(title="Lead Engineer", employer="Google", dates="2024", bullets=[]),
                       Job(title="Data Analyst", employer="Petronas", dates="2021 - 2024",
                           bullets=["Saved RM 5 million", "Built dashboards"])],
                 education=[Education(qualification="PhD AI", school="MIT", dates="2020")],
                 summary="Has 10 years of experience.", skills=["SQL", "Kubernetes"])
    cleaned, dropped = cv_writer.check(fake, CV, ["SQL"])
    assert [j.employer for j in cleaned.jobs] == ["Petronas"]
    assert cleaned.jobs[0].bullets == ["Built dashboards"]
    assert cleaned.education == [] and cleaned.summary == "" and cleaned.skills == ["SQL"]
    assert any("Google" in d for d in dropped) and any("Kubernetes" in d for d in dropped)


@pytest.fixture
def client(settings):
    return TestClient(create_app(load_context(settings)))


def _token(client):
    review = client.post("/api/cv/extract", json={"sample": "aina"}).json()["data"]
    kept = [row["skill_id"] for row in review["rows"] if row["default_keep"]]
    return client.post("/api/profile/apply", json={"review_id": review["review_id"], "kept_ids": kept}).json()["data"]["token"]


def test_generate_without_a_model_keeps_the_cv(settings, client, monkeypatch):
    token = _token(client)
    headers = {"X-Profile-Token": token}
    assert client.post("/api/cv/generate", headers=headers).json()["meta"]["code"] == "NO_TARGET_ROLE"
    saved = accounts_store.get_cv_text(settings, token_owner(token))
    assert saved and "aina" in saved.casefold()
    roles = client.get("/api/roles/suggestions", headers=headers).json()["data"]["roles"]
    client.post("/api/profile/target-role", json={"roleId": roles[0]["roleId"]}, headers=headers)

    def no_model(*_a, **_k):
        raise LlmUnavailable("NO_KEY")
    monkeypatch.setattr("trendsignal.web.roles_api.call_model", no_model)
    out = client.post("/api/cv/generate", headers=headers).json()["data"]
    assert out["mode"] == "off:NO_KEY" and out["markdown"].startswith(saved.strip()[:20])
    assert f"## Skills for {out['role']}" in out["markdown"]

    client.delete("/api/profile", headers=headers)
    assert accounts_store.get_cv_text(settings, token_owner(token)) is None


def test_no_saved_cv_asks_for_a_reupload():
    profile_md = cv_writer.fallback(None, "Data Engineer", ["SQL"], {"SQL"})
    assert cv_writer.NO_CV_NOTE in profile_md and "- SQL (learned through Varity)" in profile_md
