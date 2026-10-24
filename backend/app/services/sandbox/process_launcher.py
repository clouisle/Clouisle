"""Sandbox process launcher."""

from __future__ import annotations

import asyncio
import math
import os
import re
import shutil
import signal
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

from .egress_proxy import SandboxEgressProxy

_session_lock_fd: ContextVar[int | None] = ContextVar(
    "sandbox_session_lock_fd", default=None
)

#: Shared upper bound for one execution's stdout+stderr logs. Reaching it stops
#: the process; the in-memory preview is bounded separately by
#: ``max_stdout_kb``/``max_stderr_kb``.
MAX_EXECUTION_LOG_BYTES = 8 * 1024 * 1024
_LOG_STEM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


@dataclass
class ProcessLaunchResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stdout_log: str | None = None
    stderr_log: str | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_lines: int | None = None
    stderr_lines: int | None = None


@dataclass
class _StreamCapture:
    payload: bytes = b""
    truncated: bool = False
    total_bytes: int = 0
    lines: int = 0


class _LogBudget:
    """Shared byte budget for one execution's stdout and stderr logs."""

    def __init__(self, limit_bytes: int):
        self.remaining = limit_bytes


class SandboxIsolationError(RuntimeError):
    """Raised when the configured filesystem jail cannot be created."""


