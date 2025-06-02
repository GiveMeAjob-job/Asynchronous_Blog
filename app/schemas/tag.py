# app/schemas/tag.py
from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re


# ---- 基础类 ---------------------------------------------------
class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=30, description="标签名称")

    @validator('name')
    def validate_name(cls, v):
        """验证标签名称格式"""
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$', v):
            raise ValueError('标签名称只能包含中英文、数字、横线和下划线')
        return v.strip().lower()  # 标签名统一小写


# ---- 请求体 ---------------------------------------------------
class TagCreate(TagBase):
    """创建标签的请求体"""
    pass


class TagUpdate(BaseModel):
    """更新标签的请求体 - 所有字段可选"""
    name: Optional[str] = Field(None, min_length=1, max_length=30)

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$', v):
                raise ValueError('标签名称只能包含中英文、数字、横线和下划线')
            return v.strip().lower()
        return v


# ---- 响应体 ---------------------------------------------------
class Tag(TagBase):
    """基础标签信息"""
    id: int

    class Config:
        from_attributes = True


class TagDetail(Tag):
    """标签详情 - 包含统计信息"""
    post_count: int = 0

    class Config:
        from_attributes = True


# ---- 标签云相关 -----------------------------------------------
class TagCloudItem(BaseModel):
    """标签云中的单个标签项"""
    name: str
    count: int
    size: int = Field(..., ge=1, le=5, description="标签大小等级 1-5")


class TagCloud(BaseModel):
    """标签云数据"""
    tags: List[TagCloudItem]
    min_count: int
    max_count: int


# ---- 内部使用 -------------------------------------------------
class TagInDB(TagBase):
    """数据库中的标签对象 - 内部使用"""
    id: int

    class Config:
        from_attributes = True


# ---- 导出列表 -------------------------------------------------
__all__ = [
    "Tag",
    "TagCreate",
    "TagUpdate",
    "TagDetail",
    "TagCloud",
    "TagCloudItem",
    "TagInDB",
]
