"""Startup API-key identity migration (PostgreSQL before generate_schemas).

The migration adds nullable columns to existing tables and then creates the
Tortoise-equivalent index. On a brand-new database the tables do not exist yet
and ``CREATE INDEX`` must be skipped: PostgreSQL would raise ``relation does
not exist`` before ``generate_schemas()`` could create the table and its Meta
index. These tests pin both the fresh-install and existing-install paths.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core import api_key_approval_migration as module


class _Connection:
    def __init__(self, dialect: str, tables: tuple[str, ...] = ()) -> None:
        self.capabilities = SimpleNamespace(dialect=dialect)
        self.tables = tables
        self.queries: list[str] = []

    async def execute_query(self, query: str):
        self.queries.append(query)
        return len(self.tables), [(table,) for table in self.tables]


@pytest.fixture
def execute(monkeypatch):
    statements: list[str] = []

    async def fake_execute(_connection, query: str):
        statements.append(query)
        return None

    monkeypatch.setattr(module, "execute_startup_migration_query", fake_execute)
    return statements


def _install(monkeypatch, connection: _Connection) -> None:
    monkeypatch.setattr(module.Tortoise, "get_connection", lambda _name: connection)


@pytest.mark.asyncio
async def test_sqlite_skips_every_statement(monkeypatch, execute):
    connection = _Connection("sqlite", ("agent_runs", "tool_executions"))
    _install(monkeypatch, connection)

    await module.migrate_api_key_approval_schema()

    assert execute == []
    assert connection.queries == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tables",
    [
        (),
        # A half-initialized database with only the run table must not attempt
        # the index on the missing execution table either.
        ("agent_runs",),
    ],
)
async def test_fresh_database_skips_the_index(
    monkeypatch, execute, tables: tuple[str, ...]
):
    connection = _Connection("postgres", tables)
    _install(monkeypatch, connection)

    await module.migrate_api_key_approval_schema()

    assert len(execute) == 2
    assert all("ADD COLUMN IF NOT EXISTS api_key_id UUID" in sql for sql in execute)
    assert not any("CREATE INDEX" in sql for sql in execute)
    # Existence is checked through the canonical table probe, not ORM reads.
    assert len(connection.queries) == 1


@pytest.mark.asyncio
async def test_existing_database_adds_columns_then_the_meta_index(monkeypatch, execute):
    connection = _Connection("postgres", ("agent_runs", "tool_executions"))
    _install(monkeypatch, connection)

    await module.migrate_api_key_approval_schema()

    assert len(execute) == 3
    assert "agent_runs" in execute[0]
    assert "tool_executions" in execute[1]
    assert execute[2].strip().startswith("CREATE INDEX IF NOT EXISTS")
    # The name must equal Tortoise's Meta index name for
    # ("api_key_id", "created_at") so generate_schemas cannot create a twin.
    assert "idx_tool_execut_api_key_2bd9ba" in execute[2]
    assert "ON tool_executions (api_key_id, created_at)" in execute[2]


@pytest.mark.asyncio
async def test_migration_is_idempotent_by_statement_contract(monkeypatch, execute):
    connection = _Connection("postgres", ("agent_runs", "tool_executions"))
    _install(monkeypatch, connection)

    await module.migrate_api_key_approval_schema()
    await module.migrate_api_key_approval_schema()

    add_statements = [sql for sql in execute if "ADD COLUMN" in sql]
    index_statements = [sql for sql in execute if "CREATE INDEX" in sql]
    assert len(add_statements) == 4
    assert len(index_statements) == 2
    assert all("IF NOT EXISTS" in sql for sql in add_statements + index_statements)
