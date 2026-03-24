from typing import List, Optional, Union
import secrets
from urllib.parse import urlparse

from pydantic import EmailStr, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Async Blog"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    APP_BASE_URL: str = "http://localhost:8000"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    SECRET_KEY: Optional[str] = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SESSION_REFRESH_EXPIRE_HOURS: int = 12
    POST_PREVIEW_EXPIRE_HOURS: int = 24

    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]

    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_DOMAIN: Optional[str] = None
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: Optional[bool] = None

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/async_blog"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 3600
    DB_USE_NULL_POOL: bool = False

    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    CACHE_TTL: int = 3600

    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672//"
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[EmailStr] = None
    MAIL_PORT: int = 587
    MAIL_SERVER: Optional[str] = None
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False

    ADMIN_EMAIL: EmailStr = "admin@example.com"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "Admin123!"

    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100

    MAX_UPLOAD_SIZE: int = 10485760
    ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "gif", "webp"]
    UPLOAD_DIR: str = "uploads"

    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    SITE_NAME: str = "Async Blog"
    SITE_DESCRIPTION: str = "一个基于FastAPI的现代异步博客系统"
    SITE_KEYWORDS: List[str] = ["blog", "fastapi", "async", "python"]

    ENABLE_REGISTRATION: bool = True
    REQUIRE_EMAIL_VERIFICATION: Optional[bool] = None
    ENABLE_COMMENTS: bool = True
    ENABLE_CACHE: bool = True
    ENABLE_RATE_LIMIT: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        return list(value)

    @field_validator("ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_allowed_hosts(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return list(value)

    @field_validator("ALLOWED_EXTENSIONS", mode="before")
    @classmethod
    def assemble_allowed_extensions(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return [item.lower() for item in value]

    @model_validator(mode="after")
    def set_runtime_defaults(self) -> "Settings":
        if not self.SECRET_KEY:
            self.SECRET_KEY = secrets.token_urlsafe(32)

        if self.REQUIRE_EMAIL_VERIFICATION is None:
            self.REQUIRE_EMAIL_VERIFICATION = self.is_production

        if self.COOKIE_SECURE is None:
            parsed_base_url = urlparse(self.APP_BASE_URL)
            self.COOKIE_SECURE = parsed_base_url.scheme == "https" or self.is_production

        if self.CELERY_BROKER_URL is None:
            self.CELERY_BROKER_URL = self.RABBITMQ_URL
        if self.CELERY_RESULT_BACKEND is None:
            if self.REDIS_URL.endswith("/0"):
                self.CELERY_RESULT_BACKEND = self.REDIS_URL[:-2] + "/1"
            else:
                self.CELERY_RESULT_BACKEND = self.REDIS_URL
        return self

    @field_validator("COOKIE_SAMESITE")
    @classmethod
    def validate_cookie_samesite(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE 必须是 lax、strict 或 none")
        return normalized

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if not self.is_production:
            return self

        insecure_secrets = {
            "your-secret-key-here",
            "change-me",
            "changeme",
            "secret",
            "dev-secret",
        }
        base_host = urlparse(self.APP_BASE_URL).hostname or ""
        errors: list[str] = []

        if not self.SECRET_KEY or self.SECRET_KEY in insecure_secrets:
            errors.append("SECRET_KEY 必须在生产环境中显式配置且不能使用占位值")
        if base_host in {"localhost", "127.0.0.1", "0.0.0.0"}:
            errors.append("APP_BASE_URL 不能指向 localhost/127.0.0.1")
        if "*" in self.ALLOWED_HOSTS:
            errors.append("ALLOWED_HOSTS 不能在生产环境中使用 *")
        if self.ADMIN_EMAIL == "admin@example.com" or self.ADMIN_USERNAME == "admin" or self.ADMIN_PASSWORD == "Admin123!":
            errors.append("默认管理员账号配置必须在生产环境中替换")
        if self.REQUIRE_EMAIL_VERIFICATION and not self.mail_enabled:
            errors.append("启用邮箱验证时必须完整配置邮件服务")
        if self.COOKIE_SAMESITE == "none" and not self.COOKIE_SECURE:
            errors.append("COOKIE_SAMESITE=none 时必须同时启用 COOKIE_SECURE")

        if errors:
            raise ValueError("生产环境配置无效: " + "；".join(errors))

        return self

    def get_database_url(self, async_mode: bool = True) -> str:
        url = self.DATABASE_URL
        if async_mode and "postgresql://" in url and "postgresql+asyncpg://" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://")
        elif not async_mode and "postgresql+asyncpg://" in url:
            url = url.replace("postgresql+asyncpg://", "postgresql://")
        return url

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def mail_enabled(self) -> bool:
        return bool(
            self.MAIL_SERVER
            and self.MAIL_PORT
            and self.MAIL_FROM
            and self.MAIL_USERNAME
            and self.MAIL_PASSWORD
        )


settings = Settings()
