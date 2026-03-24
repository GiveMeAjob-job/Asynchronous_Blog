# app/main.py
from contextlib import asynccontextmanager
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
import math
import logging
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, Request, Depends, Query, HTTPException, status, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, \
    async_sessionmaker  # async_sessionmaker 用于 get_db_context 和 create_admin_user
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, and_, or_
from jose import JWTError
from markdown import markdown as render_markdown
from markupsafe import Markup

from app.core.config import settings
from app.core.database import get_db, async_session  # async_session 是 sessionmaker 实例
from app.core.logging import setup_logging
from app.api.v1 import auth, comments, posts, users, categories, tags
from app.models import import_all
from app.models.comment import COMMENT_STATUS_APPROVED, COMMENT_STATUS_HIDDEN, COMMENT_STATUS_PENDING
from app.models.like import PostLike
from app.core.security import decode_access_token, decode_post_preview_token, get_password_hash
from app.core.middleware import (
    SecurityHeadersMiddleware,
    RateLimitContextMiddleware,
    log_requests,
    add_process_time_header,
)
from app.utils.slug import generate_slug

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)

# 导入模型
User, Category, Tag, Post, post_tag, Comment = import_all()


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME}")
    try:
        from app.core.redis import get_redis_connection

        redis = await get_redis_connection()
        await redis.ping()
        logger.info("Redis connection successful")
    except ModuleNotFoundError as e:
        logger.warning(f"Redis support unavailable: {e}")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    yield

    logger.info(f"Shutting down {settings.PROJECT_NAME}")

# 创建应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# 中间件配置
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitContextMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.ENVIRONMENT == "development" else settings.ALLOWED_HOSTS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定义中间件
app.middleware("http")(log_requests)
app.middleware("http")(add_process_time_header)

# 设置静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 设置模板
templates = Jinja2Templates(directory="app/templates")


def static_asset(request: Request, path: str) -> str:
    asset_path = Path("static") / path
    version = str(int(asset_path.stat().st_mtime)) if asset_path.exists() else settings.VERSION
    return f"{request.url_for('static', path=path)}?v={version}"


def markdown_filter(value: Optional[str]) -> Markup:
    if not value:
        return Markup("")
    rendered = render_markdown(
        value,
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
    return Markup(rendered)


def excerpt_filter(value: Optional[str], length: int = 180) -> str:
    if not value:
        return ""
    plain_text = " ".join(value.split())
    if len(plain_text) <= length:
        return plain_text
    return plain_text[:length].rsplit(" ", 1)[0] + "..."


templates.env.filters["markdown"] = markdown_filter
templates.env.filters["excerpt"] = excerpt_filter
templates.env.globals["static_asset"] = static_asset

# 注册API路由 - 统一使用 API 版本前缀
api_v1_routers = [
    (auth.router, "auth", ["认证"]),
    (users.router, "users", ["用户"]),
    (posts.router, "posts", ["文章"]),
    (comments.router, "comments", ["评论"]),
    (categories.router, "categories", ["分类"]),
    (tags.router, "tags", ["标签"]),
]


for router_item, prefix, tags_list in api_v1_routers:  # 避免与 tags 模型名冲突
    app.include_router(
        router_item,
        prefix=f"{settings.API_V1_STR}/{prefix}",
        tags=tags_list
    )






# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# --- 认证依赖函数 ---
async def get_dashboard_user(
        request: Request,
        db: AsyncSession = Depends(get_db),  # get_db 提供了会话
        access_token: Optional[str] = Cookie(None, alias=settings.ACCESS_COOKIE_NAME)
) -> User:
    """
    仪表盘页面的用户认证依赖。
    尝试从 Authorization header 或 access_token cookie 获取并验证 token。
    失败时，如果请求是 HTML 页面，则重定向到登录页；否则抛出 HTTPException。
    """
    authorization_header: Optional[str] = request.headers.get("Authorization")
    token_to_decode: Optional[str] = None

    if authorization_header and authorization_header.startswith("Bearer "):
        token_to_decode = authorization_header.split("Bearer ")[1]
    elif access_token:
        token_to_decode = access_token

    if not token_to_decode:
        accept_header = request.headers.get("accept", "")
        redirect_path = request.url.path
        if request.url.query:
            redirect_path += f"?{request.url.query}"  # 保留查询参数

        logger.info(f"No token found for dashboard access to {redirect_path}. Redirecting to login.")
        if "text/html" in accept_header:
            return RedirectResponse(url=f"/login?redirect={redirect_path}", status_code=status.HTTP_302_FOUND)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="需要登录")

    try:
        payload = decode_access_token(token_to_decode)
        user_id_from_token: Optional[str] = payload.get("sub")
        token_version = int(payload.get("ver", 0))
        if user_id_from_token is None:
            raise JWTError("Invalid token: sub claim missing")

        try:
            user_id = int(user_id_from_token)
        except ValueError:
            raise JWTError("Invalid token: sub is not a valid integer format")

    except JWTError as e:
        logger.warning(f"JWT validation failed in get_dashboard_user for path {request.url.path}: {e}")
        accept_header = request.headers.get("accept", "")
        redirect_path = request.url.path
        if request.url.query:
            redirect_path += f"?{request.url.query}"

        if "text/html" in accept_header:
            return RedirectResponse(url=f"/login?session_expired=true&reason=invalid_token&redirect={redirect_path}",
                                    status_code=status.HTTP_302_FOUND)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")

    user = await db.get(User, user_id)
    if not user or not user.is_active or user.token_version != token_version:
        logger.warning(
            f"User not found or inactive in get_dashboard_user for user_id: {user_id} (path: {request.url.path})")
        accept_header = request.headers.get("accept", "")
        redirect_path = request.url.path
        if request.url.query:
            redirect_path += f"?{request.url.query}"

        if "text/html" in accept_header:
            return RedirectResponse(url=f"/login?session_expired=true&reason=user_issue&redirect={redirect_path}",
                                    status_code=status.HTTP_302_FOUND)
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或未激活")

    return user


async def get_current_user_optional(request: Request) -> Optional[User]:
    """可选的用户认证，用于非强制登录页面，不会抛出异常或重定向。"""
    token_to_decode: Optional[str] = None
    authorization_header: Optional[str] = request.headers.get("Authorization")

    if authorization_header and authorization_header.startswith("Bearer "):
        token_to_decode = authorization_header.split("Bearer ")[1]
    else:
        token_to_decode = request.cookies.get(settings.ACCESS_COOKIE_NAME)

    if not token_to_decode:
        return None

    try:
        payload = decode_access_token(token_to_decode)
        user_id_from_token: Optional[str] = payload.get("sub")
        token_version = int(payload.get("ver", 0))
        if user_id_from_token is None:
            return None

        try:
            user_id = int(user_id_from_token)
        except ValueError:
            return None  # Invalid ID format

        async with async_session() as db:
            user = await db.get(User, user_id)
            return user if user and user.is_active and user.token_version == token_version else None

    except JWTError:
        return None
    except Exception as e:  # 捕获其他潜在错误
        logger.error(f"Unexpected error in get_current_user_optional: {e}")
        return None


async def update_post_views(db: AsyncSession, post: Post):
    """异步更新文章阅读量"""
    post.views = (post.views or 0) + 1
    await db.flush()
    await db.commit()


def serialize_category_counts(rows: list[tuple[Category, int]]) -> list[dict[str, Any]]:
    return [
        {
            "id": category.id,
            "name": category.name,
            "slug": category.slug,
            "description": category.description,
            "post_count": post_count,
        }
        for category, post_count in rows
    ]


def serialize_tag_counts(rows: list[tuple[Tag, int]]) -> list[dict[str, Any]]:
    return [
        {
            "id": tag.id,
            "name": tag.name,
            "slug": tag.slug,
            "post_count": post_count,
        }
        for tag, post_count in rows
    ]


