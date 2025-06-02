# 修复文件：app/schemas/post.py

from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, validator, Field, ConfigDict
import re


# 定义基础schemas
class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class Category(CategoryBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    username: str
    email: str


class User(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    post_id: int


class Comment(CommentBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_id: int
    post_id: int
    # 为了避免循环引用，这里可以选择包含作者信息
    author: Optional[User] = None

    model_config = ConfigDict(from_attributes=True)


# 文章相关schemas
class PostBase(BaseModel):
    title: str
    content: str
    published: Optional[bool] = False
    category_id: Optional[int] = None


class PostCreate(PostBase):
    slug: Optional[str] = None
    tags: Optional[List[str]] = []

    @validator('slug', pre=True, always=True)
    def generate_slug(cls, v, values):
        if 'title' in values and (v is None or v == ""):
            slug = values['title'].lower()
            slug = re.sub(r'\s+', '-', slug)
            slug = re.sub(r'[^\w\-]', '', slug)
            slug = re.sub(r'-+', '-', slug)
            return slug.strip('-')
        if v is not None:
            slug = v.lower()
            slug = re.sub(r'\s+', '-', slug)
            slug = re.sub(r'[^\w\-]', '', slug)
            slug = re.sub(r'-+', '-', slug)
            return slug.strip('-')
        return v


class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None
    category_id: Optional[int] = None
    tags: Optional[List[str]] = None


class Post(PostBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_id: int
    views: Optional[int] = 0

    # 关系字段 - 使用Optional避免加载问题
    tags: Optional[List[Tag]] = []
    category: Optional[Category] = None
    author: Optional[User] = None

    model_config = ConfigDict(
        from_attributes=True,
        # 允许在序列化时忽略None值
        exclude_none=False
    )

    @validator('tags', pre=True)
    def ensure_tags_list(cls, v):
        """确保tags始终是列表"""
        if v is None:
            return []
        return v


class PostDetail(Post):
    # 继承Post的所有字段
    comments: Optional[List[Comment]] = []

    model_config = ConfigDict(
        from_attributes=True,
        exclude_none=False
    )

    @validator('comments', pre=True)
    def ensure_comments_list(cls, v):
        """确保comments始终是列表"""
        if v is None:
            return []
        return v
