from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.services.workflow.cache import CacheKey, WorkflowCache, hash_content
from app.services.workflow.serialization import dumps_value


def test_cache_key_builders_include_all_identifiers():
    assert CacheKey.workflow("workflow") == "wf:cache:workflow:workflow"
    assert CacheKey.workflow("workflow", "v2") == "wf:cache:workflow:workflow:v2"
    assert (
        CacheKey.execution_plan("workflow", "definition")
        == "wf:cache:plan:workflow:definition"
    )
    assert (
        CacheKey.node_result("node", "llm", "inputs") == "wf:cache:node:llm:node:inputs"
    )
    assert (
        CacheKey.llm_response("model", "prompt", "params")
        == "wf:cache:llm:model:prompt:params"
    )
    assert CacheKey.tool_result("tool", "inputs") == "wf:cache:tool:tool:inputs"


def test_hash_content_is_stable_for_equivalent_objects():
    assert hash_content({"a": 1, "nested": {"b": [2, 3]}}) == hash_content(
        {"nested": {"b": [2, 3]}, "a": 1}
    )


def test_hash_content_distinguishes_values_and_hashes_raw_strings():
    assert hash_content({"value": 1}) != hash_content({"value": 2})
    assert hash_content("hello") == "2cf24dba5fb0a30e"




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


@pytest.mark.asyncio
async def test_workflow_cache_hit_miss_and_invalidation(cache, redis):
    key = CacheKey.workflow("workflow-1", "v1")
    redis.get.side_effect = [None, dumps_value({"nodes": []})]

    assert await cache.get_workflow("workflow-1", "v1") is None
    assert await cache.get_workflow("workflow-1", "v1") == {"nodes": []}

    await cache.invalidate_workflow("workflow-1", "v1")

    redis.get.assert_awaited_with(key)
    redis.delete.assert_awaited_once_with(key)
    assert key not in cache._local_cache


@pytest.mark.asyncio
async def test_invalid_redis_payload_is_cache_miss(cache, redis):
    redis.get.return_value = "invalid-payload"

    assert await cache.get_workflow("workflow-1") is None


@pytest.mark.asyncio
async def test_set_workflow_uses_expected_key_and_ttl(cache, redis):
    definition = {"nodes": []}

    await cache.set_workflow("workflow-1", definition, version="v1", ttl=42)

    redis.setex.assert_awaited_once_with(
        CacheKey.workflow("workflow-1", "v1"), 42, dumps_value(definition)
    )


@pytest.mark.asyncio
async def test_plan_node_llm_and_tool_cache_methods(cache, redis):
    definition = {"nodes": []}
    plan = {"order": ["start"]}
    inputs = {"text": "hello"}
    messages = [{"role": "user", "content": "hello"}]
    response = {"content": "hi"}
    node_key = CacheKey.node_result("node-1", "code", hash_content(inputs))
    plan_key = CacheKey.execution_plan("workflow-1", hash_content(definition))
    llm_key = CacheKey.llm_response(
        "model-1", hash_content(messages), hash_content({"temperature": 0})
    )
    tool_key = CacheKey.tool_result("tool-1", hash_content(inputs))
    redis.get.side_effect = [
        dumps_value(plan),
        dumps_value({"result": "node"}),
        dumps_value(response),
        dumps_value({"result": "tool"}),
    ]

    assert await cache.get_plan("workflow-1", definition) == plan
    assert await cache.get_node_result("node-1", "code", inputs) == {"result": "node"}
    assert (
        await cache.get_llm_response("model-1", messages, {"temperature": 0})
        == response
    )
    assert await cache.get_tool_result("tool-1", inputs) == {"result": "tool"}

    await cache.set_plan("workflow-1", definition, plan)
    await cache.set_node_result("node-1", "code", inputs, {"result": "node"})
    await cache.set_llm_response("model-1", messages, response, {"temperature": 0})
    await cache.set_tool_result("tool-1", inputs, {"result": "tool"})

    redis.get.assert_has_awaits(
        [
            call(plan_key),
            call(node_key),
            call(llm_key),
            call(tool_key),
        ]
    )
    redis.setex.assert_has_awaits(
        [
            call(plan_key, cache.config.execution_plan_ttl, dumps_value(plan)),
            call(
                node_key, cache.config.node_result_ttl, dumps_value({"result": "node"})
            ),
            call(llm_key, cache.config.llm_response_ttl, dumps_value(response)),
            call(
                tool_key, cache.config.tool_result_ttl, dumps_value({"result": "tool"})
            ),
        ]
    )


@pytest.mark.asyncio
async def test_node_cache_skips_non_deterministic_nodes(cache, redis):
    assert await cache.get_node_result("node-1", "llm", {"text": "hello"}) is None

    await cache.set_node_result("node-1", "llm", {"text": "hello"}, {"content": "hi"})

    redis.get.assert_not_awaited()
    redis.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_stats_and_clear_all(cache, redis):
    redis.keys.side_effect = [
        ["workflow"],
        ["plan", "plan-2"],
        [],
        ["llm"],
        ["tool"],
        ["workflow", "plan"],
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

    redis.delete.assert_awaited_once_with("workflow", "plan")
    assert cache._local_cache == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("get_workflow", ("workflow-1",), None),
        ("set_workflow", ("workflow-1", {}), None),
        ("invalidate_workflow", ("workflow-1",), None),
        ("get_plan", ("workflow-1", {}), None),
        ("set_plan", ("workflow-1", {}, {}), None),
        ("get_node_result", ("node-1", "code", {}), None),
        ("set_node_result", ("node-1", "code", {}, {}), None),
        ("get_llm_response", ("model-1", []), None),
        ("set_llm_response", ("model-1", [], {}), None),
        ("get_tool_result", ("tool-1", {}), None),
        ("set_tool_result", ("tool-1", {}, {}), None),
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
