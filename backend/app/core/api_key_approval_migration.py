"""Add the API-key identity columns used by tool approval bindings.

Existing installations already have ``agent_runs`` and ``tool_executions``;
``generate_schemas()`` never alters them. Both columns are nullable so the
migration is safe while an old pod still runs (rolling deploy): a NULL key id
means "not created by an API key" and the approval service falls back to the
legacy ``api_key`` entrypoint id for rows persisted before this column existed.
"""

from __future__ import annotations

from tortoise import Tortoise

from app.core.init_data import execute_startup_migration_query


async def migrate_api_key_approval_schema() -> None:
    """Add ``agent_runs.api_key_id`` / ``tool_executions.api_key_id`` once."""
    connection = Tortoise.get_connection("default")
    if connection.capabilities.dialect == "sqlite":
        return
    await execute_startup_migration_query(
        connection,
        """
        ALTER TABLE IF EXISTS agent_runs
            ADD COLUMN IF NOT EXISTS api_key_id UUID
        """,
    )
    await execute_startup_migration_query(
        connection,
        """
        ALTER TABLE IF EXISTS tool_executions
            ADD COLUMN IF NOT EXISTS api_key_id UUID
        """,
    )
    # This runs before ``generate_schemas()``. On a brand-new database the
    # table does not exist yet, and PostgreSQL rejects even
    # ``CREATE INDEX IF NOT EXISTS ... ON tool_executions`` with
    # ``relation does not exist``. ``generate_schemas()`` then creates the
    # table together with the identical Meta index, so only existing
    # installations need the explicit statement here.
    from app.core.tool_approval_caller_migration import existing_tables

    if "tool_executions" not in await existing_tables(connection, ("tool_executions",)):
        return
    # Name matches the Tortoise Meta index so a fresh schema does not end up
    # with two identical indexes.
    await execute_startup_migration_query(
        connection,
        """
        CREATE INDEX IF NOT EXISTS idx_tool_execut_api_key_2bd9ba
            ON tool_executions (api_key_id, created_at)
        """,
    )


__all__ = ["migrate_api_key_approval_schema"]
