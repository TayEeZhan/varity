from datetime import timedelta
from types import SimpleNamespace

from trendsignal.agents.editor import build_tools, write_brief
from trendsignal.agents.template import render_brief, story_facts
from trendsignal.agents.verifier import StoryFacts, check_line, verify_brief
from trendsignal.queries import SourceLink, StoryView
from trendsignal.timeutil import now_utc
from tests.conftest import fake_message


def view(story_id=12, tier="must_know", title="Gemini 4 launches with 2M context", tldr="Google released Gemini 4."):
    return StoryView(
        id=story_id, title=title, tier=tier, importance=81.4, rank_score=70.0, category="model_release",
        status="confirmed", tldr=tldr, why_it_matters="Try it for long documents.", audience=("student",),
        entities=("gemini",), time_to_understand_min=8, is_breaking_change=False,
        first_seen_at=now_utc() - timedelta(hours=3), reasons=("official source (Google)", "3 independent reports"),
        features={"impact": 1.0}, url="https://blog.google/gemini-4",
        sources=(SourceLink("Google", "A", "https://blog.google/gemini-4"),), enriched_by="heuristic",
    )


FACTS = {12: story_facts(view())}


def test_template_brief_passes_verification_completely():
    groups = {"must_know": [view()], "worth_a_look": [view(13, "worth_a_look", "Small update", "A fix.")],
              "emerging": [], "minor": [view(14, "minor")]}
    facts = {v.id: story_facts(v) for vs in groups.values() for v in vs}
    result = verify_brief(render_brief("Brief", "daily", groups), facts, title="Brief", required_ids=[12])
    assert result.failed_lines == 0 and result.passed()


def test_valid_line_passes():
    assert check_line("Gemini 4 has a 2M context and takes 8 min to read [S12]", FACTS) is None


def test_line_without_citation_fails():
    assert check_line("Gemini 4 is out", FACTS) == "no citation"


def test_line_citing_a_story_outside_the_brief_fails():
    assert "outside" in check_line("Something [S99]", FACTS)


def test_invented_number_fails():
    assert "number" in check_line("Gemini 4 has a 10M context [S12]", FACTS)


def test_foreign_or_script_links_fail():
    assert "link" in check_line("[Read](https://evil.example/x) [S12]", FACTS)
    assert "link" in check_line("[Read](javascript:alert(1)) [S12]", FACTS)
    assert check_line("[Read](https://blog.google/gemini-4) [S12]", FACTS) is None


def test_raw_html_fails():
    assert "HTML" in check_line("<img src=x onerror=alert(1)> [S12]", FACTS)


def test_failed_lines_are_stripped_and_ratio_decides_pass():
    draft = "# Title\n\nGood line [S12]\nInvented 99 users [S12]\nNo citation here\n"
    result = verify_brief(draft, FACTS, title="Title")
    assert "Invented" not in result.body and "Good line" in result.body
    assert result.checked_lines == 4 and result.failed_lines == 2 and not result.passed()


def test_empty_draft_does_not_pass():
    assert not verify_brief("# Only a heading\n", FACTS).passed()


def test_story_facts_include_minutes_and_scores():
    facts = StoryFacts(1, frozenset(), "8 min 81.4")
    assert facts.numbers == frozenset({"8", "81.4"})


# ---------------------------------------------------------------- editor agent with a fake tool runner

def fake_runner_client(messages):
    calls = []

    def tool_runner(**kwargs):
        calls.append(kwargs)
        return iter(messages)

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(tool_runner=tool_runner))), calls


def test_editor_tools_only_expose_stories_in_the_brief():
    tools = build_tools({"must_know": [view()]}, lambda story_id: [{"id": story_id}], lambda: [])
    get_top, get_story, _ = tools
    assert '"citation": "[S12]"' in get_top.call({})
    assert "not part of this brief" in get_story.call({"story_id": 99})
    assert '"id": 12' in get_story.call({"story_id": 12})


def test_write_brief_returns_text_and_cost():
    client, calls = fake_runner_client([fake_message("", stop_reason="tool_use"), fake_message("# Brief\nLine [S12]")])
    result = write_brief(client, "claude-sonnet-5-5", "Brief", "daily", tools=[])
    assert result.markdown == "# Brief\nLine [S12]" and result.error is None and result.cost_usd > 0
    assert calls[0]["fallbacks"] == "default" and calls[0]["max_iterations"] == 6


def test_write_brief_reports_refusals():
    client, _ = fake_runner_client([fake_message("", stop_reason="refusal")])
    result = write_brief(client, "claude-sonnet-5-5", "Brief", "daily", tools=[])
    assert result.markdown is None and "declined" in result.error
