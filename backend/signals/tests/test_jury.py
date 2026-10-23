import json

import httpx
import pytest

from eval.jury import (Juror, JuryError, compare_with_humans, jury_gold, majority, parse_vote, run_jury)

STORIES = [{"url": f"https://e.x/{i}", "title": f"Story {i}", "sources": "S"} for i in range(1, 4)]


def client_answering(labels_by_model, status=200):
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if status != 200:
            return httpx.Response(status, text="nope")
        label = labels_by_model[body["model"]]
        content = json.dumps({"label": label, "reason": "because"})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10}})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


@pytest.mark.parametrize("content, expected", [
    ('{"label": "must_know", "reason": "big"}', "must_know"),
    ('Sure! ```json\n{"label": "Minor", "reason": "patch"}\n```', "minor"),
    ("I would say worth_a_look.", "worth_a_look"),
])
def test_parse_vote(content, expected):
    assert parse_vote(content)[0] == expected


def test_parse_vote_rejects_replies_without_a_label():
    with pytest.raises(JuryError):
        parse_vote("No idea.")


def test_majority_needs_more_than_half():
    assert majority(["must_know", "must_know", "minor"]) == "must_know"
    assert majority(["must_know", "minor", "worth_a_look"]) == ""
    assert majority(["minor", "", ""]) == "minor"


def test_jury_marks_each_story_with_each_model_and_takes_the_majority():
    http, calls = client_answering({"a/x": "must_know", "b/y": "must_know", "c/z": "minor"})
    jurors = [Juror(http, "https://or.example/api", "k", m) for m in ("a/x", "b/y", "c/z")]
    votes = run_jury(STORIES, jurors)
    assert len(votes) == 9 and len(calls) == 9
    assert calls[0]["temperature"] == 0 and "<story>" in calls[0]["messages"][1]["content"]
    gold, report = jury_gold(votes)
    assert {g["gold_tier"] for g in gold} == {"must_know"} and report["labelled"] == 3 and report["unanimous"] == 0
    assert "x=must_know" in gold[0]["note"]


def test_an_unavailable_model_is_skipped_after_three_failures(capsys):
    from eval.jury import model_summary

    http, calls = client_answering({}, status=404)
    stories = STORIES + [{"url": f"https://e.x/{i}", "title": f"S{i}", "sources": "S"} for i in range(4, 9)]
    votes = run_jury(stories, [Juror(http, "https://or.example/api", "k", "missing/model")])
    assert len(calls) == 3 and len(votes) == 8 and all(v.vote == "" and "404" in v.reason for v in votes)
    assert "skipping missing/model" in capsys.readouterr().out
    assert "0/8 votes; first error: error: HTTP 404" in model_summary(votes)[0]


def test_models_fall_back_to_openrouters_public_list():
    from eval.jury import list_models

    def handler(request):
        if "localhost" in str(request.url):
            return httpx.Response(405)
        return httpx.Response(200, json={"data": [{"id": "anthropic/claude-x"}, {"id": "meta/llama"},
                                                  {"id": "google/gemini-y"}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    models, source = list_models(http, "http://localhost:1106/modelfarm/openrouter", "k")
    assert models == ["anthropic/claude-x", "google/gemini-y"] and "public" in source


def test_rate_limits_are_retried():
    replies = iter([httpx.Response(429), httpx.Response(200, json={
        "choices": [{"message": {"content": '{"label": "minor", "reason": "r"}'}}]})])
    http = httpx.Client(transport=httpx.MockTransport(lambda request: next(replies)))
    waits = []
    assert Juror(http, "https://or.example/api", "k", "m", sleep=waits.append).mark("t", "s")[0] == "minor"
    assert waits == [2.0]


def test_call_cap_is_enforced():
    with pytest.raises(SystemExit, match="cap"):
        run_jury(STORIES, [Juror(httpx.Client(), "u", "k", "m")], max_calls=2)


def test_jury_is_compared_with_human_labels():
    jury = [{"url": "u1", "gold_tier": "must_know"}, {"url": "u2", "gold_tier": "minor"},
            {"url": "u3", "gold_tier": "minor"}, {"url": "u4", "gold_tier": "minor"}]
    sheet = [{"url": "u1", "label_A": "must_know", "label_B": "must_know", "final": ""},
             {"url": "u2", "label_A": "minor", "label_B": "worth_a_look", "final": "minor"},
             {"url": "u3", "label_A": "minor", "label_B": "minor", "final": ""},
             {"url": "u4", "label_A": "", "label_B": "", "final": ""}]
    result = compare_with_humans(jury, sheet)
    assert result["compared"] == 3 and result["agreement"] == 1.0 and result["trusted"]


def test_jev_cannot_sit_on_the_jury(monkeypatch):
    from eval import jury

    monkeypatch.setenv("AI_INTEGRATIONS_OPENROUTER_BASE_URL", "https://or.example/api")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENROUTER_API_KEY", "k")
    with pytest.raises(SystemExit, match="Jev"):
        jury.main(["run", "--models", "anthropic/claude", "jev-latest"])