def build_absolute_url(path: str) -> str:
    base = settings.APP_BASE_URL.rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base}{normalized_path}"


async def ensure_category_slug(db: AsyncSession, category: Category) -> str:
    if category.slug:
        return category.slug

    base_slug = generate_slug(category.name, max_length=100)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(select(Category.id).where(Category.slug == slug, Category.id != category.id))
        if result.scalar_one_or_none() is None:
            category.slug = slug
            await db.flush()
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


async def ensure_tag_slug(db: AsyncSession, tag: Tag) -> str:
    if tag.slug:
        return tag.slug

    base_slug = generate_slug(tag.name, max_length=255)
    slug = base_slug
    suffix = 1
    while True:
        result = await db.execute(select(Tag.id).where(Tag.slug == slug, Tag.id != tag.id))
        if result.scalar_one_or_none() is None:
            tag.slug = slug
            await db.flush()
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1


async def get_sidebar_data(db: AsyncSession) -> dict:
    """获取侧边栏数据"""
    try:
        cat_query = (
            select(Category, func.count(Post.id).label("post_count"))
            .outerjoin(Post, and_(Category.id == Post.category_id, Post.published == True))
            .group_by(Category.id)
            .order_by(func.count(Post.id).desc(), Category.name.asc())
        )
        cat_result = await db.execute(cat_query)
        categories = cat_result.all()

        tag_query = (
            select(Tag, func.count(Post.id).label("post_count"))
            .outerjoin(post_tag, Tag.id == post_tag.c.tag_id)
            .outerjoin(Post, and_(post_tag.c.post_id == Post.id, Post.published == True))
            .group_by(Tag.id)
            .order_by(func.count(Post.id).desc(), Tag.name.asc())
            .limit(30)
        )
        tag_result = await db.execute(tag_query)
        tags = tag_result.all()

        slugs_updated = False
        for category, _ in categories:
            if not category.slug:
                await ensure_category_slug(db, category)
                slugs_updated = True
        for tag, _ in tags:
            if not tag.slug:
                await ensure_tag_slug(db, tag)
                slugs_updated = True
        if slugs_updated:
            await db.commit()

        popular_query = (
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
            .where(Post.published == True)
            .order_by((Post.views + Post.like_count * 2 + Post.comment_count * 3).desc(), Post.created_at.desc())
            .limit(5)
        )
        popular_result = await db.execute(popular_query)
        popular_posts = popular_result.scalars().all()

        featured_query = (
            select(Post)
            .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
            .where(Post.published == True, Post.is_featured == True)
            .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
            .limit(3)
        )
        featured_result = await db.execute(featured_query)
        featured_posts = featured_result.scalars().all()

        for post in popular_posts:
            _ = post.author
            _ = post.category
            _ = post.tags
        for post in featured_posts:
            _ = post.author
            _ = post.category
            _ = post.tags

        return {
            "categories": serialize_category_counts(categories),
            "tags": serialize_tag_counts(tags),
            "popular_posts": popular_posts,
            "featured_posts": featured_posts,
        }
    except Exception as e:
        logger.error(f"Error fetching sidebar data: {e}")
        return {"categories": [], "tags": [], "popular_posts": [], "featured_posts": []}


async def get_related_posts(db: AsyncSession, post: Post, limit: int = 5):
    """获取相关文章"""
    try:
        tag_ids = [tag.id for tag in post.tags] if post.tags else []

        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(
            and_(
                Post.id != post.id,
                Post.published == True
            )
        )

        # 如果有标签或分类，添加相关性筛选
        if tag_ids or post.category_id:
            if tag_ids and post.category_id:
                query = query.where(
                    or_(
                        Post.category_id == post.category_id,
                        Post.tags.any(Tag.id.in_(tag_ids))
                    )
                )
            elif post.category_id:
                query = query.where(Post.category_id == post.category_id)
            elif tag_ids:
                query = query.where(Post.tags.any(Tag.id.in_(tag_ids)))

        query = query.order_by(Post.created_at.desc()).limit(limit)
        result = await db.execute(query)
        posts = result.scalars().all()

        # 确保关系已加载
        for related_post in posts:
            _ = related_post.author
            _ = related_post.category
            _ = related_post.tags

        return posts
    except Exception as e:
        logger.error(f"Error fetching related posts: {e}")
        return []


# 在 index 函数中的修改部分
@app.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(settings.DEFAULT_PAGE_SIZE, le=settings.MAX_PAGE_SIZE),
        sort: str = Query("newest", pattern="^(newest|oldest|popular)$"),
        category_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)
):
    """首页 - 支持分页、排序和筛选"""
    posts_data = []
    total = 0
    total_pages = 0
    sidebar_data = {"categories": [], "tags": [], "popular_posts": [], "featured_posts": []}

    try:
        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True)

        if category_id:
            query = query.where(Post.category_id == category_id)
        if tag_name:
            query = query.join(post_tag).join(Tag).where(Tag.name == tag_name)

        order_mapping = {
            "newest": Post.created_at.desc(),
            "oldest": Post.created_at.asc(),
            "popular": Post.views.desc()
        }
        query = query.order_by(order_mapping[sort])

        count_query = select(func.count()).select_from(query.order_by(None).subquery())

        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        if total > 0:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
            result = await db.execute(query)
            posts_data = result.scalars().all()
            total_pages = math.ceil(total / per_page)
            for post in posts_data:
                _ = post.author
                _ = post.category
                _ = post.tags

        sidebar_data = await get_sidebar_data(db)

    except Exception as e:
        logger.error(f"Error in index page data fetching: {str(e)}")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "posts": posts_data,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages if total_pages else False,
            "has_prev": page > 1,
            "sort": sort,
            "category_id": category_id,
            "tag_name": tag_name,
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "featured_posts": sidebar_data["featured_posts"],
            "current_year": datetime.now().year,
            "user_is_authenticated": current_user is not None,
            "current_user": current_user
        }
    )


