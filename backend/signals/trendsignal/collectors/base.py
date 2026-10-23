"""Shared collector types and an HTTP helper with retries."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from trendsignal.config import Settings, SourceConfig
from trendsignal.models import RawItemIn

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT_SECONDS = 20.0


class CollectError(RuntimeError):
    """A source could not be collected. The runner records it and trips the circuit breaker."""


@dataclass(frozen=True)
class CollectContext:
    settings: Settings
    http: httpx.Client
    etag: str | None = None
    last_modified: str | None = None
    budget_remaining_usd: float | None = None

    @property
    def db_path(self) -> Path:
        return self.settings.db_path


@dataclass(frozen=True)
class CollectResult:
    items: tuple[RawItemIn, ...]
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False
    cost_usd: float = 0.0
    note: str | None = None


Collector = Callable[[SourceConfig, CollectContext], CollectResult]


def make_http_client(settings: Settings) -> httpx.Client:
    return httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
    )


def get_with_retry(
    client: httpx.Client,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> httpx.Response:
    """GET with exponential backoff on 429/5xx and network errors. 304 counts as success."""
    last_error: str = "no attempt made"
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TransportError as exc:
            last_error = f"network error: {exc.__class__.__name__}: {exc}"
        else:
            if response.status_code < 400:
                return response
            if response.status_code not in RETRYABLE_STATUS:
                raise CollectError(f"HTTP {response.status_code} from {url}")
            last_error = f"HTTP {response.status_code} from {url}"
        if attempt < attempts - 1:
            time.sleep(backoff_seconds * (2**attempt))
    raise CollectError(last_error)
