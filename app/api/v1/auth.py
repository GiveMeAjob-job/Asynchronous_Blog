from datetime import timedelta, datetime
from typing import Any
import secrets
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer



# 导入相关模块
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import (
    User as UserSchema,
    UserCreate,
    Token,
    EmailSchema,
    PasswordResetSchema,
)
from app.tasks.email import send_email
from fastapi.templating import Jinja2Templates
import logging


router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")
templates = Jinja2Templates(directory="app/templates")

async def login(
        db: AsyncSession = Depends(get_db),
        form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """用户登录"""
    # 检查用户是否存在
    query = select(User).where(User.email == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户未激活")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "token_type": "bearer",
    }

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@router.post("/register", response_model=UserSchema)
async def register(
        *,
        db: AsyncSession = Depends(get_db),
        user_in: UserCreate,
) -> Any:
    logger.info(f"Received: {user_in}")
    """用户注册"""
    # 检查邮箱是否已存在
    query = select(User).where(User.email == user_in.email)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邮箱已被注册",
        )

    # 检查用户名是否已存在
    query = select(User).where(User.username == user_in.username)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用",
        )

    # 创建新用户并生成验证 token
    verify_token = secrets.token_urlsafe(32)
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        is_active=False,
        is_superuser=user_in.is_superuser,
        email_verification_token=verify_token,
        email_verification_token_expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    verify_link = f"http://localhost:8000/api/v1/auth/verify-email/{verify_token}"
    template = templates.env.get_template("email/email_verification_email.html")
    html = template.render(user=user, verify_link=verify_link)
    send_email.delay(
        email_to=user.email,
        subject="验证您的邮箱",
        html_content=html,
        text_content="请点击链接验证您的邮箱",
    )

    return user


@router.post("/refresh-token", response_model=Token)
async def refresh_token(
        current_token: str = Depends(oauth2_scheme),
        db: AsyncSession = Depends(get_db)
):
    try:
        payload = jwt.decode(
            current_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            options={"verify_exp": False}
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的令牌")

        # 验证用户存在
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        # 创建新令牌
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            user.id, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的令牌")


@router.post("/login", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """用户登录"""
    # 检查用户是否存在
    query = select(User).where(User.email == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户未激活")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/verify-email/{token}")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    query = select(User).where(
        (User.email_verification_token == token) &
        (User.email_verification_token_expires_at > datetime.utcnow())
    )
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="链接无效或已过期")

    user.is_active = True
    user.email_verification_token = None
    user.email_verification_token_expires_at = None
    await db.commit()
    return {"message": "邮箱已验证"}


@router.post("/request-password-reset")
async def request_password_reset(
    email_in: EmailSchema,
    db: AsyncSession = Depends(get_db),
):
    query = select(User).where(User.email == email_in.email)
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        return {"message": "如果邮箱存在，将发送重置邮件"}

    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_token_expires_at = datetime.utcnow() + timedelta(hours=2)
    await db.commit()

    reset_link = f"http://localhost:8000/reset-password?token={reset_token}"
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
    query = select(User).where(
        (User.password_reset_token == data.token) &
        (User.password_reset_token_expires_at > datetime.utcnow())
    )
    result = await db.execute(query)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="无效或过期的重置链接")

    user.hashed_password = get_password_hash(data.new_password)
    user.password_reset_token = None
    user.password_reset_token_expires_at = None
    await db.commit()
    return {"message": "密码已重置"}
