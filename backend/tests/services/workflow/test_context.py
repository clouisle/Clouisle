"""Tests for Redis-backed workflow execution context state."""

import json
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.workflow.context import ExecutionContext
from app.services.workflow.serialization import dumps_value


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expirations: list[tuple[str, int]] = []

    async def set(self, key: str, value: str):
        self.values[key] = value

    async def get(self, key: str):
        return self.values.get(key)

    async def hset(self, key: str, field=None, value=None, *, mapping=None):
        target = self.hashes.setdefault(key, {})
        if mapping is not None:
            target.update({name: str(item) for name, item in mapping.items()})
        elif field is not None:
            target[field] = value

    async def hget(self, key: str, field: str):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key: str):
        return dict(self.hashes.get(key, {}))

    async def expire(self, key: str, seconds: int):
        self.expirations.append((key, seconds))

    async def publish(self, key: str, value: str):
        self.published = (key, value)

    async def delete(self, key: str):
        self.values.pop(key, None)
        self.hashes.pop(key, None)


@pytest.fixture
def redis_client() -> Any:
    return FakeRedis()


@pytest.fixture
def context(redis_client: Any) -> ExecutionContext:
    return ExecutionContext(run_id=str(uuid4()), redis_client=redis_client)


class TestExecutionContextCreation:
    @pytest.mark.asyncio
    async def test_create_context(self, redis_client):
        run_id = str(uuid4())
        workflow_id = str(uuid4())
        user_id = str(uuid4())
        context = await ExecutionContext.create(
            run_id, redis_client, workflow_id, user_id=user_id, ttl=60
        )
        assert context.run_id == run_id
        assert context._system_variables["workflow_id"] == workflow_id
        assert context._system_variables["user_id"] == user_id
        assert await context.get_status() == "pending"
        assert len(redis_client.expirations) == 5

    @pytest.mark.asyncio
    async def test_load_context(self, redis_client):
        run_id = str(uuid4())
        workflow_id = str(uuid4())
        await redis_client.hset(
            ExecutionContext.META_KEY.format(run_id=run_id),
            mapping={"workflow_id": workflow_id, "user_id": "user-1"},
        )
        context = await ExecutionContext.load(run_id, redis_client)
        assert context._system_variables["workflow_id"] == workflow_id
        assert context._system_variables["user_id"] == "user-1"

    @pytest.mark.asyncio
    async def test_load_missing_context(self, redis_client):
        context = await ExecutionContext.load(str(uuid4()), redis_client)
        assert context._system_variables == {}


class TestExecutionContextVariables:
    @pytest.mark.asyncio
    async def test_variables_round_trip(self, context):
        await context.set_variable("test_var", {"value": [1, 2]})
        assert await context.get_variable("test_var") == {"value": [1, 2]}
        assert await context.get_variable("missing") is None
        assert await context.get_all_variables() == {"test_var": {"value": [1, 2]}}

    @pytest.mark.asyncio
    async def test_inputs_round_trip(self, context):
        inputs = {"query": "test", "limit": 10}
        await context.set_inputs(inputs)
        assert await context.get_inputs() == inputs
        assert await context.get_variable("sys.inputs.query") == "test"
        assert await context.get_variable("sys.inputs.limit") == 10


class TestExecutionContextNodeOutputs:
    @pytest.mark.asyncio
    async def test_node_outputs_round_trip(self, context):
        outputs = {"result": "success", "data": [1, 2, 3]}
        await context.set_node_outputs("node_1", outputs)
        assert await context.get_node_outputs("node_1") == outputs

    @pytest.mark.asyncio
    async def test_missing_node_outputs(self, context):
        assert await context.get_node_outputs("missing_node") is None

    @pytest.mark.asyncio
    async def test_all_node_outputs_ignores_non_mapping_values(self, context):
        await context.set_node_outputs("node_1", {"value": 1})
        key = context.OUTPUTS_KEY.format(run_id=context.run_id)
        context.redis.hashes[key]["invalid"] = dumps_value("not a mapping")

        assert await context.get_all_node_outputs() == {"node_1": {"value": 1}}


