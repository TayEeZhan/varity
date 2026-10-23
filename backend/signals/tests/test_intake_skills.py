"""Tests for the skill graph, the canonicaliser, the expander and the keyword pass."""
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intake.keyword_pass import build_patterns, has_learning_cue, keyword_hits  # noqa: E402
from intake.pipeline import run_intake  # noqa: E402
from intake.skills import canonicalise, expand, load_graph, slugify  # noqa: E402

GOLD = json.loads((ROOT / "intake" / "samples" / "gold.json").read_text(encoding="utf-8"))["samples"]


@pytest.fixture(scope="module")
def graph():
    return load_graph()


@pytest.fixture(scope="module")
def patterns(graph):
    return build_patterns(graph)


def sample_text(name):
    sample = GOLD[name]
    return sample.get("text") or (ROOT / "intake" / "samples" / sample["file"]).read_text(encoding="utf-8")


# ---------------------------------------------------------------- graph file


def test_graph_size_and_edges(graph):
    assert 100 <= len(graph.nodes) <= 160
    for node in graph.nodes.values():
        for kind in ("requires", "part_of", "often_uses"):
            assert all(target in graph.nodes for target in getattr(node, kind)), node.id


def test_graph_rejects_a_name_used_by_two_skills(tmp_path):
    bad = {"skills": [{"id": "a", "name": "Same"}, {"id": "b", "name": "same"}]}
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="belongs to both"):
        load_graph(path)


def test_graph_rejects_an_edge_to_nowhere(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"skills": [{"id": "a", "name": "A", "requires": ["ghost"]}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown skill"):
        load_graph(path)


def test_every_keyword_pattern_compiles(patterns, graph):
    assert len(patterns) == len(graph.nodes)


# ---------------------------------------------------------------- canonicaliser


@pytest.mark.parametrize("phrase, skill_id", [
    ("Postgres", "postgresql"),
    ("python programming", "python"),
    ("Obsidian.md", "obsidian"),
    ("k8s", "kubernetes"),
    ("web building", "web-development"),
    ("C++", "cpp"),
    ("C", "c"),
    ("Node", "node-js"),
    ("momentum backtest", "momentum-backtest"),
])
def test_canonicalise(phrase, skill_id, graph):
    assert canonicalise(phrase, graph).skill_id == skill_id


def test_unknown_phrase_becomes_a_new_skill_not_a_near_match(graph):
    named = canonicalise("Obsidian Dataview", graph)
    assert named.known is False
    assert named.skill_id == "obsidian-dataview"
    assert named.name == "Obsidian Dataview"


@pytest.mark.parametrize("name, slug", [("C++", "cpp"), ("F#", "fsharp"), ("Next.js", "next-js"), ("日本語", None)])
def test_slugify(name, slug):
    result = slugify(name)
    if slug is None:
        assert result.startswith("skill-")
    else:
        assert result == slug


# ---------------------------------------------------------------- expander


def test_expand_gives_implied_and_suggested_with_rules(graph):
    found = {item.skill_id: item for item in expand(["react"], graph)}
    assert found["javascript"].kind == "requires"
    assert found["javascript"].rule == "React requires JavaScript"
    assert found["frontend-development"].kind == "part_of"
    assert {found[s].kind for s in ("html", "css", "typescript")} == {"often_uses"}


def test_expand_is_one_level_only(graph):
    found = {item.skill_id for item in expand(["nextjs"], graph)}
    assert "react" in found
    assert "javascript" not in found  # that would be React's edge, two levels away


def test_expand_never_adds_a_stated_skill_and_implied_beats_suggested(graph):
    found = {item.skill_id: item.kind for item in expand(["react", "typescript", "javascript"], graph)}
    assert "javascript" not in found and "typescript" not in found
    assert expand(["unknown-skill"], graph) == ()


# ---------------------------------------------------------------- keyword pass (LLM off)


@pytest.mark.parametrize("name", sorted(GOLD))
def test_keyword_path_matches_gold(name, graph, patterns):
    gold = GOLD[name]
    result = run_intake(sample_text(name), graph=graph, patterns=patterns, as_of=date(2026, 10, 23))
    kept = {row.skill_id for row in result.review.rows if row.basis == "stated" and row.default_keep}
    assert kept == set(gold["keyword_kept"])
    assert not kept & set(gold["must_not_keep"])
    assert {item.skill_id for item in result.review.interests} == set(gold["interests"])


def test_keyword_hits_carry_the_matched_text(patterns):
    hits = keyword_hits("Built mobile screens in React Native.", patterns)
    assert [(hit.skill_id, hit.phrase) for hit in hits] == [("react-native", "React Native")]


@pytest.mark.parametrize("line, cue", [
    ("Currently learning Rust.", True),
    ("I want to learn Kubernetes.", True),
    ("Planning to learn React next year.", True),
    ("Built machine learning models in Python.", False),
    ("SQL, familiar with Docker", False),
])
def test_learning_cue(line, cue):
    assert has_learning_cue(line) is cue
