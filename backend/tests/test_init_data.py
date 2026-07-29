from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from app.core import init_data


@pytest.mark.asyncio
async def test_startup_migration_resets_lock_timeout_after_success() -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[None, (1, ["ok"]), None])
    )

    result = await init_data.execute_startup_migration_query(
        conn, "ALTER TABLE example"
    )

    assert result == (1, ["ok"])
    assert conn.execute_query.await_args_list == [
        call("SET lock_timeout = '2s'"),
        call("ALTER TABLE example"),
        call("RESET lock_timeout"),
    ]


@pytest.mark.asyncio
async def test_startup_migration_resets_lock_timeout_after_failure() -> None:
    error = RuntimeError("migration failed")
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[None, error, None]))

    with pytest.raises(RuntimeError, match="migration failed"):
        await init_data.execute_startup_migration_query(conn, "BROKEN SQL")

    assert conn.execute_query.await_args_list[-1] == call("RESET lock_timeout")


@pytest.mark.asyncio
async def test_postgres_lexical_search_initializes_and_validates(monkeypatch) -> None:
    conn = SimpleNamespace(
        execute_query_dict=AsyncMock(
            side_effect=[
                [{"libraries": "pg_search,pg_stat_statements"}],
                [{"extversion": "0.24.3"}],
            ]
        ),
        execute_query=AsyncMock(),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_postgres_lexical_search()

    queries = [item.args[0] for item in conn.execute_query.await_args_list]
    migration_queries = [
        query
        for query in queries
        if "document_chunks" in query and "updated_at" in query
    ]
    assert len(migration_queries) == 3
    assert "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ" in migration_queries[0]
    assert "SET updated_at = created_at" in migration_queries[1]
    assert "ALTER COLUMN updated_at SET NOT NULL" in migration_queries[2]
    assert all(query.count(";") <= 1 for query in migration_queries)
    assert any(
        "CREATE TABLE IF NOT EXISTS knowledge_lexical_chunks" in q for q in queries
    )
    assert any("USING bm25" in q and "pdb.jieba" in q for q in queries)


@pytest.mark.asyncio
async def test_postgres_lexical_search_rejects_missing_preload(monkeypatch) -> None:
    conn = SimpleNamespace(
        execute_query_dict=AsyncMock(return_value=[{"libraries": "pg_stat_statements"}])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="pg_search"):
        await init_data.init_postgres_lexical_search()


@pytest.mark.asyncio
async def test_sync_role_permissions_adds_and_removes_only_differences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wanted = SimpleNamespace(id="wanted", code="wanted")
    existing = SimpleNamespace(id="existing", code="existing")
    obsolete = SimpleNamespace(id="obsolete", code="obsolete")
    found = {permission.code: permission for permission in (wanted, existing)}

    async def first_for_code(*, code: str) -> object:
        return found.get(code)

    permission_filter = lambda **kwargs: SimpleNamespace(  # noqa: E731
        first=lambda: first_for_code(**kwargs)
    )
    monkeypatch.setattr(init_data.Permission, "filter", permission_filter)

    role_permissions = SimpleNamespace(
        filter=lambda **kwargs: SimpleNamespace(
            exists=AsyncMock(return_value=kwargs["id"] == existing.id)
        ),
        add=AsyncMock(),
        all=AsyncMock(return_value=[existing, obsolete]),
        remove=AsyncMock(),
    )
    role = SimpleNamespace(permissions=role_permissions)

    await init_data.sync_role_permissions(role, ["wanted", "existing"], "Test")

    role_permissions.add.assert_awaited_once_with(wanted)
    role_permissions.remove.assert_awaited_once_with(obsolete)


@pytest.mark.asyncio
async def test_sync_role_permissions_ignores_missing_and_keeps_idempotent_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(id="existing", code="existing")

    async def first_for_code(*, code: str) -> object:
        return existing if code == existing.code else None

    monkeypatch.setattr(
        init_data.Permission,
        "filter",
        lambda **kwargs: SimpleNamespace(first=lambda: first_for_code(**kwargs)),
    )
    role_permissions = SimpleNamespace(
        filter=lambda **_kwargs: SimpleNamespace(exists=AsyncMock(return_value=True)),
        add=AsyncMock(),
        all=AsyncMock(return_value=[existing]),
        remove=AsyncMock(),
    )

    await init_data.sync_role_permissions(
        SimpleNamespace(permissions=role_permissions),
        ["existing", "missing"],
        "Test",
    )

    role_permissions.add.assert_not_awaited()
    role_permissions.remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_tables_skip_creation_when_workflows_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(1, ["workflows"])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_workflow_tables()

    conn.execute_query.assert_awaited_once()
    assert "information_schema.tables" in conn.execute_query.await_args.args[0]


@pytest.mark.asyncio
async def test_workflow_tables_create_all_tables_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_workflow_tables()

    queries = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert len(queries) == 5
    assert "CREATE TABLE IF NOT EXISTS workflows" in queries[1]
    assert "CREATE TABLE IF NOT EXISTS workflow_runs" in queries[2]
    assert "CREATE TABLE IF NOT EXISTS node_executions" in queries[3]
    assert "CREATE INDEX IF NOT EXISTS idx_workflows_team_id" in queries[4]
    assert "CREATE INDEX IF NOT EXISTS idx_node_executions_status" in queries[4]


@pytest.mark.asyncio
async def test_workflow_tables_stop_after_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = RuntimeError("cannot create workflow runs")
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(0, []), (0, []), error])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot create workflow runs") as exc_info:
        await init_data.init_workflow_tables()

    assert exc_info.value is error
    assert conn.execute_query.await_count == 3
    assert (
        "CREATE TABLE IF NOT EXISTS workflow_runs"
        in (conn.execute_query.await_args_list[-1].args[0])
    )


