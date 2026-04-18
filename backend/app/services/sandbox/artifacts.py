"""Sandbox artifact persistence helpers."""

from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path

import aiofiles

from app.api.v1.endpoints.upload import save_generated_upload

from .models import SandboxArtifact, SandboxArtifactSpec
from .workspace import SandboxWorkspace, SandboxWorkspaceManager


class SandboxArtifactStore:
    CATEGORY = "sandbox-artifacts"

    def __init__(self, workspace_manager: SandboxWorkspaceManager | None = None):
        self.workspace_manager = workspace_manager or SandboxWorkspaceManager()

    async def collect(
        self,
        *,
        job_id: str,
        artifacts: list[SandboxArtifactSpec],
        workspace: SandboxWorkspace,
    ) -> list[SandboxArtifact]:
        collected: list[SandboxArtifact] = []
        for artifact in artifacts:
            resolved = self.workspace_manager.resolve_workspace_path(workspace, artifact.path)
            if not resolved.exists():
                if artifact.optional:
                    continue
                raise FileNotFoundError(f"Required artifact not found: {artifact.path}")

            collected.append(
                await self._persist_artifact(
                    job_id=job_id,
                    artifact=artifact,
                    resolved=resolved,
                )
            )
        return collected

    async def _persist_artifact(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
    ) -> SandboxArtifact:
        if resolved.is_dir():
            return await self._persist_directory(
                job_id=job_id,
                artifact=artifact,
                resolved=resolved,
            )
        return await self._persist_file(job_id=job_id, artifact=artifact, resolved=resolved)

    async def _persist_file(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
    ) -> SandboxArtifact:
        async with aiofiles.open(resolved, "rb") as f:
            content = await f.read()

        content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        upload_info = await save_generated_upload(
            content=content,
            category=self.CATEGORY,
            content_type=content_type,
            filename=f"{job_id}_{resolved.name}",
        )
        return SandboxArtifact(
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
        )

    async def _persist_directory(
        self,
        *,
        job_id: str,
        artifact: SandboxArtifactSpec,
        resolved: Path,
    ) -> SandboxArtifact:
        archive_base = resolved.parent / f"{resolved.name}__artifact"
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", root_dir=resolved))
        try:
            async with aiofiles.open(archive_path, "rb") as f:
                content = await f.read()
        finally:
            if archive_path.exists():
                archive_path.unlink()

        upload_info = await save_generated_upload(
            content=content,
            category=self.CATEGORY,
            content_type="application/zip",
            filename=f"{job_id}_{resolved.name}.zip",
        )
        size = sum(path.stat().st_size for path in resolved.rglob("*") if path.is_file())
        return SandboxArtifact(
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
        )


def artifact_manifest(paths: list[str]) -> list[SandboxArtifactSpec]:
    return [SandboxArtifactSpec(path=path) for path in paths]
