from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.comment import Comment
from app.models.post import Post
from app.schemas.comment import CommentCreate, CommentUpdate


class CRUDComment(CRUDBase[Comment, CommentCreate, CommentUpdate]):
    async def create_with_author(
        self,
        db: AsyncSession,
        *,
        obj_in: CommentCreate,
        author_id: int,
    ) -> Comment:
        db_obj = Comment(**obj_in.model_dump(), author_id=author_id)
        db.add(db_obj)
        post = await db.get(Post, obj_in.post_id)
        if post is not None:
            post.comment_count += 1
        await db.commit()
        return await self.get_with_author(db, id=db_obj.id)

    async def get_with_author(self, db: AsyncSession, *, id: int) -> Optional[Comment]:
        result = await db.execute(
            select(Comment)
            .where(Comment.id == id)
            .options(selectinload(Comment.author), selectinload(Comment.likes), selectinload(Comment.replies))
        )
        return result.scalar_one_or_none()

    async def get_by_post(
        self,
        db: AsyncSession,
        *,
        post_id: int,
        skip: int = 0,
        limit: int = 20,
        only_approved: bool = True,
        parent_id: Optional[int] = None,
    ) -> list[Comment]:
        query = select(Comment).where(Comment.post_id == post_id)
        if only_approved:
            query = query.where(Comment.is_approved == True)
        if parent_id is None:
            query = query.where(Comment.parent_id.is_(None))
        else:
            query = query.where(Comment.parent_id == parent_id)

        result = await db.execute(
            query.options(
                selectinload(Comment.author),
                selectinload(Comment.likes),
                selectinload(Comment.replies).selectinload(Comment.author),
            )
            .order_by(Comment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_author(
        self,
        db: AsyncSession,
        *,
        author_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Comment]:
        result = await db.execute(
            select(Comment)
            .where(Comment.author_id == author_id)
            .options(selectinload(Comment.author), selectinload(Comment.post))
            .order_by(Comment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def update_content(self, db: AsyncSession, *, db_obj: Comment, content: str) -> Comment:
        db_obj.content = content
        db_obj.is_edited = True
        await db.commit()
        return await self.get_with_author(db, id=db_obj.id)

    async def approve(self, db: AsyncSession, *, comment_id: int) -> Optional[Comment]:
        comment = await self.get(db, id=comment_id)
        if comment is None:
            return None
        comment.is_approved = True
        await db.commit()
        return await self.get_with_author(db, id=comment.id)

    async def remove_with_update_count(self, db: AsyncSession, *, id: int) -> Optional[Comment]:
        comment = await self.get(db, id=id)
        if comment is None:
            return None
        post = await db.get(Post, comment.post_id)
        if post is not None:
            post.comment_count = max(0, post.comment_count - 1)
        await db.delete(comment)
        await db.commit()
        return comment


comment = CRUDComment(Comment)
