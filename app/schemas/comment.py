from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBrief


class CommentBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: Optional[int] = None


class CommentCreate(CommentBase):
    post_id: int


class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class Comment(CommentBase):
    id: int
    post_id: int
    author_id: int
    is_approved: bool = True
    is_edited: bool = False
    created_at: datetime
    updated_at: datetime
    author: UserBrief
    like_count: int = 0
    reply_count: int = 0
    is_liked: bool = False
    replies: list["Comment"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CommentInDB(Comment):
    pass


Comment.model_rebuild()
