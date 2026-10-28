"""Real persistence tests for identity-bound approval execution."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.tool import Tool, ToolShare
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ToolApprovalRequest,
    ToolExecution,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.schemas.response import BusinessError
from app.schemas.tool_connection import ToolConnectionCreate
from app.services.tool_approvals import REDACTED, decide_approval
from app.services.tool_connections import ToolConnectionService
from app.services.tool_execution import (
    PendingToolApproval,
    ToolCallContext,
    execute_stored_tool,
)


async def grant_team_read(user):
    permission = await Permission.filter(code="team:read").first()
    if permission is None:
        permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"Tool user {uuid4().hex[:6]}")
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


@pytest.mark.asyncio
async def test_chat_mcp_child_policy_pauses_before_call_and_resumes_once(monkeypatch):
    import json
    from types import SimpleNamespace

    from app.api.v1.endpoints.chat_tools import execute_tool_call
    from app.llm.tools.interaction import ToolInteractionRequest
    from app.models.tool_approval import ToolExecution
    from app.services.tool import ToolExecutor
    from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username="mcp_chat", email="mcp_chat@test.invalid", hashed_password="x"
        )
        await grant_team_read(user)
        team = await Team.create(name="MCP chat")
        await TeamMember.create(team=team, user=user, role="owner")
        tool = await Tool.create(
            name="personal_tasks",
            display_name="Tasks",
            description="",
            team=team,
            created_by=user,
            type="mcp",
            mcp_config={"transport": "http", "url": "https://example.invalid/mcp"},
            approval_policy={
                "default_decision": "allow",
                "operation_overrides": {
                    "tool:delete_task": {"default_decision": "require_approval"}
                },
            },
        )
        agent = SimpleNamespace(
            id=uuid4(),
            team_id=team.id,
            tools_config=[{"type": "mcp", "server_id": str(tool.id)}],
        )
        calls = []

        async def call_mcp(config, operation, parameters, **kwargs):
            calls.append((operation, parameters))
            return SimpleNamespace(to_dict=lambda: {"success": True, "result": "ok"})

        monkeypatch.setattr("app.services.tool.execute_mcp_tool", call_mcp)
        with tool_identity_scope(
            RuntimeToolIdentity(entrypoint="chat", interactive=True)
        ):
            pending = await execute_tool_call(
                "mcp_personal_tasks_delete_task", {"id": 7}, agent=agent, user=user
            )
            assert isinstance(pending, ToolInteractionRequest)
            assert pending.arguments["interaction_kind"] == "tool_approval"
            assert calls == []
            execution_id = pending.arguments["execution_id"]
            execution = await ToolExecution.get(id=execution_id)
            assert execution.operation == "tool:delete_task"
            gate = await ToolApprovalRequest.get(execution_id=execution_id)
            await decide_approval(
                gate.id, user, decision="approve", idempotency_key=uuid4().hex
            )
            context = ToolCallContext(
                actor=user,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                interactive=True,
                execution_id=execution.id,
            )
            result = await ToolExecutor().execute(
                tool, {"id": 7}, context=context, operation="delete_task"
            )
            assert result == {"success": True, "result": "ok"}
            with pytest.raises(BusinessError):
                await ToolExecutor().execute(
                    tool, {"id": 7}, context=context, operation="delete_task"
                )
            allowed = await execute_tool_call(
                "mcp_personal_tasks_list_tasks", {}, agent=agent, user=user
            )
            assert json.loads(allowed)["success"] is True
        assert calls == [("delete_task", {"id": 7}), ("list_tasks", {})]
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entrypoint,run_kind,interactive,require_approval,expected_wait",
    [
        ("chat", None, True, True, True),
        ("agent_run", None, True, True, True),
        ("chat", "workflow", True, True, False),
        ("workflow", None, False, True, False),
        ("tool_test", None, True, True, False),
        ("admin_test", None, True, True, False),
        ("api_key", None, False, True, "closed"),
        ("chat", None, False, True, "closed"),
        ("chat", None, True, False, False),
    ],
)
async def test_agent_confirmation_cannot_be_relaxed_by_mcp_child_allow(
    entrypoint, run_kind, interactive, require_approval, expected_wait
):
    from app.models.tool_approval import ExecutionRunKind

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username="origins", email="origins@test.invalid", hashed_password="x"
        )
        await grant_team_read(user)
        team = await Team.create(name="Origins")
        await TeamMember.create(team=team, user=user, role="owner")
        tool = await Tool.create(
            name="tasks",
            display_name="Tasks",
            description="",
            team=team,
            created_by=user,
            type="mcp",
            approval_policy={
                "default_decision": "require_approval",
                "operation_overrides": {"tool:read": {"default_decision": "allow"}},
            },
        )
        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint(entrypoint),
            entrypoint_id="origin",
            run_kind=ExecutionRunKind(run_kind) if run_kind else None,
            run_id=uuid4() if run_kind else None,
            interactive=interactive,
            require_approval=require_approval,
        )
        calls = []

        async def invoke(parameters, connection):
            calls.append(parameters)
            return {"result": "read"}

        if expected_wait == "closed":
            # A non-interactive Agent run cannot satisfy a caller gate, so the
            # tool policy fails closed instead of being skipped.
            with pytest.raises(BusinessError) as fail_closed:
                await execute_stored_tool(tool, "tool:read", {}, context, invoke)
            assert fail_closed.value.msg_key == (
                "tool_approval_policy_configuration_required"
            )
            assert fail_closed.value.data == {"reason": "approval_audience_unavailable"}
            assert calls == []
            return

        result = await execute_stored_tool(tool, "tool:read", {}, context, invoke)
        if expected_wait:
            assert isinstance(result, PendingToolApproval)
            assert calls == []
        else:
            assert result == {"result": "read"}
            assert calls == [{}]
        if not expected_wait and not (
            entrypoint == "chat" and interactive and not run_kind
        ):
            result = await execute_stored_tool(tool, "tool:delete", {}, context, invoke)
            assert result == {"result": "read"}
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_shared_workflow_uses_bound_owner_connection_but_direct_ids_do_not():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        owner = await User.create(
            username="owner", email="owner@test.invalid", hashed_password="x"
        )
        member = await User.create(
            username="member", email="member@test.invalid", hashed_password="x"
        )
        await grant_team_read(owner)
        await grant_team_read(member)
        team = await Team.create(name="Shared workflow")
        await TeamMember.create(team=team, user=owner, role="owner")
        await TeamMember.create(team=team, user=member, role="member")
        tool = await Tool.create(
            name="tasks",
            display_name="Tasks",
            description="",
            team=team,
            created_by=owner,
            type="mcp",
            visibility="team",
            identity_policy="personal_only",
            connection_fields=[{"name": "token", "required": True, "secret": True}],
            approval_policy={"default_decision": "allow"},
        )
        connection = await ToolConnectionService.create_connection(
            actor=owner,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=tool.id,
                scope="user",
                name="Owner account",
                config={"token": "owner-secret"},
            ),
        )
        calls = []

        async def invoke(parameters, resolved):
            calls.append(resolved.secrets["token"])
            return {"ok": True}

        # An untrusted direct selection of the owner's personal connection fails.
        with pytest.raises(BusinessError):
            await execute_stored_tool(
                tool,
                "tool:read",
                {},
                ToolCallContext(
                    actor=member,
                    team_id=team.id,
                    entrypoint=ExecutionEntrypoint.TOOL_TEST,
                    interactive=True,
                    connection_id=connection.id,
                ),
                invoke,
            )
        assert calls == []

        # A persisted workflow binding authorizes the member to execute it.
        assert await execute_stored_tool(
            tool,
            "tool:read",
            {},
            ToolCallContext(
                actor=member,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.WORKFLOW,
                entrypoint_id="workflow-1",
                interactive=False,
                connection_id=connection.id,
            ),
            invoke,
        ) == {"ok": True}
        assert calls == ["owner-secret"]
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_type", ["builtin", "custom", "mcp"])
async def test_approval_preview_keeps_business_arguments_and_redacts_secrets(
    tool_type,
):
    """Every tool type previews the invoked arguments, not its configuration."""

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username=f"preview_{tool_type}",
            email=f"preview_{tool_type}@test.invalid",
            hashed_password="x",
        )
        await grant_team_read(user)
        team = await Team.create(name=f"Preview {tool_type}")
        await TeamMember.create(team=team, user=user, role="owner")
        tool = await Tool.create(
            name=f"preview_{tool_type}",
            display_name="Preview",
            description="",
            team=team,
            created_by=user,
            type=tool_type,
            identity_policy="none",
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        parameters = {
            "order_id": "A-100",
            "customer": {"name": "Ada", "password": "s3cret"},
            "token_count": 3,
        }
        calls = []

        async def invoke(approved, _resolved):
            calls.append(approved)
            return {"ok": True}

        pending = await execute_stored_tool(
            tool,
            "tool:read" if tool_type == "mcp" else "read",
            parameters,
            ToolCallContext(
                actor=user,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                interactive=True,
                require_approval=True,
            ),
            invoke,
        )
        assert isinstance(pending, PendingToolApproval)
        assert calls == []

        execution = await ToolExecution.get(id=pending.execution_id)
        assert execution.parameters_preview == {
            "order_id": "A-100",
            "customer": {"name": "Ada", "password": REDACTED},
            # Exact-name matching only: a business counter stays readable.
            "token_count": 3,
        }
        assert "s3cret" not in str(execution.parameters_preview)
        assert "s3cret" not in str(execution.parameters_cipher)
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_builtin_web_search_preview_excludes_orchestration_engine(monkeypatch):
    """The Agent-selected engine is execution config, not a call argument."""

    from app.services import tool as tool_service
    from app.services.tool import ToolExecutor

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username="search_preview",
            email="search_preview@test.invalid",
            hashed_password="x",
        )
        await grant_team_read(user)
        team = await Team.create(name="Search preview")
        await TeamMember.create(team=team, user=user, role="owner")
        definition = await Tool.create(
            name="web_search",
            display_name="Web Search",
            description="",
            team=team,
            created_by=user,
            type="builtin",
            identity_policy="none",
            approval_policy={
                "default_decision": "require_approval",
                "gates": [{"kind": "caller"}],
            },
        )
        monkeypatch.setattr(
            tool_service, "get_builtin_definition", AsyncMock(return_value=definition)
        )
        executed = []

        async def fake_execute(name, arguments, credentials=None, **kwargs):
            executed.append((name, arguments, credentials))
            return {"ok": True}

        monkeypatch.setattr(tool_service.tool_registry, "execute", fake_execute)
        from app.models.tool_approval import ExecutionRunKind

        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            run_kind=ExecutionRunKind.AGENT,
            run_id=uuid4(),
            tool_call_id="call-search",
            interactive=True,
            require_approval=True,
        )

        pending = await ToolExecutor().execute_builtin_tool(
            "web_search",
            {"query": "weather"},
            team_id=team.id,
            context=context,
            agent_tool_config={"engine": "bocha"},
        )
        assert isinstance(pending, PendingToolApproval)
        assert executed == []

        execution = await ToolExecution.get(id=pending.execution_id)
        assert execution.parameters_preview == {"query": "weather"}
        gate = await ToolApprovalRequest.get(execution_id=execution.id)
        await decide_approval(
            gate.id, user, decision="approve", idempotency_key=uuid4().hex
        )

        result = await ToolExecutor().execute_builtin_tool(
            "web_search",
            {},
            team_id=team.id,
            context=context,
            agent_tool_config={"engine": "bocha"},
        )
        assert result == {"ok": True}
        # The handler still receives the orchestration engine; neither the
        # approval preview nor the model arguments contain it.
        assert executed == [
            ("web_search", {"query": "weather", "search_engine": "bocha"}, {})
        ]
        refreshed = await ToolExecution.get(id=execution.id)
        assert refreshed.parameters_preview == {"query": "weather"}
    finally:
        await Tortoise.close_connections()
