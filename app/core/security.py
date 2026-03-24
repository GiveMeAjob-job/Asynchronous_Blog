from datetime import datetime, timedelta
from typing import Any, Optional, Union

from fastapi import Response
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

# Workaround for passlib 1.7 with bcrypt>=4.0
try:
    import bcrypt

    if not hasattr(bcrypt, "__about__"):
        # passlib expects bcrypt.__about__.__version__
        version = getattr(bcrypt, "__version__", "0")
        bcrypt.__about__ = type("about", (), {"__version__": version})
except Exception:  # pragma: no cover - bcrypt may not be installed in tests
    bcrypt = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ACCESS_TOKEN_SCOPE = "access"
REFRESH_TOKEN_SCOPE = "refresh"
POST_PREVIEW_SCOPE = "post_preview"


def _create_signed_token(
    *,
    subject: Union[str, Any],
    scope: str,
    token_version: int = 0,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    expire = datetime.utcnow() + expires_delta
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "scope": scope,
        "ver": token_version,
    }
    if extra_claims:
        to_encode.update(extra_claims)
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, Any],
    token_version: int = 0,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建JWT访问令牌"""
    return _create_signed_token(
        subject=subject,
        scope=ACCESS_TOKEN_SCOPE,
        token_version=token_version,
        expires_delta=expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    subject: Union[str, Any],
    token_version: int = 0,
    persistent: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建刷新令牌"""
    default_delta = (
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        if persistent
        else timedelta(hours=settings.SESSION_REFRESH_EXPIRE_HOURS)
    )
    return _create_signed_token(
        subject=subject,
        scope=REFRESH_TOKEN_SCOPE,
        token_version=token_version,
        expires_delta=expires_delta or default_delta,
        extra_claims={"persistent": persistent},
    )


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("scope") != ACCESS_TOKEN_SCOPE:
        raise JWTError("Invalid access token scope")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("scope") != REFRESH_TOKEN_SCOPE:
        raise JWTError("Invalid refresh token scope")
    return payload


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    refresh_max_age: Optional[int] = None,
) -> None:
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN,
        path="/",
        max_age=refresh_max_age,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


def create_post_preview_token(
    post_id: int,
    author_id: int,
    updated_at: Optional[datetime],
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, datetime]:
    expire = datetime.utcnow() + (
        expires_delta or timedelta(hours=settings.POST_PREVIEW_EXPIRE_HOURS)
    )
    content_stamp = (updated_at or datetime.utcnow()).isoformat()
    to_encode = {
        "exp": expire,
        "sub": f"post-preview:{post_id}",
        "scope": POST_PREVIEW_SCOPE,
        "post_id": post_id,
        "author_id": author_id,
        "content_stamp": content_stamp,
    }
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, expire


def decode_post_preview_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("scope") != POST_PREVIEW_SCOPE:
        raise JWTError("Invalid preview token scope")
    return payload
