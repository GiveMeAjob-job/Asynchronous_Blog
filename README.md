# Async Blog

一个基于现代技术栈的异步博客系统，采用 FastAPI、SQLAlchemy、Celery 和 Redis 构建。

## 🚀 项目特性

- **高性能异步 API**：基于 FastAPI 构建
- **现代 ORM**：使用 SQLAlchemy 异步数据库操作
- **分布式任务队列**：Celery 处理后台任务
- **缓存优化**：Redis 性能提升
- **安全认证**：JWT 鉴权系统
- **容器化部署**：Docker Compose 一键部署

## 📦 技术栈

- **后端**：FastAPI, SQLAlchemy
- **异步支持**：asyncio
- **数据库**：PostgreSQL
- **缓存**：Redis
- **任务队列**：Celery, RabbitMQ
- **认证**：JWT
- **依赖管理**：Poetry
- **容器化**：Docker, Docker Compose

## 🛠️ 快速开始

### 先决条件

- Docker & Docker Compose
- Python 3.11+
- Poetry

### 开发环境部署

```bash
# 克隆项目
git clone https://github.com/yourusername/async-blog.git
cd async-blog

# 创建并配置 .env 文件
cp .env.example .env
# 编辑 .env 设置环境变量

# 使用 Docker Compose 启动服务
docker compose up -d

# 创建数据库迁移
docker compose exec web alembic revision --autogenerate -m "Initial migration"

# 应用数据库迁移
docker compose exec web alembic upgrade head
```

### 本地开发

```bash
# 安装 Poetry
pip install poetry

# 安装项目依赖
poetry install

# 激活虚拟环境
poetry shell

# 启动开发服务器
uvicorn app.main:app --reload
```

## 🌐 访问服务

- **Web 应用**：http://localhost:8000
- **API 文档**：http://localhost:8000/docs
- **RabbitMQ 管理**：http://localhost:15672
- **Celery 监控**：http://localhost:5555

## 📂 项目结构

```
async_blog/
├── alembic/              # 数据库迁移
├── app/
│   ├── api/              # API 路由
│   ├── core/             # 核心配置
│   ├── models/           # 数据库模型
│   ├── schemas/          # 数据验证模型
│   ├── services/         # 业务逻辑
│   ├── tasks/            # 后台任务
│   └── templates/        # 前端模板
├── static/               # 静态资源
├── tests/                # 单元测试
└── docker-compose.yml    # 容器编排
```

## 🔧 开发指南

### 数据库迁移

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述变更"

# 应用迁移
alembic upgrade head
```

### 后台任务

```bash
# 启动 Celery worker
celery -A app.tasks.worker worker -l info
```

## 🤝 贡献

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交变更 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 🛡️ 安全

请查看 [SECURITY.md](SECURITY.md) 了解报告安全漏洞的流程。

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🌟 鸣谢

感谢所有为项目做出贡献的开发者和开源社区！
