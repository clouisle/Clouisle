from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

CONV_SEQ_KEY_PREFIX = "im:conv:{}:seq"
CONV_LOCK_PREFIX = "im:lock:conv:{}"
CREATE_CONV_LOCK_PREFIX = "im:lock:create_conv:{}:{}:{}"
DEDUP_KEY_PREFIX = "im:dedup:{}"
DEDUP_RESULT_PREFIX = "im:msg_result:{}:{}"
USER_TOTAL_UNREAD_PREFIX = "im:user:{}:total_unread"
USER_CONV_UNREAD_PREFIX = "im:user:{}:conv_unread"
USER_EVENT_CHANNEL_PREFIX = "im:channel:user:{}"

# Lua Script: 原子写入会话剩余未读数，并按差值调整总未读数，避免分布式竞态与负数
_SET_CONV_UNREAD_LUA = """
local conv_hash_key = KEYS[1]
local total_key = KEYS[2]
local conv_field = ARGV[1]
local remaining = tonumber(ARGV[2]) or 0
if remaining < 0 then remaining = 0 end

local current_raw = redis.call('HGET', conv_hash_key, conv_field)
local current_val = tonumber(current_raw) or 0
if current_val < 0 then current_val = 0 end

if remaining ~= current_val then
    if remaining > 0 then
        redis.call('HSET', conv_hash_key, conv_field, remaining)
    else
        redis.call('HDEL', conv_hash_key, conv_field)
    end
    local new_total = redis.call('INCRBY', total_key, remaining - current_val)
    if new_total < 0 then
        redis.call('SET', total_key, 0)
    end
end

if current_val > remaining then
    return current_val - remaining
end
return 0
"""

# Lua Script: 安全释放分布式锁（仅在持有者 token 匹配时才释放，防止误删别人续期的锁）
_RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

# Lua Script: 原子增加会话未读数与总未读数
_INCR_UNREAD_LUA = """
local conv_hash_key = KEYS[1]
local total_key = KEYS[2]
local conv_field = ARGV[1]
local amount = tonumber(ARGV[2]) or 1

redis.call('HINCRBY', conv_hash_key, conv_field, amount)
redis.call('INCRBY', total_key, amount)
return 1
"""


class DistributedLock:
    """基于 Redis 的分布式排它锁，支持租约超时与安全释放 (CAS)。"""

    def __init__(self, key: str, lease_seconds: int = 10):
        self.key = key
        self.lease_seconds = lease_seconds
        self.token = str(
            UUID(int=asyncio.get_event_loop().time().__hash__() & ((1 << 128) - 1))
        )

    async def acquire(self, timeout_seconds: float = 5.0) -> bool:
        """尝试获取分布式锁，支持在 timeout_seconds 内自旋等待。"""
        import time

        deadline = time.time() + timeout_seconds
        try:
            r = await get_redis()
            while time.time() < deadline:
                ok = await r.set(self.key, self.token, ex=self.lease_seconds, nx=True)
                if ok:
                    return True
                await asyncio.sleep(0.05)
            return False
        except Exception as exc:
            logger.warning("DistributedLock acquire error for %s: %s", self.key, exc)
            return True  # 降级放行，避免 Redis 临时不可用时全站死锁

    async def release(self) -> None:
        """安全释放分布式锁。"""
        try:
            r = await get_redis()
            await r.eval(_RELEASE_LOCK_LUA, 1, self.key, self.token)
        except Exception as exc:
            logger.warning("DistributedLock release error for %s: %s", self.key, exc)

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.release()


def get_conversation_lock(conversation_id: UUID) -> DistributedLock:
    """获取指定会话的分布式串行锁，保证高并发发消息时严格有序、无 seq 空洞。"""
    return DistributedLock(CONV_LOCK_PREFIX.format(conversation_id), lease_seconds=10)


def get_create_conversation_lock(team_id: UUID, u1: UUID, u2: UUID) -> DistributedLock:
    """获取创建会话的分布式锁，防止并发创建重复会话。"""
    return DistributedLock(
        CREATE_CONV_LOCK_PREFIX.format(team_id, u1, u2), lease_seconds=5
    )


