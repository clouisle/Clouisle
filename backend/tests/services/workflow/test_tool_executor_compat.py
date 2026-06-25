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
    async def test_builtin_image_tool_exposes_media_artifacts(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_image",
            "type": "tool",
            "data": {
                "toolConfig": {
                    "toolName": "generate_image",
                    "toolType": "builtin",
                    "parameterMappings": [
                        {
                            "name": "prompt",
                            "source": "constant",
                            "constantValue": "A calm lake",
                        }
                    ],
                    "outputVariable": "generatedMedia",
                }
            },
        }
        media_result = {
            "display_result": {
                "kind": "media.image",
                "success": True,
                "images": [
                    {
                        "image": {
                            "url": "https://cdn.example/image.png",
                            "format": "png",
                        },
                        "seed": 7,
                    }
                ],
                "error": None,
            },
            "llm_result": "Generated 1 image",
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
                new=AsyncMock(return_value=media_result),
            ),
        ):
            mock_workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs["result"] == media_result
        assert result.outputs["generatedMedia"] == media_result
        assert result.outputs["status"] == "success"
        assert result.outputs["mediaKind"] == "image"
        assert result.outputs["artifact"] == media_result["display_result"]["images"][0]
        assert result.outputs["artifacts"] == media_result["display_result"]["images"]

    @pytest.mark.anyio
    async def test_builtin_video_tool_exposes_pending_status_without_artifact(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_video",
            "type": "tool",
            "data": {
                "toolConfig": {
                    "toolName": "generate_video",
                    "toolType": "builtin",
                    "parameterMappings": [
                        {
                            "name": "prompt",
                            "source": "constant",
                            "constantValue": "A slow camera pan",
                        }
                    ],
                    "outputVariable": "generatedVideo",
                }
            },
        }
        media_result = {
            "display_result": {
                "kind": "media.video",
                "success": True,
                "task_id": "task-1",
                "status": "processing",
                "video": None,
                "requires_polling": True,
                "error": None,
            },
            "llm_result": "Video generation started",
        }

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock()
        run = MagicMock()
        run.triggered_by_id = "user-1"
        run.workflow_id = None

        with patch(
            "app.services.tool.ToolExecutor.execute_builtin_tool",
            new=AsyncMock(return_value=media_result),
        ):
            result = await executor.execute(node, context, run)

        assert result.success is True
        assert result.outputs["generatedVideo"] == media_result
        assert result.outputs["mediaKind"] == "video"
        assert result.outputs["artifact"] is None
        assert result.outputs["artifacts"] == []
        assert result.outputs["result"]["display_result"]["requires_polling"] is True

    @pytest.mark.anyio
    async def test_builtin_media_tool_failure_sets_retry_ready_error_outputs(self):
        executor = ToolNodeExecutor()
        node = {
            "id": "tool_image_fail",
            "type": "tool",
            "data": {
                "toolConfig": {
                    "toolName": "generate_image",
                    "toolType": "builtin",
                    "parameterMappings": [
                        {
                            "name": "prompt",
                            "source": "constant",
                            "constantValue": "Blocked prompt",
                        }
                    ],
                    "outputVariable": "generatedMedia",
                }
            },
        }
        media_result = {
            "display_result": {
                "kind": "media.image",
                "success": False,
                "images": [],
                "error": "Safety filter blocked the request",
            },
            "llm_result": "Image generation failed",
        }

        context = MagicMock()
        context.resolve_variable_ref = AsyncMock()
        run = MagicMock()
        run.triggered_by_id = "user-1"
        run.workflow_id = None

        with patch(
            "app.services.tool.ToolExecutor.execute_builtin_tool",
            new=AsyncMock(return_value=media_result),
        ):
            result = await executor.execute(node, context, run)

        assert result.success is False
        assert result.error == "Safety filter blocked the request"
        assert result.outputs["status"] == "error"
        assert result.outputs["error"] == "Safety filter blocked the request"
        assert result.outputs["artifact"] is None
        assert result.outputs["artifacts"] == []
        assert result.outputs["generatedMedia"] == media_result
