# app/core/logging.py
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def setup_logging():
    """设置日志配置"""
    # 创建日志目录
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # 清除现有的处理器
    root_logger.handlers = []

    # JSON 格式化器
    json_formatter = jsonlogger.JsonFormatter(
        "%(timestamp)s %(level)s %(name)s %(message)s",
        rename_fields={"timestamp": "@timestamp", "level": "severity"}
    )

    # 标准格式化器
    standard_formatter = logging.Formatter(
        settings.LOG_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        json_formatter if settings.ENVIRONMENT == "production" else standard_formatter
    )
    root_logger.addHandler(console_handler)

    # 文件处理器 - 按大小轮转
    file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(json_formatter)
    file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)

    # 错误日志文件处理器
    error_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setFormatter(json_formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)

    # 访问日志处理器 - 按天轮转
    access_logger = logging.getLogger("access")
    access_handler = TimedRotatingFileHandler(
        log_dir / "access.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    access_handler.setFormatter(json_formatter)
    access_logger.addHandler(access_handler)
    access_logger.setLevel(logging.INFO)

    # 设置第三方库的日志级别
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    logging.getLogger("aioredis").setLevel(logging.WARNING)

    # 自定义日志过滤器
    class HealthCheckFilter(logging.Filter):
        """过滤健康检查的日志"""

        def filter(self, record):
            return "/health" not in record.getMessage()

    # 为访问日志添加过滤器
    for handler in access_logger.handlers:
        handler.addFilter(HealthCheckFilter())

    root_logger.info(
        f"Logging configured - Level: {settings.LOG_LEVEL}, "
        f"Environment: {settings.ENVIRONMENT}"
    )


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志记录器"""
    return logging.getLogger(name)


class LoggerMixin:
    """日志混入类，为类提供日志功能"""

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__module__ + "." + self.__class__.__name__)
