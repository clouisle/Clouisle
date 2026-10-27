"""Execution-service behavior: derived tool-call context and OAuth boundaries.

Every scenario runs against a real SQLite Tortoise schema so actor lookup,
tool ownership and configuration copies use the production models. Only the
process-external collaborators (stored-tool runner, MCP/HTTP executors, OAuth
token exchange) are replaced.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_connection import ToolConnectionScope, ToolConnectionStatus
from app.models.user import Team, User
from app.schemas.response import BusinessError
from app.schemas.tool_approval import ExecutionEntrypoint
from app.services.tool import ToolExecutor, build_mcp_config
from app.services.tool_connections import ResolvedConnection
from app.services.tool_execution import ToolCallContext


@pytest.fixture
def run_orm(tmp_path):
    """Run one scenario against a fresh file-backed SQLite schema."""
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-service.sqlite3'}"

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


async def _make_user(name: str) -> User:
    return await User.create(
        id=uuid4(),
        username=name,
        email=f"{name}@tool-service.test",
        hashed_password="not-used",
    )


async def _make_team(name: str, owner: User) -> Team:
    return await Team.create(id=uuid4(), name=name, owner_id=owner.id)


async def _make_tool(team: Team, *, name: str, **values) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name=name,
        display_name=name,
        description="",
        **values,
    )


def _resolved(
    team: Team,
    user: User,
    tool: Tool | None = None,
    *,
    builtin_key: str | None = None,
) -> ResolvedConnection:
    return ResolvedConnection(
        connection_id=uuid4(),
        team_id=team.id,
        scope=ToolConnectionScope.USER,
        owner_user_id=user.id,
        effective_user_id=user.id,
        tool_id=tool.id if tool is not None else None,
        builtin_tool_key=builtin_key,
        account_label=None,
        status=ToolConnectionStatus.ACTIVE,
        secret_version=1,
        secrets={"api_key": "sk-live"},
    )


def _invoke_with(resolved):
    """Stored-tool boundary that immediately invokes with one connection."""

    async def fake_execute(tool_arg, operation, arguments, ctx_arg, invoke):
        return await invoke(arguments, resolved)

    return fake_execute


def test_execute_builtin_derives_context_from_actor_and_tool_team(run_orm):
    async def scenario():
        user = await _make_user("builtin-actor")
        team = await _make_team("builtin-team", user)
        tool = await _make_tool(team, name="get_current_time", type=ToolType.BUILTIN)
        executor = ToolExecutor()
        calls: list[dict] = []

        async def fake_execute_builtin_tool(**kwargs):
            calls.append(kwargs)
            return {"ok": True}

        with patch.object(
            executor, "execute_builtin_tool", new=fake_execute_builtin_tool
        ):
            chat_result = await executor.execute(
                tool, {"timezone_name": "UTC"}, user_id=str(user.id)
            )
            workflow_run_id = uuid4()
            workflow_result = await executor.execute(
                tool, {}, user_id=user.id, workflow_run_id=workflow_run_id
            )

        assert chat_result == {"ok": True}
        assert workflow_result == {"ok": True}
        chat_context = calls[0]["context"]
        assert chat_context.actor.id == user.id
        assert chat_context.team_id == team.id
        assert chat_context.entrypoint == ExecutionEntrypoint.CHAT
        assert calls[1]["context"].entrypoint == ExecutionEntrypoint.WORKFLOW

    run_orm(scenario)


def test_execute_denies_builtin_without_a_resolvable_actor(run_orm):
    async def scenario():
        owner = await _make_user("deny-owner")
        team = await _make_team("deny-team", owner)
        tool = await _make_tool(team, name="get_current_time", type=ToolType.BUILTIN)
        executor = ToolExecutor()

        with pytest.raises(BusinessError) as missing_actor:
            await executor.execute(tool, {}, user_id=str(uuid4()))
        assert missing_actor.value.msg_key == "user_context_required"
        assert missing_actor.value.status_code == 403

        with pytest.raises(BusinessError) as anonymous:
            await executor.execute(tool, {})
        assert anonymous.value.msg_key == "user_context_required"

    run_orm(scenario)


def test_custom_http_oauth_requires_connection_and_replaces_authorization(run_orm):
    async def scenario():
        user = await _make_user("oauth-user")
        team = await _make_team("oauth-team", user)
        tool = await _make_tool(
            team,
            name="oauth-http",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            http_config={
                "url": "https://api.example.test/v1",
                "headers": {
                    "authorization": "Bearer stale",
                    "X-Trace": "trace-1",
                },
                "oauth2": {"authorization_endpoint": "https://auth.example.test"},
            },
        )
        context = ToolCallContext(
            actor=user, team_id=team.id, entrypoint=ExecutionEntrypoint.CHAT
        )
        executor = ToolExecutor()

        with (
            patch(
                "app.services.tool.execute_stored_tool",
                new=AsyncMock(side_effect=_invoke_with(None)),
            ),
            pytest.raises(BusinessError) as missing_connection,
        ):
            await executor.execute(tool, {"q": "x"}, context=context)
        assert missing_connection.value.msg_key == "tool_connection_required"

        resolved = _resolved(team, user, tool)
        custom_executor = AsyncMock(return_value={"ok": True})
        with (
            patch(
                "app.services.tool.execute_stored_tool",
                new=AsyncMock(side_effect=_invoke_with(resolved)),
            ),
            patch.object(executor, "_execute_custom_tool", new=custom_executor),
            patch(
                "app.services.tool_oauth.ToolOAuthService.get_authorization_header",
                new=AsyncMock(return_value="Bearer fresh"),
            ),
        ):
            result = await executor.execute(
                tool, {"q": "x"}, context=context, operation="search"
            )

        assert result == {"ok": True}
        execution_tool = custom_executor.await_args.args[0]
        assert execution_tool.http_config["headers"] == {
            "X-Trace": "trace-1",
            "Authorization": "Bearer fresh",
        }
        # The persisted definition is never mutated by credential injection.
        assert tool.http_config["headers"] == {
            "authorization": "Bearer stale",
            "X-Trace": "trace-1",
        }

        code_tool = await _make_tool(
            team,
            name="code-without-config",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.CODE,
            code_config={},
        )
        with pytest.raises(ValueError):
            await executor._execute_custom_tool(code_tool, {})

    run_orm(scenario)


def test_mcp_execute_derives_context_and_denies_oauth_without_connection(run_orm):
    async def scenario():
        user = await _make_user("mcp-user")
        team = await _make_team("mcp-team", user)
        tool = await _make_tool(
            team,
            name="mcp-oauth",
            type=ToolType.MCP,
            mcp_config={
                "url": "https://mcp.example.test/sse",
                "oauth": {"provider": "github"},
            },
        )
        executor = ToolExecutor()
        captured: dict[str, object] = {}

        async def fake_execute(tool_arg, operation, arguments, ctx_arg, invoke):
            captured["context"] = ctx_arg
            return await invoke(arguments, None)

        with patch(
            "app.services.tool.execute_stored_tool",
            new=AsyncMock(side_effect=fake_execute),
        ):
            with pytest.raises(BusinessError) as exc_info:
                await executor.execute(tool, {"x": 1}, user_id=str(user.id))

        assert exc_info.value.msg_key == "tool_connection_required"
        context = captured["context"]
        assert context.actor.id == user.id
        assert context.team_id == team.id
        assert context.entrypoint == ExecutionEntrypoint.CHAT

    run_orm(scenario)


def test_build_mcp_config_renders_secrets_and_discovers_provider(run_orm):
    async def scenario():
        user = await _make_user("mcp-render-user")
        team = await _make_team("mcp-render-team", user)
        tool = await _make_tool(
            team,
            name="mcp-render",
            type=ToolType.MCP,
            mcp_config={
                "url": "https://mcp.example.test/sse",
                "headers": {
                    "Authorization": "Bearer stale",
                    "X-Api-Key": "{{api_key}}",
                },
                "env": {"LOG_LEVEL": "debug", "SESSION": "{{api_key}}"},
            },
        )
        resolved = _resolved(team, user, tool)

        with (
            patch(
                "app.services.tool_oauth.ToolOAuthService.has_oauth_binding",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.services.tool_oauth.ToolOAuthService.get_authorization_header",
                new=AsyncMock(return_value="Bearer fresh"),
            ),
        ):
            config = await build_mcp_config(tool, resolved)

        assert config["headers"] == {
            "X-Api-Key": "sk-live",
            "Authorization": "Bearer fresh",
        }
        assert config["env"] == {"LOG_LEVEL": "debug", "SESSION": "sk-live"}
        assert tool.mcp_config["headers"]["Authorization"] == "Bearer stale"
        assert tool.mcp_config["env"]["SESSION"] == "{{api_key}}"

        without_connection = await build_mcp_config(tool, None)
        without_connection["headers"]["X-Api-Key"] = "mutated"
        assert tool.mcp_config["headers"]["X-Api-Key"] == "{{api_key}}"

    run_orm(scenario)


def test_builtin_execution_requires_call_context(run_orm):
    async def scenario():
        user = await _make_user("scope-user")
        team = await _make_team("scope-team", user)
        executor = ToolExecutor()

        with patch(
            "app.services.tool.get_builtin_definition",
            new=AsyncMock(return_value=SimpleNamespace()),
        ):
            with pytest.raises(BusinessError) as exc_info:
                await executor.execute_builtin_tool(
                    "generate_image", {}, team_id=team.id
                )
        assert exc_info.value.msg_key == "user_context_required"
        assert exc_info.value.status_code == 403

    run_orm(scenario)
