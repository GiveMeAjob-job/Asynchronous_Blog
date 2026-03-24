from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


USERNAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fa5-]+$")


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)
    is_active: bool = True
    is_superuser: bool = False

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError("用户名只能包含中英文、数字、下划线和横线")
        return value.strip()


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", value):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"[0-9]", value):
            raise ValueError("密码必须包含至少一个数字")
        return value


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = Field(None, max_length=1000)
    avatar_url: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, min_length=8)

    @field_validator("username")
    @classmethod
    def validate_optional_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not USERNAME_PATTERN.match(value):
            raise ValueError("用户名只能包含中英文、数字、下划线和横线")
        return value.strip()

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.search(r"[A-Z]", value):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", value):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"[0-9]", value):
            raise ValueError("密码必须包含至少一个数字")
        return value


class UserBrief(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserResponse(UserBase):
    id: int
    is_verified: bool = False
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    post_count: int = 0
    comment_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInDB(UserResponse):
    hashed_password: str


User = UserResponse


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: Optional[int] = None


class EmailSchema(BaseModel):
    email: EmailStr


class PasswordResetSchema(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise ValueError("密码必须包含至少一个大写字母")
        if not re.search(r"[a-z]", value):
            raise ValueError("密码必须包含至少一个小写字母")
        if not re.search(r"[0-9]", value):
            raise ValueError("密码必须包含至少一个数字")
        return value
