from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=200)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9\s\-_]+$", value):
            raise ValueError("分类名称只能包含中英文、数字、空格、横线和下划线")
        return value.strip()


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_optional_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.match(r"^[\u4e00-\u9fa5a-zA-Z0-9\s\-_]+$", value):
            raise ValueError("分类名称只能包含中英文、数字、空格、横线和下划线")
        return value.strip()


class Category(CategoryBase):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
    post_count: int = 0

    model_config = ConfigDict(from_attributes=True)


CategoryDetail = Category
