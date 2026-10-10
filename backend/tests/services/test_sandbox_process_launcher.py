import asyncio
import subprocess
import sys
import tracemalloc
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.services.sandbox.egress_proxy import SandboxEgressProxy
from app.services.sandbox.process_launcher import (
    SandboxIsolationError,
    SandboxProcessLauncher,
)


@pytest.mark.asyncio
async def test_launch_collects_output_and_truncates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"abcdef")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_data(b"error")
    stderr.feed_eof()
    process = Mock(returncode=3, stdout=stdout, stderr=stderr)
    process.wait = AsyncMock(return_value=3)
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)

    result = await launcher.launch(
        ["python", "script.py"],
        cwd="/tmp",
        env={"MODE": "test"},
        max_stdout_kb=0,
        max_stderr_kb=0,
    )

    assert result.exit_code == 3
    assert result.stdout == "\n...<truncated>"
    assert result.stderr == "\n...<truncated>"
    create_process.assert_awaited_once_with(
        "python",
        "script.py",
        cwd="/tmp",
        env={"MODE": "test"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    process.communicate.assert_not_called()


@pytest.mark.asyncio
async def test_launch_bounds_memory_for_large_child_output() -> None:
    code = (
        "import os\n"
        "chunk = b'x' * 65536\n"
        "for _ in range(128):\n"
        "    os.write(1, chunk)\n"
        "    os.write(2, chunk)\n"
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    tracemalloc.start()
    baseline, _ = tracemalloc.get_traced_memory()
    try:
        result = await launcher.launch(
            [sys.executable, "-c", code],
            timeout_seconds=10,
            max_stdout_kb=1,
            max_stderr_kb=1,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    marker = "\n...<truncated>"
    assert result.exit_code == 0
    assert result.stdout == "x" * 1024 + marker
    assert result.stderr == "x" * 1024 + marker
    assert peak - baseline < 8 * 1024 * 1024


@pytest.mark.asyncio
async def test_launch_mounts_workspace_at_logical_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "jobs" / "job-1"
    (workspace / "tmp").mkdir(parents=True)
    (workspace / "output").mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"ok")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()
    process = Mock(returncode=0, stdout=stdout, stderr=stderr)
    process.wait = AsyncMock(return_value=0)
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else "/usr/bin/prlimit",
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    result = await launcher.launch(
        [str(workspace / ".venv/bin/python"), str(workspace / "script.py")],
        cwd=str(workspace / "output"),
        env={
            "HOME": str(workspace),
            "PATH": f"{workspace}/.venv/bin:/usr/bin",
        },
        workspace_root=str(workspace),
        cache_root=str(cache),
    )

    assert result.stdout == "ok"
    args = list(create_process.await_args.args)
    assert args[0] == "/usr/bin/bwrap"
    assert ["--bind", str(workspace.resolve()), "/workspace"] == args[
        args.index("--bind") : args.index("--bind") + 3
    ]
    memory_bytes = settings.SANDBOX_TASK_MEMORY_MB * 1024 * 1024
    file_bytes = settings.SANDBOX_TASK_MAX_FILE_SIZE_MB * 1024 * 1024
    cpu_seconds = min(settings.SANDBOX_TASK_MAX_CPU_SECONDS, 30)
    assert args[-8:] == [
        "/usr/bin/prlimit",
        f"--as={memory_bytes}:{memory_bytes}",
        f"--cpu={cpu_seconds}:{cpu_seconds}",
        f"--fsize={file_bytes}:{file_bytes}",
        f"--nofile={settings.SANDBOX_TASK_MAX_OPEN_FILES}:{settings.SANDBOX_TASK_MAX_OPEN_FILES}",
        "--",
        "/workspace/.venv/bin/python",
        "/workspace/script.py",
    ]
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert create_process.await_args.kwargs["cwd"] is None
    assert create_process.await_args.kwargs["env"] == {
        "HOME": "/workspace",
        "PATH": "/workspace/.venv/bin:/usr/bin",
    }


@pytest.mark.asyncio
async def test_isolated_launch_requires_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which",
        lambda _: "/usr/bin/bwrap",
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    with pytest.raises(
        SandboxIsolationError,
        match="require a workspace root",
    ):
        await launcher.launch(["python3"])


@pytest.mark.asyncio
async def test_isolated_launch_fails_closed_without_prlimit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "jobs" / "job-1"
    (workspace / "tmp").mkdir(parents=True)
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    with pytest.raises(SandboxIsolationError, match="resource limiter not found"):
        await launcher.launch(
            ["python3"], cwd=str(workspace), workspace_root=str(workspace)
        )


@pytest.mark.asyncio
async def test_allowlisted_launch_uses_network_namespace_and_bridge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "jobs" / "job-1"
    (workspace / "tmp").mkdir(parents=True)
    stdout = asyncio.StreamReader()
    stdout.feed_data(b"ok")
    stdout.feed_eof()
    stderr = asyncio.StreamReader()
    stderr.feed_eof()
    process = Mock(returncode=0, stdout=stdout, stderr=stderr)
    process.wait = AsyncMock(return_value=0)
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else "/usr/bin/prlimit",
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=True)

    async with SandboxEgressProxy(job_id="job-1", allowed_hosts=["pypi.org"]) as proxy:
        reader, writer = await asyncio.open_unix_connection(str(proxy.socket_path))
        writer.write(
            b"CONNECT blocked.example:443 HTTP/1.1\r\nHost: blocked.example:443\r\n\r\n"
        )
        await writer.drain()
        assert b"HTTP/1.1 403 Forbidden" in await reader.read()
        writer.close()
        await writer.wait_closed()

        result = await launcher.launch(
            ["python3", "-c", "print('ok')"],
            cwd=str(workspace),
            env={"PATH": "/usr/bin"},
            workspace_root=str(workspace),
            network_proxy=proxy,
        )
        args = list(create_process.await_args.args)

        assert result.stdout == "ok"
        assert "[sandbox-network] blocked host=blocked.example" in result.stderr
        assert "--unshare-net" in args
        proxy_mount_index = args.index(str(proxy.socket_path.parent))
        assert args[proxy_mount_index - 1] == "--ro-bind"
        assert args[proxy_mount_index + 1] == "/run/clouisle-sandbox-egress"
        prlimit_index = args.index("/usr/bin/prlimit")
        assert args[prlimit_index + 6 : prlimit_index + 10] == [
            str(Path(sys.executable).resolve()),
            "/tmp/clouisle-network-bridge.py",
            "--proxy-socket",
            "/run/clouisle-sandbox-egress/proxy.sock",
        ]
        assert "--cap-drop" not in args
        assert args[-4:] == ["--", "python3", "-c", "print('ok')"]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux capability semantics")
def test_proxy_bridge_drops_capabilities_before_payload() -> None:
    child_code = (
        "import ctypes; "
        "from app.services.sandbox.network_bridge import "
        "_CapabilityData, _CapabilityHeader, _drop_capabilities; "
        "_drop_capabilities(); "
        "libc = ctypes.CDLL(None); "
        "libc.capget.argtypes = [ctypes.POINTER(_CapabilityHeader), "
        "ctypes.POINTER(_CapabilityData)]; "
        "header = _CapabilityHeader(0x20080522, 0); "
        "data = (_CapabilityData * 2)(); "
        "assert libc.capget(ctypes.byref(header), data) == 0; "
        "assert all(not (entry.effective | entry.permitted | entry.inheritable) "
        "for entry in data); "
        "assert libc.prctl(39, 0, 0, 0, 0) == 1"
    )
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_launch_terminates_timed_out_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(stdout=asyncio.StreamReader(), stderr=asyncio.StreamReader())
    process.wait = AsyncMock()
    create_process = AsyncMock(return_value=process)
    terminate = AsyncMock()

    async def timeout(awaitable, *, timeout):
        if hasattr(awaitable, "cancel"):
            awaitable.cancel()
        else:
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    monkeypatch.setattr(launcher, "_terminate_process_group", terminate)

    result = await launcher.launch(["python"], timeout_seconds=2.5)

    assert result.exit_code == -1
    assert result.stderr == "Execution timeout (2.5s)"
    assert result.timed_out is True
    terminate.assert_awaited_once_with(process)


@pytest.mark.asyncio
async def test_terminate_process_group_escalates_after_graceful_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(pid=42)
    process.wait = AsyncMock()
    killpg = Mock()

    async def timeout(awaitable, *, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr("app.services.sandbox.process_launcher.os.killpg", killpg)
    monkeypatch.setattr(asyncio, "wait_for", timeout)

    await SandboxProcessLauncher()._terminate_process_group(process)

    assert [call.args for call in killpg.call_args_list] == [(42, 15), (42, 9)]
    process.wait.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_cancellation_stops_writer_before_returning(tmp_path):
    ready = tmp_path / "ready"
    late_write = tmp_path / "late-write"
    code = (
        "import time\nfrom pathlib import Path\n"
        f"Path({str(ready)!r}).write_text('ready')\n"
        "time.sleep(0.5)\n"
        f"Path({str(late_write)!r}).write_text('unsafe')\n"
    )
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    task = asyncio.create_task(launcher.launch([sys.executable, "-c", code]))
    try:
        async with asyncio.timeout(5):
            while not ready.exists():
                await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.6)
        assert not late_write.exists()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_session_tool_cannot_leave_background_writer(tmp_path):
    from app.services.sandbox.process_launcher import _session_lock_fd

    ready = tmp_path / "ready"
    late_write = tmp_path / "late-write"
    child = (
        "import time\nfrom pathlib import Path\n"
        f"Path({str(ready)!r}).write_text('ready')\n"
        "time.sleep(0.5)\n"
        f"Path({str(late_write)!r}).write_text('unsafe')\n"
    )
    parent = (
        "import subprocess,sys,time\nfrom pathlib import Path\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"while not Path({str(ready)!r}).exists(): time.sleep(0.01)\n"
        "print('tool finished')\n"
    )
    with (tmp_path / "lease").open("w") as lease:
        token = _session_lock_fd.set(lease.fileno())
        try:
            result = await SandboxProcessLauncher(
                filesystem_isolation_enabled=False
            ).launch([sys.executable, "-c", parent])
        finally:
            _session_lock_fd.reset(token)
    assert result.stdout.strip() == "tool finished"
    await asyncio.sleep(0.6)
    assert not late_write.exists()
