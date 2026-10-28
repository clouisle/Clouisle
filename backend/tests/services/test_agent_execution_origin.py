import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.tool_secrets import encrypt_tool_secret
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_connection import ToolConnection, ToolConnectionScope
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import ExecutionEntrypoint, ExecutionRunKind
from app.services.tool_context import entrypoint_is_interactive
from app.services.tool_execution import ToolCallContext, resolve_tool_connection


@pytest_asyncio.fixture
async def database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


def test_interactive_origin_is_derived_from_known_entrypoints():
    assert entrypoint_is_interactive("chat") is True
    assert entrypoint_is_interactive("agent_run") is True
    assert entrypoint_is_interactive("tool_test") is True
    assert entrypoint_is_interactive("feishu_channel") is True
    assert entrypoint_is_interactive("wechat_channel") is True
    for entrypoint in (
        "api_key",
        "embed",
        "channel",
        "schedule",
        "subworkflow",
        "nested_agent",
        None,
        "legacy-unknown",
    ):
        assert entrypoint_is_interactive(entrypoint) is False


@pytest.mark.asyncio
async def test_personal_default_is_not_used_by_background_origins(database):
    owner = await User.create(
        id=uuid4(),
        username=f"origin_{uuid4().hex[:8]}",
        email=f"{uuid4().hex}@origin.test",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name=f"origin_team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    tool = await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"origin_tool_{uuid4().hex[:8]}",
        display_name="Origin tool",
        description="origin test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        identity_policy="personal_only",
        approval_policy={"default_decision": "allow"},
        connection_fields=[],
    )
    connection = await ToolConnection.create(
        id=uuid4(),
        team_id=team.id,
        tool_id=tool.id,
        scope=ToolConnectionScope.USER,
        owner_user_id=owner.id,
        name="owner account",
        account_label="owner@example.test",
        encrypted_config="",
        secret_fields=[],
        is_default=True,
        default_slot=f"user:{team.id}:{owner.id}:tool:{tool.id}",
        status="active",
    )

    interactive = ToolCallContext(
        actor=owner,
        team_id=team.id,
        entrypoint=ExecutionEntrypoint.CHAT,
        entrypoint_id=str(uuid4()),
        interactive=True,
    )
    resolved, binding = await resolve_tool_connection(tool, interactive, "read")
    assert resolved is not None
    assert resolved.connection_id == connection.id
    assert binding is not None
    assert binding.connection_id == connection.id

    for entrypoint in (
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.CHANNEL,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.SUBWORKFLOW,
        ExecutionEntrypoint.NESTED_AGENT,
    ):
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=entrypoint,
            entrypoint_id=str(uuid4()),
            interactive=False,
        )
        with pytest.raises(BusinessError) as blocked:
            await resolve_tool_connection(tool, context, "read")
        assert int(blocked.value.code) == int(ResponseCode.TOOL_CONNECTION_REQUIRED)

    for entrypoint in (
        ExecutionEntrypoint.FEISHU_CHANNEL,
        ExecutionEntrypoint.WECHAT_CHANNEL,
    ):
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=entrypoint,
            entrypoint_id=str(uuid4()),
            interactive=True,
        )
        with pytest.raises(BusinessError) as blocked:
            await resolve_tool_connection(tool, context, "read")
        assert int(blocked.value.code) == int(ResponseCode.TOOL_CONNECTION_REQUIRED)


async def _user(prefix: str) -> User:
    suffix = uuid4().hex[:8]
    return await User.create(
        id=uuid4(),
        username=f"{prefix}_{suffix}",
        email=f"{suffix}@{prefix}.test",
        hashed_password="x",
    )


async def _team_with_owner(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


async def _selectable_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=f"auto_tool_{uuid4().hex[:8]}",
        display_name="Automatic tool",
        description="automatic connection test",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        identity_policy="selectable",
        approval_policy={"default_decision": "allow"},
        connection_fields=[{"name": "token", "required": True, "secret": True}],
    )


