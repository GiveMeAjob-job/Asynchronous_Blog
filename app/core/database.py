# app/core/database.py - 修复数据库URL处理
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, DeclarativeMeta
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import event, MetaData, text

from app.core.config import settings

logger = logging.getLogger(__name__)

# 自定义元数据命名约定
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=naming_convention)
Base: DeclarativeMeta = declarative_base(metadata=metadata)

# 修复：正确获取数据库URL
database_url = settings.get_database_url(async_mode=True)

# 根据环境选择连接池
if settings.ENVIRONMENT == "testing":
    # 测试环境使用 NullPool
    engine = create_async_engine(
        database_url,
        echo=False,
        poolclass=NullPool,
    )
else:
    # 生产环境使用 QueuePool
    engine = create_async_engine(
        database_url,
        echo=settings.DEBUG,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        pool_recycle=settings.DB_POOL_RECYCLE,
        connect_args={
            "server_settings": {"jit": "off"},
            "command_timeout": 60,
        }
    )

# 创建异步会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    依赖函数，提供数据库会话

    Yields:
        AsyncSession: 数据库会话
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    上下文管理器版本的数据库会话

    Usage:
        async with get_db_context() as db:
            # 使用 db 进行数据库操作
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class DatabaseManager:
    """数据库管理器"""

    @staticmethod
    async def create_all():
        """创建所有表"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created")

    @staticmethod
    async def drop_all():
        """删除所有表（谨慎使用）"""
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            logger.warning("Database tables dropped")

    @staticmethod
    async def check_connection() -> bool:
        """检查数据库连接"""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    @staticmethod
    async def get_pool_status() -> dict:
        """获取连接池状态"""
        pool = engine.pool
        return {
            "size": pool.size() if hasattr(pool, 'size') else "N/A",
            "checked_in": pool.checkedin() if hasattr(pool, 'checkedin') else "N/A",
            "checked_out": pool.checkedout() if hasattr(pool, 'checkedout') else "N/A",
            "overflow": pool.overflow() if hasattr(pool, 'overflow') else "N/A",
            "total": pool.total() if hasattr(pool, 'total') else "N/A",
        }

    @staticmethod
    async def close():
        """关闭数据库连接"""
        await engine.dispose()
        logger.info("Database connections closed")


# 数据库事件监听器 - 修复SQLite检查
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """为 SQLite 设置优化参数"""
    # 修复：检查字符串而不是PostgresDsn对象
    db_url = str(settings.DATABASE_URL)
    if db_url.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


# 创建全局数据库管理器实例
db_manager = DatabaseManager()
