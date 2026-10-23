import json
from datetime import timedelta
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from trendsignal.llm import LlmGate, usage_cost
from trendsignal.pipeline.enrich import EnrichItem, build_source_document, enrich_story
from trendsignal.pipeline.heuristics import classify, heuristic_enrichment, magnitude, parse_version
from trendsignal.pipeline.validate import EnrichmentInvalid, validate_enrichment
from trendsignal.timeutil import now_utc
from tests.conftest import fake_message

DEV_TERMS = ("python", "pytorch", "api")
ITEM = EnrichItem(source_name="OpenAI News", tier="A", title="Introducing GPT-6 for developers",
                  text="GPT-6 is now available in the API. It is faster and cheaper than GPT-5.",
                  url="https://openai.com/index/gpt-6", published_at=now_utc() - timedelta(hours=1))


def good_payload(**overrides):
    payload = {
        "category": "model_release", "entities": [{"name": "GPT-6", "type": "model"}],
        "change_magnitude": 5, "magnitude_reason": "new frontier model", "audience": ["backend", "student"],
        "is_breaking_change": False, "tldr": "OpenAI released GPT-6 in the API.",
        "why_it_matters": "Check whether it is cheaper for your app.",
        "evidence_quotes": ["GPT-6 is now available in the API"],
    }
    return {**payload, **overrides}


class FakeMessages:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fake_client(*outcomes):
    return SimpleNamespace(messages=FakeMessages(outcomes))


def api_error(cls, status):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("error", response=httpx.Response(status, request=request), body=None)


# ---------------------------------------------------------------- heuristics

@pytest.mark.parametrize("title, expected", [
    ("Next.js 16.0.0", (4, "major")), ("PyTorch 2.6.0", (3, "minor")), ("vLLM v0.9.2", (2, "patch")),
    ("Transformers v5.0.0rc1", (1, "pre-release")),
])
def test_release_magnitude_follows_semver(title, expected):
    level, reason = magnitude("dev_tool_release", title, "A", 0)
    assert level == expected[0] and expected[1] in reason


def test_nightly_builds_are_noise():
    assert magnitude("dev_tool_release", "PyTorch trunk/1404563568be4b2d23634a409bd7a9c", "A", 0)[0] == 1


def test_parse_version_handles_missing_version():
    assert parse_version("No version here") is None
    assert parse_version("v1.2") == (1, 2, 0, False)


@pytest.mark.parametrize("title, text, tier, release_feed, expected", [
    ("Compromised LiteLLM on PyPI installs a backdoor", "", "C", False, "security_incident"),
    ("Blog post", "A critical vulnerability (CVE-2026-1234) was found.", "A", False, "security_incident"),
    ("LangChain 1.2.0", "", "A", True, "dev_tool_release"),
    ("GitHub Copilot models deprecated on October 19", "", "A", False, "api_pricing_change"),
    ("Introducing Gemini 4, our most capable model", "", "A", False, "model_release"),
    ("Learning the 4D World", "We introduce a model that...", "B", False, "research"),
    ("Ask HN: what are you working on?", "", "C", False, "opinion"),
    ("How to build agents on Amazon Bedrock", "", "A", False, "product_feature"),
])
def test_classify(title, text, tier, release_feed, expected):
    assert classify(title, text, tier, release_feed) == expected


def test_tutorials_rank_below_announcements():
    assert magnitude("product_feature", "How to fine-tune a model on AWS", "A", 0)[0] == 2
    assert magnitude("product_feature", "Copilot now reviews pull requests", "A", 0)[0] == 3


def test_heuristic_enrichment_never_invents_numbers():
    long_sentence = "Adds support for " + "new and faster models, " * 40 + "and more."
    enrichment = heuristic_enrichment("Ollama v0.12.0", long_sentence, "A", True, 0, DEV_TERMS)
    assert enrichment.enriched_by == "heuristic"
    assert enrichment.tldr.endswith("…") and len(enrichment.tldr) <= 281
    assert enrichment.evidence_quotes == ("Ollama v0.12.0",)


# ---------------------------------------------------------------- validation

def test_valid_payload_passes():
    enrichment = validate_enrichment(json.dumps(good_payload()), build_source_document([ITEM]), "claude-haiku-5-5")
    assert enrichment.change_magnitude == 5 and enrichment.enriched_by == "claude-haiku-5-5"


def test_quote_that_is_not_in_the_source_is_rejected():
    with pytest.raises(EnrichmentInvalid, match="not found"):
        validate_enrichment(good_payload(evidence_quotes=["GPT-6 cures every bug"]), ITEM.text, "m")


@pytest.mark.parametrize("override", [{"change_magnitude": 9}, {"category": "gossip"}, {"evidence_quotes": []}])
def test_schema_violations_are_rejected(override):
    with pytest.raises(EnrichmentInvalid):
        validate_enrichment(good_payload(**override), ITEM.text, "m")


def test_invalid_json_is_rejected():
    with pytest.raises(EnrichmentInvalid):
        validate_enrichment("{not json", ITEM.text, "m")


# ---------------------------------------------------------------- LLM path with a fake client

def test_enrich_story_uses_claude_output_when_it_validates(llm_settings):
    gate = LlmGate(llm_settings, spent_today=0.0)
    client = fake_client(fake_message(json.dumps(good_payload())))
    outcome = enrich_story([ITEM], client, "claude-haiku-5-5", gate, DEV_TERMS)
    assert outcome.fallback_reason is None and outcome.enrichment.category == "model_release"
    assert outcome.cost_usd == pytest.approx(usage_cost("claude-haiku-5-5", fake_message("").usage))
    call = client.messages.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "<source_document>" in call["messages"][0]["content"]


def test_enrich_story_retries_once_then_falls_back_to_heuristics(llm_settings):
    gate = LlmGate(llm_settings, spent_today=0.0)
    bad = json.dumps(good_payload(evidence_quotes=["made-up quote not in source"]))
    client = fake_client(fake_message(bad), fake_message(bad))
    outcome = enrich_story([ITEM], client, "claude-haiku-5-5", gate, DEV_TERMS)
    assert outcome.enrichment.enriched_by == "heuristic"
    assert "rejected" in outcome.fallback_reason
    assert len(client.messages.calls) == 2


def test_auth_error_closes_the_gate_for_the_rest_of_the_run(llm_settings):
    gate = LlmGate(llm_settings, spent_today=0.0)
    client = fake_client(api_error(anthropic.AuthenticationError, 401))
    outcome = enrich_story([ITEM], client, "claude-haiku-5-5", gate, DEV_TERMS)
    assert outcome.enrichment.enriched_by == "heuristic"
    assert not gate.open and "rejected" in gate.reason


def test_refusal_falls_back_without_closing_the_gate(llm_settings):
    gate = LlmGate(llm_settings, spent_today=0.0)
    client = fake_client(fake_message("", stop_reason="refusal"), fake_message("", stop_reason="refusal"))
    outcome = enrich_story([ITEM], client, "claude-haiku-5-5", gate, DEV_TERMS)
    assert outcome.enrichment.enriched_by == "heuristic" and gate.open


def test_budget_gate_closes_when_spend_reaches_the_cap(llm_settings):
    gate = LlmGate(llm_settings, spent_today=llm_settings.llm_daily_budget_usd - 0.001)
    assert gate.open
    gate.record(0.01)
    assert not gate.open and "budget" in gate.reason


def test_gate_is_closed_without_credentials(settings):
    gate = LlmGate(settings, spent_today=0.0)
    assert not gate.open and "credentials" in gate.reason
