from app.models.comment import (
    COMMENT_STATUS_APPROVED,
    COMMENT_STATUS_HIDDEN,
    COMMENT_STATUS_PENDING,
    Comment,
)


def test_comment_moderation_status_helpers_stay_in_sync():
    comment = Comment(content="hello", post_id=1, author_id=1)

    comment.set_moderation_status(COMMENT_STATUS_PENDING)
    assert comment.moderation_status == COMMENT_STATUS_PENDING
    assert comment.is_pending is True
    assert comment.is_visible is False
    assert comment.is_hidden is False
    assert comment.is_approved is False

    comment.set_moderation_status(COMMENT_STATUS_APPROVED)
    assert comment.moderation_status == COMMENT_STATUS_APPROVED
    assert comment.is_pending is False
    assert comment.is_visible is True
    assert comment.is_hidden is False
    assert comment.is_approved is True

    comment.set_moderation_status(COMMENT_STATUS_HIDDEN)
    assert comment.moderation_status == COMMENT_STATUS_HIDDEN
    assert comment.is_pending is False
    assert comment.is_visible is False
    assert comment.is_hidden is True
    assert comment.is_approved is False
