"""Workflow Agent nodes delegate tool calls without a durable pause.

The delegated AgentService call is synchronous from the workflow's point of
view, so a pending approval cannot park it. These tests pin the two halves of
the contract: the workflow run/entrypoint is the trusted identity for every
delegated call (one stable id per model tool call), and a pending approval is
converted into an explicit tool error instead of an interaction object that a
loop without pause would stringify as a fake result.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.llm.tools.interaction import ToolInteractionRequest
from app.schemas.tool_approval import ExecutionEntrypoint, ExecutionRunKind
from app.services.agent import AgentService
from app.services.tool_context import (
    RuntimeToolIdentity,
    current_tool_identity,
    tool_identity_scope,
)
from app.services.tool_execution import PendingToolApproval
from app.services.workflow.executors.tool import AgentNodeExecutor
from app.utils.tool_output import get_tool_execution_payloads


def _tool_call(name: str = "get_current_time", call_id: str = "call-1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments="{}"),
    )


@pytest.mark.asyncio
async def test_agent_node_scopes_delegated_tools_to_the_workflow_origin():
    workflow_id, run_id, team_id, user_id = uuid4(), uuid4(), uuid4(), uuid4()
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        triggered_by_id=user_id,
        triggered_by=SimpleNamespace(locale=None),
        fetch_related=AsyncMock(),
        # Manual run: no stamped origin, the workflow surface is the fallback.
        context_snapshot={},
    )
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        enable_attachments=False,
        max_iterations=3,
    )
    captured: dict[str, object] = {}

    async def fake_chat(**kwargs):
        captured["identity"] = current_tool_identity()
        return {
            "response": "ok",
            "tool_calls": [],
            "usage": {},
            "dialogue": [],
            "artifacts": [],
        }

    node = {
        "id": "agent_1",
        "type": "agent",
        "data": {
            "agentConfig": {
                "agentId": str(agent.id),
                "message": "hello",
                "stream": False,
            }
        },
    }
    context = MagicMock()

    with (
        patch("app.models.agent.Agent.filter") as agent_filter,
        patch(
            "app.services.agent.AgentService.chat",
            new=AsyncMock(side_effect=fake_chat),
        ),
        patch(
            "app.core.i18n.resolve_language",
            new=AsyncMock(return_value="en"),
        ),
    ):
        agent_filter.return_value.first = AsyncMock(return_value=agent)
        result = await AgentNodeExecutor().execute(node, context, run)

    assert result.success is True
    identity = captured["identity"]
    assert identity is not None
    # A workflow run is a non-interactive entrypoint with its own stable surface,
    # even when the run was started manually.
    assert identity.run_id == run_id
    assert identity.run_kind == ExecutionRunKind.WORKFLOW.value
    assert identity.entrypoint == "workflow"
    assert identity.entrypoint_id == str(workflow_id)
    assert identity.interactive is False
    assert identity.tool_call_prefix == f"workflow-agent:{run_id}:agent_1"


@pytest.mark.asyncio
async def test_delegated_pending_approval_fails_closed_and_drops_the_request():
    user_id, team_id, run_id, workflow_id = uuid4(), uuid4(), uuid4(), uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=team_id, tools_config=None)
    execution_id = uuid4()
    identity = RuntimeToolIdentity(
        run_id=run_id,
        run_kind=ExecutionRunKind.WORKFLOW.value,
        entrypoint=ExecutionEntrypoint.SCHEDULE.value,
        entrypoint_id=str(workflow_id),
        interactive=False,
        tool_call_prefix=f"workflow-agent:{run_id}:agent_1",
    )
    boundary = AsyncMock(
        return_value=PendingToolApproval(execution_id=execution_id, tool_name="x")
    )
    cancel = AsyncMock()

    with (
        patch(
            "app.models.user.User.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(id=user_id)),
        ),
        patch("app.services.tool.ToolExecutor.execute_builtin_tool", new=boundary),
        patch("app.services.tool_approvals.cancel_execution", new=cancel),
        tool_identity_scope(identity),
    ):
        result = await AgentService()._execute_tool(
            agent, _tool_call(), user_id=str(user_id)
        )

    assert not isinstance(result, ToolInteractionRequest)
    assert result["success"] is False
    assert result["tool_name"] == "get_current_time"
    assert result["error"]  # localized failure, never a fake result
    cancel.assert_awaited_once()
    assert cancel.await_args.args[0] == execution_id

    context = boundary.await_args.kwargs["context"]
    assert context.entrypoint is ExecutionEntrypoint.SCHEDULE
    assert context.entrypoint_id == str(workflow_id)
    assert context.run_kind is ExecutionRunKind.WORKFLOW
    assert context.run_id == run_id
    # Stable per model tool call, not one id shared by the whole node.
    assert context.tool_call_id == f"workflow-agent:{run_id}:agent_1:call-1"
    assert context.interactive is False


@pytest.mark.asyncio
async def test_interaction_request_is_never_rendered_as_a_tool_result():
    import json

    request = ToolInteractionRequest(
        tool_name="mail_send", arguments={"execution_id": str(uuid4())}
    )

    display, model_text = get_tool_execution_payloads(request, "mail_send")

    payload = json.loads(display)
    assert payload["success"] is False
    assert payload["tool_name"] == "mail_send"
    assert payload["error"]
    assert display == model_text
    # It must not leak the dataclass repr into model context.
    assert "ToolInteractionRequest(" not in model_text
