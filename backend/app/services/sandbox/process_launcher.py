"""Sandbox process launcher."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessLaunchResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class SandboxIsolationError(RuntimeError):
    """Raised when the configured filesystem jail cannot be created."""


class SandboxProcessLauncher:
    RUNTIME_READONLY_ROOTS = (
        "/usr",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/etc",
    )

    def __init__(
        self,
        *,
        filesystem_isolation_enabled: bool | None = None,
        isolation_binary: str | None = None,
    ) -> None:
        from app.core.config import settings

        self.filesystem_isolation_enabled = (
            settings.SANDBOX_FILESYSTEM_ISOLATION_ENABLED
            if filesystem_isolation_enabled is None
            else filesystem_isolation_enabled
        )
        self.isolation_binary = (
            isolation_binary or settings.SANDBOX_FILESYSTEM_ISOLATION_BINARY
        )

    async def launch(
        self,
        command: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        max_stdout_kb: int = 256,
        max_stderr_kb: int = 256,
        workspace_root: str | None = None,
        cache_root: str | None = None,
    ) -> ProcessLaunchResult:
        launch_command = command
        launch_cwd = cwd
        launch_env = env
        if self.filesystem_isolation_enabled:
            launch_command, launch_cwd, launch_env = self._isolated_launch(
                command,
                cwd=cwd,
                env=env,
                workspace_root=workspace_root,
                cache_root=cache_root,
            )

        process = await asyncio.create_subprocess_exec(
            *launch_command,
            cwd=launch_cwd,
            env=launch_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
            return ProcessLaunchResult(
                exit_code=process.returncode or 0,
                stdout=self._truncate_output(stdout, max_stdout_kb),
                stderr=self._truncate_output(stderr, max_stderr_kb),
            )
        except asyncio.TimeoutError:
            await self._terminate_process_group(process)
            return ProcessLaunchResult(
                exit_code=-1,
                stderr=f"Execution timeout ({timeout_seconds}s)",
                timed_out=True,
            )

    def _isolated_launch(
        self,
        command: list[str],
        *,
        cwd: str | None,
        env: dict[str, str] | None,
        workspace_root: str | None,
        cache_root: str | None,
    ) -> tuple[list[str], None, dict[str, str] | None]:
        if not workspace_root:
            raise SandboxIsolationError(
                "Filesystem-isolated sandbox jobs require a workspace root"
            )

        isolation_binary = shutil.which(self.isolation_binary)
        if isolation_binary is None:
            raise SandboxIsolationError(
                f"Sandbox isolation binary not found: {self.isolation_binary}"
            )

        workspace = Path(workspace_root).resolve()
        if not workspace.is_dir():
            raise SandboxIsolationError(f"Sandbox workspace not found: {workspace}")
        logical_cwd = self._logical_workspace_path(cwd or str(workspace), workspace)

        mapped_command = [
            self._map_workspace_value(value, workspace_root, workspace)
            for value in command
        ]
        mapped_env = (
            {
                key: self._map_workspace_value(value, workspace_root, workspace)
                for key, value in env.items()
            }
            if env is not None
            else None
        )

        isolated_command = [
            isolation_binary,
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-uts",
            "--die-with-parent",
            "--hostname",
            "clouisle-sandbox",
        ]
        for source in self.RUNTIME_READONLY_ROOTS:
            if Path(source).exists():
                isolated_command.extend(["--ro-bind", source, source])

        isolated_command.extend(
            [
                "--dir",
                "/proc",
                "--dev",
                "/dev",
                "--bind",
                str(workspace),
                "/workspace",
                "--bind",
                str(workspace / "tmp"),
                "/tmp",
            ]
        )
        if cache_root:
            cache = Path(cache_root).resolve()
            if cache.is_dir():
                isolated_command.extend(self._cache_bind_args(cache))

        isolated_command.extend(["--chdir", logical_cwd, "--", *mapped_command])
        return isolated_command, None, mapped_env

    def _logical_workspace_path(self, cwd: str, workspace: Path) -> str:
        try:
            relative = Path(cwd).resolve().relative_to(workspace)
        except ValueError as exc:
            raise SandboxIsolationError(
                f"Sandbox cwd escapes workspace: {cwd}"
            ) from exc
        if relative == Path("."):
            return "/workspace"
        return f"/workspace/{relative.as_posix()}"

    def _map_workspace_value(
        self,
        value: str,
        workspace_root: str,
        resolved_workspace: Path,
    ) -> str:
        mapped = value
        aliases = sorted(
            {str(Path(workspace_root)), str(resolved_workspace)},
            key=len,
            reverse=True,
        )
        for alias in aliases:
            mapped = mapped.replace(alias, "/workspace")
        return mapped

    def _cache_bind_args(self, cache: Path) -> list[str]:
        destination = Path(cache.anchor)
        args: list[str] = []
        for part in cache.parts[1:-1]:
            destination /= part
            if destination in {Path("/tmp"), Path("/usr"), Path("/etc")}:
                continue
            args.extend(["--dir", str(destination)])
        args.extend(["--ro-bind", str(cache), str(cache)])
        return args

    async def _terminate_process_group(
        self,
        process: asyncio.subprocess.Process,
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            await process.wait()

    def _truncate_output(self, payload: bytes, max_kb: int) -> str:
        text = payload.decode("utf-8", errors="replace")
        max_chars = max_kb * 1024
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...<truncated>"
