"""End-to-end: seeded items -> stories -> scores and tiers -> brief, with no network and no LLM."""

import json
from dataclasses import replace
from types import SimpleNamespace

from trendsignal.db import connect
from trendsignal.jobs import make_digest
from trendsignal.pipeline.process import run_process
from trendsignal.queries import feed, skill_momentum, trend_counts
from tests.conftest import fake_message, raw, seed, source

OPENAI = source("openai_news", "A")
HN = source("hn", "C", "hn")
GH = source("gh_vllm", "A", title_prefix="vLLM")


def seed_world(settings):
    seed(settings, OPENAI, [raw("openai_news", "o1", "Introducing GPT-6 for developers", url="https://openai.com/gpt-6",
                                text="GPT-6 is now available in the API for all developers.")])
    topics = ["Rust borrow checker internals", "Postgres 19 query planner", "Why SQLite is everywhere",
              "A tour of the Linux scheduler", "Kotlin coroutines explained", "Building a tiny JavaScript engine"]
    seed(settings, HN, [raw("hn", f"h{i}", topic, author=f"u{i}", engagement={"points": 60 + i}, hours_ago=10)
                        for i, topic in enumerate(topics)])
    seed(settings, HN, [raw("hn", "h-gpt", "OpenAI launches GPT-6", url="https://openai.com/gpt-6", author="z",
                            engagement={"points": 1500})])
    seed(settings, GH, [raw("gh_vllm", "r1", "vLLM v0.9.0", hours_ago=30), raw("gh_vllm", "r2", "vLLM v0.9.1", hours_ago=5)])


def ctx_sources():
    return (OPENAI, HN, GH)


def test_pipeline_clusters_scores_and_tiers(settings, weights, watchlist):
    seed_world(settings)
    summary = run_process(settings, ctx_sources(), weights, watchlist)
    assert summary.clustered_items == 10 and summary.new_stories == 9
    assert summary.enriched == 9 and summary.llm_enriched == 0 and summary.fallback_reason is None
    assert summary.ranked_by_formula == summary.scored and summary.ranked_by_jev == 0
    assert "not configured" in summary.jev_note

    views = feed(settings, {s.id: s for s in ctx_sources()})
    gpt = next(v for v in views if "GPT-6" in v.title)
    assert len(gpt.sources) == 2 and gpt.category == "model_release"
    assert gpt.tier == "must_know" and gpt.importance >= weights.must_know_threshold
    assert gpt.url == "https://openai.com/gpt-6"

    releases = {v.title: v for v in views if v.title.startswith("vLLM")}
    assert releases["vLLM v0.9.0"].tier == "minor"
    assert "superseded by a newer release" in releases["vLLM v0.9.0"].reasons

    again = run_process(settings, ctx_sources(), weights, watchlist)
    assert again.clustered_items == 0 and again.enriched == 0


def test_haiku_is_asked_only_for_unsure_categories_when_enabled(llm_settings, weights, watchlist):
    settings = replace(llm_settings, haiku_fallback=True)
    seed(settings, OPENAI, [
        raw("openai_news", "o1", "Introducing GPT-6", text="GPT-6 is now available in the API."),  # rule is sure
        raw("openai_news", "o2", "A note on our new Atlas assistant", text="Atlas is now available in the API."),
    ])
    payload = {"category": "product_feature", "entities": [{"name": "Atlas", "type": "product"}], "change_magnitude": 3,
               "magnitude_reason": "notable feature", "audience": ["backend"], "is_breaking_change": False,
               "tldr": "Atlas is available in the API.", "why_it_matters": "Try it in your app.",
               "evidence_quotes": ["Atlas is now available in the API"]}
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return fake_message(json.dumps(payload))

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    summary = run_process(settings, (OPENAI,), weights, watchlist, client_factory=lambda: client)
    assert summary.llm_enriched == 1 and summary.cost_usd > 0 and len(calls) == 1
    with connect(settings.db_path) as conn:
        rows = {r["title"]: r for r in conn.execute("SELECT title, category_source, category_confidence FROM stories")}
    assert rows["A note on our new Atlas assistant"]["category_source"] == "haiku"
    assert rows["Introducing GPT-6"]["category_source"] == "rules"
    assert rows["Introducing GPT-6"]["category_confidence"] >= 0.5


def test_haiku_is_never_called_when_the_fallback_is_off(llm_settings, weights, watchlist):
    seed(llm_settings, OPENAI, [raw("openai_news", "o2", "A note on our new Atlas assistant", text="Atlas.")])

    def explode():
        raise AssertionError("Claude must not be called")

    summary = run_process(llm_settings, (OPENAI,), weights, watchlist, client_factory=explode)
    assert summary.llm_enriched == 0 and summary.cost_usd == 0


def test_daily_digest_uses_template_without_llm(ctx, weights, watchlist):
    seed_world(ctx.settings)
    run_process(ctx.settings, ctx_sources(), weights, watchlist)
    ctx.source_map.update({s.id: s for s in ctx_sources()})
    result = make_digest(ctx, "daily", deliver=False)
    assert result.generated_by == "template" and result.verification["failed_lines"] == 0
    assert "## 🔴 Must-know" in result.body and "GPT-6" in result.body
    with connect(ctx.settings.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM digests").fetchone()[0] == 1


def llm_ctx(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    return replace(ctx, settings=replace(ctx.settings, llm_mode="auto"))


def test_digest_keeps_a_verified_editor_draft(ctx, weights, watchlist, monkeypatch):
    ctx = llm_ctx(ctx, monkeypatch)
    seed_world(ctx.settings)
    run_process(ctx.settings, ctx_sources(), weights, watchlist)
    ctx.source_map.update({s.id: s for s in ctx_sources()})
    story_id = next(v.id for v in feed(ctx.settings, ctx.source_map) if "GPT-6" in v.title)
    draft = f"# Brief\n\n## 🔴 Must-know\n\n1. **GPT-6 is out** [S{story_id}]\n   Read more [S{story_id}]\n"
    runner = SimpleNamespace(messages=SimpleNamespace(tool_runner=lambda **_: iter([fake_message(draft)])))
    client = SimpleNamespace(beta=runner)
    result = make_digest(ctx, "daily", deliver=False, client_factory=lambda: client)
    assert result.generated_by == "claude-sonnet-5-5" and "GPT-6 is out" in result.body


def test_digest_falls_back_when_the_editor_draft_fails_verification(ctx, weights, watchlist, monkeypatch):
    ctx = llm_ctx(ctx, monkeypatch)
    seed_world(ctx.settings)
    run_process(ctx.settings, ctx_sources(), weights, watchlist)
    ctx.source_map.update({s.id: s for s in ctx_sources()})
    draft = "# Brief\n\nGPT-6 has 900 trillion parameters\nAnother uncited claim\n"
    runner = SimpleNamespace(messages=SimpleNamespace(tool_runner=lambda **_: iter([fake_message(draft)])))
    result = make_digest(ctx, "daily", deliver=False, client_factory=lambda: SimpleNamespace(beta=runner))
    assert result.generated_by == "template" and "failed verification" in result.note


def test_trend_counts_and_skill_momentum(settings, weights, watchlist):
    seed_world(settings)
    run_process(settings, ctx_sources(), weights, watchlist)
    momentum = {row["skill"]: row for row in skill_momentum(settings, watchlist)}
    assert momentum["LLM serving and inference"]["this_week"] >= 1
    assert isinstance(trend_counts(settings), list)
