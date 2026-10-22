"""Assign new items to stories: exact URL/hash matches first, then lexical similarity."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from trendsignal.config import Weights
from trendsignal.pipeline.similarity import TfidfIndex, cosine, doc_text, key_terms, versions_conflict
from trendsignal.timeutil import hours_between


@dataclass(frozen=True)
class ClusterItem:
    id: int
    source_id: str
    author: str | None
    title: str
    text: str
    canonical_url: str
    linked_url: str | None
    content_hash: str
    published_at: datetime
    story_id: int | None  # None for items not yet assigned


@dataclass(frozen=True)
class Target:
    """Where an item goes: an existing story, or a new group numbered within this run."""

    story_id: int | None = None
    new_group: int | None = None


@dataclass
class _Candidate:
    item: ClusterItem
    target: Target
    vector: dict[str, float]
    terms: frozenset[str]


BORDERLINE_MIN_SIMILARITY = 0.25  # below this the pair is clearly different; no need to ask Jev
SAME_STORY_MIN_PROBABILITY = 0.5

# (new item, candidate item, text similarity, shared distinctive names) -> P(same story), or None if unknown
SameStoryJudge = Callable[["ClusterItem", "ClusterItem", float, list[str]], "float | None"]


def _may_merge(a: ClusterItem, b: ClusterItem, multi_author_sources: frozenset[str]) -> bool:
    """Items from one feed are different stories, except multi-author sources (HN, social) with different authors."""
    if a.source_id != b.source_id:
        return True
    return a.source_id in multi_author_sources and bool(a.author) and a.author != b.author


def _passes(similarity: float, shared_terms: bool, weights: Weights) -> bool:
    if similarity >= weights.cluster_similarity:
        return True
    return shared_terms and similarity >= weights.cluster_similarity_with_key_term


def assign_clusters(
    new_items: list[ClusterItem],
    existing_items: list[ClusterItem],
    index: TfidfIndex,
    weights: Weights,
    multi_author_sources: frozenset[str],
    same_story: SameStoryJudge | None = None,
) -> dict[int, Target]:
    """Return item_id -> Target for every new item. No database access.
    `same_story` (Jev) is asked only about the closest borderline pair the rules cannot decide."""
    by_key: dict[str, list[_Candidate]] = {}
    candidates: list[_Candidate] = []

    def register(item: ClusterItem, target: Target) -> None:
        candidate = _Candidate(item, target, index.vector(doc_text(item.title, item.text)), key_terms(item.title))
        for key in _exact_keys(item):
            by_key.setdefault(key, []).append(candidate)
        candidates.append(candidate)

    for item in existing_items:
        if item.story_id is not None:
            register(item, Target(story_id=item.story_id))

    assignments: dict[int, Target] = {}
    next_group = 0
    for item in sorted(new_items, key=lambda i: i.published_at):
        target = _exact_match(item, by_key, weights, multi_author_sources)
        if target is None:
            target = _best_similar(item, candidates, index, weights, multi_author_sources, same_story)
        if target is None:
            target = Target(new_group=next_group)
            next_group += 1
        assignments[item.id] = target
        register(item, target)
    return assignments


def _is_homepage(url: str) -> bool:
    return urlsplit(url).path in ("", "/")


def _exact_keys(item: ClusterItem) -> list[str]:
    """Same article URL, same linked URL, or same content. Homepage links say nothing about the story."""
    urls = [u for u in (item.canonical_url, item.linked_url) if u and not _is_homepage(u)]
    return [f"url:{u}" for u in urls] + [f"hash:{item.content_hash}"]


def _compatible(item: ClusterItem, other: _Candidate, weights: Weights, multi_author_sources: frozenset[str]) -> bool:
    within_window = hours_between(min(item.published_at, other.item.published_at),
                                  max(item.published_at, other.item.published_at)) <= weights.cluster_window_hours
    return (within_window and _may_merge(item, other.item, multi_author_sources)
            and not versions_conflict(key_terms(item.title), other.terms))


def _exact_match(item: ClusterItem, by_key: dict[str, list[_Candidate]], weights: Weights,
                 multi_author_sources: frozenset[str]) -> Target | None:
    for key in _exact_keys(item):
        for candidate in by_key.get(key, []):
            if _compatible(item, candidate, weights, multi_author_sources):
                return candidate.target
    return None


def _best_similar(item: ClusterItem, candidates: list[_Candidate], index: TfidfIndex,
                  weights: Weights, multi_author_sources: frozenset[str],
                  same_story: SameStoryJudge | None = None) -> Target | None:
    vector = index.vector(doc_text(item.title, item.text))
    terms = key_terms(item.title)
    best: tuple[float, Target] | None = None
    borderline: tuple[float, _Candidate, list[str]] | None = None
    for candidate in candidates:
        if not _compatible(item, candidate, weights, multi_author_sources):
            continue
        similarity = cosine(vector, candidate.vector)
        shared_terms = sorted(t for t in terms & candidate.terms if index.is_distinctive(t))
        if _passes(similarity, bool(shared_terms), weights):
            if best is None or similarity > best[0]:
                best = (similarity, candidate.target)
        elif similarity >= BORDERLINE_MIN_SIMILARITY and (borderline is None or similarity > borderline[0]):
            borderline = (similarity, candidate, shared_terms)
    if best is not None:
        return best[1]
    if borderline is not None and same_story is not None:
        similarity, candidate, shared_terms = borderline
        probability = same_story(item, candidate.item, similarity, shared_terms)
        if probability is not None and probability >= SAME_STORY_MIN_PROBABILITY:
            return candidate.target
    return None
