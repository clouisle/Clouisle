from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.integration import Integration
    from app.models.user import User


class SSOSession(models.Model):
    """Temporary SSO session state (for OAuth2/OIDC state parameter, SAML RelayState)"""

    integration_id: UUID
    link_user_id: UUID | None

    id = fields.UUIDField(primary_key=True)
    session_id = fields.CharField(
        max_length=255, unique=True, description="Random state/RelayState"
    )
    integration: fields.ForeignKeyRelation["Integration"] = fields.ForeignKeyField(
        "models.Integration", related_name="sessions", on_delete=fields.CASCADE
    )
    link_user: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="sso_link_sessions",
        null=True,
        on_delete=fields.CASCADE,
    )

    # OAuth2/OIDC specific
    code_verifier = fields.CharField(
        max_length=255, null=True, description="PKCE code verifier"
    )
    nonce = fields.CharField(max_length=255, null=True, description="OIDC nonce")
    # Link intent is completed by the authenticated owner after provider callback.
    link_user_info: dict | None = fields.JSONField(null=True)

    # Redirect after login
    redirect_url = fields.CharField(max_length=512, null=True)

    # Metadata
    created_at = fields.DatetimeField(auto_now_add=True)
    expires_at = fields.DatetimeField(description="Session expiry (10 minutes)")

    class Meta:
        table = "sso_sessions"

    def __str__(self):
        return f"Session {self.session_id}"
