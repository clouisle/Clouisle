"""Add actor ownership and completion state to pending SSO account links."""

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core.init_data import execute_startup_migration_query


async def _migrate_self_service_links() -> None:
    """Backfill prior manual links once, atomically with the provenance column."""
    async with in_transaction() as connection:
        sqlite = connection.capabilities.dialect == "sqlite"
        if not sqlite:
            await connection.execute_query("SET LOCAL lock_timeout = '2s'")
            await connection.execute_query(
                "SELECT pg_advisory_xact_lock(hashtext('sso-self-service-link-schema'))"
            )
        rows = await connection.execute_query_dict(
            'PRAGMA table_info("user_sso_connections")'
            if sqlite
            else "SELECT column_name AS name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='user_sso_connections'"
        )
        if not rows or any(row["name"] == "self_service_linked" for row in rows):
            return
        await connection.execute_query(
            'ALTER TABLE "user_sso_connections" '
            'ADD COLUMN "self_service_linked" BOOLEAN NOT NULL DEFAULT FALSE'
        )
        tables = await connection.execute_query_dict(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
            if sqlite
            else "SELECT to_regclass('audit_logs') AS name"
        )
        if tables and tables[0]["name"]:
            await connection.execute_query(
                'UPDATE "user_sso_connections" SET "self_service_linked" = TRUE '
                'WHERE EXISTS (SELECT 1 FROM "integrations" i, "audit_logs" a '
                'WHERE i.id = "user_sso_connections".integration_id '
                "AND i.provider_type = 'feishu' "
                'AND a.user_id = "user_sso_connections".user_id '
                "AND a.action = 'link_sso' AND a.status = 'success' "
                "AND a.resource_name = i.name "
                'AND a.created_at >= "user_sso_connections".first_login)'
            )


async def migrate_sso_link_sessions() -> None:
    """Ensure optional account-link fields exist on upgraded databases."""
    connection = Tortoise.get_connection("default")
    dialect = connection.capabilities.dialect
    await _migrate_self_service_links()

    if dialect == "sqlite":
        rows = await connection.execute_query_dict('PRAGMA table_info("sso_sessions")')
        if not rows:
            return
        columns = {row["name"] for row in rows}
        if "link_user_id" not in columns:
            await connection.execute_query(
                'ALTER TABLE "sso_sessions" ADD COLUMN "link_user_id" UUID NULL '
                'REFERENCES "users"("id") ON DELETE CASCADE'
            )
        if "link_user_info" not in columns:
            await connection.execute_query(
                'ALTER TABLE "sso_sessions" ADD COLUMN "link_user_info" JSON NULL'
            )
    else:
        tables = await connection.execute_query_dict(
            "SELECT to_regclass('sso_sessions') AS name"
        )
        if not tables or tables[0]["name"] is None:
            return
        await execute_startup_migration_query(
            connection,
            'ALTER TABLE IF EXISTS "sso_sessions" '
            'ADD COLUMN IF NOT EXISTS "link_user_id" UUID NULL '
            'REFERENCES "users"("id") ON DELETE CASCADE',
        )
        await execute_startup_migration_query(
            connection,
            'ALTER TABLE IF EXISTS "sso_sessions" '
            'ADD COLUMN IF NOT EXISTS "link_user_info" JSONB NULL',
        )