class TestExecutionContextResolution:
    @pytest.mark.asyncio
    async def test_resolves_system_inputs_globals_nodes_and_templates(self, context):
        context._system_variables = {"user_id": "user-1"}
        await context.set_inputs({"query": "hello"})
        await context.set_variable("topic", "billing")
        await context.set_variable("conversation_name", "thread")
        await context.set_node_outputs("node", {"result": {"ok": True}})

        assert await context.resolve_variable_ref("{{sys_user_id}}") == "user-1"
        assert await context.resolve_variable_ref("{{query}}") == "hello"
        assert await context.resolve_variable_ref("{{topic}}") == "billing"
        assert (
            await context.resolve_variable_ref("{{conversation.conversation_name}}")
            == "thread"
        )
        assert await context.resolve_variable_ref("{{node}}") == {
            "result": {"ok": True}
        }
        assert await context.resolve_template("Result: {{node.result}}") == (
            'Result: {"ok": true}'
        )
        assert await context.resolve_variable_ref(4) == 4
        assert await context.resolve_template("") == ""

    @pytest.mark.asyncio
    async def test_lazy_node_output_executes_once_and_persists_metadata(self, context):
        from app.services.workflow.lazy_stream import LazyStreamResult

        lazy = LazyStreamResult("model", [], 0, None, 1, context=context)
        lazy.execute = AsyncMock(return_value="complete")
        lazy._reasoning = "reason"
        lazy._usage = {"total_tokens": 2}
        await context.set_node_outputs("llm", {"text": lazy})

        assert (
            await context.resolve_variable_ref("{{llm.text}}", "answer") == "complete"
        )
        lazy.execute.assert_awaited_once_with("answer")
        assert await context.get_node_outputs("llm") == {
            "text": "complete",
            "reasoning": "reason",
            "usage": {"total_tokens": 2},
        }


class TestExecutionContextStatus:
    @pytest.mark.asyncio
    async def test_status_round_trip(self, context):
        assert await context.get_status() is None
        await context.set_status("cancelled")
        assert await context.get_status() == "cancelled"


class TestExecutionContextBranches:
    @pytest.mark.asyncio
    async def test_single_branch_round_trip(self, context):
        await context.set_branch("node_1", "true")
        assert await context.get_active_branches("node_1") == ["true"]

    @pytest.mark.asyncio
    async def test_multiple_and_missing_branches(self, context):
        await context.set_active_branches("node_1", ["case-1", "case-2"])
        assert await context.get_active_branches("node_1") == ["case-1", "case-2"]
        assert await context.get_active_branches("missing") is None

    @pytest.mark.asyncio
    async def test_should_execute_node_respects_outputs_and_active_handles(
        self, context
    ):
        assert await context.should_execute_node("start", [])
        assert not await context.should_execute_node(
            "target", [{"source": None, "sourceHandle": "yes"}]
        )

        await context.set_node_outputs("plain", {"value": 1})
        assert await context.should_execute_node(
            "target", [{"source": "plain", "sourceHandle": None}]
        )

        await context.set_active_branches("condition", ["yes"])
        assert await context.should_execute_node(
            "target", [{"source": "condition", "sourceHandle": "yes"}]
        )
        assert not await context.should_execute_node(
            "target", [{"source": "condition", "sourceHandle": "no"}]
        )


class TestExecutionContextLifecycle:
    @pytest.mark.asyncio
    async def test_publishes_unicode_event_to_run_channel(self, context, redis_client):
        await context.publish_event({"message": "完成"})

        channel, payload = redis_client.published
        assert channel == context.get_stream_channel()
        assert json.loads(payload) == {"message": "完成"}

    @pytest.mark.asyncio
    async def test_cleanup_removes_all_context_keys(self, context, redis_client):
        await context.set_inputs({"query": "test"})
        await context.set_status("running")
        await context.set_branch("condition", "yes")
        await redis_client.hset(
            context.META_KEY.format(run_id=context.run_id), mapping={"workflow_id": "w"}
        )

        await context.cleanup()

        assert redis_client.values == {}
        assert redis_client.hashes == {}
