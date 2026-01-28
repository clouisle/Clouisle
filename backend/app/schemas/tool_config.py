"""
Tool Configuration schemas
"""

from pydantic import BaseModel, Field
from uuid import UUID


class ToolConfigCreate(BaseModel):
    """Create tool configuration"""

    tool_name: str = Field(..., description="Tool name (e.g., web_search)")
    credentials: dict[str, str] = Field(..., description="Tool credentials (API keys, tokens, etc.)")


class ToolConfigUpdate(BaseModel):
    """Update tool configuration"""

    credentials: dict[str, str] = Field(..., description="Tool credentials (API keys, tokens, etc.)")


class ToolConfigOut(BaseModel):
    """Tool configuration output"""

    id: UUID
    tool_name: str
    team_id: UUID | None
    credentials: dict[str, str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
