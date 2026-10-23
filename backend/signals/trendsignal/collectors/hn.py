"""Hacker News collector via the Algolia search API (free, no key)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import now_utc, parse_any

ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    lowered = title.lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])", lowered) for k in keywords)


def parse_hits(source: SourceConfig, data: Any) -> tuple[RawItemIn, ...]:
    hits = data.get("hits") if isinstance(data, dict) else None
    if hits is None:
        raise CollectError("unexpected Hacker News response shape")
    keywords = list(source.params.get("keywords") or [])
    items = []
    for hit in hits:
        object_id = hit.get("objectID")
        title = str(hit.get("title") or "").strip()
        published = parse_any(hit.get("created_at_i"))
        if not object_id or not title or published is None or not _matches_keywords(title, keywords):
            continue
        discussion = f"https://news.ycombinator.com/item?id={object_id}"
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(object_id),
                url=str(hit.get("url") or discussion),
                title=title,
                text=str(hit.get("story_text") or ""),
                published_at=published,
                author=hit.get("author"),
                engagement={"points": float(hit.get("points") or 0), "comments": float(hit.get("num_comments") or 0)},
                payload={"discussion_url": discussion},
            )
        )
    return tuple(items)


def collect_hn(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    since = now_utc() - timedelta(hours=int(source.params.get("lookback_hours", 48)))
    min_points = int(source.params.get("min_points", 50))
    params = {
        "tags": "story",
        "numericFilters": f"points>={min_points},created_at_i>={int(since.timestamp())}",
        "hitsPerPage": 200,
    }
    response = get_with_retry(ctx.http, ALGOLIA_SEARCH, params=params)
    return CollectResult(items=parse_hits(source, response.json()))
