from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from app.core import init_data
from app.models.site_setting import SiteSetting


@pytest.mark.asyncio
async def test_registration_settings_migrate_only_legacy_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = SimpleNamespace(category="general", save=AsyncMock())
    current = SimpleNamespace(category="security", save=AsyncMock())
    settings = {
        "allow_registration": legacy,
        "require_approval": current,
        "email_verification": None,
        "allow_account_deletion": None,
    }
    first = AsyncMock(side_effect=lambda: settings[first.key])

    def filter_setting(*, key: str) -> SimpleNamespace:
        first.key = key
        return SimpleNamespace(first=first)

    monkeypatch.setattr(SiteSetting, "filter", filter_setting)

    await init_data.migrate_registration_settings_category()

    assert legacy.category == "security"
    legacy.save.assert_awaited_once_with()
    current.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_history_index_created_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["messages"]),  # table exists
                (1, []),  # index missing
            ]
        )
    )
    migration = AsyncMock(return_value=(1, []))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_message_history_index()

    migration.assert_awaited_once_with(conn, ANY)
    sql = migration.await_args.args[1]
    assert "idx_messages_conversation_active_created_at" in sql
    assert "ON messages (conversation_id, is_active, created_at)" in sql


@pytest.mark.asyncio
async def test_message_history_index_skipped_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["messages"]),  # table exists
                (1, [{"indexname": "idx_messages_conversation_active_created_at"}]),
            ]
        )
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_message_history_index()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_history_index_skipped_before_first_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(return_value=(1, []))  # messages table missing
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_message_history_index()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_history_index_sqlite_created_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(
            side_effect=[
                (1, ["messages"]),  # sqlite_master table probe
                (1, []),  # index missing
            ]
        ),
    )
    migration = AsyncMock(return_value=(1, []))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_message_history_index()

    migration.assert_awaited_once_with(conn, ANY)
    sql = migration.await_args.args[1]
    assert "idx_messages_conversation_active_created_at" in sql
    assert "ON messages (conversation_id, is_active, created_at)" in sql
    statements = [a.args[0] for a in conn.execute_query.await_args_list]
    assert any("sqlite_master" in s for s in statements)
    assert not any("information_schema" in s for s in statements)
    assert not any("pg_indexes" in s for s in statements)


@pytest.mark.asyncio
async def test_message_history_index_sqlite_skipped_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(
            side_effect=[
                (1, ["messages"]),
                (1, [{"name": "idx_messages_conversation_active_created_at"}]),
            ]
        ),
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_message_history_index()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_notification_tables_create_only_missing_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (0, []),
                (0, []),
                (0, []),
                (0, []),
                (0, []),
                (0, ["notification_deliveries"]),
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_notification_tables()

    queries = [args.args[0] for args in conn.execute_query.await_args_list]
    assert any("CREATE TABLE IF NOT EXISTS notifications" in query for query in queries)
    assert any(
        "CREATE TABLE IF NOT EXISTS notification_reads" in query for query in queries
    )
    assert any(
        "CREATE TABLE IF NOT EXISTS notification_audits" in query for query in queries
    )
    assert not any(
        "CREATE TABLE IF NOT EXISTS notification_deliveries" in query
        for query in queries
    )


@pytest.mark.asyncio
async def test_notification_tables_existing_state_executes_only_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["notifications"]),
                (1, ["notification_deliveries"]),
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_notification_tables()

    assert conn.execute_query.await_count == 2
    assert all(
        "SELECT table_name FROM information_schema.tables" in awaited.args[0]
        for awaited in conn.execute_query.await_args_list
    )


@pytest.mark.asyncio
async def test_agent_powered_by_text_column_is_added_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(1, ["agents"]), (1, [])]  # table probe, column probe
        )
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_powered_by_text()

    assert migration.await_count == 1
    assert "ADD COLUMN powered_by_text TEXT" in migration.await_args.args[1]


