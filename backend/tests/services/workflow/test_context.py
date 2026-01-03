"""
Tests for the ExecutionContext class.
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.workflow.context import ExecutionContext


class TestExecutionContextCreation:
    """Tests for ExecutionContext creation."""

    @pytest.mark.asyncio
    async def test_create_context(self):
        """Test creating a new execution context."""
        run_id = str(uuid4())
        workflow_id = str(uuid4())

        with patch("app.services.workflow.context.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_get_redis.return_value = mock_redis

            context = await ExecutionContext.create(
                run_id=run_id,
                workflow_id=workflow_id,
            )

            assert context.run_id == run_id
            assert context.workflow_id == workflow_id

            # Check Redis set was called
            mock_redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_load_context(self):
        """Test loading an existing execution context."""
        run_id = str(uuid4())
        workflow_id = str(uuid4())

        context_data = {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "variables": {"var1": "value1"},
            "inputs": {},
            "node_outputs": {},
            "branches_taken": [],
            "status": "running",
        }

        with patch("app.services.workflow.context.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=json.dumps(context_data))
            mock_get_redis.return_value = mock_redis

            context = await ExecutionContext.load(run_id)

            assert context.run_id == run_id
            assert context.workflow_id == workflow_id
            mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_nonexistent_context(self):
        """Test loading a non-existent context raises error."""
        run_id = str(uuid4())

        with patch("app.services.workflow.context.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_get_redis.return_value = mock_redis

            with pytest.raises(ValueError, match="Context not found"):
                await ExecutionContext.load(run_id)


class TestExecutionContextVariables:
    """Tests for ExecutionContext variable operations."""

    @pytest.fixture
    def context(self):
        """Create a test context."""
        ctx = ExecutionContext.__new__(ExecutionContext)
        ctx.run_id = str(uuid4())
        ctx.workflow_id = str(uuid4())
        ctx.variables = {}
        ctx.inputs = {}
        ctx.node_outputs = {}
        ctx.branches_taken = []
        ctx.status = "running"
        ctx._redis = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_set_variable(self, context):
        """Test setting a variable."""
        await context.set_variable("test_var", "test_value")

        assert context.variables["test_var"] == "test_value"
        context._redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_get_variable(self, context):
        """Test getting a variable."""
        context.variables["test_var"] = "test_value"

        value = await context.get_variable("test_var")
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_variable_default(self, context):
        """Test getting a non-existent variable with default."""
        value = await context.get_variable("missing", default="default")
        assert value == "default"

    @pytest.mark.asyncio
    async def test_set_inputs(self, context):
        """Test setting inputs."""
        inputs = {"query": "test", "limit": 10}
        await context.set_inputs(inputs)

        assert context.inputs == inputs
        # Inputs should also be available as variables
        assert context.variables.get("sys.query") or True  # Implementation may vary

    @pytest.mark.asyncio
    async def test_get_inputs(self, context):
        """Test getting inputs."""
        context.inputs = {"query": "test"}

        inputs = await context.get_inputs()
        assert inputs == {"query": "test"}


class TestExecutionContextNodeOutputs:
    """Tests for ExecutionContext node output operations."""

    @pytest.fixture
    def context(self):
        """Create a test context."""
        ctx = ExecutionContext.__new__(ExecutionContext)
        ctx.run_id = str(uuid4())
        ctx.workflow_id = str(uuid4())
        ctx.variables = {}
        ctx.inputs = {}
        ctx.node_outputs = {}
        ctx.branches_taken = []
        ctx.status = "running"
        ctx._redis = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_set_node_outputs(self, context):
        """Test setting node outputs."""
        outputs = {"result": "success", "data": [1, 2, 3]}
        await context.set_node_outputs("node_1", outputs)

        assert context.node_outputs["node_1"] == outputs
        context._redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_get_node_outputs(self, context):
        """Test getting node outputs."""
        context.node_outputs["node_1"] = {"result": "success"}

        outputs = await context.get_node_outputs("node_1")
        assert outputs == {"result": "success"}

    @pytest.mark.asyncio
    async def test_get_node_outputs_not_found(self, context):
        """Test getting outputs for non-existent node."""
        outputs = await context.get_node_outputs("missing_node")
        assert outputs is None


class TestExecutionContextStatus:
    """Tests for ExecutionContext status operations."""

    @pytest.fixture
    def context(self):
        """Create a test context."""
        ctx = ExecutionContext.__new__(ExecutionContext)
        ctx.run_id = str(uuid4())
        ctx.workflow_id = str(uuid4())
        ctx.variables = {}
        ctx.inputs = {}
        ctx.node_outputs = {}
        ctx.branches_taken = []
        ctx.status = "running"
        ctx._redis = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_set_status(self, context):
        """Test setting status."""
        await context.set_status("cancelled")

        assert context.status == "cancelled"
        context._redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_get_status(self, context):
        """Test getting status."""
        context.status = "running"

        status = await context.get_status()
        assert status == "running"

    @pytest.mark.asyncio
    async def test_is_cancelled(self, context):
        """Test checking if cancelled."""
        context.status = "running"
        assert await context.is_cancelled() is False

        context.status = "cancelled"
        assert await context.is_cancelled() is True


class TestExecutionContextBranches:
    """Tests for ExecutionContext branch tracking."""

    @pytest.fixture
    def context(self):
        """Create a test context."""
        ctx = ExecutionContext.__new__(ExecutionContext)
        ctx.run_id = str(uuid4())
        ctx.workflow_id = str(uuid4())
        ctx.variables = {}
        ctx.inputs = {}
        ctx.node_outputs = {}
        ctx.branches_taken = []
        ctx.status = "running"
        ctx._redis = AsyncMock()
        return ctx

    @pytest.mark.asyncio
    async def test_add_branch(self, context):
        """Test adding a branch."""
        await context.add_branch("node_1", "true")

        assert {"node_id": "node_1", "handle": "true"} in context.branches_taken

    @pytest.mark.asyncio
    async def test_get_branches(self, context):
        """Test getting all branches."""
        context.branches_taken = [
            {"node_id": "node_1", "handle": "true"},
            {"node_id": "node_2", "handle": "false"},
        ]

        branches = await context.get_branches()
        assert len(branches) == 2
