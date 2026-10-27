"""Permission and failure boundaries of the workflow tool nodes.

These pin behavior a workflow author depends on: a malformed connection or MCP
operation fails before any tool runs, another user's private tool is
indistinguishable from a missing one, and an anonymous run cannot borrow a team
identity.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.tool import ToolVisibility
from app.services.error_messages import resolve_user_visible_error
from app.services.tool_execution import PendingToolApproval
from app.services.workflow.executors import tool as tool_module
from app.services.workflow.executors.tool import (
    AgentNodeExecutor,
    HTTPRequestNodeExecutor,
    ToolNodeExecutor,
)


def _context() -> MagicMock:
    context = MagicMock(run_id="run-1")
    context.resolve_variable_ref = AsyncMock(return_value=None)
    return context


def test_malformed_connection_reference_fails_before_any_tool_lookup():
    async def scenario():
        context = _context()
        run = MagicMock(workflow_id=None, triggered_by_id="user-1")

        with patch("app.models.tool.Tool.filter") as tool_filter:
            result = await ToolNodeExecutor().execute(
                {
                    "data": {
                        "toolConfig": {
                            "toolId": "tool-1",
                            "connectionId": "not-a-uuid",
                        }
                    }
                },
                context,
                run,
            )

        assert result.error == "tool_connection_invalid"
        assert result.outputs == {}
        tool_filter.assert_not_called()
        context.resolve_variable_ref.assert_not_awaited()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["   ", "\t", 7, {"name": "x"}, ["x"]])
def test_blank_or_non_string_mcp_operation_is_rejected(operation):
    async def scenario():
        context = _context()
        run = MagicMock(workflow_id=None, triggered_by_id="user-1")

        with patch("app.models.tool.Tool.filter") as tool_filter:
            result = await ToolNodeExecutor().execute(
                {
                    "data": {
                        "toolConfig": {
                            "toolId": "tool-1",
                            "mcpToolName": operation,
                        }
                    }
                },
                context,
                run,
            )

        assert result.error == "invalid_tool_arguments"
        tool_filter.assert_not_called()
        context.resolve_variable_ref.assert_not_awaited()

    asyncio.run(scenario())


def test_private_tool_owned_by_another_user_fails_as_not_found():
    async def scenario():
        tool = SimpleNamespace(
            id="tool-1",
            team_id="team-1",
            visibility=ToolVisibility.PRIVATE,
            created_by_id="owner-2",
            name="private-query",
            type="custom",
        )
        workflow = SimpleNamespace(team_id="team-1")
        run = MagicMock(triggered_by_id="user-1", workflow_id="workflow-1")

        with (
            patch("app.models.workflow.Workflow.filter") as workflow_filter,
            patch("app.models.tool.Tool.filter") as tool_filter,
            patch("app.services.tool.ToolExecutor.execute", new=AsyncMock()) as execute,
        ):
            workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            tool_filter.return_value.first = AsyncMock(return_value=tool)

            result = await ToolNodeExecutor().execute(
                {"data": {"toolConfig": {"toolId": "tool-1"}}},
                _context(),
                run,
            )

        assert result.error == "tool_not_found"
        execute.assert_not_awaited()

    asyncio.run(scenario())


def test_anonymous_run_never_reaches_tool_execution():
    async def scenario():
        workflow = SimpleNamespace(team_id="team-1")
        run = MagicMock(triggered_by_id=None, workflow_id="workflow-1")

        with (
            patch("app.models.workflow.Workflow.filter") as workflow_filter,
            patch(
                "app.services.tool.ToolExecutor.execute_builtin_tool",
                new=AsyncMock(),
            ) as execute,
        ):
            workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            result = await ToolNodeExecutor().execute(
                {
                    "data": {
                        "toolConfig": {
                            "toolType": "builtin",
                            "toolName": "get_current_time",
                        }
                    }
                },
                _context(),
                run,
            )

        assert result.error == "user_context_required"
        execute.assert_not_awaited()

    asyncio.run(scenario())


def test_agent_node_without_workflow_identity_fails_closed():
    async def scenario():
        agent = SimpleNamespace(enable_attachments=False, max_iterations=5)
        run = MagicMock(
            triggered_by_id="user-1",
            workflow_id=None,
            triggered_by=None,
        )
        run.fetch_related = AsyncMock()

        with (
            patch("app.models.agent.Agent.filter") as agent_filter,
            patch("app.services.agent.AgentService") as service_cls,
        ):
            agent_filter.return_value.first = AsyncMock(return_value=agent)
            result = await AgentNodeExecutor().execute(
                {"data": {"config": {"agentId": "agent-1", "stream": False}}},
                _context(),
                run,
            )

        assert result.error == "user_context_required"
        service_cls.return_value.chat.assert_not_called()

    asyncio.run(scenario())


def test_container_approval_is_still_failed_when_cancellation_breaks():
    async def scenario():
        workflow = SimpleNamespace(team_id="team-1")
        run = MagicMock(
            triggered_by_id="user-1",
            workflow_id="workflow-1",
            id="run-1",
        )
        run.fetch_related = AsyncMock()
        pending = PendingToolApproval(
            execution_id=uuid4(), tool_name="get_current_time"
        )

        with (
            patch("app.models.workflow.Workflow.filter") as workflow_filter,
            patch(
                "app.models.user.User.get_or_none",
                new=AsyncMock(return_value=SimpleNamespace(id="user-1")),
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
                new=AsyncMock(return_value=pending),
            ),
            patch(
                "app.services.tool_approvals.cancel_execution",
                new=AsyncMock(side_effect=RuntimeError("cancel failed")),
            ) as cancel,
        ):
            workflow_filter.return_value.only.return_value.first = AsyncMock(
                return_value=workflow
            )
            result = await ToolNodeExecutor().execute(
                {
                    "id": "tool-node",
                    "data": {
                        "parentId": "loop-node",
                        "toolConfig": {
                            "toolType": "builtin",
                            "toolName": "get_current_time",
                        },
                    },
                },
                _context(),
                run,
            )

        assert result.error == "tool_approval_inside_container"
        cancel.assert_awaited_once()

    asyncio.run(scenario())


def test_http_node_maps_validation_value_error_to_public_error():
    async def scenario():
        with (
            patch.object(
                tool_module,
                "get_ssrf_allowed_targets",
                new=AsyncMock(return_value=set()),
            ),
            patch.object(
                tool_module,
                "validate_external_http_url",
                side_effect=ValueError("private network target"),
            ),
        ):
            result = await HTTPRequestNodeExecutor().execute(
                {
                    "data": {
                        "config": {"url": "http://169.254.169.254/latest/meta-data"}
                    }
                },
                _context(),
                MagicMock(),
            )

        assert result.error == resolve_user_visible_error("private network target")

    asyncio.run(scenario())