# 在 post_detail 函数中的修改
@app.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(
        request: Request,
        slug: str,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)
):
    """文章详情页"""
    try:
        query = select(Post).options(
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.likes),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.likes),
            selectinload(Post.tags),
            selectinload(Post.category),
            selectinload(Post.author),
            selectinload(Post.likes),
        ).where(Post.slug == slug, Post.published == True)

        result = await db.execute(query)
        post = result.scalars().first()

        if not post:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "current_year": datetime.now().year, "current_user": current_user},
                status_code=404
            )

        _ = post.author
        _ = post.category
        _ = post.tags
        _ = post.comments
        visible_comments = [
            comment for comment in post.comments
            if comment.parent_id is None and comment.moderation_status == COMMENT_STATUS_APPROVED
        ]
        for comment in visible_comments:
            comment.replies = [
                reply for reply in comment.replies if reply.moderation_status == COMMENT_STATUS_APPROVED
            ]

        await update_post_views(db, post)
        related_posts = await get_related_posts(db, post)
        stats = await get_post_stats(db, post)
        liked_post_ids: set[int] = set()
        liked_comment_ids: set[int] = set()

        if current_user:
            liked_post_result = await db.execute(
                select(PostLike.post_id).where(PostLike.user_id == current_user.id, PostLike.post_id == post.id)
            )
            liked_post_ids = set(liked_post_result.scalars().all())

            comment_ids = [comment.id for comment in visible_comments]
            reply_ids = [reply.id for comment in visible_comments for reply in comment.replies]
            all_comment_ids = comment_ids + reply_ids
            if all_comment_ids:
                from app.models.like import CommentLike

                liked_comment_result = await db.execute(
                    select(CommentLike.comment_id).where(
                        CommentLike.user_id == current_user.id,
                        CommentLike.comment_id.in_(all_comment_ids),
                    )
                )
                liked_comment_ids = set(liked_comment_result.scalars().all())

        for comment in visible_comments:
            comment.is_liked = comment.id in liked_comment_ids
            for reply in comment.replies:
                reply.is_liked = reply.id in liked_comment_ids

        return templates.TemplateResponse(
            "post.html",
            {
                "request": request,
                "post": post,
                "comments": visible_comments,
                "related_posts": related_posts,
                "stats": stats,
                "post_is_liked": post.id in liked_post_ids,
                "current_year": datetime.now().year,
                "user_is_authenticated": current_user is not None,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error in post detail for slug {slug}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def _can_access_draft_preview(post: Post, current_user: Optional[User]) -> bool:
    if current_user is None:
        return False
    return current_user.is_superuser or current_user.id == post.author_id


def _preview_token_matches_post(payload: dict[str, Any], post: Post) -> bool:
    content_stamp = (post.updated_at or post.created_at or datetime.utcnow()).isoformat()
    return (
        payload.get("post_id") == post.id
        and payload.get("author_id") == post.author_id
        and payload.get("content_stamp") == content_stamp
    )


@app.get("/preview/posts/{post_id}", response_class=HTMLResponse, name="post_preview_page")
async def post_preview_page(
        request: Request,
        post_id: int,
        token: Optional[str] = None,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)
):
    result = await db.execute(
        select(Post).options(
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.likes),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.author),
            selectinload(Post.comments).selectinload(Comment.replies).selectinload(Comment.likes),
            selectinload(Post.tags),
            selectinload(Post.category),
            selectinload(Post.author),
            selectinload(Post.likes),
        ).where(Post.id == post_id)
    )
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=404, detail="文章未找到")

    if post.published:
        return RedirectResponse(url=f"/post/{post.slug}", status_code=status.HTTP_302_FOUND)

    preview_expires_at: Optional[datetime] = None
    has_access = _can_access_draft_preview(post, current_user)

    if not has_access and token:
        try:
            payload = decode_post_preview_token(token)
        except JWTError:
            payload = None

        if payload and _preview_token_matches_post(payload, post):
            has_access = True
            exp_value = payload.get("exp")
            if isinstance(exp_value, (int, float)):
                preview_expires_at = datetime.fromtimestamp(exp_value)

    if not has_access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="该预览链接无效或已过期")

    stats = await get_post_stats(db, post)
    related_posts = await get_related_posts(db, post)

    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "post": post,
            "comments": [],
            "related_posts": related_posts,
            "stats": stats,
            "post_is_liked": False,
            "preview_mode": True,
            "preview_expires_at": preview_expires_at,
            "current_year": datetime.now().year,
            "user_is_authenticated": current_user is not None,
            "current_user": current_user,
        }
    )


async def get_post_stats(db: AsyncSession, post: Post) -> dict:
    # ... (您的原有逻辑) ...
    comment_count_result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post.id, Comment.moderation_status == COMMENT_STATUS_APPROVED)
    )
    word_count = len(post.content.split())  # 更准确的词数
    read_time = max(1, math.ceil(word_count / 200))  # 每分钟200词

    return {
        "comment_count": comment_count_result.scalar_one_or_none() or 0,
        "word_count": word_count,
        "read_time": read_time
    }


async def get_author_stats(db: AsyncSession, author_id: int) -> dict[str, int]:
    result = await db.execute(
        select(
            func.count(Post.id),
            func.coalesce(func.sum(Post.views), 0),
            func.coalesce(func.sum(Post.like_count), 0),
            func.coalesce(func.sum(Post.comment_count), 0),
        ).where(Post.author_id == author_id, Post.published == True)
    )
    post_count, total_views, total_likes, total_comments = result.one()
    return {
        "post_count": post_count or 0,
        "total_views": total_views or 0,
        "total_likes": total_likes or 0,
        "total_comments": total_comments or 0,
    }


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "current_year": datetime.now().year}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "current_year": datetime.now().year}
    )


# --- 仪表盘路由 ---
ANALYTICS_PERIOD_LABELS = {
    30: "近 30 天",
    90: "近 90 天",
    180: "近 180 天",
    365: "近 365 天",
}

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def normalize_analytics_period(period: Optional[int]) -> int:
    if period in ANALYTICS_PERIOD_LABELS:
        return period
    return 90


def format_metric_value(value: float | int, precision: int = 1, suffix: str = "") -> str:
    quantize_pattern = "1" if precision == 0 else f"1.{'0' * precision}"
    numeric = Decimal(str(value)).quantize(Decimal(quantize_pattern), rounding=ROUND_HALF_UP)
    if precision == 0 or numeric == numeric.to_integral():
        return f"{int(numeric)}{suffix}"
    return f"{numeric:.{precision}f}{suffix}"


def describe_metric_change(
    current: float,
    previous: float,
    *,
    precision: int = 1,
    higher_is_better: bool = True,
    suffix: str = "",
) -> dict[str, str]:
    delta = round(float(current) - float(previous), precision)
    if abs(delta) < (10 ** (-precision)):
        return {"delta_text": "与上一周期持平", "delta_tone": "neutral"}

    if previous == 0:
        tone = "positive" if (current > 0 and higher_is_better) or (current < 0 and not higher_is_better) else "neutral"
        return {
            "delta_text": f"较上一周期新增 {format_metric_value(abs(current), precision, suffix)}",
            "delta_tone": tone,
        }

    percent_change = abs(delta) / abs(previous) * 100
    improved = delta > 0 if higher_is_better else delta < 0
    direction_label = "提升" if improved else "回落"
    return {
        "delta_text": (
            f"{direction_label} {format_metric_value(abs(delta), precision, suffix)}"
            f" / {format_metric_value(percent_change, 0, '%')}"
        ),
        "delta_tone": "positive" if improved else "negative",
    }


def rate_to_tone(rate: float) -> str:
    if rate >= 80:
        return "positive"
    if rate >= 55:
        return "warning"
    return "negative"


def build_ratio_health_card(label: str, completed: int, total: int, helper: str) -> dict[str, str]:
    rate = round((completed / total) * 100, 1) if total else 0
    return {
        "label": label,
        "value": format_metric_value(rate, 0, "%"),
        "helper": helper,
        "tone": rate_to_tone(rate) if total else "neutral",
    }


def describe_elapsed_days(timestamp: Optional[datetime], now: datetime) -> str:
    if timestamp is None:
        return "尚未开始"
    days = max((now.date() - timestamp.date()).days, 0)
    if days == 0:
        return "今天更新"
    if days == 1:
        return "昨天更新"
    return f"{days} 天前更新"


def post_engagement_score(post: Post) -> float:
    return round((post.like_count * 3.0) + (post.comment_count * 4.0) + (post.views / 20.0), 1)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
        request: Request,
        current_user: User = Depends(get_dashboard_user)  # 使用统一认证依赖
):
    if isinstance(current_user, RedirectResponse):  # 检查是否是重定向
        return current_user

    async with async_session() as db:  # 为特定操作获取新会话或确保传递 db
        stats = await get_user_dashboard_stats(db, current_user)
        recent_posts_query = select(Post).where(Post.author_id == current_user.id) \
            .order_by(Post.created_at.desc()).limit(10)
        recent_posts_result = await db.execute(recent_posts_query)
        recent_posts = recent_posts_result.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            **stats,
            "recent_posts": recent_posts,
            "dashboard_section": "overview",
            "current_year": datetime.now().year
        }
    )


