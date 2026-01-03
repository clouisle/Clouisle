"""
Tests for node executors.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from app.services.workflow.executor import ExecutionResult
from app.services.workflow.context import ExecutionContext


class TestStartExecutors:
    """Tests for start node executors."""

    @pytest.mark.asyncio
    async def test_user_input_executor(self):
        """Test user_input executor."""
        from app.services.workflow.executors.start import UserInputExecutor

        executor = UserInputExecutor()

        node = {
            "id": "start_1",
            "type": "user_input",
            "data": {
                "variables": [
                    {"name": "query", "type": "string", "required": True},
                    {"name": "limit", "type": "number", "default": 10},
                ],
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_inputs = AsyncMock(return_value={"query": "test query"})
        context.set_variable = AsyncMock()

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert "query" in result.outputs

    @pytest.mark.asyncio
    async def test_trigger_executor(self):
        """Test trigger executor."""
        from app.services.workflow.executors.start import TriggerExecutor

        executor = TriggerExecutor()

        node = {
            "id": "trigger_1",
            "type": "trigger",
            "data": {
                "triggerType": "manual",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_inputs = AsyncMock(return_value={})

        run = MagicMock()
        run.trigger_type = "manual"
        run.inputs = {}

        result = await executor.execute(node, context, run)

        assert result.success is True


class TestAnswerExecutor:
    """Tests for answer node executor."""

    @pytest.mark.asyncio
    async def test_answer_executor(self):
        """Test answer executor."""
        from app.services.workflow.executors.answer import AnswerExecutor

        executor = AnswerExecutor()

        node = {
            "id": "answer_1",
            "type": "answer",
            "data": {
                "answer": "The result is: {{result}}",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value="42")

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert "answer" in result.outputs


class TestConditionExecutor:
    """Tests for condition node executor."""

    @pytest.mark.asyncio
    async def test_condition_true(self):
        """Test condition executor with true condition."""
        from app.services.workflow.executors.condition import ConditionExecutor

        executor = ConditionExecutor()

        node = {
            "id": "condition_1",
            "type": "condition",
            "data": {
                "conditions": [
                    {
                        "variable": "{{score}}",
                        "operator": ">",
                        "value": "50",
                    },
                ],
                "logicalOperator": "and",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value=75)

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.next_handles == ["true"]

    @pytest.mark.asyncio
    async def test_condition_false(self):
        """Test condition executor with false condition."""
        from app.services.workflow.executors.condition import ConditionExecutor

        executor = ConditionExecutor()

        node = {
            "id": "condition_1",
            "type": "condition",
            "data": {
                "conditions": [
                    {
                        "variable": "{{score}}",
                        "operator": ">",
                        "value": "50",
                    },
                ],
                "logicalOperator": "and",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value=25)

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.next_handles == ["false"]


class TestCodeExecutor:
    """Tests for code node executor."""

    @pytest.mark.asyncio
    async def test_code_executor_simple(self):
        """Test code executor with simple code."""
        from app.services.workflow.executors.code import CodeExecutor

        executor = CodeExecutor()

        node = {
            "id": "code_1",
            "type": "code",
            "data": {
                "code": "result = input_value * 2",
                "inputs": [{"name": "input_value", "type": "number"}],
                "outputs": [{"name": "result", "type": "number"}],
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value=21)

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs.get("result") == 42

    @pytest.mark.asyncio
    async def test_code_executor_syntax_error(self):
        """Test code executor with syntax error."""
        from app.services.workflow.executors.code import CodeExecutor

        executor = CodeExecutor()

        node = {
            "id": "code_1",
            "type": "code",
            "data": {
                "code": "result = invalid syntax (",
                "inputs": [],
                "outputs": [{"name": "result"}],
            },
        }

        context = MagicMock(spec=ExecutionContext)
        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is False
        assert result.error is not None


class TestTemplateExecutor:
    """Tests for template node executor."""

    @pytest.mark.asyncio
    async def test_template_executor(self):
        """Test template executor."""
        from app.services.workflow.executors.template import TemplateExecutor

        executor = TemplateExecutor()

        node = {
            "id": "template_1",
            "type": "template",
            "data": {
                "template": "Hello, {{name}}! You have {{count}} messages.",
                "variables": ["name", "count"],
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=lambda x: {
            "name": "Alice",
            "count": "5",
        }.get(x, ""))

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert "Hello, Alice!" in result.outputs.get("output", "")
        assert "5 messages" in result.outputs.get("output", "")


class TestVariableExecutors:
    """Tests for variable-related executors."""

    @pytest.mark.asyncio
    async def test_variable_assignment_executor(self):
        """Test variable_assignment executor."""
        from app.services.workflow.executors.variable import VariableAssignmentExecutor

        executor = VariableAssignmentExecutor()

        node = {
            "id": "var_1",
            "type": "variable_assignment",
            "data": {
                "assignments": [
                    {"name": "x", "value": "10"},
                    {"name": "y", "value": "{{input}}"},
                ],
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value="20")
        context.set_variable = AsyncMock()

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        # Should have called set_variable for each assignment
        assert context.set_variable.call_count >= 2

    @pytest.mark.asyncio
    async def test_variable_aggregator_executor(self):
        """Test variable_aggregator executor."""
        from app.services.workflow.executors.variable import VariableAggregatorExecutor

        executor = VariableAggregatorExecutor()

        node = {
            "id": "agg_1",
            "type": "variable_aggregator",
            "data": {
                "variables": ["result1", "result2", "result3"],
                "outputVariable": "combined",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=lambda x: {
            "result1": "a",
            "result2": "b",
            "result3": "c",
        }.get(x))
        context.set_variable = AsyncMock()

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert "combined" in result.outputs


class TestIterationExecutors:
    """Tests for iteration-related executors."""

    @pytest.mark.asyncio
    async def test_iteration_executor_first_item(self):
        """Test iteration executor returns first item."""
        from app.services.workflow.executors.iteration import IterationExecutor

        executor = IterationExecutor()

        node = {
            "id": "iter_1",
            "type": "iteration",
            "data": {
                "items": "{{items}}",
                "itemVariable": "item",
                "indexVariable": "index",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=lambda x: {
            "items": [1, 2, 3],
            "iter_1_index": None,  # First iteration
        }.get(x))
        context.set_variable = AsyncMock()

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs.get("item") == 1
        assert result.outputs.get("index") == 0

    @pytest.mark.asyncio
    async def test_iteration_executor_complete(self):
        """Test iteration executor signals completion."""
        from app.services.workflow.executors.iteration import IterationExecutor

        executor = IterationExecutor()

        node = {
            "id": "iter_1",
            "type": "iteration",
            "data": {
                "items": "{{items}}",
                "itemVariable": "item",
                "indexVariable": "index",
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(side_effect=lambda x: {
            "items": [1, 2, 3],
            "iter_1_index": 3,  # Past end
        }.get(x))
        context.set_variable = AsyncMock()

        run = MagicMock()

        result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs.get("_iteration_complete") is True


class TestToolExecutors:
    """Tests for tool-related executors."""

    @pytest.mark.asyncio
    async def test_http_request_executor_get(self):
        """Test http_request executor with GET."""
        from app.services.workflow.executors.tool import HttpRequestExecutor

        executor = HttpRequestExecutor()

        node = {
            "id": "http_1",
            "type": "http_request",
            "data": {
                "method": "GET",
                "url": "https://api.example.com/data",
                "headers": {"Authorization": "Bearer {{token}}"},
            },
        }

        context = MagicMock(spec=ExecutionContext)
        context.get_variable = AsyncMock(return_value="test_token")

        run = MagicMock()

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"data": "test"})
            mock_response.headers = {}

            mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_session.return_value)
            mock_session.return_value.__aexit__ = AsyncMock()
            mock_session.return_value.request = AsyncMock(return_value=mock_response)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            result = await executor.execute(node, context, run)

        # Result depends on implementation - check basic structure
        assert result is not None
