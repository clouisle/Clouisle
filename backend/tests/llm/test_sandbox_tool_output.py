import json
from pathlib import Path

import pytest

from app.llm.tools.bash import BashSandboxTool
from app.llm.tools.sandbox_files import (
    _HASHLINE_READ_CODE,
    SandboxArtifactTool,
)
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.process_launcher import (
    SandboxProcessLauncher,
    _StreamCapture,
)
from app.utils.sandbox_output import (
    PREVIEW_MAX_CHARS,
    PREVIEW_MAX_LINES,
    preview_stream,
    render_sandbox_output,
)
from app.utils.tool_output import ToolExecutionResult


def test_preview_stream_windows_long_output_and_clips_wide_lines():
    preview, omitted, clipped = preview_stream(
        "\n".join(f"line {i}" for i in range(200))
    )

    assert len(preview.splitlines()) == PREVIEW_MAX_LINES + 1
    assert f"<{omitted} lines omitted>" in preview
    assert preview.startswith("line 0")
    assert preview.endswith("line 199")
    assert clipped is False

    wide, _, clipped = preview_stream("x" * (PREVIEW_MAX_CHARS + 500))
    assert clipped is True
    assert len(wide) <= PREVIEW_MAX_CHARS + 40
    assert "middle characters omitted" in wide


def test_bash_renderer_omits_empty_fields_and_points_at_persisted_log():
    payload = {
        "success": True,
        "status": "completed",
        "exit_code": 0,
        "stdout": "first\nlast",
        "stdout_log": "/workspace/logs/exec-1.stdout.log",
        "stdout_lines": 120,
        "stdout_omitted_lines": 118,
    }

    rendered = render_sandbox_output("bash", payload)

    assert rendered.startswith("Status: completed · exit 0")
    assert "<stdout>\nfirst\nlast\n</stdout>" in rendered
    assert "<stderr>" not in rendered
    assert "full log: /workspace/logs/exec-1.stdout.log (120 line(s))" in rendered
    assert "read with start_line/end_line" in rendered


def test_bash_renderer_reports_timeout_without_empty_blocks():
    rendered = render_sandbox_output(
        "bash",
        {
            "success": False,
            "status": "timed_out",
            "stderr": "Execution timeout (30s)",
            "stderr_log": "/workspace/logs/exec-2.stderr.log",
            "stderr_capture_truncated": True,
            "error": "Execution timeout (30s)",
        },
    )

    assert rendered.startswith("Status: timed out")
    assert "Error:" not in rendered
    assert "<stdout>" not in rendered
    assert "shows the beginning of output beyond the capture limit" in rendered


def test_sandbox_renderers_keep_write_edit_read_concise():
    assert (
        render_sandbox_output(
            "write", {"success": True, "path": "/workspace/a.py", "bytes": 12}
        )
        == "Wrote /workspace/a.py (12 bytes)."
    )

    assert render_sandbox_output(
        "edit",
        {
            "success": True,
            "path": "/workspace/a.py",
            "edits": 2,
            "changed": 1,
            "bytes": 15,
            "tag": "AB12",
            "warnings": ["insert_block_after fell back"],
        },
    ) == (
        "Edited /workspace/a.py: 1 of 2 operation(s) changed, 15 bytes, tag AB12.\n"
        "Warning: insert_block_after fell back"
    )

    assert (
        render_sandbox_output(
            "read",
            {
                "success": True,
                "path": "/workspace/a.py",
                "tag": "AB12",
                "content": "1#AB12| x",
            },
        )
        == "/workspace/a.py · tag=AB12\n1#AB12| x"
    )
    assert (
        render_sandbox_output(
            "read", {"success": True, "path": "/workspace/empty.txt", "content": ""}
        )
        == "/workspace/empty.txt\nNo lines returned."
    )
    assert (
        render_sandbox_output(
            "read", {"success": False, "path": "/workspace/a.py", "content": None}
        )
        == "/workspace/a.py\nRead failed."
    )


def test_artifact_renderer_keeps_links_refs_and_errors():
    rendered = render_sandbox_output(
        "artifact",
        {
            "success": False,
            "instruction": "Use these Markdown links in your final answer.",
            "artifacts": [
                {
                    "filename": "report.docx",
                    "url": "/files/report.docx",
                    "asset_ref": "a1b2",
                    "size": 10,
                    "content_type": "application/docx",
                }
            ],
            "error": "one path was missing",
        },
    )

    assert (
        "- [report.docx](/files/report.docx) · ref=a1b2 · 10 bytes · application/docx"
        in rendered
    )
    assert "Error: one path was missing" in rendered
    assert "Use these Markdown links in your final answer." in rendered


@pytest.mark.anyio
async def test_launcher_persists_complete_log_beyond_capture_limit(tmp_path):
    log_dir = tmp_path / "logs"
    result = await SandboxProcessLauncher(filesystem_isolation_enabled=False).launch(
        ["bash", "-c", "for i in $(seq 1 5000); do echo line-$i; done"],
        max_stdout_kb=16,
        log_dir=str(log_dir),
        log_stem="exec-long",
    )

    assert result.stdout_truncated is True
    assert result.stdout_log is not None
    persisted = Path(result.stdout_log).read_text(encoding="utf-8")
    assert persisted.splitlines()[-1] == "line-5000"
    assert result.stdout_lines == 5000


def test_capture_counts_lines_across_chunk_boundaries():
    class ChunkedStream:
        def __init__(self, chunks):
            self.chunks = list(chunks)

        async def read(self, _size):
            return self.chunks.pop(0) if self.chunks else b""

    import asyncio

    capture = asyncio.run(
        SandboxProcessLauncher._read_bounded(
            ChunkedStream([b"a", b"b\nc", b"\nd"]), 1024
        )
    )

    assert isinstance(capture, _StreamCapture)
    assert capture.lines == 3
    assert capture.payload == b"ab\nc\nd"


