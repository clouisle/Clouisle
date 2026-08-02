import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.llm.tools.builtin.media import ToolExecutionResult
from app.llm.tools.registry import tool_registry
from app.llm.tools.sandbox_files import (
    SandboxArtifactTool,
    SandboxEditTool,
    SandboxReadTool,
    SandboxWriteTool,
    _HASHLINE_EDIT_CODE,
    _HASHLINE_READ_CODE,
    register_sandbox_file_tools,
)
from app.services.sandbox.models import SandboxArtifact


def _run_sandbox_code(code: str, params: dict):
    body = "\n".join(f"    {line}" for line in code.splitlines())
    namespace = {"params": params}
    exec(f"def execute():\n{body}", namespace)
    return namespace["execute"]()


@pytest.mark.anyio
async def test_write_tool_maps_workspace_path_to_session_relative_path():
    tool = SandboxWriteTool(
        session_id="session-1", agent_id="agent-1", team_id="team-1"
    )

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                result={"bytes": 11},
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute("/workspace/create_essay.py", "print('ok')")

    assert result == {
        "success": True,
        "path": "/workspace/create_essay.py",
        "bytes": 11,
        "error": None,
    }
    job = mock_submit.await_args.args[0]
    assert job.cwd == "/workspace"
    assert job.metadata["params"] == {
        "path": "create_essay.py",
        "content": "print('ok')",
    }


@pytest.mark.anyio
async def test_edit_tool_maps_hashline_edits_to_session_relative_path():
    tool = SandboxEditTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                result={"edits": 1, "changed": 1, "bytes": 11},
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute(
            "/workspace/example.txt",
            [{"line": "2#XJ", "new": "replacement"}],
        )

    assert result == {
        "success": True,
        "path": "/workspace/example.txt",
        "edits": 1,
        "changed": 1,
        "bytes": 11,
        "error": None,
    }
    job = mock_submit.await_args.args[0]
    assert job.metadata["params"] == {
        "path": "example.txt",
        "edits": [{"line": "2#XJ", "new": "replacement"}],
    }


@pytest.mark.anyio
async def test_read_tool_maps_workspace_path_to_session_relative_path():
    tool = SandboxReadTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                result="hello",
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute(
            "/workspace/秋天的校园.docx",
            1000,
            start_line=10,
            end_line=20,
            search="校园",
        )

    assert result == {
        "success": True,
        "path": "/workspace/秋天的校园.docx",
        "content": "hello",
        "error": None,
    }
    job = mock_submit.await_args.args[0]
    assert job.cwd == "/workspace"
    assert job.metadata["params"] == {
        "path": "秋天的校园.docx",
        "max_chars": 1000,
        "start_line": 10,
        "end_line": 20,
        "search": "校园",
    }


def test_hashline_read_anchors_drive_localized_edit_without_rewriting_neighbors(
    tmp_path,
):
    path = tmp_path / "example.txt"
    path.write_bytes(b"alpha\r\nworld\r\nomega\r\n")

    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {"path": str(path), "max_chars": 200_000},
    )
    hashline = content.splitlines()[1]
    assert re.fullmatch(r"2#[A-Z]{2}\| world", hashline)

    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "edits": [
                {
                    "line": hashline.split("|", 1)[0],
                    "new": "WORLD\nmiddle",
                }
            ],
        },
    )

    assert result["edits"] == 1
    assert result["changed"] == 1
    assert path.read_bytes() == b"alpha\r\nWORLD\r\nmiddle\r\nomega\r\n"


def test_hashline_read_combines_inclusive_range_and_literal_search(tmp_path):
    path = tmp_path / "example.txt"
    path.write_text(
        "before\nneedle one\nNeedle case\nneedle two\nafter\n",
        encoding="utf-8",
    )
    full_content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {"path": str(path), "max_chars": 200_000},
    )

    filtered_content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {
            "path": str(path),
            "max_chars": 200_000,
            "start_line": 2,
            "end_line": 4,
            "search": "needle",
        },
    )

    full_lines = full_content.splitlines()
    assert filtered_content.splitlines() == [full_lines[1], full_lines[3]]
    assert re.fullmatch(r"2#[A-Z]{2}\| needle one", full_lines[1])
    assert re.fullmatch(r"4#[A-Z]{2}\| needle two", full_lines[3])

    with pytest.raises(
        ValueError,
        match="start_line 6 exceeds file length 5",
    ):
        _run_sandbox_code(
            _HASHLINE_READ_CODE,
            {
                "path": str(path),
                "max_chars": 200_000,
                "start_line": 6,
            },
        )


def test_hashline_edit_rejects_stale_batch_before_writing_any_change(tmp_path):
    path = tmp_path / "example.txt"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {"path": str(path), "max_chars": 200_000},
    )
    anchors = [line.split("|", 1)[0] for line in content.splitlines()]
    path.write_text("ONE\ntwo\nthree\nfour\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=r"stale line reference.*re-read the file before editing",
    ):
        _run_sandbox_code(
            _HASHLINE_EDIT_CODE,
            {
                "path": str(path),
                "edits": [
                    {"line": anchors[0], "new": "won"},
                    {"line": anchors[3], "new": "FOUR"},
                ],
            },
        )

    assert path.read_text(encoding="utf-8") == "ONE\ntwo\nthree\nfour\n"


