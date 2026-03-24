from app.main import (
    build_absolute_url,
    describe_metric_change,
    excerpt_filter,
    format_metric_value,
    get_recent_month_labels,
    markdown_filter,
    normalize_analytics_period,
)


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


def test_normalize_analytics_period_falls_back_to_default():
    assert normalize_analytics_period(90) == 90
    assert normalize_analytics_period(45) == 90


def test_format_metric_value_compacts_integer_like_floats():
    assert format_metric_value(12.0, 1) == "12"
    assert format_metric_value(12.35, 1) == "12.4"
    assert format_metric_value(18.2, 1, "%") == "18.2%"


def test_describe_metric_change_handles_flat_and_growth_states():
    assert describe_metric_change(10, 10, precision=0) == {
        "delta_text": "与上一周期持平",
        "delta_tone": "neutral",
    }
    growth = describe_metric_change(8, 4, precision=0)
    assert growth["delta_tone"] == "positive"
    assert "提升" in growth["delta_text"]
