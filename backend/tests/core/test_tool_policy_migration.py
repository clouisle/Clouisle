"""Post-schema CHECK constraints for tool connections (PostgreSQL only)."""

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
