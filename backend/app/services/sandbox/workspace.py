"""Sandbox workspace helpers."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import os
import shutil
import stat
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.sandbox.checkpoint import (
    WorkspaceCheckpointStore,
    fsync_directory,
    remove_session_temporary_trees,
    remove_workspace_tree,
    validate_session_id,
)


@dataclass
class SandboxWorkspace:
    root: Path
    input_dir: Path
    output_dir: Path
    tmp_dir: Path
    logs_dir: Path


class SandboxWorkspaceManager:
    def __init__(self, root: str | None = None, *, checkpoint_root: str | None = None):
        self.root = Path(root or settings.SANDBOX_WORKSPACE_ROOT)
        self.sessions_root = self.root / "sessions"
        self.checkpoint_root = Path(
            checkpoint_root
            or getattr(settings, "SANDBOX_CHECKPOINT_ROOT", "")
            or self.root.parent / "checkpoints"
        )
        self.locks_root = self.root.parent / "session-locks"
        runtime = self.root.resolve()
        for external in (self.checkpoint_root, self.locks_root):
            resolved = external.resolve()
            if resolved == runtime or runtime in resolved.parents:
                raise ValueError(
                    "Sandbox checkpoints and locks must be outside the runtime root"
                )
        self.checkpoints = WorkspaceCheckpointStore(
            self.checkpoint_root,
            runtime_cache_root=self.cache_root,
            runtime_python_paths=tuple(settings.SANDBOX_DEFAULT_PYTHON_BINARIES),
        )

    @property
    def cache_root(self) -> Path:
        return self.root.parent / "cache"

    def job_root(self, job_id: str) -> Path:
        return self.root / job_id

    def get_session_root(self, session_id: str) -> Path:
        """Return a confined session path without creating a workspace."""
        validate_session_id(session_id)
        return self.sessions_root / session_id

    @asynccontextmanager
    async def session_lock(
        self,
        session_id: str,
        *,
        deadline_at: float | None = None,
        guard: Callable[[], Awaitable[object]] | None = None,
    ):
        """Serialize local lifecycle operations without blocking the event loop."""
        validate_session_id(session_id)
        self.locks_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.locks_root.is_symlink():
            raise ValueError("Sandbox lock root must not be a symlink")
        fd = os.open(
            self.locks_root / f"{session_id}.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
        )
        acquired = False
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Sandbox session lock must be a regular file")
            while not acquired:
                if deadline_at is not None and time.time() >= deadline_at:
                    raise TimeoutError("Sandbox workspace lock deadline expired")
                if guard is not None:
                    await guard()
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    await asyncio.sleep(0.05)
            yield fd
        finally:
            try:
                if acquired:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        # Never unlink: other processes may still be waiting on this inode.

    @staticmethod
    def _workspace(root: Path) -> SandboxWorkspace:
        return SandboxWorkspace(
            root=root,
            input_dir=root / "input",
            output_dir=root / "output",
            tmp_dir=root / "tmp",
            logs_dir=root / "logs",
        )

    @staticmethod
    def _disk_limit_bytes() -> int:
        limit = settings.SANDBOX_MAX_DISK_MB * 1024 * 1024
        if limit < 0:
            raise ValueError("Sandbox disk limit must not be negative")
        return limit

    def prepare_session(self, session_id: str) -> SandboxWorkspace:
        """Initialize a first-use workspace; lifecycle callers hold session_lock."""
        root = self.get_session_root(session_id)
        if root.is_symlink() or self.sessions_root.is_symlink():
            raise ValueError("Sandbox session root must not be a symlink")
        workspace = self._workspace(root)
        for path in (
            root,
            workspace.input_dir,
            workspace.output_dir,
            workspace.tmp_dir,
            workspace.logs_dir,
        ):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return workspace

    def save_checkpoint(self, session_id: str) -> bool:
        """Save existing runtime data, never creating a missing workspace."""
        if self.sessions_root.is_symlink():
            raise ValueError("Sandbox sessions root must not be a symlink")
        return self.checkpoints.save(
            session_id,
            self.get_session_root(session_id),
            max_bytes=self._disk_limit_bytes(),
        )

    def restore_session(
        self, session_id: str, *, allow_empty: bool = True, force: bool = False
    ) -> SandboxWorkspace:
        """Reuse live data, restore a checkpoint, or initialize genuine first use."""
        root = self.get_session_root(session_id)
        if self.sessions_root.is_symlink():
            raise ValueError("Sandbox sessions root must not be a symlink")
        if not force and (root.exists() or root.is_symlink()):
            if root.is_symlink() or not root.is_dir():
                raise ValueError("Sandbox session root must be a directory")
            return self._workspace(root)
        if self.checkpoints.restore(
            session_id, root, max_bytes=self._disk_limit_bytes(), force=force
        ):
            return self._workspace(root)
        if force or not allow_empty:
            raise FileNotFoundError(
                f"Sandbox workspace and checkpoint are missing: {session_id}"
            )
        return self.prepare_session(session_id)

    def evict_session(self, session_id: str) -> bool:
        """Remove runtime data only after its complete checkpoint is durable."""
        if not self.save_checkpoint(session_id):
            return False
        self.cleanup_session(session_id)
        return True

    def delete_session(self, session_id: str) -> None:
        """Permanently delete both saved and live data under session_lock."""
        self.checkpoints.delete(session_id)
        self.cleanup_session(session_id)
        remove_session_temporary_trees(session_id, self.sessions_root)

    def cleanup_session(self, session_id: str) -> None:
        """Internal runtime-only removal; checkpoint deletion is explicit."""
        if self.sessions_root.is_symlink():
            raise ValueError("Sandbox sessions root must not be a symlink")
        root = self.get_session_root(session_id)
        if root.exists() or root.is_symlink():
            remove_workspace_tree(root)
            fsync_directory(self.sessions_root)

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

    def resolve_workspace_path(
        self, workspace: SandboxWorkspace, sandbox_path: str
    ) -> Path:
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
                    if e.errno == errno.ELOOP:
                        raise ValueError(f"Path contains symlink: {current}") from e
            current = current.parent

    def workspace_size_bytes(self, workspace: SandboxWorkspace) -> int:
        total = 0
        for path in workspace.root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        return total
