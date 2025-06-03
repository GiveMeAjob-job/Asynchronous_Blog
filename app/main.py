# app/main.py
from datetime import datetime
from typing import Optional, Any  # Any 可能在 UserCreate 中用到
import math
import logging

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
from jose import jwt, JWTError  # <--- 确保导入 JWTError

# 从 app.api.v1.dependencies 导入 get_current_user (如果 API 端点仍在使用它)
# from app.api.v1.dependencies import get_current_user # 注意：下面的 get_current_user_optional 是新定义的
from app.core.config import settings
from app.core.database import get_db, async_session  # async_session 是 sessionmaker 实例
from app.core.logging import setup_logging
from app.api.v1 import auth, posts, users, categories, tags
from app.models import import_all
from app.core.security import get_password_hash
from app.core.middleware import log_requests, add_process_time_header

# 设置日志
setup_logging()
logger = logging.getLogger(__name__)

# 导入模型
User, Category, Tag, Post, post_tag, Comment = import_all()

# 创建应用
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

# 中间件配置
app.add_middleware(GZipMiddleware, minimum_size=1000)
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

# 注册API路由 - 统一使用 API 版本前缀
api_v1_routers = [
    (auth.router, "auth", ["认证"]),
    (users.router, "users", ["用户"]),
    (posts.router, "posts", ["文章"]),
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
        access_token: Optional[str] = Cookie(None)
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
        payload = jwt.decode(token_to_decode, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_from_token: Optional[str] = payload.get("sub")
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
    if not user or not user.is_active:
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


async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    """可选的用户认证，用于非强制登录页面，不会抛出异常或重定向。"""
    token_to_decode: Optional[str] = None
    authorization_header: Optional[str] = request.headers.get("Authorization")

    if authorization_header and authorization_header.startswith("Bearer "):
        token_to_decode = authorization_header.split("Bearer ")[1]
    else:
        token_to_decode = request.cookies.get("access_token")

    if not token_to_decode:
        return None

    try:
        payload = jwt.decode(token_to_decode, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id_from_token: Optional[str] = payload.get("sub")
        if user_id_from_token is None:
            return None

        try:
            user_id = int(user_id_from_token)
        except ValueError:
            return None  # Invalid ID format

        user = await db.get(User, user_id)
        return user if user and user.is_active else None

    except JWTError:
        return None
    except Exception as e:  # 捕获其他潜在错误
        logger.error(f"Unexpected error in get_current_user_optional: {e}")
        return None


async def update_post_views(db: AsyncSession, post: Post):
    """异步更新文章阅读量"""
    post.views = (post.views or 0) + 1
    # 不需要单独 commit，依赖 get_db 的 commit
    await db.merge(post)  # 使用 merge 以确保 post 在 session 中
    # 注意：如果 get_db 在异常时 rollback，这个浏览量可能不会保存。
    # 对于浏览量这种非关键数据，可以考虑更独立的更新机制，或者接受它在某些错误情况下可能不保存。


async def get_sidebar_data(db: AsyncSession) -> dict:
    """获取侧边栏数据"""
    try:
        # 分类查询 - 使用 selectinload 预加载关系
        cat_query = select(Category, func.count(Post.id).label('post_count')) \
            .outerjoin(Post, and_(Category.id == Post.category_id, Post.published == True)) \
            .group_by(Category.id)
        cat_result = await db.execute(cat_query)
        categories = cat_result.all()

        # 标签查询
        tag_query = select(Tag).order_by(Tag.name).limit(30)
        tag_result = await db.execute(tag_query)
        tags = tag_result.scalars().all()

        # 热门文章查询 - 预加载关系
        popular_query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True) \
            .order_by(Post.views.desc()) \
            .limit(5)
        popular_result = await db.execute(popular_query)
        popular_posts = popular_result.scalars().all()

        # 确保关系已加载
        for post in popular_posts:
            _ = post.author
            _ = post.category
            _ = post.tags

        return {
            "categories": categories,
            "tags": tags,
            "popular_posts": popular_posts
        }
    except Exception as e:
        logger.error(f"Error fetching sidebar data: {e}")
        return {"categories": [], "tags": [], "popular_posts": []}


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
        sort: str = Query("newest", regex="^(newest|oldest|popular)$"),
        category_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        db: AsyncSession = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)
):
    """首页 - 支持分页、排序和筛选"""
    posts_data = []
    total = 0
    total_pages = 0
    sidebar_data = {"categories": [], "tags": [], "popular_posts": []}

    try:
        # 构建查询 - 预加载关系
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

        # 计算总数
        count_query = select(func.count()).select_from(
            select(Post).where(Post.published == True).subquery()
        )
        if category_id:
            count_query = select(func.count()).select_from(
                select(Post).where(
                    and_(Post.published == True, Post.category_id == category_id)
                ).subquery()
            )
        if tag_name:
            count_query = select(func.count()).select_from(
                select(Post).join(post_tag).join(Tag).where(
                    and_(Post.published == True, Tag.name == tag_name)
                ).subquery()
            )

        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        if total > 0:
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
            result = await db.execute(query)
            posts_data = result.scalars().all()
            total_pages = math.ceil(total / per_page)

            # 确保关系已加载
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
        # 预加载所有关系
        query = select(Post).options(
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.tags),
            selectinload(Post.category),
            selectinload(Post.author)
        ).where(Post.slug == slug, Post.published == True)

        result = await db.execute(query)
        post = result.scalars().first()

        if not post:
            return templates.TemplateResponse(
                "404.html",
                {"request": request, "current_year": datetime.now().year, "current_user": current_user},
                status_code=404
            )

        # 确保关系已加载
        _ = post.author
        _ = post.category
        _ = post.tags
        _ = post.comments

        await update_post_views(db, post)
        related_posts = await get_related_posts(db, post)
        stats = await get_post_stats(db, post)

        return templates.TemplateResponse(
            "post.html",
            {
                "request": request,
                "post": post,
                "related_posts": related_posts,
                "stats": stats,
                "current_year": datetime.now().year,
                "user_is_authenticated": current_user is not None,
                "current_user": current_user
            }
        )
    except Exception as e:
        logger.error(f"Error in post detail for slug {slug}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_post_stats(db: AsyncSession, post: Post) -> dict:
    # ... (您的原有逻辑) ...
    comment_count_result = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post.id)
    )
    word_count = len(post.content.split())  # 更准确的词数
    read_time = max(1, math.ceil(word_count / 200))  # 每分钟200词

    return {
        "comment_count": comment_count_result.scalar_one_or_none() or 0,
        "word_count": word_count,
        "read_time": read_time
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
            "current_year": datetime.now().year
        }
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
    # ... (您的原有搜索逻辑) ...
    # 确保在模板中传递 current_user 和 user_is_authenticated
    posts_data = []
    total = 0
    # ... (您的原有查询逻辑) ...
    # 确保 posts_data 和 total 被正确赋值
    if q or category or tag:
        # ... (您的查询逻辑) ...
        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True)

        if q:
            search_term = f"%{q}%"
            query = query.where(or_(Post.title.ilike(search_term), Post.content.ilike(search_term)))
        if category:
            query = query.join(Category).where(Category.name == category)
        if tag:
            query = query.join(post_tag).join(Tag).where(Tag.name == tag)

        count_query = select(func.count()).select_from(query.correlate(None).subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one_or_none() or 0

        if total > 0:
            per_page = settings.DEFAULT_PAGE_SIZE
            offset = (page - 1) * per_page
            query = query.offset(offset).limit(per_page)
            result = await db.execute(query)
            posts_data = result.scalars().all()
            total_pages = math.ceil(total / per_page)

    popular_tags_data = []  # 获取热门标签和分类数据 (如果需要显示在空搜索结果页)
    categories_data_list = []
    if not (q or category or tag or posts_data):  # 如果没有搜索条件且没有结果
        sidebar_data_for_search = await get_sidebar_data(db)
        popular_tags_data = sidebar_data_for_search["tags"]  # 假设 get_sidebar_data 返回热门标签
        categories_data_list = sidebar_data_for_search["categories"]  # 假设 get_sidebar_data 返回分类

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
            "current_year": datetime.now().year,
            "user_is_authenticated": current_user is not None,
            "current_user": current_user,
            "popular_tags": popular_tags_data,  # 传递热门标签
            "categories": categories_data_list  # 传递分类
        }
    )


