"""Integration management contracts; secrets are input-only."""

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.integrations.registry import integration_registry


class LoginConfig(BaseModel):
    allow_signup: bool = True
    require_approval: bool = False
    default_role_id: UUID | None = None


class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider_type: str
    display_name: str = Field(min_length=1, max_length=100)
    icon_url: str | None = Field(default=None, max_length=512)
    button_text: str | None = Field(default=None, max_length=50)
    is_enabled: bool = True
    enabled_capabilities: list[str] = Field(default_factory=lambda: ["user_login"])
    config: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, str] = Field(default_factory=dict)
    login_config: LoginConfig = Field(default_factory=LoginConfig)
    attribute_mapping: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", value):
            raise ValueError("sso_invalid_provider_name")
        return value

    @field_validator("icon_url")
    @classmethod
    def validate_icon_url(cls, value: str | None) -> str | None:
        if value and not re.match(r"^https?://", value):
            raise ValueError("sso_invalid_icon_url")
        return value

    @model_validator(mode="after")
    def validate_capabilities(self):
        definition = integration_registry.get(self.provider_type)
        if definition.singleton:
            raise ValueError("Builtin integrations cannot be created more than once")
        if not set(self.enabled_capabilities).issubset(definition.capabilities):
            raise ValueError("Unsupported integration capability")
        if not set(self.credentials).issubset(definition.secret_fields):
            raise ValueError("Unsupported integration credential field")
        if set(self.config) & set(definition.secret_fields):
            raise ValueError("Credentials must use the credentials field")
        return self


class IntegrationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: str | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    icon_url: str | None = Field(default=None, max_length=512)
    button_text: str | None = Field(default=None, max_length=50)
    is_enabled: bool | None = None
    enabled_capabilities: list[str] | None = None
    config: dict[str, Any] | None = None
    credentials: dict[str, str] | None = None
    login_config: LoginConfig | None = None
    attribute_mapping: dict[str, str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return IntegrationCreate.validate_name(value) if value is not None else value

    @field_validator("icon_url")
    @classmethod
    def validate_icon_url(cls, value: str | None) -> str | None:
        return IntegrationCreate.validate_icon_url(value)


class IntegrationAdmin(BaseModel):
    id: UUID
    name: str
    provider_type: str
    display_name: str
    icon_url: str | None
    button_text: str | None
    is_enabled: bool
    enabled_capabilities: list[str]
    supported_capabilities: list[str]
    config: dict[str, Any]
    credentials_configured: list[str]
    login_config: dict[str, Any]
    attribute_mapping: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IntegrationLoginPublic(BaseModel):
    id: UUID
    name: str
    display_name: str
    icon_url: str | None
    button_text: str | None
    provider_type: str

    model_config = ConfigDict(from_attributes=True)


class IntegrationTypeOut(BaseModel):
    provider_type: str
    display_name: str
    supported_capabilities: list[str]
    singleton: bool
