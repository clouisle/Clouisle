"""Sandbox workspace helpers."""

from __future__ import annotations

import os
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
        self.sessions_root = self.root / "sessions"

    @property
    def cache_root(self) -> Path:
        return self.root.parent / "cache"

    def job_root(self, job_id: str) -> Path:
        return self.root / job_id

    def get_session_root(self, session_id: str) -> Path:
        """获取会话工作空间根目录"""
        return self.sessions_root / session_id

    def prepare_session(self, session_id: str) -> SandboxWorkspace:
        """创建或复用会话工作空间"""
        root = self.get_session_root(session_id)
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

    def cleanup_session(self, session_id: str) -> None:
        """清理会话工作空间"""
        shutil.rmtree(self.get_session_root(session_id), ignore_errors=True)

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

        # 符号链接防护
        self._check_no_symlinks(resolved, workspace.root)

        workspace_root = workspace.root.resolve()
        if resolved != workspace_root and workspace_root not in resolved.parents:
            raise ValueError(f"Sandbox path escapes workspace: {sandbox_path}")
        return resolved

    def _check_no_symlinks(self, path: Path, workspace_root: Path) -> None:
        """检查已存在路径及父目录链中不存在符号链接"""
        current = path
        while current != workspace_root and current != current.parent:
            if current.exists() or current.is_symlink():
                if current.is_symlink():
                    raise ValueError(f"Path contains symlink: {current}")
                try:
                    fd = os.open(current, os.O_RDONLY | os.O_NOFOLLOW)
                    os.close(fd)
                except OSError as e:
                    if e.errno == 40:  # ELOOP
                        raise ValueError(f"Path contains symlink: {current}") from e
            current = current.parent

    def workspace_size_bytes(self, workspace: SandboxWorkspace) -> int:
        total = 0
        for path in workspace.root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        return total
