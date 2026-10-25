from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import sso_link_migration as migration


class MigrationConnection:
    def __init__(self, dialect, rows, tables):
        self.capabilities = SimpleNamespace(dialect=dialect)
        self.rows = rows
        self.tables = tables
        self.queries = []

    async def execute_query(self, query):
        self.queries.append(query)

    async def execute_query_dict(self, query):
        self.queries.append(query)
        if "table_info" in query or "information_schema" in query:
            return self.rows
        return self.tables


@pytest.mark.asyncio
async def test_migration_skips_absent_link_table_and_absent_session_table(monkeypatch):
    connection = MigrationConnection("sqlite", [], [])

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(migration.Tortoise, "get_connection", lambda _: connection)

    await migration.migrate_sso_link_sessions()

    assert connection.queries == [
        'PRAGMA table_info("user_sso_connections")',
        'PRAGMA table_info("sso_sessions")',
    ]


@pytest.mark.asyncio
async def test_migration_adds_provenance_without_audit_table(monkeypatch):
    connection = MigrationConnection(
        "sqlite",
        [{"name": "id"}, {"name": "integration_id"}],
        [],
    )

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(migration.Tortoise, "get_connection", lambda _: connection)

    await migration.migrate_sso_link_sessions()

    assert any(
        'ADD COLUMN "self_service_linked"' in query for query in connection.queries
    )
    assert not any(query.startswith("UPDATE") for query in connection.queries)


@pytest.mark.asyncio
async def test_postgres_migration_returns_when_session_table_is_absent(monkeypatch):
    connection = MigrationConnection(
        "postgres", [{"name": "self_service_linked"}], [{"name": None}]
    )

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(migration.Tortoise, "get_connection", lambda _: connection)

    await migration.migrate_sso_link_sessions()

    assert any("pg_advisory_xact_lock" in query for query in connection.queries)
    assert not any("ADD COLUMN" in query for query in connection.queries)


@pytest.mark.asyncio
async def test_migration_backfills_when_audit_table_exists(monkeypatch):
    connection = MigrationConnection(
        "sqlite",
        [{"name": "id"}, {"name": "integration_id"}],
        [{"name": "audit_logs"}],
    )

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(migration.Tortoise, "get_connection", lambda _: connection)

    await migration.migrate_sso_link_sessions()

    assert any(query.startswith("UPDATE") for query in connection.queries)


@pytest.mark.asyncio
async def test_postgres_migration_updates_sessions_when_table_exists(monkeypatch):
    connection = MigrationConnection(
        "postgres", [{"name": "self_service_linked"}], [{"name": "sso_sessions"}]
    )
    execute_migration = AsyncMock()

    @asynccontextmanager
    async def transaction():
        yield connection

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(migration.Tortoise, "get_connection", lambda _: connection)
    monkeypatch.setattr(migration, "execute_startup_migration_query", execute_migration)

    await migration.migrate_sso_link_sessions()

    assert execute_migration.await_count == 2
    assert all(
        "ADD COLUMN IF NOT EXISTS" in call.args[1]
        for call in execute_migration.await_args_list
    )