@pytest.mark.asyncio
async def test_init_db_initializes_roles_settings_and_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_names = [
        "init_user_locale_field",
        "init_agent_tools_credentials",
        "init_permission_is_system_field",
        "init_model_type_unique_constraint",
        "init_kb_rerank_fields",
        "init_clouisle_import_sessions_table",
        "drop_obsolete_retrieval_evaluation_tables",
        "init_scoped_role_assignments_table",
        "init_default_settings",
        "migrate_registration_settings_category",
        "migrate_storage_settings_category",
        "init_workflow_tables",
        "init_notification_tables",
        "init_tool_shares_table",
        "init_skills_table",
        "fix_cascade_delete_policies",
        "init_sso_tables",
        "init_memory_tables",
        "init_agent_hide_tool_calls_field",
        "init_agent_memory_fields",
        "init_agent_media_generation_fields",
    ]
    migrations = {name: AsyncMock() for name in migration_names}
    for name, migration in migrations.items():
        monkeypatch.setattr(init_data, name, migration)

    monkeypatch.setattr(
        init_data.SystemPermissions,
        "get_all_definitions",
        lambda: [{"code": "*", "scope": "system", "description": "All"}],
    )
    monkeypatch.setattr(init_data.Permission, "get_or_create", AsyncMock())
    all_permission = SimpleNamespace(code="*")
    monkeypatch.setattr(
        init_data.Permission, "get", AsyncMock(return_value=all_permission)
    )

    roles = {}

    async def get_or_create_role(*, name: str, defaults: dict) -> tuple[object, bool]:
        role = SimpleNamespace(
            id=f"role-{name.lower()}",
            name=name,
            defaults=defaults,
            permissions=SimpleNamespace(add=AsyncMock()),
        )
        roles[name] = role
        return role, True

    monkeypatch.setattr(init_data.Role, "get_or_create", get_or_create_role)
    sync_permissions = AsyncMock()
    monkeypatch.setattr(init_data, "sync_role_permissions", sync_permissions)
    from app.models.site_setting import SiteSetting

    monkeypatch.setattr(SiteSetting, "get_value", AsyncMock(return_value=""))
    set_value = AsyncMock()
    monkeypatch.setattr(SiteSetting, "set_value", set_value)

    await init_data.init_db()

    assert set(roles) == {init_data.SUPER_ADMIN_ROLE, "Admin", "Member", "Viewer"}
    roles[init_data.SUPER_ADMIN_ROLE].permissions.add.assert_awaited_once_with(
        all_permission
    )
    assert [awaited.args[2] for awaited in sync_permissions.await_args_list] == [
        "Admin",
        "Member",
        "Viewer",
    ]
    set_value.assert_awaited_once_with(
        key="default_role_id",
        value="role-viewer",
        value_type="string",
        category="security",
        description="Default role ID for new users",
        is_public=False,
    )
    for migration in migrations.values():
        assert migration.await_count >= 1
    assert migrations["init_agent_tools_credentials"].await_count == 2


