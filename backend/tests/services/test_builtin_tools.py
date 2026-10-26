"""Stable builtin definitions and unified execution boundary behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.llm.tools import tool_registry
from app.llm.tools.registry import ToolConcurrency, ToolInfo
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_approval import (
    ExecutionEntrypoint,
    ToolExecution,
    ToolExecutionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool_approval import ApprovalDecision, ToolApprovalPolicy
from app.schemas.tool_connection import ToolConnectionCreate
from app.models.tool_connection import ToolConnectionScope
from app.services.builtin_tools import get_builtin_definition
from app.services.tool import ToolExecutor
from app.services.tool_connections import ToolConnectionService
from app.services.tool_execution import ToolCallContext


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'builtin-tools.sqlite3'}"

    def run(scenario):
        async def _wrapped():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                await context.generate_schemas()
                return await scenario()

        return runner.run(_wrapped())

    try:
        yield run
    finally:
        runner.close()


async def _fixtures():
    user = await User.create(
        id=uuid4(),
        username="builtin-owner",
        email="builtin-owner@example.com",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name="builtin-team", owner_id=user.id)
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=user.id, role="owner")
    return user, team


def test_builtin_definition_is_stable_and_fail_closed(run_orm):
    async def scenario():
        _user, team = await _fixtures()

        first = await get_builtin_definition(team.id, "get_current_time")
        second = await get_builtin_definition(team.id, "get_current_time")
        assert first.id == second.id
        assert await Tool.filter(team_id=team.id, type=ToolType.BUILTIN).count() == 1
        assert first.identity_policy == "none"
        assert first.visibility.value == "team"
        assert first.approval_policy["default_decision"] == "allow"
        assert first.parameters

        # Read-only evidence is explicit; side-effecting builtins keep the
        # fail-closed require-approval default.
        exclusive = await get_builtin_definition(team.id, "bash")
        assert exclusive.approval_policy == {}

        # A user-defined tool must never be shadowed by a builtin name.
        other_team = await Team.create(
            id=uuid4(), name="builtin-team-2", owner_id=_user.id
        )
        await Tool.create(
            id=uuid4(),
            team_id=other_team.id,
            name="calculate",
            display_name="Custom calculate",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
        )
        with pytest.raises(BusinessError) as exc:
            await get_builtin_definition(other_team.id, "calculate")
        assert exc.value.code == ResponseCode.DUPLICATE_NAME

        with pytest.raises(BusinessError) as exc:
            await get_builtin_definition(team.id, "not_a_registered_tool")
        assert exc.value.code == ResponseCode.NOT_FOUND

        with pytest.raises(BusinessError) as exc:
            await get_builtin_definition(None, "get_current_time")
        assert exc.value.code == ResponseCode.FORBIDDEN

    run_orm(scenario)


def test_builtin_key_default_resolves_for_materialized_definition(run_orm):
    from app.llm.tools import tool_registry
    from app.llm.tools.registry import ToolConcurrency, ToolInfo

    tool_registry.register_tool(
        ToolInfo(
            name="fake_default_tool",
            description="test-only default tool",
            parameters=[],
            handler=lambda credentials=None: None,
            concurrency=ToolConcurrency.EXCLUSIVE,
        )
    )

    async def scenario():
        user, team = await _fixtures()
        other_team = await Team.create(
            id=uuid4(), name="builtin-default-other", owner_id=user.id
        )
        await TeamMember.create(
            id=uuid4(), team_id=other_team.id, user_id=user.id, role="owner"
        )
        definition = await get_builtin_definition(team.id, "fake_default_tool")
        # Legacy/consumer-created default keyed by builtin_tool_key, before the
        # stable definition existed.
        await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                builtin_tool_key="fake_default_tool",
                scope=ToolConnectionScope.TEAM,
                name="Legacy default",
                config={"api_key": "default-secret"},
                is_default=True,
            ),
        )
        await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=other_team.id,
                builtin_tool_key="fake_default_tool",
                scope=ToolConnectionScope.TEAM,
                name="Other team default",
                config={"api_key": "other-secret"},
                is_default=True,
            ),
        )
        definition.identity_policy = "team_only"
        definition.connection_fields = [
            {"name": "api_key", "label": "API key", "required": True, "secret": True}
        ]
        await definition.save()

        resolved = await ToolConnectionService.resolve_connection(
            team_id=team.id,
            actor=user,
            use_default=True,
            scope=ToolConnectionScope.TEAM,
            tool_id=definition.id,
            builtin_tool_key=definition.name,
        )
        assert resolved.secrets == {"api_key": "default-secret"}

    try:
        run_orm(scenario)
    finally:
        from app.llm.tools import tool_registry as registry

        registry.unregister("fake_default_tool")


def test_internal_descriptors_and_skill_refresh_fail_closed(run_orm):
    from app.services.builtin_tools import (
        get_builtin_definition,
        supported_internal_tool_keys,
    )

    async def scenario():
        _user, team = await _fixtures()
        assert "list_assets" in supported_internal_tool_keys()
        assert "knowledge_search" in supported_internal_tool_keys()
        assert "search_memory" in supported_internal_tool_keys()
        assert "file_download" in supported_internal_tool_keys()
        assert "ask_user" not in supported_internal_tool_keys()

        internal = await get_builtin_definition(team.id, "list_assets")
        assert internal.type == ToolType.BUILTIN
        assert internal.approval_policy["default_decision"] == "allow"
        assert internal.identity_policy == "none"
        mutation = await get_builtin_definition(team.id, "materialize_asset")
        assert mutation.approval_policy == {}

        # A legacy empty synthetic row is upgraded; an admin policy is kept.
        await Tool.filter(id=internal.id).update(approval_policy={})
        refreshed_readonly = await get_builtin_definition(team.id, "list_assets")
        assert refreshed_readonly.approval_policy["default_decision"] == "allow"

        skill = await get_builtin_definition(
            team.id,
            "skill_research_123",
            descriptor={
                "name": "skill_research_123",
                "description": "Skill v1",
                "parameters": [{"name": "query", "type": "string"}],
                "definition_version": 3,
                "approval_policy": {"default_decision": "allow"},
            },
        )
        assert skill.definition_version == 3
        assert skill.parameters == [{"name": "query", "type": "string"}]
        # Descriptor approval is ignored: skills require approval; only the
        # audited internal read-only set (and registry/sandbox SHARED) may allow.
        assert skill.approval_policy == {}

        refreshed = await get_builtin_definition(
            team.id,
            "skill_research_123",
            descriptor={
                "name": "skill_research_123",
                "description": "Skill v2",
                "parameters": [],
                "definition_version": 4,
            },
        )
        assert refreshed.id == skill.id
        assert refreshed.definition_version == 4
        assert refreshed.description == "Skill v2"

    run_orm(scenario)


def test_registry_identity_requires_connection_when_config_declared(
    run_orm, monkeypatch
):
    from app.schemas.tool import BUILTIN_TOOLS_METADATA

    monkeypatch.setitem(
        BUILTIN_TOOLS_METADATA,
        "get_current_time",
        {
            "requires_config": True,
            "config_fields": ["SERPER_API_KEY"],
        },
    )

    async def scenario():
        _user, team = await _fixtures()
        definition = await get_builtin_definition(team.id, "get_current_time")
        assert definition.identity_policy == "team_only"
        assert definition.connection_fields == [
            {
                "name": "SERPER_API_KEY",
                "label": "SERPER_API_KEY",
                "required": True,
                "secret": True,
            }
        ]

        # Legacy rows persisted with identity none are upgraded, not replaced.
        legacy_team = await Team.create(
            id=uuid4(), name="legacy-identity-team", owner_id=_user.id
        )
        await Tool.create(
            id=uuid4(),
            team_id=legacy_team.id,
            name="get_current_time",
            display_name="get_current_time",
            description="legacy",
            type=ToolType.BUILTIN,
            identity_policy="none",
            connection_fields=[],
        )
        refreshed = await get_builtin_definition(legacy_team.id, "get_current_time")
        assert refreshed.identity_policy == "team_only"
        assert {field["name"] for field in refreshed.connection_fields} == {
            "SERPER_API_KEY"
        }

    run_orm(scenario)


def test_builtin_execution_uses_connection_and_approval_boundary(run_orm, monkeypatch):
    from app.api.v1.endpoints import tools as tools_endpoint
    from app.api import team_access

    monkeypatch.setattr(
        tools_endpoint, "check_tool_access", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(team_access, "check_team_access", AsyncMock(return_value=None))

    async def handler(credentials=None):
        return {"credentials": credentials}

    tool_registry.register_tool(
        ToolInfo(
            name="fake_boundary_tool",
            description="test-only builtin",
            parameters=[],
            handler=handler,
            concurrency=ToolConcurrency.EXCLUSIVE,
        )
    )

    async def scenario():
        user, team = await _fixtures()
        definition = await get_builtin_definition(team.id, "fake_boundary_tool")
        assert definition.approval_policy == {}

        connection = await ToolConnectionService.create_connection(
            actor=user,
            payload=ToolConnectionCreate(
                team_id=team.id,
                tool_id=definition.id,
                scope=ToolConnectionScope.TEAM,
                name="Boundary account",
                config={"api_key": "boundary-secret"},
                is_default=True,
            ),
        )
        definition.identity_policy = "team_only"
        definition.connection_fields = [
            {"name": "api_key", "label": "API key", "required": True, "secret": True}
        ]
        # Explicit operator decision: this test exercises secret injection, not
        # the approval gate (covered separately).
        definition.approval_policy = ToolApprovalPolicy(
            default_decision=ApprovalDecision.ALLOW
        ).model_dump(mode="json")
        await definition.save()

        context = ToolCallContext(
            actor=user,
            team_id=team.id,
            entrypoint=ExecutionEntrypoint.CHAT,
            entrypoint_id=str(team.id),
            interactive=True,
        )
        result = await ToolExecutor().execute_builtin_tool(
            tool_name="fake_boundary_tool",
            arguments={},
            team_id=team.id,
            context=context,
        )
        assert result == {"credentials": {"api_key": "boundary-secret"}}

        execution = await ToolExecution.filter(tool_id=definition.id).get()
        assert execution.status == ToolExecutionStatus.SUCCEEDED
        assert execution.connection_id == connection.id

        # Without an interactive audience a non-interactive entrypoint cannot
        # resolve a connection: fail closed instead of falling back.
        with pytest.raises(BusinessError) as exc:
            await ToolExecutor().execute_builtin_tool(
                tool_name="fake_boundary_tool",
                arguments={},
                team_id=team.id,
                context=ToolCallContext(
                    actor=user,
                    team_id=team.id,
                    entrypoint=ExecutionEntrypoint.WORKFLOW,
                    entrypoint_id=None,
                    interactive=False,
                ),
            )
        assert int(exc.value.code) in {
            int(ResponseCode.TOOL_CONNECTION_GRANT_DENIED),
            int(ResponseCode.TOOL_CONNECTION_REQUIRED),
            403,
        }

    try:
        run_orm(scenario)
    finally:
        tool_registry.unregister("fake_boundary_tool")
