import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# 确保可以导入项目模块
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from app.core.database import Base

# 显式导入所有模型
from app.models.user import User
from app.models.post import Post, post_tag
from app.models.comment import Comment
from app.models.category import Category
from app.models.tag import Tag

target_metadata = Base.metadata

# 导入项目配置
from app.core.config import settings

# 设置数据库连接 URL
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run actual migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """Run migrations in 'online' mode."""
    # 使用异步引擎
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


# 异步运行迁移的包装器
def run_async_migrations():
    """Async migrations wrapper for sync context."""
    asyncio.run(run_migrations_online())


# 根据离线/在线模式选择迁移方法
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_async_migrations()
