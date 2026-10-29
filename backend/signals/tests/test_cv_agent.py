"""The CV agent (advisor/cv_agent.py) with a scripted fake model: read tools run here, ask / plan / edit stop the
loop, a rejected edit goes back to the model, Just do it never asks, and the route wires it to the saved draft.
tests/cv_agent_cases.json is run against a real model only when VARITY_AGENT_EVAL=1 (it costs money)."""
import json
import os
from functools import partial
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from advisor import cv_agent
from advisor.cv_agent import Context
from intake.llm_extract import SpendGate
from trendsignal.jobs import load_context
from trendsignal.web.app import create_app

CV = "Aina Rahman\nData Analyst, Petronas 2021 - 2024\n- Helped the finance team clean monthly data"
HELP = "Helped the finance team clean monthly data"
DRAFT = {"name": "Aina Rahman", "contact": "[email]", "summary": "Analyst.", "projects": [], "education": [],
         "skills": ["SQL"], "jobs": [{"title": "Data Analyst", "employer": "Petronas", "dates": "2021 - 2024",
                                      "bullets": [{"source": HELP, "text": HELP}]}]}
CASES = Path(__file__).with_name("cv_agent_cases.json")


def use(name, args=None, i=0):
    return SimpleNamespace(type="tool_use", name=name, input=args or {}, id=f"t{i}")


def say(text):
    return SimpleNamespace(type="text", text=text)


class FakeClient:
    """Plays back one list of content blocks per call and records what the agent sent."""

    def __init__(self, *turns):
        self.turns, self.sent = list(turns), []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.sent.append(kw["messages"][:])
        return SimpleNamespace(content=self.turns.pop(0))


def ctx(**kw):
    return Context(**{"role": "Data Engineer", "role_row": {"have": [{"skill": "SQL"}], "gap": [{"skill": "AWS"}]},
                      "skills": ["SQL"], "learned": set(), "cv_text": CV, "draft": json.loads(json.dumps(DRAFT)), **kw})


run = partial(cv_agent.run, gate=SpendGate(100.0))


def test_reads_then_asks_the_user():
    client = FakeClient([use("read_current_cv")],
                        [say("Which part?"), use("ask_user", {"questions": [{"question": "Which part?", "options": ["Summary", "Bullets"]}]}, 1)])
    out = run(ctx(), [], "make it better", client=client)
    assert out == {"type": "ask", "text": "Which part?", "questions": [{"question": "Which part?", "options": ["Summary", "Bullets"]}]}
    assert json.loads(client.sent[1][-1]["content"][0]["content"])["draft"]["summary"] == "Analyst."


def test_a_rejected_edit_goes_back_to_the_model():
    invented = {"section": "jobs[0].bullets", "value": [{"source": HELP, "text": "Helped clean data for 40 accounts"}], "reason": "x"}
    client = FakeClient([use("edit_section", invented)],
                        [use("ask_user", {"questions": [{"question": "How many accounts?", "options": []}]}, 1)])
    out = run(ctx(), [], "add numbers", client=client)
    assert out["type"] == "ask"
    result = client.sent[1][-1]["content"][0]["content"]
    assert "rejected" in result and "ask_user" in result


def test_an_edit_backed_by_the_users_answer_is_marked_added_by_you():
    edit = {"section": "jobs[0].bullets", "value": [{"source": HELP, "text": "Helped clean monthly data for 40 accounts"}],
            "reason": "you told me"}
    out = run(ctx(facts=["it was 40 accounts"]), [], "40", client=FakeClient([use("edit_section", edit)]))
    assert out["type"] == "edit" and out["addedByYou"] is True
    assert out["before"][0]["text"] == HELP and out["after"][0]["text"].endswith("40 accounts")


def test_a_stronger_verb_is_rejected():
    edit = {"section": "jobs[0].bullets", "value": [{"source": HELP, "text": "Led the finance team's data cleaning"}], "reason": "x"}
    client = FakeClient([use("edit_section", edit)], [say("I kept your wording.")])
    out = run(ctx(), [], "make it stronger", client=client)
    assert out == {"type": "say", "text": "I kept your wording."}
    assert "stronger verb" in client.sent[1][-1]["content"][0]["content"]


