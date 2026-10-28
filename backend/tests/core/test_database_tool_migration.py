"""Database builtin cutover against real ORM rows, without external services."""

import asyncio
import json

import pytest
from tortoise import Tortoise
from tortoise.context import TortoiseContext

from app.core.database_tool_migration import (
    DatabaseToolMigrationError,
    migrate_custom_database_tools,
)
from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.agent import Agent
from app.models.tool import Tool
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
                    await scenario()

            runner.run(wrapped())

        yield run


async def fixtures():
    owner = await User.create(
        username="owner", email="owner@test.invalid", hashed_password="x"
    )
    team = await Team.create(name="Database migration", owner=owner)
    return owner, team


async def legacy_tool(team, name, config, **kwargs):
    tool = await Tool.create(
        team=team,
        name=name,
        display_name=name,
        description="private metadata",
        type="custom",
        database_config=config,
        **kwargs,
    )
    await Tortoise.get_connection("default").execute_query(
        "UPDATE tools SET custom_type='database' WHERE id=?", [str(tool.id)]
    )
    return tool


def test_cutover_preserves_connection_identity_and_versioned_references(run_orm):
    async def scenario():
        owner, team = await fixtures()
        legacy = await legacy_tool(
            team,
            "orders",
            {
                "db_type": "postgresql",
                "host": "db.example.test",
                "database": "orders",
                "password": "{{password}}",
            },
            approval_policy={"default_decision": "deny"},
            visibility="private",
        )
        connection = await ToolConnection.create(
            team=team,
            tool=legacy,
            scope="user",
            owner_user=owner,
            name="Personal orders",
            encrypted_config=encrypt_tool_secret(
                json.dumps({"password": "personal-password"})
            ),
        )
        agent = await Agent.create(
            team=team,
            name="Orders",
            tools_config=[
                {
                    "type": "custom",
                    "name": "orders",
                    "tool_id": str(legacy.id),
                    "connection_mode": "personal",
                    "connection_id": str(connection.id),
                }
            ],
        )
        definition = {
            "nodes": [
                {
                    "id": "db",
                    "type": "tool",
                    "data": {
                        "toolConfig": {"toolType": "custom", "toolId": str(legacy.id)}
                    },
                }
            ],
            "edges": [],
        }
        workflow = await Workflow.create(
            team=team, name="Orders flow", definition=definition
        )
        version = await WorkflowVersion.create(
            workflow=workflow, version=1, definition=definition
        )

        result = await migrate_custom_database_tools()
        assert result["tools"] == 1
        migrated = await ToolConnection.get(id=connection.id)
        assert migrated.owner_user_id == owner.id
        assert migrated.scope == "user"
        assert migrated.tool_id is None
        assert migrated.builtin_tool_key == "postgresql_query"
        assert json.loads(decrypt_tool_secret(migrated.encrypted_config)) == {
            "host": "db.example.test",
            "database": "orders",
            "password": "personal-password",
        }
        retired = await Tool.get(id=legacy.id)
        assert retired.is_enabled is False
        assert retired.visibility == "private"
        assert retired.database_config == {}
        canonical = await Tool.get(team=team, name="postgresql_query")
        assert canonical.approval_policy["default_decision"] == "deny"
        assert canonical.identity_policy == "selectable"
        await agent.refresh_from_db()
        assert agent.tools_config[0]["type"] == "builtin"
        assert agent.tools_config[0]["name"] == "postgresql_query"
        assert agent.tools_config[0]["connection_id"] == str(connection.id)
        for model, item in ((Workflow, workflow), (WorkflowVersion, version)):
            saved = await model.get(id=item.id)
            config = saved.definition["nodes"][0]["data"]["toolConfig"]
            assert config["toolName"] == "postgresql_query"
            assert config["connectionId"] == str(connection.id)
            assert "toolId" not in config
        again = await migrate_custom_database_tools()
        assert again["tools"] == 0
        assert (
            await ToolConnection.filter(builtin_tool_key="postgresql_query").count()
            == 1
        )

    run_orm(scenario)


