"""Claude client, per-call cost accounting, and the daily LLM budget gate."""

from __future__ import annotations

import threading
from datetime import datetime

import anthropic

from trendsignal.config import Settings
from trendsignal.db import connect
from trendsignal.timeutil import now_utc

# USD per million tokens (input, output), first-party API list prices.
PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
LLM_JOBS = ("enrich", "digest:daily", "digest:weekly")
CLIENT_TIMEOUT_SECONDS = 120.0


def make_client() -> anthropic.Anthropic:
    """Credentials come from the environment (ANTHROPIC_API_KEY, an `ant auth login` profile, or
    the Replit AI Integrations pair that config.use_replit_anthropic maps to ANTHROPIC_*)."""
    return anthropic.Anthropic(max_retries=2, timeout=CLIENT_TIMEOUT_SECONDS)


def usage_cost(model: str, usage: object) -> float:
    input_price, output_price = PRICES_PER_MTOK.get(model, PRICES_PER_MTOK["claude-sonnet-5-5"])
    input_tokens = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    return (input_tokens * input_price + cached * input_price * 0.1 + output_tokens * output_price) / 1_000_000


def llm_spent_since(settings: Settings, since_iso: str) -> float:
    placeholders = ",".join("?" for _ in LLM_JOBS)
    with connect(settings.db_path) as conn:
        row = conn.execute(
            f"SELECT COALESCE(SUM(cost_usd), 0) AS spent FROM runs WHERE job IN ({placeholders}) AND started_at >= ?",
            (*LLM_JOBS, since_iso),
        ).fetchone()
    return float(row["spent"])


class LlmGate:
    """Decides whether Claude may be called right now. Thread-safe; closes for the rest of a run
    once the daily budget is spent or a non-retryable API error (auth, model not found) happens."""

    def __init__(self, settings: Settings, spent_today: float, now: datetime | None = None):
        self._lock = threading.Lock()
        self._budget = settings.llm_daily_budget_usd
        self._spent = spent_today
        self.started_at = now or now_utc()
        self.run_cost = 0.0
        self.reason: str | None = None
        if not settings.has_llm_credentials:
            self.reason = "no Claude credentials (set ANTHROPIC_API_KEY, or enable Replit AI Integrations for Anthropic) or TRENDSIGNAL_LLM=off"
        elif spent_today >= self._budget:
            self.reason = f"daily LLM budget of ${self._budget:.2f} reached"

    @property
    def open(self) -> bool:
        with self._lock:
            return self.reason is None

    def record(self, cost: float) -> None:
        with self._lock:
            self._spent += cost
            self.run_cost += cost
            if self._spent >= self._budget and self.reason is None:
                self.reason = f"daily LLM budget of ${self._budget:.2f} reached"

    def close(self, reason: str) -> None:
        with self._lock:
            if self.reason is None:
                self.reason = reason
