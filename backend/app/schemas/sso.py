import re
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Provider name: lowercase letters, numbers, hyphens, underscores; must start with a letter
PROVIDER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def _validate_provider_name(v: str) -> str:
    if not PROVIDER_NAME_PATTERN.match(v):
        raise ValueError("sso_invalid_provider_name")
    return v


def _validate_icon_url(v: Optional[str]) -> Optional[str]:
    if v is not None and v != "":
        if not re.match(r"^https?://", v):
            raise ValueError("sso_invalid_icon_url")
    return v


# SSO Provider Schemas
class SSOProviderBase(BaseModel):
    name: str = Field(..., max_length=100, description="Unique provider identifier")
    protocol: str = Field(..., description="Protocol: oidc, saml2, cas")
    display_name: str = Field(..., max_length=100, description="User-facing name")
    icon_url: Optional[str] = Field(None, max_length=512)
    button_text: Optional[str] = Field(None, max_length=50)
    config: Dict[str, Any] = Field(..., description="Protocol-specific configuration")
    attribute_mapping: Dict[str, str] = Field(
        default_factory=dict, description="Maps provider attributes to user fields"
    )
    is_enabled: bool = Field(default=True)
    allow_signup: bool = Field(default=True)
    require_approval: bool = Field(default=False)
    default_role_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_provider_name(v)

    @field_validator("icon_url")
    @classmethod
    def validate_icon_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_icon_url(v)


class SSOProviderCreate(SSOProviderBase):
    pass


class SSOProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    protocol: Optional[str] = None
    display_name: Optional[str] = Field(None, max_length=100)
    icon_url: Optional[str] = Field(None, max_length=512)
    button_text: Optional[str] = Field(None, max_length=50)
    config: Optional[Dict[str, Any]] = None
    attribute_mapping: Optional[Dict[str, str]] = None
    is_enabled: Optional[bool] = None
    allow_signup: Optional[bool] = None
    require_approval: Optional[bool] = None
    default_role_id: Optional[UUID] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_provider_name(v)
        return v

    @field_validator("icon_url")
    @classmethod
    def validate_icon_url(cls, v: Optional[str]) -> Optional[str]:
        return _validate_icon_url(v)


class SSOProviderPublic(BaseModel):
    """Public SSO provider info (for login page)"""

    id: UUID
    name: str
    display_name: str
    icon_url: Optional[str]
    button_text: Optional[str]
    protocol: str

    class Config:
        from_attributes = True


class SSOProviderAdmin(BaseModel):
    """Full SSO provider info (for admin)"""

    id: UUID
    name: str
    protocol: str
    display_name: str
    icon_url: Optional[str]
    button_text: Optional[str]
    config: Dict[str, Any]
    attribute_mapping: Dict[str, str]
    is_enabled: bool
    allow_signup: bool
    require_approval: bool
    default_role_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# User SSO Connection Schemas
class UserSSOConnectionSchema(BaseModel):
    """User SSO connection info for display"""

    id: UUID
    provider_id: UUID
    provider_name: str
    provider_display_name: str
    provider_icon_url: Optional[str]
    provider_user_id: str
    provider_username: Optional[str]
    provider_email: Optional[str]
    first_login: datetime
    last_login: datetime

    class Config:
        from_attributes = True
