"""Skill schemas."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.skill import SkillCategory, SkillSourceType
from app.schemas.tool import SandboxArtifactSchema


class SkillConflict(BaseModel):
    type: str
    skill_id: UUID | None = None
    message: str | None = None


class SkillPreviewItem(BaseModel):
    package_path: str
    name: str | None = None
    display_name: str | None = None
    description: str = ""
    version: str = "1.0.0"
    category: SkillCategory = SkillCategory.OTHER
    icon: str | None = None
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflict: SkillConflict | None = None
    file_count: int = 0
    package_hash: str | None = None


class SkillImportPreviewOut(BaseModel):
    session_id: UUID
    source_type: SkillSourceType
    source_uri: str | None = None
    source_ref: str | None = None
    source_subdir: str | None = None
    skills: list[SkillPreviewItem] = Field(default_factory=list)
    invalid: list[SkillPreviewItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SkillImportPreviewGitRequest(BaseModel):
    team_id: UUID | None = Field(default=None)
    repo_url: str = Field(..., min_length=1, max_length=2000)
    ref: str | None = Field(default=None, max_length=255)


class SkillInstallAction(str, Enum):
    INSTALL = "install"
    UPDATE = "update"
    SKIP = "skip"


class SkillImportInstallItem(BaseModel):
    package_path: str
    action: SkillInstallAction = SkillInstallAction.INSTALL
    skill_id: UUID | None = None


class SkillImportInstallRequest(BaseModel):
    items: list[SkillImportInstallItem] = Field(default_factory=list)
    is_enabled: bool = True


class SkillImportInstallOut(BaseModel):
    installed: list[UUID] = Field(default_factory=list)
    updated: list[UUID] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SkillUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=100)
    category: SkillCategory | None = None
    is_enabled: bool | None = None
    default_config: dict[str, Any] | None = None


class SkillOut(BaseModel):
    id: UUID
    team_id: UUID | None = None
    name: str
    display_name: str
    description: str
    icon: str | None = None
    category: SkillCategory
    version: str
    source_type: SkillSourceType
    source_uri: str | None = None
    source_ref: str | None = None
    source_subdir: str | None = None
    package_path: str | None = None
    package_hash: str | None = None
    input_schema: dict[str, Any]
    default_config: dict[str, Any]
    is_enabled: bool
    is_system: bool = False
    import_warnings: list[str] = Field(default_factory=list)
    created_by_id: UUID | None = None
    created_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SkillDetailOut(SkillOut):
    skill_md: str = ""
    instructions: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    package_manifest: dict[str, Any] = Field(default_factory=dict)
    execution_config: dict[str, Any] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)


class SkillListOut(BaseModel):
    system: list[SkillOut] = Field(default_factory=list)
    team: list[SkillOut] = Field(default_factory=list)


class SkillTestRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class SkillTestResponse(BaseModel):
    success: bool
    result: Any = None
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[SandboxArtifactSchema] = Field(default_factory=list)
    duration_ms: int | None = None


_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,99}$")


class SkillCreate(BaseModel):
    team_id: UUID | None = Field(default=None)
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    icon: str | None = Field(default=None, max_length=100)
    category: SkillCategory = SkillCategory.OTHER
    version: str = Field(default="1.0.0", max_length=50)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    skill_spec: dict[str, Any] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    default_config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _SKILL_NAME_PATTERN.match(value):
            raise ValueError("skill_invalid_name")
        return value