@pytest.mark.asyncio
async def test_agent_powered_by_text_skips_when_column_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(1, ["agents"]), (1, [{"column_name": "powered_by_text"}])]
        )
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_powered_by_text()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_powered_by_text_skips_without_agents_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(1, [])))
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_powered_by_text()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_powered_by_text_sqlite_column_added_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(
            side_effect=[
                (1, ["agents"]),  # sqlite_master table probe
                (1, [(0, "id"), (1, "name")]),  # PRAGMA table_info, column absent
            ]
        ),
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_powered_by_text()

    migration.assert_awaited_once()
    assert "ADD COLUMN powered_by_text TEXT" in migration.await_args.args[1]
    statements = [a.args[0] for a in conn.execute_query.await_args_list]
    assert any("sqlite_master" in s for s in statements)
    assert any("PRAGMA table_info" in s for s in statements)
    assert not any("information_schema" in s for s in statements)


@pytest.mark.asyncio
async def test_agent_powered_by_text_sqlite_skips_when_column_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(
            side_effect=[
                (1, ["agents"]),
                (1, [(0, "id"), (1, "powered_by_text")]),
            ]
        ),
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_powered_by_text()

    migration.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_pause_migration_skips_non_postgres_and_keeps_create_resilient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"), execute_query=AsyncMock()
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: sqlite)
    await init_data.init_workflow_pause_requests_table()
    sqlite.execute_query.assert_not_awaited()

    postgres = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        execute_query=AsyncMock(
            side_effect=[
                RuntimeError("schema not generated"),
                None,
                RuntimeError(),
                RuntimeError(),
                None,
                None,
            ]
        ),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: postgres)
    await init_data.init_workflow_pause_requests_table()
    queries = [call.args[0] for call in postgres.execute_query.await_args_list]
    assert len(queries) == 6
    assert "CREATE TABLE IF NOT EXISTS workflow_pause_requests" in queries[1]
    assert "ADD COLUMN IF NOT EXISTS description" in queries[2]
    assert "ADD COLUMN IF NOT EXISTS approvals" in queries[3]


@pytest.mark.asyncio
async def test_agent_run_migration_skips_absent_table_and_updates_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, []), (1, ["agent_runs"])])
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_run_fields()
    assert not migration.await_count
    await init_data.init_agent_run_fields()
    migration.assert_awaited_once()
    assert "pending_tool_input JSONB" in migration.await_args.args[1]


@pytest.mark.asyncio
async def test_knowledge_base_share_migration_skips_existing_table_and_builds_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, ["exists"]), (1, []), None])
    )
    ddl = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "_execute_ddl", ddl)

    await init_data.init_knowledge_base_shares_table()
    assert conn.execute_query.await_count == 1
    ddl.assert_not_awaited()
    await init_data.init_knowledge_base_shares_table()
    assert (
        "CREATE TABLE IF NOT EXISTS knowledge_base_shares"
        in conn.execute_query.await_args.args[0]
    )
    ddl.assert_awaited_once()
    assert "idx_kb_shares_team_id" in ddl.await_args.args[1]


@pytest.mark.asyncio
async def test_notification_delivery_migration_creates_only_missing_delivery_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, ["notifications"]), (1, []), None])
    )
    ddl = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "_execute_ddl", ddl)

    await init_data.init_notification_tables()

    queries = [call.args[0] for call in conn.execute_query.await_args_list]
    assert any(
        "CREATE TABLE IF NOT EXISTS notification_deliveries" in q for q in queries
    )
    ddl.assert_awaited_once()
    assert "idx_notification_deliveries_status_created" in ddl.await_args.args[1]


@pytest.mark.asyncio
async def test_run_and_agent_visibility_migrations_skip_unavailable_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(side_effect=[(1, []), (1, []), (1, []), (1, [])]),
    )
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_run_fields()
    await init_data.init_agent_hide_message_actions_reasoning_fields()
    await init_data.init_agent_enable_citations_field()
    await init_data.init_agent_hide_artifact_list_field()

    migration.assert_not_awaited()
    assert conn.execute_query.await_count == 4


@pytest.mark.asyncio
async def test_visibility_and_model_revert_migrations_handle_absent_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, []), (1, []), (1, [])])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_kb_visibility_fields()
    await init_data.init_tool_visibility_fields()
    await init_data.revert_channel_id_to_model_id()

    assert conn.execute_query.await_count == 3


