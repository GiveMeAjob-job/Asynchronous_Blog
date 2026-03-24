from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from markdown import markdown as render_markdown
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.api.v1.dependencies import get_current_active_user, get_current_user_optional
from app.core.database import get_db
from app.core.security import create_post_preview_token
from app.models.comment import COMMENT_STATUS_APPROVED, COMMENT_STATUS_PENDING, Comment
from app.models.like import PostLike
from app.models.post import Post
from app.models.tag import Tag
from app.models.user import User
from app.schemas.comment import Comment as CommentSchema, CommentCreate
from app.schemas.post import Post as PostSchema, PostCreate, PostDetail, PostUpdate
from app.utils.slug import generate_slug


router = APIRouter()


class MarkdownPreviewPayload(BaseModel):
    content: str = Field("", max_length=50000)


class PostPreviewLinkResponse(BaseModel):
    post_id: int
    preview_url: str
    expires_at: datetime
    published: bool


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


async def _get_post_comment_author_counts(db: AsyncSession, post_id: int) -> dict[int, int]:
    result = await db.execute(
        select(Comment.author_id, func.count(Comment.id)).where(Comment.post_id == post_id).group_by(Comment.author_id)
    )
    return {author_id: count for author_id, count in result.all()}


async def _refresh_post_comment_count(db: AsyncSession, post_id: int) -> None:
    result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post_id, Comment.moderation_status == COMMENT_STATUS_APPROVED)
    )
    post = await db.get(Post, post_id)
    if post is not None:
        post.comment_count = result.scalar_one_or_none() or 0


def _determine_comment_status(current_user: User, post: Post) -> str:
    if current_user.is_superuser or post.author_id == current_user.id:
        return COMMENT_STATUS_APPROVED
    return COMMENT_STATUS_PENDING


def _can_manage_post(current_user: User, post: Post) -> bool:
    return current_user.is_superuser or post.author_id == current_user.id


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
        query = query.where(Post.title.ilike(search_term) | Post.content.ilike(search_term) | Post.summary.ilike(search_term))

    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().unique().all()


@router.get("/{slug}", response_model=PostDetail)
async def read_post(
    *,
    db: AsyncSession = Depends(get_db),
    slug: str,
    current_user: User | None = Depends(get_current_user_optional),
) -> Any:
    result = await db.execute(
        select(Post)
        .options(
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.likes),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.likes),
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
    visible_comments = [comment for comment in post.comments if comment.parent_id is None and comment.moderation_status == COMMENT_STATUS_APPROVED]
    for comment in visible_comments:
        comment.replies = [reply for reply in comment.replies if reply.moderation_status == COMMENT_STATUS_APPROVED]
    post.comments = visible_comments
    if current_user:
        like_result = await db.execute(
            select(PostLike.id).where(PostLike.user_id == current_user.id, PostLike.post_id == post.id)
        )
        post.is_liked_by_current_user = like_result.scalar_one_or_none() is not None
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
    set_committed_value(post, "tags", [])
    post.tags.extend(await _resolve_tags(db, post_in.tags))
    current_user.post_count += 1
    await db.commit()
    return await _load_post(db, post.id)


@router.post("/preview-markdown")
async def preview_markdown(
    *,
    payload: MarkdownPreviewPayload,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    html = render_markdown(
        payload.content or "",
        extensions=[
            "extra",
            "fenced_code",
            "tables",
            "sane_lists",
            "nl2br",
            "toc",
        ],
        output_format="html5",
    )
    return {"html": html, "requested_by": current_user.username}


@router.post("/{post_id}/preview-link", response_model=PostPreviewLinkResponse)
async def create_post_preview_link(
    *,
    request: Request,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")
    if not _can_manage_post(current_user, post):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限为此文章生成预览链接")
    if post.published:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已发布文章不需要私密预览链接")

    token, expires_at = create_post_preview_token(post.id, post.author_id, post.updated_at or post.created_at)
    preview_url = str(request.url_for("post_preview_page", post_id=post.id))
    return {
        "post_id": post.id,
        "preview_url": f"{preview_url}?token={token}",
        "expires_at": expires_at,
        "published": post.published,
    }


@router.put("/{post_id}", response_model=PostSchema)
async def update_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    post_in: PostUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await db.execute(select(Post).options(selectinload(Post.tags)).where(Post.id == post_id))
    post = result.scalars().first()
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

    author_comment_counts = await _get_post_comment_author_counts(db, post_id)
    await db.delete(post)
    current_user.post_count = max(0, current_user.post_count - 1)
    for author_id, count in author_comment_counts.items():
        author = await db.get(User, author_id)
        if author:
            author.comment_count = max(0, author.comment_count - count)
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
    if comment_in.parent_id:
        parent_comment = await db.get(Comment, comment_in.parent_id)
        if parent_comment is None or parent_comment.post_id != post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父评论不存在")
        if parent_comment.moderation_status != COMMENT_STATUS_APPROVED and current_user.id != post.author_id and not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能回复未公开的评论")

    moderation_status = _determine_comment_status(current_user, post)
    comment = Comment(
        content=comment_in.content,
        post_id=post_id,
        author_id=current_user.id,
        parent_id=comment_in.parent_id,
        moderation_status=moderation_status,
        is_approved=moderation_status == COMMENT_STATUS_APPROVED,
    )
    db.add(comment)
    current_user.comment_count += 1
    await db.flush()
    await _refresh_post_comment_count(db, post_id)
    await db.commit()

    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.author),
            selectinload(Comment.likes),
            selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.likes),
        )
        .where(Comment.id == comment.id)
    )
    return result.scalars().first()


@router.post("/{post_id}/like")
async def like_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章不存在")

    result = await db.execute(
        select(PostLike).where(PostLike.user_id == current_user.id, PostLike.post_id == post_id)
    )
    existing = result.scalars().first()
    if existing is None:
        db.add(PostLike(user_id=current_user.id, post_id=post_id))
        post.like_count += 1
        await db.commit()
    return {"detail": "文章点赞成功", "like_count": post.like_count, "liked": True}


@router.delete("/{post_id}/like")
async def unlike_post(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await db.execute(
        select(PostLike).where(PostLike.user_id == current_user.id, PostLike.post_id == post_id)
    )
    like = result.scalars().first()
    if like is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="尚未点赞该文章")

    post = await db.get(Post, post_id)
    if post:
        post.like_count = max(0, post.like_count - 1)
    await db.delete(like)
    await db.commit()
    return {"detail": "已取消点赞", "like_count": post.like_count if post else 0, "liked": False}
