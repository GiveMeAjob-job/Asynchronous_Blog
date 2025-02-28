README_MD = """
# Async Blog

一个基于FastAPI、SQLAlchemy、Celery和Redis的现代异步博客系统。

## 特性

- 基于FastAPI构建的异步API
- SQLAlchemy ORM与异步数据库操作
- Celery任务队列处理后台任务
- Redis缓存提升性能
- JWT认证系统
- 响应式前端界面
- Docker容器化部署

## 快速开始

### 使用Docker Compose

```bash
# 克隆仓库
git clone https://github.com/yourusername/async-blog.git
cd async-blog

# 创建.env文件
cp .env.example .env
# 编辑.env文件设置环境变量

# 启动容器
docker compose up -d

# 创建初始迁移
docker-compose exec web alembic revision --autogenerate -m "Initial migration"

# 应用迁移
docker-compose exec web alembic upgrade head
```

### 访问

- Web应用：http://localhost:8000
- API文档：http://localhost:8000/docs
- RabbitMQ管理界面：http://localhost:15672
- Flower任务监控：http://localhost:5555

## 开发

### 安装依赖

```bash
# 安装Poetry
pip install poetry

# 安装项目依赖
poetry install
```

### 本地运行

```bash
# 激活虚拟环境
poetry shell

# 运行应用
uvicorn app.main:app --reload
```

## 项目结构

```
async_blog/
├── alembic/              # 数据库迁移
├── app/                  # 应用代码
│   ├── api/              # API路由
│   ├── core/             # 核心配置
│   ├── models/           # 数据库模型
│   ├── schemas/          # Pydantic模型
│   ├── services/         # 业务逻辑
│   ├── tasks/            # Celery任务
│   └── templates/        # 前端模板
├── static/               # 静态资源
│   ├── css/
│   ├── js/
│   └── img/
├── tests/                # 测试代码
├── .env                  # 环境变量
└── docker-compose.yml    # Docker配置
```

## 贡献

欢迎贡献代码、报告问题或提出新功能建议。

## 许可证

MIT
"""

#############################################################################
# 12. 使用指南
#############################################################################

"""
项目使用指南
=============

1. 项目结构设置
---------------

按照文件顶部显示的目录结构创建项目文件。可以使用以下命令快速创建目录结构：

```bash
mkdir -p async_blog/{alembic/versions,app/{api,core,models,schemas,services,tasks,templates,utils},static/{css,js,img},tests}
touch async_blog/{.env,.gitignore,alembic.ini,docker-compose.yml,Dockerfile,pyproject.toml,README.md}
touch async_blog/app/{__init__.py,main.py}
touch async_blog/app/{api,core,models,schemas,services,tasks,utils}/__init__.py
touch async_blog/tests/__init__.py
```

2. 复制代码
-----------

将各个部分的代码复制到相应的文件中，确保文件路径与上面的文件结构一致。

3. 运行项目
-----------

### 使用Docker Compose（推荐）:

1. 确保已安装Docker和Docker Compose
2. 在项目根目录下创建.env文件：
   ```bash
   cp .env.example .env
   # 编辑.env文件，设置密钥等配置
   ```
3. 启动所有服务：
   ```bash
   docker-compose up -d
   ```
4. 创建初始数据库迁移：
   ```bash
   docker-compose exec web alembic revision --autogenerate -m "Initial migration"
   ```
5. 应用迁移：
   ```bash
   docker-compose exec web alembic upgrade head
   ```
6. 访问网站：http://localhost:8000

### 本地开发：

1. 安装Poetry：
   ```bash
   pip install poetry
   ```
2. 安装项目依赖：
   ```bash
   poetry install
   ```
3. 激活虚拟环境：
   ```bash
   poetry shell
   ```
4. 启动PostgreSQL、Redis和RabbitMQ（可使用Docker）
5. 创建并编辑.env文件配置连接信息
6. 创建初始数据库迁移：
   ```bash
   alembic revision --autogenerate -m "Initial migration"
   ```
7. 应用迁移：
   ```bash
   alembic upgrade head
   ```
8. 启动应用：
   ```bash
   uvicorn app.main:app --reload
   ```
9. 在另一个终端启动Celery工作进程：
   ```bash
   celery -A app.tasks.worker worker -l info
   ```

4. 功能测试
-----------

- 访问API文档：http://localhost:8000/docs
- 注册新用户：http://localhost:8000/register
- 登录系统：http://localhost:8000/login
- 查看文章列表：http://localhost:8000/
- 创建新文章：通过API或仪表盘功能

5. 后续开发
-----------

1. 完善前端界面，添加更多交互功能
2. 实现更复杂的权限控制系统
3. 添加搜索功能（考虑使用Elasticsearch）
4. 实现多语言支持
5. 添加文件上传功能
6. 实现社交分享和评论审核系统
"""

