# Async Blog

一个基于 FastAPI、SQLAlchemy、Jinja2 和 Celery 的博客系统，包含公开博客页、后台管理页和一组 REST API。

## 项目现状

- 支持文章、分类、标签、评论、用户认证与密码重置
- Web 页面和 API 统一挂载在同一个 FastAPI 应用中
- Docker Compose 提供 PostgreSQL、Redis、RabbitMQ、Web、Celery 和 Nginx 运行环境
- 测试已经覆盖应用导入、健康检查、OpenAPI 暴露、JWT 生成和 slug 工具函数

## 技术栈

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- Redis
- Celery + RabbitMQ
- Jinja2
- Poetry

## 快速开始

### 本地开发

```bash
cp .env.example .env
poetry install
poetry shell
uvicorn app.main:app --reload
```

### Docker

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f web
```

默认情况下，Docker 会把 PostgreSQL 暴露到宿主机 `5433` 端口，避免和本机常见的 `5432` 冲突。

## 常用地址

- Web 应用: http://localhost:8000
- API 文档: http://localhost:8000/api/v1/docs
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json
- PostgreSQL: `localhost:5433`
- RabbitMQ 管理台: http://localhost:15672
- Flower: http://localhost:5555

## 项目结构

```text
async_blog/
├── alembic/
├── app/
│   ├── api/
│   ├── core/
│   ├── crud/
│   ├── models/
│   ├── schemas/
│   ├── tasks/
│   ├── templates/
│   └── utils/
├── static/
├── tests/
├── docker-compose.yml
└── pyproject.toml
```

## 测试

```bash
pytest -q
```

## 后台任务

```bash
celery -A app.tasks.worker worker --loglevel=info
celery -A app.tasks.worker beat --loglevel=info
```