@pytest.mark.asyncio
async def test_chat_tool_reports_access_and_connection_guidance(database):
    from app.api.v1.endpoints.chat_tools import execute_tool_call
    from app.core.i18n import set_language
    from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope
    from app.models.user import Permission, Role

    owner = await _user("guidance_owner")
    member = await _user("guidance_member")
    team = await _team_with_owner(owner)
    permission = await Permission.create(code="team:read", scope="team")
    role = await Role.create(name="Guidance reader")
    await role.permissions.add(permission)
    await member.roles.add(role)
    await TeamMember.create(team_id=team.id, user_id=member.id, role="member")
    tool = await _selectable_tool(team)
    tool.created_by_id = owner.id
    tool.visibility = "private"
    await tool.save()
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=team.id,
        tools_config=[{"type": "custom", "tool_id": str(tool.id)}],
    )
    set_language("zh")
    with tool_identity_scope(RuntimeToolIdentity(entrypoint="chat", interactive=True)):
        denied = json.loads(
            await execute_tool_call(f"custom_{tool.name}", {}, agent=agent, user=member)
        )
        assert "Automatic tool" in denied["error"] and "无权" in denied["error"]
        tool.visibility = "team"
        await tool.save()
        missing = json.loads(
            await execute_tool_call(f"custom_{tool.name}", {}, agent=agent, user=member)
        )
        assert "Automatic tool" in missing["error"] and "登录" in missing["error"]
        connection = await _personal_connection(team, tool, member, "token")
        connection.status = "reauth_required"
        await connection.save()
        inactive = json.loads(
            await execute_tool_call(f"custom_{tool.name}", {}, agent=agent, user=member)
        )
        assert "Automatic tool" in inactive["error"] and "重新登录" in inactive["error"]
    set_language("en")


async def _personal_connection(
    team: Team, tool: Tool, owner: User, token: str, *, is_default: bool = False
) -> ToolConnection:
    return await ToolConnection.create(
        id=uuid4(),
        team_id=team.id,
        tool_id=tool.id,
        scope=ToolConnectionScope.USER,
        owner_user_id=owner.id,
        name=f"{owner.username} account",
        account_label=f"{owner.username}@example.test",
        encrypted_config=encrypt_tool_secret(
            json.dumps({"token": token}, separators=(",", ":"))
        ),
        secret_fields=["token"],
        is_default=is_default,
        default_slot=(
            f"user:{team.id}:{owner.id}:tool:{tool.id}" if is_default else None
        ),
        status="active",
    )


@pytest.mark.asyncio
async def test_missing_mode_selects_each_callers_personal_connection(database):
    owner = await _user("owner")
    member = await _user("member")
    team = await _team_with_owner(owner)
    await TeamMember.create(
        id=uuid4(), team_id=team.id, user_id=member.id, role="member"
    )
    tool = await _selectable_tool(team)
    owner_connection = await _personal_connection(team, tool, owner, "owner-token")
    member_connection = await _personal_connection(team, tool, member, "member-token")

    for actor, expected, token in (
        (owner, owner_connection, "owner-token"),
        (member, member_connection, "member-token"),
    ):
        context = ToolCallContext(
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_id=str(uuid4()),
            interactive=True,
        )
        resolved, binding = await resolve_tool_connection(tool, context, "read")
        assert resolved is not None
        assert resolved.connection_id == expected.id
        assert resolved.effective_user_id == actor.id
        assert dict(resolved.secrets) == {"token": token}
        assert binding is not None
        assert binding.connection_id == expected.id
        assert binding.effective_user_id == actor.id

    # An explicit default wins over the other available accounts.
    default_connection = await _personal_connection(
        team, tool, owner, "owner-default", is_default=True
    )
    resolved, _ = await resolve_tool_connection(
        tool,
        ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_id=str(uuid4()),
            interactive=True,
        ),
        "read",
    )
    assert resolved is not None
    assert resolved.connection_id == default_connection.id
    assert dict(resolved.secrets) == {"token": "owner-default"}

    # Two personal accounts with no default are ambiguous and fail closed.
    await _personal_connection(team, tool, member, "member-second")
    with pytest.raises(BusinessError) as ambiguous:
        await resolve_tool_connection(
            tool,
            ToolCallContext(
                actor=member,
                team_id=team.id,
                entrypoint=ExecutionEntrypoint.CHAT,
                entrypoint_id=str(uuid4()),
                interactive=True,
            ),
            "read",
        )
    assert int(ambiguous.value.code) == int(
        ResponseCode.TOOL_CONNECTION_DEFAULT_REQUIRED
    )
    assert ambiguous.value.msg_key == "tool_connection_default_required"


