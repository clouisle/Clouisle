"""
Workflow caching layer.

Provides caching for workflow definitions, execution plans, and node results
to improve performance and reduce database/computation overhead.
"""

import json
import hashlib
import logging
from typing import TypeVar, Callable, cast
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps

from app.core.redis import get_redis
from .serialization import dumps_value, loads_value
from .types import WorkflowValue

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Cache configuration."""

    # Default TTLs in seconds
    workflow_definition_ttl: int = 300  # 5 minutes
    execution_plan_ttl: int = 300  # 5 minutes
    node_result_ttl: int = 60  # 1 minute
    llm_response_ttl: int = 3600  # 1 hour (for identical prompts)
    tool_result_ttl: int = 300  # 5 minutes

    # Cache key prefixes
    prefix: str = "wf:cache:"

    # Maximum cache sizes (for LRU eviction)
    max_workflow_cache: int = 1000
    max_plan_cache: int = 1000
    max_node_cache: int = 10000


# Global cache config
CACHE_CONFIG = CacheConfig()


class CacheKey:
    """Cache key generator."""

    @staticmethod
    def workflow(workflow_id: str, version: str | None = None) -> str:
        """Generate cache key for workflow definition."""
        if version:
            return f"{CACHE_CONFIG.prefix}workflow:{workflow_id}:{version}"
        return f"{CACHE_CONFIG.prefix}workflow:{workflow_id}"

    @staticmethod
    def execution_plan(workflow_id: str, definition_hash: str) -> str:
        """Generate cache key for execution plan."""
        return f"{CACHE_CONFIG.prefix}plan:{workflow_id}:{definition_hash}"

    @staticmethod
    def node_result(
        node_id: str,
        node_type: str,
        inputs_hash: str,
    ) -> str:
        """Generate cache key for node result."""
        return f"{CACHE_CONFIG.prefix}node:{node_type}:{node_id}:{inputs_hash}"

    @staticmethod
    def llm_response(
        model: str,
        prompt_hash: str,
        params_hash: str,
    ) -> str:
        """Generate cache key for LLM response."""
        return f"{CACHE_CONFIG.prefix}llm:{model}:{prompt_hash}:{params_hash}"

    @staticmethod
    def tool_result(
        tool_id: str,
        inputs_hash: str,
    ) -> str:
        """Generate cache key for tool result."""
        return f"{CACHE_CONFIG.prefix}tool:{tool_id}:{inputs_hash}"


def hash_content(content: WorkflowValue) -> str:
    """Generate a hash for any content."""
    if isinstance(content, str):
        data = content.encode()
    else:
        data = json.dumps(content, sort_keys=True, default=str).encode()
    return hashlib.sha256(data).hexdigest()[:16]


class WorkflowCache:
    """
    Workflow cache manager.

    Provides caching for:
    - Workflow definitions
    - Execution plans
    - Node results (for deterministic nodes)
    - LLM responses (for identical prompts)
    - Tool results

    Example:
        cache = WorkflowCache()

        # Cache workflow definition
        await cache.set_workflow(workflow_id, definition)
        definition = await cache.get_workflow(workflow_id)

        # Cache execution plan
        await cache.set_plan(workflow_id, definition, plan)
        plan = await cache.get_plan(workflow_id, definition)
    """

    def __init__(self, config: CacheConfig | None = None):
        """Initialize cache manager."""
        self.config = config or CACHE_CONFIG
        self._redis = None
        self._local_cache: dict[str, tuple[WorkflowValue, datetime]] = {}
        self._local_cache_max = 100  # Local cache size limit

    async def _get_redis(self):
        """Get Redis connection."""
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    def _get_local(self, key: str) -> WorkflowValue | None:
        """Get value from local cache."""
        if key in self._local_cache:
            value, expires = self._local_cache[key]
            if datetime.utcnow() < expires:
                return value
            else:
                del self._local_cache[key]
        return None

    def _set_local(self, key: str, value: WorkflowValue, ttl: int):
        """Set value in local cache."""
        # Simple LRU: remove oldest if full
        if len(self._local_cache) >= self._local_cache_max:
            oldest_key = min(
                self._local_cache.keys(),
                key=lambda k: self._local_cache[k][1],
            )
            del self._local_cache[oldest_key]

        expires = datetime.utcnow() + timedelta(seconds=ttl)
        self._local_cache[key] = (value, expires)

    # Workflow Definition Cache

    async def get_workflow(
        self,
        workflow_id: str,
        version: str | None = None,
    ) -> dict | None:
        """
        Get cached workflow definition.

        Args:
            workflow_id: Workflow UUID
            version: Optional version identifier

        Returns:
            Workflow definition dict or None if not cached
        """
        key = CacheKey.workflow(workflow_id, version)

        # Check local cache first
        local = self._get_local(key)
        if local is not None:
            logger.debug(f"Workflow cache hit (local): {workflow_id}")
            return cast("dict | None", local) if isinstance(local, dict) else None

        # Check Redis
        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                definition = loads_value(data)
                self._set_local(key, definition, self.config.workflow_definition_ttl)
                logger.debug(f"Workflow cache hit (redis): {workflow_id}")
                return (
                    cast("dict | None", definition)
                    if isinstance(definition, dict)
                    else None
                )
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set_workflow(
        self,
        workflow_id: str,
        definition: dict,
        version: str | None = None,
        ttl: int | None = None,
    ) -> None:
        """
        Cache workflow definition.

        Args:
            workflow_id: Workflow UUID
            definition: Workflow definition dict
            version: Optional version identifier
            ttl: Optional TTL override
        """
        key = CacheKey.workflow(workflow_id, version)
        ttl = ttl or self.config.workflow_definition_ttl

        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl, dumps_value(definition))
            self._set_local(key, definition, ttl)
            logger.debug(f"Workflow cached: {workflow_id}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    async def invalidate_workflow(
        self,
        workflow_id: str,
        version: str | None = None,
    ) -> None:
        """Invalidate workflow cache."""
        key = CacheKey.workflow(workflow_id, version)

        try:
            redis = await self._get_redis()
            await redis.delete(key)
            if key in self._local_cache:
                del self._local_cache[key]
            logger.debug(f"Workflow cache invalidated: {workflow_id}")
        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")

    # Execution Plan Cache

    async def get_plan(
        self,
        workflow_id: str,
        definition: dict,
    ) -> dict | None:
        """
        Get cached execution plan.

        Args:
            workflow_id: Workflow UUID
            definition: Workflow definition (for hash)

        Returns:
            Execution plan dict or None if not cached
        """
        def_hash = hash_content(definition)
        key = CacheKey.execution_plan(workflow_id, def_hash)

        # Check local cache
        local = self._get_local(key)
        if local is not None:
            logger.debug(f"Plan cache hit (local): {workflow_id}")
            return cast("dict | None", local) if isinstance(local, dict) else None

        # Check Redis
        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                plan = loads_value(data)
                self._set_local(key, plan, self.config.execution_plan_ttl)
                logger.debug(f"Plan cache hit (redis): {workflow_id}")
                return cast("dict | None", plan) if isinstance(plan, dict) else None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set_plan(
        self,
        workflow_id: str,
        definition: dict,
        plan: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache execution plan."""
        def_hash = hash_content(definition)
        key = CacheKey.execution_plan(workflow_id, def_hash)
        ttl = ttl or self.config.execution_plan_ttl

        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl, dumps_value(plan))
            self._set_local(key, plan, ttl)
            logger.debug(f"Plan cached: {workflow_id}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    # Node Result Cache (for deterministic nodes)

    async def get_node_result(
        self,
        node_id: str,
        node_type: str,
        inputs: dict,
    ) -> dict | None:
        """
        Get cached node result.

        Only works for deterministic nodes (code, template, condition).

        Args:
            node_id: Node ID
            node_type: Node type
            inputs: Node inputs (for hash)

        Returns:
            Node outputs dict or None if not cached
        """
        # Only cache deterministic nodes
        if node_type not in ("code", "template", "condition", "variable_assignment"):
            return None

        inputs_hash = hash_content(inputs)
        key = CacheKey.node_result(node_id, node_type, inputs_hash)

        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                logger.debug(f"Node cache hit: {node_id}")
                result = loads_value(data)
                if isinstance(result, dict):
                    return result
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set_node_result(
        self,
        node_id: str,
        node_type: str,
        inputs: dict,
        outputs: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache node result."""
        # Only cache deterministic nodes
        if node_type not in ("code", "template", "condition", "variable_assignment"):
            return

        inputs_hash = hash_content(inputs)
        key = CacheKey.node_result(node_id, node_type, inputs_hash)
        ttl = ttl or self.config.node_result_ttl

        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl, dumps_value(outputs))
            logger.debug(f"Node result cached: {node_id}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    # LLM Response Cache

    async def get_llm_response(
        self,
        model: str,
        messages: list[dict],
        params: dict | None = None,
    ) -> dict | None:
        """
        Get cached LLM response.

        Args:
            model: Model name
            messages: Chat messages
            params: Generation parameters

        Returns:
            LLM response dict or None if not cached
        """
        prompt_hash = hash_content(cast("WorkflowValue", messages))
        params_hash = hash_content(cast("WorkflowValue", params or {}))
        key = CacheKey.llm_response(model, prompt_hash, params_hash)

        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                logger.debug(f"LLM cache hit: {model}")
                result = loads_value(data)
                if isinstance(result, dict):
                    return result
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set_llm_response(
        self,
        model: str,
        messages: list[dict],
        response: dict,
        params: dict | None = None,
        ttl: int | None = None,
    ) -> None:
        """Cache LLM response."""
        prompt_hash = hash_content(cast("WorkflowValue", messages))
        params_hash = hash_content(cast("WorkflowValue", params or {}))
        key = CacheKey.llm_response(model, prompt_hash, params_hash)
        ttl = ttl or self.config.llm_response_ttl

        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl, dumps_value(response))
            logger.debug(f"LLM response cached: {model}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    # Tool Result Cache

    async def get_tool_result(
        self,
        tool_id: str,
        inputs: dict,
    ) -> dict | None:
        """Get cached tool result."""
        inputs_hash = hash_content(inputs)
        key = CacheKey.tool_result(tool_id, inputs_hash)

        try:
            redis = await self._get_redis()
            data = await redis.get(key)
            if data:
                logger.debug(f"Tool cache hit: {tool_id}")
                result = loads_value(data)
                if isinstance(result, dict):
                    return result
        except Exception as e:
            logger.warning(f"Cache get error: {e}")

        return None

    async def set_tool_result(
        self,
        tool_id: str,
        inputs: dict,
        outputs: dict,
        ttl: int | None = None,
    ) -> None:
        """Cache tool result."""
        inputs_hash = hash_content(inputs)
        key = CacheKey.tool_result(tool_id, inputs_hash)
        ttl = ttl or self.config.tool_result_ttl

        try:
            redis = await self._get_redis()
            await redis.setex(key, ttl, dumps_value(outputs))
            logger.debug(f"Tool result cached: {tool_id}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")

    # Cache Statistics

    async def get_stats(self) -> dict:
        """Get cache statistics."""
        try:
            redis = await self._get_redis()

            # Count keys by type
            workflow_keys = await redis.keys(f"{self.config.prefix}workflow:*")
            plan_keys = await redis.keys(f"{self.config.prefix}plan:*")
            node_keys = await redis.keys(f"{self.config.prefix}node:*")
            llm_keys = await redis.keys(f"{self.config.prefix}llm:*")
            tool_keys = await redis.keys(f"{self.config.prefix}tool:*")

            return {
                "workflow_count": len(workflow_keys),
                "plan_count": len(plan_keys),
                "node_count": len(node_keys),
                "llm_count": len(llm_keys),
                "tool_count": len(tool_keys),
                "local_cache_size": len(self._local_cache),
            }
        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return {}

    async def clear_all(self) -> int:
        """Clear all workflow cache entries."""
        try:
            redis = await self._get_redis()
            keys = await redis.keys(f"{self.config.prefix}*")
            if keys:
                await redis.delete(*keys)
            self._local_cache.clear()
            logger.info(f"Cache cleared: {len(keys)} keys")
            return len(keys)
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return 0


def cached(
    key_func: Callable[..., str],
    ttl: int = 300,
    cache_none: bool = False,
):
    """
    Decorator for caching async function results.

    Args:
        key_func: Function to generate cache key from args
        ttl: Time to live in seconds
        cache_none: Whether to cache None results

    Example:
        @cached(
            key_func=lambda workflow_id: f"workflow:{workflow_id}",
            ttl=300,
        )
        async def get_workflow(workflow_id: str) -> dict:
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = key_func(*args, **kwargs)
            full_key = f"{CACHE_CONFIG.prefix}func:{key}"

            # Try to get from cache
            try:
                redis = await get_redis()
                data = await redis.get(full_key)
                if data is not None:
                    return loads_value(data)
            except Exception:
                pass

            # Call function
            result = await func(*args, **kwargs)

            # Cache result
            if result is not None or cache_none:
                try:
                    redis = await get_redis()
                    await redis.setex(full_key, ttl, dumps_value(result))
                except Exception:
                    pass

            return result

        return wrapper

    return decorator


# Global cache instance
_cache_instance: WorkflowCache | None = None


def get_workflow_cache() -> WorkflowCache:
    """Get global workflow cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = WorkflowCache()
    return _cache_instance