class SandboxOutputLimitError(RuntimeError):
    """Raised when an execution stream exceeds its persisted log budget."""

    def __init__(
        self,
        limit_bytes: int,
        *,
        stream: str | None = None,
        log_path: str | None = None,
    ):
        self.limit_bytes = limit_bytes
        self.stream = stream
        self.log_path = log_path
        super().__init__(
            "Sandbox command output exceeded the "
            f"{limit_bytes // (1024 * 1024)} MB execution log limit; "
            "the process was stopped and its log is partial"
        )


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
        log_dir: str | None = None,
        log_stem: str | None = None,
    ) -> ProcessLaunchResult:
        if network_proxy is not None and not self.filesystem_isolation_enabled:
            raise SandboxIsolationError(
                "Allowlisted sandbox egress requires filesystem isolation"
            )
        stdout_log_path, stderr_log_path = self._execution_log_paths(log_dir, log_stem)
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
        stdout_handle = (
            stdout_log_path.open("wb") if stdout_log_path is not None else None
        )
        stderr_handle = (
            stderr_log_path.open("wb") if stderr_log_path is not None else None
        )
        process: asyncio.subprocess.Process | None = None
        stdout_task: asyncio.Task[_StreamCapture] | None = None
        stderr_task: asyncio.Task[_StreamCapture] | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *launch_command,
                cwd=launch_cwd,
                env=launch_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
                **inherited,
            )
            log_budget = (
                _LogBudget(MAX_EXECUTION_LOG_BYTES)
                if stdout_handle is not None or stderr_handle is not None
                else None
            )
            stdout_task = asyncio.create_task(
                self._read_bounded(
                    process.stdout,
                    max_stdout_kb * 1024,
                    log_handle=stdout_handle,
                    log_budget=log_budget,
                    stream_name="stdout",
                )
            )
            stderr_task = asyncio.create_task(
                self._read_bounded(
                    process.stderr,
                    max_stderr_kb * 1024,
                    log_handle=stderr_handle,
                    log_budget=log_budget,
                    stream_name="stderr",
                )
            )
            limit_hit = asyncio.get_running_loop().create_future()
            limit_error: list[SandboxOutputLimitError] = []

            def observe_reader(task: asyncio.Task[_StreamCapture]) -> None:
                if task.cancelled():
                    return
                error = task.exception()
                if isinstance(error, SandboxOutputLimitError):
                    limit_error.append(error)
                    if not limit_hit.done():
                        limit_hit.set_result(None)

            stdout_task.add_done_callback(observe_reader)
            stderr_task.add_done_callback(observe_reader)
            wait_task = asyncio.ensure_future(process.wait())
            timed_out = False
            if timeout_seconds is None:
                await asyncio.wait(
                    {wait_task, limit_hit}, return_when=asyncio.FIRST_COMPLETED
                )
            else:
                await asyncio.wait(
                    {wait_task, limit_hit},
                    timeout=timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            if not limit_hit.done():
                limit_hit.cancel()
            if limit_hit.done() and not limit_hit.cancelled():
                await self._terminate_process_group(process)
                for task in (stdout_task, stderr_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise limit_error[0]
            if wait_task.cancelled():
                for task in (stdout_task, stderr_task):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                raise asyncio.CancelledError
            if not wait_task.done():
                timed_out = True
                await self._terminate_process_group(process)
                if not wait_task.done():
                    wait_task.cancel()
                captures = await self._captures_after_stop(stdout_task, stderr_task)
            else:
                try:
                    captures = await asyncio.gather(stdout_task, stderr_task)
                except SandboxOutputLimitError:
                    for task in (stdout_task, stderr_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        stdout_task, stderr_task, return_exceptions=True
                    )
                    raise
                except Exception:
                    for task in (stdout_task, stderr_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        stdout_task, stderr_task, return_exceptions=True
                    )
                    raise
            if lock_fd is not None and not timed_out:
                # A completed tool cannot leave background writers in the workspace.
                self._kill_remaining_process_group(process)
            stdout_capture, stderr_capture = captures
            stderr = self._decode_output(
                stderr_capture.payload, stderr_capture.truncated
            )
            if timed_out:
                timeout_message = f"Execution timeout ({timeout_seconds}s)"
                stderr = f"{timeout_message}\n{stderr}" if stderr else timeout_message
            return self._add_network_diagnostics(
                ProcessLaunchResult(
                    exit_code=-1 if timed_out else (process.returncode or 0),
                    stdout=self._decode_output(
                        stdout_capture.payload, stdout_capture.truncated
                    ),
                    stderr=stderr,
                    timed_out=timed_out,
                    stdout_log=str(stdout_log_path) if stdout_log_path else None,
                    stderr_log=str(stderr_log_path) if stderr_log_path else None,
                    stdout_truncated=stdout_capture.truncated,
                    stderr_truncated=stderr_capture.truncated,
                    stdout_lines=stdout_capture.lines
                    if stdout_log_path is not None
                    else None,
                    stderr_lines=stderr_capture.lines
                    if stderr_log_path is not None
                    else None,
                ),
                network_proxy,
            )
        except asyncio.CancelledError:
            if process is not None:
                await self._terminate_process_group(process)
            for task in (stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
            raise
        finally:
            for handle in (stdout_handle, stderr_handle):
                if handle is not None:
                    handle.close()

    @staticmethod
    def _execution_log_paths(
        log_dir: str | None, log_stem: str | None
    ) -> tuple[Path | None, Path | None]:
        if log_dir is None or log_stem is None:
            return None, None
        if not _LOG_STEM_RE.fullmatch(log_stem):
            raise ValueError("Invalid execution log stem")
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True)
        return (
            directory / f"{log_stem}.stdout.log",
            directory / f"{log_stem}.stderr.log",
        )

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
    async def _captures_after_stop(
        *tasks: asyncio.Task[_StreamCapture],
    ) -> tuple[_StreamCapture, _StreamCapture]:
        """Collect killed-process output without waiting on an unclosed stdout."""
        _, pending = await asyncio.wait(tasks, timeout=1.0)
        for task in pending:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        captures: list[_StreamCapture] = []
        for result in results:
            if isinstance(result, SandboxOutputLimitError):
                raise result
            captures.append(
                result if isinstance(result, _StreamCapture) else _StreamCapture()
            )
        return captures[0], captures[1]

    @staticmethod
    async def _read_bounded(
        stream: asyncio.StreamReader | None,
        max_bytes: int,
        *,
        log_handle: Any | None = None,
        log_budget: _LogBudget | None = None,
        stream_name: str | None = None,
    ) -> _StreamCapture:
        if stream is None:
            return _StreamCapture()

        max_bytes = max(0, max_bytes)
        capture = _StreamCapture()
        output = bytearray()
        total_newlines = 0
        last_byte = b""
        while chunk := await stream.read(64 * 1024):
            capture.total_bytes += len(chunk)
            total_newlines += chunk.count(b"\n")
            last_byte = chunk[-1:]
            remaining = max_bytes - len(output)
            if remaining > 0:
                output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                capture.truncated = True
            if log_handle is not None:
                budget = log_budget or _LogBudget(MAX_EXECUTION_LOG_BYTES)
                if len(chunk) > budget.remaining:
                    raise SandboxOutputLimitError(
                        MAX_EXECUTION_LOG_BYTES,
                        stream=stream_name,
                        log_path=getattr(log_handle, "name", None),
                    )
                budget.remaining -= len(chunk)
                log_handle.write(chunk)
        capture.lines = total_newlines + (
            1 if capture.total_bytes and last_byte != b"\n" else 0
        )
        if log_handle is not None:
            log_handle.flush()
        capture.payload = bytes(output)
        return capture

    @staticmethod
    def _decode_output(payload: bytes, truncated: bool) -> str:
        text = payload.decode("utf-8", errors="replace")
        if truncated:
            return text + "\n...<truncated>"
        return text
