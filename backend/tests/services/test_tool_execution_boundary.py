"""Real persistence tests for identity-bound approval execution."""

from dataclasses import replace
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool, ToolShare
from app.models.tool_approval import ExecutionEntrypoint, ToolApprovalRequest
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError
from app.schemas.tool_connection import ToolConnectionCreate
from app.services.tool_approvals import decide_approval
from app.services.tool_connections import ToolConnectionService
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    execute_stored_tool,
)


async def grant_team_read(user):
    permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name="Tool user")
    await role.permissions.add(permission)
    await user.roles.add(role)


@pytest.mark.asyncio
async def test_approval_pins_original_personal_account_and_rejects_parameter_changes():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username="boundary", email="boundary@test.invalid", hashed_password="x"
        )
        await grant_team_read(user)
        team = await Team.create(name="Boundary")
        await TeamMember.create(team=team, user=user, role="owner")
        tool = await Tool.create(
            name="tasks",
            display_name="Tasks",
            description="",
            team=team,
            created_by=user,
            type="mcp",
            identity_policy="personal_only",
            connection_fields=[{"name": "token", "required": True, "secret": True}],
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        first = await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="user",
                name="First",
                config={"token": "first-account"},
                is_default=True,
            ),
        )
        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            interactive=True,
            require_approval=True,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append((parameters, connection.connection_id))
            return {"account": connection.secrets["token"]}

        pending = await execute_stored_tool(
            tool, "tool:delete", {"id": 7}, context, invoke
        )
        assert isinstance(pending, PendingToolApproval)
        assert calls == []
        gate = await ToolApprovalRequest.get(execution_id=pending.execution_id)
        await decide_approval(
            gate.id, user, decision="approve", idempotency_key=uuid4().hex
        )
        await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="user",
                name="Second",
                config={"token": "second-account"},
                is_default=True,
            ),
        )
        resume = replace(context, execution_id=pending.execution_id)
        with pytest.raises(BusinessError):
            await execute_stored_tool(tool, "tool:delete", {"id": 8}, resume, invoke)
        result = await execute_stored_tool(
            tool, "tool:delete", {"id": 7}, resume, invoke
        )
        assert result == {"account": "first-account"}
        assert calls == [({"id": 7}, first.id)]
        with pytest.raises(BusinessError):
            await execute_stored_tool(tool, "tool:delete", {"id": 7}, resume, invoke)
        assert len(calls) == 1
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_shared_tool_uses_consuming_team_authorization():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username="shared", email="shared@test.invalid", hashed_password="x"
        )
        await grant_team_read(user)
        source = await Team.create(name="Source")
        target = await Team.create(name="Target")
        await TeamMember.create(team=target, user=user, role="member")
        tool = await Tool.create(
            name="shared_tool",
            display_name="Shared",
            description="",
            team=source,
            type="custom",
            visibility="team",
            approval_policy={"default_decision": "allow"},
        )
        share = await ToolShare.create(tool=tool, shared_with_team=target)
        context = ToolCallContext(
            actor=user,
            team_id=target.id,
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
            interactive=True,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters["value"])
            return parameters["value"] * 2

        assert (
            await execute_stored_tool(tool, tool.name, {"value": 4}, context, invoke)
            == 8
        )
        await share.delete()
        with pytest.raises(BusinessError):
            await execute_stored_tool(tool, tool.name, {"value": 5}, context, invoke)
        assert calls == [4]
    finally:
        await Tortoise.close_connections()
