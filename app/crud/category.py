from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.category import Category
from app.models.post import Post
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.utils.slug import generate_slug


class CRUDCategory(CRUDBase[Category, CategoryCreate, CategoryUpdate]):
    async def create(self, db: AsyncSession, *, obj_in: CategoryCreate) -> Category:
        slug = await self._build_unique_slug(db, obj_in.name)
        db_obj = Category(**obj_in.model_dump(), slug=slug)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def _build_unique_slug(self, db: AsyncSession, name: str) -> str:
        base_slug = generate_slug(name)
        slug = base_slug
        suffix = 1
        while True:
            result = await db.execute(select(Category.id).where(Category.slug == slug))
            if result.scalar_one_or_none() is None:
                return slug
            slug = f"{base_slug}-{suffix}"
            suffix += 1

    async def get_by_slug(self, db: AsyncSession, *, slug: str) -> Optional[Category]:
        result = await db.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def get_active(self, db: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[Category]:
        result = await db.execute(
            select(Category).where(Category.is_active == True).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def get_with_post_count(self, db: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[dict]:
        result = await db.execute(
            select(Category, func.count(Post.id).label("post_count"))
            .outerjoin(Post, (Category.id == Post.category_id) & (Post.published == True))
            .group_by(Category.id)
            .offset(skip)
            .limit(limit)
        )
        return [
            {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "description": category.description,
                "is_active": category.is_active,
                "created_at": category.created_at,
                "updated_at": category.updated_at,
                "post_count": post_count,
            }
            for category, post_count in result.all()
        ]


category = CRUDCategory(Category)