@pytest.mark.asyncio
async def test_init_db_continues_after_optional_migration_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    optional_names = [
        "init_user_locale_field",
        "init_agent_tools_credentials",
        "init_permission_is_system_field",
        "init_model_type_unique_constraint",
        "init_kb_rerank_fields",
        "init_clouisle_import_sessions_table",
        "drop_obsolete_retrieval_evaluation_tables",
    ]
    for name in optional_names:
        monkeypatch.setattr(
            init_data, name, AsyncMock(side_effect=RuntimeError(f"{name} failed"))
        )

    monkeypatch.setattr(init_data.SystemPermissions, "get_all_definitions", lambda: [])
    monkeypatch.setattr(init_data.Permission, "get_or_create", AsyncMock())

    roles = []

    async def get_or_create_role(*, name: str, defaults: dict) -> tuple[object, bool]:
        roles.append((name, defaults))
        return SimpleNamespace(
            id=name, permissions=SimpleNamespace(add=AsyncMock())
        ), False

    monkeypatch.setattr(init_data.Role, "get_or_create", get_or_create_role)
    monkeypatch.setattr(init_data, "sync_role_permissions", AsyncMock())
    monkeypatch.setattr(
        init_data,
        "init_scoped_role_assignments_table",
        AsyncMock(side_effect=RuntimeError("required migration failed")),
    )

    with pytest.raises(RuntimeError, match="required migration failed"):
        await init_data.init_db()

    assert [name for name, _ in roles] == [
        init_data.SUPER_ADMIN_ROLE,
        "Admin",
        "Member",
        "Viewer",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("migration", "existing_queries", "expected_count", "expected_fragment"),
    [
        (init_data.init_user_locale_field, [(0, [])], 1, None),
        (init_data.init_user_locale_field, [(1, ["users"]), (1, ["locale"])], 2, None),
        (
            init_data.init_user_locale_field,
            [(1, ["users"]), (0, [])],
            3,
            "ADD COLUMN locale",
        ),
        (init_data.init_permission_is_system_field, [(0, [])], 1, None),
        (
            init_data.init_permission_is_system_field,
            [(1, ["permissions"]), (1, ["is_system"])],
            2,
            None,
        ),
        (
            init_data.init_permission_is_system_field,
            [(1, ["permissions"]), (0, [])],
            3,
            "ADD COLUMN is_system",
        ),
        (init_data.init_kb_rerank_fields, [(0, [])], 1, None),
        (
            init_data.init_kb_rerank_fields,
            [(1, ["knowledge_bases"]), (1, ["rerank_model_id"])],
            2,
            None,
        ),
        (
            init_data.init_kb_rerank_fields,
            [(1, ["knowledge_bases"]), (0, [])],
            3,
            "ADD COLUMN IF NOT EXISTS rerank_model_id",
        ),
    ],
)
async def test_simple_startup_migrations_cover_absent_existing_and_create_paths(
    monkeypatch: pytest.MonkeyPatch,
    migration,
    existing_queries: list[tuple[int, list[str]]],
    expected_count: int,
    expected_fragment: str | None,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[*existing_queries, (0, [])])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await migration()

    assert conn.execute_query.await_count == expected_count
    if expected_fragment:
        assert expected_fragment in conn.execute_query.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "migration",
    [init_data.init_user_locale_field, init_data.init_permission_is_system_field],
)
async def test_simple_startup_migrations_propagate_schema_change_failure(
    monkeypatch: pytest.MonkeyPatch, migration
) -> None:
    failure = RuntimeError("schema change failed")
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, ["table"]), (0, []), failure])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="schema change failed"):
        await migration()


@pytest.mark.asyncio
async def test_model_unique_constraint_skips_or_runs_both_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_model_type_unique_constraint()
    conn.execute_query.assert_awaited_once()

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [(1, ["models"]), (0, []), (0, [])]
    await init_data.init_model_type_unique_constraint()

    assert conn.execute_query.await_count == 3
    queries = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert "UNIQUE (provider, model_id)" in queries[1]
    assert "UNIQUE (provider, model_id, model_type)" in queries[2]


