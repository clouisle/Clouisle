"""
Redis 数据库工具

功能: 连接 Redis 数据库，支持 scan (键扫描与类型查看)、get (单键详细信息/内容获取)、command (执行白名单命令)。

实际执行入口为 db_executor.execute_database_tool（自定义 `database` 工具类型），凭证来自
工具的业务编排配置 (tools_config.database_config)，不暴露给 LLM 工具参数。
"""

from typing import Any

READONLY_COMMANDS = {
    "GET",
    "MGET",
    "HGET",
    "HGETALL",
    "HMGET",
    "HEXISTS",
    "HLEN",
    "HKEYS",
    "HVALS",
    "LRANGE",
    "LLEN",
    "LINDEX",
    "SMEMBERS",
    "SCARD",
    "SISMEMBER",
    "ZRANGE",
    "ZCARD",
    "ZSCORE",
    "ZRANK",
    "TYPE",
    "TTL",
    "PTTL",
    "EXISTS",
    "STRLEN",
    "PING",
}

DANGEROUS_COMMANDS = {
    "FLUSHALL",
    "FLUSHDB",
    "CONFIG",
    "SHUTDOWN",
    "EVAL",
    "EVALSHA",
    "SCRIPT",
    "DEBUG",
    "SAVE",
    "BGSAVE",
    "BGREWRITEAOF",
    "SLAVEOF",
    "REPLICAOF",
    "KEYS",
}


def _get_redis_client(db_config: dict[str, Any] | None):
    import redis.asyncio as aioredis

    config = dict(db_config or {})

    url = config.get("url")
    if url:
        return aioredis.from_url(url, decode_responses=True)

    host = config.get("host") or "127.0.0.1"
    port = int(config.get("port") or 6379)
    db = int(config.get("db") or 0)
    password = config.get("password") or None
    username = config.get("username") or None

    return aioredis.Redis(
        host=host,
        port=port,
        db=db,
        username=username,
        password=password,
        decode_responses=True,
        socket_connect_timeout=5.0,
        socket_timeout=10.0,
    )
