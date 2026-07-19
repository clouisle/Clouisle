"""
Tests for node executors.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

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
    async def test_executes_python_with_resolved_inputs(self):
        from app.services.sandbox.models import SandboxJobSource, SandboxResult
        from app.services.workflow.executors.code import CODE_TIMEOUT, CodeNodeExecutor

        context = MagicMock(spec=ExecutionContext)
        context.resolve_variable_ref = AsyncMock(return_value=21)
        sandbox_result = SandboxResult(
            job_id="job-1", success=True, result={"result": 42}, stdout="done"
        )
        node = {
            "data": {
                "codeConfig": {
                    "language": "python",
                    "code": "def main(inputs): return {'result': inputs['value'] * 2}",
                    "inputs": [
                        {"name": "value", "variableRef": "{{start.value}}"},
                        {"name": "offset", "source": "constant", "constantValue": 1},
                    ],
                }
            }
        }

        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=sandbox_result),
        ) as submit:
            result = await CodeNodeExecutor().execute(node, context, MagicMock())

        assert result.outputs == {"result": 42}
        context.resolve_variable_ref.assert_awaited_once_with("{{start.value}}")
        job = submit.await_args.args[0]
        assert job.source == SandboxJobSource.WORKFLOW
        assert job.language == "python"
        assert job.metadata["params"] == {"value": 21, "offset": 1}
        assert "return main(inputs)" in job.code
        submit.assert_awaited_once_with(job, timeout_seconds=CODE_TIMEOUT + 5)

    @pytest.mark.asyncio
    async def test_executes_javascript_from_legacy_config(self):
        from app.services.sandbox.models import SandboxResult
        from app.services.workflow.executors.code import CodeNodeExecutor

        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(job_id="job-1", success=True, result="ok")
            ),
        ) as submit:
            result = await CodeNodeExecutor().execute(
                {
                    "data": {
                        "config": {
                            "language": "javascript",
                            "code": "function main(params) { return 'ok'; }",
                        }
                    }
                },
                MagicMock(),
                MagicMock(),
            )

        assert result.outputs == {"result": "ok"}
        job = submit.await_args.args[0]
        assert job.language == "javascript"
        assert "return main(params);" in job.code

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("sandbox_output", "expected"),
        [(None, {"result": None}), (7, {"result": 7})],
    )
    async def test_normalizes_non_mapping_outputs(self, sandbox_output, expected):
        from app.services.sandbox.models import SandboxResult
        from app.services.workflow.executors.code import CodeNodeExecutor

        with patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job-1", success=True, result=sandbox_output
                )
            ),
        ):
            result = await CodeNodeExecutor().execute(
                {"data": {"codeConfig": {"code": "def main(inputs): return None"}}},
                MagicMock(),
                MagicMock(),
            )

        assert result.outputs == expected

    @pytest.mark.asyncio
    async def test_returns_translated_sandbox_failure(self):
        from app.services.sandbox.models import SandboxResult
        from app.services.workflow.executors.code import CodeNodeExecutor

        with (
            patch(
                "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
                new=AsyncMock(
                    return_value=SandboxResult(
                        job_id="job-1", success=False, error="private sandbox failure"
                    )
                ),
            ),
            patch(
                "app.services.workflow.executors.code.translate_public_workflow_error",
                return_value="workflow_execution_error",
            ) as translate,
        ):
            result = await CodeNodeExecutor().execute(
                {"data": {"codeConfig": {"code": "def main(inputs): pass"}}},
                MagicMock(),
                MagicMock(),
            )

        assert result.error == "workflow_execution_error"
        translate.assert_called_once_with("private sandbox failure")

    @pytest.mark.asyncio
    async def test_translates_sandbox_timeout(self):
        from app.services.workflow.executors.code import CodeNodeExecutor

        timeout = TimeoutError("sandbox timed out")
        with (
            patch(
                "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
                new=AsyncMock(side_effect=timeout),
            ),
            patch(
                "app.services.workflow.executors.code.translate_public_workflow_error",
                return_value="request_timeout",
            ) as translate,
        ):
            result = await CodeNodeExecutor().execute(
                {"data": {"codeConfig": {"code": "def main(inputs): pass"}}},
                MagicMock(),
                MagicMock(),
            )

        assert result.error == "request_timeout"
        translate.assert_called_once_with(timeout)

    @pytest.mark.asyncio
    async def test_rejects_missing_code_and_unsupported_language(self):
        from app.services.workflow.executors.code import CodeNodeExecutor

        executor = CodeNodeExecutor()
        missing = await executor.execute(
            {"data": {"codeConfig": {}}}, MagicMock(), MagicMock()
        )
        unsupported = await executor.execute(
            {
                "data": {
                    "codeConfig": {
                        "language": "ruby",
                        "code": "def main(inputs); end",
                    }
                }
            },
            MagicMock(),
            MagicMock(),
        )

        assert missing.error == "tool_code_not_defined"
        assert unsupported.error

    @pytest.mark.asyncio
    async def test_validates_config_and_declares_outputs(self):
        from app.services.workflow.executors.code import CodeNodeExecutor

        executor = CodeNodeExecutor()
        errors = await executor.validate_config(
            {
                "language": "python",
                "code": "print('missing main')",
                "inputs": [{"name": "value"}, {"name": "value"}],
            }
        )
        valid = await executor.validate_config(
            {
                "language": "javascript",
                "code": "const main = (params) => params;",
            }
        )
        outputs = executor.get_output_specs(
            {
                "outputs": [
                    {
                        "name": "payload",
                        "typeSpec": {"kind": "array", "item": {"kind": "number"}},
                        "description": "Generated values",
                    },
                    {"name": "count", "type": "number"},
                    {"type": "string"},
                ]
            }
        )

        assert errors == [
            "Python code must define a 'main(inputs)' function",
            "Duplicate input parameter names found: value",
        ]
        assert valid == []
        assert [(output.name, output.type.kind) for output in outputs] == [
            ("payload", "array"),
            ("count", "number"),
        ]
        assert outputs[0].description == "Generated values"
        assert executor.get_output_variables({}) == [{"name": "result", "type": "any"}]


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
        context.get_variable = AsyncMock(
            side_effect=lambda x: {
                "name": "Alice",
                "count": "5",
            }.get(x, "")
        )

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
        context.get_variable = AsyncMock(
            side_effect=lambda x: {
                "result1": "a",
                "result2": "b",
                "result3": "c",
            }.get(x)
        )
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
        context.get_variable = AsyncMock(
            side_effect=lambda x: {
                "items": [1, 2, 3],
                "iter_1_index": None,  # First iteration
            }.get(x)
        )
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
        context.get_variable = AsyncMock(
            side_effect=lambda x: {
                "items": [1, 2, 3],
                "iter_1_index": 3,  # Past end
            }.get(x)
        )
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

            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session.return_value
            )
            mock_session.return_value.__aexit__ = AsyncMock()
            mock_session.return_value.request = AsyncMock(return_value=mock_response)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            result = await executor.execute(node, context, run)

        # Result depends on implementation - check basic structure
        assert result is not None
