from datetime import datetime

from app.core.security import (
    POST_PREVIEW_SCOPE,
    create_post_preview_token,
    decode_post_preview_token,
)


def test_post_preview_token_round_trip():
    updated_at = datetime(2026, 3, 24, 12, 30, 0)

    token, expires_at = create_post_preview_token(
        post_id=7,
        author_id=3,
        updated_at=updated_at,
    )
    payload = decode_post_preview_token(token)

    assert expires_at > datetime.utcnow()
    assert payload["scope"] == POST_PREVIEW_SCOPE
    assert payload["post_id"] == 7
    assert payload["author_id"] == 3
    assert payload["content_stamp"] == updated_at.isoformat()
