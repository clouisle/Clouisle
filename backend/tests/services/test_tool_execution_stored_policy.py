"""Stored site/team/entrypoint layers must reach the real execution boundary."""

from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool
from app.models.tool_approval import ExecutionEntrypoint
from app.models.tool_approval_policy import ToolApprovalPolicyDefinition
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError
from app.schemas.tool_approval_policy import ToolApprovalPolicyScope
from app.services.tool_approval_policies import build_scope_key
from app.services.tool_approvals import normalize_tool_approval_policy, policy_hash
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    execute_stored_tool,
)


async def _grant_team_read(user: User) -> None:
    permission = await Permission.filter(code="team:read").first()
    if permission is None:
        permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"policy user {uuid4().hex[:6]}")
    await role.permissions.add(permission)
    await user.roles.add(role)


async def _fixture():
    user = await User.create(
        username=f"policy_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@policy.test",
        hashed_password="x",
    )
    await _grant_team_read(user)
    team = await Team.create(name=f"Policy {uuid4().hex[:6]}")
    await TeamMember.create(team=team, user=user, role="owner")
    tool = await Tool.create(
        name=f"policy_tool_{uuid4().hex[:6]}",
        display_name="Policy tool",
        description="",
        team=team,
        created_by=user,
        type="custom",
        approval_policy={"default_decision": "allow"},
    )
    return user, team, tool


async def _store_team_layer(*, user, team, policy):
    normalized = normalize_tool_approval_policy(policy)
    await ToolApprovalPolicyDefinition.create(
        id=uuid4(),
        scope=ToolApprovalPolicyScope.TEAM,
        scope_key=build_scope_key(scope=ToolApprovalPolicyScope.TEAM, team_id=team.id),
        team_id=team.id,
        policy=normalized.model_dump(mode="json"),
        policy_hash=policy_hash(normalized),
        version=1,
        created_by_id=user.id,
    )


@pytest.mark.asyncio
async def test_team_deny_layer_blocks_execution():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        await _store_team_layer(
            user=user, team=team, policy={"default_decision": "deny"}
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_id=str(uuid4()),
            interactive=True,
        )
        with pytest.raises(BusinessError):
            await execute_stored_tool(tool, "read", {}, context, invoke)
        assert calls == []
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_team_require_approval_layer_pauses_even_for_tool_test():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        await _store_team_layer(
            user=user,
            team=team,
            policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"ok": True}

        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
            entrypoint_id=str(uuid4()),
            interactive=True,
        )
        result = await execute_stored_tool(tool, "read", {}, context, invoke)
        assert isinstance(result, PendingToolApproval)
        assert calls == []
    finally:
        await Tortoise.close_connections()
