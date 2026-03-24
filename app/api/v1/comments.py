from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.dependencies import get_current_active_user, get_current_user_optional
from app.core.database import get_db
from app.models.comment import (
    COMMENT_STATUS_APPROVED,
    COMMENT_STATUS_HIDDEN,
    COMMENT_STATUS_PENDING,
    Comment,
)
from app.models.like import CommentLike
from app.models.post import Post
from app.models.user import User
from app.schemas.comment import Comment as CommentSchema, CommentCreate, CommentUpdate


router = APIRouter()


async def _get_comment(db: AsyncSession, comment_id: int) -> Comment | None:
    result = await db.execute(
        select(Comment)
        .options(
            selectinload(Comment.author),
            selectinload(Comment.likes),
            selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.likes),
        )
        .where(Comment.id == comment_id)
    )
    return result.scalars().first()


def _serialize_comment(comment: Comment) -> dict[str, Any]:
    return CommentSchema.model_validate(comment).model_dump(mode="json")


async def _refresh_post_comment_count(db: AsyncSession, post_id: int) -> None:
    result = await db.execute(
        select(func.count(Comment.id)).where(
            Comment.post_id == post_id, Comment.moderation_status == COMMENT_STATUS_APPROVED
        )
    )
    visible_count = result.scalar_one_or_none() or 0
    post = await db.get(Post, post_id)
    if post is not None:
        post.comment_count = visible_count


def _determine_initial_moderation_status(current_user: User, post: Post) -> str:
    if current_user.is_superuser or post.author_id == current_user.id:
        return COMMENT_STATUS_APPROVED
    return COMMENT_STATUS_PENDING


async def _collect_comment_subtree(
    db: AsyncSession, root_comment: Comment
) -> tuple[list[int], dict[int, int], int, int, int]:
    result = await db.execute(
        select(Comment.id, Comment.author_id, Comment.parent_id, Comment.moderation_status).where(
            Comment.post_id == root_comment.post_id
        )
    )
    rows = result.all()

    children_by_parent: dict[int | None, list[tuple[int, int, str]]] = {}
    for comment_id, author_id, parent_id, moderation_status in rows:
        children_by_parent.setdefault(parent_id, []).append((comment_id, author_id, moderation_status))

    subtree_ids: list[int] = []
    author_counts: dict[int, int] = {}
    approved_count = 0
    pending_count = 0
    hidden_count = 0
    stack: list[tuple[int, int, str]] = [(root_comment.id, root_comment.author_id, root_comment.moderation_status)]

    while stack:
        comment_id, author_id, moderation_status = stack.pop()
        subtree_ids.append(comment_id)
        author_counts[author_id] = author_counts.get(author_id, 0) + 1
        if moderation_status == COMMENT_STATUS_APPROVED:
            approved_count += 1
        elif moderation_status == COMMENT_STATUS_PENDING:
            pending_count += 1
        else:
            hidden_count += 1
        stack.extend(children_by_parent.get(comment_id, []))

    return subtree_ids, author_counts, approved_count, pending_count, hidden_count


async def _get_comment_with_post(db: AsyncSession, comment_id: int) -> Comment | None:
    result = await db.execute(
        select(Comment)
        .options(selectinload(Comment.post), selectinload(Comment.author), selectinload(Comment.likes))
        .where(Comment.id == comment_id)
    )
    return result.scalars().first()


def _can_delete_comment(current_user: User, comment: Comment, post: Post | None) -> bool:
    if current_user.is_superuser:
        return True
    if comment.author_id == current_user.id:
        return True
    return post is not None and post.author_id == current_user.id


def _can_manage_comment_visibility(current_user: User, post: Post | None) -> bool:
    if current_user.is_superuser:
        return True
    return post is not None and post.author_id == current_user.id


