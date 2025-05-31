# app/api/v1/categories.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cache import cache_key_wrapper, invalidate_cache_pattern
from app.api.v1.dependencies import get_current_superuser
from app.models import import_all
from app.schemas.category import (
    Category as CategorySchema,
    CategoryCreate,
    CategoryUpdate,
    CategoryDetail
)

router = APIRouter()

User, Category, Tag, Post, post_tag, Comment = import_all()


@router.get("/", response_model=List[CategoryDetail])
@cache_key_wrapper("categories:list", expire=3600)
async def read_categories(
        db: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, le=1000),
        include_empty: bool = Query(True, description="包含没有文章的分类")
) -> List[CategoryDetail]:
    """
    获取分类列表，包含每个分类的文章数量
    """
    # 查询分类及文章数量
    query = select(
        Category,
        func.count(Post.id).label('post_count')
    ).outerjoin(
        Post,
        (Category.id == Post.category_id) & (Post.published == True)
    ).group_by(Category.id)

    # 是否包含空分类
    if not include_empty:
        query = query.having(func.count(Post.id) > 0)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    categories = []

    for category, post_count in result:
        category_dict = {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "post_count": post_count
        }
        categories.append(category_dict)

    return categories


@router.get("/{category_id}", response_model=CategoryDetail)
@cache_key_wrapper("categories:detail", expire=1800)
async def read_category(
        category_id: int,
        db: AsyncSession = Depends(get_db)
) -> CategoryDetail:
    """
    获取分类详情
    """
    # 查询分类
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分类不存在"
        )

    # 统计文章数量
    post_count_query = select(func.count(Post.id)).where(
        (Post.category_id == category_id) & (Post.published == True)
    )
    post_count_result = await db.execute(post_count_query)
    post_count = post_count_result.scalar_one()

    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "post_count": post_count
    }


@router.get("/{category_id}/posts", response_model=List[dict])
async def read_category_posts(
        category_id: int,
        db: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(10, le=100),
        sort: str = Query("newest", regex="^(newest|oldest|popular)$")
) -> List[dict]:
    """
    获取分类下的文章列表
    """
    # 验证分类存在
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分类不存在"
        )

    # 构建查询
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.tags)
    ).where(
        (Post.category_id == category_id) & (Post.published == True)
    )

    # 排序
    if sort == "newest":
        query = query.order_by(Post.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(Post.created_at.asc())
    elif sort == "popular":
        query = query.order_by(Post.views.desc())

    # 分页
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    return [
        {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "content": post.content[:200] + "..." if len(post.content) > 200 else post.content,
            "author": post.author.username,
            "tags": [tag.name for tag in post.tags],
            "views": post.views,
            "created_at": post.created_at
        }
        for post in posts
    ]


@router.post("/", response_model=CategorySchema)
async def create_category(
        category_in: CategoryCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_superuser)
) -> Category:
    """
    创建新分类（仅管理员）
    """
    # 检查分类名是否已存在
    existing_query = select(Category).where(
        func.lower(Category.name) == func.lower(category_in.name)
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该分类名已存在"
        )

    # 创建分类
    category = Category(
        name=category_in.name,
        description=category_in.description
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)

    # 清除缓存
    await invalidate_cache_pattern("categories:*")

    return category


@router.put("/{category_id}", response_model=CategorySchema)
async def update_category(
        category_id: int,
        category_in: CategoryUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_superuser)
) -> Category:
    """
    更新分类（仅管理员）
    """
    # 获取分类
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分类不存在"
        )

    # 如果要更新名称，检查是否重复
    if category_in.name and category_in.name != category.name:
        existing_query = select(Category).where(
            (func.lower(Category.name) == func.lower(category_in.name)) &
            (Category.id != category_id)
        )
        existing_result = await db.execute(existing_query)
        if existing_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该分类名已存在"
            )
        category.name = category_in.name

    if category_in.description is not None:
        category.description = category_in.description

    await db.commit()
    await db.refresh(category)

    # 清除缓存
    await invalidate_cache_pattern("categories:*")
    await invalidate_cache_pattern(f"posts:*")  # 文章列表可能受影响

    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
        category_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_superuser),
        move_to_category_id: Optional[int] = Query(None, description="将文章移动到的目标分类ID")
) -> None:
    """
    删除分类（仅管理员）

    如果指定了 move_to_category_id，则将该分类下的文章移动到目标分类；
    否则，将文章的分类设置为空。
    """
    # 获取分类
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分类不存在"
        )

    # 如果指定了目标分类，验证其存在性
    if move_to_category_id:
        target_category = await db.get(Category, move_to_category_id)
        if not target_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标分类不存在"
            )
        if move_to_category_id == category_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标分类不能是当前分类"
            )

    # 更新该分类下的所有文章
    posts_query = select(Post).where(Post.category_id == category_id)
    posts_result = await db.execute(posts_query)
    posts = posts_result.scalars().all()

    for post in posts:
        post.category_id = move_to_category_id

    # 删除分类
    await db.delete(category)
    await db.commit()

    # 清除缓存
    await invalidate_cache_pattern("categories:*")
    await invalidate_cache_pattern("posts:*")
