"""Post-schema CHECK constraints for tool connections and grants."""

import asyncio
from types import SimpleNamespace

from app.core import tool_policy_migration as module


def test_connection_constraints_skip_sqlite(monkeypatch):
    executed: list[str] = []

    async def fake_execute(connection, query):
        executed.append(query)

    monkeypatch.setattr(module, "execute_startup_migration_query", fake_execute)
    monkeypatch.setattr(
        module.Tortoise,
        "get_connection",
        lambda name: SimpleNamespace(capabilities=SimpleNamespace(dialect="sqlite")),
    )

    asyncio.run(module.apply_tool_connection_constraints())

    assert executed == []


def test_connection_constraints_are_idempotent_postgres_ddl(monkeypatch):
    executed: list[str] = []
    connection = SimpleNamespace(capabilities=SimpleNamespace(dialect="postgres"))

    async def fake_execute(target, query):
        assert target is connection
        executed.append(" ".join(query.split()))

    monkeypatch.setattr(module, "execute_startup_migration_query", fake_execute)
    monkeypatch.setattr(module.Tortoise, "get_connection", lambda name: connection)

    asyncio.run(module.apply_tool_connection_constraints())

    assert len(executed) == 5
    combined = "\n".join(executed)
    for constraint in (
        "ck_tool_connections_scope_identity",
        "ck_tool_connections_service_identity",
        "ck_tool_connections_default_state",
        "ck_connection_grants_entrypoint",
        "ck_connection_grants_operations",
    ):
        assert constraint in combined
        assert combined.count(f"ADD CONSTRAINT {constraint}") == 1
    # Idempotency guard must tolerate missing tables and existing constraints.
    assert combined.count("to_regclass('tool_connections')") >= 3
    assert combined.count("SELECT 1 FROM pg_constraint") == 5
    assert (
        "scope = 'user' AND owner_user_id IS NOT NULL AND team_id IS NOT NULL"
        in combined
    )
    assert "scope = 'site' AND owner_user_id IS NULL AND team_id IS NULL" in combined
    assert "jsonb_array_length(allowed_operations::jsonb) > 0" in combined
