from app.utils.slug import generate_slug


def test_generate_slug_normalizes_unicode_and_spacing():
    assert generate_slug(" Café del Mar 2026 ") == "cafe-del-mar-2026"