def test_failed_cutover_rolls_back_all_rows_and_plaintext_credentials(run_orm):
    async def scenario():
        _, team = await fixtures()
        valid = await legacy_tool(
            team,
            "valid",
            {"db_type": "mysql", "host": "db.example.test", "password": "{{token}}"},
            credentials={"token": "old-password"},
        )
        invalid = await legacy_tool(team, "invalid", {})
        with pytest.raises(DatabaseToolMigrationError):
            await migrate_custom_database_tools()
        assert await ToolConnection.all().count() == 0
        assert await Tool.filter(name="mysql_query").count() == 0
        _, rows = await Tortoise.get_connection("default").execute_query(
            "SELECT custom_type FROM tools WHERE id IN (?,?)",
            [str(valid.id), str(invalid.id)],
        )
        assert [row["custom_type"] for row in rows] == ["database", "database"]

    run_orm(scenario)


def test_existing_canonical_deny_cannot_be_relaxed_by_legacy_allow_override(run_orm):
    async def scenario():
        _, team = await fixtures()
        await Tool.create(
            team=team,
            name="redis_query",
            display_name="Redis",
            description="",
            type="builtin",
            is_enabled=False,
            approval_policy={"default_decision": "deny"},
        )
        await legacy_tool(
            team,
            "cache",
            {"db_type": "redis", "host": "cache.example.test"},
            approval_policy={
                "default_decision": "allow",
                "operation_overrides": {"cache": {"default_decision": "allow"}},
            },
        )
        await migrate_custom_database_tools()
        canonical = await Tool.get(team=team, name="redis_query")
        assert canonical.is_enabled is False
        assert canonical.approval_policy["default_decision"] == "deny"
        assert not canonical.approval_policy.get("operation_overrides")

    run_orm(scenario)


def test_two_explicit_defaults_are_not_silently_merged(run_orm):
    async def scenario():
        _, team = await fixtures()
        first = await legacy_tool(
            team, "first", {"db_type": "postgresql", "host": "first.example.test"}
        )
        second = await legacy_tool(
            team, "second", {"db_type": "postgresql", "host": "second.example.test"}
        )
        for tool in (first, second):
            await ToolConnection.create(
                team=team,
                tool=tool,
                scope="team",
                name=tool.name,
                is_default=True,
                default_slot=f"legacy:{tool.id}",
                encrypted_config=encrypt_tool_secret("{}"),
            )
        with pytest.raises(DatabaseToolMigrationError, match="default"):
            await migrate_custom_database_tools()
        connections = await ToolConnection.all()
        assert {item.tool_id for item in connections} == {first.id, second.id}
        assert all(item.is_default for item in connections)
        assert all(item.builtin_tool_key is None for item in connections)

    run_orm(scenario)


def test_two_database_aliases_in_one_agent_fail_without_losing_bindings(run_orm):
    async def scenario():
        _, team = await fixtures()
        first = await legacy_tool(
            team, "first", {"db_type": "mysql", "host": "first.example.test"}
        )
        second = await legacy_tool(
            team, "second", {"db_type": "mysql", "host": "second.example.test"}
        )
        original = [
            {"type": "custom", "tool_id": str(tool.id), "name": tool.name}
            for tool in (first, second)
        ]
        agent = await Agent.create(
            team=team, name="Two databases", tools_config=original
        )
        with pytest.raises(DatabaseToolMigrationError, match="more than one"):
            await migrate_custom_database_tools()
        await agent.refresh_from_db()
        assert agent.tools_config == original
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_workflow_migration_keeps_explicit_snake_case_identity():
    from types import SimpleNamespace
    from app.core.database_tool_migration import rewrite_workflow_definition

    definition = {
        "nodes": [
            {
                "data": {
                    "config": {
                        "toolType": "custom",
                        "tool_id": "old-tool",
                        "connection_id": "chosen-account",
                        "connection_mode": "personal",
                    }
                }
            }
        ]
    }
    migrated, changed = rewrite_workflow_definition(
        definition,
        "old-tool",
        "postgresql_query",
        SimpleNamespace(id="different-default", scope="team"),
    )
    assert changed
    config = migrated["nodes"][0]["data"]["config"]
    assert config == {
        "toolType": "builtin",
        "toolName": "postgresql_query",
        "connectionId": "chosen-account",
        "connectionMode": "personal",
    }
