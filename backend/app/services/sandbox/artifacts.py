"""Sandbox artifact persistence helpers."""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiofiles
import httpx

from app.core.config import settings

from .models import SandboxArtifact, SandboxArtifactLimits, SandboxArtifactSpec
from .workspace import SandboxWorkspace, SandboxWorkspaceManager


class SandboxArtifactStore:
    CATEGORY = "sandbox-artifacts"
    UPLOAD_ENDPOINT = "/api/v1/upload/sandbox-artifact"
    REQUEST_TIMEOUT_SECONDS = 60.0
    INTERNAL_TIMESTAMP_HEADER = "X-Sandbox-Artifact-Timestamp"
    INTERNAL_SIGNATURE_HEADER = "X-Sandbox-Artifact-Signature"

    def __init__(self, workspace_manager: SandboxWorkspaceManager | None = None):
        self.workspace_manager = workspace_manager or SandboxWorkspaceManager()

    async def collect(
        self,
        *,
        job_id: str,
        artifacts: list[SandboxArtifactSpec],
        workspace: SandboxWorkspace,
        artifact_limits: SandboxArtifactLimits,
    ) -> list[SandboxArtifact]:
        collected: list[SandboxArtifact] = []
        total_uploaded_bytes = 0
        for artifact in artifacts:
            resolved = self.workspace_manager.resolve_workspace_path(
                workspace, artifact.path
            )
            if not resolved.exists():
                if artifact.optional:
                    continue
                raise FileNotFoundError(f"Required artifact not found: {artifact.path}")

            persisted_artifact, uploaded_bytes = await self._persist_artifact(
                job_id=job_id,
                artifact=artifact,
                resolved=resolved,
                artifact_limits=artifact_limits,
                total_uploaded_bytes=total_uploaded_bytes,
            )
            total_uploaded_bytes += uploaded_bytes
            collected.append(persisted_artifact)
        return collected

    async def _persist_artifact(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
        artifact_limits: SandboxArtifactLimits,
        total_uploaded_bytes: int,
    ) -> tuple[SandboxArtifact, int]:
        if resolved.is_dir():
            return await self._persist_directory(
                job_id=job_id,
                artifact=artifact,
                resolved=resolved,
                artifact_limits=artifact_limits,
                total_uploaded_bytes=total_uploaded_bytes,
            )
        return await self._persist_file(
            job_id=job_id,
            artifact=artifact,
            resolved=resolved,
            artifact_limits=artifact_limits,
            total_uploaded_bytes=total_uploaded_bytes,
        )

    async def _persist_file(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
        artifact_limits: SandboxArtifactLimits,
        total_uploaded_bytes: int,
    ) -> tuple[SandboxArtifact, int]:
        file_size = resolved.stat().st_size
        self._validate_artifact_size(
            artifact=artifact,
            size_bytes=file_size,
            artifact_limits=artifact_limits,
        )
        self._validate_total_size(
            artifact=artifact,
            next_total_bytes=total_uploaded_bytes + file_size,
            artifact_limits=artifact_limits,
        )

        async with aiofiles.open(resolved, "rb") as f:
            content = await f.read()

        content_type = (
            mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        )
        upload_info = await self._upload_artifact(
            content=content,
            content_type=content_type,
            filename=f"{job_id}_{resolved.name}",
        )
        return (
            SandboxArtifact(
                path=artifact.path,
                optional=artifact.optional,
                description=artifact.description,
                file_type="file",
                size=len(content),
                checksum=hashlib.sha256(content).hexdigest(),
                content_type=content_type,
                storage_path=upload_info["path"],
                url=upload_info["url"],
                filename=upload_info["filename"],
            ),
            len(content),
        )

    async def _persist_directory(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
        artifact_limits: SandboxArtifactLimits,
        total_uploaded_bytes: int,
    ) -> tuple[SandboxArtifact, int]:
        archive_base = resolved.parent / f"{resolved.name}__artifact"
        archive_path = Path(
            shutil.make_archive(str(archive_base), "zip", root_dir=resolved)
        )
        try:
            archive_size = archive_path.stat().st_size
            self._validate_artifact_size(
                artifact=artifact,
                size_bytes=archive_size,
                artifact_limits=artifact_limits,
            )
            self._validate_total_size(
                artifact=artifact,
                next_total_bytes=total_uploaded_bytes + archive_size,
                artifact_limits=artifact_limits,
            )
            async with aiofiles.open(archive_path, "rb") as f:
                content = await f.read()
        finally:
            if archive_path.exists():
                archive_path.unlink()

        upload_info = await self._upload_artifact(
            content=content,
            content_type="application/zip",
            filename=f"{job_id}_{resolved.name}.zip",
        )
        size = sum(
            path.stat().st_size for path in resolved.rglob("*") if path.is_file()
        )
        return (
            SandboxArtifact(
                path=artifact.path,
                optional=artifact.optional,
                description=artifact.description,
                file_type="directory",
                size=size,
                checksum=hashlib.sha256(content).hexdigest(),
                content_type="application/zip",
                storage_path=upload_info["path"],
                url=upload_info["url"],
                filename=upload_info["filename"],
            ),
            len(content),
        )

    def _artifact_limit_bytes(self, artifact_limits: SandboxArtifactLimits) -> int:
        return int(artifact_limits.max_size_mb * 1024 * 1024)

    def _artifact_total_limit_bytes(
        self, artifact_limits: SandboxArtifactLimits
    ) -> int:
        return int(artifact_limits.max_total_size_mb * 1024 * 1024)

    def _validate_artifact_size(
        self,
        *,
        artifact: SandboxArtifactSpec,
        size_bytes: int,
        artifact_limits: SandboxArtifactLimits,
    ) -> None:
        limit_bytes = self._artifact_limit_bytes(artifact_limits)
        if size_bytes > limit_bytes:
            raise ValueError(
                f"Artifact '{artifact.path}' is {size_bytes} bytes, exceeding per-file limit {limit_bytes} bytes"
            )

    def _validate_total_size(
        self,
        *,
        artifact: SandboxArtifactSpec,
        next_total_bytes: int,
        artifact_limits: SandboxArtifactLimits,
    ) -> None:
        limit_bytes = self._artifact_total_limit_bytes(artifact_limits)
        if next_total_bytes > limit_bytes:
            raise ValueError(
                f"Artifact '{artifact.path}' would raise total artifact size to {next_total_bytes} bytes, exceeding total limit {limit_bytes} bytes"
            )

    def _upload_base_url(self) -> str:
        if settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL:
            return settings.SANDBOX_ARTIFACT_UPLOAD_BASE_URL.rstrip("/")

        api_base_url = (settings.API_BASE_URL or "").strip()
        if not api_base_url:
            return "http://backend:8000"

        parts = urlsplit(api_base_url)
        if parts.hostname not in {"localhost", "127.0.0.1"}:
            return api_base_url.rstrip("/")

        if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
            return "http://backend:8000"

        return api_base_url.rstrip("/")

    def _upload_headers(self, *, content: bytes, filename: str) -> dict[str, str]:
        api_key = settings.SANDBOX_ARTIFACT_UPLOAD_API_KEY
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}

        timestamp = str(int(time.time()))
        digest = hashlib.sha256(content).hexdigest()
        payload = f"{timestamp}:{filename}:{digest}".encode("utf-8")
        signature = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return {
            self.INTERNAL_TIMESTAMP_HEADER: timestamp,
            self.INTERNAL_SIGNATURE_HEADER: signature,
        }

    async def _upload_artifact(
        self,
        *,
        content: bytes,
        content_type: str,
        filename: str,
    ) -> dict[str, Any]:
        url = f"{self._upload_base_url()}{self.UPLOAD_ENDPOINT}"
        headers = self._upload_headers(content=content, filename=filename)
        timeout = httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS)
        files = {"file": (filename, content, content_type)}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, files=files, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or str(exc)
            raise ValueError(f"Sandbox artifact upload failed: {detail}") from exc
        except httpx.HTTPError as exc:
            raise ValueError(f"Sandbox artifact upload failed: {exc}") from exc

        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Sandbox artifact upload failed: missing response data")
        required_keys = {"path", "url", "filename", "size", "content_type"}
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise ValueError(
                f"Sandbox artifact upload failed: missing response fields {', '.join(sorted(missing))}"
            )
        return data


def artifact_manifest(paths: list[str]) -> list[SandboxArtifactSpec]:
    return [SandboxArtifactSpec(path=path) for path in paths]
