"""Real-schema behaviour for the custom-database-tool cutover.

Every scenario drives the public migration against real Tool, ToolConnection,
Agent, Workflow and WorkflowVersion rows, and asserts on persisted state:
identity preservation, isolation of unrelated rows, fail-closed rollback and
idempotent re-runs.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from tortoise import Tortoise
from tortoise.context import TortoiseContext

import app.core.database_tool_migration as migration
from app.core.database_tool_migration import (
    DatabaseToolMigrationError,
    migrate_custom_database_tools,
)
from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.agent import Agent
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_connection import ToolConnection
from app.models.user import Team, User
from app.models.workflow import Workflow, WorkflowVersion


@pytest.fixture
def run_orm():
    with asyncio.Runner() as runner:

        def run(scenario):
            async def wrapped():
                async with TortoiseContext() as context:
                    await context.init(
                        db_url="sqlite://:memory:", modules={"models": ["app.models"]}
                    )
                    await context.generate_schemas()
                    return await scenario()

            return runner.run(wrapped())

        yield run


async def _team_with_owner() -> tuple[User, Team]:
    owner = await User.create(
        username="owner", email="owner@test.invalid", hashed_password="x"
    )
    team = await Team.create(name="Database migration edges", owner=owner)
    return owner, team


async def _legacy_tool(team: Team, name: str, config: dict, **kwargs) -> Tool:
    tool = await Tool.create(
        team=team,
        name=name,
        display_name=name,
        description="legacy database tool",
        type="custom",
        database_config=config,
        **kwargs,
    )
    await Tortoise.get_connection("default").execute_query(
        "UPDATE tools SET custom_type='database' WHERE id=?", [str(tool.id)]
    )
    return tool


def test_name_collision_with_a_custom_tool_aborts_the_cutover(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        await Tool.create(
            team=team,
            name="postgresql_query",
            display_name="Occupied",
            description="",
            type="custom",
            custom_type=CustomToolType.HTTP,
        )
        await _legacy_tool(
            team, "orders", {"db_type": "postgresql", "host": "db.example.test"}
        )

        with pytest.raises(DatabaseToolMigrationError, match="rename it"):
            await migrate_custom_database_tools()

        assert await ToolConnection.all().count() == 0
        assert (
            await Tool.filter(name="postgresql_query", type=ToolType.BUILTIN).count()
            == 0
        )

    run_orm(scenario)


def test_unreadable_connection_config_fails_closed(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team, "unreadable", {"db_type": "postgresql", "host": "db.example.test"}
        )
        await ToolConnection.create(
            team=team,
            tool=legacy,
            scope="team",
            name="broken",
            encrypted_config="not-a-fernet-token",
        )

        with pytest.raises(DatabaseToolMigrationError, match="unreadable"):
            await migrate_custom_database_tools()

        assert await Tool.filter(name="postgresql_query").count() == 0
        assert await ToolConnection.filter(builtin_tool_key__isnull=False).count() == 0

    run_orm(scenario)


def test_non_mapping_connection_config_is_rejected(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team, "list", {"db_type": "postgresql", "host": "db.example.test"}
        )
        await ToolConnection.create(
            team=team,
            tool=legacy,
            scope="team",
            name="list",
            encrypted_config=encrypt_tool_secret("[]"),
        )

        with pytest.raises(DatabaseToolMigrationError, match="not a mapping"):
            await migrate_custom_database_tools()

        assert await ToolConnection.filter(builtin_tool_key__isnull=False).count() == 0

    run_orm(scenario)


def test_connection_with_empty_ciphertext_uses_the_definition_credentials(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team,
            "orders",
            {"db_type": "postgresql", "host": "db.example.test"},
            credentials={"password": "definition-password"},
        )
        connection = await ToolConnection.create(
            team=team,
            tool=legacy,
            scope="team",
            name="orders",
            encrypted_config="",
        )

        result = await migrate_custom_database_tools()

        assert result["connections_migrated"] == 1
        migrated = await ToolConnection.get(id=connection.id)
        assert migrated.builtin_tool_key == "postgresql_query"
        assert migrated.secret_fields == ["host", "password"]
        assert json.loads(decrypt_tool_secret(migrated.encrypted_config)) == {
            "host": "db.example.test",
            "password": "definition-password",
        }

    run_orm(scenario)


def test_bound_connection_without_host_or_url_is_rejected(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team, "incomplete", {"db_type": "postgresql", "database": "app"}
        )
        await ToolConnection.create(
            team=team, tool=legacy, scope="team", name="incomplete"
        )

        with pytest.raises(DatabaseToolMigrationError, match="no host or URL"):
            await migrate_custom_database_tools()

        assert await Tool.filter(name="postgresql_query").count() == 0

    run_orm(scenario)


def test_new_connection_without_host_or_url_is_rejected(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        await _legacy_tool(
            team, "incomplete", {"db_type": "postgresql", "database": "app"}
        )

        with pytest.raises(
            DatabaseToolMigrationError, match="no host or URL to preserve"
        ):
            await migrate_custom_database_tools()

        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_unsupported_engine_is_reported_before_any_row_changes(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        await _legacy_tool(team, "oracle", {"db_type": "oracle", "host": "ora"})

        with pytest.raises(DatabaseToolMigrationError, match="unsupported db_type"):
            await migrate_custom_database_tools()

        assert await ToolConnection.all().count() == 0
        assert await Tool.filter(name="postgresql_query").count() == 0

    run_orm(scenario)


def test_legacy_row_already_named_after_the_builtin_is_converted_in_place(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team,
            "postgresql_query",
            {
                "db_type": "postgres",
                "host": "db.example.test",
                "port": 5432,
            },
            approval_policy={"default_decision": "deny"},
            credentials={"password": "plain"},
        )
        original_id = legacy.id

        result = await migrate_custom_database_tools()

        assert result["tools"] == 1
        assert result["retired"] == 0
        converted = await Tool.get(id=original_id)
        assert converted.type == "builtin"
        assert converted.custom_type is None
        assert converted.display_name == "postgresql_query"
        assert converted.identity_policy == "selectable"
        assert converted.definition_version == 2
        assert converted.database_config == {}
        assert converted.credentials == {}
        assert converted.approval_policy["default_decision"] == "deny"
        assert {field["name"] for field in converted.connection_fields} >= {
            "host",
            "port",
        }
        connection = await ToolConnection.get(
            tool_id=None, builtin_tool_key="postgresql_query"
        )
        assert json.loads(decrypt_tool_secret(connection.encrypted_config)) == {
            "host": "db.example.test",
            "port": "5432",
            "password": "plain",
        }

    run_orm(scenario)


def test_interrupted_rows_are_recovered_and_unrelated_custom_tools_are_ignored(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        interrupted = await Tool.create(
            team=team,
            name="interrupted",
            display_name="Interrupted",
            description="",
            type="custom",
            custom_type=None,
            database_config={"db_type": "mysql", "host": "mysql.example.test"},
        )
        unrelated = await Tool.create(
            team=team,
            name="plain-http",
            display_name="Plain HTTP",
            description="",
            type="custom",
            custom_type=CustomToolType.HTTP,
            database_config={},
        )

        result = await migrate_custom_database_tools()

        assert result["tools"] == 1
        retired = await Tool.get(id=interrupted.id)
        assert retired.type == "builtin"
        assert retired.is_enabled is False
        assert await ToolConnection.filter(builtin_tool_key="mysql_query").count() == 1
        untouched = await Tool.get(id=unrelated.id)
        assert untouched.type == "custom"
        assert untouched.custom_type == "http"
        assert untouched.name == "plain-http"

        again = await migrate_custom_database_tools()
        assert again["tools"] == 0
        assert await ToolConnection.filter(builtin_tool_key="mysql_query").count() == 1

    run_orm(scenario)


def test_ambiguous_multi_connection_reference_stays_unbound_and_is_logged(
    run_orm, caplog
):
    async def scenario():
        _, team = await _team_with_owner()
        legacy = await _legacy_tool(
            team, "orders", {"db_type": "postgresql", "host": "db.example.test"}
        )
        for name in ("primary", "replica"):
            await ToolConnection.create(team=team, tool=legacy, scope="team", name=name)
        agent = await Agent.create(
            team=team,
            name="Ambiguous agent",
            tools_config=[
                {"type": "custom", "tool_id": str(legacy.id), "name": "orders"}
            ],
        )

        caplog.set_level(logging.WARNING, logger=migration.__name__)
        result = await migrate_custom_database_tools()

        assert result["agents"] == 1
        await agent.refresh_from_db()
        entry = agent.tools_config[0]
        assert entry["type"] == "builtin"
        assert entry["name"] == "postgresql_query"
        assert "connection_id" not in entry
        assert "connection_mode" not in entry
        assert "unbound" in caplog.text
        assert "Ambiguous agent" in caplog.text

    run_orm(scenario)


def test_unrelated_agents_workflows_and_snapshots_are_not_rewritten(run_orm):
    async def scenario():
        _, team = await _team_with_owner()
        await _legacy_tool(
            team, "orders", {"db_type": "postgresql", "host": "db.example.test"}
        )
        agent = await Agent.create(
            team=team,
            name="Unrelated agent",
            tools_config=[{"type": "builtin", "name": "get_current_time"}],
        )
        workflow = await Workflow.create(
            team=team,
            name="Unrelated flow",
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
        version = await WorkflowVersion.create(
            workflow=workflow, version=1, definition=workflow.definition
        )

        result = await migrate_custom_database_tools()

        assert result["agents"] == 0
        assert result["workflows"] == 0
        assert result["versions"] == 0
        await agent.refresh_from_db()
        assert agent.tools_config == [{"type": "builtin", "name": "get_current_time"}]
        saved_workflow = await Workflow.get(id=workflow.id)
        assert saved_workflow.definition == workflow.definition
        saved_version = await WorkflowVersion.get(id=version.id)
        assert saved_version.definition == version.definition

    run_orm(scenario)