async def generate_next_seq(conversation_id: UUID) -> int:
    """原子生成会话内的单调自增序号 (seq)。

    高并发下通过 Redis INCR 保证严格有序递增。
    当返回 1 且会话已存在历史消息时，执行一次 DB 校验校准以应对 Redis 重启缓存冷启动。
    """
    conv_id_str = str(conversation_id)
    key = CONV_SEQ_KEY_PREFIX.format(conv_id_str)

    try:
        r = await get_redis()
        seq = await r.incr(key)
        if seq == 1:
            from app.models.im import ImMessage

            max_msg = (
                await ImMessage.filter(conversation_id=conversation_id)
                .order_by("-seq")
                .first()
            )
            if max_msg and max_msg.seq > 0:
                corrected_seq = max_msg.seq + 1
                await r.set(key, corrected_seq)
                return corrected_seq
        return int(seq)
    except Exception as exc:
        logger.warning(
            "Redis generate_next_seq failed for conversation %s: %s, falling back to DB query",
            conv_id_str,
            exc,
        )
        from app.models.im import ImMessage

        max_msg = (
            await ImMessage.filter(conversation_id=conversation_id)
            .order_by("-seq")
            .first()
        )
        return (max_msg.seq + 1) if max_msg else 1


async def acquire_dedup_lock(client_msg_id: str, ttl_seconds: int = 60) -> bool:
    """尝试获取客户端消息去重锁，防止高并发或网络超时重复提交。"""
    if not client_msg_id:
        return True
    key = DEDUP_KEY_PREFIX.format(client_msg_id)
    try:
        r = await get_redis()
        acquired = await r.set(key, "1", ex=ttl_seconds, nx=True)
        return bool(acquired)
    except Exception as exc:
        logger.warning("Redis acquire_dedup_lock failed for %s: %s", client_msg_id, exc)
        return True


async def cache_message_result(
    conversation_id: UUID,
    client_msg_id: str,
    message_data: dict[str, Any],
    ttl_seconds: int = 60,
) -> None:
    """缓存消息投递结果，供同一会话内的并发重试直接命中返回。

    键必须包含会话 ID：客户端的 client_msg_id 只在会话内唯一，跨会话复用时
    不得命中其他会话的消息。
    """
    if not client_msg_id:
        return
    key = DEDUP_RESULT_PREFIX.format(conversation_id, client_msg_id)
    try:
        r = await get_redis()
        await r.setex(key, ttl_seconds, json.dumps(message_data, default=str))
    except Exception as exc:
        logger.warning(
            "Redis cache_message_result failed for %s/%s: %s",
            conversation_id,
            client_msg_id,
            exc,
        )


async def get_cached_message_result(
    conversation_id: UUID, client_msg_id: str
) -> dict[str, Any] | None:
    """获取指定会话内已缓存的消息投递结果。"""
    if not client_msg_id:
        return None
    key = DEDUP_RESULT_PREFIX.format(conversation_id, client_msg_id)
    try:
        r = await get_redis()
        raw = await r.get(key)
        if raw:
            text = raw.decode() if isinstance(raw, bytes) else str(raw)
            return json.loads(text)
    except Exception as exc:
        logger.warning(
            "Redis get_cached_message_result failed for %s/%s: %s",
            conversation_id,
            client_msg_id,
            exc,
        )
    return None


async def release_dedup_lock(client_msg_id: str) -> None:
    """在消息处理遇到非重复错误时主动释放去重锁。"""
    if not client_msg_id:
        return
    key = DEDUP_KEY_PREFIX.format(client_msg_id)
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as exc:
        logger.warning("Redis release_dedup_lock failed for %s: %s", client_msg_id, exc)


async def increment_user_unread(
    user_id: UUID, conversation_id: UUID, amount: int = 1
) -> None:
    """通过 Lua 脚本原子增加接收方的会话未读数及全局总未读数。"""
    user_str = str(user_id)
    conv_str = str(conversation_id)
    total_key = USER_TOTAL_UNREAD_PREFIX.format(user_str)
    conv_hash_key = USER_CONV_UNREAD_PREFIX.format(user_str)

    try:
        r = await get_redis()
        await r.eval(_INCR_UNREAD_LUA, 2, conv_hash_key, total_key, conv_str, amount)
    except Exception as exc:
        logger.warning(
            "Redis increment_user_unread failed for user %s: %s", user_str, exc
        )


