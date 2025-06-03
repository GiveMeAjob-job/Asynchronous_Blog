from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta



# 导入相关模块
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import User as UserSchema, UserCreate, Token
import logging
import secrets

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

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

    # 创建新用户
    user = User(
        email=user_in.email,
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
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


@router.post("/request-password-reset")
async def request_password_reset(
        email_data: dict,  # 应该定义一个 EmailSchema
        db: AsyncSession = Depends(get_db)
):
    """请求密码重置"""
    email = email_data.get("email")
    user = await db.execute(select(User).where(User.email == email))
    user = user.scalars().first()

    if user:
        # 生成重置token
        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        await db.commit()

        # 发送邮件 (需要实现)
        # send_password_reset_email.delay(user.email, token)

    # 总是返回成功，避免泄露邮箱是否存在
    return {"message": "如果邮箱存在，重置链接已发送"}


@router.post("/reset-password")
async def reset_password(
        reset_data: dict,  # 应该定义一个 PasswordResetSchema
        db: AsyncSession = Depends(get_db)
):
    """重置密码"""
    token = reset_data.get("token")
    new_password = reset_data.get("new_password")

    user = await db.execute(
        select(User).where(
            User.password_reset_token == token,
            User.password_reset_token_expires > datetime.utcnow()
        )
    )
    user = user.scalars().first()

    if not user:
        raise HTTPException(status_code=400, detail="无效或已过期的重置链接")

    user.hashed_password = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_token_expires = None
    await db.commit()

    return {"message": "密码已成功重置"}


@router.get("/verify-email/{token}")
async def verify_email(
        token: str,
        db: AsyncSession = Depends(get_db)
):
    """验证邮箱"""
    user = await db.execute(
        select(User).where(
            User.email_verification_token == token,
            User.email_verification_token_expires > datetime.utcnow()
        )
    )
    user = user.scalars().first()

    if not user:
        raise HTTPException(status_code=400, detail="无效或已过期的验证链接")

    user.is_active = True
    user.email_verification_token = None
    user.email_verification_token_expires = None
    await db.commit()

    return {"message": "邮箱验证成功"}

