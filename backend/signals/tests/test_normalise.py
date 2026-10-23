from trendsignal.pipeline.normalise import canonical_url, clean_text, content_hash, normalise, reading_minutes
from tests.conftest import raw


def test_canonical_url_strips_tracking_www_fragment_and_trailing_slash():
    url = "http://www.Example.com/post/?utm_source=x&b=2&a=1&fbclid=abc#section"
    assert canonical_url(url) == "https://example.com/post?a=1&b=2"


def test_arxiv_versions_pdf_and_hugging_face_papers_map_to_one_url():
    expected = "https://arxiv.org/abs/2410.12345"
    assert canonical_url("https://arxiv.org/abs/2410.12345v3") == expected
    assert canonical_url("https://arxiv.org/pdf/2410.12345v1.pdf") == expected
    assert canonical_url("https://huggingface.co/papers/2410.12345") == expected


def test_clean_text_removes_tags_scripts_and_unescapes_entities():
    html = "<p>Hello&nbsp;<b>world</b></p><script>alert(1)</script><style>p{}</style> &amp; more"
    assert clean_text(html) == "Hello world & more"


def test_content_hash_ignores_case_and_punctuation():
    assert content_hash("New Model!", "Body text") == content_hash("new model", "body   text")


def test_reading_minutes_gives_papers_at_least_half_an_hour():
    assert reading_minutes("word " * 100, "research") == 30
    assert reading_minutes("word " * 2300, "product_feature") == 10
    assert reading_minutes("", "dev_tool_release") == 2


def test_normalise_maps_linked_url_from_payload():
    item = raw("bsky", "1", "Post", payload={"linked_url": "https://www.openai.com/index/x/?utm_medium=y"})
    assert normalise(item).linked_url == "https://openai.com/index/x"
