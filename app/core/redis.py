# app/core/redis.py
import json
from typing import Any, Optional
import redis.asyncio as redis
from .config import settings

# 创建Redis连接池
redis_pool = redis.ConnectionPool.from_url(str(settings.REDIS_URL))

async def get_redis_connection():
    """获取Redis连接"""
    return redis.Redis(connection_pool=redis_pool)

async def set_cache(key: str, value: Any, expire: int = 3600):
    """设置缓存"""
    r = await get_redis_connection()
    if isinstance(value, (dict, list)):
        value = json.dumps(value)
    await r.set(key, value, ex=expire)
    await r.close()

async def get_cache(key: str) -> Optional[Any]:
    """获取缓存"""
    r = await get_redis_connection()
    value = await r.get(key)
    await r.close()
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value.decode()
    return None

async def delete_cache(key: str):
    """删除缓存"""
    r = await get_redis_connection()
    await r.delete(key)
    await r.close()

async def flush_cache_by_pattern(pattern: str):
    """按模式批量删除缓存"""
    r = await get_redis_connection()
    cursor = b'0'
    while cursor:
        cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await r.delete(*keys)
    await r.close()
