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
    (
        "ck_connection_grants_entrypoint",
        "connection_grants",
        "length(btrim(entrypoint_id)) > 0",
    ),
    (
        "ck_connection_grants_operations",
        "connection_grants",
        "jsonb_typeof(allowed_operations::jsonb) = 'array' "
        "AND jsonb_array_length(allowed_operations::jsonb) > 0",
    ),
)


async def apply_tool_connection_constraints() -> None:
    """Enforce connection scope/owner/team invariants in PostgreSQL.

    Must run AFTER ``Tortoise.generate_schemas()`` because it alters the new
    ``tool_connections`` / ``connection_grants`` tables. Existing installations
    and rolling upgrades converge on the same constraints; SQLite tests rely on
    ``model.validate_invariants()`` instead.
    """
    connection = Tortoise.get_connection("default")
    if connection.capabilities.dialect != "postgres":
        return

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
