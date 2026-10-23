"""Hugging Face Daily Papers collector. Upvotes give a community attention signal for papers."""

from __future__ import annotations

from typing import Any

from trendsignal.collectors.base import CollectContext, CollectError, CollectResult, get_with_retry
from trendsignal.config import SourceConfig
from trendsignal.models import RawItemIn
from trendsignal.timeutil import parse_any

DAILY_PAPERS_API = "https://huggingface.co/api/daily_papers"


def parse_daily_papers(source: SourceConfig, data: Any) -> tuple[RawItemIn, ...]:
    if not isinstance(data, list):
        raise CollectError("unexpected Hugging Face daily_papers response shape")
    min_upvotes = int(source.params.get("min_upvotes", 0))
    items = []
    for entry in data:
        paper = entry.get("paper") or {}
        paper_id = paper.get("id")
        upvotes = float(paper.get("upvotes") or 0)
        published = parse_any(entry.get("publishedAt") or paper.get("publishedAt"))
        title = " ".join(str(entry.get("title") or paper.get("title") or "").split())
        if not paper_id or published is None or not title or upvotes < min_upvotes:
            continue
        authors = [a.get("name") for a in paper.get("authors", []) if a.get("name")]
        items.append(
            RawItemIn(
                source_id=source.id,
                external_id=str(paper_id),
                url=f"https://huggingface.co/papers/{paper_id}",
                title=title,
                text=" ".join(str(paper.get("summary") or "").split()),
                published_at=published,
                author=(f"{authors[0]} et al." if len(authors) > 1 else (authors[0] if authors else None)),
                engagement={"upvotes": upvotes, "comments": float(entry.get("numComments") or 0)},
                payload={"arxiv_id": paper_id},
            )
        )
    return tuple(items)


def collect_hf_papers(source: SourceConfig, ctx: CollectContext) -> CollectResult:
    response = get_with_retry(ctx.http, DAILY_PAPERS_API, params={"limit": 50})
    return CollectResult(items=parse_daily_papers(source, response.json()))