@pytest.mark.asyncio
async def test_manual_workflow_origin_auto_selects_triggering_user(database):
    owner = await _user("flow_owner")
    member = await _user("flow_member")
    team = await _team_with_owner(owner)
    await TeamMember.create(
        id=uuid4(), team_id=team.id, user_id=member.id, role="member"
    )
    tool = await _selectable_tool(team)
    owner_connection = await _personal_connection(team, tool, owner, "flow-owner")
    member_connection = await _personal_connection(team, tool, member, "flow-member")

    workflow_id = uuid4()
    for actor, expected in (
        (owner, owner_connection),
        (member, member_connection),
    ):
        context = ToolCallContext(
            actor=actor,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.WORKFLOW,
            entrypoint_id=str(workflow_id),
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=uuid4(),
            tool_call_id=f"call-{actor.id}",
            interactive=False,
        )
        resolved, binding = await resolve_tool_connection(tool, context, "read")
        assert resolved is not None
        assert resolved.connection_id == expected.id
        assert resolved.effective_user_id == actor.id
        assert binding is not None
        assert binding.connection_id == expected.id

    # Background workflow origins remain fixed-only even for the same tool.
    for entrypoint in (
        ExecutionEntrypoint.API_KEY,
        ExecutionEntrypoint.EMBED,
        ExecutionEntrypoint.SCHEDULE,
        ExecutionEntrypoint.SUBWORKFLOW,
    ):
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=entrypoint,
            entrypoint_id=str(uuid4()),
            run_kind=ExecutionRunKind.WORKFLOW,
            run_id=uuid4(),
            tool_call_id=f"call-{entrypoint.value}",
            interactive=False,
        )
        with pytest.raises(BusinessError) as blocked:
            await resolve_tool_connection(tool, context, "read")
        assert int(blocked.value.code) == int(ResponseCode.TOOL_CONNECTION_REQUIRED)


def test_run_payload_persists_trusted_origin():
    from app.models.agent_run import AgentRunMode
    from app.services.agent_run_worker import build_payload

    payload = build_payload(
        agent_id=uuid4(),
        conversation_id=uuid4(),
        user_id=uuid4(),
        mode=AgentRunMode.SEND,
        user_message_id=uuid4(),
        round_id=uuid4(),
        run_id=uuid4(),
        message="hello",
        tool_entrypoint="embed",
        tool_entrypoint_id="agent-123",
    )
    assert payload["tool_entrypoint"] == "embed"
    assert payload["tool_entrypoint_id"] == "agent-123"


def test_submit_origin_mapping_is_server_derived_only():
    from app.models.tool_approval import ExecutionEntrypoint
    from app.services.agent_submission import resolve_tool_origin

    key = SimpleNamespace(id=uuid4())
    assert resolve_tool_origin(key) == (ExecutionEntrypoint.API_KEY, str(key.id))
    assert resolve_tool_origin(None) == (ExecutionEntrypoint.CHAT, None)
    assert resolve_tool_origin(
        key,
        ExecutionEntrypoint.EMBED,
        "agent-embed-1",
    ) == (ExecutionEntrypoint.EMBED, "agent-embed-1")
    assert resolve_tool_origin(
        None,
        ExecutionEntrypoint.CHANNEL,
        "integration-1",
    ) == (ExecutionEntrypoint.CHANNEL, "integration-1")
    assert resolve_tool_origin(
        None,
        "agent_run",
        None,
    ) == (ExecutionEntrypoint.AGENT_RUN, None)
