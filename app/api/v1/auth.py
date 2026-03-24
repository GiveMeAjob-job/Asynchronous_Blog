from datetime import datetime, timedelta
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    clear_auth_cookies,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    get_password_hash,
    set_auth_cookies,
    verify_password,
)
from app.models.user import User
from app.schemas.user import EmailSchema, PasswordResetSchema, Token, User as UserSchema, UserCreate
from app.tasks.email import send_email


router = APIRouter()
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


def _require_email_delivery(feature_name: str) -> None:
    if not settings.mail_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"当前未配置邮件服务，暂时无法使用{feature_name}",
        )


def _issue_auth_tokens(user: User, remember_me: bool = False) -> tuple[str, str, int | None]:
    access_token = create_access_token(
        user.id,
        token_version=user.token_version,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_lifetime = (
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        if remember_me
        else timedelta(hours=settings.SESSION_REFRESH_EXPIRE_HOURS)
    )
    refresh_token = create_refresh_token(
        user.id,
        token_version=user.token_version,
        persistent=remember_me,
        expires_delta=refresh_lifetime,
    )
    refresh_max_age = int(refresh_lifetime.total_seconds()) if remember_me else None
    return access_token, refresh_token, refresh_max_age


def _build_login_response(response: Response, user: User, remember_me: bool = False) -> Token:
    access_token, refresh_token, refresh_max_age = _issue_auth_tokens(user, remember_me=remember_me)
    set_auth_cookies(
        response,
        access_token=access_token,
        refresh_token=refresh_token,
        refresh_max_age=refresh_max_age,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return Token(access_token=access_token, token_type="bearer")


async def _resolve_user_from_signed_token(
    db: AsyncSession,
    token: str,
    *,
    refresh_token: bool = False,
) -> tuple[User | None, dict[str, Any] | None]:
    try:
        payload = decode_refresh_token(token) if refresh_token else decode_access_token(token)
        user_id = int(payload.get("sub"))
        token_version = int(payload.get("ver", 0))
    except (JWTError, TypeError, ValueError):
        return None, None

    user = await db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != token_version:
        return None, payload
    return user, payload


def _extract_refresh_token(
    request: Request,
    refresh_cookie: str | None,
) -> str | None:
    authorization_header = request.headers.get("Authorization")
    if authorization_header and authorization_header.startswith("Bearer "):
        return authorization_header.split("Bearer ", 1)[1]
    return refresh_cookie or request.cookies.get(settings.REFRESH_COOKIE_NAME)


@router.post("/register", response_model=UserSchema)
async def register(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
) -> Any:
    if await _get_user_by_email(db, user_in.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该邮箱已被注册")
    if await _get_user_by_username(db, user_in.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该用户名已被使用")

    require_email_verification = bool(settings.REQUIRE_EMAIL_VERIFICATION)
    verify_token = secrets.token_urlsafe(32) if require_email_verification else None
    if require_email_verification:
        _require_email_delivery("邮箱验证")

    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        is_active=not require_email_verification,
        is_superuser=False,
        is_verified=not require_email_verification,
        email_verification_token=verify_token,
        email_verification_token_expires_at=(
            datetime.utcnow() + timedelta(hours=48) if require_email_verification else None
        ),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if require_email_verification and verify_token:
        verify_link = f"{settings.APP_BASE_URL}/api/v1/auth/verify-email/{verify_token}"
        template = templates.env.get_template("email/email_verification_email.html")
        html = template.render(user=user, verify_link=verify_link)
        send_email.delay(
            email_to=user.email,
            subject="验证您的邮箱",
            html_content=html,
            text_content="请点击链接验证您的邮箱",
        )
    return user


@router.post("/login", response_model=Token)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = Form(False),
    db: AsyncSession = Depends(get_db),
) -> Any:
    user = await _get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户未激活")
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先完成邮箱验证")
    return _build_login_response(response, user, remember_me=remember_me)


@router.post("/refresh-token", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> Token:
    current_token = _extract_refresh_token(request, refresh_cookie)
    if not current_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新令牌")

    user, payload = await _resolve_user_from_signed_token(db, current_token, refresh_token=True)
    if user is None or payload is None:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的刷新令牌")

    return _build_login_response(response, user, remember_me=bool(payload.get("persistent")))


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    refresh_cookie: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    access_token = request.cookies.get(settings.ACCESS_COOKIE_NAME)
    user: User | None = None

    if access_token:
        user, _ = await _resolve_user_from_signed_token(db, access_token, refresh_token=False)
    if user is None:
        current_refresh_token = _extract_refresh_token(request, refresh_cookie)
        if current_refresh_token:
            user, _ = await _resolve_user_from_signed_token(db, current_refresh_token, refresh_token=True)

    if user is not None:
        user.bump_token_version()
        await db.commit()

    clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return {"message": "已退出登录"}


@router.get("/verify-email/{token}")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(
            (User.email_verification_token == token)
            & (User.email_verification_token_expires_at > datetime.utcnow())
        )
    )
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="链接无效或已过期")

    user.verify_email()
    await db.commit()
    return {"message": "邮箱已验证"}


@router.post("/request-password-reset")
async def request_password_reset(
    email_in: EmailSchema,
    db: AsyncSession = Depends(get_db),
):
    _require_email_delivery("密码找回")
    user = await _get_user_by_email(db, email_in.email)
    if user is None:
        return {"message": "如果邮箱存在，将发送重置邮件"}

    reset_token = user.generate_password_reset_token()
    await db.commit()

    reset_link = f"{settings.APP_BASE_URL}/reset-password?token={reset_token}"
    template = templates.env.get_template("email/password_reset_email.html")
    html = template.render(user=user, reset_link=reset_link)
    send_email.delay(
        email_to=user.email,
        subject="密码重置",
        html_content=html,
        text_content="请点击链接重置密码",
    )
    return {"message": "如果邮箱存在，将发送重置邮件"}


@router.post("/reset-password")
async def reset_password(
    data: PasswordResetSchema,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(
            (User.password_reset_token == data.token)
            & (User.password_reset_token_expires_at > datetime.utcnow())
        )
    )
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效或过期的重置链接")

    user.hashed_password = get_password_hash(data.new_password)
    user.password_reset_token = None
    user.password_reset_token_expires_at = None
    user.bump_token_version()
    await db.commit()
    return {"message": "密码已重置"}