@pytest.mark.asyncio
async def test_existing_visibility_columns_only_change_future_default(monkeypatch):
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["knowledge_bases"]),
                (1, ["visibility"]),
                None,
                (1, ["tools"]),
                (1, ["visibility"]),
                None,
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_kb_visibility_fields()
    await init_data.init_tool_visibility_fields()

    statements = [call.args[0] for call in conn.execute_query.await_args_list]
    assert len(statements) == 6
    assert all(
        "SET DEFAULT 'private'" in q
        for q in statements
        if "ALTER COLUMN visibility" in q
    )
    assert not any("ADD COLUMN visibility" in q for q in statements)


@pytest.mark.asyncio
async def test_assets_tables_representation_migration_failure_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock())
    migration = AsyncMock(
        side_effect=[(1, []), RuntimeError("representation DDL failed")]
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    with pytest.raises(RuntimeError, match="representation DDL failed"):
        await init_data.init_assets_tables()


@pytest.mark.asyncio
async def test_conversation_summary_columns_use_idempotent_alters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock())
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_conversation_context_summary_columns()

    conn.execute_query.assert_not_awaited()
    assert [c.args[0] for c in migration.await_args_list] == [conn, conn]
    statements = [c.args[1] for c in migration.await_args_list]
    assert all("ADD COLUMN IF NOT EXISTS" in s for s in statements)
    assert "context_summary_text" in statements[0]
    assert "context_summary_watermark_id" in statements[1]


@pytest.mark.asyncio
async def test_workflow_run_page_config_sets_presentation_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock())
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_workflow_run_page_config()

    migration.assert_awaited_once()
    sql = migration.await_args.args[1]
    assert migration.await_args.args[0] is conn
    assert "ALTER TABLE workflows" in sql
    assert "ADD COLUMN IF NOT EXISTS run_page_config JSONB NOT NULL" in sql
    assert '"presentation_mode": "simple"' in sql


@pytest.mark.asyncio
async def test_revert_channel_id_renames_only_when_legacy_column_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["models"]),  # table probe
                (1, [{"column_name": "channel_id"}]),  # legacy column probe
                None,  # rename
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.revert_channel_id_to_model_id()

    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert statements[2] == "ALTER TABLE models RENAME COLUMN channel_id TO model_id"


@pytest.mark.asyncio
async def test_revert_channel_id_keeps_model_id_column_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["models"]),  # table probe
                (0, []),  # legacy column absent
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.revert_channel_id_to_model_id()

    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert not any("RENAME COLUMN" in s for s in statements)


@pytest.mark.asyncio
async def test_tool_visibility_adds_legacy_column_then_retargets_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["tools"]),  # table probe
                (0, []),  # visibility column probe
                None,  # add column
                None,  # retarget default
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_tool_visibility_fields()

    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert "ADD COLUMN visibility VARCHAR(20) NOT NULL DEFAULT 'team'" in statements[2]
    assert "SET DEFAULT 'private'" in statements[3]


@pytest.mark.asyncio
async def test_password_expiration_propagates_history_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = RuntimeError("cannot create password_history")
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (1, ["users"]),
                (1, [{"column_name": "password_changed_at"}]),
                (0, []),
                error,
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot create password_history"):
        await init_data.init_password_expiration()

    assert conn.execute_query.await_count == 4


@pytest.mark.asyncio
async def test_agent_hide_message_actions_and_reasoning_add_both_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[(1, ["agents"])]))
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_hide_message_actions_reasoning_fields()

    conn.execute_query.assert_awaited_once()
    statements = [c.args[1] for c in migration.await_args_list]
    assert len(statements) == 2
    assert all("ALTER TABLE agents" in s for s in statements)
    assert all("ADD COLUMN IF NOT EXISTS" in s for s in statements)
    assert "hide_message_actions BOOLEAN NOT NULL DEFAULT FALSE" in statements[0]
    assert "hide_reasoning BOOLEAN NOT NULL DEFAULT FALSE" in statements[1]


