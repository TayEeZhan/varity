"""Bluesky collector: curated accounts via the public AppView (no login needed)."""

from __future__ import annotations

from typing import Any

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import parse_any

AUTHOR_FEED = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"


def _post_url(post: dict[str, Any]) -> str:
    handle = (post.get("author") or {}).get("handle", "")
    rkey = str(post.get("uri", "")).rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def parse_author_feed(source: SourceConfig, data: Any) -> tuple[RawItemIn, ...]:
    feed = data.get("feed") if isinstance(data, dict) else None
    if feed is None:
        raise CollectError("unexpected Bluesky response shape")
    items = []
    for entry in feed:
        if entry.get("reason"):
            continue  # a repost: the original author's post is what matters
        post = entry.get("post") or {}
        record = post.get("record") or {}
        published = parse_any(record.get("createdAt"))
        text = str(record.get("text") or "").strip()
        if not post.get("uri") or published is None or not text:
            continue
        external = ((post.get("embed") or {}).get("external")) or {}
        linked = external.get("uri")
        full_text = " ".join(filter(None, [text, external.get("title"), external.get("description")]))
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(post["uri"]),
                url=_post_url(post),
                title=text.split("\n", 1)[0][:200],
                text=full_text,
                published_at=published,
                author=(post.get("author") or {}).get("handle"),
                engagement={
                    "likes": float(post.get("likeCount") or 0),
                    "reposts": float(post.get("repostCount") or 0),
                    "replies": float(post.get("replyCount") or 0),
                },
                payload={"linked_url": linked} if linked else {},
            )
        )
    return tuple(items)


def collect_bluesky(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    handles = list(source.params.get("handles") or [])
    if not handles:
        raise CollectError("bluesky source has no handles configured")
    collected: list[RawItemIn] = []
    for handle in handles:
        params = {"actor": handle, "limit": 30, "filter": "posts_no_replies"}
        response = get_with_retry(ctx.http, AUTHOR_FEED, params=params)
        collected.extend(parse_author_feed(source, response.json()))
    return CollectResult(items=tuple(collected))
