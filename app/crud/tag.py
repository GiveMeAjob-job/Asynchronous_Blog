from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.post import Post
from app.models.tag import Tag, post_tag
from app.schemas.tag import TagCreate, TagUpdate
from app.utils.slug import generate_slug


class CRUDTag(CRUDBase[Tag, TagCreate, TagUpdate]):
    async def _build_unique_slug(self, db: AsyncSession, name: str) -> str:
        base_slug = generate_slug(name, max_length=255)
        slug = base_slug
        suffix = 1
        while True:
            result = await db.execute(select(Tag.id).where(Tag.slug == slug))
            if result.scalar_one_or_none() is None:
                return slug
            slug = f"{base_slug}-{suffix}"
            suffix += 1

    async def get_by_name(self, db: AsyncSession, *, name: str) -> Optional[Tag]:
        result = await db.execute(select(Tag).where(func.lower(Tag.name) == func.lower(name)))
        return result.scalar_one_or_none()

    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[Tag]:
        result = await db.execute(select(Tag).where(Tag.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, *, obj_in: TagCreate) -> Tag:
        db_obj = Tag(name=obj_in.name, slug=await self._build_unique_slug(db, obj_in.name))
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_or_create_by_name(self, db: AsyncSession, *, name: str) -> Tag:
        tag = await self.get_by_name(db, name=name)
        if tag is not None:
            return tag
        return await self.create(db, obj_in=TagCreate(name=name))

    async def update(self, db: AsyncSession, *, db_obj: Tag, obj_in: TagUpdate) -> Tag:
        if obj_in.name is not None and obj_in.name != db_obj.name:
            db_obj.name = obj_in.name
            db_obj.slug = await self._build_unique_slug(db, obj_in.name)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_multi_with_post_count(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
    ) -> list[tuple[Tag, int]]:
        query = (
            select(Tag, func.count(Post.id).label("post_count"))
            .outerjoin(post_tag, Tag.id == post_tag.c.tag_id)
            .outerjoin(Post, post_tag.c.post_id == Post.id)
            .group_by(Tag.id)
            .order_by(Tag.name)
            .offset(skip)
            .limit(limit)
        )
        if search:
            query = query.where(Tag.name.ilike(f"%{search}%"))
        result = await db.execute(query)
        return result.all()

    async def get_popular_tags(self, db: AsyncSession, *, limit: int = 10) -> list[tuple[Tag, int]]:
        result = await db.execute(
            select(Tag, func.count(Post.id).label("post_count"))
            .join(post_tag, Tag.id == post_tag.c.tag_id)
            .join(Post, post_tag.c.post_id == Post.id)
            .group_by(Tag.id)
            .order_by(func.count(Post.id).desc(), Tag.name.asc())
            .limit(limit)
        )
        return result.all()


crud_tag = CRUDTag(Tag)
