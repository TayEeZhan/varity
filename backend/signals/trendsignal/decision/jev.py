"""Jev client: TypeSafe AI's System One decision model (ARCHITECTURE_JEV_RANKER.md section 6).

Jev takes structured state plus typed questions and answers with probability distributions.
We ask three questions:
  tier        Choice  must_know / worth_a_look / minor
  impact      Score   five ordered impact levels
  same_story  Noul    yes/no probability, only for item pairs the clusterer cannot decide

Guardrails: a 2-second timeout and no SDK retries; non-retryable errors (auth, permission,
unknown model, rate limit) close the client for the rest of the run; every answer is
validated before use and cached by a hash of the state, so unchanged stories are not paid for twice.
Any failure raises JevError and the caller falls back to the formula.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Protocol

from trendsignal.config import Settings
from trendsignal.db import connect, dumps
from trendsignal.pipeline.features import StoryFeatures, jev_state, state_hash
from trendsignal.timeutil import now_utc, to_iso

log = logging.getLogger(__name__)

try:
    from typesafe_sdk import (TypeSafeAuthenticationError, TypeSafeNotFoundError, TypeSafePermissionDeniedError,
                              TypeSafeRateLimitError)
except ImportError:  # the SDK is optional: without it make_jev_client returns None
    FATAL_ERRORS: tuple[type[BaseException], ...] = ()
    RATE_LIMIT_ERRORS: tuple[type[BaseException], ...] = ()
else:
    # These will not fix themselves within a run, so stop asking and let the formula rank.
    FATAL_ERRORS = (TypeSafeAuthenticationError, TypeSafePermissionDeniedError, TypeSafeNotFoundError)
    # A rate limit clears in seconds: wait and retry before giving up on the run.
    RATE_LIMIT_ERRORS = (TypeSafeRateLimitError,)

RATE_LIMIT_RETRIES = 4
RATE_LIMIT_FIRST_WAIT_S = 2.0  # doubles each retry: 2, 4, 8, 16 s

USD_PER_MILLION_INPUT_TOKENS = 0.042  # TypeSafe list price; output tokens are free
DEFAULT_MAX_CALLS_PER_RUN = 400
PROBABILITY_SUM_TOLERANCE = 0.05

TIER_KEYS = ("must_know", "worth_a_look", "minor")

STATE_GUIDE = (
    "The state is a feature vector computed by code for one AI or tech news story. best_tier: highest-trust "
    "source (A official, B research, C community, D social). origins: independent sources reporting it. "
    "velocity_z: attention growth versus that source's normal (above 1.5 is trending). category_rule and "
    "category_confidence: a rule-based label and how sure the rule was. release_level: version bump for tool "
    "releases. novelty: 1 means unlike any story from the last 14 days. superseded: a newer release of the "
    "same tool exists. age_hours: time since first seen."
)

TIER_CRITERIA = {
    "must_know": "Most CS students and software developers should know this today: a new frontier model or "
                 "major platform shift, a critical security issue in widely used software, or a breaking "
                 "change in a widely used tool, normally confirmed by an official source or several reports.",
    "worth_a_look": "Useful to many developers but not urgent: a notable release or feature, research with "
                    "practical results, or a significant pricing or policy change.",
    "minor": "Routine or niche: patch or pre-releases, tutorials, opinion, business news, or a single "
             "unconfirmed social post.",
}

IMPACT_LEVELS = (
    "Noise: opinion, rumour, marketing, nightly or pre-release builds.",
    "Minor: a point or patch release, a small feature, an ordinary paper, routine business news.",
    "Notable: a new API capability, a significant library release, a paper with clear practical results.",
    "Big: a major version of a widely used tool, an API pricing or deprecation change, a state-of-the-art "
    "result with released code.",
    "Changes how many developers work: a new frontier model, a major platform shift, a critical "
    "vulnerability in a widely used library.",
)

SAME_STORY_INSTRUCTIONS = (
    "Two news items are given with their titles, sources, publication gap in hours, text similarity "
    "(0 to 1) and shared distinctive names. Answer yes only if both items report the same real-world "
    "event, release or announcement, not merely the same topic or product."
)


class JevError(RuntimeError):
    """Jev could not answer this request; the caller falls back to the formula."""


class SystemOneClient(Protocol):
    def system_one(self, state: Any, questions: dict, *, timeout: float | None = None) -> Any: ...


@dataclass(frozen=True)
class JevDecision:
    tier_probs: dict[str, float]
    impact_probs: dict[int, float]  # impact level 1..5 -> probability
    tier_confidence: float  # Jev's own confidence values, stored for calibration analysis
    impact_confidence: float
    model: str
    cached: bool = False

    def as_cache(self) -> dict:
        return {"tier_probs": self.tier_probs, "impact_probs": {str(k): v for k, v in self.impact_probs.items()},
                "tier_confidence": self.tier_confidence, "impact_confidence": self.impact_confidence}


def story_questions() -> dict[str, dict]:
    return {
        "tier": {"type": "choice", "instructions": f"{STATE_GUIDE} Which tier fits this story?",
                 "criteria": dict(TIER_CRITERIA)},
        "impact": {"type": "score", "instructions": f"{STATE_GUIDE} How large is the change for developers?",
                   "criteria": list(IMPACT_LEVELS)},
    }


def _normalised(probs: dict, keys: tuple, what: str) -> dict:
    values = {}
    for key in keys:
        value = probs.get(key)
        if value is None or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
            raise JevError(f"{what}: missing or invalid probability for {key!r}")
        values[key] = float(value)
    total = sum(values.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise JevError(f"{what}: probabilities sum to {total:.3f}, not 1")
    return {key: value / total for key, value in values.items()}


def _impact_level_map(answer: Any) -> dict[Any, int]:
    """Map Jev's score keys to impact levels 1..5. Prefer the legend (the criterion text it echoes);
    otherwise accept 0..4 or 1..5 indices."""
    probabilities = getattr(answer, "probabilities", None) or {}
    legend = getattr(answer, "legend", None) or {}
    by_text = {text: level for level, text in enumerate(IMPACT_LEVELS, start=1)}
    mapped = {key: by_text[value] for key, value in legend.items() if isinstance(value, str) and value in by_text}
    if len(mapped) == len(IMPACT_LEVELS):
        return mapped
    keys = sorted(int(k) for k in probabilities)
    if keys == [0, 1, 2, 3, 4]:
        return {k: int(k) + 1 for k in probabilities}
    if keys == [1, 2, 3, 4, 5]:
        return {k: int(k) for k in probabilities}
    raise JevError(f"impact: cannot map score keys {keys} to levels 1..5")


def parse_story_answers(response: Any, model: str) -> JevDecision:
    answers = getattr(response, "answers", None)
    if not isinstance(answers, dict) or "tier" not in answers or "impact" not in answers:
        raise JevError("response is missing the tier or impact answer")
    tier, impact = answers["tier"], answers["impact"]
    tier_probs = _normalised(getattr(tier, "probabilities", None) or {}, TIER_KEYS, "tier")
    level_map = _impact_level_map(impact)
    raw_impact = {level_map[key]: value for key, value in (impact.probabilities or {}).items()}
    impact_probs = _normalised(raw_impact, (1, 2, 3, 4, 5), "impact")
    return JevDecision(
        tier_probs={k: round(v, 4) for k, v in tier_probs.items()},
        impact_probs={k: round(v, 4) for k, v in impact_probs.items()},
        tier_confidence=round(float(getattr(tier, "confidence", 0.0) or 0.0), 4),
        impact_confidence=round(float(getattr(impact, "confidence", 0.0) or 0.0), 4),
        model=str(getattr(response, "model", None) or model),
    )


class JevCache:
    """Answers keyed by (model, state hash) in SQLite."""

    def __init__(self, db_path: Path):
        self._db_path = db_path

    def get(self, model: str, key: str) -> JevDecision | None:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT answers_json FROM jev_cache WHERE model = ? AND state_hash = ?",
                               (model, key)).fetchone()
        if row is None:
            return None
        data = json.loads(row["answers_json"])
        return JevDecision(
            tier_probs=data["tier_probs"], impact_probs={int(k): v for k, v in data["impact_probs"].items()},
            tier_confidence=data["tier_confidence"], impact_confidence=data["impact_confidence"],
            model=model, cached=True,
        )

    def put(self, model: str, key: str, decision: JevDecision) -> None:
        with connect(self._db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO jev_cache (state_hash, model, answers_json, created_at)"
                         " VALUES (?, ?, ?, ?)", (key, model, dumps(decision.as_cache()), to_iso(now_utc())))


class JevClient:
    """Thread-safe wrapper used by one pipeline run."""

    def __init__(self, client: SystemOneClient, model: str, *, timeout_s: float = 2.0,
                 cache: JevCache | None = None, max_calls: int = DEFAULT_MAX_CALLS_PER_RUN,
                 sleep: Callable[[float], None] = time.sleep):
        self._client, self.model, self._timeout = client, model, timeout_s
        self._cache, self._max_calls, self._sleep = cache, max_calls, sleep
        self._lock = threading.Lock()
        self.calls = 0
        self.input_tokens = 0
        self.reason: str | None = None

    @property
    def open(self) -> bool:
        with self._lock:
            return self.reason is None

    @property
    def cost_usd(self) -> float:
        return round(self.input_tokens * USD_PER_MILLION_INPUT_TOKENS / 1_000_000, 6)

    def _reserve_call(self) -> None:
        with self._lock:
            if self.reason is not None:
                raise JevError(self.reason)
            if self.calls >= self._max_calls:
                self.reason = f"Jev call limit of {self._max_calls} per run reached"
                raise JevError(self.reason)
            self.calls += 1

    def _close(self, reason: str) -> None:
        with self._lock:
            if self.reason is None:
                self.reason = reason
        log.warning("Jev disabled for this run: %s", reason)

    def _ask(self, state: dict, questions: dict) -> Any:
        self._reserve_call()
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                response = self._client.system_one(state, questions, timeout=self._timeout)
                break
            except RATE_LIMIT_ERRORS as exc:
                if attempt == RATE_LIMIT_RETRIES or not self.open:
                    self._close(f"Jev rate limit persisted after {RATE_LIMIT_RETRIES} retries")
                    raise JevError(self.reason) from exc
                self._sleep(RATE_LIMIT_FIRST_WAIT_S * (2 ** attempt))
            except FATAL_ERRORS as exc:
                self._close(f"Jev rejected the request ({exc.__class__.__name__})")
                raise JevError(self.reason) from exc
            except Exception as exc:  # timeout, connection, server or validation error: fall back for this call only
                raise JevError(f"Jev call failed ({exc.__class__.__name__})") from exc
        usage = getattr(response, "usage", None)
        with self._lock:
            self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        return response

    def decide(self, features: StoryFeatures) -> JevDecision:
        state = jev_state(features)
        key = state_hash(state)
        if self._cache is not None:
            cached = self._cache.get(self.model, key)
            if cached is not None:
                return cached
        decision = parse_story_answers(self._ask(state, story_questions()), self.model)
        if self._cache is not None:
            self._cache.put(self.model, key, decision)
        return decision

    def same_story(self, pair_state: dict) -> float:
        response = self._ask(pair_state, {"same_story": {"type": "noul", "instructions": SAME_STORY_INSTRUCTIONS}})
        answer = (getattr(response, "answers", None) or {}).get("same_story")
        value = getattr(answer, "noul", None)
        if not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0:
            raise JevError("same_story: missing or out-of-range probability")
        return float(value)


def make_jev_client(settings: Settings) -> JevClient | None:
    """None when Jev is not configured; the formula then ranks on its own."""
    if not settings.jev_enabled:
        return None
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient
    except ImportError:
        log.warning("TYPESAFE_API_KEY is set but typesafe-sdk is not installed; ranking with the formula")
        return None
    client = TypeSafeClient(api_key=settings.jev_api_key, model=settings.jev_model, timeout=settings.jev_timeout_s,
                            base_url=settings.jev_base_url,  # Replit AI Integrations route; None = TypeSafe's API
                            retry=RetryPolicy(max_retries=0, timeout=settings.jev_timeout_s))
    return JevClient(client, settings.jev_model, timeout_s=settings.jev_timeout_s, cache=JevCache(settings.db_path))
