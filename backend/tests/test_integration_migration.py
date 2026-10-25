"""Database-backed regressions for identity and credential preservation at cutover."""

import json
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.core.integration_migration import (
    initialize_integrations,
    migrate_integration_permissions,
    migrate_integration_schema,
)
from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.models.integration import Integration
from app.models.site_setting import SiteSetting
from app.models.sso_session import SSOSession
from app.models.user import Permission, Role, User
from app.models.user_sso_connection import UserSSOConnection


@pytest_asyncio.fixture
async def database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    await Tortoise.generate_schemas()
    from app.models.integration import Integration

    await Integration.create(
        name="wechat",
        provider_type="wechat",
        display_name="WeChat iLink",
        enabled_capabilities=[],
    )
    try:
        yield Tortoise.get_connection("default")
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_legacy_identity_connections_and_authorization_sessions_survive_cutover(
    database,
):
    user = await User.create(
        username="migration-user", email="user@example.com", hashed_password=""
    )
    integration = await Integration.create(
        name="company",
        provider_type="oidc",
        display_name="Company",
        config={"client_id": "client", "client_secret": "legacy-secret"},
        attribute_mapping={"username": "name"},
    )
    connection = await UserSSOConnection.create(
        user=user,
        integration=integration,
        provider_user_id="external-subject",
    )
    session = await SSOSession.create(
        integration=integration,
        session_id="pending-authorization",
        code_verifier="unchanged-verifier",
        redirect_url="/app",
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    for table in ("sso_sessions", "user_sso_connections"):
        await database.execute_query(
            f'ALTER TABLE "{table}" RENAME COLUMN integration_id TO provider_id'
        )
    await database.execute_query(
        "ALTER TABLE integrations RENAME COLUMN provider_type TO protocol"
    )
    for field in ("enabled_capabilities", "credentials", "login_config"):
        await database.execute_query(f'ALTER TABLE integrations DROP COLUMN "{field}"')
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN allow_signup BOOL NOT NULL DEFAULT 0"
    )
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN require_approval BOOL NOT NULL DEFAULT 1"
    )
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN default_role_id VARCHAR(36)"
    )
    await database.execute_query("ALTER TABLE integrations RENAME TO sso_providers")

    await migrate_integration_schema()
    await migrate_integration_schema()

    migrated = await Integration.get(id=integration.id)
    assert migrated.login_config == {
        "allow_signup": False,
        "require_approval": True,
        "default_role_id": None,
    }
    assert migrated.config == {"client_id": "client"}
    assert decrypt_secret(migrated.credentials["client_secret"]) == "legacy-secret"
    assert migrated.enabled_capabilities == ["user_login"]
    assert migrated.attribute_mapping == {"username": "name"}
    assert (
        await UserSSOConnection.get(id=connection.id)
    ).integration_id == integration.id
    restored = await SSOSession.get(id=session.id)
    assert restored.integration_id == integration.id
    assert restored.code_verifier == "unchanged-verifier"
    assert restored.redirect_url == "/app"
    assert (await User.get(id=user.id)).hashed_password == ""


@pytest.mark.asyncio
async def test_builtin_settings_move_once_without_overwriting_later_edits(database):
    await SiteSetting.set_value("smtp_enabled", True, value_type="bool")
    await SiteSetting.set_value("smtp_password", "smtp-secret")
    await SiteSetting.set_value("smtp_host", "smtp.example.com")
    await SiteSetting.set_value(
        "webhook_headers", {"Authorization": "Bearer header-secret"}, value_type="json"
    )
    await SiteSetting.set_value("feishu_app_id", "cli-existing")
    await SiteSetting.set_value(
        "feishu_app_secret_encrypted", encrypt_secret("feishu-secret")
    )
    await SiteSetting.set_value(
        "feishu_department_scope", ["department"], value_type="json"
    )
    await SiteSetting.set_value(
        "sso_match_by_email", False, value_type="bool", category="sso"
    )
    await initialize_integrations()

    email = await Integration.get(provider_type="email")
    assert email.is_enabled
    assert decrypt_secret(email.credentials["smtp_password"]) == "smtp-secret"
    assert "smtp_password" not in email.config
    webhook = await Integration.get(provider_type="webhook")
    assert json.loads(decrypt_secret(webhook.credentials["webhook_headers"])) == {
        "Authorization": "Bearer header-secret"
    }
    feishu = await Integration.get(provider_type="feishu")
    assert feishu.config == {"app_id": "cli-existing", "department_ids": ["department"]}
    assert decrypt_secret(feishu.credentials["app_secret"]) == "feishu-secret"
    assert feishu.enabled_capabilities == ["directory_sync"]
    email.config = {**email.config, "smtp_host": "new.example.com"}
    await email.save()
    await initialize_integrations()
    assert (await Integration.get(id=email.id)).config["smtp_host"] == "new.example.com"
    wechat = await Integration.get(provider_type="wechat")
    assert wechat.enabled_capabilities == []
    assert not await SiteSetting.filter(key="smtp_password").exists()
    assert await SiteSetting.get_value("sso_match_by_email") is False


