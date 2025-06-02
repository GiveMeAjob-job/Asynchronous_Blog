# app/main.py
from datetime import datetime
from typing import Optional
import math
import logging

from fastapi import FastAPI, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, and_, or_




from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db, async_session
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

for router, prefix, tags in api_v1_routers:
    app.include_router(
        router,
        prefix=f"{settings.API_V1_STR}/{prefix}",
        tags=tags
    )


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}



# 前端路由
@app.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(settings.DEFAULT_PAGE_SIZE, le=settings.MAX_PAGE_SIZE),
        sort: str = Query("newest", regex="^(newest|oldest|popular)$"),
        category_id: Optional[int] = None,
        tag_name: Optional[str] = None,
        db: AsyncSession = Depends(get_db)
):
    """首页 - 支持分页、排序和筛选"""
    try:
        # 基础查询 - 优化查询，预加载关联数据
        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True)

        # 分类筛选
        if category_id:
            query = query.where(Post.category_id == category_id)

        # 标签筛选
        if tag_name:
            query = query.join(post_tag).join(Tag).where(Tag.name == tag_name)

        # 排序
        order_mapping = {
            "newest": Post.created_at.desc(),
            "oldest": Post.created_at.asc(),
            "popular": Post.views.desc()
        }
        query = query.order_by(order_mapping[sort])

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # 分页
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # 执行查询
        result = await db.execute(query)
        posts = result.scalars().all()

        # 获取侧边栏数据
        sidebar_data = await get_sidebar_data(db)

        # 计算分页数据
        total_pages = math.ceil(total / per_page) if total > 0 else 0

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "posts": posts,
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
                "sort": sort,
                "category_id": category_id,
                "tag_name": tag_name,
                "categories": sidebar_data["categories"],
                "tags": sidebar_data["tags"],
                "popular_posts": sidebar_data["popular_posts"],
                "current_year": datetime.now().year
            }
        )
    except Exception as e:
        logger.error(f"Error in index page: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(
        request: Request,
        slug: str,
        db: AsyncSession = Depends(get_db)
):
    """文章详情页 - 包含阅读量统计和相关文章"""
    try:
        # 查询文章 - 优化查询
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
                {"request": request, "current_year": datetime.now().year},
                status_code=404
            )

        # 异步更新阅读量
        await update_post_views(db, post)

        # 获取相关文章
        related_posts = await get_related_posts(db, post)

        # 获取文章统计
        stats = await get_post_stats(db, post)

        return templates.TemplateResponse(
            "post.html",
            {
                "request": request,
                "post": post,
                "related_posts": related_posts,
                "stats": stats,
                "current_year": datetime.now().year
            }
        )
    except Exception as e:
        logger.error(f"Error in post detail: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_sidebar_data(db: AsyncSession) -> dict:
    """获取侧边栏数据"""
    # 获取分类及文章数
    cat_query = select(
        Category,
        func.count(Post.id).label('post_count')
    ).outerjoin(Post).group_by(Category.id)
    cat_result = await db.execute(cat_query)
    categories = cat_result.all()

    # 获取标签
    tag_query = select(Tag).limit(20)
    tag_result = await db.execute(tag_query)
    tags = tag_result.scalars().all()

    # 获取热门文章
    popular_query = select(Post).where(
        Post.published == True
    ).order_by(Post.views.desc()).limit(5)
    popular_result = await db.execute(popular_query)
    popular_posts = popular_result.scalars().all()

    return {
        "categories": categories,
        "tags": tags,
        "popular_posts": popular_posts
    }


async def update_post_views(db: AsyncSession, post: Post):
    """异步更新文章阅读量"""
    post.views = (post.views or 0) + 1
    await db.commit()


async def get_related_posts(db: AsyncSession, post: Post, limit: int = 5):
    """获取相关文章"""
    # 基于相同分类或标签的相关文章
    tag_ids = [tag.id for tag in post.tags]

    query = select(Post).where(
        and_(
            Post.id != post.id,
            Post.published == True,
            or_(
                Post.category_id == post.category_id,
                Post.tags.any(Tag.id.in_(tag_ids)) if tag_ids else False
            )
        )
    ).order_by(func.random()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


async def get_post_stats(db: AsyncSession, post: Post) -> dict:
    """获取文章统计信息"""
    # 评论数
    comment_count = await db.execute(
        select(func.count(Comment.id)).where(Comment.post_id == post.id)
    )

    # 预计阅读时间（假设每分钟阅读200字）
    word_count = len(post.content)
    read_time = max(1, word_count // 200)

    return {
        "comment_count": comment_count.scalar_one(),
        "word_count": word_count,
        "read_time": read_time
    }


# 其他页面路由
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "current_year": datetime.now().year}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """注册页面"""
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "current_year": datetime.now().year}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """仪表盘页面（需要登录）"""
    # 获取用户统计数据
    stats = await get_user_dashboard_stats(db, current_user)

    # 获取最近文章
    recent_posts_query = select(Post).where(
        Post.author_id == current_user.id
    ).order_by(Post.created_at.desc()).limit(10)

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


async def get_user_dashboard_stats(db: AsyncSession, user: User) -> dict:
    """获取用户仪表盘统计数据"""
    # 总文章数
    total_posts = await db.execute(
        select(func.count(Post.id)).where(Post.author_id == user.id)
    )

    # 已发布文章数
    published_posts = await db.execute(
        select(func.count(Post.id)).where(
            and_(Post.author_id == user.id, Post.published == True)
        )
    )

    # 草稿数
    draft_posts = await db.execute(
        select(func.count(Post.id)).where(
            and_(Post.author_id == user.id, Post.published == False)
        )
    )

    # 总阅读量
    total_views = await db.execute(
        select(func.sum(Post.views)).where(Post.author_id == user.id)
    )

    # 总评论数
    total_comments = await db.execute(
        select(func.count(Comment.id)).join(Post).where(Post.author_id == user.id)
    )

    return {
        "total_posts": total_posts.scalar_one(),
        "published_posts": published_posts.scalar_one(),
        "draft_posts": draft_posts.scalar_one(),
        "total_views": total_views.scalar_one() or 0,
        "total_comments": total_comments.scalar_one()
    }


@app.get("/search", response_class=HTMLResponse)
async def search(
        request: Request,
        q: str = Query(None, min_length=1, max_length=100),
        category: Optional[str] = None,
        tag: Optional[str] = None,
        page: int = Query(1, ge=1),
        db: AsyncSession = Depends(get_db)
):
    """搜索页面 - 支持全文搜索"""
    posts = []
    total = 0

    if q or category or tag:
        query = select(Post).options(
            selectinload(Post.author),
            selectinload(Post.category),
            selectinload(Post.tags)
        ).where(Post.published == True)

        # 全文搜索
        if q:
            search_term = f"%{q}%"
            query = query.where(
                or_(
                    Post.title.ilike(search_term),
                    Post.content.ilike(search_term)
                )
            )

        # 分类筛选
        if category:
            query = query.join(Category).where(Category.name == category)

        # 标签筛选
        if tag:
            query = query.join(post_tag).join(Tag).where(Tag.name == tag)

        # 计算总数
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # 分页
        per_page = settings.DEFAULT_PAGE_SIZE
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # 执行查询
        result = await db.execute(query)
        posts = result.scalars().all()

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "posts": posts,
            "query": q,
            "category": category,
            "tag": tag,
            "page": page,
            "total": total,
            "current_year": datetime.now().year
        }
    )


# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    logger.info(f"Starting {settings.PROJECT_NAME}")

    # 创建默认管理员账号
    await create_admin_user()

    # 初始化缓存
    from app.core.redis import get_redis_connection
    try:
        redis = await get_redis_connection()
        await redis.ping()
        await redis.close()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")


# 在 app/main.py 的 create_admin_user 函数中添加更详细的错误处理

async def create_admin_user():
    """在应用启动时创建超级管理员账号（如果不存在）"""
    async with async_session() as db:
        try:
            # 检查admin账号是否已存在
            query = select(User).where(User.email == settings.ADMIN_EMAIL)
            result = await db.execute(query)
            admin_user = result.scalars().first()

            if not admin_user:
                # 创建超级管理员账号
                admin = User(
                    email=settings.ADMIN_EMAIL,
                    username=settings.ADMIN_USERNAME,
                    hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                    is_active=True,
                    is_superuser=True
                )
                db.add(admin)
                await db.commit()
                logger.info(f"Created admin user: {settings.ADMIN_USERNAME}")
            else:
                logger.info("Admin user already exists")
        except Exception as e:
            # 如果是唯一约束冲突，说明其他进程已经创建了admin用户
            if "duplicate key value violates unique constraint" in str(e):
                logger.info("Admin user already exists (created by another process)")
            else:
                logger.error(f"Error creating admin user: {e}")
            await db.rollback()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时执行"""
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


# 错误处理
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """404错误处理"""
    return templates.TemplateResponse(
        "404.html",
        {"request": request, "current_year": datetime.now().year},
        status_code=404
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    """500错误处理"""
    logger.error(f"Server error: {exc}")
    return templates.TemplateResponse(
        "500.html",
        {"request": request, "current_year": datetime.now().year},
        status_code=500
    )


@app.get("/dashboard/posts", response_class=HTMLResponse)
async def my_posts(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """我的文章列表页面"""
    # 查询当前用户的文章
    query = select(Post).options(
        selectinload(Post.category)
    ).where(Post.author_id == current_user.id).order_by(Post.created_at.desc())

    result = await db.execute(query)
    posts = result.scalars().all()

    return templates.TemplateResponse(
        "list.html",  # Changed from "posts/list.html"
        {"request": request, "posts": posts, "current_user": current_user}
    )

async def get_current_user_optional(request: Request, db: AsyncSession = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token") # 或者从 localStorage 获取并由 JS 传递
    if not token:
        # 如果你想通过 Authorization header (由 axios 拦截器添加) 来判断
        # 这在纯前端渲染模板时比较复杂，因为Jinja2渲染时JS还没运行
        # 更简单的方式是依赖cookie或传递一个状态
        return None
    try:
        # 这是一个简化的例子，实际中你可能需要调用类似 get_current_user 的逻辑
        # 但要注意 get_current_user 会在 token 无效时抛出 HTTPException
        # 这里我们需要一个不会在 token 无效时中断页面渲染的版本
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: Optional[int] = payload.get("sub")
        if user_id is None:
            return None
        user = await db.get(User, user_id)
        return user
    except (JWTError, HTTPException): # 捕获JWT错误或HTTPException
        return None

    sidebar_data = await get_sidebar_data(db) # 确保这个函数存在并返回期望数据

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "posts": posts, # 确保 posts 已定义
            # ... (page, per_page, total, total_pages, has_next, has_prev, sort, category_id, tag_name) ...
            "categories": sidebar_data["categories"],
            "tags": sidebar_data["tags"],
            "popular_posts": sidebar_data["popular_posts"],
            "current_year": datetime.now().year,
            "user_is_authenticated": user_is_authenticated # 新增传递这个状态
        }
    )

@app.get("/dashboard/posts/new", response_class=HTMLResponse)
async def new_post_page(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    """创建新文章页面"""
    # 获取分类和标签数据
    categories = await db.execute(select(Category))
    tags = await db.execute(select(Tag))

    return templates.TemplateResponse(
        "new.html",  # Changed from "posts/new.html"
        {
            "request": request,
            "categories": categories.scalars().all(),
            "tags": tags.scalars().all(),
            "current_user": current_user
        }
    )
