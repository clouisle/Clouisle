"""Schemas for tool connections and delegation grants.

Every public model here is secret-safe: it exposes *which* credential fields
are configured (``secret_fields``) and never their values or the encrypted
blob. Decrypted material is only available through the internal resolver in
``app.services.tool_connections``, never through a response schema.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.tool_connection import (
    ToolConnectionScope,
    ToolConnectionStatus,
)

# Credential field names are declared by the tool definition. Keep them
# identifier-like so they cannot be used to smuggle template fragments.
_SECRET_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
# Operation keys follow MCP tool names / HTTP operation labels: bounded,
# printable, no whitespace or control characters.
_OPERATION_PATTERN = re.compile(r"^[^\s\x00-\x1f]{1,200}$")
_BUILTIN_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,99}$")

MAX_SECRET_FIELDS = 50
MAX_SECRET_VALUE_LENGTH = 8192
MAX_OPERATIONS = 200


def _validate_secret_field_name(name: str) -> str:
    if not _SECRET_FIELD_PATTERN.fullmatch(name or ""):
        raise ValueError("invalid_credential_field_name")
    return name


def _validate_secret_mapping(config: dict[str, str]) -> dict[str, str]:
    if len(config) > MAX_SECRET_FIELDS:
        raise ValueError("too_many_credential_fields")
    cleaned: dict[str, str] = {}
    for raw_name, raw_value in config.items():
        name = _validate_secret_field_name(raw_name)
        if not isinstance(raw_value, str):
            raise ValueError("credential_value_must_be_string")
        # Empty means "not set"; removal is explicit via config_remove so a
        # blank input can never silently keep an old secret.
        if raw_value == "":
            raise ValueError("credential_value_empty")
        if len(raw_value) > MAX_SECRET_VALUE_LENGTH:
            raise ValueError("credential_value_too_long")
        cleaned[name] = raw_value
    return cleaned


class ToolConnectionDraft(BaseModel):
    """Fields shared by connection creation entrypoints."""

    model_config = ConfigDict(extra="forbid")

    team_id: UUID | None = Field(
        default=None, description="Required for user/team scope; forbidden for site"
    )
    scope: ToolConnectionScope
    name: str = Field(min_length=1, max_length=100)
    account_label: str | None = Field(
        default=None,
        max_length=150,
        description="Non-secret external account label for display",
    )
    config: dict[str, str] = Field(
        default_factory=dict, description="Credential field values (write-only)"
    )
    is_default: bool = False

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name_required")
        return normalized

    @field_validator("account_label")
    @classmethod
    def _strip_account_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("config")
    @classmethod
    def _validate_config(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_secret_mapping(value)

    @model_validator(mode="after")
    def _validate_team_scope(self) -> "ToolConnectionDraft":
        if self.scope == ToolConnectionScope.SITE:
            if self.team_id is not None:
                raise ValueError("site_connection_team_not_allowed")
        elif self.team_id is None:
            raise ValueError("connection_team_required")
        return self


class ToolConnectionCreate(ToolConnectionDraft):
    """Create a connection for a Tool row or a builtin tool key."""

    tool_id: UUID | None = Field(
        default=None, description="Tool definition this connection serves"
    )
    builtin_tool_key: str | None = Field(
        default=None, description="Builtin tool key when no Tool row exists"
    )

    @field_validator("builtin_tool_key")
    @classmethod
    def _validate_builtin_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _BUILTIN_KEY_PATTERN.fullmatch(value):
            raise ValueError("invalid_builtin_tool_key")
        return value

    @model_validator(mode="after")
    def _validate_service_identity(self) -> "ToolConnectionCreate":
        if (self.tool_id is None) == (self.builtin_tool_key is None):
            raise ValueError("connection_service_identity_invalid")
        return self


class ToolConnectionForToolCreate(ToolConnectionDraft):
    """Create a connection whose tool identity comes from the URL path."""


class ToolConnectionUpdate(BaseModel):
    """Partial update.

    ``config_set=None`` retains existing secrets; naming a key in
    ``config_remove`` removes it. The two collections must not overlap.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    account_label: str | None = Field(default=None, max_length=150)
    status: ToolConnectionStatus | None = None
    config_set: dict[str, str] | None = None
    config_remove: list[str] | None = None
    is_default: bool | None = None
    expected_secret_version: int | None = Field(
        default=None, ge=1, description="Optimistic concurrency guard"
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name_required")
        return normalized

    @field_validator("account_label")
    @classmethod
    def _strip_account_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("config_set")
    @classmethod
    def _validate_config_set(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        if value is None:
            return None
        return _validate_secret_mapping(value)

    @field_validator("config_remove")
    @classmethod
    def _validate_config_remove(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned: list[str] = []
        for name in value:
            cleaned.append(_validate_secret_field_name(name))
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("credential_field_duplicate")
        return cleaned

    @model_validator(mode="after")
    def _validate_update(self) -> "ToolConnectionUpdate":
        if self.status == ToolConnectionStatus.REVOKED:
            raise ValueError("revoked_status_requires_revoke")
        if self.config_set and self.config_remove:
            overlap = set(self.config_set) & set(self.config_remove)
            if overlap:
                raise ValueError("credential_field_conflict")
        return self


class ToolConnectionOut(BaseModel):
    """Secret-safe connection metadata returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID | None
    tool_id: UUID | None
    builtin_tool_key: str | None
    scope: ToolConnectionScope
    name: str
    account_label: str | None
    status: ToolConnectionStatus
    secret_fields: list[str] = Field(default_factory=list)
    secret_version: int
    is_default: bool
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ToolConnectionCreate",
    "ToolConnectionDraft",
    "ToolConnectionForToolCreate",
    "ToolConnectionOut",
    "ToolConnectionUpdate",
]
