# app/core/cache.py - 简化版本以解决导入问题
import json
import hashlib
from functools import wraps
from typing import Optional, Callable, Any
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# 简单的内存缓存（用于开发环境）
_memory_cache = {}


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    key_parts = [prefix]

    # 处理位置参数
    for arg in args:
        if hasattr(arg, 'id'):
            key_parts.append(f"{type(arg).__name__}:{arg.id}")
        else:
            key_parts.append(str(arg))

    # 处理关键字参数
    for k, v in sorted(kwargs.items()):
        if v is not None:
            key_parts.append(f"{k}:{v}")

    # 生成哈希值以避免键过长
    key_string = ":".join(key_parts)
    if len(key_string) > 200:
        key_hash = hashlib.md5(key_string.encode()).hexdigest()
        return f"{prefix}:hash:{key_hash}"

    return key_string


def cache_key_wrapper(
        prefix: str,
        expire: int = None,
        key_func: Optional[Callable] = None,
        condition: Optional[Callable] = None
):
    """
    缓存装饰器 - 简化版本
    """
    if expire is None:
        expire = settings.CACHE_TTL

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 检查是否启用缓存
            if not settings.ENABLE_CACHE:
                return await func(*args, **kwargs)

            # 检查缓存条件
            if condition and not condition(*args, **kwargs):
                return await func(*args, **kwargs)

            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = generate_cache_key(prefix, *args, **kwargs)

            try:
                # 尝试获取缓存（简化版本 - 使用内存缓存）
                if cache_key in _memory_cache:
                    logger.debug(f"Cache hit: {cache_key}")
                    return _memory_cache[cache_key]

                # 执行函数
                result = await func(*args, **kwargs)

                # 设置缓存（简化版本）
                if result is not None:
                    _memory_cache[cache_key] = result
                    logger.debug(f"Cache set: {cache_key}")

                return result

            except Exception as e:
                logger.error(f"Cache error: {e}")
                # 缓存错误时直接执行函数
                return await func(*args, **kwargs)

        return wrapper

    return decorator


async def invalidate_cache_pattern(pattern: str):
    """按模式删除缓存 - 简化版本"""
    keys_to_delete = [key for key in _memory_cache.keys() if pattern.replace('*', '') in key]
    for key in keys_to_delete:
        del _memory_cache[key]
    logger.debug(f"Cache pattern invalidated: {pattern}")


# 为兼容性提供的函数
async def invalidate_cache(prefix: str, *args, **kwargs):
    """删除特定缓存"""
    cache_key = generate_cache_key(prefix, *args, **kwargs)
    if cache_key in _memory_cache:
        del _memory_cache[cache_key]
    logger.debug(f"Cache invalidated: {cache_key}")


class CacheManager:
    """缓存管理器 - 简化版本"""

    async def get_stats(self) -> dict:
        """获取缓存统计信息"""
        return {
            "total_keys": len(_memory_cache),
            "memory_usage": "N/A",
            "hit_rate": "N/A",
        }

    async def clear_all(self):
        """清除所有缓存"""
        _memory_cache.clear()
        logger.warning("All cache cleared")


# 创建全局缓存管理器实例
cache_manager = CacheManager()
