from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.category import Category
from app.schemas.comment import Comment
from app.schemas.tag import Tag
from app.schemas.user import UserBrief


def _normalize_slug(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^\w\u4e00-\u9fa5-]", "", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or None


class PostBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = Field(None, max_length=500)
    content: str = Field(..., min_length=1)
    featured_image: Optional[str] = None
    category_id: Optional[int] = None
    published: bool = False
    is_featured: bool = False
    allow_comments: bool = True
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)


class PostCreate(PostBase):
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    tags: list[str] = Field(default_factory=list)

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_slug(value)


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    summary: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    featured_image: Optional[str] = None
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    category_id: Optional[int] = None
    tags: Optional[list[str]] = None
    published: Optional[bool] = None
    is_featured: Optional[bool] = None
    allow_comments: Optional[bool] = None
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    meta_keywords: Optional[str] = Field(None, max_length=255)

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_update_slug(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_slug(value)


class PostResponse(PostBase):
    id: int
    slug: str
    author_id: int
    published_at: Optional[datetime] = None
    views: int = 0
    like_count: int = 0
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime
    author: UserBrief
    category: Optional[Category] = None
    tags: list[Tag] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PostDetailResponse(PostResponse):
    comments: list[Comment] = Field(default_factory=list)
    is_liked_by_current_user: bool = False


Post = PostResponse
PostDetail = PostDetailResponse


class PostStats(BaseModel):
    total_posts: int
    published_posts: int
    draft_posts: int
    total_views: int
    total_likes: int
    total_comments: int
