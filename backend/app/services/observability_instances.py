"""Current API instance presence and explicitly host-scoped psutil samples."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import socket
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

from app.core.config import settings
from app.core.redis import get_redis

try:
    import psutil
except ImportError:  # pragma: no cover - optional runtime dependency
    psutil = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

REGISTRY_PREFIX = "admin:observability:instances:v1"
INDEX_KEY = f"{REGISTRY_PREFIX}:index"
HEARTBEAT_SECONDS = 10
LEASE_SECONDS = 30
FRESH_MILLISECONDS = 30_000
OFFLINE_MILLISECONDS = 60_000
RETENTION_MILLISECONDS = 300_000
REDIS_TIMEOUT_SECONDS = 2.0
SAMPLE_TIMEOUT_SECONDS = 2.0

InstanceState = Literal["healthy", "warning", "unavailable", "stale", "offline"]


class InstanceRow(TypedDict):
    instance_id: str
    name: str
    role: Literal["api"]
    cpu_percent: float | None
    memory_percent: float | None
    metric_scope: Literal["host"]
    observed_at: str | None
    state: InstanceState


class InstanceRegistrySnapshot(TypedDict):
    available: bool
    instances: list[InstanceRow]


# The lease token belongs to one process, not the shared container/Pod identity.
# Publication checks it again after sampling; an expired owner cannot reacquire
# implicitly or overwrite the sample of a process that took over its lease.
_ACQUIRE_SCRIPT = """
local owner = redis.call('GET', KEYS[1])
if owner and owner ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""
_PUBLISH_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
local time = redis.call('TIME')
local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local sample = cjson.decode(ARGV[2])
sample.observed_at_ms = now_ms
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('SET', KEYS[2], cjson.encode(sample), 'PX', ARGV[4])
redis.call('ZADD', KEYS[3], now_ms + tonumber(ARGV[4]), sample.instance_id)
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now_ms)
return 1
"""
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""
_READ_SCRIPT = """
local time = redis.call('TIME')
local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now_ms)
local instances = redis.call('ZRANGE', KEYS[1], 0, -1)
local samples = {}
for _, instance_id in ipairs(instances) do
    local sample = redis.call('GET', ARGV[1] .. instance_id .. ':sample')
    if sample then
        table.insert(samples, {instance_id, sample})
    else
        redis.call('ZREM', KEYS[1], instance_id)
    end
