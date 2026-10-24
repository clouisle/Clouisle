"""Existing SSO login sessions survive the link-field upgrade."""

from datetime import timedelta

import pytest
from tortoise import Tortoise

from app.core.sso_link_migration import migrate_sso_link_sessions
from app.core.timezone import now_utc
from app.models.integration import Integration
from app.models.sso_session import SSOSession
from app.models.user import User


@pytest.mark.asyncio
async def test_upgrade_keeps_login_state_and_supports_owned_link_sessions():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        db = Tortoise.get_connection("default")
        integration = await Integration.create(
            name="feishu", provider_type="feishu", display_name="Feishu"
        )
        session = await SSOSession.create(
            integration=integration,
            session_id="pending-login",
            code_verifier="unchanged",
            expires_at=now_utc() + timedelta(minutes=10),
        )
        # Recreate the pre-upgrade session shape without the new columns or index.
        await db.execute_query("DROP TABLE sso_sessions")
        await db.execute_query(
            "CREATE TABLE sso_sessions (id CHAR(36) PRIMARY KEY, session_id VARCHAR(255) UNIQUE, integration_id CHAR(36), code_verifier VARCHAR(255), nonce VARCHAR(255), redirect_url VARCHAR(512), created_at TIMESTAMP, expires_at TIMESTAMP)"
        )
        await db.execute_query(
            "INSERT INTO sso_sessions (id, session_id, integration_id, code_verifier, expires_at) VALUES (?, ?, ?, ?, ?)",
            [
                str(session.id),
                "pending-login",
                str(integration.id),
                "unchanged",
                session.expires_at,
            ],
        )
        await migrate_sso_link_sessions()
        await migrate_sso_link_sessions()
        restored = await SSOSession.get(id=session.id)
        assert restored.code_verifier == "unchanged"
        assert restored.link_user_id is None
        actor = await User.create(
            username="actor", email="actor@example.com", hashed_password="kept"
        )
        pending = await SSOSession.create(
            integration=integration,
            session_id="pending-link",
            link_user=actor,
            link_user_info={"provider_user_id": "union"},
            expires_at=now_utc() + timedelta(minutes=10),
        )
        assert (await SSOSession.get(id=pending.id)).link_user_id == actor.id
        await actor.delete()
        assert not await SSOSession.filter(id=pending.id).exists()
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_upgrade_preserves_manual_link_exclusions_across_restarts():
    from app.models.audit_log import AuditLog
    from app.models.user_sso_connection import UserSSOConnection

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        db = Tortoise.get_connection("default")
        integration = await Integration.create(
            name="feishu", provider_type="feishu", display_name="Feishu"
        )
        linked = await User.create(
            username="linked", email="linked@example.com", hashed_password="kept"
        )
        ordinary = await User.create(
            username="ordinary", email="ordinary@example.com", hashed_password="kept"
        )
        await UserSSOConnection.create(
            user=linked, integration=integration, provider_user_id="manual"
        )
        await UserSSOConnection.create(
            user=ordinary, integration=integration, provider_user_id="ordinary"
        )
        await AuditLog.create(
            user_id=linked.id,
            action="link_sso",
            resource_type="sso_connection",
            resource_name="feishu",
            operation="create",
            status="success",
        )
        await db.execute_query(
            'ALTER TABLE "user_sso_connections" DROP COLUMN "self_service_linked"'
        )

        await migrate_sso_link_sessions()
        assert (await UserSSOConnection.get(user=linked)).self_service_linked is True
        assert (await UserSSOConnection.get(user=ordinary)).self_service_linked is False
        # Old audit events must not classify a replacement login connection.
        await UserSSOConnection.filter(user=linked).delete()
        await UserSSOConnection.create(
            user=linked, integration=integration, provider_user_id="replacement"
        )
        await migrate_sso_link_sessions()
        assert (await UserSSOConnection.get(user=linked)).self_service_linked is False
    finally:
        await Tortoise.close_connections()
