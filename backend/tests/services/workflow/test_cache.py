from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.services.workflow import cache as cache_module
from app.services.workflow.cache import CacheKey, WorkflowCache, cached, hash_content
from app.services.workflow.serialization import dumps_value


@pytest.fixture
def redis():
    client = MagicMock()
    client.get = AsyncMock()
    client.setex = AsyncMock()
    client.delete = AsyncMock()
    client.keys = AsyncMock()
    return client


@pytest.fixture
def cache(redis):
    instance = WorkflowCache()
    instance._redis = redis
    return instance


def test_cache_keys_and_hashes_are_stable():
    assert CacheKey.workflow("workflow") == "wf:cache:workflow:workflow"
    assert CacheKey.workflow("workflow", "v2") == "wf:cache:workflow:workflow:v2"
    assert CacheKey.execution_plan("workflow", "definition") == (
        "wf:cache:plan:workflow:definition"
    )
    assert CacheKey.node_result("node", "code", "inputs") == (
        "wf:cache:node:code:node:inputs"
    )
    assert CacheKey.llm_response("model", "prompt", "params") == (
        "wf:cache:llm:model:prompt:params"
    )
    assert CacheKey.tool_result("tool", "inputs") == "wf:cache:tool:tool:inputs"
    assert hash_content("hello") == "2cf24dba5fb0a30e"
    assert hash_content({"a": 1, "b": 2}) == hash_content({"b": 2, "a": 1})


@pytest.mark.asyncio
async def test_redis_is_loaded_lazily():
    instance = WorkflowCache()
    redis = MagicMock()

    with patch.object(cache_module, "get_redis", AsyncMock(return_value=redis)) as get:
        assert await instance._get_redis() is redis
        assert await instance._get_redis() is redis

    get.assert_awaited_once()


def test_local_cache_hit_expiration_and_eviction(cache):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    cache._local_cache_max = 2

    with patch.object(cache_module, "datetime", wraps=datetime) as clock:
        clock.now.return_value = now
        cache._set_local("old", {"value": 1}, 1)
        cache._set_local("new", {"value": 2}, 10)
        assert cache._get_local("old") == {"value": 1}

        clock.now.return_value = now + timedelta(seconds=2)
        assert cache._get_local("old") is None
        assert "old" not in cache._local_cache

        cache._set_local("middle", {"value": 3}, 5)
        cache._set_local("latest", {"value": 4}, 20)

    assert "middle" not in cache._local_cache
    assert set(cache._local_cache) == {"new", "latest"}


@pytest.mark.asyncio
async def test_workflow_local_and_redis_hit_miss_and_invalidation(cache, redis):
    key = CacheKey.workflow("workflow-1", "v1")
    cache._set_local(key, {"source": "local"}, 60)

    assert await cache.get_workflow("workflow-1", "v1") == {"source": "local"}
    redis.get.assert_not_awaited()

    cache._local_cache.clear()
    redis.get.side_effect = [None, dumps_value({"source": "redis"})]
    assert await cache.get_workflow("workflow-1", "v1") is None
    assert await cache.get_workflow("workflow-1", "v1") == {"source": "redis"}
    assert key in cache._local_cache

    await cache.invalidate_workflow("workflow-1", "v1")
    redis.delete.assert_awaited_once_with(key)
    assert key not in cache._local_cache


@pytest.mark.asyncio
async def test_workflow_rejects_non_dict_and_invalid_payload(cache, redis):
    key = CacheKey.workflow("workflow-1")
    cache._set_local(key, ["not-a-dict"], 60)
    assert await cache.get_workflow("workflow-1") is None

    cache._local_cache.clear()
    redis.get.side_effect = [dumps_value(["not-a-dict"]), "invalid-payload"]
    assert await cache.get_workflow("workflow-1") is None
    assert await cache.get_workflow("workflow-1") is None


@pytest.mark.asyncio
async def test_set_workflow_uses_override_and_default_ttls(cache, redis):
    definition = {"nodes": []}

    await cache.set_workflow("workflow-1", definition, version="v1", ttl=42)
    await cache.set_workflow("workflow-2", definition)

    redis.setex.assert_has_awaits(
        [
            call(CacheKey.workflow("workflow-1", "v1"), 42, dumps_value(definition)),
            call(
                CacheKey.workflow("workflow-2"),
                cache.config.workflow_definition_ttl,
                dumps_value(definition),
            ),
        ]
    )


@pytest.mark.asyncio
async def test_plan_local_hit_and_wrong_types_are_misses(cache, redis):
    definition = {"nodes": []}
    key = CacheKey.execution_plan("workflow-1", hash_content(definition))
    cache._set_local(key, {"order": []}, 60)
    assert await cache.get_plan("workflow-1", definition) == {"order": []}

    cache._local_cache[key] = (
        ["not-a-dict"],
        datetime.now(UTC) + timedelta(seconds=60),
    )
    assert await cache.get_plan("workflow-1", definition) is None

    cache._local_cache.clear()
    redis.get.return_value = dumps_value(["not-a-dict"])
    assert await cache.get_plan("workflow-1", definition) is None


