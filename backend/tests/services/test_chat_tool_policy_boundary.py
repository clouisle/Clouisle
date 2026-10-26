"""Real persistence tests for the early chat tool policy boundary.

These exercise the actual ``ToolExecution`` state machine: a managed operation
must create an approval gate without performing its side effect, and resuming
the approved execution must run the real operation exactly once with the
snapshotted parameters. Read-only internal tools use the audited explicit
allow list and must not create an approval gate.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.api.v1.endpoints import chat_tools
from app.llm.tools.interaction import ToolInteractionRequest
from app.models.agent import Agent, Conversation
from app.models.asset import Asset, AssetScopeRef, AssetScopeType, AssetSource
from app.models.skill import Skill
from app.models.tool import Tool
from app.models.tool_approval import (
    ToolApprovalRequest,
    ToolExecution,
    ToolExecutionStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.services.builtin_tools import supported_internal_tool_keys
from app.services.skill import SkillService
from app.services.tool_approvals import decide_approval
from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


async def _make_team_user() -> tuple[User, Team]:
    user = await User.create(
        username=f"policy-{uuid4().hex[:8]}",
        email=f"{uuid4().hex[:8]}@test.invalid",
        hashed_password="x",
    )
    permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"Policy user {uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await user.roles.add(role)
    team = await Team.create(name=f"Policy {uuid4().hex[:8]}")
    await TeamMember.create(team=team, user=user, role="owner")
    return user, team


async def _make_conversation(user: User, team: Team) -> tuple[Agent, Conversation]:
    agent = await Agent.create(
        id=uuid4(), name="policy-agent", team=team, enable_attachments=True
    )
    conversation = await Conversation.create(id=uuid4(), agent=agent, user=user)
    return agent, conversation


def _identity(
    conversation: Conversation, tool_call_id: str, **overrides
) -> RuntimeToolIdentity:
    values = dict(
        run_id=uuid4(),
        tool_call_id=tool_call_id,
        entrypoint="chat",
        entrypoint_id=str(conversation.id),
        interactive=True,
    )
    values.update(overrides)
    return RuntimeToolIdentity(**values)


async def _approve(request_id, user: User) -> None:
    await decide_approval(
        request_id, user, decision="approve", idempotency_key=uuid4().hex
    )


async def _asset(user: User, team: Team, ref: str, conversation: Conversation):
    asset = await Asset.create(
        id=uuid4(),
        team=team,
        created_by=user,
        storage_key=f"private/{uuid4()}",
        original_filename="notes.txt",
        display_filename="notes.txt",
        content_type="text/plain",
        size=12,
        checksum="a" * 64,
        source=AssetSource.UPLOAD,
    )
    await AssetScopeRef.create(
        id=uuid4(),
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation.id,
        asset=asset,
        ref=ref,
    )
    return asset


@pytest.mark.asyncio
async def test_materialize_asset_pending_has_no_side_effect_and_resume_runs_once(
    database,
):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    await _asset(user, team, "0001", conversation)
    submit = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    from app.services.sandbox.gateway import sandbox_gateway

    original_submit = sandbox_gateway.submit_and_wait
    sandbox_gateway.submit_and_wait = submit
    try:
        identity = _identity(
            conversation,
            "call-materialize",
            run_kind="workflow",
            entrypoint="workflow",
        )
        with tool_identity_scope(identity):
            pending = await chat_tools.execute_tool_call(
                "materialize_asset",
                {"ref": "0001", "path": "data/notes.txt"},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
                session_id="session-1",
            )
        assert isinstance(pending, ToolInteractionRequest)
        assert pending.arguments["interaction_kind"] == "tool_approval"
        assert submit.await_count == 0
        execution = await ToolExecution.get(id=UUID(pending.arguments["execution_id"]))
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL
        assert execution.run_kind.value == "workflow"
        definition = await Tool.get(id=execution.tool_id)
        assert definition.name == "materialize_asset"
        assert definition.approval_policy == {}

        gate = await ToolApprovalRequest.get(execution_id=execution.id)
        await _approve(gate.id, user)

        with tool_identity_scope(identity):
            result = json.loads(
                await chat_tools.execute_tool_call(
                    "materialize_asset",
                    {},
                    agent=agent,
                    user=user,
                    conversation_id=conversation.id,
                    session_id="session-1",
                )
            )
        assert result == {
            "ref": "0001",
            "path": "/workspace/data/notes.txt",
            "filename": "notes.txt",
            "size": 12,
        }
        assert submit.await_count == 1
        job = submit.await_args.args[0]
        assert job.input_files[0].target_path == "/workspace/data/notes.txt"
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.SUCCEEDED
    finally:
        sandbox_gateway.submit_and_wait = original_submit


@pytest.mark.asyncio
async def test_memory_mutation_pending_has_no_side_effect_and_resume_runs_once(
    database,
):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    handler = AsyncMock(return_value={"id": "entity-1", "name": "Python"})
    from app.services.memory import MemoryService

    original = MemoryService.handle_create_entity
    MemoryService.handle_create_entity = handler
    try:
        identity = _identity(conversation, "call-memory")
        with tool_identity_scope(identity):
            pending = await chat_tools.execute_tool_call(
                "create_memory_entity",
                {"name": "Python", "entity_type": "skill"},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
            )
        assert isinstance(pending, ToolInteractionRequest)
        assert handler.await_count == 0
        execution = await ToolExecution.get(id=UUID(pending.arguments["execution_id"]))
        assert execution.status == ToolExecutionStatus.AWAITING_APPROVAL

        gate = await ToolApprovalRequest.get(execution_id=execution.id)
        await _approve(gate.id, user)

        with tool_identity_scope(identity):
            result = json.loads(
                await chat_tools.execute_tool_call(
                    "create_memory_entity",
                    {},
                    agent=agent,
                    user=user,
                    conversation_id=conversation.id,
                )
            )
        assert result == {"id": "entity-1", "name": "Python"}
        assert handler.await_count == 1
        assert handler.await_args.kwargs["name"] == "Python"
        assert handler.await_args.kwargs["entity_type"] == "skill"
        await execution.refresh_from_db()
        assert execution.status == ToolExecutionStatus.SUCCEEDED
    finally:
        MemoryService.handle_create_entity = original


@pytest.mark.asyncio
async def test_noninteractive_identity_fails_closed_without_side_effect(database):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    handler = AsyncMock(return_value={"id": "entity-1"})
    from app.services.memory import MemoryService

    original = MemoryService.handle_create_entity
    MemoryService.handle_create_entity = handler
    try:
        with tool_identity_scope(
            RuntimeToolIdentity(
                entrypoint="channel",
                entrypoint_id="channel-1",
                interactive=False,
            )
        ):
            result = json.loads(
                await chat_tools.execute_tool_call(
                    "create_memory_entity",
                    {"name": "Python", "entity_type": "skill"},
                    agent=agent,
                    user=user,
                    conversation_id=conversation.id,
                )
            )
        assert result["error"]
        assert handler.await_count == 0
        assert await ToolExecution.all().count() == 0

        # A direct call with no trusted identity is also non-interactive.
        direct = json.loads(
            await chat_tools.execute_tool_call(
                "create_memory_entity",
                {"name": "Python", "entity_type": "skill"},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
            )
        )
        assert direct["error"]
        assert handler.await_count == 0
        assert await ToolExecution.all().count() == 0
    finally:
        MemoryService.handle_create_entity = original


@pytest.mark.asyncio
async def test_read_only_internal_tool_executes_without_approval(database):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    await _asset(user, team, "0002", conversation)
    identity = _identity(conversation, "call-inspect")
    with tool_identity_scope(identity):
        result = json.loads(
            await chat_tools.execute_tool_call(
                "inspect_asset",
                {"ref": "0002"},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
            )
        )
    assert result["ref"] == "0002"
    assert result["filename"] == "notes.txt"
    assert await ToolApprovalRequest.all().count() == 0
    execution = await ToolExecution.get()
    assert execution.status == ToolExecutionStatus.SUCCEEDED
    assert execution.run_kind.value == "agent"


@pytest.mark.asyncio
async def test_workflow_agent_pending_approval_is_cancelled_not_returned(database):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    handler = AsyncMock(return_value={"id": "entity-1"})
    from app.services.memory import MemoryService

    original = MemoryService.handle_create_entity
    MemoryService.handle_create_entity = handler
    try:
        identity = _identity(
            conversation,
            "workflow-agent:run:node:call-1",
            run_kind="workflow",
            entrypoint="workflow",
            tool_call_prefix="workflow-agent:run:node",
        )
        with tool_identity_scope(identity):
            result = json.loads(
                await chat_tools.execute_tool_call(
                    "create_memory_entity",
                    {"name": "Python", "entity_type": "skill"},
                    agent=agent,
                    user=user,
                    conversation_id=conversation.id,
                )
            )
        assert result["success"] is False
        assert result["tool_name"] == "create_memory_entity"
        assert result["error"]
        assert handler.await_count == 0
        execution = await ToolExecution.get()
        assert execution.status == ToolExecutionStatus.CANCELLED
    finally:
        MemoryService.handle_create_entity = original


@pytest.mark.asyncio
async def test_skill_definition_binds_real_version_and_rejects_stale_approval(
    database,
):
    user, team = await _make_team_user()
    agent, conversation = await _make_conversation(user, team)
    skill = await Skill.create(
        id=uuid4(),
        team=team,
        name="demo_skill",
        display_name="Demo Skill",
        description="Runs a demo",
        version="1.0.0",
        input_schema={"type": "object", "properties": {}},
        default_config={"mode": "fast"},
    )
    tool_name = SkillService.build_tool_name(skill)
    agent.tools_config = [
        {"type": "skill", "skill_id": str(skill.id), "config": {"nested": 1}}
    ]
    await agent.save()

    identity = _identity(conversation, "call-skill")
    with tool_identity_scope(identity):
        pending = await chat_tools.execute_tool_call(
            tool_name,
            {},
            agent=agent,
            user=user,
            conversation_id=conversation.id,
        )
    assert isinstance(pending, ToolInteractionRequest)
    execution = await ToolExecution.get(id=UUID(pending.arguments["execution_id"]))
    definition = await Tool.get(id=execution.tool_id)
    assert definition.name == tool_name
    expected = chat_tools._skill_definition_version(
        skill, {"mode": "fast", "nested": 1}
    )
    assert definition.definition_version == expected
    assert definition.approval_policy == {}
    assert expected >= 1

    gate = await ToolApprovalRequest.get(execution_id=execution.id)
    await _approve(gate.id, user)

    # The Skill changed after approval: the pinned definition version must
    # invalidate the old approval instead of executing the new code.
    skill.version = "1.1.0"
    await skill.save()
    with tool_identity_scope(identity):
        stale = json.loads(
            await chat_tools.execute_tool_call(
                tool_name,
                {},
                agent=agent,
                user=user,
                conversation_id=conversation.id,
            )
        )
    assert stale["error"]
    await execution.refresh_from_db()
    assert execution.status == ToolExecutionStatus.CANCELLED


def test_supported_internal_keys_cover_early_operations_without_ask_user():
    keys = set(supported_internal_tool_keys())
    assert {
        "list_assets",
        "inspect_asset",
        "read_asset",
        "search_asset",
        "materialize_asset",
        "view_asset",
        "knowledge_search",
        "create_memory_entity",
        "create_memory_relation",
        "update_memory_entity",
        "search_memory",
        "get_memory_subgraph",
    } <= keys
    assert "ask_user" not in keys


def test_skill_definition_version_tracks_real_content_and_config():
    skill = SimpleNamespace(
        id=uuid4(),
        version="1.0.0",
        package_hash="a" * 64,
        package_path="skills/demo",
        source_type="zip",
        source_uri=None,
        source_ref=None,
        source_subdir=None,
        input_schema={"type": "object", "properties": {}},
        default_config={},
    )
    first = chat_tools._skill_definition_version(skill, {"nested": 1})
    assert first == chat_tools._skill_definition_version(skill, {"nested": 1})
    assert first != chat_tools._skill_definition_version(skill, {"nested": 2})
    skill.version = "1.1.0"
    assert first != chat_tools._skill_definition_version(skill, {"nested": 1})


@pytest.mark.asyncio
async def test_wrapper_preserves_asset_view_result_identity(monkeypatch):
    view = chat_tools.AssetViewResult(
        display_result={"kind": "asset.view", "version": 1},
        llm_result="content-marker",
    )
    monkeypatch.setattr(
        chat_tools, "_policy_tool_context", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        chat_tools,
        "_resolve_policy_invoke",
        AsyncMock(return_value=(SimpleNamespace(), AsyncMock())),
    )
    monkeypatch.setattr(
        "app.services.tool_execution.execute_stored_tool",
        AsyncMock(return_value=view),
    )

    returned = await chat_tools._execute_policy_managed_tool(
        "view_asset",
        {"ref": "abcd"},
        agent=SimpleNamespace(team_id=uuid4()),
        user=SimpleNamespace(id=uuid4()),
        conversation_id=None,
        workflow_run_id=None,
        session_id=None,
    )

    assert returned is view
    assert returned.display_result == {"kind": "asset.view", "version": 1}
    assert returned.llm_result == "content-marker"
