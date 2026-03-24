from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_active_user, get_current_user_optional
from app.core.database import get_db
from app.models.comment import Comment
from app.models.like import CommentLike
from app.models.post import Post
from app.models.user import User
from app.schemas.comment import Comment as CommentSchema, CommentCreate, CommentUpdate


router = APIRouter()


async def _get_comment(db: AsyncSession, comment_id: int) -> Comment | None:
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.author), selectinload(Comment.likes), selectinload(Comment.replies))
        .where(Comment.id == comment_id)
    )
    return result.scalars().first()


@router.get("/post/{post_id}", response_model=list[CommentSchema])
async def read_post_comments(
    *,
    db: AsyncSession = Depends(get_db),
    post_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User | None = Depends(get_current_user_optional),
) -> Any:
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    result = await db.execute(
        select(Comment)
        .where(Comment.post_id == post_id, Comment.is_approved == True, Comment.parent_id.is_(None))
        .options(
            selectinload(Comment.author),
            selectinload(Comment.likes),
            selectinload(Comment.replies).selectinload(Comment.author),
        )
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    comments = result.scalars().all()

    if current_user and comments:
        liked_result = await db.execute(
            select(CommentLike.comment_id).where(
                CommentLike.user_id == current_user.id,
                CommentLike.comment_id.in_([comment.id for comment in comments]),
            )
        )
        liked_comment_ids = set(liked_result.scalars().all())
        for comment in comments:
            comment.is_liked = comment.id in liked_comment_ids

    return comments


@router.post("/", response_model=CommentSchema)
async def create_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_in: CommentCreate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    post = await db.get(Post, comment_in.post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if not post.allow_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Comments are disabled for this post")

    if comment_in.parent_id:
        parent_comment = await db.get(Comment, comment_in.parent_id)
        if parent_comment is None or parent_comment.post_id != comment_in.post_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid parent comment")

    comment = Comment(
        content=comment_in.content,
        post_id=comment_in.post_id,
        parent_id=comment_in.parent_id,
        author_id=current_user.id,
    )
    db.add(comment)
    post.comment_count += 1
    await db.commit()
    return await _get_comment(db, comment.id)


@router.patch("/{comment_id}", response_model=CommentSchema)
async def update_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    comment_in: CommentUpdate,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    comment.content = comment_in.content
    comment.is_edited = True
    await db.commit()
    return await _get_comment(db, comment.id)


@router.delete("/{comment_id}")
async def delete_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    post = await db.get(Post, comment.post_id)
    if post:
        post.comment_count = max(0, post.comment_count - 1)
    await db.delete(comment)
    await db.commit()
    return {"detail": "Comment deleted successfully"}


@router.post("/{comment_id}/like")
async def like_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    result = await db.execute(
        select(CommentLike).where(CommentLike.user_id == current_user.id, CommentLike.comment_id == comment_id)
    )
    existing = result.scalars().first()
    if existing is None:
        db.add(CommentLike(user_id=current_user.id, comment_id=comment_id))
        await db.commit()
    return {"detail": "Comment liked successfully"}


@router.delete("/{comment_id}/like")
async def unlike_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    result = await db.execute(
        select(CommentLike).where(CommentLike.user_id == current_user.id, CommentLike.comment_id == comment_id)
    )
    like = result.scalars().first()
    if like is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Comment not liked")

    await db.delete(like)
    await db.commit()
    return {"detail": "Comment unliked successfully"}


@router.get("/user/{user_id}", response_model=list[CommentSchema])
async def read_user_comments(
    *,
    db: AsyncSession = Depends(get_db),
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> Any:
    result = await db.execute(
        select(Comment)
        .where(Comment.author_id == user_id)
        .options(selectinload(Comment.author), selectinload(Comment.post))
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
