"""Add the per-workflow access-policy columns (PostgreSQL).

An empty `access_policy` keeps the legacy rules, so existing rows need no
backfill: the columns default to "inherit" and the migration only adds them.
It is safe to run on every startup.
"""

from tortoise.transactions import in_transaction


async def migrate_workflow_access_policy_columns() -> None:
    """Add the policy columns once, atomically, before serving workflows."""
    async with in_transaction() as connection:
        if connection.capabilities.dialect == "sqlite":
            return  # SQLite test databases use generate_schemas().
        await connection.execute_query(
            "SELECT pg_advisory_xact_lock(hashtext('workflow-access-policy'))"
        )
        await connection.execute_query("SET LOCAL lock_timeout = '5s'")
        from app.core.integration_migration import _columns, _tables

        if "workflows" not in await _tables(connection):
            return
        columns = await _columns(connection, "workflows")
        if "access_policy" not in columns:
            await connection.execute_query(
                "ALTER TABLE workflows ADD COLUMN access_policy JSONB "
                "NOT NULL DEFAULT '{}'::jsonb"
            )
        if "access_policy_version" not in columns:
            await connection.execute_query(
                "ALTER TABLE workflows ADD COLUMN access_policy_version "
                "INTEGER NOT NULL DEFAULT 1"
            )
