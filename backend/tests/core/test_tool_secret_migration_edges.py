"""Real-schema behaviour for the legacy plaintext credential cutover.

Scenarios drive the public migration (and its operator CLI) against real Tool,
ToolConfig and ToolConnection rows and assert on persisted state: encrypted
secrets, in-place updates, deletion only after commit, fail-closed aborts and
idempotent re-runs.
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core.config import settings
from app.core.tool_secret_migration import (
    LegacySecretMigrationError,
    main,
    migrate_global_tool_config,
    migrate_legacy_tool_secrets,
)
from app.core.tool_secrets import decrypt_tool_secret, encrypt_tool_secret
from app.models.tool import CustomToolType, Tool, ToolType
from app.models.tool_config import ToolConfig
from app.models.tool_connection import ToolConnection
from app.models.user import Team, User


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


async def _fixtures() -> tuple[User, Team]:
    owner = await User.create(
        username="owner", email="owner@test.invalid", hashed_password="x"
    )
    team = await Team.create(name="Secret migration edges", owner=owner)
    return owner, team


def test_mcp_headers_are_encrypted_while_templates_and_plain_headers_survive(run_orm):
    async def scenario():
        _, team = await _fixtures()
        tool = await Tool.create(
            team=team,
            name="mcp-service",
            display_name="MCP service",
            description="",
            type=ToolType.MCP,
            mcp_config={
                "transport": "stdio",
                "env": {"123": "digit-secret", "TEMPLATED": "{{already}}"},
                "headers": {
                    "Authorization": "Bearer raw-token",
                    "X-Trace": "trace-1",
                    "Cookie": "{{cookie}}",
                },
            },
        )

        mapping = await migrate_legacy_tool_secrets()

        connection = await ToolConnection.get(id=mapping[f"tool:{tool.id}"])
        assert json.loads(decrypt_tool_secret(connection.encrypted_config)) == {
            "mcp_header_authorization": "Bearer raw-token",
            "value_123": "digit-secret",
        }
        saved = await Tool.get(id=tool.id)
        assert saved.mcp_config["headers"] == {
            "Authorization": "{{mcp_header_authorization}}",
            "X-Trace": "trace-1",
            "Cookie": "{{cookie}}",
        }
        assert saved.mcp_config["env"] == {
            "123": "{{value_123}}",
            "TEMPLATED": "{{already}}",
        }

    run_orm(scenario)


def test_conflicting_env_and_credential_values_fail_before_writing(run_orm):
    async def scenario():
        _, team = await _fixtures()
        tool = await Tool.create(
            team=team,
            name="conflict",
            display_name="Conflict",
            description="",
            type=ToolType.MCP,
            credentials={"api_key": "from-credentials"},
            mcp_config={"env": {"api_key": "from-env"}},
        )

        with pytest.raises(LegacySecretMigrationError, match="conflicting values"):
            await migrate_legacy_tool_secrets()

        assert await ToolConnection.all().count() == 0
        saved = await Tool.get(id=tool.id)
        assert saved.credentials == {"api_key": "from-credentials"}
        assert saved.mcp_config["env"] == {"api_key": "from-env"}

    run_orm(scenario)


def test_invalid_credential_field_names_fail_closed(run_orm):
    async def scenario():
        _, team = await _fixtures()
        await Tool.create(
            team=team,
            name="bad-name",
            display_name="Bad name",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            credentials={"bad-name": "secret"},
        )

        with pytest.raises(LegacySecretMigrationError, match="not a valid credential"):
            await migrate_legacy_tool_secrets()

        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_existing_tool_connection_is_updated_in_place(run_orm):
    async def scenario():
        _, team = await _fixtures()
        tool = await Tool.create(
            team=team,
            name="http-service",
            display_name="HTTP service",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            credentials={"api_key": "new-secret"},
        )
        stale = await ToolConnection.create(
            team=team,
            tool=tool,
            scope="team",
            name="Migrated http-service",
            encrypted_config=encrypt_tool_secret(json.dumps({"api_key": "old-secret"})),
            secret_fields=["api_key"],
            secret_version=3,
        )

        mapping = await migrate_legacy_tool_secrets()

        updated = await ToolConnection.get(id=stale.id)
        assert mapping[f"tool:{tool.id}"] == str(stale.id)
        assert updated.secret_version == 4
        assert updated.tool_id == tool.id
        assert updated.builtin_tool_key is None
        assert json.loads(decrypt_tool_secret(updated.encrypted_config)) == {
            "api_key": "new-secret"
        }

        # A second pass finds the re-keyed connection and must not bump it.
        again = await migrate_legacy_tool_secrets()
        assert again[f"tool:{tool.id}"] == str(stale.id)
        unchanged = await ToolConnection.get(id=stale.id)
        assert unchanged.secret_version == 4
        assert await ToolConnection.all().count() == 1

    run_orm(scenario)


def test_existing_definition_connection_is_rekeyed_and_reencrypted(run_orm):
    async def scenario():
        _, team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=team.id,
            credentials={"SERPER_API_KEY": "new-value"},
        )
        stale = await ToolConnection.create(
            team=team,
            tool_id=None,
            builtin_tool_key="get_current_time",
            scope="team",
            name="Migrated get_current_time",
            encrypted_config=encrypt_tool_secret(
                json.dumps({"SERPER_API_KEY": "old-value"})
            ),
            secret_fields=["SERPER_API_KEY"],
            secret_version=7,
        )

        mapping = await migrate_legacy_tool_secrets()

        updated = await ToolConnection.get(id=stale.id)
        assert mapping[f"builtin:get_current_time:{team.id}"] == str(stale.id)
        assert updated.secret_version == 8
        assert updated.builtin_tool_key is None
        assert updated.tool_id is not None
        assert json.loads(decrypt_tool_secret(updated.encrypted_config)) == {
            "SERPER_API_KEY": "new-value"
        }
        assert not await ToolConfig.filter(id=config.id).exists()

    run_orm(scenario)


def test_unreadable_existing_connection_aborts_before_plaintext_is_touched(run_orm):
    async def scenario():
        _, team = await _fixtures()
        tool = await Tool.create(
            team=team,
            name="http-service",
            display_name="HTTP service",
            description="",
            type=ToolType.CUSTOM,
            custom_type=CustomToolType.HTTP,
            credentials={"api_key": "plaintext"},
        )
        await ToolConnection.create(
            team=team,
            tool=tool,
            scope="team",
            name="Migrated http-service",
            encrypted_config="destroyed-ciphertext",
        )

        with pytest.raises(LegacySecretMigrationError, match="unreadable"):
            await migrate_legacy_tool_secrets()

        saved = await Tool.get(id=tool.id)
        assert saved.credentials == {"api_key": "plaintext"}

    run_orm(scenario)


def test_unknown_builtin_keeps_an_encrypted_connection_without_a_definition(run_orm):
    async def scenario():
        _, team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="retired_widget",
            team_id=team.id,
            credentials={"WIDGET_KEY": "secret"},
        )

        mapping = await migrate_legacy_tool_secrets()

        connection_id = mapping[f"builtin:retired_widget:{team.id}"]
        connection = await ToolConnection.get(id=connection_id)
        assert connection.tool_id is None
        assert connection.builtin_tool_key == "retired_widget"
        assert connection.scope == "team"
        assert json.loads(decrypt_tool_secret(connection.encrypted_config)) == {
            "WIDGET_KEY": "secret"
        }
        assert not await ToolConfig.filter(id=config.id).exists()
        assert await Tool.filter(name="retired_widget").count() == 0

    run_orm(scenario)


def test_non_string_tool_config_secret_fails_without_deleting_the_row(run_orm):
    async def scenario():
        _, team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=team.id,
            credentials={"SERPER_API_KEY": 42},
        )

        with pytest.raises(LegacySecretMigrationError, match="not a string"):
            await migrate_legacy_tool_secrets()

        assert await ToolConfig.filter(id=config.id).exists()
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_global_config_with_only_empty_values_is_deleted(run_orm):
    async def scenario():
        _, team = await _fixtures()
        config = await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=None,
            credentials={"SERPER_API_KEY": ""},
        )

        result = await migrate_global_tool_config("get_current_time", team.id)

        assert result is None
        assert not await ToolConfig.filter(id=config.id).exists()
        assert await ToolConnection.all().count() == 0

    run_orm(scenario)


def test_global_config_requires_an_existing_target_team(run_orm):
    async def scenario():
        _, _team = await _fixtures()
        await ToolConfig.create(
            id=uuid4(),
            tool_name="get_current_time",
            team_id=None,
            credentials={"SERPER_API_KEY": "secret"},
        )

        with pytest.raises(LegacySecretMigrationError, match="does not exist"):
            await migrate_global_tool_config("get_current_time", uuid4())

        assert await ToolConfig.filter(tool_name="get_current_time").count() == 1

    run_orm(scenario)


def test_cli_reports_success_and_failure_as_json(tmp_path, monkeypatch, capsys):
    database_url = f"sqlite://{tmp_path / 'cli.sqlite3'}"

    async def prepare() -> str:
        async with TortoiseContext() as context:
            await context.init(db_url=database_url, modules={"models": ["app.models"]})
            await context.generate_schemas()
            owner = await User.create(
                username="cli-owner", email="cli@test.invalid", hashed_password="x"
            )
            team = await Team.create(name="CLI team", owner=owner)
            await ToolConfig.create(
                id=uuid4(),
                tool_name="get_current_time",
                team_id=None,
                credentials={"SERPER_API_KEY": "cli-secret"},
            )
            return str(team.id)

    team_id = asyncio.run(prepare())
    monkeypatch.setattr(settings, "DATABASE_URL", database_url)

    assert main(["--tool-name", "get_current_time", "--target-team", team_id]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool_name"] == "get_current_time"
    assert payload["target_team"] == team_id
    assert payload["connection_id"]

    assert main(["--tool-name", "get_current_time", "--target-team", team_id]) == 1
    error = json.loads(capsys.readouterr().out)
    assert "no global ToolConfig rows" in error["error"]
