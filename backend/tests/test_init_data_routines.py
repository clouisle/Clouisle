from types import SimpleNamespace
from unittest.mock import AsyncMock

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


@pytest.mark.parametrize(
    ("public_count", "expected_queries"),
    [(2, 2), (0, 1)],
    ids=["normalizes-legacy-values", "already-normalized"],
)
@pytest.mark.asyncio
async def test_agent_visibility_normalization_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    public_count: int,
    expected_queries: int,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(1, ["agents"])))
    migration = AsyncMock(side_effect=[(1, [{"public_count": public_count}]), (1, [])])
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    await init_data.init_agent_visibility_values()

    assert migration.await_count == expected_queries
    if public_count:
        assert "SET visibility = 'team'" in migration.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_agent_visibility_normalization_propagates_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(execute_query=AsyncMock(return_value=(1, ["agents"])))
    error = RuntimeError("database unavailable")
    migration = AsyncMock(side_effect=error)
    monkeypatch.setattr(init_data.Tortoise, "get_connection", lambda _name: conn)
    monkeypatch.setattr(init_data, "execute_startup_migration_query", migration)

    with pytest.raises(RuntimeError, match="database unavailable") as exc_info:
        await init_data.init_agent_visibility_values()

    assert exc_info.value is error
    migration.assert_awaited_once()


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
