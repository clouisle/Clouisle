"""
Redis 连接和 Token 黑名单管理
"""

import redis.asyncio as redis
from typing import Optional

from app.core.config import settings

# Redis 连接池
_redis_pool: Optional[redis.Redis] = None

# Token 黑名单的 key 前缀
TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
# 用户当前会话 key 前缀（用于单一会话模式）
USER_SESSION_PREFIX = "user:session:"


async def get_redis() -> redis.Redis:
    """获取 Redis 连接"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
    return _redis_pool


async def close_redis():
    """关闭 Redis 连接"""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


async def add_token_to_blacklist(token: str, expires_in: int):
    """
    将 token 添加到黑名单

    Args:
        token: JWT token
        expires_in: 过期时间（秒），通常设置为 token 的剩余有效期
    """
    r = await get_redis()
    key = f"{TOKEN_BLACKLIST_PREFIX}{token}"
    await r.setex(key, expires_in, "1")


async def is_token_blacklisted(token: str) -> bool:
    """
    检查 token 是否在黑名单中

    Args:
        token: JWT token

    Returns:
        True 如果 token 在黑名单中
    """
    r = await get_redis()
    key = f"{TOKEN_BLACKLIST_PREFIX}{token}"
    result = await r.exists(key)
    return result > 0


async def set_user_session(user_id: str, token: str, expires_in: int):
    """
    设置用户当前会话（用于单一会话模式）

    Args:
        user_id: 用户 ID
        token: JWT token
        expires_in: 过期时间（秒）
    """
    r = await get_redis()
    key = f"{USER_SESSION_PREFIX}{user_id}"
    await r.setex(key, expires_in, token)


async def get_user_session(user_id: str) -> Optional[str]:
    """
    获取用户当前会话 token

    Args:
        user_id: 用户 ID

    Returns:
        当前有效的 token，如果没有则返回 None
    """
    r = await get_redis()
    key = f"{USER_SESSION_PREFIX}{user_id}"
    return await r.get(key)


async def invalidate_user_session(user_id: str, token_expires_in: int = 86400 * 30):
    """
    使用户当前会话失效（踢出旧会话）

    Args:
        user_id: 用户 ID
        token_expires_in: 旧 token 的剩余有效期估计值（默认30天）
    """
    r = await get_redis()
    key = f"{USER_SESSION_PREFIX}{user_id}"

    # 获取旧 token 并加入黑名单
    old_token = await r.get(key)
    if old_token:
        await add_token_to_blacklist(old_token, token_expires_in)

    # 删除用户会话记录
    await r.delete(key)


async def clear_user_session(user_id: str):
    """
    清除用户会话记录（不加入黑名单，仅清除记录）

    Args:
        user_id: 用户 ID
    """
    r = await get_redis()
    key = f"{USER_SESSION_PREFIX}{user_id}"
    await r.delete(key)
