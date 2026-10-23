"""Map intake skill names (intake/skill_graph.json) to the engine's taxonomy names (data/taxonomy.json)."""

from __future__ import annotations

from typing import Iterable, Mapping

from intake.models import Profile
from intake.skills import fold


def taxonomy_index(taxonomy: Iterable[Mapping]) -> dict[str, str]:
    """Folded name -> taxonomy skill. Exact names win over synonyms (TypeScript stays TypeScript)."""
    taxonomy = list(taxonomy)
    index = {fold(t["skill"]): t["skill"] for t in taxonomy}
    for t in taxonomy:
        for synonym in t.get("synonyms") or ():
            index.setdefault(fold(synonym), t["skill"])
    return index


def map_profile(profile: Profile, index: Mapping[str, str]) -> tuple[dict[str, float | None], list[str]]:
    """({taxonomy skill: years}, [intake names with no taxonomy match]). Unknown stays unmapped, never guessed."""
    held: dict[str, float | None] = {}
    unmapped: list[str] = []
    for entry in profile.skills:
        name = next((index[fold(n)] for n in (entry.name, entry.skill_id) if fold(n) in index), None)
        if name is None:
            unmapped.append(entry.name)
            continue
        years = [y for y in (held.get(name), entry.years) if y is not None]
        held[name] = max(years) if years else None
    return held, sorted(unmapped)
