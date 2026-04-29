"""Sandbox runtime contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cache import normalize_package_source_url


class SandboxTaskStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COLLECTING = "collecting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SandboxStage(str, Enum):
    QUEUE = "queue"
    PREPARATION = "preparation"
    INSTALL = "install"
    EXECUTION = "execution"
    COLLECTION = "collection"


class SandboxJobSource(str, Enum):
    TOOL = "tool"
    CHAT = "chat"
    WORKFLOW = "workflow"
    DEBUG = "debug"
    SKILL = "skill"
    LEGACY_SNIPPET = "legacy_snippet"


class SandboxArtifactSpec(BaseModel):
    path: str = Field(..., description="Artifact path inside workspace")
    optional: bool = Field(default=False, description="Whether missing artifact is allowed")
    description: str | None = Field(default=None, description="Artifact description")


class SandboxInputFileSpec(BaseModel):
    target_path: str = Field(..., description="Destination path inside workspace")
    content_base64: str = Field(..., description="Base64-encoded file content")
    mode: int | None = Field(default=None, ge=0, le=0o777, description="Optional file mode")


class SandboxArtifact(BaseModel):
    path: str = Field(..., description="Artifact path inside workspace")
    optional: bool = Field(default=False, description="Whether missing artifact is allowed")
    description: str | None = Field(default=None, description="Artifact description")
    file_type: str = Field(..., description="Artifact type (file or directory)")
    size: int = Field(..., ge=0, description="Artifact size in bytes")
    checksum: str | None = Field(default=None, description="Artifact checksum for files")
    content_type: str | None = Field(default=None, description="Detected content type")
    storage_path: str = Field(..., description="Persisted storage path")
    url: str = Field(..., description="Backend file URL")
    filename: str = Field(..., description="Persisted filename")


class SandboxLimits(BaseModel):
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=600.0)
    disk_mb: int = Field(default=1024, ge=0, le=102400)
    max_stdout_kb: int = Field(default=256, ge=16, le=8192)
    max_stderr_kb: int = Field(default=256, ge=16, le=8192)


class SandboxExecutionMetadata(BaseModel):
    status: SandboxTaskStatus = Field(default=SandboxTaskStatus.QUEUED)
    stage: SandboxStage | None = Field(default=SandboxStage.QUEUE)
    queued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    prepare_started_at: datetime | None = None
    prepare_completed_at: datetime | None = None
    install_started_at: datetime | None = None
    install_completed_at: datetime | None = None
    execute_started_at: datetime | None = None
    execute_completed_at: datetime | None = None
    collect_started_at: datetime | None = None
    collect_completed_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    queue_wait_ms: int | None = None
    prepare_ms: int | None = None
    install_duration_ms: int | None = None
    install_ms: int | None = None
    execute_ms: int | None = None
    collect_ms: int | None = None
    total_ms: int | None = None
    cache_hit_python: bool = False
    cache_hit_node: bool = False
    exit_code: int | None = None
    worker_id: str | None = None

    def mark_started(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.started_at = timestamp
        self.stage = SandboxStage.PREPARATION
        self.status = SandboxTaskStatus.PREPARING
        self._refresh_durations(reference_time=timestamp)

    def mark_prepare_started(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        if self.started_at is None:
            self.started_at = timestamp
        self.prepare_started_at = timestamp
        self.stage = SandboxStage.PREPARATION
        self.status = SandboxTaskStatus.PREPARING
        self._refresh_durations(reference_time=timestamp)

    def mark_prepare_completed(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.prepare_completed_at = timestamp
        self._refresh_durations(reference_time=timestamp)

    def mark_install_started(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.install_started_at = timestamp
        self.stage = SandboxStage.INSTALL
        self.status = SandboxTaskStatus.RUNNING
        self._refresh_durations(reference_time=timestamp)

    def mark_install_completed(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.install_completed_at = timestamp
        self._refresh_durations(reference_time=timestamp)

    def mark_execute_started(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.execute_started_at = timestamp
        self.stage = SandboxStage.EXECUTION
        self.status = SandboxTaskStatus.RUNNING
        self._refresh_durations(reference_time=timestamp)

    def mark_execute_completed(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.execute_completed_at = timestamp
        self._refresh_durations(reference_time=timestamp)

    def mark_collect_started(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.collect_started_at = timestamp
        self.stage = SandboxStage.COLLECTION
        self.status = SandboxTaskStatus.COLLECTING
        self._refresh_durations(reference_time=timestamp)

    def mark_collect_completed(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.collect_completed_at = timestamp
        self._refresh_durations(reference_time=timestamp)

    def mark_completed(self, now: datetime | None = None) -> None:
        timestamp = now or datetime.now(UTC)
        self.completed_at = timestamp
        self.stage = None
        self._refresh_durations(reference_time=timestamp)

    def _refresh_durations(self, *, reference_time: datetime | None = None) -> None:
        reference = reference_time or self.completed_at or datetime.now(UTC)
        self.queue_wait_ms = self._duration_ms(self.queued_at, self.started_at or reference)
        self.prepare_ms = self._duration_ms(self.prepare_started_at, self.prepare_completed_at or reference)

        install_start = self.install_started_at
        install_end = self.install_completed_at or reference
        if install_start is None and self.install_completed_at is None:
            self.install_ms = 0
            self.install_duration_ms = 0
        else:
            install_duration = self._duration_ms(install_start, install_end)
            self.install_ms = install_duration
            self.install_duration_ms = install_duration

        self.execute_ms = self._duration_ms(self.execute_started_at, self.execute_completed_at or reference)

        collect_start = self.collect_started_at
        collect_end = self.collect_completed_at or reference
        if collect_start is None and self.collect_completed_at is None:
            self.collect_ms = 0
        else:
            self.collect_ms = self._duration_ms(collect_start, collect_end)

        self.total_ms = self._duration_ms(self.queued_at, self.completed_at or reference)
        self.duration_ms = self.total_ms

    @staticmethod
    def _duration_ms(start: datetime | None, end: datetime | None) -> int | None:
        if start is None or end is None:
            return None
        normalized_start = SandboxExecutionMetadata._ensure_utc(start)
        normalized_end = SandboxExecutionMetadata._ensure_utc(end)
        return max(0, int((normalized_end - normalized_start).total_seconds() * 1000))

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SandboxJob(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str | None = Field(default=None)
    source: SandboxJobSource = Field(default=SandboxJobSource.DEBUG)
    runtime_profile: str = Field(default="standard")
    language: str | None = Field(default=None, description="Legacy snippet language")
    code: str | None = Field(default=None, description="Legacy snippet code")
    command: list[str] = Field(default_factory=list)
    shell: bool = Field(default=False)
    python_packages: list[str] = Field(default_factory=list)
    js_packages: list[str] = Field(default_factory=list)
    python_package_index_url: str | None = Field(default=None)
    node_package_registry_url: str | None = Field(default=None)
    cwd: str = Field(default="/workspace")
    env: dict[str, str] = Field(default_factory=dict)
    input_files: list[SandboxInputFileSpec] = Field(default_factory=list)
    artifacts: list[SandboxArtifactSpec] = Field(default_factory=list)
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_input_files(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        input_files = data.get("input_files")
        if input_files is None:
            return data
        normalized = []
        for item in input_files:
            if isinstance(item, dict) and "content" in item and "content_base64" not in item:
                normalized.append({**item, "content_base64": item["content"]})
            else:
                normalized.append(item)
        data["input_files"] = normalized
        return data

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: list[str]) -> list[str]:
        if any(not item for item in value):
            raise ValueError("Sandbox command arguments must be non-empty strings")
        return value

    @field_validator("python_package_index_url", "node_package_registry_url", mode="before")
    @classmethod
    def normalize_package_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Sandbox package source URL must be a string")
        return normalize_package_source_url(value)


class SandboxResult(BaseModel):
    job_id: str
    success: bool = False
    status: SandboxTaskStatus = Field(default=SandboxTaskStatus.QUEUED)
    result: Any = None
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: list[SandboxArtifact] = Field(default_factory=list)
    metadata: SandboxExecutionMetadata = Field(default_factory=SandboxExecutionMetadata)


class SandboxSkillSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    version: str = Field(default="1.0.0")
    runtime_profile: str = Field(default="standard")
    python_packages: list[str] = Field(default_factory=list)
    js_packages: list[str] = Field(default_factory=list)
    command_template: list[str] = Field(default_factory=list)
    shell: bool = False
    env: dict[str, str] = Field(default_factory=dict)
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    artifacts: list[SandboxArtifactSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
