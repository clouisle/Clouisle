from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.bash import BashSandboxTool


@pytest.mark.anyio
async def test_bash_tool_allows_running_workspace_python_script():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute("python3 output/create_doc.py")

    assert result["success"] is True
    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "python3 output/create_doc.py"]
    assert job.cwd == "/workspace"


@pytest.mark.anyio
async def test_bash_tool_maps_workspace_paths_to_relative_paths():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("ls /workspace/output")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "ls ./output"]


@pytest.mark.anyio
async def test_bash_tool_maps_workspace_paths_from_nested_cwd():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("ls /workspace/output", cwd="/workspace/skill/demo")

    job = mock_submit.await_args.args[0]
    assert job.cwd == "/workspace/skill/demo"
    assert job.command == ["bash", "-c", "ls ../../output"]


@pytest.mark.anyio
async def test_bash_tool_allows_cd_inside_workspace():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("cd /workspace/output && pwd")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "cd ./output && pwd"]


@pytest.mark.anyio
async def test_bash_tool_allows_cd_outside_workspace():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("cd /tmp && pwd")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "cd /tmp && pwd"]


@pytest.mark.anyio
async def test_bash_tool_allows_pip_install():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("pip install python-docx")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "python3 -m pip install python-docx"]


@pytest.mark.anyio
async def test_bash_tool_allows_python_m_pip_install():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("python3 -m pip install python-docx")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "python3 -m pip install python-docx"]


@pytest.mark.anyio
async def test_bash_tool_allows_arbitrary_pip_invocations():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("pip uninstall python-docx")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "pip uninstall python-docx"]


@pytest.mark.anyio
async def test_bash_tool_allows_common_workspace_commands():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute(
            "mkdir -p output && cp create_docx.py output/create_docx.py && which python3"
        )

    job = mock_submit.await_args.args[0]
    assert job.command == [
        "bash",
        "-c",
        "mkdir -p output && cp create_docx.py output/create_docx.py && which python3",
    ]


@pytest.mark.anyio
async def test_bash_tool_allows_common_command_paths_outside_workspace():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("cp /etc/passwd output/passwd")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "cp /etc/passwd output/passwd"]


@pytest.mark.anyio
async def test_bash_tool_allows_npm_install():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("npm install mammoth")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "npm install mammoth"]


@pytest.mark.anyio
async def test_bash_tool_allows_npm_run():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("npm run build")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "npm run build"]


@pytest.mark.anyio
async def test_bash_tool_allows_inline_python_execution():
    tool = BashSandboxTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                stdout="ok\n",
                stderr="",
                metadata=SimpleNamespace(exit_code=0),
                status=SimpleNamespace(value="completed"),
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute("python3 -c 'print(1)'")

    job = mock_submit.await_args.args[0]
    assert job.command == ["bash", "-c", "python3 -c 'print(1)'"]