@pytest.mark.asyncio
async def test_plan_node_llm_and_tool_setters_use_override_ttls(cache, redis):
    definition = {"nodes": []}
    inputs = {"text": "hello"}
    messages = [{"role": "user", "content": "hello"}]

    await cache.set_plan("workflow", definition, {"order": []}, ttl=1)
    await cache.set_node_result("node", "code", inputs, {"value": 1}, ttl=2)
    await cache.set_llm_response("model", messages, {"content": "hi"}, ttl=3)
    await cache.set_tool_result("tool", inputs, {"value": 2}, ttl=4)

    assert [entry.args[1] for entry in redis.setex.await_args_list] == [1, 2, 3, 4]


@pytest.mark.asyncio
@pytest.mark.parametrize("node_type", ["llm", "agent", "tool"])
async def test_node_cache_skips_non_deterministic_nodes(cache, redis, node_type):
    assert await cache.get_node_result("node", node_type, {}) is None
    await cache.set_node_result("node", node_type, {}, {})

    redis.get.assert_not_awaited()
    redis.setex.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("get_node_result", ("node", "code", {})),
        ("get_llm_response", ("model", [])),
        ("get_tool_result", ("tool", {})),
    ],
)
async def test_result_getters_treat_misses_and_non_dict_values_as_misses(
    cache, redis, method, args
):
    redis.get.side_effect = [None, dumps_value(["not-a-dict"])]

    assert await getattr(cache, method)(*args) is None
    assert await getattr(cache, method)(*args) is None


@pytest.mark.asyncio
async def test_stats_and_clear_all_include_empty_clear_branch(cache, redis):
    redis.keys.side_effect = [
        ["workflow"],
        ["plan", "plan-2"],
        [],
        ["llm"],
        ["tool"],
        ["workflow", "plan"],
        [],
    ]
    cache._set_local("local", {"cached": True}, 60)

    assert await cache.get_stats() == {
        "workflow_count": 1,
        "plan_count": 2,
        "node_count": 0,
        "llm_count": 1,
        "tool_count": 1,
        "local_cache_size": 1,
    }
    assert await cache.clear_all() == 2
    assert await cache.clear_all() == 0
    redis.delete.assert_awaited_once_with("workflow", "plan")
    assert cache._local_cache == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("get_workflow", ("workflow",), None),
        ("set_workflow", ("workflow", {}), None),
        ("invalidate_workflow", ("workflow",), None),
        ("get_plan", ("workflow", {}), None),
        ("set_plan", ("workflow", {}, {}), None),
        ("get_node_result", ("node", "code", {}), None),
        ("set_node_result", ("node", "code", {}, {}), None),
        ("get_llm_response", ("model", []), None),
        ("set_llm_response", ("model", [], {}), None),
        ("get_tool_result", ("tool", {}), None),
        ("set_tool_result", ("tool", {}, {}), None),
        ("get_stats", (), {}),
        ("clear_all", (), 0),
    ],
)
async def test_redis_errors_are_swallowed(cache, redis, method, args, expected):
    redis.get.side_effect = ConnectionError("Redis unavailable")
    redis.setex.side_effect = ConnectionError("Redis unavailable")
    redis.delete.side_effect = ConnectionError("Redis unavailable")
    redis.keys.side_effect = ConnectionError("Redis unavailable")

    assert await getattr(cache, method)(*args) == expected


@pytest.mark.asyncio
async def test_invalidation_error_keeps_local_value(cache, redis):
    key = CacheKey.workflow("workflow")
    cache._set_local(key, {"cached": True}, 60)
    redis.delete.side_effect = ConnectionError("Redis unavailable")

    await cache.invalidate_workflow("workflow")

    assert key in cache._local_cache


@pytest.mark.asyncio
async def test_cached_decorator_hits_cache_and_preserves_metadata(redis):
    redis.get.return_value = dumps_value({"cached": True})
    function = AsyncMock(return_value={"fresh": True})

    @cached(lambda value: value, ttl=42)
    async def decorated(value):
        return await function(value)

    with patch.object(cache_module, "get_redis", AsyncMock(return_value=redis)):
        assert await decorated("key") == {"cached": True}

    assert decorated.__name__ == "decorated"
    function.assert_not_awaited()
    redis.setex.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "cache_none", "set_count"),
    [({"fresh": True}, False, 1), (None, False, 0), (None, True, 1)],
)
async def test_cached_decorator_miss_controls_result_storage(
    redis, result, cache_none, set_count
):
    redis.get.return_value = None
    function = AsyncMock(return_value=result)

    @cached(lambda value: value, ttl=42, cache_none=cache_none)
    async def decorated(value):
        return await function(value)

    with patch.object(cache_module, "get_redis", AsyncMock(return_value=redis)):
        assert await decorated("key") == result

    function.assert_awaited_once_with("key")
    assert redis.setex.await_count == set_count
    if set_count:
        redis.setex.assert_awaited_once_with(
            "wf:cache:func:key", 42, dumps_value(result)
        )


@pytest.mark.asyncio
async def test_cached_decorator_survives_read_and_write_errors(redis):
    redis.get.side_effect = ConnectionError("read failed")
    redis.setex.side_effect = ConnectionError("write failed")

    @cached(lambda: "key")
    async def decorated():
        return {"fresh": True}

    with patch.object(cache_module, "get_redis", AsyncMock(return_value=redis)):
        assert await decorated() == {"fresh": True}

    redis.setex.assert_awaited_once()


def test_global_cache_is_a_singleton():
    with patch.object(cache_module, "_cache_instance", None):
        first = cache_module.get_workflow_cache()
        assert cache_module.get_workflow_cache() is first
