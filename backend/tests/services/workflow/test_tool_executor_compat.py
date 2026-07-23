"""
Compatibility tests for the workflow tool executor.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.workflow.executors.tool import ToolNodeExecutor


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
        run.triggered_by_id = "user-1"
        run.workflow_id = "workflow-1"

        workflow = MagicMock()
        workflow.team_id = "team-1"

        with (
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
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
        mock_execute_builtin.assert_awaited_once_with(
            tool_name="get_current_time",
            arguments={"timezone_name": "Asia/Shanghai"},
            team_id="team-1",
        )

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

        tool = MagicMock()
        workflow = MagicMock()
        workflow.team_id = "team-1"

        with (
            patch("app.models.tool.Tool.filter") as mock_filter,
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
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
        mock_execute.assert_awaited_once_with(
            tool=tool,
            arguments={"query": "hello", "limit": "10"},
            user_id="user-1",
            team_id="team-1",
        )

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

        assert result.success is True
        assert result.outputs["result"] == {"legacy": True}
        mock_execute.assert_awaited_once_with(
            tool=tool,
            arguments={"query": "legacy-query"},
            user_id=None,
            team_id=None,
        )

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
    async def test_execute_uses_no_team_when_workflow_is_missing(self):
        run = MagicMock(workflow_id="missing-workflow", triggered_by_id=123)
        tool = MagicMock()

        with (
            patch("app.models.tool.Tool.filter") as mock_tool_filter,
            patch("app.models.workflow.Workflow.filter") as mock_workflow_filter,
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

        assert result.success is True
        assert result.outputs["result"] == "done"
        assert set(result.outputs) == {"result", "status", "executionTime"}
        mock_execute.assert_awaited_once_with(
            tool=tool,
            arguments={},
            user_id="123",
            team_id=None,
        )

    @pytest.mark.anyio
    async def test_execute_maps_tool_failure_to_public_error_outputs(self):
        run = MagicMock(workflow_id=None, triggered_by_id="user-1")
        tool = MagicMock()

        with (
            patch("app.models.tool.Tool.filter") as mock_filter,
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
