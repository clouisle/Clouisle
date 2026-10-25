import asyncio
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.tools import bash as bash_module
from app.llm.tools.bash import BashSandboxTool, execute_bash
from app.core.config import settings
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.process_launcher import (
    SandboxIsolationError,
    SandboxOutputLimitError,
    SandboxProcessLauncher,
)
from app.utils.sandbox_output import preview_stream, render_sandbox_output


def test_renderer_falls_back_to_compact_json_for_unknown_shapes():
    assert render_sandbox_output("unknown", [1, 2]) == "[1,2]"
    assert render_sandbox_output("unknown", {"a": 1}) == '{"a":1}'
    assert render_sandbox_output("bash", "text") == '"text"'


def test_bash_renderer_success_without_status_and_without_log_location():
    rendered = render_sandbox_output(
        "bash",
        {
            "success": True,
            "stdout": "done",
            "stdout_omitted_lines": 2,
            "stdout_preview_chars_truncated": True,
        },
    )

    assert rendered.startswith("Status: completed")
    assert "clips long line content" in rendered
    assert "the omitted portion is not available" in rendered


def test_bash_renderer_failed_without_status_marks_partial_log():
    rendered = render_sandbox_output(
        "bash",
        {
            "success": False,
            "stdout_log": "/workspace/logs/exec-1.stdout.log",
            "stdout_log_partial": True,
        },
    )

    assert rendered.startswith("Status: failed")
    assert "partial log: /workspace/logs/exec-1.stdout.log" in rendered
    assert "stopped at the output limit" in rendered


def test_read_renderer_error_variants_keep_or_omit_header():
    assert (
        render_sandbox_output("read", {"error": "denied", "path": "/workspace/a.txt"})
        == "/workspace/a.txt\nError: denied"
    )
    assert render_sandbox_output("read", {"error": "denied"}) == "Error: denied"
    assert (
        render_sandbox_output("read", {"success": False, "path": "/workspace/a.txt"})
        == "/workspace/a.txt\nRead failed."
    )
    assert render_sandbox_output("read", {"success": False}) == "Read failed."


def test_edit_write_renderers_error_and_minimal_fields():
    assert render_sandbox_output("edit", {"error": "stale"}) == "Error: stale"
    assert (
        render_sandbox_output(
            "edit",
            {"success": True, "path": "/workspace/a.txt", "edits": 1, "changed": 1},
        )
        == "Edited /workspace/a.txt: 1 of 1 operation(s) changed."
    )
    assert render_sandbox_output("write", {"error": "denied"}) == "Error: denied"
    assert (
        render_sandbox_output("write", {"success": False, "path": "/workspace/a.txt"})
        == "Wrote /workspace/a.txt."
    )


def test_artifact_renderer_handles_non_list_items_and_minimal_fields():
    assert (
        render_sandbox_output("artifact", {"artifacts": "bad"}) == '{"artifacts":"bad"}'
    )
    rendered = render_sandbox_output(
        "artifact",
        {
            "artifacts": [
                "ignored",
                {"path": "/workspace/plain.txt"},
                {"filename": "x"},
            ],
            "instruction": "Use links.",
        },
    )

    assert "Collected 3 file(s)." in rendered
    assert "- /workspace/plain.txt" in rendered
    assert "- x" in rendered
    assert "Use links." in rendered


def test_preview_stream_empty_and_single_line():
    assert preview_stream(None) == ("", 0, False)
    assert preview_stream("one line") == ("one line", 0, False)


def test_bash_helpers_cover_workspace_and_cwd_normalization(monkeypatch):
    tool = BashSandboxTool()
    assert tool._normalize_logical_cwd("/workspace", Path("/workspace")) == "/workspace"
    assert (
        tool._normalize_logical_cwd("/workspace/sub", Path("/workspace"))
        == "/workspace/sub"
    )
    assert tool._normalize_logical_cwd("/elsewhere", Path("/workspace")) == "/elsewhere"

    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", True)
    assert asyncio.run(tool._runtime_workspace_root()) == Path("/workspace")

    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    assert asyncio.run(BashSandboxTool()._runtime_workspace_root()) == Path(
        "/workspace"
    )

    with pytest.raises(bash_module.BashRootScanError):
        BashSandboxTool(session_id="s")._confine_find_root_scans(
            "find /tmp / -name x | head"
        )


