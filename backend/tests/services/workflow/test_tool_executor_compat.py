"""
Compatibility tests for the workflow tool executor.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import json

import httpx

from app.services.workflow.executors.tool import ToolNodeExecutor, _convert_tool_input
from app.llm.tools.builtin import web_search as search_module
from app.llm.tools.registry import ToolRegistry


@pytest.mark.anyio
@pytest.mark.parametrize("source", ["constant", "variable"])
async def test_workflow_search_uses_integer_result_limit(source):
    registry = ToolRegistry()
    registry.register(name="web_search", description="search")(search_module.web_search)
    node = {
        "data": {
            "toolConfig": {
                "toolType": "builtin",
                "toolName": "web_search",
                "parameterMappings": [
                    {
                        "name": "query",
                        "type": "string",
                        "source": "constant",
                        "constantValue": "cloud",
                    },
                    {
                        "name": "num_results",
                        "type": "integer",
                        "source": source,
                        "constantValue": "3",
                        "variableRef": "{{start.limit}}",
                    },
                ],
            }
        }
    }
    context = MagicMock(resolve_variable_ref=AsyncMock(return_value="3"))
    real_client = httpx.AsyncClient

    def respond(request):
        limit = json.loads(request.content)["max_results"]
        assert type(limit) is int
        assert limit == 3
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Cloud",
                        "url": "https://example.test/cloud",
                        "content": "Cloud article",
                    }
                ]
            },
        )

    async def run_builtin(
        *, tool_name, arguments, team_id, context, workflow_run_id=None, operation=None
    ):
        return await registry.execute(
            name=tool_name, arguments=arguments, credentials={}
        )

    workflow = MagicMock(team_id="team-1")
    run = MagicMock(id="run-1", workflow_id="workflow-1", triggered_by_id="user-1")

    with (
        patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
        patch(
            "app.models.user.User.get_or_none",
            new=AsyncMock(return_value=MagicMock(id="user-1")),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.token_for_attempt",
            new=AsyncMock(return_value="call-1"),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.find_execution_for_token",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.tool.ToolExecutor.execute_builtin_tool",
            new=AsyncMock(side_effect=run_builtin),
        ),
        patch.object(
            search_module,
            "get_web_search_runtime",
            AsyncMock(return_value=("tavily", {"TAVILY_API_KEY": "test-key"})),
        ),
        patch.object(
            search_module.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(
                transport=httpx.MockTransport(respond), **kwargs
            ),
        ),
    ):
        mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=workflow
        )
        result = await ToolNodeExecutor().execute(node, context, run)

    assert result.success is True
    assert result.outputs["result"]["success"] is True
    assert result.outputs["result"]["results"][0]["url"] == "https://example.test/cloud"


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["abc", "3.5", True, 3.5, [], None])
async def test_invalid_workflow_tool_integer_fails_before_execution(value):
    node = {
        "data": {
            "toolConfig": {
                "toolType": "builtin",
                "toolName": "web_search",
                "outputVariable": "answer",
                "parameterMappings": [
                    {
                        "name": "num_results",
                        "type": "integer",
                        "source": "constant",
                        "constantValue": value,
                    }
                ],
            }
        }
    }
    with patch(
        "app.services.tool.ToolExecutor.execute_builtin_tool", new_callable=AsyncMock
    ) as execute:
        result = await ToolNodeExecutor().execute(
            node, MagicMock(), MagicMock(workflow_id=None)
        )

    assert result.success is False
    assert result.outputs["status"] == "error"
    assert result.outputs["answer"] is None
    execute.assert_not_awaited()


@pytest.mark.parametrize(
    ("value", "parameter_type", "expected"),
    [
        (" 5 ", "integer", 5),
        ("-2", "integer", -2),
        (0, "integer", 0),
        ("1e2", "number", 100.0),
        (2.5, "number", 2.5),
        ("false", "boolean", False),
        ("true", "boolean", True),
        (False, "boolean", False),
        ('[1, "x"]', "array", [1, "x"]),
        ('{"x": 1}', "object", {"x": 1}),
        ([1, 2], "array", [1, 2]),
        ({"x": False}, "object", {"x": False}),
        ("003", "string", "003"),
        ("", "string", ""),
        ("10", "", "10"),
    ],
)
def test_tool_input_conversion_preserves_declared_types(
    value, parameter_type, expected
):
    converted = _convert_tool_input(value, parameter_type)
    assert converted == expected
    assert type(converted) is type(expected)


@pytest.mark.parametrize(
    ("value", "parameter_type"),
    [
        ("NaN", "number"),
        (float("inf"), "number"),
        (True, "number"),
        ("yes", "boolean"),
        ("1", "boolean"),
        ("{}", "array"),
        ("[]", "object"),
        ("{invalid}", "object"),
        ("null", "object"),
        (5, "string"),
        (["a"], "string"),
        ({"a": 1}, "string"),
    ],
)
def test_tool_input_conversion_rejects_invalid_declared_values(value, parameter_type):
    from app.services.workflow.errors import WorkflowError

    with pytest.raises(WorkflowError) as exc_info:
        _convert_tool_input(value, parameter_type)
    assert exc_info.value.msg_key == "invalid_tool_arguments"


class TestToolNodeExecutorCompatibility:
    @pytest.mark.anyio
    async def test_execute_reads_builtin_tool_config_without_tool_id(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_builtin",
            "type": "tool",
            "data": {
                "toolConfig": {
                    "toolId": None,
                    "toolName": "get_current_time",
                    "toolType": "builtin",
                    "parameterMappings": [
                        {
                            "name": "timezone_name",
                            "source": "constant",
                            "constantValue": "Asia/Shanghai",
                        }
                    ],
                    "outputVariable": "currentTime",
                }
            },
        }

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock()

        run = MagicMock()
        run.id = "run-1"
        run.triggered_by_id = "user-1"
        run.workflow_id = "workflow-1"

        workflow = MagicMock()
        workflow.team_id = "team-1"

        with (
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch(
                "app.models.user.User.get_or_none",
                new=AsyncMock(return_value=MagicMock(id="user-1")),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.token_for_attempt",
                new=AsyncMock(return_value="call-1"),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.find_execution_for_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.tool.ToolExecutor.execute_builtin_tool",
                new=AsyncMock(return_value={"now": "2026-04-01 12:00:00"}),
            ) as mock_execute_builtin,
        ):
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )

            result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs["result"] == {"now": "2026-04-01 12:00:00"}
        assert result.outputs["currentTime"] == {"now": "2026-04-01 12:00:00"}
        kwargs = mock_execute_builtin.await_args.kwargs
        assert kwargs["tool_name"] == "get_current_time"
        assert kwargs["arguments"] == {"timezone_name": "Asia/Shanghai"}
        assert kwargs["team_id"] == "team-1"
        call_context = kwargs["context"]
        assert call_context.team_id == "team-1"
        assert call_context.entrypoint.value == "workflow"
        assert call_context.entrypoint_id == "workflow-1"
        assert call_context.run_id == "run-1"
        assert call_context.tool_call_id == "call-1"
        assert call_context.interactive is False

    @pytest.mark.anyio
    async def test_execute_reads_frontend_tool_config(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_1",
            "type": "tool",
            "data": {
                "toolConfig": {
                    "toolId": "tool-123",
                    "parameterMappings": [
                        {
                            "name": "query",
                            "source": "variable",
                            "variableRef": "{{start.query}}",
                        },
                        {
                            "name": "limit",
                            "source": "constant",
                            "constantValue": "10",
                        },
                    ],
                    "outputVariable": "searchResult",
                }
            },
        }

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value="hello")

        run = MagicMock()
        run.triggered_by_id = "user-1"
        run.workflow_id = "workflow-1"

        tool = MagicMock(team_id="team-1")
        workflow = MagicMock()
        workflow.team_id = "team-1"

        with (
            patch("app.models.tool.Tool.filter") as mock_filter,
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch(
                "app.models.user.User.get_or_none",
                new=AsyncMock(return_value=MagicMock(id="user-1")),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.token_for_attempt",
                new=AsyncMock(return_value="call-1"),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.find_execution_for_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.tool.ToolExecutor.execute", new=AsyncMock()
            ) as mock_execute,
        ):
            mock_filter.return_value.first = AsyncMock(return_value=tool)
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            mock_execute.return_value = {"ok": True}

            result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs["result"] == {"ok": True}
        assert result.outputs["searchResult"] == {"ok": True}
        assert result.outputs["status"] == "success"
        mock_execute.assert_awaited_once()
        kwargs = mock_execute.await_args.kwargs
        assert kwargs["tool"] is tool
        assert kwargs["arguments"] == {"query": "hello", "limit": "10"}
        assert kwargs["user_id"] == "user-1"
        assert kwargs["team_id"] == "team-1"
        assert kwargs["operation"] == tool.name
        assert kwargs["context"].run_kind.value == "workflow"

    @pytest.mark.anyio
    async def test_execute_hides_unshared_cross_team_tool(self):
        node = {
            "id": "tool_1",
            "data": {"toolConfig": {"toolId": "tool-123"}},
        }
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock()
        run = MagicMock(triggered_by_id="user-1", workflow_id="workflow-1")
        workflow = MagicMock(team_id="team-1")
        tool = MagicMock(id="tool-123", team_id="other-team")
        tool.visibility = "team"
        share_query = MagicMock()
        share_query.exists = AsyncMock(return_value=False)

        with (
            patch("app.models.workflow.Workflow.filter") as workflow_filter,
            patch("app.models.tool.Tool.filter") as tool_filter,
            patch("app.models.tool.ToolShare.filter", return_value=share_query),
            patch("app.services.tool.ToolExecutor.execute", new=AsyncMock()) as execute,
        ):
            workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            tool_filter.return_value.first = AsyncMock(return_value=tool)

            result = await ToolNodeExecutor().execute(node, context, run)

        assert result.error == "tool_not_found"
        execute.assert_not_awaited()

    @pytest.mark.anyio
    async def test_execute_reads_legacy_tool_config(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_legacy",
            "type": "tool",
            "data": {
                "config": {
                    "tool_id": "tool-legacy",
                    "arguments": {
                        "query": "{{start.query}}",
                    },
                }
            },
        }

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock(return_value="legacy-query")

        run = MagicMock()
        run.triggered_by_id = None
        run.workflow_id = None

        tool = MagicMock()

        with (
            patch("app.models.tool.Tool.filter") as mock_filter,
            patch(
                "app.services.tool.ToolExecutor.execute", new=AsyncMock()
            ) as mock_execute,
        ):
            mock_filter.return_value.first = AsyncMock(return_value=tool)
            mock_execute.return_value = {"legacy": True}

            result = await executor.execute(node, context, run)

        # Non-interactive entrypoints need a real triggering user and team; an
        # anonymous legacy run must never execute a tool unapproved.
        assert result.error == "user_context_required"
        assert result.outputs["status"] == "error"
        mock_execute.assert_not_awaited()

    @pytest.mark.anyio
    async def test_execute_rejects_config_without_tool_identifier(self):
        context = MagicMock()
        context.resolve_variable_ref = AsyncMock()

        result = await ToolNodeExecutor().execute(
            {"data": {"toolConfig": {"toolType": "custom"}}},
            context,
            MagicMock(),
        )

        assert result.error == "tool_not_found"
        assert result.outputs == {}
        context.resolve_variable_ref.assert_not_awaited()

    @pytest.mark.anyio
    async def test_execute_returns_not_found_when_configured_tool_is_missing(self):
        run = MagicMock(workflow_id=None)

        with patch("app.models.tool.Tool.filter") as mock_filter:
            mock_filter.return_value.first = AsyncMock(return_value=None)
            result = await ToolNodeExecutor().execute(
                {"data": {"config": {"toolId": "missing-tool"}}},
                MagicMock(),
                run,
            )

        assert result.error == "tool_not_found"
        assert result.outputs == {}
        mock_filter.assert_called_once_with(id="missing-tool")

    @pytest.mark.anyio
    async def test_execute_requires_workflow_team_context(self):
        run = MagicMock(workflow_id="missing-workflow", triggered_by_id=123, id="run-1")
        tool = MagicMock()

        with (
            patch("app.models.tool.Tool.filter") as mock_tool_filter,
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch(
                "app.models.user.User.get_or_none",
                new=AsyncMock(return_value=MagicMock(id=123)),
            ),
            patch(
                "app.services.tool.ToolExecutor.execute",
                new=AsyncMock(return_value="done"),
            ) as mock_execute,
        ):
            mock_tool_filter.return_value.first = AsyncMock(return_value=tool)
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=None
            )
            result = await ToolNodeExecutor().execute(
                {"data": {"config": {"toolId": "tool-1"}}},
                MagicMock(),
                run,
            )

        assert result.error == "user_context_required"
        assert result.outputs["status"] == "error"
        mock_execute.assert_not_awaited()

    @pytest.mark.anyio
    async def test_execute_maps_tool_failure_to_public_error_outputs(self):
        run = MagicMock(workflow_id="workflow-1", triggered_by_id="user-1", id="run-1")
        tool = MagicMock(team_id="team-1", visibility="team")
        workflow = MagicMock(team_id="team-1")

        with (
            patch("app.models.tool.Tool.filter") as mock_filter,
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
            patch(
                "app.models.user.User.get_or_none",
                new=AsyncMock(return_value=MagicMock(id="user-1")),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.token_for_attempt",
                new=AsyncMock(return_value="call-1"),
            ),
            patch(
                "app.services.workflow.tool_approval_resume.find_execution_for_token",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.services.tool.ToolExecutor.execute",
                new=AsyncMock(side_effect=RuntimeError("private detail")),
            ),
            patch(
                "app.services.workflow.executors.tool.translate_public_workflow_error",
                return_value="public error",
            ) as translate_error,
        ):
            mock_filter.return_value.first = AsyncMock(return_value=tool)
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            result = await ToolNodeExecutor().execute(
                {
                    "data": {
                        "toolConfig": {
                            "toolId": "tool-1",
                            "outputVariable": "answer",
                        }
                    }
                },
                MagicMock(),
                run,
            )

        assert result.error == "public error"
        assert result.outputs["result"] is None
        assert result.outputs["answer"] is None
        assert result.outputs["status"] == "error"
        assert isinstance(result.outputs["executionTime"], int)
        translate_error.assert_called_once()
        assert isinstance(translate_error.call_args.args[0], RuntimeError)

    @pytest.mark.parametrize(
        ("config", "names"),
        [
            ({}, ["result", "status", "executionTime"]),
            (
                {"outputVariable": "answer"},
                ["answer", "result", "status", "executionTime"],
            ),
            (
                {"outputVariable": ""},
                ["result", "status", "executionTime"],
            ),
        ],
    )
    def test_output_declarations_handle_default_alias_and_empty_alias(
        self, config, names
    ):
        executor = ToolNodeExecutor()

        assert [item["name"] for item in executor.get_output_variables(config)] == names
        assert [item.name for item in executor.get_output_specs(config)] == names