# 启动事件
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.PROJECT_NAME}")
    await create_admin_user()
    try:
        from app.core.redis import get_redis_connection  # 移到函数内部，避免顶层导入问题
        redis = await get_redis_connection()
        await redis.ping()
        # PEXPIRE key milliseconds -- Set a key's time to live in milliseconds.
        # await redis.close() # 不要在启动时关闭连接池创建的连接
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")


async def create_admin_user():
    # ... (您的原有逻辑) ...
    pass  # 保持不变


@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {settings.PROJECT_NAME}")
    # from app.core.database import db_manager # 如果您有 db_manager
    # await db_manager.close()


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
        "about.html",
        {
            "request": request,
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/contact", response_class=HTMLResponse)
async def contact_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "contact.html",
        {
            "request": request,
            "current_user": current_user,
            "user_is_authenticated": current_user is not None,
            "current_year": datetime.now().year,
        },
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request, current_user: Optional[User] = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "privacy.html",
        {
            "request": request,
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

    return templates.TemplateResponse(
        "dashboard/categories_manage.html",
        {
            "request": request,
            "current_user": current_user,
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

    return templates.TemplateResponse(
        "dashboard/tags_manage.html",
        {
            "request": request,
            "current_user": current_user,
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

    return templates.TemplateResponse(
        "dashboard/users_manage.html",
        {
            "request": request,
            "current_user": current_user,
            "current_year": datetime.now().year,
        },
    )

