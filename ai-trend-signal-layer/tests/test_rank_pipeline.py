"""End to end: seeded items -> features -> Jev (faked SDK transport) or formula -> rankings -> JSON/CSV."""

import csv
import io
import json
from dataclasses import replace

from trendsignal.cli import main
from trendsignal.db import connect
from trendsignal.decision.jev import JevClient
from trendsignal.jobs import load_context, run_pipeline, write_ranking_outputs
from trendsignal.output import format_table, latest_run_id, ranking_rows, to_csv
from tests.conftest import raw, seed, source
from tests.test_jev import FakeTypeSafe, response
from tests.test_pipeline import ctx_sources, seed_world


def ranker_ctx(settings, mode="formula"):
    ctx = load_context(replace(settings, ranker=mode))
    ctx.source_map.update({s.id: s for s in ctx_sources()})
    return replace(ctx, sources=ctx_sources())


def test_formula_ranking_is_stored_and_written_in_the_plan_format(settings):
    seed_world(settings)
    ctx = ranker_ctx(settings)
    _, processed = run_pipeline(ctx, collect=False, jev_factory=lambda _s: None)
    assert processed.ranked_by_formula == processed.scored == 9 and processed.run_id

    document, paths = write_ranking_outputs(ctx)
    top = document["stories"][0]
    assert document["ranked_by"] == "formula" and document["run_id"] == processed.run_id
    assert top["rank"] == 1 and "GPT-6" in top["title"] and top["tier"] == "must_know"
    assert set(top) >= {"rank", "title", "url", "sources", "tier", "tier_probs", "expected_impact", "confidence",
                        "final_score", "top_features"}
    assert top["sources"] == ["Openai News", "Hn"] and top["tier_probs"] is None
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["stories"][0]["title"] == top["title"]
    rows = list(csv.DictReader(io.StringIO(paths["csv"].read_text(encoding="utf-8"))))
    assert rows[0]["title"] == top["title"] and len(rows) == len(document["stories"])
    assert json.loads(paths["skills"].read_text(encoding="utf-8"))[0]["skill"]


def test_jev_ranks_when_selected_and_answers_are_stored(settings):
    seed_world(settings)
    ctx = ranker_ctx(settings, "jev")
    fake = FakeTypeSafe()  # every story gets the default answer: P(must_know) 0.72
    _, processed = run_pipeline(ctx, collect=False, jev_factory=lambda _s: JevClient(fake, "jev-1.13.0"))
    assert processed.ranked_by_jev == processed.scored == processed.jev_answers == 9
    assert len(fake.calls) == 9

    rows = ranking_rows(ctx.settings, ctx.source_map)
    assert all(r["ranked_by"] == "jev" and r["tier_probs"]["must_know"] == 0.72 for r in rows)
    must = [r for r in rows if r["tier"] == "must_know"]
    assert len(must) <= 5  # daily cap still applies
    superseded = next(r for r in rows if r["title"] == "vLLM v0.9.0")
    assert superseded["tier"] == "minor" and "superseded" in superseded["notes"][0]
    with connect(settings.db_path) as conn:
        run = conn.execute("SELECT items, cost_usd FROM runs WHERE job = 'jev'").fetchone()
    assert run["items"] == 9 and run["cost_usd"] > 0


def test_jev_as_second_opinion_does_not_change_the_formula_ranking(settings):
    seed_world(settings)
    ctx = ranker_ctx(settings, "formula")
    run_pipeline(ctx, collect=False, jev_factory=lambda _s: None)
    formula_order = [r["story_id"] for r in ranking_rows(ctx.settings, ctx.source_map)]
    run_pipeline(ctx, collect=False, jev_factory=lambda _s: JevClient(FakeTypeSafe(), "jev-1.13.0"))
    rows = ranking_rows(ctx.settings, ctx.source_map)
    assert [r["story_id"] for r in rows] == formula_order
    assert all(r["ranked_by"] == "formula" and r["tier_probs"] for r in rows)


def test_jev_outage_falls_back_to_the_formula_for_every_story(settings):
    import httpx2
    from typesafe_sdk import TypeSafeAuthenticationError

    seed_world(settings)
    ctx = ranker_ctx(settings, "jev")
    fake = FakeTypeSafe(TypeSafeAuthenticationError(401, {}, httpx2.Headers()))
    _, processed = run_pipeline(ctx, collect=False, jev_factory=lambda _s: JevClient(fake, "jev-1.13.0"))
    assert processed.ranked_by_formula == processed.scored and "rejected" in processed.jev_note
    assert len(fake.calls) == 1
    assert all(r["ranked_by"] == "formula" and r["jev_error"] for r in ranking_rows(ctx.settings, ctx.source_map))


def _borderline_world(settings):
    a, b = source("openai_news", "A"), source("techcrunch", "C")
    seed(settings, a, [raw("openai_news", "1", "OpenAI ships Atlas agent for coding teams",
                           text="Atlas helps teams review pull requests.", hours_ago=3)])
    seed(settings, b, [raw("techcrunch", "2", "Atlas from OpenAI wants to review your pull requests",
                           text="The new coding agent is rolling out.", hours_ago=2)])
    return a, b


def _same_story(probability):
    from typesafe_sdk import NoulAnswer, SystemOneResponse, Usage

    return SystemOneResponse(model="m", usage=Usage(input_tokens=5),
                             answers={"same_story": NoulAnswer(noul=probability)})


def test_jev_decides_borderline_pairs_the_rules_cannot(settings, weights, watchlist):
    from trendsignal.pipeline.process import run_process

    # Raise the rule thresholds so this similar-but-not-identical pair lands in the borderline band.
    strict = replace(weights, cluster_similarity=0.99, cluster_similarity_with_key_term=0.99)
    a, b = _borderline_world(settings)
    fake = FakeTypeSafe(_same_story(0.9))
    summary = run_process(settings, (a, b), strict, watchlist, jev=JevClient(fake, "m"))
    assert summary.new_stories == 1 and fake.calls[0][1].keys() == {"same_story"}
    assert fake.calls[0][0]["item_a"]["title"] and 0.25 <= fake.calls[0][0]["text_similarity"] < 0.99


def test_jev_saying_no_keeps_a_borderline_pair_apart(settings, weights, watchlist):
    from trendsignal.pipeline.process import run_process

    strict = replace(weights, cluster_similarity=0.99, cluster_similarity_with_key_term=0.99)
    a, b = _borderline_world(settings)
    summary = run_process(settings, (a, b), strict, watchlist, jev=JevClient(FakeTypeSafe(_same_story(0.1)), "m"))
    assert summary.new_stories == 2


def test_output_helpers_handle_empty_and_injection(settings):
    assert latest_run_id(settings) is None and ranking_rows(settings, {}) == []
    row = {"rank": 1, "tier": "minor", "final_score": 1.0, "ranked_by": "formula", "expected_impact": 1.0,
           "confidence": None, "tier_probs": None, "formula_score": 1.0, "title": "=HYPERLINK(\"x\")",
           "url": "https://e.x", "sources": ["S"], "top_features": []}
    assert "'=HYPERLINK" in to_csv([row])
    assert "=HYPERLINK" in format_table([row])


def test_rank_command_prints_the_table_and_writes_files(settings, capsys):
    seed_world(settings)
    assert main(["rank", "--no-collect", "--limit", "3"]) == 0
    out = capsys.readouterr().out
    assert "ranked by: formula" in out and "GPT-6" in out and "latest.csv" in out
    assert main(["rank", "--no-collect", "--format", "json", "--limit", "2"]) == 0
    assert len(json.loads(capsys.readouterr().out)["stories"]) == 2