@app.get("/dashboard/posts", response_class=HTMLResponse)
async def my_posts(
        request: Request,
        current_user: User = Depends(get_dashboard_user)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    async with async_session() as db:
        query = select(Post).options(selectinload(Post.category)) \
            .where(Post.author_id == current_user.id).order_by(Post.created_at.desc())
        result = await db.execute(query)
        posts_data = result.scalars().all()

    return templates.TemplateResponse(
        "posts/list.html",
        {
            "request": request,
            "posts": posts_data,
            "current_user": current_user,
            "dashboard_section": "posts",
            "current_year": datetime.now().year
        }
    )


@app.get("/dashboard/analytics", response_class=HTMLResponse, name="dashboard_analytics_page")
async def dashboard_analytics_page(
        request: Request,
        current_user: User = Depends(get_dashboard_user),
        period: int = Query(90),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    selected_period = normalize_analytics_period(period)
    async with async_session() as db:
        stats = await get_user_dashboard_stats(db, current_user)
        analytics = await get_user_analytics_snapshot(db, current_user, selected_period)

    return templates.TemplateResponse(
        "dashboard/analytics.html",
        {
            "request": request,
            "current_user": current_user,
            **stats,
            **analytics,
            "dashboard_section": "analytics",
            "current_year": datetime.now().year,
        },
    )


@app.get("/dashboard/posts/new", response_class=HTMLResponse)
async def new_post_page(
        request: Request,
        current_user: User = Depends(get_dashboard_user)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    async with async_session() as db:
        categories_result = await db.execute(select(Category))
        tags_result = await db.execute(select(Tag))
        categories_data = categories_result.scalars().all()
        tags_data = tags_result.scalars().all()

    return templates.TemplateResponse(
        "posts/new.html",
        {
            "request": request,
            "categories": categories_data,
            "tags": tags_data,
            "current_user": current_user,
            "dashboard_section": "new_post",
            "current_year": datetime.now().year
        }
    )


async def get_user_dashboard_stats(db: AsyncSession, user: User) -> dict:
    # ... (您的原有逻辑，确保 scalar_one() 在可能为空时有处理，例如 scalar_one_or_none() or 0) ...
    total_posts_res = await db.execute(select(func.count(Post.id)).where(Post.author_id == user.id))
    published_posts_res = await db.execute(
        select(func.count(Post.id)).where(and_(Post.author_id == user.id, Post.published == True)))
    draft_posts_res = await db.execute(
        select(func.count(Post.id)).where(and_(Post.author_id == user.id, Post.published == False)))
    total_views_res = await db.execute(select(func.sum(Post.views)).where(Post.author_id == user.id))
    total_comments_res = await db.execute(select(func.count(Comment.id)).join(Post).where(Post.author_id == user.id))

    return {
        "total_posts": total_posts_res.scalar_one_or_none() or 0,
        "published_posts": published_posts_res.scalar_one_or_none() or 0,
        "draft_posts": draft_posts_res.scalar_one_or_none() or 0,
        "total_views": total_views_res.scalar_one_or_none() or 0,
        "total_comments": total_comments_res.scalar_one_or_none() or 0
    }


def get_recent_month_labels(month_count: int = 6) -> list[str]:
    now = datetime.now()
    current_month_index = now.year * 12 + now.month - 1
    labels = []
    for offset in range(month_count - 1, -1, -1):
        month_index = current_month_index - offset
        year = month_index // 12
        month = month_index % 12 + 1
        labels.append(f"{year}-{month:02d}")
    return labels


async def get_user_analytics_snapshot(
    db: AsyncSession,
    user: User,
    period_days: int,
) -> dict[str, Any]:
    posts_result = await db.execute(
        select(Post)
        .options(selectinload(Post.category), selectinload(Post.tags))
        .where(Post.author_id == user.id)
        .order_by(Post.created_at.desc())
    )
    posts = posts_result.scalars().all()
    published_posts = [post for post in posts if post.published]
    draft_posts = [post for post in posts if not post.published]
    now = datetime.utcnow()
    period_days = normalize_analytics_period(period_days)
    period_label = ANALYTICS_PERIOD_LABELS[period_days]
    period_start = now - timedelta(days=period_days)
    previous_period_start = period_start - timedelta(days=period_days)

    def activity_date(post: Post) -> datetime:
        return post.published_at or post.created_at

    period_posts = [post for post in published_posts if period_start <= activity_date(post) <= now]
    previous_period_posts = [
        post for post in published_posts if previous_period_start <= activity_date(post) < period_start
    ]

    average_views = round(sum(post.views for post in published_posts) / len(published_posts), 1) if published_posts else 0
    average_likes = round(sum(post.like_count for post in published_posts) / len(published_posts), 1) if published_posts else 0
    average_comments = round(sum(post.comment_count for post in published_posts) / len(published_posts), 1) if published_posts else 0
    latest_published_post = max(published_posts, key=activity_date, default=None)

    period_views = sum(post.views for post in period_posts)
    period_likes = sum(post.like_count for post in period_posts)
    period_comments = sum(post.comment_count for post in period_posts)
    previous_views = sum(post.views for post in previous_period_posts)
    previous_likes = sum(post.like_count for post in previous_period_posts)
    previous_comments = sum(post.comment_count for post in previous_period_posts)

    period_avg_views = round(period_views / len(period_posts), 1) if period_posts else 0
    period_avg_likes = round(period_likes / len(period_posts), 1) if period_posts else 0
    period_avg_comments = round(period_comments / len(period_posts), 1) if period_posts else 0
    previous_avg_views = round(previous_views / len(previous_period_posts), 1) if previous_period_posts else 0
    previous_avg_likes = round(previous_likes / len(previous_period_posts), 1) if previous_period_posts else 0
    previous_avg_comments = round(previous_comments / len(previous_period_posts), 1) if previous_period_posts else 0

    period_engagement_rate = round(((period_likes + period_comments) / period_views) * 100, 1) if period_views else 0
    previous_engagement_rate = (
        round(((previous_likes + previous_comments) / previous_views) * 100, 1) if previous_views else 0
    )

    month_count = 12 if period_days >= 365 else 6 if period_days >= 180 else 4
    month_labels = get_recent_month_labels(month_count)
    month_counts = {label: 0 for label in month_labels}
    for post in published_posts:
        label = activity_date(post).strftime("%Y-%m")
        if label in month_counts:
            month_counts[label] += 1

    monthly_data = [{"label": label, "count": count} for label, count in month_counts.items()]
    max_month_count = max((item["count"] for item in monthly_data), default=0)
    for item in monthly_data:
        item["percent"] = 0 if max_month_count == 0 else int(item["count"] / max_month_count * 100)

    weekday_counts = {label: 0 for label in WEEKDAY_LABELS}
    for post in period_posts:
        weekday_counts[WEEKDAY_LABELS[activity_date(post).weekday()]] += 1
    weekday_breakdown = [{"label": label, "count": count} for label, count in weekday_counts.items()]
    max_weekday_count = max((item["count"] for item in weekday_breakdown), default=0)
    for item in weekday_breakdown:
        item["percent"] = 0 if max_weekday_count == 0 else int(item["count"] / max_weekday_count * 100)
    best_weekday = max(weekday_breakdown, key=lambda item: item["count"], default=None)

    category_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for post in published_posts:
        category_name = post.category.name if post.category else "未分类"
        category_counts[category_name] = category_counts.get(category_name, 0) + 1
        for tag in post.tags:
            tag_counts[tag.name] = tag_counts.get(tag.name, 0) + 1

    category_breakdown = [
        {"name": name, "count": count}
        for name, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    max_category_count = max((item["count"] for item in category_breakdown), default=0)
    for item in category_breakdown:
        item["percent"] = 0 if max_category_count == 0 else int(item["count"] / max_category_count * 100)

    tag_breakdown = [
        {"name": name, "count": count}
        for name, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]

    recent_comments_result = await db.execute(
        select(Comment)
        .join(Post)
        .options(selectinload(Comment.author), selectinload(Comment.post))
        .where(Post.author_id == user.id)
        .order_by(Comment.created_at.desc())
        .limit(8)
    )
    recent_comments = recent_comments_result.scalars().all()

    pending_comments_count = (
        await db.execute(
            select(func.count(Comment.id))
            .join(Post)
            .where(Post.author_id == user.id, Comment.moderation_status == COMMENT_STATUS_PENDING)
        )
    ).scalar_one_or_none() or 0

    stale_drafts = [
        post for post in draft_posts if (now - (post.updated_at or post.created_at)).days >= 14
    ]
    stale_drafts_count = len(stale_drafts)

    published_with_category = sum(1 for post in published_posts if post.category is not None)
    published_with_summary = sum(1 for post in published_posts if (post.summary or "").strip())
    published_with_cover = sum(1 for post in published_posts if (post.featured_image or "").strip())
    published_with_comments_enabled = sum(1 for post in published_posts if post.allow_comments)
    uncategorized_posts = [post for post in published_posts if post.category is None]

    feature_candidates = sorted(
        [
            post
            for post in published_posts
            if not post.is_featured and (post.views >= max(average_views, 20) or post.comment_count >= 2)
        ],
        key=lambda post: (post.views, post.comment_count, post.like_count),
        reverse=True,
    )
    low_engagement_posts = sorted(
        [
            post
            for post in published_posts
            if (now - activity_date(post)).days >= 30
            and post.views <= max(int(average_views * 0.35), 15)
            and post.comment_count == 0
            and post.like_count == 0
        ],
        key=lambda post: (post.views, activity_date(post)),
    )

    top_posts = [
        {
            "title": post.title,
            "slug": post.slug,
            "views": post.views,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "engagement_score": post_engagement_score(post),
        }
        for post in sorted(
            published_posts,
            key=lambda post: (post_engagement_score(post), post.created_at.timestamp()),
            reverse=True,
        )[:5]
    ]

    latest_drafts = [
        {
            "id": post.id,
            "title": post.title,
            "updated_label": describe_elapsed_days(post.updated_at or post.created_at, now),
            "status_label": "久未更新" if post in stale_drafts else "进行中",
            "status_tone": "warning" if post in stale_drafts else "neutral",
        }
        for post in sorted(draft_posts, key=lambda item: item.updated_at or item.created_at, reverse=True)[:5]
    ]

    highlight_cards = [
        {
            "label": "已发布文章",
            "value": format_metric_value(len(published_posts), 0),
            "helper": "当前公开可读的内容总量",
            "delta_text": f"上次发布：{describe_elapsed_days(activity_date(latest_published_post), now) if latest_published_post else '暂无'}",
            "delta_tone": "neutral",
        },
        {
            "label": "本期发布",
            "value": format_metric_value(len(period_posts), 0),
            "helper": f"{period_label}内发布的文章数",
            **describe_metric_change(len(period_posts), len(previous_period_posts), precision=0),
        },
        {
            "label": "平均浏览",
            "value": format_metric_value(average_views, 1),
            "helper": "单篇发布文章当前累计平均浏览",
            "delta_text": f"{period_label}新文章平均 {format_metric_value(period_avg_views, 1)} 浏览",
            "delta_tone": "neutral",
        },
        {
            "label": "本期互动率",
            "value": format_metric_value(period_engagement_rate, 1, "%"),
            "helper": "（点赞 + 评论）/ 浏览，衡量内容被回应的程度",
            **describe_metric_change(period_engagement_rate, previous_engagement_rate, precision=1, suffix="%"),
        },
        {
            "label": "待审核评论",
            "value": format_metric_value(pending_comments_count, 0),
            "helper": "读者正在等你处理这些评论",
            "delta_text": "评论流转正常" if pending_comments_count == 0 else "建议优先处理，避免对话中断",
            "delta_tone": "positive" if pending_comments_count == 0 else "warning",
        },
        {
            "label": "久未更新草稿",
            "value": format_metric_value(stale_drafts_count, 0),
            "helper": "超过 14 天没有继续推进的草稿",
            "delta_text": "草稿节奏健康" if stale_drafts_count == 0 else "可以挑一篇继续补完",
            "delta_tone": "positive" if stale_drafts_count == 0 else "warning",
        },
    ]

    comparison_metrics = [
        {
            "label": "发布文章",
            "current": format_metric_value(len(period_posts), 0),
            "previous": format_metric_value(len(previous_period_posts), 0),
            **describe_metric_change(len(period_posts), len(previous_period_posts), precision=0),
        },
        {
            "label": "平均浏览 / 篇",
            "current": format_metric_value(period_avg_views, 1),
            "previous": format_metric_value(previous_avg_views, 1),
            **describe_metric_change(period_avg_views, previous_avg_views, precision=1),
        },
        {
            "label": "平均评论 / 篇",
            "current": format_metric_value(period_avg_comments, 1),
            "previous": format_metric_value(previous_avg_comments, 1),
            **describe_metric_change(period_avg_comments, previous_avg_comments, precision=1),
        },
        {
            "label": "平均点赞 / 篇",
            "current": format_metric_value(period_avg_likes, 1),
            "previous": format_metric_value(previous_avg_likes, 1),
            **describe_metric_change(period_avg_likes, previous_avg_likes, precision=1),
        },
    ]

    health_cards = [
        build_ratio_health_card("分类完整度", published_with_category, len(published_posts), "已归入分类的文章占比"),
        build_ratio_health_card("摘要完整度", published_with_summary, len(published_posts), "带摘要的文章占比"),
        build_ratio_health_card("封面覆盖率", published_with_cover, len(published_posts), "设置了封面图的文章占比"),
        build_ratio_health_card("开放评论率", published_with_comments_enabled, len(published_posts), "仍允许读者互动的文章占比"),
    ]

    attention_items: list[dict[str, str]] = []
    if pending_comments_count:
        attention_items.append(
            {
                "title": f"有 {pending_comments_count} 条评论待审核",
                "detail": "优先把读者的对话放出来，互动会更连贯。",
                "href": "/dashboard/comments?status=pending",
                "action_label": "去处理评论",
                "tone": "warning",
            }
        )
    if stale_drafts:
        oldest_draft = sorted(stale_drafts, key=lambda item: item.updated_at or item.created_at)[0]
        attention_items.append(
            {
                "title": f"草稿《{oldest_draft.title}》已放置较久",
                "detail": f"{describe_elapsed_days(oldest_draft.updated_at or oldest_draft.created_at, now)}，适合决定继续写还是关闭。",
                "href": f"/dashboard/posts/edit/{oldest_draft.id}",
                "action_label": "继续完善草稿",
                "tone": "warning",
            }
        )
    if feature_candidates:
        candidate = feature_candidates[0]
        attention_items.append(
            {
                "title": f"《{candidate.title}》值得考虑设为精选",
                "detail": f"这篇文章已拿到 {candidate.views} 浏览和 {candidate.comment_count} 条评论，但还没有被标记为精选。",
                "href": f"/dashboard/posts/edit/{candidate.id}",
                "action_label": "去编辑文章",
                "tone": "positive",
            }
        )
    if uncategorized_posts:
        attention_items.append(
            {
                "title": f"还有 {len(uncategorized_posts)} 篇文章没有分类",
                "detail": "补齐分类后，归档页、搜索和主题分布会更清晰。",
                "href": "/dashboard/posts",
                "action_label": "整理文章分类",
                "tone": "neutral",
            }
        )
    if low_engagement_posts:
        quiet_post = low_engagement_posts[0]
        attention_items.append(
            {
                "title": f"《{quiet_post.title}》互动偏低",
                "detail": "可以补摘要、封面、标题或在正文开头增加更明确的切入点。",
                "href": f"/dashboard/posts/edit/{quiet_post.id}",
                "action_label": "优化这篇文章",
                "tone": "neutral",
            }
        )
    if not attention_items:
        attention_items.append(
            {
                "title": "当前内容状态很健康",
                "detail": "没有明显的待办堵点，可以继续写作，或者回到数据里找下一篇值得扩展的主题。",
                "href": "/dashboard/posts/new",
                "action_label": "继续写新文章",
                "tone": "positive",
            }
        )

    period_options = [
        {
            "label": label,
            "days": days,
            "href": f"/dashboard/analytics?period={days}",
            "active": days == period_days,
        }
        for days, label in ANALYTICS_PERIOD_LABELS.items()
    ]

    return {
        "top_posts": top_posts,
        "monthly_data": monthly_data,
        "weekday_breakdown": weekday_breakdown,
        "best_weekday": best_weekday,
        "category_breakdown": category_breakdown,
        "tag_breakdown": tag_breakdown,
        "recent_comments": recent_comments,
        "latest_drafts": latest_drafts,
        "highlight_cards": highlight_cards,
        "comparison_metrics": comparison_metrics,
        "health_cards": health_cards,
        "attention_items": attention_items,
        "analytics_period_label": period_label,
        "analytics_period_days": period_days,
        "analytics_period_options": period_options,
        "analytics_window_label": f"{period_start.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}",
        "average_views": average_views,
        "average_likes": average_likes,
        "average_comments": average_comments,
        "period_post_count": len(period_posts),
    }


async def get_comment_dashboard_snapshot(db: AsyncSession, user: User, status_filter: str) -> dict[str, Any]:
    total_query = select(func.count(Comment.id)).join(Post)
    visible_query = select(func.count(Comment.id)).join(Post).where(Comment.moderation_status == COMMENT_STATUS_APPROVED)
    pending_query = select(func.count(Comment.id)).join(Post).where(Comment.moderation_status == COMMENT_STATUS_PENDING)
    hidden_query = select(func.count(Comment.id)).join(Post).where(Comment.moderation_status == COMMENT_STATUS_HIDDEN)

    comments_query = (
        select(Comment)
        .join(Post)
        .options(selectinload(Comment.author), selectinload(Comment.post))
        .order_by(Comment.created_at.desc())
        .limit(200)
    )

    if not user.is_superuser:
        total_query = total_query.where(Post.author_id == user.id)
        visible_query = visible_query.where(Post.author_id == user.id)
        pending_query = pending_query.where(Post.author_id == user.id)
        hidden_query = hidden_query.where(Post.author_id == user.id)
        comments_query = comments_query.where(Post.author_id == user.id)

    if status_filter == "visible":
        comments_query = comments_query.where(Comment.moderation_status == COMMENT_STATUS_APPROVED)
    elif status_filter == "pending":
        comments_query = comments_query.where(Comment.moderation_status == COMMENT_STATUS_PENDING)
    elif status_filter == "hidden":
        comments_query = comments_query.where(Comment.moderation_status == COMMENT_STATUS_HIDDEN)

    total = (await db.execute(total_query)).scalar_one_or_none() or 0
    visible = (await db.execute(visible_query)).scalar_one_or_none() or 0
    pending = (await db.execute(pending_query)).scalar_one_or_none() or 0
    hidden = (await db.execute(hidden_query)).scalar_one_or_none() or 0
    comments = (await db.execute(comments_query)).scalars().all()

    return {"total": total, "visible": visible, "pending": pending, "hidden": hidden, "comments": comments}


@app.get("/search", response_class=HTMLResponse)
async def search(
        request: Request,
        q: Optional[str] = Query(None, min_length=1, max_length=100),  # q 可以是 Optional
        category: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = Query(1, ge=1),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)  # 可选认证
):
    posts_data = []
    total = 0
    total_pages = 0
    per_page = settings.DEFAULT_PAGE_SIZE
    sidebar_data = await get_sidebar_data(db)

    if q or category or tag:
        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True)

        if q:
            search_term = f"%{q}%"
            query = query.where(
                or_(Post.title.ilike(search_term), Post.content.ilike(search_term), Post.summary.ilike(search_term))
            )
        if category:
            query = query.join(Category).where(Category.name == category)
        if tag:
            query = query.join(post_tag).join(Tag).where(Tag.name == tag)

        count_query = select(func.count()).select_from(query.order_by(None).subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        if total > 0:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
            result = await db.execute(query)
            posts_data = result.scalars().all()
            total_pages = math.ceil(total / per_page)

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "posts": posts_data,
            "query": q,
            "category": category,
            "tag": tag,
            "page": page,
            "total": total,
            "total_pages": total_pages,
            "per_page": per_page,
            "has_next": page < total_pages if total_pages else False,
            "has_prev": page > 1,
            "current_year": datetime.now().year,
            "user_is_authenticated": current_user is not None,
            "current_user": current_user,
            "popular_tags": sidebar_data["tags"],
            "categories": sidebar_data["categories"],
            "popular_posts": sidebar_data["popular_posts"],
        }
    )


@app.get("/categories/{slug}", response_class=HTMLResponse, name="category_page")
async def category_page(
        request: Request,
        slug: str,
        page: int = Query(1, ge=1),
        per_page: int = Query(settings.DEFAULT_PAGE_SIZE, le=settings.MAX_PAGE_SIZE),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional),
):
    category_result = await db.execute(select(Category).where(Category.slug == slug, Category.is_active == True))
    category = category_result.scalars().first()
    if not category:
        fallback_categories = (
            await db.execute(select(Category).where(Category.slug.is_(None), Category.is_active == True))
        ).scalars().all()
        for candidate in fallback_categories:
            if await ensure_category_slug(db, candidate) == slug:
                category = candidate
                await db.commit()
                break
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分类不存在")

    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        .where(Post.published == True, Post.category_id == category.id)
        .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
    )
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one_or_none() or 0
    total_pages = math.ceil(total / per_page) if total else 0

    posts_data = []
    if total:
        result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
        posts_data = result.scalars().all()

    sidebar_data = await get_sidebar_data(db)

    return templates.TemplateResponse(
        "taxonomy.html",
        {
            "request": request,
            "topic_type": "分类",
            "topic_name": category.name,
            "topic_slug": category.slug,
            "topic_description": category.description or "按一条更清晰的主题线索把相关文章整理在一起。",
            "topic_badge": "Category",
            "posts": posts_data,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages if total_pages else False,
            "has_prev": page > 1,
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/tags/{slug}", response_class=HTMLResponse, name="tag_page")
async def tag_page(
        request: Request,
        slug: str,
        page: int = Query(1, ge=1),
        per_page: int = Query(settings.DEFAULT_PAGE_SIZE, le=settings.MAX_PAGE_SIZE),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional),
):
    tag_result = await db.execute(select(Tag).where(Tag.slug == slug))
    tag = tag_result.scalars().first()
    if not tag:
        fallback_tags = (await db.execute(select(Tag).where(Tag.slug.is_(None)))).scalars().all()
        for candidate in fallback_tags:
            if await ensure_tag_slug(db, candidate) == slug:
                tag = candidate
                await db.commit()
                break
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")

    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        .join(post_tag, Post.id == post_tag.c.post_id)
        .where(Post.published == True, post_tag.c.tag_id == tag.id)
        .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
    )
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one_or_none() or 0
    total_pages = math.ceil(total / per_page) if total else 0

    posts_data = []
    if total:
        result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
        posts_data = result.scalars().unique().all()

    sidebar_data = await get_sidebar_data(db)

    return templates.TemplateResponse(
        "taxonomy.html",
        {
            "request": request,
            "topic_type": "标签",
            "topic_name": tag.name,
            "topic_slug": tag.slug,
            "topic_description": f"围绕 #{tag.name} 的公开文章集合，适合顺着一个技术主题继续深入。",
            "topic_badge": "Tag",
            "posts": posts_data,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages if total_pages else False,
            "has_prev": page > 1,
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/archive", response_class=HTMLResponse)
async def archive_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional),
):
    result = await db.execute(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        .where(Post.published == True)
        .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
    )
    posts_data = result.scalars().all()

    archive_groups: dict[str, dict[str, Any]] = {}
    for post in posts_data:
        dt = post.published_at or post.created_at
        group_key = dt.strftime("%Y-%m")
        if group_key not in archive_groups:
            archive_groups[group_key] = {
                "label": dt.strftime("%Y 年 %m 月"),
                "count": 0,
                "posts": [],
            }
        archive_groups[group_key]["count"] += 1
        archive_groups[group_key]["posts"].append(post)

    sidebar_data = await get_sidebar_data(db)

    return templates.TemplateResponse(
        "archive.html",
        {
            "request": request,
            "archive_groups": list(archive_groups.values()),
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/rss.xml", include_in_schema=False)
async def rss_feed(db: AsyncSession = Depends(get_db)) -> Response:
    result = await db.execute(
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category))
        .where(Post.published == True)
        .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
        .limit(20)
    )
    posts_data = result.scalars().all()
    items = []
    for post in posts_data:
        published_at = post.published_at or post.created_at
        items.append(
            f"""
            <item>
                <title>{xml_escape(post.title)}</title>
                <link>{xml_escape(build_absolute_url(f"/post/{post.slug}"))}</link>
                <guid>{xml_escape(build_absolute_url(f"/post/{post.slug}"))}</guid>
                <description>{xml_escape(excerpt_filter(post.summary or post.content, 240))}</description>
                <pubDate>{published_at.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>
            </item>
            """.strip()
        )

    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{xml_escape(settings.PROJECT_NAME)}</title>
    <link>{xml_escape(settings.APP_BASE_URL)}</link>
    <description>Async Blog 最新发布内容</description>
    <language>zh-cn</language>
    {' '.join(items)}
  </channel>