@pytest.mark.anyio
async def test_runtime_workspace_handles_missing_session_workspace(monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
    monkeypatch.setattr(
        bash_module.sandbox_gateway,
        "get_session_workspace",
        AsyncMock(return_value=None),
    )
    tool = BashSandboxTool(session_id="s", workspace_root="/fallback")

    assert await tool._runtime_workspace_root() == Path("/fallback")


@pytest.mark.anyio
async def test_bash_tool_minimal_success_and_flags(monkeypatch):
    result = SandboxResult(
        job_id="job",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout_truncated=True,
        stdout_log_partial=True,
        metadata=SandboxExecutionMetadata(),
    )
    monkeypatch.setattr(
        bash_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(return_value=result),
    )

    tool_result = await BashSandboxTool(session_id="s").execute("true")

    assert "exit_code" not in tool_result.display_result
    assert "duration_ms" not in tool_result.display_result
    assert tool_result.display_result["stdout_capture_truncated"] is True
    assert tool_result.display_result["stdout_log_partial"] is True
    assert "stderr" not in tool_result.display_result


@pytest.mark.anyio
async def test_bash_tool_exception_becomes_failed_result(monkeypatch):
    monkeypatch.setattr(
        bash_module.sandbox_gateway,
        "submit_and_wait",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    result = await BashSandboxTool(session_id="s").execute("true")

    assert result.display_result["status"] == "failed"
    assert result.display_result["error"] == "boom"


@pytest.mark.anyio
async def test_execute_bash_convenience_wraps_tool(monkeypatch):
    execute = AsyncMock(return_value="ok")
    monkeypatch.setattr(BashSandboxTool, "execute", execute)

    assert await execute_bash("true", timeout=3) == "ok"
    assert execute.await_args.kwargs == {"command": "true", "timeout": 3}


def test_launcher_log_path_helpers(tmp_path):
    assert SandboxProcessLauncher._execution_log_paths(None, None) == (None, None)
    with pytest.raises(ValueError, match="Invalid execution log stem"):
        SandboxProcessLauncher._execution_log_paths(str(tmp_path), "../bad")
    stdout_log, stderr_log = SandboxProcessLauncher._execution_log_paths(
        str(tmp_path), "exec-1"
    )
    assert stdout_log == tmp_path / "exec-1.stdout.log"
    assert stderr_log == tmp_path / "exec-1.stderr.log"


@pytest.mark.anyio
async def test_launcher_reader_without_stream_and_without_budget(tmp_path):
    empty = await SandboxProcessLauncher._read_bounded(None, 10)
    assert empty.payload == b""
    assert empty.lines == 0

    stream = asyncio.StreamReader()
    stream.feed_data(b"a\nb")
    stream.feed_eof()
    handle = io.BytesIO()
    capture = await SandboxProcessLauncher._read_bounded(
        stream, 1024, log_handle=handle
    )

    assert capture.lines == 2
    assert handle.getvalue() == b"a\nb"


@pytest.mark.anyio
async def test_captures_after_stop_raises_limit_and_fills_missing_tasks():
    async def limit_task():
        raise SandboxOutputLimitError(8)

    async def broken_task():
        raise ValueError("read failed")

    with pytest.raises(SandboxOutputLimitError):
        await SandboxProcessLauncher._captures_after_stop(
            asyncio.create_task(limit_task()),
            asyncio.create_task(broken_task()),
        )


def test_launcher_network_policy_and_workspace_path_helpers(tmp_path):
    with pytest.raises(SandboxIsolationError, match="Allowlisted sandbox egress"):
        asyncio.run(
            SandboxProcessLauncher(filesystem_isolation_enabled=False).launch(
                ["python"], network_proxy=SimpleNamespace()
            )
        )

    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    workspace = tmp_path / "workspace"
    (workspace / "sub").mkdir(parents=True)
    assert launcher._logical_workspace_path(str(workspace), workspace) == "/workspace"
    assert (
        launcher._logical_workspace_path(str(workspace / "sub"), workspace)
        == "/workspace/sub"
    )
    with pytest.raises(SandboxIsolationError, match="escapes workspace"):
        launcher._logical_workspace_path(str(tmp_path / "other"), workspace)
    assert launcher._cache_bind_args(Path("/tmp/cache"))[-3:] == [
        "--ro-bind",
        "/tmp/cache",
        "/tmp/cache",
    ]


def test_launcher_adds_network_diagnostics():
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    result = SimpleNamespace(stderr="err")
    proxy = SimpleNamespace(blocked_diagnostics=["blocked example.com"])

    updated = launcher._add_network_diagnostics(result, proxy)

    assert updated.stderr == "err\nblocked example.com"
    assert launcher._add_network_diagnostics(result, None) is result


@pytest.mark.anyio
async def test_launcher_without_timeout_and_terminate_lookup_error(monkeypatch):
    result = await SandboxProcessLauncher(filesystem_isolation_enabled=False).launch(
        ["bash", "-c", "printf ok"], timeout_seconds=None
    )

    assert result.stdout == "ok"
    assert result.timed_out is False

    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.os.killpg",
        lambda *args: (_ for _ in ()).throw(ProcessLookupError()),
    )
    process = SimpleNamespace(pid=123)
    await SandboxProcessLauncher()._terminate_process_group(process)


@pytest.mark.anyio
async def test_bash_tool_reports_duration_omissions_and_error(monkeypatch):
    result = SandboxResult(
        job_id="job",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout="a\nb\nc",
        stdout_log="logs/exec-1.stdout.log",
        stdout_lines=9,
        error="warning",
        metadata=SandboxExecutionMetadata(total_ms=12),
    )
    monkeypatch.setattr(
        bash_module.sandbox_gateway, "submit_and_wait", AsyncMock(return_value=result)
    )

    tool_result = await BashSandboxTool(session_id="s").execute("true")
    display = tool_result.display_result

    assert display["duration_ms"] == 12
    assert display["stdout_lines"] == 9
    assert display["stdout_omitted_lines"] == 6
    assert display["error"] == "warning"
    assert "exit_code" not in display


def test_register_bash_tool_registers_info():
    from app.llm.tools.registry import tool_registry

    bash_module.register_bash_tool()

    infos = tool_registry.get_sandbox_tool_infos(["bash"])
    assert infos and infos[0].parameters[0].name == "command"


def test_launcher_empty_network_diagnostics_and_isolation_failures(
    monkeypatch, tmp_path
):
    launcher = SandboxProcessLauncher(filesystem_isolation_enabled=False)
    result = SimpleNamespace(stderr="")
    assert (
        launcher._add_network_diagnostics(
            result, SimpleNamespace(blocked_diagnostics=[])
        )
        is result
    )

    isolation = SandboxProcessLauncher(
        filesystem_isolation_enabled=True, isolation_binary="missing-bwrap"
    )
    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which", lambda _: None
    )
    with pytest.raises(SandboxIsolationError, match="isolation binary not found"):
        isolation._isolated_launch(
            ["python"],
            workspace_root=str(tmp_path),
            cwd=None,
            env=None,
            cache_root=None,
            network_proxy=None,
            timeout_seconds=None,
        )

    monkeypatch.setattr(
        "app.services.sandbox.process_launcher.shutil.which", lambda _: "/bin/true"
    )
    with pytest.raises(SandboxIsolationError, match="workspace not found"):
        isolation._isolated_launch(
            ["python"],
            workspace_root=str(tmp_path / "missing"),
            cwd=None,
            env=None,
            cache_root=None,
            network_proxy=None,
            timeout_seconds=None,
        )
