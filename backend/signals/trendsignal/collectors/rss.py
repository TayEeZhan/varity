"""RSS / Atom collector. Covers lab blogs, press, and GitHub releases (releases.atom)."""

from __future__ import annotations

import feedparser

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import parse_any

DEFAULT_MAX_ENTRIES = 40


def _entry_text(entry: feedparser.FeedParserDict) -> str:
    content = entry.get("content")
    if content:
        return str(content[0].get("value", ""))
    return str(entry.get("summary", ""))


def _entry_title(entry: feedparser.FeedParserDict, prefix: str | None) -> str:
    title = str(entry.get("title", "")).strip()
    if prefix and not title.lower().startswith(prefix.lower()):
        return f"{prefix} {title}".strip()
    return title


def parse_feed(source: SourceConfig, body: bytes) -> tuple[RawItemIn, ...]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise CollectError(f"unparseable feed for {source.id}: {feed.get('bozo_exception')}")
    prefix = source.params.get("title_prefix")
    max_entries = int(source.params.get("max_entries", DEFAULT_MAX_ENTRIES))
    items = []
    for entry in feed.entries[:max_entries]:
        published = parse_any(entry.get("published_parsed") or entry.get("updated_parsed"))
        link = str(entry.get("link") or "")
        title = _entry_title(entry, prefix)
        if published is None or not link or not title:
            continue  # no date, no link or no title: not a usable record
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(entry.get("id") or link),
                url=link,
                title=title,
                text=_entry_text(entry),
                published_at=published,
                author=entry.get("author"),
                payload={"feed_title": feed.feed.get("title", ""), "tags": [t.get("term") for t in entry.get("tags", [])]},
            )
        )
    return tuple(items)


def collect_rss(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    headers = {}
    if ctx.etag:
        headers["If-None-Match"] = ctx.etag
    if ctx.last_modified:
        headers["If-Modified-Since"] = ctx.last_modified
    response = get_with_retry(ctx.http, str(source.url), headers=headers)
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")
    if response.status_code == 304:
        return CollectResult(items=(), etag=ctx.etag, last_modified=ctx.last_modified, not_modified=True)
    return CollectResult(items=parse_feed(source, response.content), etag=etag, last_modified=last_modified)
