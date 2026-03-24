from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from app.models.like import PostLike, CommentLike
from app.models.post import Post
from app.models.comment import Comment


class CRUDPostLike:
    async def get(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            post_id: int
    ) -> Optional[PostLike]:
        query = select(PostLike).where(
            and_(
                PostLike.user_id == user_id,
                PostLike.post_id == post_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            post_id: int
    ) -> PostLike:
        # 检查是否已经点赞
        existing = await self.get(db, user_id=user_id, post_id=post_id)
        if existing:
            return existing

        # 创建点赞记录
        db_obj = PostLike(user_id=user_id, post_id=post_id)
        db.add(db_obj)

        # 更新文章点赞数
        await db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(like_count=Post.like_count + 1)
        )

        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            post_id: int
    ) -> bool:
        # 查找点赞记录
        like = await self.get(db, user_id=user_id, post_id=post_id)
        if not like:
            return False

        # 删除点赞记录
        await db.delete(like)

        # 更新文章点赞数
        await db.execute(
            update(Post)
            .where(Post.id == post_id)
            .values(like_count=Post.like_count - 1)
        )

        await db.commit()
        return True

    async def check_liked(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            post_id: int
    ) -> bool:
        like = await self.get(db, user_id=user_id, post_id=post_id)
        return like is not None


class CRUDCommentLike:
    async def get(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            comment_id: int
    ) -> Optional[CommentLike]:
        query = select(CommentLike).where(
            and_(
                CommentLike.user_id == user_id,
                CommentLike.comment_id == comment_id
            )
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def create(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            comment_id: int
    ) -> CommentLike:
        # 检查是否已经点赞
        existing = await self.get(db, user_id=user_id, comment_id=comment_id)
        if existing:
            return existing

        # 创建点赞记录
        db_obj = CommentLike(user_id=user_id, comment_id=comment_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            comment_id: int
    ) -> bool:
        # 查找点赞记录
        like = await self.get(db, user_id=user_id, comment_id=comment_id)
        if not like:
            return False

        # 删除点赞记录
        await db.delete(like)
        await db.commit()
        return True

    async def check_liked(
            self,
            db: AsyncSession,
            *,
            user_id: int,
            comment_id: int
    ) -> bool:
        like = await self.get(db, user_id=user_id, comment_id=comment_id)
        return like is not None


post_like = CRUDPostLike()
comment_like = CRUDCommentLike()
