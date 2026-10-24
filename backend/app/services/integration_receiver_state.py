"""Ephemeral receiver ownership/status; business receipts remain in PostgreSQL."""

import hashlib
import json

import redis.asyncio as redis

from app.core.config import settings
from app.models.integration import Integration
from app.services.feishu_agent_events import get_connection_mode
from app.services.integration_features import active_features

RECEIVER_TTL_SECONDS = 15
RECONCILE_SECONDS = 2
REFRESH_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value or cjson.decode(value).owner ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""
RELEASE_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value or cjson.decode(value).owner ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


def receiver_redis():
    """Each lifecycle thread/process owns its client and bounded I/O."""
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def receiver_key(integration_id) -> str:
    return f"integration:receiver:feishu:{integration_id}"


def receiver_fingerprint(integration: Integration) -> str:
    value = json.dumps(
        [
            str(integration.id),
            integration.config.get("app_id"),
            integration.credentials.get("app_secret"),
            get_connection_mode(integration),
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


def configured_receiver(integration: Integration | None) -> bool:
    return bool(
        integration
        and "agent_chat" in active_features(integration)
        and get_connection_mode(integration) == "long_connection"
        and integration.config.get("app_id")
        and integration.credentials.get("app_secret")
    )


async def receiver_status(integration: Integration) -> dict:
    if "agent_chat" not in active_features(integration):
        return {"state": "disabled", "managed": False}
    if get_connection_mode(integration) == "callback":
        return {"state": "callback", "managed": False}
    if not configured_receiver(integration):
        return {"state": "unconfigured", "managed": True}
    client = receiver_redis()
    try:
        value = await client.get(receiver_key(integration.id))
        presence = json.loads(value) if value else {}
        if not isinstance(presence, dict):
            return {"state": "error", "managed": True}
        state = presence.get("state")
        if presence.get("fingerprint") != receiver_fingerprint(integration):
            state = "waiting"
        if state not in {"starting", "connected", "reconnecting", "error"}:
            state = "waiting"
        return {"state": state, "managed": True}
    except (redis.RedisError, ValueError, TypeError):
        return {"state": "error", "managed": True}
    finally:
        await client.aclose()
