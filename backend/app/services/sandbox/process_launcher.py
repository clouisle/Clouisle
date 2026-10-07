"""Sandbox process launcher."""

from __future__ import annotations

import asyncio
import math
import os
import shutil
import signal
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import sys

from .egress_proxy import SandboxEgressProxy

_session_lock_fd: ContextVar[int | None] = ContextVar(
    "sandbox_session_lock_fd", default=None
)


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
        timeout_seconds: float | None = 30.0,
        max_stdout_kb: int = 256,
        max_stderr_kb: int = 256,
        workspace_root: str | None = None,
        cache_root: str | None = None,
        network_proxy: SandboxEgressProxy | None = None,
    ) -> ProcessLaunchResult:
        if network_proxy is not None and not self.filesystem_isolation_enabled:
            raise SandboxIsolationError(
                "Allowlisted sandbox egress requires filesystem isolation"
            )
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
                network_proxy=network_proxy,
                timeout_seconds=timeout_seconds,
            )

        lock_fd = _session_lock_fd.get()
        # The isolated payload must not receive a host lock descriptor.
        inherited = (
            {"pass_fds": (lock_fd,)}
            if lock_fd is not None and not self.filesystem_isolation_enabled
            else {}
        )
        process = await asyncio.create_subprocess_exec(
            *launch_command,
            cwd=launch_cwd,
            env=launch_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            **inherited,
        )

        stdout_task = asyncio.create_task(
            self._read_bounded(process.stdout, max_stdout_kb * 1024)
        )
        stderr_task = asyncio.create_task(
            self._read_bounded(process.stderr, max_stderr_kb * 1024)
        )
        completion = asyncio.gather(process.wait(), stdout_task, stderr_task)
        try:
            if timeout_seconds is None:
                output = await completion
            else:
                output = await asyncio.wait_for(completion, timeout=timeout_seconds)
            _, (stdout, stdout_truncated), (stderr, stderr_truncated) = output
            if lock_fd is not None:
                # A completed tool cannot leave background writers in the workspace.
                self._kill_remaining_process_group(process)
            return self._add_network_diagnostics(
                ProcessLaunchResult(
                    exit_code=process.returncode or 0,
                    stdout=self._decode_output(stdout, stdout_truncated),
                    stderr=self._decode_output(stderr, stderr_truncated),
                ),
                network_proxy,
            )
        except asyncio.TimeoutError:
            await self._terminate_process_group(process)
            return self._add_network_diagnostics(
                ProcessLaunchResult(
                    exit_code=-1,
                    stderr=f"Execution timeout ({timeout_seconds}s)",
                    timed_out=True,
                ),
                network_proxy,
            )
        except asyncio.CancelledError:
            await self._terminate_process_group(process)
            raise

    def _isolated_launch(
        self,
        command: list[str],
        *,
        cwd: str | None,
        env: dict[str, str] | None,
        workspace_root: str | None,
        cache_root: str | None,
        network_proxy: SandboxEgressProxy | None,
        timeout_seconds: float | None,
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
            "--unshare-net",
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

        if network_proxy is not None:
            bridge_script = Path(__file__).with_name("network_bridge.py")
            if not bridge_script.is_file():
                bridge_script = bridge_script.with_suffix(".pyc")
            if not bridge_script.is_file():
                raise SandboxIsolationError("Sandbox network bridge script is missing")
            socket_name = network_proxy.socket_path.name
            proxy_mount = "/run/clouisle-sandbox-egress"
            bridge_mount = f"/tmp/clouisle-network-bridge{bridge_script.suffix}"
            isolated_command.extend(
                [
                    "--dir",
                    "/run",
                    "--dir",
                    proxy_mount,
                    "--ro-bind",
                    str(network_proxy.socket_path.parent),
                    proxy_mount,
                    "--ro-bind",
                    str(bridge_script),
                    bridge_mount,
                ]
            )
            mapped_command = [
                str(Path(sys.executable).resolve()),
                bridge_mount,
                "--proxy-socket",
                f"{proxy_mount}/{socket_name}",
                "--",
                *mapped_command,
            ]
        from app.core.config import settings

        prlimit_binary = shutil.which("prlimit")
        if prlimit_binary is None:
            raise SandboxIsolationError("Sandbox resource limiter not found: prlimit")
        cpu_seconds = settings.SANDBOX_TASK_MAX_CPU_SECONDS
        if timeout_seconds is not None:
            cpu_seconds = min(cpu_seconds, max(1, math.ceil(timeout_seconds)))
        memory_bytes = settings.SANDBOX_TASK_MEMORY_MB * 1024 * 1024
        max_file_bytes = settings.SANDBOX_TASK_MAX_FILE_SIZE_MB * 1024 * 1024
        max_open_files = settings.SANDBOX_TASK_MAX_OPEN_FILES
        mapped_command = [
            prlimit_binary,
            f"--as={memory_bytes}:{memory_bytes}",
            f"--cpu={cpu_seconds}:{cpu_seconds}",
            f"--fsize={max_file_bytes}:{max_file_bytes}",
            f"--nofile={max_open_files}:{max_open_files}",
            "--",
            *mapped_command,
        ]
        isolated_command.extend(["--chdir", logical_cwd])
        if network_proxy is None:
            isolated_command.extend(["--cap-drop", "ALL"])
        isolated_command.extend(["--", *mapped_command])
        return isolated_command, None, mapped_env

    @staticmethod
    def _add_network_diagnostics(
        result: ProcessLaunchResult,
        network_proxy: SandboxEgressProxy | None,
    ) -> ProcessLaunchResult:
        if network_proxy is None:
            return result
        diagnostics = network_proxy.blocked_diagnostics
        if diagnostics:
            result.stderr = "\n".join(
                part for part in (result.stderr, *diagnostics) if part
            )
        return result

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
            pass
        finally:
            self._kill_remaining_process_group(process)
        await process.wait()

    def _kill_remaining_process_group(
        self, process: asyncio.subprocess.Process
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    @staticmethod
    async def _read_bounded(
        stream: asyncio.StreamReader | None,
        max_bytes: int,
    ) -> tuple[bytes, bool]:
        if stream is None:
            return b"", False

        max_bytes = max(0, max_bytes)
        output = bytearray()
        truncated = False
        while chunk := await stream.read(64 * 1024):
            remaining = max_bytes - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        return bytes(output), truncated

    @staticmethod
    def _decode_output(payload: bytes, truncated: bool) -> str:
        text = payload.decode("utf-8", errors="replace")
        if truncated:
            return text + "\n...<truncated>"
        return text
