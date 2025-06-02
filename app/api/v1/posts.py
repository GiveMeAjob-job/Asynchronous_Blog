# 修复文件：app/api/v1/posts.py

from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.tag import Tag, post_tag
from sqlalchemy.orm import selectinload

# 导入相关模块
from app.core.database import get_db
from app.api.v1.dependencies import get_current_active_user
from app.models import import_all
from app.schemas.post import (
    Post as PostSchema,
    PostCreate,
    PostUpdate,
    PostDetail,
    Comment as CommentSchema,
    CommentCreate
)

router = APIRouter()

User, Category, Tag, Post, post_tag, Comment = import_all()


@router.get("/", response_model=List[PostSchema])
async def read_posts(
        db: AsyncSession = Depends(get_db),
        skip: int = 0,
        limit: int = 10,
        published: Optional[bool] = True,
        category_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        search: Optional[str] = None,
) -> Any:
    """获取文章列表，支持分页、筛选和搜索"""
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags)  # 预加载标签关系
    )

    # 按发布状态筛选
    if published is not None:
        query = query.where(Post.published == published)

    # 按分类筛选
    if category_id is not None:
        query = query.where(Post.category_id == category_id)

    # 按标签筛选
    if tag_name is not None:
        tag_query = select(Tag.id).where(func.lower(Tag.name) == func.lower(tag_name))
        tag_result = await db.execute(tag_query)
        tag_id = tag_result.scalars().first()

        if tag_id:
            query = query.join(post_tag).where(post_tag.c.tag_id == tag_id)

    # 搜索功能
    if search is not None:
        search_term = f"%{search}%"
        query = query.where(
            (Post.title.ilike(search_term)) |
            (Post.content.ilike(search_term))
        )

    # 分页
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    posts = result.scalars().all()

    # 确保所有关系都已加载
    for post in posts:
        # 触发关系加载以确保它们在session中
        _ = post.tags
        _ = post.author
        _ = post.category

    return posts


@router.get("/{slug}", response_model=PostDetail)
async def read_post(
        *,
        db: AsyncSession = Depends(get_db),
        slug: str,
) -> Any:
    """获取文章详情"""
    query = select(Post).options(
        selectinload(Post.comments).selectinload(Comment.author),
        selectinload(Post.tags),
        selectinload(Post.category),
        selectinload(Post.author)
    ).where(Post.slug == slug)

    result = await db.execute(query)
    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    if not post.published:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该文章尚未发布",
        )

    # 确保所有关系都已加载
    _ = post.tags
    _ = post.comments
    _ = post.category
    _ = post.author

    return post


@router.post("/", response_model=PostSchema)
async def create_post(
        *,
        db: AsyncSession = Depends(get_db),
        post_in: PostCreate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """创建文章"""
    # 检查slug是否已存在
    query = select(Post).where(Post.slug == post_in.slug)
    result = await db.execute(query)
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该slug已被使用",
        )

    # 创建文章对象
    post = Post(
        title=post_in.title,
        slug=post_in.slug,
        content=post_in.content,
        published=post_in.published,
        author_id=current_user.id,
        category_id=post_in.category_id,
    )

    # 处理标签
    if post_in.tags:
        for tag_name in post_in.tags:
            tag_name_lower = tag_name.strip().lower()
            if not tag_name_lower:
                continue

            # 检查标签是否存在
            tag_query = select(Tag).where(func.lower(Tag.name) == tag_name_lower)
            result = await db.execute(tag_query)
            tag = result.scalars().first()

            if not tag:
                # 创建新标签
                tag = Tag(name=tag_name_lower)
                db.add(tag)
                await db.flush()  # 确保获得tag.id

            post.tags.append(tag)

    db.add(post)
    await db.commit()

    # 重新查询以获取完整的关系数据
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags)
    ).where(Post.id == post.id)

    result = await db.execute(query)
    post = result.scalars().first()

    return post


@router.put("/{post_id}", response_model=PostSchema)
async def update_post(
        *,
        db: AsyncSession = Depends(get_db),
        post_id: int,
        post_in: PostUpdate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """更新文章"""
    # 查询时预加载关系
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags)
    ).where(Post.id == post_id)

    result = await db.execute(query)
    post = result.scalars().first()

    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    # 检查权限
    if post.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限修改此文章",
        )

    # 更新文章信息
    if post_in.title is not None:
        post.title = post_in.title
    if post_in.content is not None:
        post.content = post_in.content
    if post_in.published is not None:
        post.published = post_in.published
    if post_in.category_id is not None:
        post.category_id = post_in.category_id

    # 处理标签更新
    if post_in.tags is not None:
        # 清除现有标签关系
        post.tags.clear()

        # 添加新标签
        for tag_name in post_in.tags:
            tag_name_lower = tag_name.strip().lower()
            if not tag_name_lower:
                continue

            tag_query = select(Tag).where(func.lower(Tag.name) == tag_name_lower)
            result = await db.execute(tag_query)
            tag = result.scalars().first()

            if not tag:
                tag = Tag(name=tag_name_lower)
                db.add(tag)
                await db.flush()

            post.tags.append(tag)

    await db.commit()

    # 重新查询以获取完整的关系数据
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags)
    ).where(Post.id == post.id)

    result = await db.execute(query)
    post = result.scalars().first()

    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
        *,
        db: AsyncSession = Depends(get_db),
        post_id: int,
        current_user: User = Depends(get_current_active_user),
) -> None:
    """删除文章"""
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    # 检查权限
    if post.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限删除此文章",
        )

    await db.delete(post)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{post_id}/comments", response_model=CommentSchema)
async def create_comment(
        *,
        db: AsyncSession = Depends(get_db),
        post_id: int,
        comment_in: CommentCreate,
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """创建评论"""
    # 检查文章是否存在
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    if not post.published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能对未发布的文章进行评论",
        )

    # 创建评论
    comment = Comment(
        content=comment_in.content,
        post_id=post_id,
        author_id=current_user.id,
    )
    db.add(comment)
    await db.commit()

    # 重新查询以获取完整的关系数据
    query = select(Comment).options(
        selectinload(Comment.author)
    ).where(Comment.id == comment.id)

    result = await db.execute(query)
    comment = result.scalars().first()

    return comment
