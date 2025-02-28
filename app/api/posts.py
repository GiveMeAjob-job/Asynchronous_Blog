from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

# 导入相关模块
# from app.core.database import get_db
# from app.api.dependencies import get_current_active_user, get_current_superuser
# from app.models.post import Post, Comment, Category, Tag, post_tag
# from app.models.user import User
# from app.schemas.post import (
#     Post as PostSchema,
#     PostCreate,
#     PostUpdate,
#     PostDetail,
#     Comment as CommentSchema,
#     CommentCreate,
#     Tag as TagSchema,
#     TagCreate,
#     Category as CategorySchema,
#     CategoryCreate
# )

router = APIRouter()


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
        selectinload(Post.tags)
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
        selectinload(Post.category)
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

    # 创建文章
    post = Post(
        title=post_in.title,
        slug=post_in.slug,
        content=post_in.content,
        published=post_in.published,
        author_id=current_user.id,
        category_id=post_in.category_id,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
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

    await db.commit()
    await db.refresh(post)
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
        *,
        db: AsyncSession = Depends(get_db),
        post_id: int,
        current_user: User = Depends(get_current_active_user),
) -> Any:
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
    return None


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
    await db.refresh(comment)
    return comment