@pytest.mark.asyncio
async def test_agent_citation_preference_migration_adds_default_false_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[(1, ["agents"])]))
    migration = AsyncMock()
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_enable_citations_field()

    statement = migration.await_args.args[1]
    assert (
        "ADD COLUMN IF NOT EXISTS enable_citations BOOLEAN NOT NULL DEFAULT FALSE"
        in statement
    )


@pytest.mark.asyncio
async def test_feishu_placeholder_email_rewrites_only_legacy_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import feishu_directory

    sql = init_data.feishu_placeholder_email_update_sql(
        feishu_directory.LEGACY_PLACEHOLDER_EMAIL_DOMAIN,
        feishu_directory.PLACEHOLDER_EMAIL_DOMAIN,
    )
    assert feishu_directory.LEGACY_PLACEHOLDER_EMAIL_DOMAIN in sql
    assert feishu_directory.PLACEHOLDER_EMAIL_DOMAIN in sql
    assert "auth_source = 'feishu'" in sql
    assert "REPLACE(email," in sql

    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        execute_query=AsyncMock(side_effect=[(1, ["users"]), (1, [])]),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_feishu_placeholder_emails()

    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert any("information_schema" in s for s in statements)
    assert statements[1] == sql


@pytest.mark.asyncio
async def test_feishu_placeholder_email_uses_sqlite_probe_and_skips_missing_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="sqlite"),
        execute_query=AsyncMock(side_effect=[(1, ["users"]), (1, []), (0, [])]),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_feishu_placeholder_emails()
    first_statement = conn.execute_query.await_args_list[0].args[0]
    assert "sqlite_master" in first_statement

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [(0, [])]

    await init_data.init_feishu_placeholder_emails()

    assert conn.execute_query.await_count == 1
    assert "sqlite_master" in conn.execute_query.await_args.args[0]