@pytest.mark.anyio
async def test_bash_tool_returns_compact_live_result_equal_to_replay_and_keeps_logs(
    monkeypatch, tmp_path
):
    from app.llm.tools import bash

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    log_path = workspace / "logs" / "exec-test.stdout.log"
    log_path.parent.mkdir()
    log_path.write_text("\n".join(f"row-{i}" for i in range(1, 201)) + "\n")
    result = SandboxResult(
        job_id="job",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        stdout="\n".join(f"row-{i}" for i in range(1, 201)) + "\n",
        stdout_log="logs/exec-test.stdout.log",
        stdout_lines=200,
        metadata=SandboxExecutionMetadata(exit_code=0, total_ms=12),
    )

    async def submit_and_wait(*args, **kwargs):
        return result

    monkeypatch.setattr(bash.sandbox_gateway, "submit_and_wait", submit_and_wait)
    tool_result = await BashSandboxTool(session_id="session").execute("echo rows")

    assert isinstance(tool_result, ToolExecutionResult)
    assert tool_result.display_result["stdout_log"] == (
        "/workspace/logs/exec-test.stdout.log"
    )
    assert "stderr" not in tool_result.display_result
    assert tool_result.display_result["stdout_omitted_lines"] > 0
    assert "/workspace/logs/exec-test.stdout.log" in tool_result.llm_result
    assert tool_result.llm_result == render_sandbox_output(
        "bash", tool_result.display_result
    )


@pytest.mark.anyio
async def test_launcher_written_log_is_readable_through_bounded_hashline_read(
    tmp_path,
):
    log_dir = tmp_path / "logs"
    launch = await SandboxProcessLauncher(filesystem_isolation_enabled=False).launch(
        ["bash", "-c", "for i in $(seq 1 300); do echo value-$i; done"],
        max_stdout_kb=16,
        log_dir=str(log_dir),
        log_stem="exec-read",
    )
    body = "\n".join(f"    {line}" for line in _HASHLINE_READ_CODE.splitlines())
    namespace = {
        "params": {
            "path": launch.stdout_log,
            "max_chars": 200_000,
            "start_line": 290,
            "end_line": 300,
            "search": None,
            "snapshot_dir": str(tmp_path / "snapshots"),
        }
    }
    exec(f"def execute():\n{body}", namespace)

    content = namespace["execute"]()

    assert "290#" in content


@pytest.mark.anyio
async def test_artifact_tool_uses_shared_result_type():
    tool = SandboxArtifactTool(session_id="session")

    result = tool._result(success=True)

    assert isinstance(result, ToolExecutionResult)
    assert result.display_result["success"] is True
    assert result.llm_result == (
        "No downloadable links are available for these artifacts."
    )


def test_sandbox_renderer_fallbacks_and_status_inference():
    assert json.loads(render_sandbox_output("bash", "text")) == "text"
    assert json.loads(render_sandbox_output("unknown", {"a": 1})) == {"a": 1}
    assert render_sandbox_output("bash", {"success": True}) == "Status: completed"
    assert render_sandbox_output("bash", {"success": False}) == "Status: failed"


def test_bash_preview_flags_and_missing_log_location():
    rendered = render_sandbox_output(
        "bash",
        {
            "status": "failed",
            "error": "boom",
            "stdout": "partial",
            "stdout_preview_chars_truncated": True,
            "stdout_log": "/workspace/out.log",
            "stdout_log_partial": True,
        },
    )
    assert "Status: failed" in rendered
    assert "Error: boom" in rendered
    assert "clips long line content" in rendered
    assert "partial log: /workspace/out.log" in rendered
    assert "process was stopped at the output limit" in rendered

    unavailable = render_sandbox_output(
        "bash", {"status": "completed", "stdout_omitted_lines": 2}
    )
    assert "the omitted portion is not available" in unavailable


def test_sandbox_edit_write_errors_and_sparse_fields():
    assert render_sandbox_output("edit", {"error": "bad"}) == "Error: bad"
    assert (
        render_sandbox_output("edit", {"path": "f", "changed": 1, "edits": 2})
        == "Edited f: 1 of 2 operation(s) changed."
    )
    assert (
        render_sandbox_output(
            "edit",
            {
                "path": "f",
                "bytes": 3,
                "tag": "t",
                "warnings": ["careful"],
            },
        )
        == "Edited f: 0 of 0 operation(s) changed, 3 bytes, tag t.\nWarning: careful"
    )
    assert (
        render_sandbox_output("edit", {"path": "f", "warnings": "bad"})
        == "Edited f: 0 of 0 operation(s) changed."
    )
    assert render_sandbox_output("write", {"error": "bad"}) == "Error: bad"
    assert render_sandbox_output("write", {"path": "f"}) == "Wrote f."


def test_artifact_renderer_non_list_non_dict_and_no_instruction():
    assert json.loads(render_sandbox_output("artifact", {"artifacts": "bad"})) == {
        "artifacts": "bad"
    }
    assert (
        render_sandbox_output("artifact", {"artifacts": [1]}) == "Collected 1 file(s)."
    )
    assert render_sandbox_output("artifact", {"artifacts": [{"path": "a"}]}) == (
        "Collected 1 file(s).\n- a"
    )
    assert render_sandbox_output("artifact", {"error": "bad"}) == "Error: bad"
    assert (
        render_sandbox_output("artifact", {"artifacts": [], "result": "done"}) == "done"
    )