</rss>
"""
    return Response(content=rss_content, media_type="application/rss+xml; charset=utf-8")


@app.get("/authors/{username}", response_class=HTMLResponse, name="author_page")
async def author_page(
        request: Request,
        username: str,
        page: int = Query(1, ge=1),
        per_page: int = Query(settings.DEFAULT_PAGE_SIZE, le=settings.MAX_PAGE_SIZE),
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional),
):
    author_result = await db.execute(select(User).where(User.username == username, User.is_active == True))
    author = author_result.scalars().first()
    if not author:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="作者不存在")

    query = (
        select(Post)
        .options(selectinload(Post.author), selectinload(Post.category), selectinload(Post.tags))
        .where(Post.author_id == author.id, Post.published == True)
        .order_by(Post.published_at.desc().nullslast(), Post.created_at.desc())
    )
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one_or_none() or 0
    total_pages = math.ceil(total / per_page) if total else 0

    posts_data = []
    if total:
        result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
        posts_data = result.scalars().all()

    stats = await get_author_stats(db, author.id)
    sidebar_data = await get_sidebar_data(db)

    return templates.TemplateResponse(
        "author.html",
        {
            "request": request,
            "author": author,
            "posts": posts_data,
            "stats": stats,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages if total_pages else False,
            "has_prev": page > 1,
            "can_edit_profile": current_user is not None and current_user.id == author.id,
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml(db: AsyncSession = Depends(get_db)) -> Response:
    now = datetime.utcnow()
    static_urls = [
        ("/", now),
        ("/archive", now),
        ("/search", now),
        ("/about", now),
        ("/contact", now),
        ("/privacy", now),
    ]

    post_result = await db.execute(
        select(Post.slug, Post.updated_at).where(Post.published == True).order_by(Post.updated_at.desc()).limit(500)
    )
    category_result = await db.execute(select(Category).where(Category.is_active == True))
    tag_result = await db.execute(select(Tag))
    author_result = await db.execute(select(User.username, User.updated_at).where(User.is_active == True))
    slugs_updated = False

    entries = [
        f"<url><loc>{xml_escape(build_absolute_url(path))}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>"
        for path, updated_at in static_urls
    ]
    entries.extend(
        f"<url><loc>{xml_escape(build_absolute_url(f'/post/{slug}'))}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>"
        for slug, updated_at in post_result.all()
    )
    category_entries = []
    for category in category_result.scalars().all():
        if not category.slug:
            slugs_updated = True
        slug = await ensure_category_slug(db, category)
        category_entries.append(
            f"<url><loc>{xml_escape(build_absolute_url(f'/categories/{slug}'))}</loc><lastmod>{category.updated_at.date().isoformat()}</lastmod></url>"
        )
    entries.extend(category_entries)

    tag_entries = []
    for tag in tag_result.scalars().all():
        if not tag.slug:
            slugs_updated = True
        slug = await ensure_tag_slug(db, tag)
        tag_entries.append(
            f"<url><loc>{xml_escape(build_absolute_url(f'/tags/{slug}'))}</loc><lastmod>{tag.updated_at.date().isoformat()}</lastmod></url>"
        )
    entries.extend(tag_entries)
    if slugs_updated:
        await db.commit()
    entries.extend(
        f"<url><loc>{xml_escape(build_absolute_url(f'/authors/{username}'))}</loc><lastmod>{updated_at.date().isoformat()}</lastmod></url>"
        for username, updated_at in author_result.all()
    )

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  {" ".join(entries)}\n'
        "</urlset>\n"
    )
    return Response(content=content, media_type="application/xml")


async def create_admin_user():
    async with async_session() as db:
        # 检查是否已存在管理员
        result = await db.execute(
            select(User).where(User.email == settings.ADMIN_EMAIL)
        )
        admin = result.scalars().first()

        if not admin:
            admin = User(
                email=settings.ADMIN_EMAIL,
                username=settings.ADMIN_USERNAME,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_active=True,
                is_superuser=True
            )
            db.add(admin)
            await db.commit()
            logger.info("Admin user created")
# 错误处理
@app.exception_handler(HTTPException)  # 更具体地捕获 FastAPI 的 HTTPException
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException: {exc.status_code} - {exc.detail} for {request.url.path}")
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request, "current_year": datetime.now().year},
                                          status_code=404)
    if exc.status_code == 401:  # 未授权
        return templates.TemplateResponse("login.html", {"request": request, "current_year": datetime.now().year,
                                                         "error_message": "请先登录"}, status_code=401)
    # 为其他HTTPException提供通用错误页面或行为
    return templates.TemplateResponse("error_generic.html",
                                      {"request": request, "status_code": exc.status_code, "detail": exc.detail,
                                       "current_year": datetime.now().year}, status_code=exc.status_code)


@app.exception_handler(Exception)  # 捕获所有其他未处理的异常
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {exc} for {request.url.path}", exc_info=True)  # 添加 exc_info=True
    return templates.TemplateResponse(
        "500.html",
        {"request": request, "current_year": datetime.now().year},
        status_code=500
    )

# 确保这个文件中的所有路由、函数和导入都是您期望的最终版本。
# 移除了重复的 /dashboard/posts 和 /dashboard/posts/new 路由定义
# 移除了 my_posts_alias 路由，因为模板路径应直接在 my_posts 中指定正确

@app.get("/dashboard/posts/edit/{post_id}", response_class=HTMLResponse, name="edit_post_page_route") # <--- 添加这个 name
async def edit_post_page( # 函数名可以是 edit_post_page 或其他，重要的是 name 参数
    request: Request,
    post_id: int,
    current_user: User = Depends(get_dashboard_user),
    # 如果 get_dashboard_user 已处理 db，或在此函数内部使用 async_session() as db:
    # db: AsyncSession = Depends(get_db)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    async with async_session() as db: # 使用新的会话，或者确保 get_db 能正确提供
        post_to_edit = await db.get(Post, post_id, options=[selectinload(Post.tags)])

        if not post_to_edit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文章未找到")

        if post_to_edit.author_id != current_user.id and not current_user.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限编辑此文章")

        categories_result = await db.execute(select(Category))
        tags_result = await db.execute(select(Tag))
        categories_data = categories_result.scalars().all()
        tags_data = tags_result.scalars().all()

        current_post_tag_names = [tag.name for tag in post_to_edit.tags]

    return templates.TemplateResponse(
        "posts/edit.html",
        {
            "request": request,
            "post": post_to_edit,
            "categories": categories_data,
            "tags": tags_data,
            "current_post_tags_str": ",".join(current_post_tag_names),
            "current_user": current_user,
            "dashboard_section": "posts",
            "current_year": datetime.now().year
        }
    )

# 在 app/main.py 文件中

# ... (其他 imports 和 get_dashboard_user 函数定义) ...

@app.get("/dashboard/profile", response_class=HTMLResponse)
async def user_profile_page(
    request: Request,
    current_user: User = Depends(get_dashboard_user) # 认证
):
    if isinstance(current_user, RedirectResponse): # 处理 get_dashboard_user 可能返回的重定向
        return current_user

    return templates.TemplateResponse(
        "dashboard/profile.html", # 您需要创建这个模板文件
        {
            "request": request,
            "current_user": current_user, # 将当前用户信息传递给模板
            "dashboard_section": "profile",
            "current_year": datetime.now().year
            # 您可以根据需要传递更多用户相关的统计信息或数据
        }
    )


# ---------------------------------------------------------------------------
# Public informational pages
# ---------------------------------------------------------------------------


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "content_page.html",
        {
            "request": request,
            "page_badge": "About",
            "page_title": "把技术博客，做成一套更能持续运营的内容产品",
            "page_lead": "Async Blog 现在不只是能启动，而是已经具备写作、阅读、归档、搜索和作者展示的一整套骨架。",
            "page_sections": [
                {
                    "title": "从能跑，到更像产品",
                    "body": "这次升级不仅修了模型和接口契约，也把首页层次、文章详情、仪表盘、归档、RSS、作者信息和公共浏览入口一起打磨，让整站更完整。",
                },
                {
                    "title": "适合长期写作",
                    "body": "如果你在写 FastAPI、异步编程、工程实践或系列教程，分类页、标签页、作者页和搜索都会比单纯的文章列表更有组织感。",
                },
                {
                    "title": "后续还能继续长",
                    "body": "这套结构现在已经更适合继续加测试、加数据统计、加内容运营能力，而不是每次改一点就牵一大片。",
                },
            ],
            "page_aside_title": "现在已经具备",
            "page_aside_items": ["精选文章", "归档页", "RSS 订阅", "作者主页", "分类页与标签页", "评论回复与点赞"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    contact_email = settings.MAIL_FROM or settings.ADMIN_EMAIL
    return templates.TemplateResponse(
        "content_page.html",
        {
            "request": request,
            "page_badge": "Contact",
            "page_title": "想反馈问题、提新功能，或者一起把它继续做强",
            "page_lead": "如果你在使用过程中发现页面细节、交互路径或内容组织还有提升空间，欢迎继续提需求。",
            "page_sections": [
                {
                    "title": "反馈什么最有帮助",
                    "body": "最有效的反馈通常包含页面位置、复现步骤、你期待的行为，以及这是视觉问题、功能问题还是数据问题。",
                },
                {
                    "title": "适合讨论的话题",
                    "body": "包括写作后台体验、评论交互、搜索与归档、SEO 与 RSS、分类和标签组织方式，或者任何你觉得博客系统还可以再进化的方向。",
                },
                {
                    "title": "联系邮箱",
                    "body": f"当前默认联系邮箱是 {contact_email}。接入真实团队邮箱后，也可以直接把这里替换成正式联系渠道。",
                },
            ],
            "page_aside_title": "推荐附带的信息",
            "page_aside_items": ["问题页面", "浏览器或设备", "是否登录", "报错信息", "你想要的改进效果"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "content_page.html",
        {
            "request": request,
            "page_badge": "Privacy",
            "page_title": "这个博客系统会保存哪些信息，以及为什么需要这些信息",
            "page_lead": "为了支持注册、登录、发文、评论和账号找回，系统会保存一部分必要的账户和内容数据。",
            "page_sections": [
                {
                    "title": "账户信息",
                    "body": "系统会保存用户名、邮箱和加密后的密码，以及你主动填写的简介、头像、网站和地区等资料，用于账号识别与公开展示。",
                },
                {
                    "title": "内容与互动记录",
                    "body": "文章、评论、点赞、归档和作者统计等数据会被保存，用于支撑前台展示、搜索、排序、后台管理和互动功能。",
                },
                {
                    "title": "安全与会话",
                    "body": "登录态由访问令牌维持，密码找回和邮箱验证会使用一次性令牌。生产环境建议配置稳定密钥、正式邮件服务和真实基础设施。",
                },
            ],
            "page_aside_title": "当前默认保护措施",
            "page_aside_items": ["密码只存哈希", "支持退出登录", "支持密码重置", "支持邮箱验证", "删除内容时会同步回收计数"],
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


# ---------------------------------------------------------------------------
# Password recovery and email verification pages
# ---------------------------------------------------------------------------


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        "forgot_password.html",
        {"request": request, "current_year": datetime.now().year},
    )


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: Optional[str] = None):
    return templates.TemplateResponse(
        "reset_password.html",
        {
            "request": request,
            "token": token,
            "current_year": datetime.now().year,
        },
    )


@app.get("/email-verified", response_class=HTMLResponse)
async def email_verified_notice_page(request: Request):
    return templates.TemplateResponse(
        "email_verified_notice.html",
        {"request": request, "current_year": datetime.now().year},
    )


@app.get("/email-verification-feedback", response_class=HTMLResponse)
async def verification_feedback_page(request: Request, success: bool = True):
    return templates.TemplateResponse(
        "verification_feedback.html",
        {
            "request": request,
            "success": success,
            "current_year": datetime.now().year,
        },
    )


# ---------------------------------------------------------------------------
# Admin management pages
# ---------------------------------------------------------------------------


@app.get("/dashboard/categories", response_class=HTMLResponse)
async def dashboard_categories_page(
    request: Request,
    current_user: User = Depends(get_dashboard_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")

    return templates.TemplateResponse(
        "dashboard/categories_manage.html",
        {
            "request": request,
            "current_user": current_user,
            "dashboard_section": "categories",
            "current_year": datetime.now().year,
        },
    )


@app.get("/dashboard/tags", response_class=HTMLResponse)
async def dashboard_tags_page(
    request: Request,
    current_user: User = Depends(get_dashboard_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")

    return templates.TemplateResponse(
        "dashboard/tags_manage.html",
        {
            "request": request,
            "current_user": current_user,
            "dashboard_section": "tags",
            "current_year": datetime.now().year,
        },
    )


@app.get("/dashboard/users", response_class=HTMLResponse)
async def dashboard_users_page(
    request: Request,
    current_user: User = Depends(get_dashboard_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")

    return templates.TemplateResponse(
        "dashboard/users_manage.html",
        {
            "request": request,
            "current_user": current_user,
            "dashboard_section": "users",
            "current_year": datetime.now().year,
        },
    )



@app.get("/dashboard/profile/edit", response_class=HTMLResponse)
async def edit_user_profile_page(
        request: Request,
        current_user: User = Depends(get_dashboard_user)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return templates.TemplateResponse(
        "dashboard/profile_edit.html",
        {
            "request": request,
            "current_user": current_user,
            "dashboard_section": "profile",
            "current_year": datetime.now().year
        }
    )


@app.get("/dashboard/comments", response_class=HTMLResponse, name="dashboard_comments_page")
async def dashboard_comments_page(
        request: Request,
        status_filter: str = Query("all", alias="status", pattern="^(all|pending|visible|hidden)$"),
        current_user: User = Depends(get_dashboard_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    async with async_session() as db:
        snapshot = await get_comment_dashboard_snapshot(db, current_user, status_filter)

    return templates.TemplateResponse(
        "dashboard/comments_manage.html",
        {
            "request": request,
            "current_user": current_user,
            "dashboard_section": "comments",
            "status_filter": status_filter,
            "comment_stats": {
                "total": snapshot["total"],
                "visible": snapshot["visible"],
                "pending": snapshot["pending"],
                "hidden": snapshot["hidden"],
            },
            "comments": snapshot["comments"],
            "current_year": datetime.now().year,
        },
    )
