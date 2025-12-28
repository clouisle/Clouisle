"""
Tool models for custom tools and MCP server configurations.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

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
    team_id: fields.Field[str]  # type: ignore[assignment]

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
    created_by: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="created_tools",
        on_delete=fields.CASCADE,
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
