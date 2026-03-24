from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$", value):
            raise ValueError("标签名称只能包含中英文、数字、横线和下划线")
        return value.strip().lower()


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$", value):
            raise ValueError("标签名称只能包含中英文、数字、横线和下划线")
        return value.strip().lower()


class Tag(TagBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
    post_count: int = 0

    model_config = ConfigDict(from_attributes=True)


TagDetail = Tag


class TagCloudItem(BaseModel):
    name: str
    count: int
    size: int = Field(..., ge=1, le=5)


class TagCloud(BaseModel):
    tags: list[TagCloudItem]
    min_count: int
    max_count: int
