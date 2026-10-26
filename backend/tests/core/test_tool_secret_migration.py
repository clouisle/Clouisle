"""Legacy plaintext credential cutover against a real SQLite ORM schema."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.tool_secret_migration import (
    LegacySecretMigrationError,
    migrate_global_tool_config,
    migrate_legacy_tool_secrets,
)
from app.core.tool_secrets import decrypt_tool_secret
from app.models.agent import Agent
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_config import ToolConfig
from app.models.tool_connection import ToolConnection, ToolConnectionScope
from app.models.user import Team, User
from app.models.workflow import Workflow, WorkflowVersion


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'tool-secrets.sqlite3'}"

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
    owner = await User.create(
        id=uuid4(),
        username="owner",
        email="owner@example.com",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name="cutover-team", owner_id=owner.id)
    return owner, team


async def _http_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name="http-service",
        display_name="HTTP service",
        description="",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.HTTP,
        credentials={"api_key": "http-secret", "region": "us"},
        http_config={
            "method": "GET",
            "url": "https://example.com",
            "headers": {
                "Authorization": "Bearer raw-token",
                "X-Trace": "trace-1",
            },
        },
    )


async def _mcp_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name="mcp-service",
        display_name="MCP service",
        description="",
        type=ToolType.MCP,
        mcp_config={
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "server"],
            "env": {"TAVILY_API_KEY": "tvly-secret", "NODE_ENV": "production"},
        },
    )


async def _database_tool(team: Team) -> Tool:
    return await Tool.create(
        id=uuid4(),
        team_id=team.id,
        name="db-service",
        display_name="DB service",
        description="",
        type=ToolType.CUSTOM,
        custom_type=CustomToolType.DATABASE,
        database_config={
            "db_type": "postgresql",
            "host": "db.internal",
            "password": "db-password",
            "url": "postgres://user:pw@db.internal/app",
        },
    )


def test_migrates_tool_secrets_into_encrypted_connections(run_orm):
    async def scenario():
        _owner, team = await _fixtures()
        http_tool = await _http_tool(team)
        mcp_tool = await _mcp_tool(team)
        db_tool = await _database_tool(team)
        team_config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=team.id,
            credentials={"SERPER_API_KEY": "serper-secret"},
        )
        # Global non-web_search rows fail closed (team must be explicit); this
        # happy-path test only covers team-scoped and site-owned web rows.
        # Site web search stays on dedicated site settings; no connection is
        # fabricated and the row is never read by the builtin path.
        web_team_config = await ToolConfig.create(
            id=uuid4(),
            tool_name="web_search",
            team_id=team.id,
            credentials={"SERPER_API_KEY": "unused"},
        )
        web_site_config = await ToolConfig.create(
            id=uuid4(),
            tool_name="web_search",
            team_id=None,
            credentials={"TAVILY_API_KEY": "unused-global"},
        )
        explicit_connection = uuid4()
        agent = await Agent.create(
            id=uuid4(),
            team_id=team.id,
            name="Bound agent",
            description="",
            tools_config=[
                {"type": "builtin", "name": "get_current_time"},
                {"type": "mcp", "server_id": str(http_tool.id)},
                {
                    "type": "custom",
                    "tool_id": str(mcp_tool.id),
                    "connection_mode": "personal",
                    "connection_id": str(explicit_connection),
                },
            ],
        )
        workflow = await Workflow.create(
            id=uuid4(),
            team_id=team.id,
            name="Bound workflow",
            definition={
                "nodes": [
                    {
                        "id": "n1",
                        "data": {
                            "toolConfig": {
                                "toolType": "builtin",
                                "toolName": "get_current_time",
                            }
                        },
                    },
                    {
                        "id": "n2",
                        "data": {
                            "toolConfig": {
                                "toolType": "custom",
                                "toolId": str(db_tool.id),
                            }
                        },
                    },
                ],
                "edges": [],
            },
        )
        historical = await WorkflowVersion.create(
            id=uuid4(),
            workflow_id=workflow.id,
            version=1,
            definition={
                "nodes": [
                    {
                        "id": "n1",
                        "data": {
                            "toolConfig": {
                                "toolType": "builtin",
                                "toolName": "get_current_time",
                            }
                        },
                    }
                ]
            },
        )

        mapping = await migrate_legacy_tool_secrets()
        assert f"tool:{http_tool.id}" in mapping
        assert f"tool:{mcp_tool.id}" in mapping
        assert f"tool:{db_tool.id}" in mapping
        assert f"builtin:get_current_time:{team.id}" in mapping
        assert not any("web_search" in key for key in mapping)

        http_connection = await ToolConnection.get(id=mapping[f"tool:{http_tool.id}"])
        assert http_connection.scope == ToolConnectionScope.TEAM
        assert http_connection.team_id == team.id
        assert http_connection.owner_user_id is None
        assert http_connection.is_default is False
        assert http_connection.secret_fields == [
            "api_key",
            "http_header_authorization",
            "region",
        ]
        http_secrets = json.loads(decrypt_tool_secret(http_connection.encrypted_config))
        assert http_secrets == {
            "api_key": "http-secret",
            "http_header_authorization": "Bearer raw-token",
            "region": "us",
        }
        assert "http-secret" not in http_connection.encrypted_config
        assert "Bearer raw-token" not in http_connection.encrypted_config

        http_tool = await Tool.get(id=http_tool.id)
        assert http_tool.credentials == {}
        assert (
            http_tool.http_config["headers"]["Authorization"]
            == "{{http_header_authorization}}"
        )
        assert http_tool.http_config["headers"]["X-Trace"] == "trace-1"
        assert http_tool.identity_policy == "team_only"
        field_names = {field["name"] for field in http_tool.connection_fields}
        assert field_names == {"api_key", "http_header_authorization", "region"}

        mcp_tool = await Tool.get(id=mcp_tool.id)
        assert mcp_tool.mcp_config["env"] == {
            "TAVILY_API_KEY": "{{TAVILY_API_KEY}}",
            "NODE_ENV": "{{NODE_ENV}}",
        }
        assert mcp_tool.mcp_config["command"] == "npx"
        mcp_connection = await ToolConnection.get(id=mapping[f"tool:{mcp_tool.id}"])
        assert json.loads(decrypt_tool_secret(mcp_connection.encrypted_config)) == {
            "NODE_ENV": "production",
            "TAVILY_API_KEY": "tvly-secret",
        }

        db_tool = await Tool.get(id=db_tool.id)
        assert db_tool.database_config["password"] == "{{password}}"
        assert db_tool.database_config["url"] == "{{url}}"
        assert db_tool.database_config["host"] == "db.internal"
        db_connection = await ToolConnection.get(id=mapping[f"tool:{db_tool.id}"])
        assert json.loads(decrypt_tool_secret(db_connection.encrypted_config)) == {
            "password": "db-password",
            "url": "postgres://user:pw@db.internal/app",
        }

        team_connection_id = mapping[f"builtin:get_current_time:{team.id}"]
        team_connection = await ToolConnection.get(id=team_connection_id)
        definition = await Tool.get(id=team_connection.tool_id)
        assert definition.type == ToolType.BUILTIN
        assert definition.name == "get_current_time"
        assert definition.identity_policy == "team_only"
        assert {field["name"] for field in definition.connection_fields} == {
            "SERPER_API_KEY"
        }
        assert definition.approval_policy["default_decision"] == "allow"
        assert team_connection.builtin_tool_key is None
        assert team_connection.scope == ToolConnectionScope.TEAM
        assert mapping[f"tool:{definition.id}"] == str(team_connection.id)
        assert json.loads(decrypt_tool_secret(team_connection.encrypted_config)) == {
            "SERPER_API_KEY": "serper-secret"
        }
        # The migrated non-web_search row is deleted with its connection;
        # site web search rows remain the dedicated site configuration store.
        assert not await ToolConfig.filter(id=team_config.id).exists()
        assert await ToolConfig.filter(id=web_team_config.id).exists()
        assert await ToolConfig.filter(id=web_site_config.id).exists()
        assert not await ToolConnection.filter(builtin_tool_key="web_search").exists()

        agent = await Agent.get(id=agent.id)
        entries = agent.tools_config
        assert entries[0]["connection_mode"] == "team"
        assert entries[0]["connection_id"] == team_connection_id
        assert entries[1]["connection_mode"] == "team"
        assert entries[1]["connection_id"] == mapping[f"tool:{http_tool.id}"]
        assert entries[2]["connection_mode"] == "personal"
        assert entries[2]["connection_id"] == str(explicit_connection)

        workflow = await Workflow.get(id=workflow.id)
        nodes = workflow.definition["nodes"]
        assert nodes[0]["data"]["toolConfig"]["connectionMode"] == "team"
        assert nodes[0]["data"]["toolConfig"]["connectionId"] == team_connection_id
        assert nodes[1]["data"]["toolConfig"]["connectionMode"] == "team"
        assert (
            nodes[1]["data"]["toolConfig"]["connectionId"]
            == mapping[f"tool:{db_tool.id}"]
        )

        # Historical version snapshots are immutable.
        historical = await WorkflowVersion.get(id=historical.id)
        assert (
            "connectionId"
            not in historical.definition["nodes"][0]["data"]["toolConfig"]
        )

        # Idempotency: no duplicate connections, no version churn.
        versions = {
            str(item.id): item.secret_version for item in await ToolConnection.all()
        }
        counts = await ToolConnection.all().count()
        await migrate_legacy_tool_secrets()
        assert await ToolConnection.all().count() == counts
        assert {
            str(item.id): item.secret_version for item in await ToolConnection.all()
        } == versions

    run_orm(scenario)


def test_global_config_fails_closed_then_migrates_to_explicit_team(run_orm):
    async def scenario():
        _owner, team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=None,
            credentials={"SERPER_API_KEY": "global-secret"},
        )

        with pytest.raises(LegacySecretMigrationError) as exc:
            await migrate_legacy_tool_secrets()

        # No silent narrowing and no fabricated site connection.
        assert str(config.id) in str(exc.value)
        assert await ToolConfig.filter(id=config.id).exists()
        assert await ToolConnection.all().count() == 0

        connection_id = await migrate_global_tool_config("get_current_time", team.id)
        assert connection_id
        assert not await ToolConfig.filter(id=config.id).exists()
        connection = await ToolConnection.get(id=connection_id)
        assert connection.team_id == team.id
        assert connection.scope == ToolConnectionScope.TEAM
        assert json.loads(decrypt_tool_secret(connection.encrypted_config)) == {
            "SERPER_API_KEY": "global-secret"
        }

        with pytest.raises(LegacySecretMigrationError):
            await migrate_global_tool_config("get_current_time", team.id)
        with pytest.raises(LegacySecretMigrationError):
            await migrate_global_tool_config("web_search", team.id)

    run_orm(scenario)


def test_empty_global_config_is_deleted_without_failing(run_orm):
    async def scenario():
        _owner, _team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=None,
            credentials={},
        )

        mapping = await migrate_legacy_tool_secrets()

        assert mapping == {}
        assert not await ToolConfig.filter(id=config.id).exists()
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_global_non_web_config_requires_explicit_team(run_orm):
    async def scenario():
        _owner, _team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=None,
            credentials={"SERPER_API_KEY": "global-secret"},
        )

        with pytest.raises(LegacySecretMigrationError) as exc:
            await migrate_legacy_tool_secrets()

        assert "--target-team" in str(exc.value)
        assert await ToolConfig.filter(id=config.id).exists()
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_non_string_secret_fails_without_mutation(run_orm):
    async def scenario():
        _owner, team = await _fixtures()
        tool = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name="broken",
            display_name="Broken",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            credentials={"api_key": 123},
        )

        with pytest.raises(LegacySecretMigrationError):
            await migrate_legacy_tool_secrets()

        assert await ToolConnection.all().count() == 0
        tool = await Tool.get(id=tool.id)
        assert tool.credentials == {"api_key": 123}
        assert tool.identity_policy == "none"

    run_orm(scenario)


def test_non_string_sensitive_header_fails_closed(run_orm):
    async def scenario():
        _owner, team = await _fixtures()
        tool = await Tool.create(
            id=uuid4(),
            team_id=team.id,
            name="broken-header",
            display_name="Broken header",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            http_config={"headers": {"Authorization": 42}},
        )

        with pytest.raises(LegacySecretMigrationError):
            await migrate_legacy_tool_secrets()

        tool = await Tool.get(id=tool.id)
        assert tool.http_config["headers"]["Authorization"] == 42
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)
