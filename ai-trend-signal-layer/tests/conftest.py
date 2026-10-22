"""Shared fixtures: an isolated database per test and helpers to seed items."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from trendsignal.collectors.runner import store_items
from trendsignal.config import PROJECT_ROOT, SourceConfig, load_settings, load_watchlist, load_weights
from trendsignal.db import connect, init_schema
from trendsignal.jobs import load_context
from trendsignal.models import RawItemIn
from trendsignal.timeutil import now_utc, to_iso

CONFIG_DIR = PROJECT_ROOT / "config"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TRENDSIGNAL_DOTENV", "0")  # never pick up a developer's real keys in tests
    monkeypatch.setenv("TRENDSIGNAL_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("TRENDSIGNAL_LLM", "off")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    loaded = load_settings()
    init_schema(loaded.db_path)
    return loaded


@pytest.fixture
def llm_settings(settings, monkeypatch):
    """Settings that believe Claude credentials exist (the client itself is always faked)."""
    monkeypatch.setenv("TRENDSIGNAL_LLM", "auto")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    return load_settings()


@pytest.fixture
def weights():
    return load_weights(CONFIG_DIR)


@pytest.fixture
def watchlist():
    return load_watchlist(CONFIG_DIR)


@pytest.fixture
def ctx(settings):
    return load_context(settings)


def source(source_id: str, tier: str = "A", adapter: str = "rss", **params) -> SourceConfig:
    return SourceConfig(id=source_id, name=source_id.replace("_", " ").title(), tier=tier, adapter=adapter,
                        poll_every_minutes=60, url="https://example.com/feed", params=params)


def raw(source_id: str, external_id: str, title: str, *, url: str | None = None, text: str = "",
        hours_ago: float = 2.0, author: str | None = None, engagement: dict | None = None,
        payload: dict | None = None, now: datetime | None = None) -> RawItemIn:
    published = (now or now_utc()) - timedelta(hours=hours_ago)
    return RawItemIn(source_id=source_id, external_id=external_id, url=url or f"https://example.com/{external_id}",
                     title=title, text=text, published_at=published, author=author,
                     engagement=engagement or {}, payload=payload or {})


def seed(settings, source_config: SourceConfig, items: list[RawItemIn]) -> tuple[int, int]:
    with connect(settings.db_path) as conn:
        return store_items(conn, source_config, tuple(items), to_iso(now_utc()))


def fake_message(text: str, stop_reason: str = "end_turn", input_tokens: int = 1000, output_tokens: int = 200):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
    )
