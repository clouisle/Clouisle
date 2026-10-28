"""Add explicit tool identity and approval policy columns before ORM reads."""

from tortoise import Tortoise

from app.core.init_data import execute_startup_migration_query


async def migrate_tool_policy_schema() -> None:
    connection = Tortoise.get_connection("default")
    await execute_startup_migration_query(
        connection,
        """
        ALTER TABLE IF EXISTS tools
            ADD COLUMN IF NOT EXISTS identity_policy VARCHAR(20) NOT NULL DEFAULT 'none',
            ADD COLUMN IF NOT EXISTS connection_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS approval_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS definition_version INTEGER NOT NULL DEFAULT 1
        """,
    )
    # Older schemas inferred VARCHAR(12) before IM origins were introduced.
    # Widening is backward-compatible and preserves existing execution rows.
    await execute_startup_migration_query(
        connection,
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'tool_executions'
                  AND column_name = 'entrypoint'
                  AND character_maximum_length < 32
            ) THEN
                ALTER TABLE tool_executions ALTER COLUMN entrypoint TYPE VARCHAR(32);
            END IF;
        END $$;
        """,
    )


# PostgreSQL cannot express these invariants in Tortoise Meta, so they are
# added after generate_schemas() has created the tables. Each statement is
# idempotent (checked against pg_constraint) and skipped on SQLite.
_TOOL_CONNECTION_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "ck_tool_connections_scope_identity",
        "tool_connections",
        "(scope = 'user' AND owner_user_id IS NOT NULL AND team_id IS NOT NULL) OR "
        "(scope = 'team' AND owner_user_id IS NULL AND team_id IS NOT NULL) OR "
        "(scope = 'site' AND owner_user_id IS NULL AND team_id IS NULL)",
    ),
    (
        "ck_tool_connections_service_identity",
        "tool_connections",
        "(tool_id IS NOT NULL) <> (builtin_tool_key IS NOT NULL)",
    ),
    (
        "ck_tool_connections_default_state",
        "tool_connections",
        "(is_default AND default_slot IS NOT NULL) OR "
        "(NOT is_default AND default_slot IS NULL)",
    ),
)


async def apply_tool_connection_constraints() -> None:
    """Enforce connection scope/owner/team invariants in PostgreSQL."""
    connection = Tortoise.get_connection("default")
    if connection.capabilities.dialect != "postgres":
        return

    # One statement per call: the asyncpg client uses the prepared-statement
    # path for DDL and rejects multi-command strings.
    await execute_startup_migration_query(
        connection, "DROP TABLE IF EXISTS connection_grants CASCADE"
    )
    await execute_startup_migration_query(
        connection,
        "ALTER TABLE IF EXISTS tool_executions DROP COLUMN IF EXISTS grant_id",
    )
    await execute_startup_migration_query(
        connection,
        "ALTER TABLE IF EXISTS tool_executions DROP COLUMN IF EXISTS grant_version",
    )

    for constraint, table, predicate in _TOOL_CONNECTION_CONSTRAINTS:
        await execute_startup_migration_query(
            connection,
            f"""
            DO $$
            BEGIN
                IF to_regclass('{table}') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_constraint
                       WHERE conname = '{constraint}'
                         AND conrelid = to_regclass('{table}')
                   )
                THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT {constraint} CHECK ({predicate});
                END IF;
            END
            $$;
            """,
        )
