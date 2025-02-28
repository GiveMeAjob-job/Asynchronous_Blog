from datetime import datetime
from typing import Optional
import math

from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import func, and_, or_

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.api import auth, users, posts
from app.models import import_all

User, Category, Tag, Post, post_tag, Comment = import_all()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# 设置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 设置模板
templates = Jinja2Templates(directory="app/templates")

# 注册API路由
app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_STR}/auth",
    tags=["认证"]
)
app.include_router(
    users.router,
    prefix=f"{settings.API_V1_STR}/users",
    tags=["用户"]
)
app.include_router(
    posts.router,
    prefix=f"{settings.API_V1_STR}/posts",
    tags=["文章"]
)


# 前端路由
@app.get("/", response_class=HTMLResponse)
async def index(
        request: Request,
        page: int = Query(1, ge=1),
        per_page: int = Query(10, le=100),
        sort: str = Query("newest", regex="^(newest|oldest|popular)$"),
        db: AsyncSession = Depends(get_db)
):
    """首页 - 支持分页和排序"""
    # 基础查询
    query = select(Post).where(Post.published == True)

    # 排序
    if sort == "newest":
        query = query.order_by(Post.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(Post.created_at.asc())
    elif sort == "popular":
        query = query.order_by(Post.views.desc())

    # 计算总数
    count_query = select(func.count(Post.id)).where(Post.published == True)
    total = await db.execute(count_query)
    total = total.scalar_one()

    # 分页
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # 执行查询
    result = await db.execute(query)
    posts = result.scalars().all()

    # 获取所有分类
    cat_query = select(Category)
    cat_result = await db.execute(cat_query)
    categories = cat_result.scalars().all()

    # 获取所有标签
    tag_query = select(Tag)
    tag_result = await db.execute(tag_query)
    tags = tag_result.scalars().all()

    # 计算分页数据
    total_pages = math.ceil(total / per_page) if total > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "posts": posts,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": has_next,
            "has_prev": has_prev,
            "sort": sort,
            "categories": categories,
            "tags": tags,
            "current_year": datetime.now().year
        }
    )


@app.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    """文章详情页 - 包含阅读量统计和相关文章"""
    # 查询文章
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

    # 更新阅读量
    post.views = (post.views or 0) + 1
    await db.commit()

    # 查询相关文章
    related_query = select(Post).where(
        and_(
            Post.id != post.id,
            Post.published == True,
            or_(
                Post.category_id == post.category_id,
                Post.author_id == post.author_id
            )
        )
    ).limit(5)

    related_result = await db.execute(related_query)
    related_posts = related_result.scalars().all()

    # 返回数据
    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "post": post,
            "related_posts": related_posts,
            "current_year": datetime.now().year
        }
    )


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
    # 获取用户文章统计
    total_posts = await db.execute(
        select(func.count(Post.id)).where(Post.author_id == current_user.id)
    )
    total_posts = total_posts.scalar_one()

    published_posts = await db.execute(
        select(func.count(Post.id)).where(
            (Post.author_id == current_user.id) & (Post.published == True)
        )
    )
    published_posts = published_posts.scalar_one()

    draft_posts = await db.execute(
        select(func.count(Post.id)).where(
            (Post.author_id == current_user.id) & (Post.published == False)
        )
    )
    draft_posts = draft_posts.scalar_one()

    # 获取最近文章
    recent_posts = await db.execute(
        select(Post)
        .where(Post.author_id == current_user.id)
        .order_by(Post.created_at.desc())
        .limit(5)
    )
    recent_posts = recent_posts.scalars().all()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "total_posts": total_posts,
            "published_posts": published_posts,
            "draft_posts": draft_posts,
            "recent_posts": recent_posts,
            "current_year": datetime.now().year
        }
    )


@app.get("/dashboard/posts/new", response_class=HTMLResponse)
async def new_post_page(request: Request):
    """新建文章页面"""
    return templates.TemplateResponse(
        "new_post.html",
        {"request": request, "current_year": datetime.now().year}
    )


@app.get("/search", response_class=HTMLResponse)
async def search(
        request: Request,
        q: str = Query(None),
        category: Optional[str] = None,
        tag: Optional[str] = None,
        db: AsyncSession = Depends(get_db)
):
    """搜索页面 - 支持关键词、分类和标签筛选"""
    query = select(Post).where(Post.published == True)

    # 全文搜索
    if q:
        query = query.where(
            or_(
                Post.title.ilike(f"%{q}%"),
                Post.content.ilike(f"%{q}%")
            )
        )

    # 分类筛选
    if category:
        query = query.join(Category).filter(Category.name == category)

    # 标签筛选
    if tag:
        query = query.join(post_tag).join(Tag).filter(Tag.name == tag)

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
            "current_year": datetime.now().year
        }
    )
