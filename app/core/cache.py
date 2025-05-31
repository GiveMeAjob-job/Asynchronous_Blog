# app/core/cache.py
import json
import hashlib
import pickle
from functools import wraps
from typing import Optional, Callable, Any, Union
from datetime import datetime, timedelta

from app.core.redis import get_redis_connection, set_cache, get_cache, delete_cache
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """生成缓存键"""
    # 将参数转换为字符串并排序以确保一致性
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
    缓存装饰器

    Args:
        prefix: 缓存键前缀
        expire: 过期时间（秒），默认使用配置中的值
        key_func: 自定义键生成函数
        condition: 缓存条件函数，返回 False 时不缓存
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
                # 尝试获取缓存
                cached_value = await get_cache(cache_key)
                if cached_value is not None:
                    logger.debug(f"Cache hit: {cache_key}")
                    return cached_value

                # 执行函数
                result = await func(*args, **kwargs)

                # 设置缓存
                if result is not None:
                    await set_cache(cache_key, result, expire)
                    logger.debug(f"Cache set: {cache_key}")

                return result

            except Exception as e:
                logger.error(f"Cache error: {e}")
                # 缓存错误时直接执行函数
                return await func(*args, **kwargs)

        # 添加缓存管理方法
        wrapper.invalidate = lambda *args, **kwargs: invalidate_cache(prefix, *args, **kwargs)
        wrapper.invalidate_pattern = lambda pattern: invalidate_cache_pattern(pattern)

        return wrapper

    return decorator


async def invalidate_cache(prefix: str, *args, **kwargs):
    """删除特定缓存"""
    cache_key = generate_cache_key(prefix, *args, **kwargs)
    await delete_cache(cache_key)
    logger.debug(f"Cache invalidated: {cache_key}")


async def invalidate_cache_pattern(pattern: str):
    """按模式删除缓存"""
    from app.core.redis import flush_cache_by_pattern
    await flush_cache_by_pattern(pattern)
    logger.debug(f"Cache pattern invalidated: {pattern}")


class CacheManager:
    """缓存管理器"""

    def __init__(self):
        self.cache_info = {}

    async def get_stats(self) -> dict:
        """获取缓存统计信息"""
        redis = await get_redis_connection()
        try:
            info = await redis.info()
            keys_count = await redis.dbsize()

            return {
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "total_keys": keys_count,
                "hit_rate": self._calculate_hit_rate(info),
                "evicted_keys": info.get("evicted_keys", 0),
            }
        finally:
            await redis.close()

    def _calculate_hit_rate(self, info: dict) -> float:
        """计算缓存命中率"""
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        if total == 0:
            return 0.0

        return round((hits / total) * 100, 2)

    async def clear_all(self):
        """清除所有缓存"""
        redis = await get_redis_connection()
        try:
            await redis.flushdb()
            logger.warning("All cache cleared")
        finally:
            await redis.close()

    async def clear_expired(self):
        """清除过期缓存（Redis 自动处理，这里主要用于日志）"""
        stats = await self.get_stats()
        logger.info(f"Cache stats: {stats}")


# 创建全局缓存管理器实例
cache_manager = CacheManager()

# 预定义的缓存装饰器
cache_post_list = cache_key_wrapper("posts:list", expire=300)
cache_post_detail = cache_key_wrapper("posts:detail", expire=600)
cache_user_profile = cache_key_wrapper("users:profile", expire=1800)
cache_categories = cache_key_wrapper("categories:all", expire=3600)
cache_tags = cache_key_wrapper("tags:all", expire=3600)
cache_sidebar = cache_key_wrapper("sidebar:data", expire=1800)
