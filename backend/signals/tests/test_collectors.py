import time

import httpx
import pytest

from trendsignal.collectors import base
from trendsignal.collectors.arxiv import parse_arxiv
from trendsignal.collectors.base import CollectContext, CollectError, get_with_retry
from trendsignal.collectors.bluesky import parse_author_feed
from trendsignal.collectors.hf_papers import parse_daily_papers
from trendsignal.collectors.hn import parse_hits
from trendsignal.collectors.rss import collect_rss, parse_feed
from trendsignal.collectors.runner import STALE_AFTER_FAILURES, collect_due
from trendsignal.collectors.threads import parse_search
from trendsignal.collectors.x_api import collect_x, parse_timeline
from trendsignal.config import SourceConfig
from trendsignal.db import connect
from tests.conftest import raw, seed, source

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Lab</title>
<item><title>Introducing Model X</title><link>https://lab.example/x</link><guid>x1</guid>
<pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Model X is here.&lt;/p&gt;</description></item>
<item><title>No date</title><link>https://lab.example/nodate</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2610.00001v1</id><title>A  Paper
 Title</title><summary>We study things.</summary><published>2026-10-21T00:00:00Z</published>
<author><name>Ada</name></author><author><name>Alan</name></author>
<link href="http://arxiv.org/abs/2610.00001v1"/><category term="cs.AI"/></entry></feed>"""


def test_parse_feed_skips_undated_entries_and_adds_title_prefix():
    items = parse_feed(source("gh_x", title_prefix="Lab"), RSS)
    assert len(items) == 1
    assert items[0].title == "Lab Introducing Model X" and items[0].external_id == "x1"


def test_parse_feed_rejects_garbage():
    with pytest.raises(CollectError):
        parse_feed(source("bad"), b"this is not xml at all <<<")


def test_parse_arxiv_collapses_whitespace_and_labels_authors():
    item = parse_arxiv(source("arxiv", "B", "arxiv"), ATOM)[0]
    assert item.title == "A Paper Title" and item.author == "Ada et al."


def test_parse_daily_papers_filters_by_upvotes():
    data = [{"title": "Hot", "publishedAt": "2026-10-21T00:00:00Z", "numComments": 3,
             "paper": {"id": "2610.1", "upvotes": 40, "summary": "s", "authors": [{"name": "A"}]}},
            {"title": "Cold", "publishedAt": "2026-10-21T00:00:00Z", "paper": {"id": "2610.2", "upvotes": 1}}]
    items = parse_daily_papers(source("hf", "B", "hf_papers", min_upvotes=5), data)
    assert [i.title for i in items] == ["Hot"] and items[0].engagement["upvotes"] == 40


def test_parse_hits_applies_keyword_filter_and_falls_back_to_discussion_url():
    data = {"hits": [
        {"objectID": "1", "title": "Show HN: a Rust compiler", "points": 100, "created_at_i": 1792600000},
        {"objectID": "2", "title": "Oregon buys a waterfall", "points": 900, "created_at_i": 1792600000,
         "url": "https://news.example/w"}]}
    items = parse_hits(source("hn", "C", "hn", keywords=["rust", "ai"]), data)
    assert [i.external_id for i in items] == ["1"]
    assert items[0].url == "https://news.ycombinator.com/item?id=1"


def test_parse_author_feed_skips_reposts_and_keeps_linked_url():
    post = {"uri": "at://did/app.bsky.feed.post/abc", "author": {"handle": "dev.bsky.social"},
            "record": {"text": "New release!", "createdAt": "2026-10-21T00:00:00Z"}, "likeCount": 10,
            "embed": {"external": {"uri": "https://lab.example/x", "title": "Model X"}}}
    data = {"feed": [{"post": post}, {"post": post, "reason": {"$type": "repost"}}]}
    items = parse_author_feed(source("bsky", "C", "bluesky"), data)
    assert len(items) == 1 and items[0].payload["linked_url"] == "https://lab.example/x"
    assert items[0].url == "https://bsky.app/profile/dev.bsky.social/post/abc"


def test_parse_timeline_and_threads_search():
    tweets = {"data": [{"id": "9", "text": "GPT-6 is out", "created_at": "2026-10-21T00:00:00Z",
                        "public_metrics": {"like_count": 50}, "entities": {"urls": [{"expanded_url": "https://o.ai/x"}]}}]}
    item = parse_timeline(source("x", "D", "x_api"), "openai", 1000, tweets)[0]
    assert item.engagement["followers"] == 1000 and item.url == "https://x.com/openai/status/9"
    threads = {"data": [{"id": "1", "text": "hi", "permalink": "https://threads.net/p/1",
                         "timestamp": "2026-10-21T00:00:00+0000", "username": "dev"}]}
    assert parse_search(source("t", "D", "threads"), threads)[0].author == "dev"


def test_get_with_retry_retries_server_errors(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _s: None)
    responses = iter([httpx.Response(503), httpx.Response(200, text="ok")])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: next(responses)))
    assert get_with_retry(client, "https://example.com").text == "ok"


def test_get_with_retry_does_not_retry_client_errors(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda _s: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    with pytest.raises(CollectError, match="404"):
        get_with_retry(client, "https://example.com")


def test_rss_conditional_get_handles_not_modified(settings):
    def handler(request):
        assert request.headers["If-None-Match"] == '"v1"'
        return httpx.Response(304)
    ctx = CollectContext(settings, httpx.Client(transport=httpx.MockTransport(handler)), etag='"v1"')
    result = collect_rss(source("lab"), ctx)
    assert result.not_modified and result.items == ()


def test_x_collector_stops_at_the_daily_budget(settings, monkeypatch):
    monkeypatch.setattr(settings, "x_bearer_token", "token", raising=False) if False else None
    object.__setattr__(settings, "x_bearer_token", "token")
    accounts = settings.config_dir  # the real x_accounts.txt lists several accounts
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/users/by"):
            names = request.url.params["usernames"].split(",")
            return httpx.Response(200, json={"data": [{"id": str(i), "username": n, "public_metrics": {"followers_count": 10}}
                                                      for i, n in enumerate(names)]})
        return httpx.Response(200, json={"data": [{"id": f"t{len(calls)}-{i}", "text": "post",
                                                   "created_at": "2026-10-21T00:00:00Z"} for i in range(5)]})

    src = SourceConfig("x_curated", "X", "D", "x_api", 180, params={"accounts_file": "x_accounts.txt",
                       "usd_per_post_read": 0.005, "usd_per_user_lookup": 0.01, "max_results_per_account": 5})
    ctx = CollectContext(settings, httpx.Client(transport=httpx.MockTransport(handler)), budget_remaining_usd=0.15)
    result = collect_x(src, ctx)
    assert accounts.exists()
    assert result.cost_usd <= 0.15 and "budget" in (result.note or "")
    assert sum(1 for path in calls if path.endswith("/tweets")) < 8


def test_runner_trips_the_circuit_breaker_after_repeated_failures(settings, monkeypatch):
    from trendsignal.collectors import runner

    def failing(_source, _ctx):
        raise CollectError("boom")

    monkeypatch.setitem(runner.ADAPTERS, "rss", failing)
    src = source("flaky")
    for _ in range(STALE_AFTER_FAILURES):
        summary = collect_due(settings, (src,), force=True)
    assert summary.errors == 1
    with connect(settings.db_path) as conn:
        state = conn.execute("SELECT * FROM source_state WHERE source_id = 'flaky'").fetchone()
    assert state["status"] == "stale" and state["consecutive_failures"] == STALE_AFTER_FAILURES


def test_store_items_dedupes_refreshes_engagement_and_skips_old_or_unsafe_links(settings):
    src = source("hn", "C", "hn")
    first = raw("hn", "1", "Story", engagement={"points": 10})
    assert seed(settings, src, [first]) == (1, 0)
    assert seed(settings, src, [raw("hn", "1", "Story", engagement={"points": 99})]) == (0, 1)
    assert seed(settings, src, [raw("hn", "2", "Old", hours_ago=24 * 40)]) == (0, 0)
    assert seed(settings, src, [raw("hn", "3", "Bad", url="javascript:alert(1)")]) == (0, 0)
    with connect(settings.db_path) as conn:
        assert conn.execute("SELECT engagement_json FROM items").fetchone()[0] == '{"points": 99}'


def test_disabled_sources_are_skipped(settings):
    src = SourceConfig("off", "Off", "D", "x_api", 60, enabled=False)
    assert collect_due(settings, (src,)).outcomes[0].status == "skipped"


def test_sources_are_not_collected_before_they_are_due(settings, monkeypatch):
    from trendsignal.collectors import runner
    from trendsignal.collectors.base import CollectResult

    monkeypatch.setitem(runner.ADAPTERS, "rss", lambda _s, _c: CollectResult(items=()))
    src = source("lab")
    assert len(collect_due(settings, (src,)).outcomes) == 1
    assert len(collect_due(settings, (src,)).outcomes) == 0
    time.sleep(0)  # no real waiting needed: the second call is simply not due yet
