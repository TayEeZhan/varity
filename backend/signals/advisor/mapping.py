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


# Assumption, not measured (tasks/plan-projects-certs.md): a skill backed only by ticked pathway tasks counts half
# in the match score until a passed project or a verified cert proves it.
LEARNED_CREDIT = 0.5


def _taxonomy_name(entry, index: Mapping[str, str]) -> str | None:
    return next((index[fold(n)] for n in (entry.name, entry.skill_id) if fold(n) in index), None)


def map_profile(profile: Profile, index: Mapping[str, str]) -> tuple[dict[str, float | None], list[str]]:
    """({taxonomy skill: years}, [intake names with no taxonomy match]). Unknown stays unmapped, never guessed."""
    held: dict[str, float | None] = {}
    unmapped: list[str] = []
    for entry in profile.skills:
        name = _taxonomy_name(entry, index)
        if name is None:
            unmapped.append(entry.name)
            continue
        years = [y for y in (held.get(name), entry.years) if y is not None]
        held[name] = max(years) if years else None
    return held, sorted(unmapped)


def skill_credit(profile: Profile, index: Mapping[str, str]) -> dict[str, float]:
    """{taxonomy skill: credit}. LEARNED_CREDIT when every evidence is a ticked pathway task, else 1.0."""
    credit: dict[str, float] = {}
    for entry in profile.skills:
        name = _taxonomy_name(entry, index)
        if name is None:
            continue
        value = LEARNED_CREDIT if all(e.method == "task_done" for e in entry.evidence) else 1.0
        credit[name] = max(credit.get(name, 0.0), value)
    return credit


def skill_levels(profile: Profile, index: Mapping[str, str]) -> dict[str, str]:
    """{taxonomy skill: strongest evidence level}: Certified > Applied > CV > Learned (ticked pathway tasks only)."""
    order = ("Learned", "CV", "Applied", "Certified")
    out: dict[str, str] = {}
    for entry in profile.skills:
        name = _taxonomy_name(entry, index)
        if name is None:
            continue
        methods = {e.method for e in entry.evidence}
        level = ("Certified" if "badge_verified" in methods else "Applied" if "jury_pass" in methods
                 else "Learned" if methods == {"task_done"} else "CV")
        if order.index(level) > order.index(out.get(name, "Learned")) or name not in out:
            out[name] = level
    return out
