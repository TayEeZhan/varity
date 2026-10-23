"""Replit AI Integrations route for Claude: env mapping, default models, intake price and label."""

from __future__ import annotations

import importlib.util

import pytest

from intake import llm_extract
from trendsignal.config import load_settings, use_replit_anthropic

REPLIT = {"AI_INTEGRATIONS_ANTHROPIC_API_KEY": "replit-key", "AI_INTEGRATIONS_ANTHROPIC_BASE_URL": "https://replit.example/anthropic"}


@pytest.fixture
def env(settings, monkeypatch):  # `settings` already clears the Anthropic variables
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("VERITY_INTAKE_MODEL", raising=False)
    monkeypatch.delenv("TRENDSIGNAL_ENRICH_MODEL", raising=False)
    monkeypatch.delenv("TRENDSIGNAL_EDITOR_MODEL", raising=False)
    for name in REPLIT:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_replit_vars_are_mapped_and_models_default(env):
    for name, value in REPLIT.items():
        env.setenv(name, value)
    env.setenv("TRENDSIGNAL_LLM", "auto")
    loaded = load_settings()
    import os
    assert os.environ["ANTHROPIC_API_KEY"] == "replit-key"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://replit.example/anthropic"
    assert (loaded.enrich_model, loaded.editor_model) == ("claude-haiku-4-5", "claude-sonnet-5")
    assert loaded.has_llm_credentials
    assert use_replit_anthropic()  # a second load keeps the route


def test_explicit_model_env_still_wins(env):
    for name, value in REPLIT.items():
        env.setenv(name, value)
    env.setenv("TRENDSIGNAL_ENRICH_MODEL", "claude-opus-5")
    assert load_settings().enrich_model == "claude-opus-5"


def test_real_key_is_not_overwritten(env):
    import os
    for name, value in REPLIT.items():
        env.setenv(name, value)
    env.setenv("ANTHROPIC_API_KEY", "real-key")
    loaded = load_settings()
    assert os.environ["ANTHROPIC_API_KEY"] == "real-key"
    assert "ANTHROPIC_BASE_URL" not in os.environ
    assert (loaded.enrich_model, loaded.editor_model) == ("claude-haiku-5-5", "claude-sonnet-5-5")


def test_no_credentials_at_all(env):
    env.setenv("TRENDSIGNAL_LLM", "auto")
    loaded = load_settings()
    assert not use_replit_anthropic()
    assert not loaded.has_llm_credentials


def _fresh_intake():
    """Run llm_extract's module-level code again under another name, so other modules keep their classes."""
    spec = importlib.util.spec_from_file_location("llm_extract_fresh", llm_extract.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_intake_model_label_and_price_follow_the_route(env):
    assert _fresh_intake().MODEL_LABEL == "Claude Haiku 5.5 (Anthropic)"
    assert (_fresh_intake().PRICE_IN_PER_M, _fresh_intake().PRICE_OUT_PER_M) == (0.10, 0.50)
    for name, value in REPLIT.items():
        env.setenv(name, value)
    module = _fresh_intake()
    assert module.MODEL == "claude-haiku-4-5"
    assert module.MODEL_LABEL == "Claude Haiku 4.5 (Anthropic via Replit AI Integrations)"
    assert (module.PRICE_IN_PER_M, module.PRICE_OUT_PER_M) == (1.00, 5.00)
