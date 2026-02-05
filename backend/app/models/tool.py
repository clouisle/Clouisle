"""
Tool models for custom tools and MCP server configurations.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User


class ToolType(str, Enum):
    """Tool type"""

    CUSTOM = "custom"  # Custom tool (HTTP API or Code)
    MCP = "mcp"  # MCP Server


class CustomToolType(str, Enum):
    """Custom tool execution type"""

    HTTP = "http"  # HTTP API call
    CODE = "code"  # Code execution (future)


class ToolCategory(str, Enum):
    """Tool category for organization"""

    TIME = "time"
    MATH = "math"
    SEARCH = "search"
    WEB = "web"
    FILE = "file"
    CODE = "code"
    API = "api"
    DATA = "data"
    OTHER = "other"


class ToolSharePermission(str, Enum):
    """Tool sharing permission level"""

    READ_ONLY = "read_only"  # Can view and use the tool
    READ_EXECUTE = "read_execute"  # Can view, use, and see execution results


class Tool(models.Model):
    """
    Custom Tool or MCP Server configuration.

    Stores user-defined tools that can be used by agents.
    """

    id = fields.UUIDField(pk=True)

    # Team association for data isolation
    team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="tools",
        on_delete=fields.CASCADE,
        description="Team that owns this tool",
    )
    team_id: UUID  # type: ignore[assignment]

    # Basic info
    name = fields.CharField(
        max_length=100, description="Tool name (unique within team)"
    )
    display_name = fields.CharField(max_length=100, description="Display name")
    description = fields.TextField(description="Tool description")
    icon = fields.CharField(max_length=100, null=True, description="Icon emoji or URL")
    category = fields.CharEnumField(
        ToolCategory, default=ToolCategory.OTHER, description="Tool category"
    )

    # Tool type
    type = fields.CharEnumField(ToolType, description="Tool type (custom or mcp)")

    # Custom tool configuration (type=custom)
    custom_type = fields.CharEnumField(
        CustomToolType, null=True, description="Custom tool execution type"
    )

    # HTTP tool config (custom_type=http)
    # {
    #   "method": "GET" | "POST" | "PUT" | "DELETE",
    #   "url": "https://api.example.com/endpoint",
    #   "headers": {"Authorization": "Bearer {{api_key}}"},
    #   "query_params": {"key": "value"},
    #   "body_template": "{\"text\": \"{{input}}\"}",
    #   "timeout": 30,
    #   "response_path": "data.result"  # JSON path to extract result
    # }
    http_config: dict = fields.JSONField(default=dict, description="HTTP configuration")  # type: ignore[assignment]

    # Code tool config (custom_type=code) - for future use
    # {
    #   "language": "python",
    #   "code": "def main(inputs): ..."
    # }
    code_config: dict = fields.JSONField(default=dict, description="Code configuration")  # type: ignore[assignment]

    # MCP Server configuration (type=mcp)
    # {
    #   "transport": "stdio" | "sse",
    #   "command": "npx",  # for stdio
    #   "args": ["-y", "@modelcontextprotocol/server-xxx"],
    #   "env": {"API_KEY": "xxx"},
    #   "url": "http://localhost:3000/sse"  # for sse transport
    # }
    mcp_config: dict = fields.JSONField(
        default=dict, description="MCP server configuration"
    )  # type: ignore[assignment]

    # Tool parameters definition (JSON Schema format)
    # [
    #   {
    #     "name": "query",
    #     "type": "string",
    #     "description": "Search query",
    #     "required": true
    #   }
    # ]
    parameters: list = fields.JSONField(
        default=list, description="Parameter definitions"
    )  # type: ignore[assignment]

    # Credentials/secrets (stored encrypted in production)
    # {"api_key": "sk-xxx", "secret": "xxx"}
    credentials: dict = fields.JSONField(default=dict, description="Tool credentials")  # type: ignore[assignment]

    # Status
    is_enabled = fields.BooleanField(
        default=True, description="Whether tool is enabled"
    )

    # Audit
    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_tools",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "tools"
        unique_together = [("team", "name")]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.display_name} ({self.name})"


class ToolShare(models.Model):
    """
    Tool sharing relationship between teams.

    Allows a tool owned by one team to be shared with other teams.
    """

    id = fields.UUIDField(pk=True)

    # The tool being shared
    tool: fields.ForeignKeyRelation["Tool"] = fields.ForeignKeyField(
        "models.Tool",
        related_name="shares",
        on_delete=fields.CASCADE,
        description="Tool being shared",
    )
    tool_id: UUID  # type: ignore[assignment]

    # The team receiving access
    shared_with_team: fields.ForeignKeyRelation["Team"] = fields.ForeignKeyField(
        "models.Team",
        related_name="shared_tools",
        on_delete=fields.CASCADE,
        description="Team receiving access",
    )
    shared_with_team_id: UUID  # type: ignore[assignment]

    # Permission level
    permission = fields.CharEnumField(
        ToolSharePermission,
        default=ToolSharePermission.READ_ONLY,
        description="Permission level",
    )

    # Audit
    shared_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="tool_shares_created",
        on_delete=fields.SET_NULL,
        null=True,
        description="User who shared the tool",
    )
    shared_by_id: UUID | None  # type: ignore[assignment]

    shared_at = fields.DatetimeField(
        auto_now_add=True, description="When the tool was shared"
    )

    class Meta:
        table = "tool_shares"
        unique_together = [("tool", "shared_with_team")]
        ordering = ["-shared_at"]

    def __str__(self):
        return f"Tool share: {self.tool_id} -> Team {self.shared_with_team_id}"
