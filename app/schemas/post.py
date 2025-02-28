from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, validator
import re


class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class Category(CategoryBase):
    id: int

    class Config:
        orm_mode = True


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

    class Config:
        orm_mode = True


class PostBase(BaseModel):
    title: str
    content: str
    published: Optional[bool] = False
    category_id: Optional[int] = None


class PostCreate(PostBase):
    slug: Optional[str] = None

    @validator('slug', pre=True, always=True)
    def generate_slug(cls, v, values):
        if v is None and 'title' in values:
            # 简单的slug生成逻辑，实际项目中可能需要更复杂的处理
            return re.sub(r'[^\w\-]', '-', values['title'].lower()).strip('-')
        return v


class PostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    published: Optional[bool] = None
    category_id: Optional[int] = None


class Post(PostBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    author_id: int
    tags: List[Tag] = []

    class Config:
        orm_mode = True


class PostDetail(Post):
    comments: List[Comment] = []
    category: Optional[Category] = None
