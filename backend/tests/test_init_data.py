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
    assert "'user-owner', 'role-admin'" in statements[3]
    assert "'user-member', 'role-member'" in statements[4]
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
