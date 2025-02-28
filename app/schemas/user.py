from typing import Optional, List
from pydantic import BaseModel, EmailStr, validator
import re


class UserBase(BaseModel):
    email: EmailStr
    username: str
    is_active: Optional[bool] = True
    is_superuser: Optional[bool] = False

    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('用户名必须是字母、数字和下划线的组合')
        return v


class UserCreate(UserBase):
    username: str
    email: str
    password: str
    is_active: bool = True  # 默认激活
    is_superuser: bool = False  # 默认非超级用户

    @validator('username')
    def username_alphanumeric(cls, v):
        # 示例：允许中英文、数字、下划线、横线
        if not re.match(r'^[\u4e00-\u9fa5_a-zA-Z0-9-]+$', v):
            raise ValueError('用户名格式不正确')
        return v

    @validator('password')
    def password_strong_enough(cls, v):
        if len(v) < 8:
            raise ValueError('密码必须至少包含8个字符')
        if not re.search(r'[A-Z]', v):
            raise ValueError('密码必须包含至少一个大写字母')
        if not re.search(r'[a-z]', v):
            raise ValueError('密码必须包含至少一个小写字母')
        if not re.search(r'[0-9]', v):
            raise ValueError('密码必须包含至少一个数字')
        return v


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None

    @validator('username')
    def username_alphanumeric(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('用户名必须是字母、数字和下划线的组合')
        return v

    @validator('password')
    def password_strong_enough(cls, v):
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError('密码必须至少包含8个字符')
        if not re.search(r'[A-Z]', v):
            raise ValueError('密码必须包含至少一个大写字母')
        if not re.search(r'[a-z]', v):
            raise ValueError('密码必须包含至少一个小写字母')
        if not re.search(r'[0-9]', v):
            raise ValueError('密码必须包含至少一个数字')
        return v


class UserInDBBase(UserBase):
    id: int

    class Config:
        from_attributes = True


class User(UserInDBBase):
    pass


class UserInDB(UserInDBBase):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: Optional[int] = None
