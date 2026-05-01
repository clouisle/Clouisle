import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.llm.tools.builtin.media import ToolExecutionResult
from app.llm.tools.registry import tool_registry
from app.llm.tools.sandbox_files import (
    SandboxArtifactTool,
    SandboxReadTool,
    SandboxWriteTool,
    register_sandbox_file_tools,
)
from app.services.sandbox.models import SandboxArtifact


@pytest.mark.anyio
async def test_write_tool_maps_workspace_path_to_session_relative_path():
    tool = SandboxWriteTool(session_id="session-1", agent_id="agent-1", team_id="team-1")

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
        result = await tool.execute("/workspace/秋天的校园.docx", 1000)

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
    }


@pytest.mark.anyio
async def test_artifact_tool_rejects_empty_paths():
    tool = SandboxArtifactTool(session_id="session-1")

    result = await tool.execute([])

    assert isinstance(result, ToolExecutionResult)
    assert result.display_result == {
        "success": False,
        "result": "Generated 0 downloadable link(s) for the assistant response.",
        "count": 0,
        "error": "At least one artifact path is required",
    }
    llm_payload = json.loads(result.llm_result)
    assert llm_payload["success"] is False
    assert llm_payload["markdown_links"] == []


@pytest.mark.anyio
async def test_artifact_tool_collects_paths_as_markdown_links():
    tool = SandboxArtifactTool(session_id="session-1", agent_id="agent-1", team_id="team-1")
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
        result = await tool.execute([
            "output/report.docx",
            {
                "path": "/workspace/output/optional.txt",
                "description": "Optional file",
                "optional": True,
            },
        ])

    assert isinstance(result, ToolExecutionResult)
    assert "artifacts" not in result.display_result
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
    assert job.artifact_limits.max_total_size_mb == settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB


@pytest.mark.anyio
async def test_artifact_tool_allows_custom_limits():
    tool = SandboxArtifactTool(session_id="session-1", agent_id="agent-1", team_id="team-1")
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


def test_artifact_tool_schema_is_registered():
    register_sandbox_file_tools()

    schemas = tool_registry.to_openai_sandbox_tools(["artifact"])

    assert schemas[0]["function"]["name"] == "artifact"
    properties = schemas[0]["function"]["parameters"]["properties"]
    paths_schema = properties["paths"]
    assert paths_schema["type"] == "array"
    assert paths_schema["items"]["required"] == ["path"]
    assert properties["max_size_mb"]["default"] == settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB
    assert (
        properties["max_total_size_mb"]["default"]
        == settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB
    )
