import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.sandbox.process_launcher import SandboxProcessLauncher


@pytest.mark.asyncio
async def test_launch_collects_output_and_truncates_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(returncode=3)
    process.communicate = AsyncMock(return_value=(b"abcdef", b"error"))
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    launcher = SandboxProcessLauncher()

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


@pytest.mark.asyncio
async def test_launch_terminates_timed_out_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock()
    process.communicate = AsyncMock()
    create_process = AsyncMock(return_value=process)
    terminate = AsyncMock()

    async def timeout(awaitable, *, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(asyncio, "wait_for", timeout)
    launcher = SandboxProcessLauncher()
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