async def mark_conversation_read_in_cache(
    user_id: UUID, conversation_id: UUID, remaining_unread: int = 0
) -> int:
    """通过 Lua 脚本原子写入会话的剩余未读数，并按差值调整全局总未读数。

    `remaining_unread` 为该会话在已读游标之后仍然未读的消息数：完全已读时为 0，
    部分已读时由调用方按数据库计数传入。返回本次清掉的未读数（旧值 - 剩余值）。
    """
    user_str = str(user_id)
    conv_str = str(conversation_id)
    total_key = USER_TOTAL_UNREAD_PREFIX.format(user_str)
    conv_hash_key = USER_CONV_UNREAD_PREFIX.format(user_str)

    try:
        r = await get_redis()
        deducted = await r.eval(
            _SET_CONV_UNREAD_LUA,
            2,
            conv_hash_key,
            total_key,
            conv_str,
            max(remaining_unread, 0),
        )
        return int(deducted or 0)
    except Exception as exc:
        logger.warning(
            "Redis mark_conversation_read_in_cache failed for user %s: %s",
            user_str,
            exc,
        )
        return 0


async def get_user_unread_counts(
    user_id: UUID,
) -> tuple[int | None, dict[str, int] | None]:
    """获取用户在缓存中的总未读数及各会话未读数。"""
    user_str = str(user_id)
    total_key = USER_TOTAL_UNREAD_PREFIX.format(user_str)
    conv_hash_key = USER_CONV_UNREAD_PREFIX.format(user_str)

    try:
        r = await get_redis()
        pipe = r.pipeline(transaction=False)
        pipe.get(total_key)
        pipe.hgetall(conv_hash_key)
        results: list[Any] = await pipe.execute()

        raw_total, raw_conv_map = results[0], results[1]
        if raw_total is None or raw_conv_map is None:
            return None, None

        total_unread = max(int(raw_total), 0)
        conv_unread: dict[str, int] = {}
        for k, v in raw_conv_map.items():
            field_name = k.decode() if isinstance(k, bytes) else str(k)
            unread_val = int(v) if v else 0
            conv_unread[field_name] = max(unread_val, 0)
        return total_unread, conv_unread
    except Exception as exc:
        logger.warning(
            "Redis get_user_unread_counts failed for user %s: %s", user_str, exc
        )
        return None, None


async def rebuild_unread_cache(
    user_id: UUID, total_unread: int, conv_unread_map: dict[str, int]
) -> None:
    """从数据库查询结果全量重建用户的未读数缓存。"""
    user_str = str(user_id)
    total_key = USER_TOTAL_UNREAD_PREFIX.format(user_str)
    conv_hash_key = USER_CONV_UNREAD_PREFIX.format(user_str)

    try:
        r = await get_redis()
        pipe = r.pipeline(transaction=True)
        pipe.set(total_key, max(total_unread, 0), ex=86400 * 7)
        pipe.delete(conv_hash_key)
        if conv_unread_map:
            clean_map = {k: max(int(v), 0) for k, v in conv_unread_map.items()}
            pipe.hset(conv_hash_key, mapping=clean_map)
            pipe.expire(conv_hash_key, 86400 * 7)
        await pipe.execute()
    except Exception as exc:
        logger.warning(
            "Redis rebuild_unread_cache failed for user %s: %s", user_str, exc
        )


async def publish_im_event(
    user_id: UUID, event_type: str, data: dict[str, Any]
) -> None:
    """向用户的 Redis 分布式订阅频道广播实时事件（支持跨 API 节点分发）。"""
    user_str = str(user_id)
    channel = USER_EVENT_CHANNEL_PREFIX.format(user_str)
    payload = json.dumps(
        {"type": event_type, "data": data, "timestamp": data.get("created_at")},
        default=str,
    )
    try:
        r = await get_redis()
        await r.publish(channel, payload)
    except Exception as exc:
        logger.warning("Redis publish_im_event failed for user %s: %s", user_str, exc)
