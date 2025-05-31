# app/schemas/category.py
from typing import Optional
from pydantic import BaseModel, Field, validator
import re


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)

    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\s\-_]+$', v):
            raise ValueError('分类名称只能包含中英文、数字、空格、横线和下划线')
        return v.strip()


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\s\-_]+$', v):
                raise ValueError('分类名称只能包含中英文、数字、空格、横线和下划线')
            return v.strip()
        return v


class Category(CategoryBase):
    id: int

    class Config:
        from_attributes = True


class CategoryDetail(Category):
    post_count: int = 0


# app/schemas/tag.py
from typing import Optional, List
from pydantic import BaseModel, Field, validator
import re


class TagBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=30)

    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$', v):
            raise ValueError('标签名称只能包含中英文、数字、横线和下划线')
        return v.strip().lower()  # 标签名统一小写


class TagCreate(TagBase):
    pass


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=30)

    @validator('name')
    def validate_name(cls, v):
        if v is not None:
            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9\-_]+$', v):
                raise ValueError('标签名称只能包含中英文、数字、横线和下划线')
            return v.strip().lower()
        return v


class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True


class TagDetail(Tag):
    post_count: int = 0


class TagCloudItem(BaseModel):
    name: str
    count: int
    size: int = Field(..., ge=1, le=5, description="标签大小等级 1-5")


class TagCloud(BaseModel):
    tags: List[TagCloudItem]
    min_count: int
    max_count: int
