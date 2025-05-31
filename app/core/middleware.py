# app/core/middleware.py
import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


async def log_requests(request: Request, call_next: Callable) -> Response:
    """记录请求日志"""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.time()

    # 记录请求信息
    logger.info(
        f"Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "client_host": request.client.host if request.client else None,
        }
    )

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        # 记录响应信息
        logger.info(
            f"Request completed",
            extra={
                "request_id": request_id,
                "status_code": response.status_code,
                "process_time": f"{process_time:.3f}s",
            }
        )

        # 添加自定义响应头
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}"

        return response

    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"Request failed",
            extra={
                "request_id": request_id,
                "error": str(e),
                "process_time": f"{process_time:.3f}s",
            },
            exc_info=True
        )
        raise


async def add_process_time_header(request: Request, call_next: Callable) -> Response:
    """添加处理时间响应头"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 如果是 HTTPS，添加 HSTS
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


class CompressionMiddleware(BaseHTTPMiddleware):
    """响应压缩中间件"""

    def __init__(self, app: ASGIApp, minimum_size: int = 1000):
        super().__init__(app)
        self.minimum_size = minimum_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # 检查是否需要压缩
        accept_encoding = request.headers.get("accept-encoding", "")
        if (
                "gzip" in accept_encoding
                and response.status_code == 200
                and int(response.headers.get("content-length", 0)) > self.minimum_size
        ):
            # 这里应该实现实际的压缩逻辑
            # 但在生产环境中，通常由 Nginx 等反向代理处理
            pass

        return response


class RateLimitContextMiddleware(BaseHTTPMiddleware):
    """速率限制上下文中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 获取客户端标识
        client_id = request.client.host if request.client else "unknown"
        request.state.client_id = client_id

        response = await call_next(request)

        # 添加速率限制信息到响应头
        if hasattr(request.state, "rate_limit_remaining"):
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)

        return response
