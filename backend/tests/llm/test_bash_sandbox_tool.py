from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.bash import BashSandboxTool
from app.services.sandbox.models import SandboxResult, SandboxTaskStatus


@pytest.mark.anyio
async def test_execute_maps_workspace_paths_to_session_root_for_command_and_cwd():
    tool = BashSandboxTool(session_id="session-1", workspace_root="/workspace")
    fake_result = SandboxResult(
        job_id="job-1",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout="ok",
        stderr="",
    )
    workspace = type("Workspace", (), {"root": Path("/tmp/sessions/abc")})()

    with patch(
        "app.llm.tools.bash.sandbox_gateway.get_session_workspace",
        new=AsyncMock(return_value=workspace),
    ), patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=fake_result),
    ) as mock_submit:
        result = await tool.execute(
            command="python3 /workspace/script.py && ls /workspace/output",
            cwd="/workspace/subdir",
        )

    assert result["success"] is True
    submitted_job = mock_submit.await_args.args[0]
    assert submitted_job.command == [
        "bash",
        "-c",
        "python3 /tmp/sessions/abc/script.py && ls /tmp/sessions/abc/output",
    ]
    assert submitted_job.cwd == "/workspace/subdir"


@pytest.mark.anyio
async def test_execute_maps_session_root_back_to_workspace_in_output():
    tool = BashSandboxTool(session_id="session-1", workspace_root="/workspace")
    workspace = type("Workspace", (), {"root": Path("/tmp/sessions/abc")})()
    fake_result = SandboxResult(
        job_id="job-1",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout="/tmp/sessions/abc/output/report.txt\n",
        stderr="Trace: /tmp/sessions/abc/script.py\n",
    )

    with patch(
        "app.llm.tools.bash.sandbox_gateway.get_session_workspace",
        new=AsyncMock(return_value=workspace),
    ), patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=fake_result),
    ):
        result = await tool.execute(command="pwd", cwd="/workspace")

    assert result["stdout"] == "/workspace/output/report.txt\n"
    assert result["stderr"] == "Trace: /workspace/script.py\n"


@pytest.mark.anyio
async def test_execute_keeps_runtime_cwd_without_double_mapping():
    tool = BashSandboxTool(session_id="session-1", workspace_root="/workspace")
    workspace = type("Workspace", (), {"root": Path("/tmp/sessions/abc")})()
    fake_result = SandboxResult(
        job_id="job-1",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout="ok",
        stderr="",
    )

    with patch(
        "app.llm.tools.bash.sandbox_gateway.get_session_workspace",
        new=AsyncMock(return_value=workspace),
    ), patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(return_value=fake_result),
    ) as mock_submit:
        await tool.execute(
            command="python3 /workspace/script.py",
            cwd="/tmp/sessions/abc",
        )

    submitted_job = mock_submit.await_args.args[0]
    assert submitted_job.command == ["bash", "-c", "python3 /tmp/sessions/abc/script.py"]
    assert submitted_job.cwd == "/workspace"
