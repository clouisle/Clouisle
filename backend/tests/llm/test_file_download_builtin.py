"""`file_download` is an internal builtin that runs through the tool boundary.

The retired inline chat branch called the HTTP transport directly. These tests
pin the replacement: a stable materialized definition, explicit caller-gated
approval when the Agent opts in, the shared SSRF-validated transport, and no
mutation of the model/approved arguments.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.llm.tools import tool_registry
from app.llm.tools.builtin.file_download import (
    FILE_DOWNLOAD_TIMEOUT_SECONDS,
    file_download,
    register_file_download_tool,
)
from app.llm.tools.registry import NON_SELECTABLE_BUILTIN_TOOLS, ToolConcurrency
from app.models.tool import ToolType
from app.models.user import Team, TeamMember, User
from app.schemas.tool_approval import (
    ApprovalDecision,
    ApprovalGate,
    ApprovalGateKind,
    ExecutionEntrypoint,
    PolicyLayer,
    PolicySource,
    ToolApprovalPolicy,
    ToolExecutionStatus,
)
from app.services import tool_approvals
from app.services.builtin_tools import get_builtin_definition


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _actor() -> tuple[User, Team]:
    user = await User.create(
        id=uuid4(),
        username=f"download_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@download.test",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name=f"download_team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role="owner")
    return user, team


def test_registered_as_a_non_selectable_side_effecting_builtin():
    register_file_download_tool()

    info = tool_registry.get_tool("file_download")

    assert info is not None
    assert info.handler is file_download
    # No SHARED concurrency: the definition's policy stays fail-closed.
    assert info.concurrency is ToolConcurrency.EXCLUSIVE
    assert "file_download" in NON_SELECTABLE_BUILTIN_TOOLS
    assert [parameter.name for parameter in info.parameters] == ["url"]
    assert info.parameters[0].required is True


@pytest.mark.asyncio
async def test_handler_uses_the_shared_ssrf_transport_without_mutating_arguments():
    arguments = {"url": "https://example.test/file.txt"}
    transport = AsyncMock(return_value={"success": True, "result": "body"})

    with (
        patch("app.llm.tools.builtin.file_download.execute_http_tool", new=transport),
        patch(
            "app.llm.tools.builtin.file_download.format_http_result_for_llm",
            return_value="body",
        ),
    ):
        result = await file_download(**arguments)

    assert result == {
        "result": {"success": True, "result": "body"},
        "llm_result": "body",
    }
    # The approved invocation arguments are never mutated in place.
    assert arguments == {"url": "https://example.test/file.txt"}
    transport.assert_awaited_once_with(
        http_config={"url": "https://example.test/file.txt", "method": "GET"},
        arguments={},
        timeout=FILE_DOWNLOAD_TIMEOUT_SECONDS,
    )


@pytest.mark.asyncio
async def test_materialized_definition_requires_approval_only_from_explicit_policy():
    """Approval is explicit: materialization never guesses it from concurrency.

    The Agent's confirmation switch supplies a caller-gated layer, and only
    then does the call pause before the HTTP transport runs.
    """

    async with _database():
        user, team = await _actor()

        definition = await get_builtin_definition(team.id, "file_download")

        assert definition.type == ToolType.BUILTIN
        assert definition.identity_policy == "none"
        assert definition.connection_fields == []
        assert definition.approval_policy["default_decision"] == "allow"

        # Re-resolving is stable: one definition per team, never a duplicate.
        again = await get_builtin_definition(team.id, "file_download")
        assert again.id == definition.id

        allowed = await tool_approvals.create_execution(
            tool=definition,
            operation="file_download",
            parameters={"url": "https://example.test/file.txt"},
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_interactive=True,
        )
        assert allowed.status == ToolExecutionStatus.READY
        allowed_evaluation = allowed.policy_snapshot["evaluation"]
        assert allowed_evaluation["decision"] == ApprovalDecision.ALLOW.value

        gated = await tool_approvals.create_execution(
            tool=definition,
            operation="file_download",
            parameters={"url": "https://example.test/file.txt"},
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_interactive=True,
            policy_layers=[
                PolicyLayer(
                    source=PolicySource.ENTRYPOINT,
                    label="agent_confirmation",
                    policy=ToolApprovalPolicy(
                        default_decision=ApprovalDecision.REQUIRE_APPROVAL,
                        gates=(ApprovalGate(kind=ApprovalGateKind.CALLER),),
                    ),
                )
            ],
        )
        assert gated.status == ToolExecutionStatus.AWAITING_APPROVAL
        evaluation = gated.policy_snapshot["evaluation"]
        assert evaluation["decision"] == ApprovalDecision.REQUIRE_APPROVAL.value
        assert [gate["kind"] for gate in evaluation["gates"]] == ["caller"]


@pytest.mark.asyncio
async def test_chat_entry_routes_file_download_through_the_boundary():
    """The retired inline branch must not call the HTTP transport itself."""
    from types import SimpleNamespace

    from app.api.v1.endpoints.chat_tools import execute_tool_call

    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), tools_config=[])
    actor = SimpleNamespace(id=uuid4())
    boundary = AsyncMock(return_value={"result": "body"})
    transport = AsyncMock()

    with (
        patch("app.models.user.User.get_or_none", new=AsyncMock(return_value=actor)),
        patch("app.services.tool.ToolExecutor.execute_builtin_tool", new=boundary),
        patch("app.llm.tools.executors.execute_http_tool", new=transport),
    ):
        result = await execute_tool_call(
            "file_download",
            {"url": "https://example.test/file.txt"},
            agent=agent,
            user=actor,
        )

    assert result == {"result": "body"}
    transport.assert_not_awaited()
    kwargs = boundary.await_args.kwargs
    assert kwargs["tool_name"] == "file_download"
    assert kwargs["arguments"] == {"url": "https://example.test/file.txt"}
    assert kwargs["team_id"] == agent.team_id
    context = kwargs["context"]
    assert context.actor is actor
    assert context.team_id == agent.team_id
    assert context.entrypoint is ExecutionEntrypoint.CHAT


async def _chat_context_for(*, require_approval: bool):
    from types import SimpleNamespace

    from app.api.v1.endpoints.chat_tools import execute_tool_call

    register_file_download_tool()
    actor = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        tools_config=[
            {
                "type": "builtin",
                "name": "file_download",
                "require_approval": require_approval,
            }
        ],
    )
    boundary = AsyncMock(return_value={"result": "body"})
    with (
        patch("app.models.user.User.get_or_none", new=AsyncMock(return_value=actor)),
        patch("app.services.tool.ToolExecutor.execute_builtin_tool", new=boundary),
    ):
        await execute_tool_call(
            "file_download",
            {"url": "https://example.test/file.txt"},
            agent=agent,
            user=actor,
        )
    return boundary.await_args.kwargs["context"]


@pytest.mark.asyncio
async def test_chat_entry_propagates_agent_confirmation_switch():
    """The Agent's explicit switch is what pauses file_download in chat."""
    assert (await _chat_context_for(require_approval=True)).require_approval is True
    assert (await _chat_context_for(require_approval=False)).require_approval is False
