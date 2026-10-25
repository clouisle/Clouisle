"""Idempotent cutover of configured SSO and builtin connections to integrations."""

import json

from tortoise.transactions import in_transaction

from app.integrations.credentials import encrypt_secret
from app.integrations.registry import (
    implicit_builtin_capabilities,
    integration_registry,
)


async def _tables(connection) -> set[str]:
    if connection.capabilities.dialect == "sqlite":
        rows = await connection.execute_query_dict(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        return {row["name"] for row in rows}
    rows = await connection.execute_query_dict(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    return {row["table_name"] for row in rows}


async def _columns(connection, table: str) -> set[str]:
    if connection.capabilities.dialect == "sqlite":
        rows = await connection.execute_query_dict(f'PRAGMA table_info("{table}")')
        return {row["name"] for row in rows}
    rows = await connection.execute_query_dict(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=$1",
        [table],
    )
    return {row["column_name"] for row in rows}


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


async def migrate_integration_schema() -> None:
    """Run before generate_schemas; preserve IDs and foreign-key relationships."""
    async with in_transaction() as connection:
        postgres = connection.capabilities.dialect != "sqlite"
        if postgres:
            await connection.execute_query("SELECT pg_advisory_xact_lock(72831041)")
            await connection.execute_query("SET LOCAL lock_timeout = '5s'")
        tables = await _tables(connection)
        if "sso_providers" in tables:
            if "integrations" in tables:
                raise RuntimeError(
                    "Both legacy SSO and integration tables exist; refusing ambiguous cutover"
                )
            await connection.execute_query(
                'ALTER TABLE "sso_providers" RENAME TO "integrations"'
            )
            tables.add("integrations")
        if "integrations" not in tables:
            return
        columns = await _columns(connection, "integrations")
        if "protocol" in columns:
            await connection.execute_query(
                'ALTER TABLE "integrations" RENAME COLUMN "protocol" TO "provider_type"'
            )
        json_type = "JSONB" if postgres else "JSON"
        additions = {
            "enabled_capabilities": f"{json_type} NOT NULL DEFAULT '[]'",
            "credentials": f"{json_type} NOT NULL DEFAULT '{{}}'",
            "login_config": f"{json_type} NOT NULL DEFAULT '{{}}'",
        }
        for column, definition in additions.items():
            if column not in columns:
                await connection.execute_query(
                    f'ALTER TABLE "integrations" ADD COLUMN "{column}" {definition}'
                )
        if "allow_signup" in columns:
            rows = await connection.execute_query_dict('SELECT * FROM "integrations"')
            for row in rows:
                provider_type = row["provider_type"].lower()
                definition = integration_registry.get(provider_type)
                config = _json(row["config"])
                credentials = _json(row["credentials"])
                for field in definition.secret_fields:
                    if field in config:
                        value = config.pop(field)
                        if value:
                            credentials[field] = encrypt_secret(str(value))
                login_config = {
                    "allow_signup": bool(row["allow_signup"]),
                    "require_approval": bool(row["require_approval"]),
                    "default_role_id": str(row["default_role_id"])
                    if row["default_role_id"]
                    else None,
                }
                placeholders = (
                    [f"${index}" for index in range(1, 7)] if postgres else ["?"] * 6
                )
                await connection.execute_query(
                    'UPDATE "integrations" SET provider_type='
                    + placeholders[0]
                    + ", config="
                    + placeholders[1]
                    + ", credentials="
                    + placeholders[2]
                    + ", login_config="
                    + placeholders[3]
                    + ", enabled_capabilities="
                    + placeholders[4]
                    + " WHERE id="
                    + placeholders[5],
                    [
                        provider_type,
                        json.dumps(config),
                        json.dumps(credentials),
                        json.dumps(login_config),
                        json.dumps(["user_login"]),
                        row["id"],
                    ],
                )
            for column in ("allow_signup", "require_approval", "default_role_id"):
                await connection.execute_query(
                    f'ALTER TABLE "integrations" DROP COLUMN "{column}"'
                )
        for table in ("sso_sessions", "user_sso_connections"):
            if table in tables and "provider_id" in await _columns(connection, table):
                await connection.execute_query(
                    f'ALTER TABLE "{table}" RENAME COLUMN "provider_id" TO "integration_id"'
                )


BUILTIN_DEFAULTS = {
    "email": {
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_encryption": "tls",
        "smtp_username": "",
        "email_from_name": "Clouisle",
        "email_from_address": "",
    },
    "webhook": {
        "webhook_url": "",
        "webhook_method": "POST",
        "webhook_body_template": '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
    },
    "feishu": {"app_id": "", "department_ids": []},
    "wechat": {},
}


async def initialize_integrations() -> None:
    """Seed builtin instances once and remove their obsolete setting keys atomically."""
    from app.models.integration import Integration
    from app.models.site_setting import SiteSetting

    from app.models.wechat_knowledge import WeChatKnowledgeBinding

    async with in_transaction() as connection:
        if connection.capabilities.dialect != "sqlite":
            await connection.execute_query("SELECT pg_advisory_xact_lock(72831041)")
        settings = {
            setting.key: SiteSetting._convert_value(setting.value, setting.value_type)
            for setting in await SiteSetting.all().using_db(connection)
        }
        for provider_type, defaults in BUILTIN_DEFAULTS.items():
            definition = integration_registry.get(provider_type)
            if provider_type == "feishu":
                config = {
                    "app_id": settings.get("feishu_app_id", ""),
                    "department_ids": settings.get("feishu_department_scope", []),
                }
                credentials = {}
                if settings.get("feishu_app_secret_encrypted"):
                    credentials["app_secret"] = settings["feishu_app_secret_encrypted"]
                elif settings.get("feishu_app_secret"):
                    credentials["app_secret"] = encrypt_secret(
                        str(settings["feishu_app_secret"])
                    )
                enabled = bool(config["app_id"] and credentials)
                keys = [
                    "feishu_app_id",
                    "feishu_department_scope",
                    "feishu_app_secret_encrypted",
                    "feishu_app_secret",
                ]
            elif provider_type == "wechat":
                config, credentials, keys = {}, {}, []
                enabled = True
            else:
                config = {
                    key: settings.get(key, value) for key, value in defaults.items()
                }
                credentials = {}
                for field in definition.secret_fields:
                    value = settings.get(field)
                    if value:
                        credentials[field] = encrypt_secret(
                            json.dumps(value) if isinstance(value, dict) else str(value)
                        )
                enabled_key = (
                    "smtp_enabled" if provider_type == "email" else "webhook_enabled"
                )
                enabled = bool(settings.get(enabled_key, False))
                keys = [*defaults, *definition.secret_fields, enabled_key]
            existing = (
                await Integration.filter(provider_type=provider_type)
                .using_db(connection)
                .first()
            )
            if existing is None:
                # A login provider may already use the builtin's display slug.
                name = provider_type
                suffix = 0
                while await Integration.filter(name=name).using_db(connection).exists():
                    suffix += 1
                    name = f"builtin-{provider_type}-{suffix}"
                capabilities = (
                    implicit_builtin_capabilities(definition) if enabled else []
                )
                if provider_type == "wechat":
                    # Preserve existing active uses once; fresh installations
                    # start with both functions off. Personal tokens stay private.
                    purposes = set(
                        await WeChatKnowledgeBinding.filter(status="connected")
                        .exclude(token="")
                        .using_db(connection)
                        .values_list("purpose", flat=True)
                    )
                    capabilities = [
                        capability
                        for purpose, capability in (
                            ("agent", "agent_chat"),
                            ("knowledge_collection", "knowledge_collection"),
                        )
                        if purpose in purposes
                    ]
                await Integration.create(
                    name=name,
                    provider_type=provider_type,
                    display_name=definition.display_name,
                    is_enabled=enabled,
                    enabled_capabilities=capabilities,
                    config=config,
                    credentials=credentials,
                    using_db=connection,
                )
            if provider_type != "feishu" or existing is None:
                await SiteSetting.filter(key__in=keys).using_db(connection).delete()
        await (
            SiteSetting.filter(category="sso")
            .using_db(connection)
            .update(category="integration")
        )


async def migrate_integration_permissions() -> None:
    """Preserve each role's management domain instead of granting broader access."""
    from app.models.user import Permission, Role
    from app.models.site_setting import SiteSetting

    mappings = {
        "admin:sso:read": "admin:integrations:login:read",
        "admin:sso:update": "admin:integrations:login:update",
        "admin:settings:read": "admin:integrations:settings:read",
        "admin:settings:update": "admin:integrations:settings:update",
    }
    async with in_transaction() as connection:
        if connection.capabilities.dialect != "sqlite":
            await connection.execute_query("SELECT pg_advisory_xact_lock(72831041)")
        marker_key = "integration_permission_migration_completed"
        if await SiteSetting.filter(key=marker_key).using_db(connection).exists():
            return
        for source, target in mappings.items():
            old = await Permission.filter(code=source).using_db(connection).first()
            if old is None:
                continue
            new, _ = await Permission.get_or_create(
                code=target,
                defaults={
                    "scope": "admin",
                    "description": "Manage integration capabilities",
                    "is_system": True,
                },
                using_db=connection,
            )
            roles = await Role.filter(permissions__id=old.id).using_db(connection)
            for role in roles:
                await role.permissions.add(new, using_db=connection)
            if source.startswith("admin:sso:"):
                for role in roles:
                    await role.permissions.remove(old, using_db=connection)
                await old.delete(using_db=connection)
        await SiteSetting.create(
            key=marker_key,
            value="true",
            value_type="bool",
            category="integration",
            is_public=False,
            using_db=connection,
        )
