"""Clouisle package import/export schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ClouisleResourceType(str, Enum):
    TOOL = "tool"
    AGENT = "agent"
    WORKFLOW = "workflow"
    KNOWLEDGE_BASE = "knowledge_base"


class ClouisleDependencyStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    FORBIDDEN = "forbidden"
    UNSUPPORTED = "unsupported"


class ClouisleConflictAction(str, Enum):
    INSTALL = "install"
    RENAME = "rename"
    UPDATE = "update"
    SKIP = "skip"


class ClouislePackageDependency(BaseModel):
    type: str
    source_id: str | None = None
    name: str | None = None
    required: bool = True
    hints: dict[str, Any] = Field(default_factory=dict)
    status: ClouisleDependencyStatus | None = None
    matched_id: UUID | None = None
    message: str | None = None


class ClouisleManifest(BaseModel):
    format_version: str
    app_version: str
    package_id: UUID
    exported_at: datetime
    resource_type: ClouisleResourceType
    resource_name: str
    resource_id: str
    dependencies: list[ClouislePackageDependency] = Field(default_factory=list)
    checksums: dict[str, str] = Field(default_factory=dict)


class ClouislePackageConflict(BaseModel):
    type: str = "none"
    existing_id: UUID | None = None
    existing_name: str | None = None
    message: str | None = None


class ClouisleImportPreviewOut(BaseModel):
    session_id: UUID
    package_id: UUID
    resource_type: ClouisleResourceType
    resource_name: str
    source_resource_id: str
    format_version: str
    app_version: str
    exported_at: datetime
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dependencies: list[ClouislePackageDependency] = Field(default_factory=list)
    conflict: ClouislePackageConflict | None = None
    allowed_actions: list[ClouisleConflictAction] = Field(default_factory=list)
    default_action: ClouisleConflictAction = ClouisleConflictAction.INSTALL


class ClouisleImportInstallRequest(BaseModel):
    action: ClouisleConflictAction = ClouisleConflictAction.INSTALL
    target_name: str | None = Field(default=None, min_length=1, max_length=100)
    dependency_mapping: dict[str, UUID] = Field(default_factory=dict)


class ClouisleImportInstallOut(BaseModel):
    installed: UUID | None = None
    updated: UUID | None = None
    skipped: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ClouisleExportOptions(BaseModel):
    include_documents: bool = False
    include_chunks: bool = False
