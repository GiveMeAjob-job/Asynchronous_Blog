# app/api/v1/tags.py
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cache import cache_key_wrapper, invalidate_cache_pattern
from app.api.v1.dependencies import get_current_active_user, get_current_superuser
from app.models import import_all
from app.schemas.tag import (
    Tag as TagSchema,
    TagCreate,
    TagUpdate,
    TagDetail,
    TagCloud
)

router = APIRouter()

User, Category, Tag, Post, post_tag, Comment = import_all()


@router.get("/", response_model=List[TagDetail])
@cache_key_wrapper("tags:list", expire=3600)
async def read_tags(
        db: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, le=1000),
        search: Optional[str] = None,
        order_by: str = Query("name", regex="^(name|post_count|created_at)$")
) -> List[TagDetail]:
    """
    获取标签列表，包含每个标签的文章数量
    """
    # 基础查询
    query = select(
        Tag,
        func.count(Post.id).label('post_count')
    ).outerjoin(
        post_tag,
        Tag.id == post_tag.c.tag_id
    ).outerjoin(
        Post,
        and_(
            post_tag.c.post_id == Post.id,
            Post.published == True
        )
    ).group_by(Tag.id)

    # 搜索
    if search:
        query = query.where(Tag.name.ilike(f"%{search}%"))

    # 排序
    if order_by == "name":
        query = query.order_by(Tag.name)
    elif order_by == "post_count":
        query = query.order_by(func.count(Post.id).desc())

    # 分页
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    tags = []

    for tag, post_count in result:
        tag_dict = {
            "id": tag.id,
            "name": tag.name,
            "post_count": post_count
        }
        tags.append(tag_dict)

    return tags


@router.get("/cloud", response_model=TagCloud)
@cache_key_wrapper("tags:cloud", expire=1800)
async def get_tag_cloud(
        db: AsyncSession = Depends(get_db),
        limit: int = Query(50, le=100, description="返回的标签数量")
) -> TagCloud:
    """
    获取标签云数据，根据文章数量计算标签权重
    """
    # 查询标签及其文章数
    query = select(
        Tag.name,
        func.count(Post.id).label('count')
    ).join(
        post_tag,
        Tag.id == post_tag.c.tag_id
    ).join(
        Post,
        and_(
            post_tag.c.post_id == Post.id,
            Post.published == True
        )
    ).group_by(Tag.id, Tag.name).order_by(
        func.count(Post.id).desc()
    ).limit(limit)

    result = await db.execute(query)
    tags_data = result.all()

    if not tags_data:
        return {"tags": [], "min_count": 0, "max_count": 0}

    # 计算权重
    counts = [count for _, count in tags_data]
    min_count = min(counts)
    max_count = max(counts)

    # 构建标签云数据
    tags = []
    for name, count in tags_data:
        # 计算相对大小（1-5级）
        if max_count == min_count:
            size = 3
        else:
            size = 1 + int((count - min_count) / (max_count - min_count) * 4)

        tags.append({
            "name": name,
            "count": count,
            "size": size
        })

    return {
        "tags": tags,
        "min_count": min_count,
        "max_count": max_count
    }


@router.get("/{tag_id}", response_model=TagDetail)
@cache_key_wrapper("tags:detail", expire=1800)
async def read_tag(
        tag_id: int,
        db: AsyncSession = Depends(get_db)
) -> TagDetail:
    """
    获取标签详情
    """
    # 查询标签
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标签不存在"
        )

    # 统计文章数量
    post_count_query = select(func.count(Post.id)).select_from(
        post_tag
    ).join(
        Post,
        and_(
            post_tag.c.post_id == Post.id,
            post_tag.c.tag_id == tag_id,
            Post.published == True
        )
    )
    post_count_result = await db.execute(post_count_query)
    post_count = post_count_result.scalar_one()

    return {
        "id": tag.id,
        "name": tag.name,
        "post_count": post_count
    }


@router.get("/{tag_id}/posts", response_model=List[dict])
async def read_tag_posts(
        tag_id: int,
        db: AsyncSession = Depends(get_db),
        skip: int = Query(0, ge=0),
        limit: int = Query(10, le=100)
) -> List[dict]:
    """
    获取标签下的文章列表
    """
    # 验证标签存在
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标签不存在"
        )

    # 查询文章
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags)
    ).join(
        post_tag,
        Post.id == post_tag.c.post_id
    ).where(
        and_(
            post_tag.c.tag_id == tag_id,
            Post.published == True
        )
    ).order_by(Post.created_at.desc())

    # 分页
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    return [
        {
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "author": post.author.username,
            "category": post.category.name if post.category else None,
            "tags": [t.name for t in post.tags],
            "created_at": post.created_at
        }
        for post in posts
    ]


@router.post("/", response_model=TagSchema)
async def create_tag(
        tag_in: TagCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
) -> Tag:
    """
    创建新标签
    """
    # 检查标签是否已存在
    existing_query = select(Tag).where(
        func.lower(Tag.name) == func.lower(tag_in.name)
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该标签已存在"
        )

    # 创建标签
    tag = Tag(name=tag_in.name)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)

    # 清除缓存
    await invalidate_cache_pattern("tags:*")

    return tag


@router.put("/{tag_id}", response_model=TagSchema)
async def update_tag(
        tag_id: int,
        tag_in: TagUpdate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_superuser)
) -> Tag:
    """
    更新标签（仅管理员）
    """
    # 获取标签
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标签不存在"
        )

    # 检查新名称是否已存在
    if tag_in.name and tag_in.name != tag.name:
        existing_query = select(Tag).where(
            (func.lower(Tag.name) == func.lower(tag_in.name)) &
            (Tag.id != tag_id)
        )
        existing_result = await db.execute(existing_query)
        if existing_result.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该标签名已存在"
            )
        tag.name = tag_in.name

    await db.commit()
    await db.refresh(tag)

    # 清除缓存
    await invalidate_cache_pattern("tags:*")
    await invalidate_cache_pattern("posts:*")

    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(
        tag_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_superuser)
) -> None:
    """
    删除标签（仅管理员）
    """
    # 获取标签
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="标签不存在"
        )

    # 删除标签（关联的 post_tag 记录会自动删除）
    await db.delete(tag)
    await db.commit()

    # 清除缓存
    await invalidate_cache_pattern("tags:*")
    await invalidate_cache_pattern("posts:*")


@router.post("/batch", response_model=List[TagSchema])
async def create_tags_batch(
        tag_names: List[str] = Query(..., description="标签名称列表"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_active_user)
) -> List[Tag]:
    """
    批量创建标签，返回创建的标签列表（已存在的会被忽略）
    """
    created_tags = []

    for name in tag_names:
        # 检查是否已存在
        existing_query = select(Tag).where(
            func.lower(Tag.name) == func.lower(name.strip())
        )
        existing_result = await db.execute(existing_query)
        existing_tag = existing_result.scalars().first()

        if existing_tag:
            created_tags.append(existing_tag)
        else:
            # 创建新标签
            new_tag = Tag(name=name.strip())
            db.add(new_tag)
            created_tags.append(new_tag)

    await db.commit()

    # 刷新所有标签
    for tag in created_tags:
        await db.refresh(tag)

    # 清除缓存
    await invalidate_cache_pattern("tags:*")

    return created_tags
