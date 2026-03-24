from app.main import build_absolute_url, excerpt_filter, get_recent_month_labels, markdown_filter


def test_excerpt_filter_truncates_text_cleanly():
    text = "FastAPI makes asynchronous APIs much easier to structure and document."
    excerpt = excerpt_filter(text, 30)
    assert excerpt.endswith("...")
    assert len(excerpt) <= 33


def test_markdown_filter_renders_html():
    rendered = str(markdown_filter("## Title\n\n**bold**"))
    assert "<h2" in rendered
    assert "<strong>bold</strong>" in rendered


def test_build_absolute_url_joins_relative_paths():
    assert build_absolute_url("/post/example").endswith("/post/example")


def test_build_absolute_url_keeps_absolute_url():
    url = "https://example.com/feed.xml"
    assert build_absolute_url(url) == url


def test_get_recent_month_labels_returns_ordered_labels():
    labels = get_recent_month_labels(4)
    assert len(labels) == 4
    assert labels == sorted(labels)
