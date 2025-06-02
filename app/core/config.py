# app/core/config.py
from typing import Optional, List, Union
from pydantic import EmailStr, validator, Field
from pydantic_settings import BaseSettings
import secrets


class Settings(BaseSettings):
    # 基本配置
    PROJECT_NAME: str = "Async Blog"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = Field("development", env="ENVIRONMENT")
    DEBUG: bool = Field(False, env="DEBUG")

    # 安全配置
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS配置
    CORS_ORIGINS: List[str] = Field(
        ["http://localhost:3000", "http://localhost:8000"],
        env="CORS_ORIGINS"
    )
    ALLOWED_HOSTS: List[str] = Field(["*"], env="ALLOWED_HOSTS")

    # 数据库配置 - 使用字符串类型避免 PostgresDsn 问题
    DATABASE_URL: str = Field(
        "postgresql+asyncpg://postgres:postgres@db:5432/async_blog",
        env="DATABASE_URL"
    )
    DB_POOL_SIZE: int = Field(20, env="DB_POOL_SIZE")
    DB_MAX_OVERFLOW: int = Field(10, env="DB_MAX_OVERFLOW")
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 3600

    # Redis配置 - 使用字符串类型避免 RedisDsn 问题
    REDIS_URL: str = Field(
        "redis://redis:6379/0",
        env="REDIS_URL"
    )
    REDIS_MAX_CONNECTIONS: int = Field(50, env="REDIS_MAX_CONNECTIONS")
    CACHE_TTL: int = Field(3600, env="CACHE_TTL")

    # RabbitMQ配置
    RABBITMQ_URL: str = Field(
        "amqp://guest:guest@rabbitmq:5672//",
        env="RABBITMQ_URL"
    )

    # Celery配置
    CELERY_BROKER_URL: Optional[str] = Field(None, env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: Optional[str] = Field(None, env="CELERY_RESULT_BACKEND")

    @validator("CELERY_BROKER_URL", pre=True)
    def set_celery_broker(cls, v, values):
        if v is None:
            return values.get("RABBITMQ_URL")
        return v

    @validator("CELERY_RESULT_BACKEND", pre=True)
    def set_celery_backend(cls, v, values):
        if v is None:
            redis_url = values.get("REDIS_URL", "")
            # 使用不同的 Redis 数据库存储 Celery 结果
            if redis_url and "/0" in redis_url:
                return redis_url.replace("/0", "/1")
        return v

    # 邮件配置
    MAIL_USERNAME: Optional[str] = Field(None, env="MAIL_USERNAME")
    MAIL_PASSWORD: Optional[str] = Field(None, env="MAIL_PASSWORD")
    MAIL_FROM: Optional[EmailStr] = Field(None, env="MAIL_FROM")
    MAIL_PORT: int = Field(587, env="MAIL_PORT")
    MAIL_SERVER: Optional[str] = Field(None, env="MAIL_SERVER")
    MAIL_TLS: bool = Field(True, env="MAIL_TLS")
    MAIL_SSL: bool = Field(False, env="MAIL_SSL")

    # 管理员账号配置
    ADMIN_EMAIL: EmailStr = Field("admin@example.com", env="ADMIN_EMAIL")
    ADMIN_USERNAME: str = Field("admin", env="ADMIN_USERNAME")
    ADMIN_PASSWORD: str = Field("Admin123!", env="ADMIN_PASSWORD")

    # 分页配置
    DEFAULT_PAGE_SIZE: int = Field(10, env="DEFAULT_PAGE_SIZE")
    MAX_PAGE_SIZE: int = Field(100, env="MAX_PAGE_SIZE")

    # 文件上传配置
    MAX_UPLOAD_SIZE: int = Field(10485760, env="MAX_UPLOAD_SIZE")  # 10MB
    ALLOWED_EXTENSIONS: List[str] = Field(
        ["jpg", "jpeg", "png", "gif", "webp"],
        env="ALLOWED_EXTENSIONS"
    )
    UPLOAD_DIR: str = Field("uploads", env="UPLOAD_DIR")

    # 限流配置
    RATE_LIMIT_PER_MINUTE: int = Field(60, env="RATE_LIMIT_PER_MINUTE")
    RATE_LIMIT_PER_HOUR: int = Field(1000, env="RATE_LIMIT_PER_HOUR")

    # 日志配置
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # SEO配置
    SITE_NAME: str = Field("Async Blog", env="SITE_NAME")
    SITE_DESCRIPTION: str = Field(
        "一个基于FastAPI的现代异步博客系统",
        env="SITE_DESCRIPTION"
    )
    SITE_KEYWORDS: List[str] = Field(
        ["blog", "fastapi", "async", "python"],
        env="SITE_KEYWORDS"
    )

    # 功能开关
    ENABLE_REGISTRATION: bool = Field(True, env="ENABLE_REGISTRATION")
    ENABLE_COMMENTS: bool = Field(True, env="ENABLE_COMMENTS")
    ENABLE_CACHE: bool = Field(True, env="ENABLE_CACHE")
    ENABLE_RATE_LIMIT: bool = Field(True, env="ENABLE_RATE_LIMIT")

    class Config:
        env_file = ".env"
        case_sensitive = True

    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    @validator("ALLOWED_HOSTS", pre=True)
    def assemble_allowed_hosts(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v

    @validator("ALLOWED_EXTENSIONS", pre=True)
    def assemble_allowed_extensions(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip().lower() for i in v.split(",")]
        return [ext.lower() for ext in v]

    def get_database_url(self, async_mode: bool = True) -> str:
        """获取数据库URL，支持同步和异步模式"""
        # 现在 DATABASE_URL 已经是字符串，可以安全使用 startswith
        url = self.DATABASE_URL

        if async_mode and "postgresql://" in url and "postgresql+asyncpg://" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        elif not async_mode and "postgresql+asyncpg://" in url:
            url = url.replace("postgresql+asyncpg://", "postgresql://")

        return url


settings = Settings()
