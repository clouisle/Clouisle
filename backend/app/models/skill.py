"""Skill models for sandboxed Agent-callable capabilities."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from tortoise import fields, models

if TYPE_CHECKING:
    from app.models.user import Team, User


class SkillCategory(str, Enum):
    """Skill category for organization."""

    FILE = "file"
    CODE = "code"
    DATA = "data"
    WEB = "web"
    API = "api"
    OTHER = "other"


class SkillSourceType(str, Enum):
    """Source used to install a Skill package."""

    ZIP = "zip"
    GIT = "git"
    MANUAL_TEXT = "manual_text"
    LEGACY = "legacy"


class SkillExecutionMode(str, Enum):
    """How an installed Skill is executed."""

    INSTRUCTIONS = "instructions"
    SCRIPT = "script"
    LEGACY = "legacy"


class SkillImportSessionStatus(str, Enum):
    """Short-lived Skill import session status."""

    PREVIEWED = "previewed"
    INSTALLED = "installed"
    EXPIRED = "expired"


class Skill(models.Model):
    """Sandboxed capability that can be selected by Agents."""

    id = fields.UUIDField(pk=True)

    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="skills",
        on_delete=fields.CASCADE,
        null=True,
        description="Team that owns this skill; null means system skill",
    )
    team_id: UUID | None  # type: ignore[assignment]

    name = fields.CharField(max_length=100, description="Stable skill name")
    display_name = fields.CharField(max_length=100, description="Display name")
    description = fields.TextField(default="", description="Skill description")
    icon = fields.CharField(max_length=100, null=True, description="Icon emoji or URL")
    category = fields.CharEnumField(
        SkillCategory,
        default=SkillCategory.OTHER,
        description="Skill category",
    )
    version = fields.CharField(
        max_length=50, default="1.0.0", description="Skill version"
    )

    source_type = fields.CharEnumField(
        SkillSourceType,
        default=SkillSourceType.LEGACY,
        description="Source used to install this Skill package",
    )
    source_uri = fields.TextField(
        null=True,
        description="Redacted source URI for Git/imported packages",
    )
    source_ref = fields.CharField(
        max_length=255,
        null=True,
        description="Git ref or resolved source revision",
    )
    source_subdir = fields.CharField(
        max_length=500,
        null=True,
        description="Source subdirectory scanned during import",
    )
    package_path = fields.CharField(
        max_length=500,
        null=True,
        description="Skill root path inside the imported source",
    )
    package_storage_path = fields.CharField(
        max_length=1000,
        null=True,
        description="Private storage path for the installed Skill package",
    )
    package_hash = fields.CharField(
        max_length=128,
        null=True,
        description="Content hash for the installed Skill package",
    )
    package_manifest: dict = fields.JSONField(
        default=dict,
        description="Installed package manifest summary",
    )  # type: ignore[assignment]
    skill_md = fields.TextField(
        default="",
        description="Raw SKILL.md content",
    )
    instructions = fields.TextField(
        default="",
        description="Markdown instructions from SKILL.md",
    )
    frontmatter: dict = fields.JSONField(
        default=dict,
        description="Parsed SKILL.md frontmatter",
    )  # type: ignore[assignment]
    execution_mode = fields.CharEnumField(
        SkillExecutionMode,
        default=SkillExecutionMode.INSTRUCTIONS,
        description="Skill execution mode",
    )
    execution_config: dict = fields.JSONField(
        default=dict,
        description="Validated Clouisle execution extension",
    )  # type: ignore[assignment]
    import_warnings: list = fields.JSONField(
        default=list,
        description="Non-blocking import warnings",
    )  # type: ignore[assignment]

    input_schema: dict = fields.JSONField(
        default=dict,
        description="JSON Schema object exposed to the model as function parameters",
    )  # type: ignore[assignment]
    skill_spec: dict = fields.JSONField(
        default=dict,
        description="Legacy SandboxSkillSpec payload",
    )  # type: ignore[assignment]
    config_schema: dict = fields.JSONField(
        default=dict,
        description="Optional per-Agent configuration schema",
    )  # type: ignore[assignment]
    default_config: dict = fields.JSONField(
        default=dict,
        description="Default per-Agent configuration values",
    )  # type: ignore[assignment]

    is_enabled = fields.BooleanField(
        default=True, description="Whether skill is enabled"
    )

    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_skills",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "skills"
        unique_together = [("team", "name")]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        scope = str(self.team_id) if self.team_id else "system"
        return f"{self.display_name} ({self.name}, {scope})"


class SkillImportSession(models.Model):
    """Preview session for importing one or more Skill packages."""

    id = fields.UUIDField(pk=True)

    team: fields.ForeignKeyRelation["Team"] | None = fields.ForeignKeyField(
        "models.Team",
        related_name="skill_import_sessions",
        on_delete=fields.CASCADE,
        null=True,
        description="Team that owns this import; null means system import",
    )
    team_id: UUID | None  # type: ignore[assignment]

    source_type = fields.CharEnumField(
        SkillSourceType,
        description="Import source type",
    )
    source_uri = fields.TextField(
        null=True,
        description="Redacted source URI",
    )
    source_ref = fields.CharField(
        max_length=255,
        null=True,
        description="Git ref or resolved source revision",
    )
    source_subdir = fields.CharField(
        max_length=500,
        null=True,
        description="Source subdirectory scanned during import",
    )
    status = fields.CharEnumField(
        SkillImportSessionStatus,
        default=SkillImportSessionStatus.PREVIEWED,
        description="Import session status",
    )
    preview: dict = fields.JSONField(
        default=dict,
        description="Preview result returned to the user",
    )  # type: ignore[assignment]
    temp_storage_path = fields.CharField(
        max_length=1000,
        null=True,
        description="Temporary staged source path or cache key",
    )
    expires_at = fields.DatetimeField(description="Import session expiry time")

    created_by: fields.ForeignKeyRelation["User"] | None = fields.ForeignKeyField(
        "models.User",
        related_name="created_skill_import_sessions",
        on_delete=fields.SET_NULL,
        null=True,
        description="Creator",
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "skill_import_sessions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        scope = str(self.team_id) if self.team_id else "system"
        return f"Skill import {self.id} ({self.source_type}, {scope})"
