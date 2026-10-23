"""Threads collector: keyword search through the official Threads API.

Public results need the `threads_keyword_search` permission (Meta App Review). Without it
the endpoint only returns the token owner's own posts, so this source ships disabled.
Meta limits each user to 2,200 queries per rolling 24 hours.
"""

from __future__ import annotations

from typing import Any

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import parse_any

KEYWORD_SEARCH = "https://graph.threads.net/v1.0/keyword_search"
FIELDS = "id,text,permalink,timestamp,username"


def parse_search(source: SourceConfig, data: Any) -> tuple[RawItemIn, ...]:
    posts = data.get("data") if isinstance(data, dict) else None
    if posts is None:
        raise CollectError("unexpected Threads response shape")
    items = []
    for post in posts:
        published = parse_any(post.get("timestamp"))
        text = str(post.get("text") or "").strip()
        if not post.get("id") or not post.get("permalink") or published is None or not text:
            continue
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(post["id"]),
                url=str(post["permalink"]),
                title=text.split("\n", 1)[0][:200],
                text=text,
                published_at=published,
                author=post.get("username"),
            )
        )
    return tuple(items)


def collect_threads(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    token = ctx.settings.threads_access_token
    if not token:
        raise CollectError("THREADS_ACCESS_TOKEN is not set")
    headers = {"Authorization": f"Bearer {token}"}
    collected: list[RawItemIn] = []
    for keyword in source.params.get("keywords") or []:
        params = {"q": keyword, "search_type": source.params.get("search_type", "TOP"), "fields": FIELDS}
        response = get_with_retry(ctx.http, KEYWORD_SEARCH, params=params, headers=headers)
        collected.extend(parse_search(source, response.json()))
    unique = {item.external_id: item for item in collected}
    return CollectResult(items=tuple(unique.values()))
