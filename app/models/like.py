from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class PostLike(Base, TimestampMixin):
    __tablename__ = "post_likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)

    user = relationship("User", back_populates="post_likes")
    post = relationship("Post", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="_user_post_like_uc"),
    )

    def __repr__(self) -> str:
        return f"<PostLike(user_id={self.user_id}, post_id={self.post_id})>"


class CommentLike(Base, TimestampMixin):
    __tablename__ = "comment_likes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False)

    user = relationship("User", back_populates="comment_likes")
    comment = relationship("Comment", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("user_id", "comment_id", name="_user_comment_like_uc"),
    )

    def __repr__(self) -> str:
        return f"<CommentLike(user_id={self.user_id}, comment_id={self.comment_id})>"