@pytest.mark.asyncio
async def test_init_db_seeds_permissions_roles_and_settings_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init_db happy path: newly created roles, permission seeding, tail steps."""
    optional_migrations = [
        "init_user_locale_field",
        "init_agent_attachment_fields",
        "init_agent_tools_credentials",
        "init_agent_powered_by_text",
        "init_message_history_index",
        "init_permission_is_system_field",
        "drop_model_provider_uniqueness",
        "init_kb_rerank_fields",
        "init_kb_visibility_fields",
        "init_clouisle_import_sessions_table",
        "drop_obsolete_retrieval_evaluation_tables",
        "init_model_provider_display_name",
        "migrate_model_input_modalities",
    ]
    for name in optional_migrations:
        monkeypatch.setattr(init_data, name, AsyncMock())

    permission_definitions = [
        {"code": "agent:read", "scope": "team", "description": "Read agents"},
        {"code": "agent:create", "scope": "team", "description": "Create agents"},
    ]
    monkeypatch.setattr(
        init_data.SystemPermissions,
        "get_all_definitions",
        lambda: permission_definitions,
    )
    seeded_permissions: list[dict] = []

    async def get_or_create_permission(*, code: str, defaults: dict):
        seeded_permissions.append({"code": code, **defaults})

    monkeypatch.setattr(init_data.Permission, "get_or_create", get_or_create_permission)

    from app.core import integration_migration

    monkeypatch.setattr(
        integration_migration, "migrate_integration_permissions", AsyncMock()
    )

    created_roles: list[str] = []
    all_permission = SimpleNamespace(code="*")

    async def get_or_create_role(*, name: str, defaults: dict):
        created_roles.append(name)
        role = SimpleNamespace(
            id=name,
            permissions=SimpleNamespace(
                add=AsyncMock(), all=AsyncMock(return_value=[])
            ),
        )
        return role, True

    monkeypatch.setattr(init_data.Role, "get_or_create", get_or_create_role)

    async def get_permission(*, code: str):
        assert code == "*"
        return all_permission

    monkeypatch.setattr(init_data.Permission, "get", get_permission)
    monkeypatch.setattr(init_data, "sync_role_permissions", AsyncMock())

    team_admin_migration = AsyncMock()
    monkeypatch.setattr(init_data, "migrate_team_admin_roles", team_admin_migration)

    monkeypatch.setattr(init_data, "init_model_endpoint_allowlist", AsyncMock())
    monkeypatch.setattr(init_data, "init_default_settings", AsyncMock())
    monkeypatch.setattr(init_data, "migrate_auto_notification_types", AsyncMock())

    from app.models.site_setting import SiteSetting

    set_value = AsyncMock()
    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    monkeypatch.setattr(SiteSetting, "set_value", set_value)

    monkeypatch.setattr(
        init_data, "migrate_registration_settings_category", AsyncMock()
    )
    monkeypatch.setattr(init_data, "migrate_storage_settings_category", AsyncMock())
    for tail in (
        "init_workflow_tables",
        "init_notification_tables",
        "init_tool_shares_table",
        "init_knowledge_base_shares_table",
        "init_skills_table",
        "fix_cascade_delete_policies",
        "init_memory_tables",
        "init_agent_hide_tool_calls_field",
        "init_agent_hide_message_actions_reasoning_fields",
        "init_agent_enable_citations_field",
        "init_agent_hide_artifact_list_field",
        "init_agent_memory_fields",
        "init_agent_media_generation_fields",
    ):
        monkeypatch.setattr(init_data, tail, AsyncMock())

    await init_data.init_db()

    assert created_roles == [
        init_data.SUPER_ADMIN_ROLE,
        "Admin",
        "Member",
        "Team Admin",
        "Viewer",
    ]
    assert [entry["code"] for entry in seeded_permissions] == [
        "agent:read",
        "agent:create",
    ]
    assert all(entry["is_system"] is True for entry in seeded_permissions)
    set_value.assert_awaited_once_with(
        key="default_role_id",
        value="Viewer",
        value_type="string",
        category="security",
        description="Default role ID for new users",
        is_public=False,
    )
    team_admin_migration.assert_awaited_once()
    init_data.init_agent_media_generation_fields.assert_awaited_once()
    assert team_admin_migration.await_args.args[0].id == "Member"
    assert team_admin_migration.await_args.args[1].id == "Team Admin"


@pytest.mark.asyncio
async def test_allowlist_seeding_skips_models_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Models with no effective base URL are skipped rather than seeded."""
    from app.core import model_endpoint_policy
    from app.models.model import Model
    from app.models.site_setting import SiteSetting

    monkeypatch.setattr(
        SiteSetting,
        "filter",
        lambda **_kwargs: SimpleNamespace(first=AsyncMock(return_value=None)),
    )
    set_value = AsyncMock()
    monkeypatch.setattr(SiteSetting, "set_value", set_value)
    monkeypatch.setattr(
        Model,
        "all",
        AsyncMock(
            return_value=[
                SimpleNamespace(id="blank", get_effective_base_url=lambda: None),
                SimpleNamespace(id="empty", get_effective_base_url=lambda: ""),
            ]
        ),
    )

    await init_data.init_model_endpoint_allowlist()

    assert set_value.await_args.kwargs["value"] == list(
        model_endpoint_policy.DEFAULT_MODEL_ENDPOINT_ALLOWLIST
    )


@pytest.mark.asyncio
async def test_auto_notification_migration_skips_non_list_enabled_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persisted config whose enabled_types is not a list is left untouched."""
    set_value = AsyncMock()
    monkeypatch.setattr(
        SiteSetting, "get_value", AsyncMock(return_value={"enabled_types": "all"})
    )
    monkeypatch.setattr(SiteSetting, "set_value", set_value)

    await init_data.migrate_auto_notification_types()

    set_value.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_settings_migration_reports_already_correct_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No legacy audit-category settings means nothing is written."""
    migrated = SimpleNamespace(category="storage", save=AsyncMock())
    settings = {
        "audit_log_retention_days": migrated,
        "audit_log_archive_path": migrated,
    }
    monkeypatch.setattr(
        SiteSetting,
        "filter",
        lambda **kwargs: SimpleNamespace(
            first=AsyncMock(return_value=settings[kwargs["key"]])
        ),
    )

    await init_data.migrate_storage_settings_category()

    migrated.save.assert_not_awaited()
