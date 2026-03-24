from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


COMMENT_STATUS_PENDING = "pending"
COMMENT_STATUS_APPROVED = "approved"
COMMENT_STATUS_HIDDEN = "hidden"


class Comment(Base, TimestampMixin):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False)
    moderation_status = Column(String(20), default=COMMENT_STATUS_PENDING, nullable=False, index=True)
    is_edited = Column(Boolean, default=False, nullable=False)

    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)

    post = relationship("Post", back_populates="comments")
    author = relationship("User", back_populates="comments")
    parent = relationship("Comment", remote_side="Comment.id", backref="replies")
    likes = relationship("CommentLike", back_populates="comment", cascade="all, delete-orphan")

    @property
    def like_count(self) -> int:
        return len(self.likes)

    @property
    def reply_count(self) -> int:
        return len(self.replies)

    @property
    def is_pending(self) -> bool:
        return self.moderation_status == COMMENT_STATUS_PENDING

    @property
    def is_hidden(self) -> bool:
        return self.moderation_status == COMMENT_STATUS_HIDDEN

    @property
    def is_visible(self) -> bool:
        return self.moderation_status == COMMENT_STATUS_APPROVED

    def set_moderation_status(self, status: str) -> None:
        self.moderation_status = status
        self.is_approved = status == COMMENT_STATUS_APPROVED

    def __repr__(self) -> str:
        comment_id = self.__dict__.get("id")
        post_id = self.__dict__.get("post_id")
        moderation_status = self.__dict__.get("moderation_status")
        return (
            f"<Comment(id={comment_id}, post_id={post_id}, "
            f"moderation_status='{moderation_status}')>"
        )
