from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.sso_provider import SSOProvider
    from app.models.user import User


class UserSSOConnection(models.Model):
    """Links users to their SSO provider accounts"""

    id = fields.UUIDField(pk=True)
    user: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User", related_name="sso_connections", on_delete=fields.CASCADE
    )
    provider: fields.ForeignKeyRelation["SSOProvider"] = fields.ForeignKeyField(
        "models.SSOProvider", related_name="user_connections", on_delete=fields.CASCADE
    )

    # Provider-specific user identifier
    provider_user_id = fields.CharField(
        max_length=255, description="Provider user ID (sub, nameID, etc.)"
    )
    provider_username = fields.CharField(max_length=255, null=True)
    provider_email = fields.CharField(max_length=255, null=True)

    # Additional provider data (JSON)
    provider_data: dict = fields.JSONField(
        default=dict, description="Store full profile data from provider"
    )  # type: ignore[assignment]

    # Metadata
    first_login = fields.DatetimeField(auto_now_add=True)
    last_login = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "user_sso_connections"
        unique_together = (("provider", "provider_user_id"),)

    def __str__(self):
        return f"{self.user} - {self.provider}"
