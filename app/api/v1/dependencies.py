import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.user import TokenPayload


logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> Optional[str]:
    authorization_header = request.headers.get("Authorization")
    if authorization_header and authorization_header.startswith("Bearer "):
        return authorization_header.split("Bearer ", 1)[1]
    return request.cookies.get(settings.ACCESS_COOKIE_NAME)


async def _resolve_user(request: Request, db: AsyncSession) -> Optional[User]:
    token = _extract_token(request)
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
        token_data = TokenPayload(sub=int(payload.get("sub")))
        token_version = int(payload.get("ver", 0))
    except (JWTError, TypeError, ValueError) as exc:
        logger.warning("Failed to decode access token: %s", exc)
        return None

    user = await db.get(User, token_data.sub)
    if user is None or not user.is_active or user.token_version != token_version:
        return None
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _resolve_user(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(
    request: Request,
) -> Optional[User]:
    token = _extract_token(request)
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
        token_data = TokenPayload(sub=int(payload.get("sub")))
        token_version = int(payload.get("ver", 0))
    except (JWTError, TypeError, ValueError) as exc:
        logger.warning("Failed to decode optional access token: %s", exc)
        return None

    async with async_session() as db:
        user = await db.get(User, token_data.sub)
        if user is None or not user.is_active or user.token_version != token_version:
            return None
        return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户未激活")
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_active_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    return current_user
