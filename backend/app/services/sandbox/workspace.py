"""Sandbox workspace helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass
class SandboxWorkspace:
    root: Path
    input_dir: Path
    output_dir: Path
    tmp_dir: Path
    logs_dir: Path


class SandboxWorkspaceManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.SANDBOX_WORKSPACE_ROOT)

    @property
    def cache_root(self) -> Path:
        return self.root.parent / "cache"

    def job_root(self, job_id: str) -> Path:
        return self.root / job_id

    def prepare(self, job_id: str) -> SandboxWorkspace:
        root = self.job_root(job_id)
        input_dir = root / "input"
        output_dir = root / "output"
        tmp_dir = root / "tmp"
        logs_dir = root / "logs"

        for path in (root, input_dir, output_dir, tmp_dir, logs_dir):
            path.mkdir(parents=True, exist_ok=True)

        return SandboxWorkspace(
            root=root,
            input_dir=input_dir,
            output_dir=output_dir,
            tmp_dir=tmp_dir,
            logs_dir=logs_dir,
        )

    def cleanup(self, job_id: str) -> None:
        shutil.rmtree(self.job_root(job_id), ignore_errors=True)

    def resolve_workspace_path(self, workspace: SandboxWorkspace, sandbox_path: str) -> Path:
        if sandbox_path == "/workspace":
            resolved = workspace.root
        elif sandbox_path.startswith("/workspace/"):
            resolved = workspace.root / sandbox_path.removeprefix("/workspace/")
        else:
            resolved = workspace.root / sandbox_path.lstrip("/")

        resolved = resolved.resolve()
        workspace_root = workspace.root.resolve()
        if resolved != workspace_root and workspace_root not in resolved.parents:
            raise ValueError(f"Sandbox path escapes workspace: {sandbox_path}")
        return resolved

    def workspace_size_bytes(self, workspace: SandboxWorkspace) -> int:
        total = 0
        for path in workspace.root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        return total
