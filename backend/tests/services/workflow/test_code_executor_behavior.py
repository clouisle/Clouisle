from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sandbox.models import SandboxJobSource, SandboxResult
from app.services.workflow.context import ExecutionContext
from app.services.workflow.executors.code import CODE_TIMEOUT, CodeNodeExecutor


@pytest.mark.asyncio
async def test_executes_python_with_resolved_inputs():
    context = MagicMock(spec=ExecutionContext)
    context.resolve_variable_ref = AsyncMock(return_value=21)
    sandbox_result = SandboxResult(
        job_id="job-1",
        success=True,
        result={"result": 42},
        stdout="done",
        stderr="warning",
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
    assert "inputs = params" in job.code
    assert "return main(inputs)" in job.code
    submit.assert_awaited_once_with(job, timeout_seconds=CODE_TIMEOUT + 5)


@pytest.mark.asyncio
async def test_executes_javascript_from_legacy_config():
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
async def test_normalizes_non_mapping_outputs(sandbox_output, expected):
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
@pytest.mark.parametrize("sandbox_error", ["private sandbox failure", None])
async def test_translates_sandbox_failure(sandbox_error):
    with (
        patch(
            "app.services.workflow.executors.code.sandbox_gateway.submit_and_wait",
            new=AsyncMock(
                return_value=SandboxResult(
                    job_id="job-1", success=False, error=sandbox_error
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
    translate.assert_called_once_with(sandbox_error or "code_execution_failed")


@pytest.mark.asyncio
async def test_translates_gateway_exception():
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
async def test_rejects_missing_code_and_unsupported_language():
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
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {},
            [
                "Code is required",
                "Python code must define a 'main(inputs)' function",
            ],
        ),
        (
            {"language": "javascript", "code": "return null"},
            ["JavaScript code must define a 'main(params)' function"],
        ),
        (
            {"language": "javascript", "code": "let main = (params) => params"},
            [],
        ),
        (
            {"language": "ruby", "code": "def main; end"},
            ["Unsupported language: ruby. Use 'python' or 'javascript'"],
        ),
    ],
)
async def test_validates_required_code_and_language(config, expected):
    assert await CodeNodeExecutor().validate_config(config) == expected


@pytest.mark.asyncio
async def test_reports_sorted_duplicate_input_names():
    errors = await CodeNodeExecutor().validate_config(
        {
            "code": "def main(inputs): return inputs",
            "inputs": [
                {"name": "z"},
                {"name": "a"},
                {"name": "z"},
                {"name": "a"},
                {},
            ],
        }
    )

    assert errors == ["Duplicate input parameter names found: a, z"]


def test_declares_legacy_output_variables():
    executor = CodeNodeExecutor()
    outputs = [{"name": "value", "type": "number"}]

    assert executor.get_output_variables({}) == [{"name": "result", "type": "any"}]
    assert executor.get_output_variables({"outputs": outputs}) is outputs


def test_builds_default_and_configured_output_specs():
    executor = CodeNodeExecutor()

    default = executor.get_output_specs({})
    configured = executor.get_output_specs(
        {
            "outputs": [
                {
                    "name": "payload",
                    "typeSpec": {"kind": "array", "item": {"kind": "number"}},
                    "description": "Generated values",
                },
                {"name": "count", "type": "number", "description": 42},
                {"type": "string"},
                {"name": "", "type": "string"},
                "invalid",
            ]
        }
    )

    assert [(output.name, output.type.kind) for output in default] == [
        ("result", "any")
    ]
    assert [(output.name, output.type.kind) for output in configured] == [
        ("payload", "array"),
        ("count", "number"),
    ]
    assert configured[0].type.item.kind == "number"
    assert configured[0].description == "Generated values"
    assert configured[1].description is None
