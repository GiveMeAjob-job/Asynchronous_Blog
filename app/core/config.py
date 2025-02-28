from typing import Optional, Dict, Any, Union
from pydantic import BaseSettings, EmailStr, PostgresDsn, RedisDsn, validator


class Settings(BaseSettings):
    PROJECT_NAME: str = "Async Blog"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 数据库配置
    DATABASE_URL: PostgresDsn

    # Redis配置
    REDIS_URL: RedisDsn

    # RabbitMQ配置
    RABBITMQ_URL: str

    # 邮件配置
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[EmailStr] = None
    MAIL_PORT: Optional[int] = 587
    MAIL_SERVER: Optional[str] = None
    MAIL_TLS: bool = True
    MAIL_SSL: bool = False

    # 环境设置
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
