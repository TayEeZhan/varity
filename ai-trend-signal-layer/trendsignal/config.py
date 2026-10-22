"""Settings from environment variables, plus the YAML files under config/."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALID_TIERS = ("A", "B", "C", "D")
VALID_ADAPTERS = ("rss", "arxiv", "hf_papers", "hn", "bluesky", "x_api", "threads")
FEATURE_NAMES = ("impact", "authority", "corroboration", "velocity", "dev_relevance", "novelty")


class ConfigError(ValueError):
    """A config file is missing a required field or has an invalid value."""


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    tier: str
    adapter: str
    poll_every_minutes: int
    enabled: bool = True
    url: str | None = None
    daily_budget_usd: float | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Weights:
    version: str
    tier_trust: dict[str, float]
    feature_weights: dict[str, float]
    corroboration_k: float
    social_origin_cap: int
    penalty_unconfirmed: float
    penalty_opinion: float
    freshness_tau_hours: dict[str, float]
    must_know_threshold: float
    worth_a_look_threshold: float
    daily_must_know_cap: int
    emerging_velocity_min: float
    cluster_similarity: float
    cluster_similarity_with_key_term: float
    cluster_window_hours: int
    novelty_lookback_days: int


@dataclass(frozen=True)
class Watchlist:
    dev_terms: tuple[str, ...]
    skills: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class Settings:
    db_path: Path
    config_dir: Path
    enrich_model: str
    editor_model: str
    llm_mode: str  # "auto" uses Claude when credentials exist; "off" forces heuristics
    llm_daily_budget_usd: float
    timezone: str
    user_agent: str
    admin_token: str | None
    x_bearer_token: str | None
    threads_access_token: str | None
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    scheduler_enabled: bool
    jev_api_key: str | None = None
    jev_model: str = "jev-1.13.0"  # pinned: moving aliases (jev-latest) can change rankings silently
    jev_timeout_s: float = 2.0
    jev_mode: str = "auto"  # "off" never calls Jev even when a key is set
    ranker: str = "formula"  # who ranks: "formula" until Jev wins on the gold set, then "jev"
    haiku_fallback: bool = False  # ask Claude Haiku for the category only when the rules are unsure
    write_briefs: bool = False  # the daily / weekly prose brief is outside the core ranker

    @property
    def jev_enabled(self) -> bool:
        return self.jev_mode != "off" and bool(self.jev_api_key)

    @property
    def has_llm_credentials(self) -> bool:
        if self.llm_mode == "off":
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from a local .env. Real environment variables always win."""
    if not path.exists() or os.environ.get("TRENDSIGNAL_DOTENV") == "0":
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value:
            os.environ.setdefault(key, value.strip("\"'"))


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    config_dir = Path(_env("TRENDSIGNAL_CONFIG_DIR", str(PROJECT_ROOT / "config")))
    llm_mode = _env("TRENDSIGNAL_LLM", "auto")
    if llm_mode not in ("auto", "off"):
        raise ConfigError(f"TRENDSIGNAL_LLM must be 'auto' or 'off', got {llm_mode!r}")
    jev_mode = _env("TRENDSIGNAL_JEV", "auto")
    if jev_mode not in ("auto", "off"):
        raise ConfigError(f"TRENDSIGNAL_JEV must be 'auto' or 'off', got {jev_mode!r}")
    ranker = _env("TRENDSIGNAL_RANKER", "formula")
    if ranker not in ("formula", "jev"):
        raise ConfigError(f"TRENDSIGNAL_RANKER must be 'formula' or 'jev', got {ranker!r}")
    return Settings(
        db_path=Path(_env("TRENDSIGNAL_DB", str(PROJECT_ROOT / "data" / "trendsignal.db"))),
        config_dir=config_dir,
        enrich_model=_env("TRENDSIGNAL_ENRICH_MODEL", "claude-haiku-5-5"),
        editor_model=_env("TRENDSIGNAL_EDITOR_MODEL", "claude-sonnet-5-5"),
        llm_mode=llm_mode,
        llm_daily_budget_usd=float(_env("TRENDSIGNAL_LLM_DAILY_BUDGET_USD", "2.0")),
        timezone=_env("TRENDSIGNAL_TZ", "Asia/Kuala_Lumpur"),
        user_agent=_env("TRENDSIGNAL_USER_AGENT", "AITrendSignalLayer/0.1 (+hackathon project)"),
        admin_token=_env("ADMIN_TOKEN"),
        x_bearer_token=_env("X_BEARER_TOKEN"),
        threads_access_token=_env("THREADS_ACCESS_TOKEN"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
        scheduler_enabled=_env("TRENDSIGNAL_SCHEDULER", "0") == "1",
        jev_api_key=_env("TYPESAFE_API_KEY"),
        jev_model=_env("TRENDSIGNAL_JEV_MODEL", "jev-1.13.0"),
        jev_timeout_s=float(_env("TRENDSIGNAL_JEV_TIMEOUT", "2.0")),
        jev_mode=jev_mode,
        ranker=ranker,
        haiku_fallback=_env("TRENDSIGNAL_HAIKU_FALLBACK", "0") == "1",
        write_briefs=_env("TRENDSIGNAL_BRIEFS", "0") == "1",
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing config file: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return data


def _parse_source(entry: dict[str, Any]) -> SourceConfig:
    missing = [key for key in ("id", "name", "tier", "adapter", "poll_every_minutes") if key not in entry]
    if missing:
        raise ConfigError(f"source {entry.get('id', '?')} is missing {missing}")
    if entry["tier"] not in VALID_TIERS:
        raise ConfigError(f"source {entry['id']}: tier must be one of {VALID_TIERS}")
    if entry["adapter"] not in VALID_ADAPTERS:
        raise ConfigError(f"source {entry['id']}: adapter must be one of {VALID_ADAPTERS}")
    if entry["adapter"] == "rss" and not entry.get("url"):
        raise ConfigError(f"source {entry['id']}: rss adapter needs a url")
    return SourceConfig(
        id=str(entry["id"]),
        name=str(entry["name"]),
        tier=str(entry["tier"]),
        adapter=str(entry["adapter"]),
        poll_every_minutes=int(entry["poll_every_minutes"]),
        enabled=bool(entry.get("enabled", True)),
        url=entry.get("url"),
        daily_budget_usd=entry.get("daily_budget_usd"),
        params=dict(entry.get("params") or {}),
    )


def load_sources(config_dir: Path) -> tuple[SourceConfig, ...]:
    entries = _read_yaml(config_dir / "sources.yaml").get("sources") or []
    sources = tuple(_parse_source(entry) for entry in entries)
    ids = [source.id for source in sources]
    duplicates = {source_id for source_id in ids if ids.count(source_id) > 1}
    if duplicates:
        raise ConfigError(f"duplicate source ids: {sorted(duplicates)}")
    return sources


def load_weights(config_dir: Path) -> Weights:
    data = _read_yaml(config_dir / "weights.yaml")
    feature_weights = {name: float(data["feature_weights"][name]) for name in FEATURE_NAMES}
    total = sum(feature_weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ConfigError(f"feature_weights must sum to 1.0, got {total:.3f}")
    tiers, cluster, penalties = data["tiers"], data["cluster"], data["penalties"]
    return Weights(
        version=str(data["version"]),
        tier_trust={tier: float(data["tier_trust"][tier]) for tier in VALID_TIERS},
        feature_weights=feature_weights,
        corroboration_k=float(data["corroboration_k"]),
        social_origin_cap=int(data["social_origin_cap"]),
        penalty_unconfirmed=float(penalties["unconfirmed"]),
        penalty_opinion=float(penalties["opinion"]),
        freshness_tau_hours={k: float(v) for k, v in data["freshness_tau_hours"].items()},
        must_know_threshold=float(tiers["must_know"]),
        worth_a_look_threshold=float(tiers["worth_a_look"]),
        daily_must_know_cap=int(tiers["daily_must_know_cap"]),
        emerging_velocity_min=float(tiers["emerging_velocity_min"]),
        cluster_similarity=float(cluster["similarity"]),
        cluster_similarity_with_key_term=float(cluster["similarity_with_key_term"]),
        cluster_window_hours=int(cluster["window_hours"]),
        novelty_lookback_days=int(cluster["novelty_lookback_days"]),
    )


def load_watchlist(config_dir: Path) -> Watchlist:
    data = _read_yaml(config_dir / "watchlist.yaml")
    dev_terms = tuple(str(term).lower() for term in data.get("dev_terms") or [])
    skills = {str(skill): tuple(str(t).lower() for t in terms) for skill, terms in (data.get("skills") or {}).items()}
    return Watchlist(dev_terms=dev_terms, skills=skills)
