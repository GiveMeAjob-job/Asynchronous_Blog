from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# 导入相关模块
# from app.core.database import get_db
# from app.core.security import get_password_hash
# from app.api.dependencies import get_current_active_user, get_current_superuser
# from app.models.user import User
# from app.schemas.user import User as UserSchema, UserCreate, UserUpdate

router = APIRouter()


@router.get("/", response_model=List[UserSchema])
async def read_users(
        db: AsyncSession = Depends(get_db),
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_superuser),
) -> Any:
    """获取用户列表（仅超级用户）"""
    query = select(User).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    return users


@router.get("/me", response_model=UserSchema)
async def read_user_me(
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """获取当前登录用户信息"""
    return current_user


@router.put("/me", response_model=UserSchema)
async def update_user_me(
        *,
        db: AsyncSession = Depends(get_db),
        user_in: UserUpdate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """更新当前登录用户信息"""
    # 如果要更新用户名，检查是否已存在
    if user_in.username is not None and user_in.username != current_user.username:
        query = select(User).where(User.username == user_in.username)
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该用户名已被使用",
            )
        current_user.username = user_in.username

    # 如果要更新邮箱，检查是否已存在
    if user_in.email is not None and user_in.email != current_user.email:
        query = select(User).where(User.email == user_in.email)
        result = await db.execute(query)
        if result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已被注册",
            )
        current_user.email = user_in.email

    # 如果要更新密码
    if user_in.password is not None:
        current_user.hashed_password = get_password_hash(user_in.password)

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{user_id}", response_model=UserSchema)
async def read_user(
        user_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """获取指定用户信息（需要登录）"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user