@pytest.mark.asyncio
async def test_scoped_role_assignments_backfills_supported_memberships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace()
    execute = AsyncMock(return_value=(0, []))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", execute)

    roles = {
        "Admin": SimpleNamespace(id="role-admin"),
        "Member": SimpleNamespace(id="role-member"),
        "Viewer": None,
    }

    class RoleQuery:
        async def first(self):
            return roles[self.name]

        def __init__(self, name: str):
            self.name = name

    monkeypatch.setattr(init_data.Role, "filter", lambda *, name: RoleQuery(name))
    memberships = [
        SimpleNamespace(
            role="owner",
            user=SimpleNamespace(id="user-owner"),
            team=SimpleNamespace(id="team-1"),
        ),
        SimpleNamespace(
            role="member",
            user=SimpleNamespace(id="user-member"),
            team=SimpleNamespace(id="team-1"),
        ),
        SimpleNamespace(
            role="viewer",
            user=SimpleNamespace(id="user-viewer"),
            team=SimpleNamespace(id="team-1"),
        ),
        SimpleNamespace(
            role="legacy",
            user=SimpleNamespace(id="user-legacy"),
            team=SimpleNamespace(id="team-1"),
        ),
    ]

    class MembershipQuery:
        async def prefetch_related(self, *_relations):
            return memberships

    monkeypatch.setattr(init_data.TeamMember, "all", lambda: MembershipQuery())

    await init_data.init_scoped_role_assignments_table()

    assert execute.await_count == 5
    statements = [awaited.args[1] for awaited in execute.await_args_list]
    assert "CREATE TABLE IF NOT EXISTS scoped_role_assignments" in statements[0]
    assert "gen_random_uuid(), 'user-owner', 'role-admin'" in statements[3]
    assert "NOW(), NOW()" in statements[3]
    assert "gen_random_uuid(), 'user-member', 'role-member'" in statements[4]
    assert "NOW(), NOW()" in statements[4]
    assert all("user-viewer" not in statement for statement in statements)
    assert all("user-legacy" not in statement for statement in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tables", "columns", "null_rows", "migration_count"),
    [
        ([], [], [], 0),
        (["agents"], ["tools_credentials"], [], 1),
        (["agents"], ["tools_credentials"], [{"null_count": 0}], 1),
        (["agents"], [], [{"null_count": 2}], 3),
    ],
)
async def test_agent_tools_credentials_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
    tables: list[str],
    columns: list[str],
    null_rows: list[dict[str, int]],
    migration_count: int,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(len(tables), tables), (len(columns), columns)]
        )
    )
    migration_results = [] if columns else [(0, [])]
    migration_results.extend([(1, null_rows), (0, [])])
    execute = AsyncMock(side_effect=migration_results)
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", execute)

    await init_data.init_agent_tools_credentials()

    assert execute.await_count == migration_count
    if migration_count == 3:
        statements = [awaited.args[1] for awaited in execute.await_args_list]
        assert "ADD COLUMN tools_credentials" in statements[0]
        assert "SELECT COUNT(*) AS null_count" in statements[1]
        assert "UPDATE agents" in statements[2]


@pytest.mark.asyncio
async def test_agent_tools_credentials_propagates_add_failure_but_tolerates_backfill_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, ["agents"]), (0, [])])
    )
    execute = AsyncMock(side_effect=RuntimeError("cannot alter"))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", execute)

    with pytest.raises(RuntimeError, match="cannot alter"):
        await init_data.init_agent_tools_credentials()

    conn.execute_query.side_effect = [(1, ["agents"]), (1, ["tools_credentials"])]
    execute.reset_mock()
    execute.side_effect = RuntimeError("cannot count")
    await init_data.init_agent_tools_credentials()
    execute.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tables", "count_rows", "expected_calls"),
    [
        ([], [], 0),
        (["agents"], [], 1),
        (["agents"], [{"public_count": 0}], 1),
        (["agents"], [{"public_count": 2}], 2),
    ],
)
async def test_agent_visibility_normalization_paths(
    monkeypatch: pytest.MonkeyPatch,
    tables: list[str],
    count_rows: list[dict[str, int]],
    expected_calls: int,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(len(tables), tables)))
    execute = AsyncMock(side_effect=[(1, count_rows), (0, [])])
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", execute)

    await init_data.init_agent_visibility_values()

    assert execute.await_count == expected_calls
    if expected_calls == 2:
        assert "SET visibility = 'team'" in execute.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_agent_visibility_normalization_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(1, ["agents"])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(
        init_data,
        "execute_startup_migration_query",
        AsyncMock(side_effect=RuntimeError("cannot normalize")),
    )

    with pytest.raises(RuntimeError, match="cannot normalize"):
        await init_data.init_agent_visibility_values()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing", "expected_calls"),
    [
        (["clouisle_import_sessions"], 3),
        ([], 5),
    ],
)
async def test_clouisle_import_sessions_ensures_existing_or_creates_table(
    monkeypatch: pytest.MonkeyPatch,
    existing: list[str],
    expected_calls: int,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(return_value=(len(existing), existing))
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_clouisle_import_sessions_table()

    assert conn.execute_query.await_count == expected_calls
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    if existing:
        assert "ADD COLUMN IF NOT EXISTS source" in statements[1]
        assert "idx_clouisle_import_sessions_source_status" in statements[2]
    else:
        assert "CREATE TABLE IF NOT EXISTS clouisle_import_sessions" in statements[1]
        assert "idx_clouisle_import_sessions_team_status" in statements[2]
        assert "idx_clouisle_import_sessions_source_status" in statements[3]
        assert "idx_clouisle_import_sessions_expires_at" in statements[4]


@pytest.mark.asyncio
async def test_clouisle_import_sessions_stops_after_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("cannot create import table")
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[(0, []), failure]))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot create import table"):
        await init_data.init_clouisle_import_sessions_table()

    assert conn.execute_query.await_count == 2


