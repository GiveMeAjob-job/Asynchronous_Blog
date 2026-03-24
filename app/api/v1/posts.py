from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.comment import Comment
from app.models.post import Post
from app.models.tag import Tag
from app.models.user import User
from app.schemas.comment import Comment as CommentSchema, CommentCreate
from app.schemas.post import Post as PostSchema, PostCreate, PostDetail, PostUpdate
from app.utils.slug import generate_slug


router = APIRouter()


async def _build_unique_post_slug(db: AsyncSession, title: str, requested_slug: Optional[str] = None) -> str:
    base_slug = requested_slug or generate_slug(title, max_length=200)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(select(Post.id).where(Post.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


async def _load_post(db: AsyncSession, post_id: int) -> Post:
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags),
            selectinload(Post.comments).selectinload(Comment.author),
        )
        .where(Post.id == post_id)
    )
    return result.scalars().first()


async def _resolve_tags(db: AsyncSession, tag_names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw_name in tag_names:
        name = raw_name.strip().lower()
        if not name:
            continue
        result = await db.execute(select(Tag).where(func.lower(Tag.name) == name))
        tag = result.scalars().first()
        if tag is None:
            tag = Tag(name=name, slug=await _build_unique_tag_slug(db, name))
            db.add(tag)
            await db.flush()
        tags.append(tag)
    return tags


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


@router.get("/", response_model=list[PostSchema])
async def read_posts(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 10,
    published: Optional[bool] = True,
    category_id: Optional[int] = None,
    tag_name: Optional[str] = None,
    search: Optional[str] = None,
) -> Any:
    query = select(Post).options(
        selectinload(Post.author),
        selectinload(Post.category),
        selectinload(Post.tags),
    )

    if published is not None:
        query = query.where(Post.published == published)
    if category_id is not None:
        query = query.where(Post.category_id == category_id)
    if tag_name:
        query = query.join(Post.tags).where(func.lower(Tag.name) == tag_name.strip().lower())
    if search:
        search_term = f"%{search}%"
        query = query.where(Post.title.ilike(search_term) | Post.content.ilike(search_term))

    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().unique().all()


@router.get("/{slug}", response_model=PostDetail)
async def read_post(
    *,
    db: AsyncSession = Depends(get_db),
    slug: str,
) -> Any:
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.tags),
            selectinload(Post.category),
            selectinload(Post.author),
        )
        .where(Post.slug == slug)
    )
    post = result.scalars().first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")
    if not post.published:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该文章尚未发布")
    return post


@router.post("/", response_model=PostSchema)
async def create_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_in: PostCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    slug = await _build_unique_post_slug(db, post_in.title, post_in.slug)
    post = Post(
        title=post_in.title,
        slug=slug,
        summary=post_in.summary,
        content=post_in.content,
        featured_image=post_in.featured_image,
        category_id=post_in.category_id,
        published=post_in.published,
        published_at=datetime.utcnow() if post_in.published else None,
        is_featured=post_in.is_featured,
        allow_comments=post_in.allow_comments,
        meta_title=post_in.meta_title,
        meta_description=post_in.meta_description,
        meta_keywords=post_in.meta_keywords,
        author_id=current_user.id,
    )
    db.add(post)
    await db.flush()
    post.tags = await _resolve_tags(db, post_in.tags)
    await db.commit()
    return await _load_post(db, post.id)


@router.put("/{post_id}", response_model=PostSchema)
async def update_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    post_in: PostUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")
    if post.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限修改此文章")

    update_data = post_in.model_dump(exclude_unset=True)
    if "slug" in update_data and update_data["slug"] and update_data["slug"] != post.slug:
        result = await db.execute(select(Post.id).where(Post.slug == update_data["slug"], Post.id != post.id))
        if result.scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该 slug 已被使用")
        post.slug = update_data.pop("slug")
    elif "title" in update_data and "slug" not in update_data:
        post.slug = await _build_unique_post_slug(db, update_data["title"])

    for field in [
        "title",
        "summary",
        "content",
        "featured_image",
        "category_id",
        "published",
        "is_featured",
        "allow_comments",
        "meta_title",
        "meta_description",
        "meta_keywords",
    ]:
        if field in update_data:
            setattr(post, field, update_data[field])

    if "published" in update_data and post.published and post.published_at is None:
        post.published_at = datetime.utcnow()

    if post_in.tags is not None:
        post.tags = await _resolve_tags(db, post_in.tags)

    await db.commit()
    return await _load_post(db, post.id)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user),
) -> None:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")
    if post.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限删除此文章")

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
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")
    if not post.published:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能对未发布的文章进行评论")
    if not post.allow_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该文章已关闭评论")

    comment = Comment(
        content=comment_in.content,
        post_id=post_id,
        author_id=current_user.id,
        parent_id=comment_in.parent_id,
    )
    db.add(comment)
    post.comment_count += 1
    await db.commit()

    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author))
        .where(Comment.id == comment.id)
    )
    return result.scalars().first()
