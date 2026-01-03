"""
Tests for the NodeExecutor base class and registry.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from app.services.workflow.executor import (
    NodeExecutor,
    NodeExecutorRegistry,
    ExecutionResult,
)
from app.services.workflow.context import ExecutionContext


class DummyExecutor(NodeExecutor):
    """Dummy executor for testing."""

    node_type = "dummy"

    async def execute(self, node, context, run):
        return ExecutionResult(
            success=True,
            outputs={"result": "dummy_output"},
        )


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        """Test successful execution result."""
        result = ExecutionResult(
            success=True,
            outputs={"key": "value"},
        )
        assert result.success is True
        assert result.outputs == {"key": "value"}
        assert result.error is None
        assert result.next_handles is None

    def test_error_result(self):
        """Test error execution result."""
        result = ExecutionResult(
            success=False,
            outputs={},
            error="Something went wrong",
        )
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_branching_result(self):
        """Test result with next handles for branching."""
        result = ExecutionResult(
            success=True,
            outputs={},
            next_handles=["true", "false"],
        )
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
        NodeExecutorRegistry.register(DummyExecutor)
        assert "dummy" in NodeExecutorRegistry._executors
        assert NodeExecutorRegistry._executors["dummy"] is DummyExecutor

    def test_get_executor(self):
        """Test getting a registered executor."""
        NodeExecutorRegistry.register(DummyExecutor)
        executor = NodeExecutorRegistry.get("dummy")
        assert isinstance(executor, DummyExecutor)

    def test_get_unknown_executor(self):
        """Test getting an unknown executor raises error."""
        with pytest.raises(ValueError, match="Unknown node type"):
            NodeExecutorRegistry.get("unknown_type")

    def test_decorator_registration(self):
        """Test the register_executor decorator."""

        @NodeExecutorRegistry.register
        class TestExecutor(NodeExecutor):
            node_type = "test_decorated"

            async def execute(self, node, context, run):
                return ExecutionResult(success=True, outputs={})

        assert "test_decorated" in NodeExecutorRegistry._executors

    def test_list_executors(self):
        """Test listing all registered executors."""
        NodeExecutorRegistry.register(DummyExecutor)
        executors = NodeExecutorRegistry.list()
        assert "dummy" in executors


class TestNodeExecutorHelpers:
    """Tests for NodeExecutor helper methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.executor = DummyExecutor()
        self.node = {
            "id": "node_1",
            "type": "dummy",
            "data": {
                "label": "Test Node",
                "param1": "value1",
                "param2": "{{var1}}",
            },
        }

    def test_get_node_id(self):
        """Test extracting node ID."""
        node_id = self.executor.get_node_id(self.node)
        assert node_id == "node_1"

    def test_get_node_data(self):
        """Test extracting node data."""
        data = self.executor.get_node_data(self.node)
        assert data["label"] == "Test Node"
        assert data["param1"] == "value1"

    @pytest.mark.asyncio
    async def test_resolve_variable_simple(self):
        """Test resolving a simple variable."""
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value="resolved_value")

        result = await self.executor.resolve_variable("{{var1}}", context)
        assert result == "resolved_value"
        context.get_variable.assert_called_once_with("var1")

    @pytest.mark.asyncio
    async def test_resolve_variable_non_template(self):
        """Test resolving a non-template value."""
        context = MagicMock(spec=ExecutionContext)

        result = await self.executor.resolve_variable("plain_value", context)
        assert result == "plain_value"
        context.get_variable.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_variable_with_default(self):
        """Test resolving a variable with default value."""
        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value=None)

        result = await self.executor.resolve_variable(
            "{{missing_var}}", context, default="default_value"
        )
        assert result == "default_value"


class TestExecutorExecution:
    """Tests for executor execution."""

    @pytest.mark.asyncio
    async def test_dummy_executor_execute(self):
        """Test executing the dummy executor."""
        executor = DummyExecutor()
        context = MagicMock(spec=ExecutionContext)
        run = MagicMock()

        node = {
            "id": "node_1",
            "type": "dummy",
            "data": {},
        }

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs == {"result": "dummy_output"}