@pytest.mark.asyncio
async def test_skills_table_creates_schema_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_skills_table()

    assert conn.execute_query.await_count == 4
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert "CREATE TABLE IF NOT EXISTS skills" in statements[0]
    assert "ALTER TABLE skills" in statements[1]
    assert "CREATE TABLE IF NOT EXISTS skill_import_sessions" in statements[2]
    assert "idx_skill_import_sessions_expires_at" in statements[3]


@pytest.mark.asyncio
async def test_skills_table_propagates_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("cannot alter skills")
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[(0, []), failure]))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot alter skills"):
        await init_data.init_skills_table()

    assert conn.execute_query.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing", "expected_calls"),
    [
        (["tool_shares"], 1),
        ([], 3),
    ],
)
async def test_tool_shares_skips_existing_or_creates_schema(
    monkeypatch: pytest.MonkeyPatch,
    existing: list[str],
    expected_calls: int,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(return_value=(len(existing), existing))
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_tool_shares_table()

    assert conn.execute_query.await_count == expected_calls
    if not existing:
        statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
        assert "CREATE TABLE IF NOT EXISTS tool_shares" in statements[1]
        assert "idx_tool_shares_shared_by" in statements[2]


@pytest.mark.asyncio
async def test_tool_shares_stops_after_table_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("cannot create tool shares")
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=[(0, []), failure]))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot create tool shares"):
        await init_data.init_tool_shares_table()

    assert conn.execute_query.await_count == 2


@pytest.mark.asyncio
async def test_cascade_policy_migration_adds_missing_columns_and_resets_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                *[(0, [])] * 13,
                *[(0, []), (0, [])] * 6,
                (0, []),
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.fix_cascade_delete_policies()

    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert len(statements) == 26
    assert statements[0] == "SET lock_timeout = '2s'"
    assert "ON DELETE SET NULL" in statements[2]
    assert "ADD COLUMN is_deleted" in statements[14]
    assert "ADD COLUMN total_conversations" in statements[24]
    assert statements[-1] == "RESET lock_timeout"


@pytest.mark.asyncio
async def test_cascade_policy_migration_skips_existing_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[*[(0, [])] * 13, *[(1, ["existing"])] * 6, (0, [])]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.fix_cascade_delete_policies()

    assert conn.execute_query.await_count == 20
    assert conn.execute_query.await_args.args[0] == "RESET lock_timeout"


@pytest.mark.asyncio
async def test_cascade_policy_migration_tolerates_failure_and_resets_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(0, []), RuntimeError("cannot alter"), (0, [])]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.fix_cascade_delete_policies()

    assert conn.execute_query.await_count == 3
    assert conn.execute_query.await_args.args[0] == "RESET lock_timeout"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("migration", "table", "column", "fragment", "uses_helper"),
    [
        (
            init_data.init_workflow_visibility_field,
            "workflows",
            "visibility",
            "ADD COLUMN visibility",
            False,
        ),
        (
            init_data.init_agent_streaming_config,
            "agents",
            "streaming_config",
            "ADD COLUMN streaming_config",
            True,
        ),
        (
            init_data.init_agent_context_compression_config,
            "agents",
            "context_compression_config",
            "ADD COLUMN context_compression_config",
            True,
        ),
        (
            init_data.init_message_manual_stop_field,
            "messages",
            "is_manually_stopped",
            "ADD COLUMN is_manually_stopped",
            False,
        ),
    ],
)
async def test_column_migrations_cover_absent_existing_and_create_paths(
    monkeypatch: pytest.MonkeyPatch,
    migration,
    table: str,
    column: str,
    fragment: str,
    uses_helper: bool,
) -> None:
    for tables, columns, expected_direct_calls in [
        ([], [], 1),
        ([table], [column], 2),
        ([table], [], 2 if uses_helper else 3),
    ]:
        conn = SimpleNamespace(
            execute_query=AsyncMock(
                side_effect=[(len(tables), tables), (len(columns), columns), (0, [])]
            )
        )
        helper = AsyncMock(return_value=(0, []))
        monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
        monkeypatch.setattr(init_data, "execute_startup_migration_query", helper)

        await migration()

        assert conn.execute_query.await_count == expected_direct_calls
        if tables and not columns:
            if uses_helper:
                assert fragment in helper.await_args.args[1]
            else:
                assert fragment in conn.execute_query.await_args.args[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "migration",
    [
        init_data.init_workflow_visibility_field,
        init_data.init_agent_streaming_config,
        init_data.init_agent_context_compression_config,
        init_data.init_message_manual_stop_field,
    ],
)
async def test_column_migrations_propagate_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
    migration,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(1, ["table"]), (0, []), RuntimeError("cannot add column")]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(
        init_data,
        "execute_startup_migration_query",
        AsyncMock(side_effect=RuntimeError("cannot add column")),
    )

    with pytest.raises(RuntimeError, match="cannot add column"):
        await migration()


