"""Stage 6: name a phrase (canonicaliser) and add the skills behind it (expander).

The skill list is open. A phrase that matches a name or synonym in skill_graph.json joins
that skill; any other phrase becomes a new skill under its own name. Nothing is ever
forced onto the nearest known skill. The expander follows only edges written in the
graph, one level deep, so every implied skill has a rule a person can read.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from intake.models import SKILL_ID_PATTERN
from intake.normalise import clean_chars, norm

GRAPH_PATH = Path(__file__).with_name("skill_graph.json")
EDGE_KINDS = ("requires", "part_of", "often_uses")
# Implied beats suggested when two edges point at the same skill.
EDGE_STRENGTH = {"requires": 0, "part_of": 1, "often_uses": 2}
_RULE_TEXT = {"requires": "{a} requires {b}", "part_of": "{a} is part of {b}", "often_uses": "{a} often uses {b}"}
# "Python programming" names the same skill as "Python".
_DROP_SUFFIXES = (" programming", " language", " framework", " library", " skills")
_DROP_TRAILING = (".md", ".io")


@dataclass(frozen=True)
class SkillNode:
    id: str
    name: str
    category: str | None
    synonyms: tuple[str, ...] = ()
    lookup_only: tuple[str, ...] = ()
    case_sensitive: bool = False
    pattern: str | None = None
    requires: tuple[str, ...] = ()
    part_of: tuple[str, ...] = ()
    often_uses: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillGraph:
    nodes: dict[str, SkillNode]
    index: dict[str, str] = field(repr=False)  # folded name -> skill id


@dataclass(frozen=True)
class Named:
    skill_id: str
    name: str
    category: str | None
    known: bool


@dataclass(frozen=True)
class Inferred:
    skill_id: str
    name: str
    category: str | None
    kind: str  # requires | part_of | often_uses
    from_skill: str
    rule: str


def fold(phrase: str) -> str:
    """Lookup form of a phrase: cleaned, casefolded, outer punctuation removed."""
    return norm(phrase).strip(" .,;:!?()[]\"'")


def _node(raw: dict) -> SkillNode:
    return SkillNode(
        id=raw["id"],
        name=raw["name"],
        category=raw.get("category"),
        synonyms=tuple(raw.get("synonyms", ())),
        lookup_only=tuple(raw.get("lookup_only", ())),
        case_sensitive=bool(raw.get("case_sensitive", False)),
        pattern=raw.get("pattern"),
        requires=tuple(raw.get("requires", ())),
        part_of=tuple(raw.get("part_of", ())),
        often_uses=tuple(raw.get("often_uses", ())),
    )


def _validate(nodes: dict[str, SkillNode]) -> dict[str, str]:
    """Check ids and edges, and build the name index. A clash is a bug in the graph file."""
    index: dict[str, str] = {}
    for node in nodes.values():
        if not re.fullmatch(SKILL_ID_PATTERN, node.id):
            raise ValueError(f"Bad skill id: {node.id!r}")
        for kind in EDGE_KINDS:
            for target in getattr(node, kind):
                if target not in nodes or target == node.id:
                    raise ValueError(f"{node.id}.{kind} points at unknown skill {target!r}")
        for name in (node.name, *node.synonyms, *node.lookup_only):
            key = fold(name)
            if index.get(key, node.id) != node.id:
                raise ValueError(f"Name {name!r} belongs to both {index[key]} and {node.id}")
            index[key] = node.id
    return index


def load_graph(path: str | Path | None = None) -> SkillGraph:
    """Read and check skill_graph.json. The default file is read once per process."""
    if path is None:
        return _default_graph()
    return _read_graph(Path(path))


@lru_cache(maxsize=1)
def _default_graph() -> SkillGraph:
    return _read_graph(GRAPH_PATH)


def _read_graph(path: Path) -> SkillGraph:
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    nodes: dict[str, SkillNode] = {}
    for entry in raw["skills"]:
        node = _node(entry)
        if node.id in nodes:
            raise ValueError(f"Duplicate skill id: {node.id}")
        nodes[node.id] = node
    return SkillGraph(nodes=nodes, index=_validate(nodes))


def slugify(name: str) -> str:
    """Skill id for a new skill. Symbols are spelled out so "C++" and "C" stay different."""
    text = clean_chars(name).casefold().replace("++", "pp").replace("#", "sharp").replace("+", "plus")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-")
    if not slug:
        slug = "skill-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return slug


def _lookup(phrase: str, graph: SkillGraph) -> str | None:
    key = fold(phrase)
    if key in graph.index:
        return graph.index[key]
    for suffix in _DROP_SUFFIXES + _DROP_TRAILING:
        if key.endswith(suffix) and key[: -len(suffix)].strip() in graph.index:
            return graph.index[key[: -len(suffix)].strip()]
    return None


def canonicalise(phrase: str, graph: SkillGraph) -> Named:
    """Name a phrase. Unknown phrases become new skills; they are never mapped to a near match."""
    skill_id = _lookup(phrase, graph)
    if skill_id is not None:
        node = graph.nodes[skill_id]
        return Named(skill_id=node.id, name=node.name, category=node.category, known=True)
    display = re.sub(r"\s+", " ", clean_chars(phrase)).strip()[:60]
    return Named(skill_id=slugify(display), name=display, category=None, known=False)


def expand(stated_ids: Iterable[str], graph: SkillGraph) -> tuple[Inferred, ...]:
    """Skills behind the stated ones: one level, only edges in the graph, never a stated skill."""
    ordered = list(dict.fromkeys(stated_ids))
    stated = set(ordered)
    found: dict[str, Inferred] = {}
    for source_id in ordered:
        source = graph.nodes.get(source_id)
        if source is None:
            continue
        for kind in EDGE_KINDS:
            for target_id in getattr(source, kind):
                if target_id in stated:
                    continue
                current = found.get(target_id)
                if current is not None and EDGE_STRENGTH[current.kind] <= EDGE_STRENGTH[kind]:
                    continue
                target = graph.nodes[target_id]
                found[target_id] = Inferred(
                    skill_id=target_id,
                    name=target.name,
                    category=target.category,
                    kind=kind,
                    from_skill=source_id,
                    rule=_RULE_TEXT[kind].format(a=source.name, b=target.name),
                )
    return tuple(found.values())