@pytest.mark.asyncio
async def test_plaintext_feishu_secret_migrates_once_without_overwriting(database):
    await SiteSetting.set_value("feishu_app_id", "cli-legacy")
    await SiteSetting.set_value("feishu_app_secret", "plain-feishu-secret")

    await initialize_integrations()

    feishu = await Integration.get(provider_type="feishu")
    assert decrypt_secret(feishu.credentials["app_secret"]) == "plain-feishu-secret"
    assert not await SiteSetting.filter(key="feishu_app_secret").exists()

    await initialize_integrations()
    migrated = await Integration.get(id=feishu.id)
    assert migrated.credentials == feishu.credentials


@pytest.mark.asyncio
async def test_encrypted_feishu_secret_takes_precedence_over_plaintext(database):
    await SiteSetting.set_value("feishu_app_id", "cli-legacy")
    await SiteSetting.set_value("feishu_app_secret", "plain-secret")
    await SiteSetting.set_value(
        "feishu_app_secret_encrypted", encrypt_secret("encrypted-secret")
    )

    await initialize_integrations()

    feishu = await Integration.get(provider_type="feishu")
    assert decrypt_secret(feishu.credentials["app_secret"]) == "encrypted-secret"


@pytest.mark.asyncio
async def test_existing_feishu_integration_and_legacy_settings_are_preserved(database):
    existing = await Integration.create(
        name="feishu",
        provider_type="feishu",
        display_name="Administrator Feishu",
        is_enabled=False,
        enabled_capabilities=[],
        config={"app_id": "admin-config"},
        credentials={"app_secret": encrypt_secret("admin-secret")},
    )
    await SiteSetting.set_value("feishu_app_id", "ambiguous-legacy-id")
    await SiteSetting.set_value("feishu_app_secret", "ambiguous-legacy-secret")

    await initialize_integrations()

    unchanged = await Integration.get(id=existing.id)
    assert unchanged.config == {"app_id": "admin-config"}
    assert decrypt_secret(unchanged.credentials["app_secret"]) == "admin-secret"
    assert await SiteSetting.filter(key="feishu_app_secret").exists()
    assert await SiteSetting.filter(key="feishu_app_id").exists()


@pytest.mark.asyncio
async def test_permission_migration_preserves_separate_admin_domains(database):
    login_role = await Role.create(name="Login managers")
    settings_role = await Role.create(name="Settings readers")
    old_login = await Permission.create(code="admin:sso:update", scope="admin")
    old_settings = await Permission.create(code="admin:settings:read", scope="admin")
    await login_role.permissions.add(old_login)
    await settings_role.permissions.add(old_settings)
    await migrate_integration_permissions()
    await migrate_integration_permissions()
    assert set(await login_role.permissions.all().values_list("code", flat=True)) == {
        "admin:integrations:login:update"
    }
    assert set(
        await settings_role.permissions.all().values_list("code", flat=True)
    ) == {"admin:settings:read", "admin:integrations:settings:read"}
    assert not await Permission.filter(code__startswith="admin:sso:").exists()
    migrated_permission = await Permission.get(code="admin:integrations:settings:read")
    await settings_role.permissions.remove(migrated_permission)
    await migrate_integration_permissions()
    assert set(
        await settings_role.permissions.all().values_list("code", flat=True)
    ) == {"admin:settings:read"}


@pytest.mark.asyncio
async def test_unsupported_legacy_provider_rolls_back_schema_cutover(database):
    await database.execute_query(
        "ALTER TABLE integrations RENAME COLUMN provider_type TO protocol"
    )
    for field in ("enabled_capabilities", "credentials", "login_config"):
        await database.execute_query(f'ALTER TABLE integrations DROP COLUMN "{field}"')
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN allow_signup BOOL NOT NULL DEFAULT 1"
    )
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN require_approval BOOL NOT NULL DEFAULT 0"
    )
    await database.execute_query(
        "ALTER TABLE integrations ADD COLUMN default_role_id VARCHAR(36)"
    )
    await database.execute_query("ALTER TABLE integrations RENAME TO sso_providers")
    await database.execute_query(
        "INSERT INTO sso_providers (id,name,protocol,display_name,is_enabled,config,attribute_mapping,created_at,updated_at) "
        "VALUES ('unsupported-id','old','unsupported','Legacy',1,'{}','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
    )
    with pytest.raises(ValueError, match="Unknown integration type"):
        await migrate_integration_schema()
    tables = await database.execute_query_dict(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    assert "sso_providers" in {row["name"] for row in tables}
    assert "integrations" not in {row["name"] for row in tables}
    columns = await database.execute_query_dict("PRAGMA table_info(sso_providers)")
    assert "allow_signup" in {row["name"] for row in columns}
    assert "credentials" not in {row["name"] for row in columns}
