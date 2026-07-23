"""Focused residual branch tests for workflow context (issue #255)."""

from unittest.mock import AsyncMock, Mock

import pytest

from app.services.workflow.context import ExecutionContext, _resolve_redis_result
from app.services.workflow.serialization import dumps_value


@pytest.mark.asyncio
async def test_issue255_context_returns_synchronous_redis_result_unchanged():
    value = object()

    assert await _resolve_redis_result(value) is value


@pytest.mark.asyncio
async def test_issue255_context_merges_cached_output_into_non_mapping_redis_value():
    redis = AsyncMock()
    redis.hget.return_value = dumps_value("placeholder")
    context = ExecutionContext("run", redis)
    cached = object()
    context._memory_cache["node"] = {"stream": cached}

    assert await context.get_node_outputs("node") == {"stream": cached}


@pytest.mark.asyncio
async def test_issue255_context_single_name_falls_through_missing_sources():
    redis = AsyncMock()
    redis.hget.return_value = None
    context = ExecutionContext("run", redis)

    assert await context.resolve_variable_ref("{{missing}}") is None


@pytest.mark.asyncio
async def test_issue255_context_lazy_output_without_metadata_persists_only_result():
    from app.services.workflow.lazy_stream import LazyStreamResult

    redis = AsyncMock()
    lazy = Mock(spec=LazyStreamResult)
    lazy.execute = AsyncMock(return_value="complete")
    lazy.reasoning = None
    lazy.usage = None
    context = ExecutionContext("run", redis)
    context.get_node_outputs = AsyncMock(return_value={"text": lazy})
    context.set_node_outputs = AsyncMock()

    assert await context.resolve_variable_ref("{{model.text}}") == "complete"
    context.set_node_outputs.assert_awaited_once_with("model", {"text": "complete"})


@pytest.mark.asyncio
async def test_issue255_context_missing_node_output_variable_returns_none():
    context = ExecutionContext("run", AsyncMock())
    context.get_node_outputs = AsyncMock(return_value={"other": "value"})

    assert await context.resolve_variable_ref("{{node.missing}}") is None


@pytest.mark.asyncio
async def test_issue255_context_rejects_non_list_branch_payload():
    redis = AsyncMock()
    redis.hget.return_value = dumps_value("yes")

    assert await ExecutionContext("run", redis).get_active_branches("condition") is None


@pytest.mark.asyncio
async def test_issue255_context_skips_inactive_edge_before_active_edge():
    context = ExecutionContext("run", AsyncMock())
    context.get_active_branches = AsyncMock(side_effect=[None, ["yes"]])
    context.get_node_outputs = AsyncMock(return_value=None)

    assert await context.should_execute_node(
        "target",
        [
            {"source": "unfinished", "sourceHandle": None},
            {"source": "condition", "sourceHandle": "yes"},
        ],
    )
