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
