"""Add the credential-binding columns before history is served (PostgreSQL).

Records written before these columns existed become part of their owner's own
history: the migration does not try to reconstruct which API key may have
created an old conversation or run. `api_key_id` therefore stays NULL for every
pre-existing row, and the record is served as the user's own history - exactly
as it was before credentials became part of the access rule.

The migration only adds columns. It never rewrites, splits or deletes a row,
and it is safe to run on every startup.

`api_key_origin_unknown` is added by the same statement because the access
filters read it. It is not set by this migration: it exists so a database that
already ran the earlier, evidence-based classification keeps those rows out of
personal history. No new quarantine state is produced.
"""

from tortoise.transactions import in_transaction


async def migrate_execution_history_schema() -> None:
    """Add the two history columns once, atomically, before serving history."""
    async with in_transaction() as connection:
        if connection.capabilities.dialect == "sqlite":
            return  # SQLite test databases use generate_schemas().
        await connection.execute_query(
            "SELECT pg_advisory_xact_lock(hashtext('execution-history-schema'))"
        )
        await connection.execute_query("SET LOCAL lock_timeout = '5s'")
        await connection.execute_query("SET LOCAL statement_timeout = '120s'")
        from app.core.integration_migration import _columns, _tables

        tables = await _tables(connection)
        for table in ("conversations", "workflow_runs"):
            if table not in tables or "api_key_origin_unknown" in await _columns(
                connection, table
            ):
                continue
            await connection.execute_query(
                f"ALTER TABLE {table} ADD COLUMN api_key_id UUID, "
                "ADD COLUMN api_key_origin_unknown BOOLEAN NOT NULL DEFAULT FALSE"
            )
