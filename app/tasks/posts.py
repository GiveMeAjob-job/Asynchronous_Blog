from datetime import datetime, timedelta
from celery import shared_task
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select

from app.core.config import settings
from app.models.post import Post, Comment
from app.core.redis import set_cache

engine = create_async_engine(
    str(settings.DATABASE_URL),
    future=True,
)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@shared_task
def update_post_stats():
    """更新文章统计数据，包括：
    1. 最热门文章（评论最多）
    2. 最近发布文章
    3. 月度统计数据
    """

    async def _update():
        async with async_session() as session:
            # 最热门文章（评论最多）
            popular_query = (
                select(Post)
                .join(Comment)
                .group_by(Post.id)
                .order_by(func.count(Comment.id).desc())
                .limit(5)
            )
            popular_result = await session.execute(popular_query)
            popular_posts = [
                {
                    "id": post.id,
                    "title": post.title,
                    "slug": post.slug,
                    "comment_count": len(post.comments)
                }
                for post in popular_result.scalars().all()
            ]

            # 最近发布文章
            recent_query = (
                select(Post)
                .where(Post.published == True)
                .order_by(Post.created_at.desc())
                .limit(5)
            )
            recent_result = await session.execute(recent_query)
            recent_posts = [
                {
                    "id": post.id,
                    "title": post.title,
                    "slug": post.slug,
                    "created_at": post.created_at.isoformat()
                }
                for post in recent_result.scalars().all()
            ]

            # 月度统计数据
            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            last_month_start = month_start - timedelta(days=30)

            # 本月文章数
            current_month_query = (
                select(func.count())
                .select_from(Post)
                .where(and_(
                    Post.created_at >= month_start,
                    Post.published == True
                ))
            )
            current_month_result = await session.execute(current_month_query)
            current_month_count = current_month_result.scalar()

            # 上月文章数
            last_month_query = (
                select(func.count())
                .select_from(Post)
                .where(and_(
                    Post.created_at >= last_month_start,
                    Post.created_at < month_start,
                    Post.published == True
                ))
            )
            last_month_result = await session.execute(last_month_query)
            last_month_count = last_month_result.scalar()

            # 收集统计数据
            stats = {
                "popular_posts": popular_posts,
                "recent_posts": recent_posts,
                "monthly_stats": {
                    "current_month": current_month_count,
                    "last_month": last_month_count,
                    "growth_rate": (
                        ((current_month_count - last_month_count) / last_month_count * 100)
                        if last_month_count > 0 else 0
                    )
                },
                "updated_at": datetime.utcnow().isoformat()
            }

            # 缓存数据
            await set_cache("blog:stats", stats, expire=3600)  # 1小时过期

    # 在Celery任务中运行异步代码
    import asyncio
    asyncio.run(_update())