@pytest.mark.asyncio
async def test_message_first_token_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = AsyncMock(return_value=(0, []))
    monkeypatch.setattr(init_data, "execute_startup_migration_query", helper)

    for dialect, tables, columns, expected_calls in [
        ("sqlite", [], [], 0),
        ("postgres", [], [], 0),
        ("postgres", ["messages"], ["first_token_ms"], 0),
        ("postgres", ["messages"], [], 1),
    ]:
        conn = SimpleNamespace(
            capabilities=SimpleNamespace(dialect=dialect),
            execute_query=AsyncMock(
                side_effect=[(len(tables), tables), (len(columns), columns)]
            ),
        )
        monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
        helper.reset_mock()

        await init_data.init_message_first_token_field()

        assert helper.await_count == expected_calls


@pytest.mark.asyncio
async def test_message_round_and_session_memory_migrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_message_round_fields()
    conn.execute_query.assert_awaited_once()

    conn.execute_query.reset_mock()
    conn.execute_query.return_value = (1, ["messages"])
    await init_data.init_message_round_fields()
    assert conn.execute_query.await_count == 7
    assert (
        "ADD COLUMN IF NOT EXISTS round_id"
        in conn.execute_query.await_args_list[1].args[0]
    )
    assert (
        "ADD COLUMN IF NOT EXISTS round_status" in conn.execute_query.await_args.args[0]
    )

    conn.execute_query.reset_mock()
    conn.execute_query.return_value = (1, ["conversation_session_memories"])
    await init_data.init_conversation_session_memory_table()
    conn.execute_query.assert_awaited_once()

    conn.execute_query.reset_mock()
    conn.execute_query.return_value = (0, [])
    await init_data.init_conversation_session_memory_table()
    assert conn.execute_query.await_count == 3
    assert (
        "CREATE TABLE IF NOT EXISTS conversation_session_memories"
        in conn.execute_query.await_args_list[1].args[0]
    )
    assert (
        "idx_conversation_session_memories_status_updated"
        in conn.execute_query.await_args.args[0]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dialect", "tables", "columns", "expected_calls"),
    [
        ("sqlite", [], [], 1),
        ("postgres", [], [], 1),
        ("sqlite", ["messages"], [{"name": "branch_parent_id"}], 6),
        ("sqlite", ["messages"], [(0, "other")], 7),
        ("postgres", ["messages"], [], 6),
    ],
)
async def test_message_branch_parent_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
    dialect: str,
    tables: list[str],
    columns: list[object],
    expected_calls: int,
) -> None:
    query_results = [(len(tables), tables)]
    if dialect == "sqlite" and tables:
        query_results.append((len(columns), columns))
    query_results.extend([(0, [])] * 5)
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect=dialect),
        execute_query=AsyncMock(side_effect=query_results),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_message_branch_parent_field()

    assert conn.execute_query.await_count == expected_calls
    if expected_calls > 1:
        statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
        assert any(
            "idx_messages_conversation_branch_parent" in sql for sql in statements
        )
        assert any("WITH active_canonical" in sql for sql in statements)
        assert any("WITH round_canonical" in sql for sql in statements)


@pytest.mark.asyncio
async def test_message_branch_parent_migration_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        execute_query=AsyncMock(
            side_effect=[(1, ["messages"]), RuntimeError("cannot add branch parent")]
        ),
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot add branch parent"):
        await init_data.init_message_branch_parent_field()


