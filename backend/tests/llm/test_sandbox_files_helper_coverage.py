import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.sandbox_files import (
    SandboxArtifactTool,
    SandboxEditTool,
    SandboxReadTool,
    SandboxWriteTool,
    _normalize_workspace_path,
    _runtime_workspace_path,
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("report.txt", "/workspace/report.txt"),
        (" /workspace/output/report.txt ", "/workspace/output/report.txt"),
        ("/workspace", "/workspace"),
    ],
)
def test_workspace_path_helpers_normalize_safe_paths(path, expected):
    normalized = _normalize_workspace_path(path)

    assert normalized == expected
    assert _runtime_workspace_path(normalized) == (
        "." if normalized == "/workspace" else normalized.removeprefix("/workspace/")
    )


@pytest.mark.parametrize(
    "path", ["", "   ", "/tmp/report.txt", "../report.txt", "/workspace/../secret.txt"]
)
def test_workspace_path_helpers_reject_missing_or_unsafe_paths(path):
    with pytest.raises(
        ValueError, match="path (is required|must stay inside /workspace)"
    ):
        _normalize_workspace_path(path)


def test_artifact_specs_transform_payload_and_reject_invalid_types():
    tool = SandboxArtifactTool(session_id="session-helper-coverage")

    specs = tool._build_artifact_specs(
        [
            "report.txt",
            {"path": "/workspace/output/数据.csv", "optional": 1, "description": 42},
        ]
    )

    assert [(spec.path, spec.optional, spec.description) for spec in specs] == [
        ("/workspace/report.txt", False, None),
        ("/workspace/output/数据.csv", True, "42"),
    ]
    with pytest.raises(ValueError, match="paths must be a list"):
        tool._build_artifact_specs("report.txt")
    with pytest.raises(
        ValueError, match="artifact path item must be a string or object"
    ):
        tool._build_artifact_specs([1])
    with pytest.raises(ValueError, match="artifact path is required"):
        tool._build_artifact_specs([{}])


def test_artifact_result_serializes_download_payload_and_error_output():
    result = SandboxArtifactTool()._result(
        success=False,
        files=[
            {
                "path": "/workspace/数据.csv",
                "filename": "数据.csv",
                "url": "/files/data.csv",
                "size": 2,
                "content_type": "text/csv",
            }
        ],
        error="missing file",
    )

    assert result.display_result == {
        "success": False,
        "result": "Generated 1 downloadable link(s) for the assistant response.",
        "count": 1,
        "error": "missing file",
    }
    assert json.loads(result.llm_result) == {
        "success": False,
        "result": None,
        "markdown_links": ["[数据.csv](/files/data.csv)"],
        "files": [
            {
                "path": "/workspace/数据.csv",
                "filename": "数据.csv",
                "url": "/files/data.csv",
                "size": 2,
                "content_type": "text/csv",
            }
        ],
        "error": "missing file",
    }


@pytest.mark.anyio
async def test_file_tools_return_errors_without_submitting_unsafe_or_oversized_payloads():
    missing_session = await SandboxReadTool().execute("report.txt")
    unsafe_path = await SandboxReadTool(session_id="session-helper-coverage").execute(
        "/tmp/report.txt"
    )
    oversized_content = await SandboxWriteTool(
        session_id="session-helper-coverage"
    ).execute("report.txt", "x" * 1_000_001)
    empty_edits = await SandboxEditTool(session_id="session-helper-coverage").execute(
        "report.txt", []
    )
    oversized_edit = await SandboxEditTool(
        session_id="session-helper-coverage"
    ).execute("report.txt", [{"line": "1#ZZ", "new": "x" * 1_000_001}])

    assert missing_session == {"success": False, "error": "Sandbox session is required"}
    assert unsafe_path == {
        "success": False,
        "error": "path must stay inside /workspace",
    }
    assert oversized_content == {"success": False, "error": "content is too large"}
    assert empty_edits == {
        "success": False,
        "error": "edits must be a non-empty list",
    }
    assert oversized_edit == {
        "success": False,
        "error": "edit content is too large",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(("requested", "expected"), [(0, 1), (200_001, 200_000)])
async def test_read_tool_clamps_size_boundaries_in_submitted_payload(
    requested, expected
):
    tool = SandboxReadTool(session_id="session-helper-coverage")

    with patch(
        "app.llm.tools.sandbox_files.sandbox_gateway.submit_and_wait",
        new=AsyncMock(
            return_value=SimpleNamespace(success=True, result="content", error=None)
        ),
    ) as mock_submit:
        result = await tool.execute("report.txt", requested)

    assert result == {
        "success": True,
        "path": "/workspace/report.txt",
        "content": "content",
        "error": None,
    }
    assert mock_submit.await_args.args[0].metadata["params"] == {
        "path": "report.txt",
        "max_chars": expected,
    }
