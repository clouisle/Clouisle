"""Deterministic failure-path coverage for the sandbox process launcher.

These tests drive the launcher's stream budget, timeout and cancellation
cleanup with controlled subprocess doubles so every branch is reached without
racing a real child process.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.sandbox import process_launcher as launcher_module
from app.services.sandbox.process_launcher import (
    MAX_EXECUTION_LOG_BYTES,
    SandboxIsolationError,
    SandboxOutputLimitError,
    SandboxProcessLauncher,
)


class _FakeProcess:
    """Minimal ``asyncio.subprocess.Process`` lookalike."""

    def __init__(self, stdout, stderr, *, wait_event=None):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = 0
        self._wait_event = wait_event

    async def wait(self):
        if self._wait_event is not None:
            await self._wait_event.wait()
        return self.returncode


class _GatedStream:
    """Returns one oversized chunk once the gate opens."""

    def __init__(self, gate: asyncio.Event, chunk: bytes, started: asyncio.Event):
        self._gate = gate
        self._chunk = chunk
        self._started = started
        self._sent = False

    async def read(self, _size: int) -> bytes:
        self._started.set()
        await self._gate.wait()
        if self._sent:
            return b""
        self._sent = True
        return self._chunk


class _FailingStream:
    def __init__(self, error: BaseException, delay: float = 0.0):
        self._error = error
        self._delay = delay

    async def read(self, _size: int) -> bytes:
        if self._delay:
            await asyncio.sleep(self._delay)
        raise self._error


class _BlockingStream:
    """Never yields output, so its reader task stays pending."""

    def __init__(self, started: asyncio.Event | None = None):
        self._started = started

    async def read(self, _size: int) -> bytes:
        if self._started is not None:
            self._started.set()
        await asyncio.Event().wait()
        return b""


def _python_launcher() -> SandboxProcessLauncher:
    return SandboxProcessLauncher(filesystem_isolation_enabled=False)


@pytest.mark.asyncio
async def test_log_limit_cancels_reader_still_waiting_for_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wait_event = asyncio.Event()
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"x" * (MAX_EXECUTION_LOG_BYTES + 65536))
    stdout.feed_eof()
    # No EOF: the stderr reader is still blocked when stdout hits the budget.
    stderr = asyncio.StreamReader()
    process = _FakeProcess(stdout, stderr, wait_event=wait_event)
    launcher = _python_launcher()
    terminate = AsyncMock()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    with pytest.raises(SandboxOutputLimitError) as error:
        await launcher.launch(
            ["python"],
            log_dir=str(tmp_path / "logs"),
            log_stem="stderr-still-open",
        )

    assert error.value.stream == "stdout"
    terminate.assert_awaited_once_with(process)
    wait_event.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_simultaneous_log_limit_errors_use_the_first_reported_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wait_event = asyncio.Event()
    gate = asyncio.Event()
    stdout_started = asyncio.Event()
    stderr_started = asyncio.Event()
    chunk = b"x" * (MAX_EXECUTION_LOG_BYTES + 1)
    process = _FakeProcess(
        _GatedStream(gate, chunk, stdout_started),
        _GatedStream(gate, chunk, stderr_started),
        wait_event=wait_event,
    )
    launcher = _python_launcher()
    terminate = AsyncMock()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    task = asyncio.create_task(
        launcher.launch(
            ["python"],
            log_dir=str(tmp_path / "logs"),
            log_stem="both-streams",
        )
    )
    await asyncio.wait_for(
        asyncio.gather(stdout_started.wait(), stderr_started.wait()), timeout=5
    )
    gate.set()

    with pytest.raises(SandboxOutputLimitError) as error:
        await task

    assert error.value.limit_bytes == MAX_EXECUTION_LOG_BYTES
    terminate.assert_awaited_once_with(process)
    wait_event.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_reader_failure_is_surfaced_and_sibling_reader_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = _BlockingStream()
    process = _FakeProcess(
        _FailingStream(RuntimeError("decoder exploded"), delay=0.01), stderr
    )
    launcher = _python_launcher()
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )

    with pytest.raises(RuntimeError, match="decoder exploded"):
        await launcher.launch(["python"], timeout_seconds=5)


@pytest.mark.asyncio
async def test_log_limit_raised_after_process_exit_stops_the_sibling_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stderr = _BlockingStream()
    process = _FakeProcess(
        _FailingStream(
            SandboxOutputLimitError(MAX_EXECUTION_LOG_BYTES, stream="stdout"),
            delay=0.01,
        ),
        stderr,
    )
    launcher = _python_launcher()
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )

    with pytest.raises(SandboxOutputLimitError) as error:
        await launcher.launch(["python"], timeout_seconds=5)

    assert error.value.stream == "stdout"


@pytest.mark.asyncio
async def test_timeout_collects_output_when_process_exits_after_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wait_event = asyncio.Event()
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"partial\n")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_data(b"warn")
    stderr.feed_eof()
    process = _FakeProcess(stdout, stderr, wait_event=wait_event)
    launcher = _python_launcher()

    async def terminate(_process) -> None:
        wait_event.set()
        await asyncio.sleep(0.01)

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    result = await launcher.launch(["python"], timeout_seconds=0.01)

    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.stdout == "partial\n"
    assert result.stderr == "Execution timeout (0.01s)\nwarn"


@pytest.mark.asyncio
async def test_cancellation_while_readers_are_blocked_stops_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wait_event = asyncio.Event()
    started = asyncio.Event()
    process = _FakeProcess(
        _BlockingStream(started),
        _BlockingStream(),
        wait_event=wait_event,
    )
    launcher = _python_launcher()
    terminate = AsyncMock()

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    task = asyncio.create_task(launcher.launch(["python"]))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    terminate.assert_awaited_once_with(process)
    wait_event.set()
    await asyncio.sleep(0)


def test_isolated_launch_falls_back_to_compiled_bridge_without_missing_binds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "jobs" / "job-1"
    (workspace / "tmp").mkdir(parents=True)
    module_dir = tmp_path / "module"
    module_dir.mkdir()
    (module_dir / "network_bridge.pyc").write_bytes(b"bytecode")
    monkeypatch.setattr(
        launcher_module, "__file__", str(module_dir / "process_launcher.py")
    )
    monkeypatch.setattr(
        launcher_module.shutil,
        "which",
        lambda name: {
            "bwrap": "/usr/bin/bwrap",
            "prlimit": "/usr/bin/prlimit",
        }.get(name),
    )
    launcher = SandboxProcessLauncher(
        filesystem_isolation_enabled=True, isolation_binary="bwrap"
    )
    proxy = SimpleNamespace(socket_path=Path("/run/clouisle/proxy.sock"))
    absent_cache = tmp_path / "absent-cache"

    command, cwd, env = launcher._isolated_launch(
        ["python3"],
        cwd=None,
        env=None,
        workspace_root=str(workspace),
        cache_root=str(absent_cache),
        network_proxy=proxy,
        network_unrestricted=False,
        timeout_seconds=None,
    )

    assert cwd is None
    assert env is None
    bridge_mount = next(
        argument
        for argument in command
        if argument.startswith("/tmp/clouisle-network-bridge")
    )
    assert bridge_mount == "/tmp/clouisle-network-bridge.pyc"
    assert str(Path(sys.executable).resolve()) in command
    assert str(absent_cache) not in command
    assert "--cap-drop" not in command
    assert command[-1] == "python3"


def test_isolated_launch_fails_closed_without_bridge_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "jobs" / "job-1"
    (workspace / "tmp").mkdir(parents=True)
    module_dir = tmp_path / "module"
    module_dir.mkdir()
    monkeypatch.setattr(
        launcher_module, "__file__", str(module_dir / "process_launcher.py")
    )
    monkeypatch.setattr(
        launcher_module.shutil,
        "which",
        lambda name: {
            "bwrap": "/usr/bin/bwrap",
            "prlimit": "/usr/bin/prlimit",
        }.get(name),
    )
    launcher = SandboxProcessLauncher(
        filesystem_isolation_enabled=True, isolation_binary="bwrap"
    )
    proxy = SimpleNamespace(socket_path=Path("/run/clouisle/proxy.sock"))

    with pytest.raises(SandboxIsolationError, match="bridge script is missing"):
        launcher._isolated_launch(
            ["python3"],
            cwd=None,
            env=None,
            workspace_root=str(workspace),
            cache_root=None,
            network_proxy=proxy,
            network_unrestricted=False,
            timeout_seconds=5,
        )