@pytest.mark.asyncio
async def test_agent_user_input_request_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = AsyncMock(return_value=(0, []))
    monkeypatch.setattr(init_data, "execute_startup_migration_query", helper)

    for tables, columns, expected_calls in [
        ([], [], 0),
        (["agents"], ["enable_user_input_request"], 0),
        (["agents"], [], 1),
    ]:
        conn = SimpleNamespace(
            execute_query=AsyncMock(
                side_effect=[(len(tables), tables), (len(columns), columns)]
            )
        )
        monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
        helper.reset_mock()

        await init_data.init_agent_user_input_request()

        assert helper.await_count == expected_calls

    conn = SimpleNamespace(
        execute_query=AsyncMock(side_effect=[(1, ["agents"]), (0, [])])
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    helper.side_effect = RuntimeError("cannot add user input flag")
    with pytest.raises(RuntimeError, match="cannot add user input flag"):
        await init_data.init_agent_user_input_request()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing", "expected_calls"),
    [
        (["sso_providers"], 1),
        ([], 8),
    ],
)
async def test_sso_tables_skip_existing_or_create_schema(
    monkeypatch: pytest.MonkeyPatch,
    existing: list[str],
    expected_calls: int,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(return_value=(len(existing), existing))
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_sso_tables()

    assert conn.execute_query.await_count == expected_calls
    if not existing:
        statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
        assert "CREATE TABLE IF NOT EXISTS sso_providers" in statements[1]
        assert "CREATE TABLE IF NOT EXISTS user_sso_connections" in statements[2]
        assert "CREATE TABLE IF NOT EXISTS sso_sessions" in statements[3]
        assert "idx_sso_sessions_expires_at" in statements[7]


@pytest.mark.asyncio
async def test_sso_tables_propagate_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(0, []), RuntimeError("cannot create sso")]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot create sso"):
        await init_data.init_sso_tables()


@pytest.mark.asyncio
async def test_storage_settings_migrate_only_legacy_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.site_setting import SiteSetting

    legacy = SimpleNamespace(category="audit", save=AsyncMock())
    current = SimpleNamespace(category="storage", save=AsyncMock())
    settings = {
        "audit_log_retention_days": legacy,
        "audit_log_archive_path": current,
    }

    def filter_setting(*, key: str) -> SimpleNamespace:
        return SimpleNamespace(first=AsyncMock(return_value=settings[key]))

    monkeypatch.setattr(SiteSetting, "filter", filter_setting)

    await init_data.migrate_storage_settings_category()

    assert legacy.category == "storage"
    legacy.save.assert_awaited_once_with()
    current.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_tables_existing_schema_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for column_info, expected_calls in [
        ([], 2),
        ([{"data_type": "character varying"}], 2),
        ([{"data_type": "uuid"}], 3),
    ]:
        conn = SimpleNamespace(
            execute_query=AsyncMock(
                side_effect=[
                    (1, ["memory_entities"]),
                    (len(column_info), column_info),
                    (0, []),
                ]
            )
        )
        monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

        await init_data.init_memory_tables()

        assert conn.execute_query.await_count == expected_calls
        if expected_calls == 3:
            assert (
                "ALTER COLUMN embedding_model_id TYPE VARCHAR"
                in conn.execute_query.await_args.args[0]
            )

    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(1, ["memory_entities"]), RuntimeError("cannot inspect")]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_memory_tables()


@pytest.mark.asyncio
async def test_memory_tables_create_entities_relations_and_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    await init_data.init_memory_tables()

    assert conn.execute_query.await_count == 8
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert "CREATE TABLE IF NOT EXISTS memory_entities" in statements[1]
    assert "idx_memory_entities_user_name" in statements[3]
    assert "CREATE TABLE IF NOT EXISTS memory_relations" in statements[4]
    assert "idx_memory_relations_user_type" in statements[7]