def test_just_do_it_never_asks_or_plans():
    client = FakeClient([use("ask_user", {"questions": [{"question": "?", "options": []}]})],
                        [use("propose_plan", {"steps": ["a"]}, 1)],
                        [use("edit_section", {"section": "summary", "value": "Data analyst moving into data engineering.", "reason": "r"}, 2)])
    out = run(ctx(), [], "go", just_do_it=True, client=client)
    assert out["type"] == "edit" and out["after"] == "Data analyst moving into data engineering."
    assert "Just do it" in client.sent[0][0]["content"]


def test_plan_and_notes():
    saved = []
    client = FakeClient([use("save_note", {"note": "British spelling"})], [use("propose_plan", {"steps": ["Summary", "Skills"]}, 1)])
    out = run(ctx(save_note=saved.append), [], "tailor everything, and always British spelling", client=client)
    assert out["type"] == "plan" and out["steps"] == ["Summary", "Skills"] and saved == [["British spelling"]]


def test_bad_sections_and_the_step_limit():
    assert cv_agent.edit_section(ctx(), "education", [])[1].startswith("section must be")
    assert cv_agent.edit_section(ctx(), "jobs[3].bullets", [])[1] == "there is no jobs[3].bullets"
    client = FakeClient(*[[use("read_original_cv", i=i)] for i in range(cv_agent.MAX_STEPS)])
    assert run(ctx(), [], "loop", client=client)["type"] == "say"


def test_history_is_merged_so_roles_alternate():
    msgs = cv_agent._messages([{"role": "assistant", "text": "hi"}, {"role": "user", "text": "a"},
                               {"role": "user", "text": "b"}], "c", "summary", False)
    assert [m["role"] for m in msgs] == ["user"] and "a\n\nb\n\nc" in msgs[0]["content"] and "summary" in msgs[0]["content"]


def test_route_uses_the_saved_draft(settings, monkeypatch):
    from tests.test_cv_writer import _aina_answer, _token
    client = TestClient(create_app(load_context(settings)))
    headers = {"X-Profile-Token": _token(client)}
    assert client.post("/api/cv/agent", json={"message": "hi"}, headers=headers).json()["meta"]["code"] == "NO_DRAFT"
    role = client.get("/api/roles/suggestions", headers=headers).json()["data"]["roles"][0]["roleId"]
    monkeypatch.setattr("trendsignal.web.roles_api.call_model", _aina_answer)
    client.post("/api/cv/generate", json={"roleId": role}, headers=headers)
    assert client.post("/api/cv/agent", json={"message": "hi"}, headers=headers).json()["data"] == {"type": "off", "code": "NO_KEY"}
    fake = FakeClient([use("read_target_role")], [say("Your CV is for this role.")])
    monkeypatch.setattr(cv_agent, "run", partial(cv_agent.run, client=fake, gate=SpendGate(100.0)))
    out = client.post("/api/cv/agent", json={"message": "which role?", "selection": "summary"}, headers=headers).json()["data"]
    assert out["type"] == "say" and json.loads(fake.sent[1][-1]["content"][0]["content"])["role"]


def test_cases_file_is_well_formed():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    assert 10 <= len(cases) <= 15 and {c["expect"] for c in cases} <= {"ask", "plan", "edit", "say"}


@pytest.mark.skipif(os.environ.get("VARITY_AGENT_EVAL") != "1", reason="real-model eval: set VARITY_AGENT_EVAL=1")
def test_real_model_asks_and_edits_at_the_right_moments():
    misses = []
    for case in json.loads(CASES.read_text(encoding="utf-8")):
        out = cv_agent.run(ctx(job_ad=case.get("job_ad", ""), selection=case.get("selection", "")), [], case["message"])
        if out["type"] != case["expect"]:
            misses.append((case["message"], case["expect"], out["type"]))
    assert len(misses) <= 2, misses
