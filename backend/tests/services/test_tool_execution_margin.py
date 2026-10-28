"""Error boundaries of the stored-tool execution and connection resolver.

Every rejection here happens before a side effect: an invalid identity policy,
an unusable connection, a changed approval binding or a stale authorization
must produce a deterministic BusinessError instead of running the tool.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ExecutionRunKind,
    ToolExecution,
    ToolExecutionStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import ApprovalDecision, ApprovalGateKind
from app.schemas.tool_connection import ToolConnectionCreate
from app.services import tool_approvals
from app.services.tool_connections import ToolConnectionService
from app.services.tool_execution import (
    ToolCallContext,
    execute_stored_tool,
    resolve_tool_connection,
    resolve_tool_layer_policy,
)


async def _grant_team_read(user: User) -> None:
    permission = await Permission.filter(code="team:read").first()
    if permission is None:
        permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"execution margin {uuid4().hex[:6]}")
    await role.permissions.add(permission)
    await user.roles.add(role)


async def _fixture(*, identity: str = "none", fields=None, enabled: bool = True):
    user = await User.create(
        username=f"exec_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@execution-margin.test",
        hashed_password="x",
    )
    await _grant_team_read(user)
    team = await Team.create(name=f"Execution {uuid4().hex[:6]}")
    await TeamMember.create(team=team, user=user, role="owner")
    tool = await Tool.create(
        name=f"exec_tool_{uuid4().hex[:8]}",
        display_name="Execution tool",
        description="",
        team=team,
        created_by=user,
        type="custom",
        identity_policy=identity,
        connection_fields=fields or [],
        is_enabled=enabled,
    )
    return user, team, tool


def _context(user, team, *, entrypoint=ExecutionEntrypoint.TOOL_TEST, **overrides):
    values = {
        "actor": user,
        "team_id": team.id,
        "entrypoint": entrypoint,
        "entrypoint_id": "test-entry",
    }
    values.update(overrides)
    return ToolCallContext(**values)


def test_tool_layer_policy_preserves_a_legacy_external_audience():
    auditor = uuid4()
    tool = Tool(
        approval_policy={
            "default_decision": "require_approval",
            "gates": [{"kind": "user", "user_ids": [str(auditor)]}],
        }
    )

    for entrypoint in (ExecutionEntrypoint.TOOL_TEST, ExecutionEntrypoint.CHAT):
        policy = resolve_tool_layer_policy(
            tool, operation="read", entrypoint=entrypoint
        )
        assert policy.default_decision == ApprovalDecision.REQUIRE_APPROVAL
        assert policy.gates[0].kind == ApprovalGateKind.USER
        assert policy.gates[0].user_ids[0] == auditor


def test_only_agent_calls_and_discovery_overrides_apply_a_stored_policy():
    tool = Tool(
        approval_policy={
            "default_decision": "allow",
            "operation_overrides": {
                "tool:read": {"default_decision": "require_approval"}
            },
        }
    )

    agent_policy = resolve_tool_layer_policy(
        tool, operation="tool:read", entrypoint=ExecutionEntrypoint.CHAT
    )
    assert "tool:read" in agent_policy.operation_overrides

    direct_policy = resolve_tool_layer_policy(
        tool, operation="tool:read", entrypoint=ExecutionEntrypoint.TOOL_TEST
    )
    assert direct_policy.default_decision == ApprovalDecision.ALLOW
    assert direct_policy.operation_overrides == {}

    no_override = resolve_tool_layer_policy(
        tool, operation="list:tools", entrypoint=ExecutionEntrypoint.TOOL_TEST
    )
    assert no_override.default_decision == ApprovalDecision.ALLOW


@pytest.mark.asyncio
async def test_identity_policy_none_refuses_an_explicit_connection():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()

        user, team, tool = await _fixture()
        with pytest.raises(BusinessError) as exc:
            await resolve_tool_connection(
                tool,
                _context(user, team, connection_id=uuid4()),
                "read",
            )

        assert exc.value.code == 403
        assert exc.value.msg_key == "tool_connection_access_denied"
        assert exc.value.status_code == 403

    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_unknown_identity_policy_is_a_configuration_error():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()

        user, team, tool = await _fixture()
        tool.identity_policy = "unsupported"

        with pytest.raises(BusinessError) as exc:
            await resolve_tool_connection(tool, _context(user, team), "read")

        assert exc.value.code == 400
        assert exc.value.msg_key == "tool_connection_invalid"
        assert exc.value.status_code == 400

    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_unknown_connection_mode_is_rejected():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()

        user, team, tool = await _fixture(identity="personal_only")

        with pytest.raises(BusinessError) as exc:
            await resolve_tool_connection(
                tool,
                _context(user, team, connection_mode="borrowed"),
                "read",
            )

        assert exc.value.code == 400
        assert exc.value.msg_key == "tool_connection_required"
        assert exc.value.status_code == 400

    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_a_connection_missing_a_required_secret_fails_closed():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(
            identity="personal_only",
            fields=[{"name": "token", "required": True, "secret": True}],
        )
        connection = await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="user",
                name="Empty",
                config={},
            ),
        )

        with pytest.raises(BusinessError) as exc:
            await resolve_tool_connection(
                tool,
                _context(
                    user,
                    team,
                    connection_mode="personal",
                    connection_id=connection.id,
                ),
                "read",
            )

        assert exc.value.code == 400
        assert exc.value.msg_key == "tool_connection_required"
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_a_disabled_tool_is_rejected_after_authorization():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture(enabled=False)
        calls = []

        async def invoke(parameters, resolved):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(tool, "read", {}, _context(user, team), invoke)

        assert exc.value.code == 403
        assert exc.value.msg_key == "tool_access_denied"
        assert calls == []
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_tool_call_execution_must_match_the_requested_operation():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        run_id = uuid4()
        execution = await tool_approvals.create_execution(
            tool=tool,
            operation="read",
            parameters={},
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
            run_kind=ExecutionRunKind.AGENT,
            run_id=run_id,
            tool_call_id="call-1",
        )
        calls = []

        async def invoke(parameters, resolved):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(
                tool,
                "write",
                {},
                _context(
                    user,
                    team,
                    run_kind=ExecutionRunKind.AGENT,
                    run_id=run_id,
                    tool_call_id="call-1",
                ),
                invoke,
            )

        assert exc.value.code == 403
        assert exc.value.msg_key == "tool_execution_access_denied"
        assert calls == []
        assert execution.operation == "read"
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_resuming_with_a_different_connection_is_a_binding_conflict():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        execution = await tool_approvals.create_execution(
            tool=tool,
            operation="read",
            parameters={},
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.TOOL_TEST,
        )
        assert execution.connection_id is None

        async def invoke(parameters, resolved):
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(
                tool,
                "read",
                {},
                _context(user, team, execution_id=execution.id, connection_id=uuid4()),
                invoke,
            )

        assert exc.value.code == 409
        assert exc.value.msg_key == "tool_approval_binding_changed"
        assert exc.value.status_code == 409
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_malformed_explicit_policy_is_rejected_before_execution():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        calls = []

        async def invoke(parameters, resolved):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(
                tool,
                "read",
                {},
                _context(user, team),
                invoke,
                policy={"default_decision": "sometimes"},
            )

        assert (
            exc.value.code == ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert exc.value.msg_key == "tool_approval_policy_configuration_required"
        assert exc.value.status_code == 409
        assert calls == []
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_malformed_stored_policy_fails_an_agent_call_closed():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        tool.approval_policy = {"default_decision": "sometimes"}
        calls = []

        async def invoke(parameters, resolved):
            calls.append(parameters)
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(
                tool,
                "read",
                {},
                _context(user, team, entrypoint=ExecutionEntrypoint.CHAT),
                invoke,
            )

        assert (
            exc.value.code == ResponseCode.TOOL_APPROVAL_POLICY_CONFIGURATION_REQUIRED
        )
        assert exc.value.msg_key == "tool_approval_policy_configuration_required"
        assert calls == []
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_claim_reauthorization_rejects_a_deactivated_actor(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        real_claim = tool_approvals.claim_execution

        async def claim_with_stale_actor(execution_id, **kwargs):
            inner = kwargs.pop("authorizer")

            async def wrapped(execution):
                await User.filter(id=user.id).update(is_active=False)
                await inner(execution)

            return await real_claim(execution_id, authorizer=wrapped, **kwargs)

        monkeypatch.setattr(tool_approvals, "claim_execution", claim_with_stale_actor)

        async def invoke(parameters, resolved):
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(tool, "read", {}, _context(user, team), invoke)

        assert exc.value.code == 403
        assert exc.value.msg_key == "tool_access_denied"
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_claim_reauthorization_detects_a_changed_definition(monkeypatch):
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()
        real_claim = tool_approvals.claim_execution

        async def claim_with_changed_definition(execution_id, **kwargs):
            inner = kwargs.pop("authorizer")

            async def wrapped(execution):
                await Tool.filter(id=tool.id).update(definition_version=99)
                await inner(execution)

            return await real_claim(execution_id, authorizer=wrapped, **kwargs)

        monkeypatch.setattr(
            tool_approvals, "claim_execution", claim_with_changed_definition
        )

        async def invoke(parameters, resolved):
            return {"ok": True}

        with pytest.raises(BusinessError) as exc:
            await execute_stored_tool(tool, "read", {}, _context(user, team), invoke)

        assert exc.value.code == 409
        assert exc.value.msg_key == "tool_approval_binding_changed"
        assert exc.value.status_code == 409
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_an_unsuccessful_result_marks_the_execution_failed():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user, team, tool = await _fixture()

        async def invoke(parameters, resolved):
            return {"success": False}

        result = await execute_stored_tool(
            tool, "read", {}, _context(user, team), invoke
        )

        assert result == {"success": False}
        execution = await ToolExecution.filter(tool_id=tool.id).first()
        assert execution is not None
        assert execution.status == ToolExecutionStatus.FAILED
        assert execution.error_code == "tool_execution_failed"
    finally:
        await Tortoise.close_connections()
