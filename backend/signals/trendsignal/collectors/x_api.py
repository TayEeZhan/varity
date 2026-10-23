"""X collector: curated account timelines through the official pay-per-use API.

Cost control: every call is priced up front (post reads and user lookups) and the
collector stops before a call could push the day's spend past the source budget.
"""

from __future__ import annotations

from typing import Any

import httpx

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.db import connect
from trendsignal.models import RawItemIn
from trendsignal.timeutil import now_utc, parse_any, to_iso

X_API = "https://api.x.com/2"
MIN_MAX_RESULTS = 5  # the timeline endpoint rejects max_results below 5
LOOKUP_BATCH = 100  # users/by accepts up to 100 usernames per request


def load_accounts(ctx: CollectContext, source: SourceConfig) -> list[str]:
    path = ctx.settings.config_dir / str(source.params.get("accounts_file", "x_accounts.txt"))
    if not path.exists():
        raise CollectError(f"X accounts file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip().lstrip("@") for line in lines if line.strip() and not line.startswith("#")]


def _cached_users(ctx: CollectContext) -> dict[str, tuple[str, int]]:
    with connect(ctx.db_path) as conn:
        rows = conn.execute("SELECT username, user_id, followers FROM x_users").fetchall()
    return {row["username"].lower(): (row["user_id"], int(row["followers"] or 0)) for row in rows}


def _cache_users(ctx: CollectContext, requested: list[str], users: list[dict[str, Any]]) -> None:
    """Cache resolved users, and remember unresolved handles (user_id '') so they are not paid for again."""
    fetched_at = to_iso(now_utc())
    found = {str(user["username"]).lower() for user in users}
    with connect(ctx.db_path) as conn:
        for user in users:
            followers = int((user.get("public_metrics") or {}).get("followers_count") or 0)
            conn.execute(
                "INSERT OR REPLACE INTO x_users (username, user_id, followers, fetched_at) VALUES (?, ?, ?, ?)",
                (str(user["username"]).lower(), str(user["id"]), followers, fetched_at),
            )
        for name in requested:
            if name.lower() not in found:
                conn.execute(
                    "INSERT OR REPLACE INTO x_users (username, user_id, followers, fetched_at) VALUES (?, '', 0, ?)",
                    (name.lower(), fetched_at),
                )


def parse_timeline(source: SourceConfig, username: str, followers: int, data: Any) -> tuple[RawItemIn, ...]:
    items = []
    for tweet in (data or {}).get("data") or []:
        published = parse_any(tweet.get("created_at"))
        text = str(tweet.get("text") or "").strip()
        if not tweet.get("id") or published is None or not text:
            continue
        metrics = tweet.get("public_metrics") or {}
        urls = ((tweet.get("entities") or {}).get("urls")) or []
        linked = urls[0].get("expanded_url") if urls else None
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(tweet["id"]),
                url=f"https://x.com/{username}/status/{tweet['id']}",
                title=text.split("\n", 1)[0][:200],
                text=text,
                published_at=published,
                author=username,
                engagement={
                    "likes": float(metrics.get("like_count") or 0),
                    "reposts": float(metrics.get("retweet_count") or 0),
                    "replies": float(metrics.get("reply_count") or 0),
                    "followers": float(followers),
                },
                payload={"linked_url": linked} if linked else {},
            )
        )
    return tuple(items)


def collect_x(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    token = ctx.settings.x_bearer_token
    if not token:
        raise CollectError("X_BEARER_TOKEN is not set")
    budget = ctx.budget_remaining_usd if ctx.budget_remaining_usd is not None else 0.0
    per_read = float(source.params.get("usd_per_post_read", 0.005))
    per_lookup = float(source.params.get("usd_per_user_lookup", 0.010))
    max_results = max(MIN_MAX_RESULTS, int(source.params.get("max_results_per_account", 5)))
    headers = {"Authorization": f"Bearer {token}"}
    spent = 0.0

    accounts = load_accounts(ctx, source)
    known = _cached_users(ctx)
    missing = [name for name in accounts if name.lower() not in known]
    for start in range(0, len(missing), LOOKUP_BATCH):
        batch_names = missing[start:start + LOOKUP_BATCH]
        lookup_cost = per_lookup * len(batch_names)
        if spent + lookup_cost > budget:
            return CollectResult(items=(), cost_usd=round(spent, 4), note="daily X budget reached before user lookup")
        response = get_with_retry(ctx.http, f"{X_API}/users/by", headers=headers,
                                  params={"usernames": ",".join(batch_names), "user.fields": "public_metrics"})
        spent += lookup_cost
        _cache_users(ctx, batch_names, response.json().get("data") or [])
    known = _cached_users(ctx)

    collected: list[RawItemIn] = []
    for name in accounts:
        user = known.get(name.lower())
        if user is None or not user[0]:
            continue  # handle could not be resolved (typo, renamed or suspended account)
        if spent + per_read * max_results > budget:
            return CollectResult(items=tuple(collected), cost_usd=round(spent, 4), note="daily X budget reached")
        try:
            response = get_with_retry(
                ctx.http, f"{X_API}/users/{user[0]}/tweets", headers=headers,
                params={"max_results": max_results, "exclude": "retweets,replies",
                        "tweet.fields": "created_at,public_metrics,entities"},
            )
        except (CollectError, httpx.HTTPError) as exc:
            # Keep what was already paid for; the next poll picks up the rest.
            return CollectResult(items=tuple(collected), cost_usd=round(spent, 4),
                                 note=f"stopped early: X timeline for {name} failed ({exc.__class__.__name__})")
        batch = parse_timeline(source, name, user[1], response.json())
        spent += per_read * len(batch)
        collected.extend(batch)
    return CollectResult(items=tuple(collected), cost_usd=round(spent, 4))
