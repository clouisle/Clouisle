from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_connection import ToolConnection, ToolConnectionScope
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError
from app.schemas.tool_approval import ExecutionEntrypoint
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
async def test_personal_default_is_only_used_by_interactive_origin(database):
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
    ):
        context = ToolCallContext(
            actor=owner,
            team_id=team.id,
            entrypoint=entrypoint,
            entrypoint_id=str(uuid4()),
            interactive=False,
        )
        with pytest.raises(BusinessError):
            await resolve_tool_connection(tool, context, "read")


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
