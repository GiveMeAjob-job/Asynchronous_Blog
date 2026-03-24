from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_superuser
from app.core.cache import cache_key_wrapper, invalidate_cache_pattern
from app.core.database import get_db
from app.models.category import Category
from app.models.post import Post
from app.models.tag import Tag
from app.models.user import User
from app.schemas.category import Category as CategorySchema, CategoryCreate, CategoryDetail, CategoryUpdate
from app.utils.slug import generate_slug


router = APIRouter()


async def _build_unique_category_slug(db: AsyncSession, name: str) -> str:
    base_slug = generate_slug(name, max_length=100)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(select(Category.id).where(Category.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


@router.get("/", response_model=list[CategoryDetail])
@cache_key_wrapper("categories:list", expire=3600)
async def read_categories(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    include_empty: bool = Query(True, description="包含没有文章的分类"),
) -> list[CategoryDetail]:
    query = (
        select(Category, func.count(Post.id).label("post_count"))
        .outerjoin(Post, (Category.id == Post.category_id) & (Post.published == True))
        .group_by(Category.id)
        .offset(skip)
        .limit(limit)
    )
    if not include_empty:
        query = query.having(func.count(Post.id) > 0)

    result = await db.execute(query)
    return [
        {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "is_active": category.is_active,
            "created_at": category.created_at,
            "updated_at": category.updated_at,
            "post_count": post_count,
        }
        for category, post_count in result.all()
    ]


@router.get("/{category_id}", response_model=CategoryDetail)
@cache_key_wrapper("categories:detail", expire=1800)
async def read_category(category_id: int, db: AsyncSession = Depends(get_db)) -> CategoryDetail:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    post_count_result = await db.execute(
        select(func.count(Post.id)).where((Post.category_id == category_id) & (Post.published == True))
    )
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "is_active": category.is_active,
        "created_at": category.created_at,
        "updated_at": category.updated_at,
        "post_count": post_count_result.scalar_one() or 0,
    }


@router.get("/{category_id}/posts", response_model=list[dict])
async def read_category_posts(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, le=100),
    sort: str = Query("newest", pattern="^(newest|oldest|popular)$"),
) -> list[dict]:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.tags))
        .where((Post.category_id == category_id) & (Post.published == True))
    )
    if sort == "newest":
        query = query.order_by(Post.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(Post.created_at.asc())
    else:
        query = query.order_by(Post.views.desc())

    result = await db.execute(query.offset(skip).limit(limit))
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
            "created_at": post.created_at,
        }
        for post in posts
    ]


@router.post("/", response_model=CategorySchema)
async def create_category(
    category_in: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Category:
    result = await db.execute(select(Category).where(func.lower(Category.name) == func.lower(category_in.name)))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该分类名已存在")

    category = Category(
        name=category_in.name,
        slug=await _build_unique_category_slug(db, category_in.name),
        description=category_in.description,
        is_active=category_in.is_active,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    await invalidate_cache_pattern("categories:*")
    return category


@router.put("/{category_id}", response_model=CategorySchema)
async def update_category(
    category_id: int,
    category_in: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Category:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    if category_in.name and category_in.name != category.name:
        result = await db.execute(
            select(Category).where(
                (func.lower(Category.name) == func.lower(category_in.name)) & (Category.id != category_id)
            )
        )
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该分类名已存在")
        category.name = category_in.name
        category.slug = await _build_unique_category_slug(db, category_in.name)

    if category_in.description is not None:
        category.description = category_in.description
    if category_in.is_active is not None:
        category.is_active = category_in.is_active

    await db.commit()
    await db.refresh(category)
    await invalidate_cache_pattern("categories:*")
    await invalidate_cache_pattern("posts:*")
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    move_to_category_id: Optional[int] = Query(None, description="将文章移动到的目标分类ID"),
) -> None:
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    if move_to_category_id is not None:
        if move_to_category_id == category_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标分类不能是当前分类")
        target_category = await db.get(Category, move_to_category_id)
        if target_category is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标分类不存在")

    result = await db.execute(select(Post).where(Post.category_id == category_id))
    for post in result.scalars().all():
        post.category_id = move_to_category_id

    await db.delete(category)
    await db.commit()
    await invalidate_cache_pattern("categories:*")
    await invalidate_cache_pattern("posts:*")
