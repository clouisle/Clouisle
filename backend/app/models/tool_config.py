"""
Tool Configuration model for storing API keys and other credentials.
"""

from typing import TYPE_CHECKING
from tortoise import fields, models
from uuid import UUID

if TYPE_CHECKING:
    from .user import Team


class ToolConfig(models.Model):
    """
    Tool configuration for storing credentials (API keys, tokens, etc.)
    per team or globally.
    """

    id = fields.UUIDField(pk=True)

    # Tool identification
    tool_name = fields.CharField(
        max_length=100, description="Tool name (e.g., web_search)"
    )

    # Team association (NULL = global configuration)
    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="tool_configs",
        on_delete=fields.CASCADE,
        null=True,
        description="Team that owns this configuration (NULL = global)",
    )
    team_id: UUID | None  # type: ignore[assignment]

    # Configuration data (API keys, tokens, etc.)
    # {"TAVILY_API_KEY": "tvly-xxx", "OPENWEATHER_API_KEY": "xxx"}
    credentials: dict = fields.JSONField(
        default=dict, description="Tool credentials (API keys, tokens, etc.)"
    )  # type: ignore[assignment]

    # Audit
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tool_configs"
        unique_together = (("tool_name", "team_id"),)  # One config per tool per team

    def __str__(self):
        scope = f"Team {self.team_id}" if self.team_id else "Global"
        return f"{self.tool_name} ({scope})"
