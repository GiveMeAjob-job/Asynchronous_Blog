from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.like import PostLike
from app.models.post import Post
from app.models.tag import Tag
from app.schemas.post import PostCreate, PostUpdate
from app.utils.slug import generate_slug


class CRUDPost(CRUDBase[Post, PostCreate, PostUpdate]):
    async def _build_unique_slug(self, db: AsyncSession, title: str, requested_slug: Optional[str] = None) -> str:
        base_slug = requested_slug or generate_slug(title, max_length=200)
        slug = base_slug
        suffix = 1
        while True:
            result = await db.execute(select(Post.id).where(Post.slug == slug))
            if result.scalar_one_or_none() is None:
                return slug
            slug = f"{base_slug}-{suffix}"
            suffix += 1

    async def _resolve_tags(self, db: AsyncSession, tag_names: list[str]) -> list[Tag]:
        tags: list[Tag] = []
        for raw_name in tag_names:
            name = raw_name.strip().lower()
            if not name:
                continue
            result = await db.execute(select(Tag).where(func.lower(Tag.name) == name))
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(name=name, slug=generate_slug(name, max_length=255))
                db.add(tag)
                await db.flush()
            tags.append(tag)
        return tags

    async def create_with_author(
        self,
        db: AsyncSession,
        *,
        obj_in: PostCreate,
        author_id: int,
    ) -> Post:
        slug = await self._build_unique_slug(db, obj_in.title, obj_in.slug)
        db_obj = Post(
            **obj_in.model_dump(exclude={"tags", "slug"}),
            slug=slug,
            author_id=author_id,
            published_at=datetime.utcnow() if obj_in.published else None,
        )
        db.add(db_obj)
        await db.flush()
        db_obj.tags = await self._resolve_tags(db, obj_in.tags)
        await db.commit()
        return await self.get_by_id_with_relations(db, post_id=db_obj.id)

    async def update_with_tags(self, db: AsyncSession, *, db_obj: Post, obj_in: PostUpdate) -> Post:
        update_data = obj_in.model_dump(exclude_unset=True, exclude={"tags"})
        if "title" in update_data and "slug" not in update_data:
            db_obj.slug = await self._build_unique_slug(db, update_data["title"])
        if "slug" in update_data and update_data["slug"]:
            db_obj.slug = update_data.pop("slug")

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        if "published" in update_data and db_obj.published and db_obj.published_at is None:
            db_obj.published_at = datetime.utcnow()

        if obj_in.tags is not None:
            db_obj.tags = await self._resolve_tags(db, obj_in.tags)

        await db.commit()
        return await self.get_by_id_with_relations(db, post_id=db_obj.id)

    async def get_by_id_with_relations(self, db: AsyncSession, *, post_id: int) -> Optional[Post]:
        result = await db.execute(
            select(Post)
            .where(Post.id == post_id)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        )
        return result.scalar_one_or_none()

    async def get_by_slug(
        self,
        db: AsyncSession,
        *,
        slug: str,
        current_user_id: Optional[int] = None,
    ) -> Optional[Post]:
        result = await db.execute(
            select(Post)
            .where(Post.slug == slug)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        )
        post = result.scalar_one_or_none()
        if post and current_user_id:
            like_result = await db.execute(
                select(PostLike.id).where(PostLike.user_id == current_user_id, PostLike.post_id == post.id)
            )
            post.is_liked = like_result.scalar_one_or_none() is not None
        return post

    async def get_multi_published(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 20,
        category_id: Optional[int] = None,
        tag_id: Optional[int] = None,
        author_id: Optional[int] = None,
        search: Optional[str] = None,
        current_user_id: Optional[int] = None,
    ) -> list[Post]:
        query = (
            select(Post)
            .where(Post.published == True)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        )
        if category_id:
            query = query.where(Post.category_id == category_id)
        if tag_id:
            query = query.join(Post.tags).where(Tag.id == tag_id)
        if author_id:
            query = query.where(Post.author_id == author_id)
        if search:
            search_filter = (
                Post.title.ilike(f"%{search}%")
                | Post.content.ilike(f"%{search}%")
                | Post.summary.ilike(f"%{search}%")
            )
            query = query.where(search_filter)

        result = await db.execute(query.order_by(Post.published_at.desc().nullslast()).offset(skip).limit(limit))
        posts = result.scalars().unique().all()

        if current_user_id and posts:
            like_result = await db.execute(
                select(PostLike.post_id).where(
                    PostLike.user_id == current_user_id,
                    PostLike.post_id.in_([post.id for post in posts]),
                )
            )
            liked_post_ids = set(like_result.scalars().all())
            for post in posts:
                post.is_liked = post.id in liked_post_ids
        return posts

    async def get_featured(self, db: AsyncSession, *, limit: int = 5) -> list[Post]:
        result = await db.execute(
            select(Post)
            .where(Post.published == True, Post.is_featured == True)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
            .order_by(Post.published_at.desc().nullslast())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_popular(self, db: AsyncSession, *, limit: int = 10, days: int = 7) -> list[Post]:
        result = await db.execute(
            select(Post)
            .where(Post.published == True)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
            .order_by((Post.views + Post.like_count * 2 + Post.comment_count * 3).desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def increment_view_count(self, db: AsyncSession, *, post_id: int) -> None:
        post = await db.get(Post, post_id)
        if post is not None:
            post.views += 1
            await db.commit()

    async def get_stats(self, db: AsyncSession, *, author_id: Optional[int] = None) -> dict[str, Any]:
        query = select(Post)
        if author_id:
            query = query.where(Post.author_id == author_id)

        total_result = await db.execute(select(func.count()).select_from(query.subquery()))
        published_result = await db.execute(
            select(func.count()).select_from(query.where(Post.published == True).subquery())
        )
        draft_result = await db.execute(
            select(func.count()).select_from(query.where(Post.published == False).subquery())
        )
        stats_result = await db.execute(
            select(
                func.coalesce(func.sum(Post.views), 0),
                func.coalesce(func.sum(Post.like_count), 0),
                func.coalesce(func.sum(Post.comment_count), 0),
            ).where(Post.author_id == author_id) if author_id else select(
                func.coalesce(func.sum(Post.views), 0),
                func.coalesce(func.sum(Post.like_count), 0),
                func.coalesce(func.sum(Post.comment_count), 0),
            )
        )
        stats = stats_result.first()
        return {
            "total_posts": total_result.scalar() or 0,
            "published_posts": published_result.scalar() or 0,
            "draft_posts": draft_result.scalar() or 0,
            "total_views": stats[0] or 0,
            "total_likes": stats[1] or 0,
            "total_comments": stats[2] or 0,
        }


post = CRUDPost(Post)
