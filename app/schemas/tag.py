# app/schemas/tag.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---- 公共字段 -------------------------------------------------
class TagBase(BaseModel):
    name: str = Field(..., max_length=50, description="标签名")
    description: Optional[str] = Field(None, max_length=200, description="标签描述")


# ---- 请求体 ---------------------------------------------------
class TagCreate(TagBase):
    """POST /tags 用到"""
    pass


class TagUpdate(BaseModel):
    """PATCH /tags/{id} 用到——所有字段都可选"""
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=200)


# ---- 数据库返回 ------------------------------------------------
class TagInDBBase(TagBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # Pydantic v2 写法


class Tag(TagInDBBase):
    """返回给客户端的完整对象"""
    pass


class TagInDB(TagInDBBase):
    """内部使用，可加额外字段（如 author_id 等）"""
    pass


__all__ = [
    "Tag",
    "TagCreate",
    "TagUpdate",
    "TagInDB",
]
