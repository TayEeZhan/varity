from datetime import timedelta

from trendsignal.pipeline.cluster import ClusterItem, assign_clusters
from trendsignal.pipeline.similarity import TfidfIndex, doc_text, key_terms, versions_conflict
from trendsignal.timeutil import now_utc

NOW = now_utc()
MULTI_AUTHOR = frozenset({"hn", "x"})


def item(item_id, source_id, title, *, text="", url=None, linked=None, hours_ago=1.0, author=None, story_id=None):
    return ClusterItem(id=item_id, source_id=source_id, author=author, title=title, text=text,
                       canonical_url=url or f"https://example.com/{item_id}", linked_url=linked,
                       content_hash=f"hash-{item_id}", published_at=NOW - timedelta(hours=hours_ago),
                       story_id=story_id)


def cluster(new, existing, weights):
    index = TfidfIndex(doc_text(i.title, i.text) for i in [*existing, *new])
    return assign_clusters(new, existing, index, weights, MULTI_AUTHOR)


def test_key_terms_keep_names_and_versions_but_drop_generic_words():
    terms = key_terms("Introducing Gemini 4 Argon: the new model from Google, v2.5.1")
    assert {"gemini", "argon", "google", "v2.5.1"} <= terms
    assert "introducing" not in terms and "new" not in terms


def test_versions_conflict_only_when_both_have_different_versions():
    assert versions_conflict(frozenset({"pytorch", "v2.5.0"}), frozenset({"pytorch", "v2.4.1"}))
    assert not versions_conflict(frozenset({"pytorch", "v2.5.0"}), frozenset({"pytorch", "2.5.0"}))
    assert not versions_conflict(frozenset({"pytorch"}), frozenset({"pytorch", "v2.5.0"}))


def test_hn_post_linking_to_an_official_post_joins_its_story(weights):
    official = item(1, "openai_news", "Introducing GPT-6", url="https://openai.com/index/gpt-6", story_id=10)
    hn = item(2, "hn", "OpenAI launches GPT-6", url="https://openai.com/index/gpt-6")
    assert cluster([hn], [official], weights)[2].story_id == 10


def test_social_post_with_linked_url_joins_the_story(weights):
    official = item(1, "deepmind", "Gemini 4 Argon", url="https://deepmind.google/gemini-4", story_id=7)
    post = item(2, "x", "wow", linked="https://deepmind.google/gemini-4", author="someone")
    assert cluster([post], [official], weights)[2].story_id == 7


def test_same_announcement_from_two_blogs_merges_by_similarity(weights):
    a = item(1, "deepmind_blog", "Gemini 4 Argon: Built to solve your hardest problems",
             text="Gemini 4 Argon is our most capable model for reasoning and coding.")
    b = item(2, "google_ai_blog", "Gemini 4 Argon: Built to solve your hardest problems",
             text="Today we are releasing Gemini 4 Argon, our most capable model.")
    result = cluster([a, b], [], weights)
    assert result[1] == result[2]


def test_different_releases_of_one_tool_stay_separate(weights):
    a = item(1, "hn", "PyTorch v2.5.0 released", author="a")
    b = item(2, "techcrunch", "PyTorch v2.4.1 released", author="b")
    result = cluster([a, b], [], weights)
    assert result[1] != result[2]


def test_items_from_one_feed_never_merge(weights):
    a = item(1, "gh_vllm", "vLLM v0.9.0")
    b = item(2, "gh_vllm", "vLLM v0.9.0")
    result = cluster([a, b], [], weights)
    assert result[1] != result[2]


def test_unrelated_items_get_their_own_stories(weights):
    a = item(1, "hn", "Rust 2.0 compiler roadmap", author="a")
    b = item(2, "techcrunch", "Startup raises funding for robot kitchens")
    result = cluster([a, b], [], weights)
    assert result[1] != result[2]
    assert result[1].new_group is not None and result[2].new_group is not None


def test_items_outside_the_time_window_do_not_merge(weights):
    old = item(1, "deepmind_blog", "Gemini 4 Argon launch", hours_ago=200, story_id=3)
    new = item(2, "google_ai_blog", "Gemini 4 Argon launch", hours_ago=1)
    assert cluster([new], [old], weights)[2].story_id is None