@pytest.mark.asyncio
async def test_agent_memory_and_media_field_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = AsyncMock(return_value=(0, []))
    monkeypatch.setattr(init_data, "execute_startup_migration_query", helper)

    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_agent_hide_tool_calls_field()
    helper.assert_not_awaited()

    conn.execute_query.return_value = (1, ["agents"])
    await init_data.init_agent_hide_tool_calls_field()
    assert "hide_tool_calls" in helper.await_args.args[1]

    helper.reset_mock()
    conn.execute_query.return_value = (1, ["enable_memory"])
    await init_data.init_agent_memory_fields()
    helper.assert_not_awaited()

    conn.execute_query.return_value = (0, [])
    await init_data.init_agent_memory_fields()
    assert helper.await_count == 2
    assert "enable_memory" in helper.await_args_list[0].args[1]
    assert "memory_config" in helper.await_args_list[1].args[1]

    helper.reset_mock()
    conn.execute_query.return_value = (0, [])
    await init_data.init_agent_media_generation_fields()
    helper.assert_not_awaited()

    conn.execute_query.return_value = (1, ["agents"])
    await init_data.init_agent_media_generation_fields()
    assert helper.await_count == 4
    statements = [awaited.args[1] for awaited in helper.await_args_list]
    assert "enable_image_generation" in statements[0]
    assert "image_generation_config" in statements[1]
    assert "enable_video_generation" in statements[2]
    assert "video_generation_config" in statements[3]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("migration", "table", "column", "fragment"),
    [
        (
            init_data.init_user_approval_status_field,
            "users",
            "approval_status",
            "ADD COLUMN approval_status",
        ),
        (
            init_data.init_totp_fields,
            "users",
            "totp_secret",
            "ADD COLUMN totp_secret",
        ),
        (
            init_data.init_agent_kb_search_mode,
            "agent_knowledge_bases",
            "search_mode",
            "ADD COLUMN IF NOT EXISTS search_mode",
        ),
    ],
)
async def test_additional_column_migrations_cover_absent_existing_and_create(
    monkeypatch: pytest.MonkeyPatch,
    migration,
    table: str,
    column: str,
    fragment: str,
) -> None:
    for tables, columns in [([], []), ([table], [column]), ([table], [])]:
        conn = SimpleNamespace(
            execute_query=AsyncMock(
                side_effect=[
                    (len(tables), tables),
                    (len(columns), columns),
                    (0, []),
                    (0, []),
                ]
            )
        )
        monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

        await migration()

        if tables and not columns:
            assert any(
                fragment in awaited.args[0]
                for awaited in conn.execute_query.await_args_list
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "migration",
    [init_data.init_user_approval_status_field, init_data.init_totp_fields],
)
async def test_additional_column_migrations_propagate_failure(
    monkeypatch: pytest.MonkeyPatch,
    migration,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[(1, ["table"]), (0, []), RuntimeError("cannot add field")]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="cannot add field"):
        await migration()


@pytest.mark.asyncio
async def test_password_expiration_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_password_expiration()
    conn.execute_query.assert_awaited_once()

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [
        (1, ["users"]),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
    ]
    await init_data.init_password_expiration()
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert len(statements) == 7
    assert "ADD COLUMN password_changed_at" in statements[2]
    assert "SET password_changed_at = created_at" in statements[3]
    assert "CREATE TABLE IF NOT EXISTS password_history" in statements[5]
    assert "idx_password_history_user_id" in statements[6]

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [
        (1, ["users"]),
        (1, ["password_changed_at"]),
        (1, ["password_history"]),
    ]
    await init_data.init_password_expiration()
    assert conn.execute_query.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_index", [2, 4])
async def test_password_expiration_migration_propagates_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    results: list[object] = [
        (1, ["users"]),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
    ]
    results[failure_index] = RuntimeError("password migration failed")
    conn = SimpleNamespace(execute_query=AsyncMock(side_effect=results))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)

    with pytest.raises(RuntimeError, match="password migration failed"):
        await init_data.init_password_expiration()


@pytest.mark.asyncio
async def test_chunk_status_migration_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(0, [])))
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_chunk_status()
    conn.execute_query.assert_awaited_once()

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [
        (1, ["document_chunks"]),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
        (0, []),
    ]
    await init_data.init_chunk_status()
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert len(statements) == 6
    assert "ADD COLUMN IF NOT EXISTS status" in statements[2]
    assert "ALTER COLUMN status SET DEFAULT 'pending'" in statements[3]
    assert "ADD COLUMN IF NOT EXISTS error_message" in statements[5]

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [
        (1, ["document_chunks"]),
        (1, ["status"]),
        (1, ["error_message"]),
    ]
    await init_data.init_chunk_status()
    assert conn.execute_query.await_count == 3


@pytest.mark.asyncio
async def test_embed_config_migration_handles_missing_existing_and_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute_query=AsyncMock(
            side_effect=[
                (0, []),
                (1, ["workflows"]),
                (1, ["embed_config"]),
            ]
        )
    )
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    await init_data.init_embed_config()
    assert conn.execute_query.await_count == 3

    conn.execute_query.reset_mock()
    conn.execute_query.side_effect = [
        (1, ["agents"]),
        (0, []),
        (0, []),
        (1, ["workflows"]),
        (0, []),
        (0, []),
    ]
    await init_data.init_embed_config()
    statements = [awaited.args[0] for awaited in conn.execute_query.await_args_list]
    assert any("ALTER TABLE agents" in statement for statement in statements)
    assert any("ALTER TABLE workflows" in statement for statement in statements)