end
return {tostring(now_ms), samples}
"""


def _resolve_identity(
    identity: str | None, name: str | None, hostname: str
) -> tuple[str, str]:
    """Hash the raw identity without exposing it; a label does not change identity."""
    raw_identity = identity or hostname
    return hashlib.sha256(raw_identity.encode()).hexdigest()[:16], name or hostname


def _percent(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) and 0 <= number <= 100 else None


def _sample_state(cpu: float | None, memory: float | None) -> InstanceState:
    if cpu is None or memory is None:
        return "unavailable"
    return "warning" if cpu >= 70 or memory >= 80 else "healthy"


def _instance_state(
    cpu: float | None, memory: float | None, age_ms: int
) -> InstanceState:
    if age_ms > OFFLINE_MILLISECONDS:
        return "offline"
    if age_ms > FRESH_MILLISECONDS:
        return "stale"
    return _sample_state(cpu, memory)


def _decode_instance(
    instance_id: Any, payload: Any, server_time_ms: int
) -> InstanceRow | None:
    """Discard untrustworthy/expired records rather than inventing observations."""
    if isinstance(instance_id, bytes):
        try:
            instance_id = instance_id.decode()
        except UnicodeDecodeError:
            return None
    if (
        not isinstance(instance_id, str)
        or len(instance_id) != 16
        or any(character not in "0123456789abcdef" for character in instance_id)
    ):
        return None
    if not isinstance(payload, (str, bytes)):
        return None
    try:
        sample = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(sample, dict):
        return None
    if (
        sample.get("instance_id") != instance_id
        or sample.get("role") != "api"
        or sample.get("metric_scope") != "host"
        or not isinstance(sample.get("name"), str)
        or not sample["name"]
    ):
        return None
    observed_ms = sample.get("observed_at_ms")
    if (
        isinstance(observed_ms, bool)
        or not isinstance(observed_ms, int)
        or observed_ms < 0
        or observed_ms > server_time_ms
    ):
        return None
    age_ms = server_time_ms - observed_ms
    if age_ms >= RETENTION_MILLISECONDS:
        return None
    try:
        observed_at = datetime.fromtimestamp(observed_ms / 1000, UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None
    cpu = _percent(sample.get("cpu_percent"))
    memory = _percent(sample.get("memory_percent"))
    return {
        "instance_id": instance_id,
        "name": sample["name"],
        "role": "api",
        "cpu_percent": cpu,
        "memory_percent": memory,
        "metric_scope": "host",
        "observed_at": observed_at,
        "state": _instance_state(cpu, memory, age_ms),
    }


def _decode_instances(samples: Sequence[Any], server_time_ms: int) -> list[InstanceRow]:
    instances = []
    for entry in samples:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        row = _decode_instance(entry[0], entry[1], server_time_ms)
        if row is not None:
            instances.append(row)
    return sorted(
        instances, key=lambda row: (row["name"].casefold(), row["instance_id"])
    )


def _sample_host_metrics() -> tuple[float | None, float | None]:
    """psutil system APIs are host scope, not container cgroup accounting."""
    if psutil is None:
        return None, None
    cpu = memory = None
    try:
        cpu = _percent(psutil.cpu_percent(interval=0.1))
    except Exception:
        logger.debug("API instance host CPU sample unavailable", exc_info=True)
    try:
        memory = _percent(psutil.virtual_memory().percent)
    except Exception:
        logger.debug("API instance host memory sample unavailable", exc_info=True)
    return cpu, memory


class ApiInstanceReporter:
    """Elect one reporter per API container/Pod; failures never stop the API."""

    def __init__(
        self,
        *,
        identity: str | None = None,
        name: str | None = None,
        redis: Any | None = None,
    ) -> None:
        self.instance_id, self.name = _resolve_identity(
            settings.OBSERVABILITY_INSTANCE_ID if identity is None else identity,
            settings.OBSERVABILITY_INSTANCE_NAME if name is None else name,
            socket.gethostname(),
        )
        self.owner_id = uuid4().hex
        self._redis = redis
        self._closed = asyncio.Event()
        self._lease_key = f"{REGISTRY_PREFIX}:{self.instance_id}:lease"
        self._sample_key = f"{REGISTRY_PREFIX}:{self.instance_id}:sample"

    async def _client(self) -> Any:
        return self._redis if self._redis is not None else await get_redis()

    async def refresh_once(self) -> bool:
        """Try to elect, sample off-loop, and publish once; false means no publish."""
        if self._closed.is_set():
            return False
        try:
            async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
                redis = await self._client()
                elected = await redis.eval(
                    _ACQUIRE_SCRIPT, 1, self._lease_key, self.owner_id, LEASE_SECONDS
                )
            if not elected or self._closed.is_set():
                return False
            try:
                cpu, memory = await asyncio.wait_for(
                    asyncio.to_thread(_sample_host_metrics), SAMPLE_TIMEOUT_SECONDS
                )
            except TimeoutError:
                cpu = memory = None
            if self._closed.is_set():
                return False
            sample = json.dumps(
                {
                    "instance_id": self.instance_id,
                    "name": self.name,
                    "role": "api",
                    "metric_scope": "host",
                    "cpu_percent": cpu,
                    "memory_percent": memory,
                },
                allow_nan=False,
            )
            async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
                published = await redis.eval(
                    _PUBLISH_SCRIPT,
                    3,
                    self._lease_key,
                    self._sample_key,
                    INDEX_KEY,
                    self.owner_id,
                    sample,
                    LEASE_SECONDS,
                    RETENTION_MILLISECONDS,
                )
            return bool(published)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("API instance heartbeat unavailable", exc_info=True)
            return False

    async def run(self) -> None:
        try:
            while not self._closed.is_set():
                await self.refresh_once()
                try:
                    await asyncio.wait_for(self._closed.wait(), HEARTBEAT_SECONDS)
                except TimeoutError:
                    pass
        finally:
            await self.close()

    async def close(self) -> None:
        """Release only our lease, retaining the last sample for timestamp aging."""
        self._closed.set()
        try:
            async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
                redis = await self._client()
                await redis.eval(_RELEASE_SCRIPT, 1, self._lease_key, self.owner_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("API instance lease release unavailable", exc_info=True)


async def list_api_instances(*, redis: Any | None = None) -> InstanceRegistrySnapshot:
    """Read all retained instances against Redis time within a two-second budget."""
    try:
        async with asyncio.timeout(REDIS_TIMEOUT_SECONDS):
            client = redis if redis is not None else await get_redis()
            reply = await client.eval(_READ_SCRIPT, 1, INDEX_KEY, f"{REGISTRY_PREFIX}:")
        server_time_ms = int(reply[0])
        if server_time_ms < 0 or not isinstance(reply[1], (list, tuple)):
            raise ValueError("Invalid API instance registry snapshot")
        return {
            "available": True,
            "instances": _decode_instances(reply[1], server_time_ms),
        }
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("API instance registry unavailable", exc_info=True)
        return {"available": False, "instances": []}
