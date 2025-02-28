from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.api import auth, users, posts
from .models import Post, Category, Tag, Comment, User

from datetime import datetime

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
async def index(request: Request, db: AsyncSession = Depends(get_db)):
    """首页"""
    # 获取最新的博客文章
    query = select(Post).where(Post.published == True).order_by(Post.created_at.desc()).limit(10)
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

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "current_year": datetime.now().year,
            "posts": posts,
            "categories": categories,
            "tags": tags
        }
    )


@app.get("/post/{slug}", response_class=HTMLResponse)
async def post_detail(request: Request, slug: str, db: AsyncSession = Depends(get_db)):
    """文章详情页"""
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
            {"request": request},
            status_code=404
        )

    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "post": post
        }
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse(
        "login.html",
        {"request": request}
    )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """注册页面"""
    return templates.TemplateResponse(
        "register.html",
        {"request": request}
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """仪表盘页面（需要登录）"""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )


@app.get("/dashboard")
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
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

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": current_user,
        "total_posts": total_posts,
        "published_posts": published_posts,
        "draft_posts": draft_posts,
        "recent_posts": recent_posts,
        "current_year": datetime.now().year
    })