async def _hide_comment_subtree(
    db: AsyncSession, root_comment: Comment
) -> tuple[list[int], int, int]:
    result = await db.execute(select(Comment).where(Comment.post_id == root_comment.post_id))
    comments = result.scalars().all()
    comments_by_id = {comment.id: comment for comment in comments}
    children_by_parent: dict[int | None, list[Comment]] = {}
    for comment in comments:
        children_by_parent.setdefault(comment.parent_id, []).append(comment)

    changed_ids: list[int] = []
    approved_changed_count = 0
    pending_changed_count = 0
    stack: list[Comment] = [root_comment]
    seen: set[int] = set()

    while stack:
        comment = stack.pop()
        if comment.id in seen:
            continue
        seen.add(comment.id)

        current_comment = comments_by_id.get(comment.id, comment)
        if current_comment.moderation_status == COMMENT_STATUS_APPROVED:
            approved_changed_count += 1
        elif current_comment.moderation_status == COMMENT_STATUS_PENDING:
            pending_changed_count += 1

        if current_comment.moderation_status != COMMENT_STATUS_HIDDEN:
            current_comment.set_moderation_status(COMMENT_STATUS_HIDDEN)
            changed_ids.append(current_comment.id)

        stack.extend(children_by_parent.get(current_comment.id, []))

    return changed_ids, approved_changed_count, pending_changed_count


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
        .where(Comment.post_id == post_id, Comment.moderation_status == COMMENT_STATUS_APPROVED, Comment.parent_id.is_(None))
        .options(
            selectinload(Comment.author),
            selectinload(Comment.likes),
            selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.likes),
        )
        .order_by(Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    comments = result.scalars().all()
    for comment in comments:
        comment.replies = [reply for reply in comment.replies if reply.moderation_status == COMMENT_STATUS_APPROVED]

    if current_user and comments:
        reply_ids = [reply.id for comment in comments for reply in comment.replies]
        liked_result = await db.execute(
            select(CommentLike.comment_id).where(
                CommentLike.user_id == current_user.id,
                CommentLike.comment_id.in_([comment.id for comment in comments] + reply_ids),
            )
        )
        liked_comment_ids = set(liked_result.scalars().all())
        for comment in comments:
            comment.is_liked = comment.id in liked_comment_ids
            for reply in comment.replies:
                reply.is_liked = reply.id in liked_comment_ids

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
        if parent_comment.moderation_status != COMMENT_STATUS_APPROVED and not _can_manage_comment_visibility(current_user, post):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot reply to a non-public comment")

    moderation_status = _determine_initial_moderation_status(current_user, post)
    comment = Comment(
        content=comment_in.content,
        post_id=comment_in.post_id,
        parent_id=comment_in.parent_id,
        author_id=current_user.id,
        moderation_status=moderation_status,
        is_approved=moderation_status == COMMENT_STATUS_APPROVED,
    )
    db.add(comment)
    current_user.comment_count += 1
    await db.flush()
    await _refresh_post_comment_count(db, comment.post_id)
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
    comment = await _get_comment_with_post(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not _can_delete_comment(current_user, comment, comment.post):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    subtree_ids, author_counts, approved_count, pending_count, hidden_count = await _collect_comment_subtree(db, comment)
    for author_id, count in author_counts.items():
        author = await db.get(User, author_id)
        if author:
            author.comment_count = max(0, author.comment_count - count)
    await db.delete(comment)
    await db.flush()
    await _refresh_post_comment_count(db, comment.post_id)
    await db.commit()
    return {
        "detail": "Comment deleted successfully",
        "deleted_count": len(subtree_ids),
        "deleted_ids": subtree_ids,
        "approved_deleted_count": approved_count,
        "pending_deleted_count": pending_count,
        "hidden_deleted_count": hidden_count,
    }


@router.post("/{comment_id}/approve")
async def approve_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    comment = await _get_comment_with_post(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not _can_manage_comment_visibility(current_user, comment.post):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    previous_status = comment.moderation_status
    if previous_status == COMMENT_STATUS_APPROVED:
        refreshed = await _get_comment(db, comment_id)
        return {
            "detail": "Comment already approved",
            "comment": _serialize_comment(refreshed),
            "approved": True,
            "previous_status": previous_status,
        }

    comment.set_moderation_status(COMMENT_STATUS_APPROVED)
    await _refresh_post_comment_count(db, comment.post_id)
    await db.commit()
    refreshed = await _get_comment(db, comment_id)
    return {
        "detail": "Comment approved successfully",
        "comment": _serialize_comment(refreshed),
        "approved": True,
        "previous_status": previous_status,
    }


@router.post("/{comment_id}/hide")
async def hide_comment(
    *,
    db: AsyncSession = Depends(get_db),
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
) -> Any:
    comment = await _get_comment_with_post(db, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if not _can_manage_comment_visibility(current_user, comment.post):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    changed_ids, approved_changed_count, pending_changed_count = await _hide_comment_subtree(db, comment)
    await _refresh_post_comment_count(db, comment.post_id)
    await db.commit()
    refreshed = await _get_comment(db, comment_id)
    return {
        "detail": "Comment hidden successfully",
        "comment": _serialize_comment(refreshed),
        "approved": False,
        "changed_ids": changed_ids,
        "approved_changed_count": approved_changed_count,
        "pending_changed_count": pending_changed_count,
    }


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
    refreshed = await _get_comment(db, comment_id)
    return {"detail": "Comment liked successfully", "like_count": refreshed.like_count if refreshed else 0, "liked": True}


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
    refreshed = await _get_comment(db, comment_id)
    return {"detail": "Comment unliked successfully", "like_count": refreshed.like_count if refreshed else 0, "liked": False}


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
