from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_active_user, get_current_superuser
from app.core.cache import cache_key_wrapper, invalidate_cache_pattern
from app.core.database import get_db
from app.models.post import Post
from app.models.tag import Tag, post_tag
from app.models.user import User
from app.schemas.tag import Tag as TagSchema, TagCloud, TagCreate, TagDetail, TagUpdate
from app.utils.slug import generate_slug


router = APIRouter()


async def _build_unique_tag_slug(db: AsyncSession, name: str) -> str:
    base_slug = generate_slug(name, max_length=255)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(select(Tag.id).where(Tag.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


@router.get("/", response_model=list[TagDetail])
@cache_key_wrapper("tags:list", expire=3600)
async def read_tags(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    search: str | None = None,
    order_by: str = Query("name", pattern="^(name|post_count|created_at)$"),
) -> list[TagDetail]:
    query = (
        select(Tag, func.count(Post.id).label("post_count"))
        .outerjoin(post_tag, Tag.id == post_tag.c.tag_id)
        .outerjoin(Post, and_(post_tag.c.post_id == Post.id, Post.published == True))
        .group_by(Tag.id)
        .offset(skip)
        .limit(limit)
    )
    if search:
        query = query.where(Tag.name.ilike(f"%{search}%"))
    if order_by == "name":
        query = query.order_by(Tag.name)
    elif order_by == "post_count":
        query = query.order_by(func.count(Post.id).desc())
    else:
        query = query.order_by(Tag.created_at.desc())

    result = await db.execute(query)
    return [
        {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
            "post_count": post_count,
        }
        for tag, post_count in result.all()
    ]


@router.get("/cloud", response_model=TagCloud)
@cache_key_wrapper("tags:cloud", expire=1800)
async def get_tag_cloud(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=100, description="返回的标签数量"),
) -> TagCloud:
    query = (
        select(Tag.name, func.count(Post.id).label("count"))
        .join(post_tag, Tag.id == post_tag.c.tag_id)
        .join(Post, and_(post_tag.c.post_id == Post.id, Post.published == True))
        .group_by(Tag.id, Tag.name)
        .order_by(func.count(Post.id).desc())
        .limit(limit)
    )
    result = await db.execute(query)
    tags_data = result.all()
    if not tags_data:
        return {"tags": [], "min_count": 0, "max_count": 0}

    counts = [count for _, count in tags_data]
    min_count = min(counts)
    max_count = max(counts)
    tags = []
    for name, count in tags_data:
        size = 3 if max_count == min_count else 1 + int((count - min_count) / (max_count - min_count) * 4)
        tags.append({"name": name, "count": count, "size": size})
    return {"tags": tags, "min_count": min_count, "max_count": max_count}


@router.get("/{tag_id}", response_model=TagDetail)
@cache_key_wrapper("tags:detail", expire=1800)
async def read_tag(tag_id: int, db: AsyncSession = Depends(get_db)) -> TagDetail:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")

    result = await db.execute(
        select(func.count(Post.id))
        .select_from(post_tag)
        .join(Post, and_(post_tag.c.post_id == Post.id, post_tag.c.tag_id == tag_id, Post.published == True))
    )
    return {
        "id": tag.id,
        "name": tag.name,
        "slug": tag.slug,
        "created_at": tag.created_at,
        "updated_at": tag.updated_at,
        "post_count": result.scalar_one() or 0,
    }


@router.get("/{tag_id}/posts", response_model=list[dict])
async def read_tag_posts(
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, le=100),
) -> list[dict]:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")

    result = await db.execute(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        .join(post_tag, Post.id == post_tag.c.post_id)
        .where(and_(post_tag.c.tag_id == tag_id, Post.published == True))
        .order_by(Post.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    posts = result.scalars().all()
    return [
        {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "author": post.author.username,
            "category": post.category.name if post.category else None,
            "tags": [item.name for item in post.tags],
            "created_at": post.created_at,
        }
        for post in posts
    ]


@router.post("/", response_model=TagSchema)
async def create_tag(
    tag_in: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Tag:
    result = await db.execute(select(Tag).where(func.lower(Tag.name) == func.lower(tag_in.name)))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该标签已存在")

    tag = Tag(name=tag_in.name, slug=await _build_unique_tag_slug(db, tag_in.name))
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    await invalidate_cache_pattern("tags:*")
    return tag


@router.put("/{tag_id}", response_model=TagSchema)
async def update_tag(
    tag_id: int,
    tag_in: TagUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> Tag:
    tag = await db.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")

    if tag_in.name and tag_in.name != tag.name:
        result = await db.execute(
            select(Tag).where((func.lower(Tag.name) == func.lower(tag_in.name)) & (Tag.id != tag_id))
        )
        if result.scalars().first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该标签名已存在")
        tag.name = tag_in.name
        tag.slug = await _build_unique_tag_slug(db, tag_in.name)

    await db.commit()
    await db.refresh(tag)
    await invalidate_cache_pattern("tags:*")
    await invalidate_cache_pattern("posts:*")
    return tag
