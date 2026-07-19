"""
Tests for the NodeExecutor base class and registry.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.services.workflow.executor import (
    NodeExecutor,
    NodeExecutorRegistry,
    ExecutionResult,
)
from app.services.workflow.context import ExecutionContext
from app.services.workflow.errors import NodeTypeNotFoundError
from app.services.workflow.types import NodeInputMapping


class DummyExecutor(NodeExecutor):
    """Dummy executor for testing."""

    node_type = "dummy"

    async def execute(self, node, context, run):
        return ExecutionResult(outputs={"result": "dummy_output"})


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        """Test successful execution result."""
        result = ExecutionResult(outputs={"key": "value"})
        assert result.success is True
        assert result.outputs == {"key": "value"}
        assert result.error is None
        assert result.next_handles is None

    def test_error_result(self):
        """Test error execution result."""
        result = ExecutionResult(error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_branching_result(self):
        """Test result with next handles for branching."""
        result = ExecutionResult(next_handles=["true", "false"])
        assert result.next_handles == ["true", "false"]


class TestNodeExecutorRegistry:
    """Tests for the NodeExecutorRegistry."""

    def setup_method(self):
        """Clear registry before each test."""
        # Save original registry
        self._original_registry = NodeExecutorRegistry._executors.copy()

    def teardown_method(self):
        """Restore registry after each test."""
        NodeExecutorRegistry._executors = self._original_registry

    def test_register_executor(self):
        """Test registering an executor."""
        NodeExecutorRegistry.register("dummy")(DummyExecutor)
        assert "dummy" in NodeExecutorRegistry._executors
        assert NodeExecutorRegistry._executors["dummy"] is DummyExecutor

    def test_get_executor(self):
        """Test getting a registered executor."""
        NodeExecutorRegistry.register("dummy")(DummyExecutor)
        executor = NodeExecutorRegistry.get("dummy")
        assert isinstance(executor, DummyExecutor)

    def test_get_unknown_executor(self):
        """Test getting an unknown executor raises error."""
        with pytest.raises(NodeTypeNotFoundError):
            NodeExecutorRegistry.get("unknown_type")

    def test_decorator_registration(self):
        """Test the register_executor decorator."""

        @NodeExecutorRegistry.register("test_decorated")
        class TestExecutor(NodeExecutor):
            node_type = "test_decorated"

            async def execute(self, node, context, run):
                return ExecutionResult()

        assert "test_decorated" in NodeExecutorRegistry._executors

    def test_list_executors(self):
        """Test listing all registered executors."""
        NodeExecutorRegistry.register("dummy")(DummyExecutor)
        assert "dummy" in NodeExecutorRegistry.list_types()


class TestNodeExecutorHelpers:
    def setup_method(self):
        self.executor = DummyExecutor()

    @pytest.mark.asyncio
    async def test_resolve_typed_inputs(self):
        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(return_value="resolved")
        mappings = [
            NodeInputMapping(name="query", variableRef="{{start.query}}"),
            NodeInputMapping(name="limit", source="constant", constantValue=10),
        ]

        result = await self.executor.resolve_inputs(context, mappings)

        assert result == {"query": "resolved", "limit": 10}
        context.resolve_variable_ref.assert_awaited_once_with("{{start.query}}")

    @pytest.mark.asyncio
    async def test_resolve_legacy_inputs(self):
        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(return_value="resolved")

        result = await self.executor.resolve_inputs(
            context,
            [
                {"name": "query", "value": "{{start.query}}"},
                {"name": "limit", "source": "constant", "constantValue": 10},
                {},
            ],
        )

        assert result == {"query": "resolved", "limit": 10}

    @pytest.mark.asyncio
    async def test_duplicate_inputs_are_rejected(self):
        with pytest.raises(ValueError):
            await self.executor.resolve_inputs(
                MagicMock(spec=ExecutionContext),
                [
                    NodeInputMapping(name="query"),
                    NodeInputMapping(name="query"),
                ],
            )

    @pytest.mark.asyncio
    async def test_default_helpers(self):
        assert await self.executor.validate_config({}) == []
        assert self.executor.get_output_variables({}) == []
        assert self.executor.get_output_specs({}) == []


class TestExecutorExecution:
    @pytest.mark.asyncio
    async def test_dummy_executor_execute(self):
        result = await DummyExecutor().execute({}, MagicMock(), MagicMock())
        assert result.success is True
        assert result.outputs == {"result": "dummy_output"}