@pytest.mark.anyio
async def test_artifact_tool_rejects_empty_paths():
    tool = SandboxArtifactTool(session_id="session-1")

    result = await tool.execute([])

    assert isinstance(result, ToolExecutionResult)
    assert result.display_result == {
        "success": False,
        "result": "Generated 0 downloadable link(s) for the assistant response.",
        "count": 0,
        "artifacts": [],
        "error": "At least one artifact path is required",
    }
    llm_payload = json.loads(result.llm_result)
    assert llm_payload["success"] is False
    assert llm_payload["markdown_links"] == []


@pytest.mark.anyio
async def test_artifact_tool_collects_paths_as_markdown_links():
    tool = SandboxArtifactTool(
        session_id="session-1", agent_id="agent-1", team_id="team-1"
    )
    artifact = SandboxArtifact(
        path="/workspace/output/report.docx",
        file_type="file",
        size=123,
        checksum="abc",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        storage_path="sandbox-artifacts/2026/05/report.docx",
        url="/api/v1/upload/files/sandbox-artifacts/2026/05/report.docx",
        filename="report.docx",
    )

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                artifacts=[artifact],
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute(
            [
                "output/report.docx",
                {
                    "path": "/workspace/output/optional.txt",
                    "description": "Optional file",
                    "optional": True,
                },
            ]
        )

    assert isinstance(result, ToolExecutionResult)
    assert result.display_result["artifacts"] == [
        {
            "path": "/workspace/output/report.docx",
            "filename": "report.docx",
            "url": "/api/v1/upload/files/sandbox-artifacts/2026/05/report.docx",
            "size": 123,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
    ]
    assert result.display_result["success"] is True
    assert result.display_result["count"] == 1
    llm_payload = json.loads(result.llm_result)
    assert llm_payload["markdown_links"] == [
        "[report.docx](/api/v1/upload/files/sandbox-artifacts/2026/05/report.docx)"
    ]
    assert llm_payload["files"][0]["filename"] == "report.docx"
    job = mock_submit.await_args.args[0]
    assert job.cwd == "/workspace"
    assert job.artifacts[0].path == "/workspace/output/report.docx"
    assert job.artifacts[0].optional is False
    assert job.artifacts[1].path == "/workspace/output/optional.txt"
    assert job.artifacts[1].optional is True
    assert job.artifacts[1].description == "Optional file"
    assert job.artifact_limits.max_size_mb == settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB
    assert (
        job.artifact_limits.max_total_size_mb
        == settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB
    )


@pytest.mark.anyio
async def test_artifact_tool_allows_custom_limits():
    tool = SandboxArtifactTool(
        session_id="session-1", agent_id="agent-1", team_id="team-1"
    )
    artifact = SandboxArtifact(
        path="/workspace/output/report.txt",
        file_type="file",
        size=2,
        checksum="abc",
        content_type="text/plain",
        storage_path="sandbox-artifacts/2026/05/report.txt",
        url="/api/v1/upload/files/sandbox-artifacts/2026/05/report.txt",
        filename="report.txt",
    )

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                artifacts=[artifact],
                error=None,
            )
        ),
    ) as mock_submit:
        await tool.execute(["output/report.txt"], max_size_mb=2, max_total_size_mb=3)

    job = mock_submit.await_args.args[0]
    assert job.artifact_limits.max_size_mb == 2
    assert job.artifact_limits.max_total_size_mb == 3


def test_read_tool_schema_exposes_range_and_literal_search_parameters():
    register_sandbox_file_tools()

    properties = tool_registry.to_openai_sandbox_tools(["read"])[0]["function"][
        "parameters"
    ]["properties"]

    assert properties["start_line"] == {
        "type": "integer",
        "description": "First line to inspect, using 1-based file line numbers. Defaults to 1.",
        "default": 1,
    }
    assert properties["end_line"]["type"] == "integer"
    assert properties["search"]["type"] == "string"


def test_artifact_tool_schema_is_registered():
    register_sandbox_file_tools()

    schemas = tool_registry.to_openai_sandbox_tools(["artifact"])

    assert schemas[0]["function"]["name"] == "artifact"
    properties = schemas[0]["function"]["parameters"]["properties"]
    paths_schema = properties["paths"]
    assert paths_schema["type"] == "array"
    assert paths_schema["items"]["required"] == ["path"]
    assert (
        properties["max_size_mb"]["default"]
        == settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB
    )
    assert (
        properties["max_total_size_mb"]["default"]
        == settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB
    )


def test_edit_tool_schema_requires_hashline_replacements():
    register_sandbox_file_tools()

    schema = tool_registry.to_openai_sandbox_tools(["edit"])[0]["function"]

    assert schema["name"] == "edit"
    edits_schema = schema["parameters"]["properties"]["edits"]
    assert edits_schema["type"] == "array"
    assert edits_schema["items"]["required"] == ["line", "new"]
    assert edits_schema["items"]["additionalProperties"] is False
