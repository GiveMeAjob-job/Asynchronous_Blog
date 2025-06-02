# app/api/v1/dependencies.py

from typing import Optional, Any
from fastapi import Depends, HTTPException, status, Request, Cookie  # 确保 Request 和 Cookie 已导入
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
import logging  # 导入 logging 模块

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User  # 确保 User 模型已导入
from app.schemas.user import TokenPayload  # 确保 TokenPayload 已导入

# 初始化 logger
logger = logging.getLogger(__name__)

# oauth2_scheme 主要用于从 Authorization header 获取 Bearer token。
# 我们会在 get_current_user 中手动检查 cookie 作为备选。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")


async def get_current_user(
        request: Request,  # FastAPI 会自动注入 Request 对象
        db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_to_decode: Optional[str] = None
    authorization_header: Optional[str] = request.headers.get("Authorization")

    if authorization_header and authorization_header.startswith("Bearer "):
        token_to_decode = authorization_header.split("Bearer ")[1]
    else:
        # 如果 Header 中没有，则尝试从名为 "access_token" 的 cookie 中获取
        token_to_decode = request.cookies.get("access_token")

    if token_to_decode is None:
        logger.info("No token found in Authorization header or access_token cookie for get_current_user.")
        raise credentials_exception

    try:
        payload = jwt.decode(
            token_to_decode, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id_from_token: Optional[str] = payload.get("sub")

        if user_id_from_token is None:
            logger.warning("Token 'sub' (user ID) claim is missing.")
            raise JWTError("Invalid token: sub claim missing")

        try:
            user_id_as_int = int(user_id_from_token)
        except ValueError:
            logger.error(f"Invalid user ID format in token 'sub': '{user_id_from_token}'")
            raise JWTError("Invalid token: sub claim is not a valid integer")

        token_data = TokenPayload(sub=user_id_as_int)

    except JWTError as e:
        logger.error(f"JWT processing error in get_current_user: {str(e)}")
        raise credentials_exception

    user = await db.get(User, token_data.sub)
    if user is None:
        logger.warning(f"User not found for ID: {token_data.sub}")
        raise credentials_exception

    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        logger.warning(f"User '{current_user.username}' (ID: {current_user.id}) is not active.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户未激活")
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_active_user)) -> User:
    """获取当前超级用户"""
    if not current_user.is_superuser:
        logger.warning(f"User '{current_user.username}' (ID: {current_user.id}) is not a superuser.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足"
        )
    return current_user
