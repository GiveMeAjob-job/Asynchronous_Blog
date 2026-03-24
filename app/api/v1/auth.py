from datetime import datetime, timedelta
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import EmailSchema, PasswordResetSchema, Token, User as UserSchema, UserCreate
from app.tasks.email import send_email


router = APIRouter()
logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
templates = Jinja2Templates(directory="app/templates")


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()


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

    verify_token = secrets.token_urlsafe(32)
    user = User(
        email=user_in.email,
        username=user_in.username,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        is_active=False,
        is_superuser=False,
        is_verified=False,
        email_verification_token=verify_token,
        email_verification_token_expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

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
    form_data: OAuth2PasswordRequestForm = Depends(),
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

    access_token = create_access_token(
        user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/refresh-token", response_model=Token)
async def refresh_token(
    current_token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Token:
    try:
        payload = jwt.decode(
            current_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的令牌")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或不可用")

    access_token = create_access_token(
        user.id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {"access_token": access_token, "token_type": "bearer"}


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
    await db.commit()
    return {"message": "密码已重置"}
