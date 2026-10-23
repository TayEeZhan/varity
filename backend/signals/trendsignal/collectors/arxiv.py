"""arXiv API collector (Atom). arXiv asks for at most one request every 3 seconds; we poll daily."""

from __future__ import annotations

import feedparser

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import parse_any

ARXIV_API = "https://export.arxiv.org/api/query"


def _author_label(entry: feedparser.FeedParserDict) -> str | None:
    authors = [a.get("name") for a in entry.get("authors", []) if a.get("name")]
    if not authors:
        return None
    return authors[0] if len(authors) == 1 else f"{authors[0]} et al."


def parse_arxiv(source: SourceConfig, body: bytes) -> tuple[RawItemIn, ...]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise CollectError(f"unparseable arXiv response: {feed.get('bozo_exception')}")
    items = []
    for entry in feed.entries:
        published = parse_any(entry.get("published_parsed"))
        link = str(entry.get("link") or entry.get("id") or "")
        if published is None or not link:
            continue
        title = " ".join(str(entry.get("title", "")).split())
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(entry.get("id") or link),
                url=link,
                title=title,
                text=" ".join(str(entry.get("summary", "")).split()),
                published_at=published,
                author=_author_label(entry),
                payload={"categories": [t.get("term") for t in entry.get("tags", [])]},
            )
        )
    return tuple(items)


def collect_arxiv(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    categories = source.params.get("categories") or ["cs.AI"]
    query = " OR ".join(f"cat:{category}" for category in categories)
    params = {
        "search_query": query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": int(source.params.get("max_results", 50)),
    }
    response = get_with_retry(ctx.http, ARXIV_API, params=params, backoff_seconds=3.0)
    return CollectResult(items=parse_arxiv(source, response.content))
