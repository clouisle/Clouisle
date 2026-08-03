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
    _HASHLINE_CLIPBOARD_PATH,
    _HASHLINE_SNAPSHOT_DIR,
    register_sandbox_file_tools,
)
from app.services.sandbox.models import SandboxArtifact


def _run_sandbox_code(code: str, params: dict):
    body = "\n".join(f"    {line}" for line in code.splitlines())
    namespace = {"params": params}
    exec(f"def execute():\n{body}", namespace)
    return namespace["execute"]()


def _read_hashline_tag(path, runtime_params):
    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {"path": str(path), "max_chars": 200_000, **runtime_params},
    )
    return content.splitlines()[0].split("#", 1)[1].split("|", 1)[0]


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
                result={
                    "edits": 1,
                    "changed": 1,
                    "bytes": 11,
                    "tag": "0A3B",
                    "recovered": False,
                },
                error=None,
            )
        ),
    ) as mock_submit:
        result = await tool.execute(
            "/workspace/example.txt",
            [{"line": "2#0A3B", "new": "replacement"}],
        )

    assert result == {
        "success": True,
        "path": "/workspace/example.txt",
        "edits": 1,
        "changed": 1,
        "bytes": 11,
        "tag": "0A3B",
        "recovered": False,
        "results": [],
        "warnings": [],
        "error": None,
    }
    job = mock_submit.await_args.args[0]
    assert job.metadata["params"] == {
        "path": "example.txt",
        "tag": None,
        "edits": [{"line": "2#0A3B", "new": "replacement"}],
        "snapshot_dir": _HASHLINE_SNAPSHOT_DIR,
        "clipboard_path": _HASHLINE_CLIPBOARD_PATH,
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
        "snapshot_dir": _HASHLINE_SNAPSHOT_DIR,
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
    assert re.fullmatch(r"2#[0-9A-F]{4}\| world", hashline)

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


def test_hashline_recovers_later_anchor_after_earlier_edit_shifts_lines(tmp_path):
    path = tmp_path / "example.txt"
    snapshot_dir = tmp_path / "snapshots"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    common_params = {"path": str(path), "snapshot_dir": str(snapshot_dir)}
    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {**common_params, "max_chars": 200_000},
    )
    anchors = [line.split("|", 1)[0] for line in content.splitlines()]

    first = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            **common_params,
            "edits": [{"line": anchors[1], "new": "TWO\ninserted"}],
        },
    )
    second = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            **common_params,
            "edits": [{"line": anchors[3], "new": "FOUR"}],
        },
    )

    assert first["recovered"] is False
    assert second["recovered"] is True
    assert path.read_text(encoding="utf-8") == "one\nTWO\ninserted\nthree\nFOUR\n"


def test_hashline_recovers_unique_final_line_without_unchanged_neighbor(tmp_path):
    path = tmp_path / "example.txt"
    snapshot_dir = tmp_path / "snapshots"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    common_params = {"path": str(path), "snapshot_dir": str(snapshot_dir)}
    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {**common_params, "max_chars": 200_000},
    )
    anchors = [line.split("|", 1)[0] for line in content.splitlines()]

    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            **common_params,
            "edits": [{"line": anchors[1], "new": "TWO\ninserted"}],
        },
    )
    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            **common_params,
            "edits": [{"line": anchors[2], "new": "THREE"}],
        },
    )

    assert result["recovered"] is True
    assert path.read_text(encoding="utf-8") == "one\nTWO\ninserted\nTHREE\n"


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
    assert re.fullmatch(r"2#[0-9A-F]{4}\| needle one", full_lines[1])
    assert re.fullmatch(r"4#[0-9A-F]{4}\| needle two", full_lines[3])

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


def test_hashline_read_never_emits_anchor_for_budget_truncated_line(tmp_path):
    path = tmp_path / "example.txt"
    snapshot_dir = tmp_path / "snapshots"
    long_line = "DUPLICATE " + "X" * 200
    path.write_text(
        f"one\ntwo\nthree\nfour\n{long_line}\n{long_line}\n", encoding="utf-8"
    )
    common = {"path": str(path), "snapshot_dir": str(snapshot_dir)}

    truncated = _run_sandbox_code(_HASHLINE_READ_CODE, {**common, "max_chars": 80})
    anchors = [line.split("|", 1)[0] for line in truncated.splitlines()]
    tag = anchors[0].split("#", 1)[1]

    # A line that did not fit the budget is not fully returned, so its anchor
    # must never appear: every shown anchor has to be an editable target.
    assert not any(anchor.startswith("5#") for anchor in anchors)
    assert len(anchors) == 4

    with pytest.raises(ValueError, match="line 5 was not returned by read"):
        _run_sandbox_code(
            _HASHLINE_EDIT_CODE,
            {**common, "edits": [{"line": f"5#{tag}", "new": "anything"}]},
        )

    # Reading the duplicates fully registers them, so the collapse edit works.
    _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {**common, "max_chars": 200_000, "start_line": 5, "end_line": 6},
    )
    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            **common,
            "edits": [
                {
                    "op": "replace",
                    "line": f"5#{tag}",
                    "end_line": f"6#{tag}",
                    "new": long_line,
                }
            ],
        },
    )
    assert result["changed"] == 1
    assert path.read_text(encoding="utf-8").splitlines() == [
        "one",
        "two",
        "three",
        "four",
        long_line,
    ]


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


def test_compact_edit_supports_range_and_all_insert_positions(tmp_path):
    path = tmp_path / "range.txt"
    path.write_text("a\nb\nc\nd\n", encoding="utf-8")
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    tag = _read_hashline_tag(path, runtime)

    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "tag": tag,
            "edits": [
                {"op": "replace", "line": 2, "end_line": 3, "new": "middle"},
                {"op": "insert_before", "line": 2, "new": "before"},
                {"op": "insert_after", "line": 3, "new": "after"},
                {"op": "insert_head", "new": "head"},
                {"op": "insert_tail", "new": "tail"},
            ],
            **runtime,
        },
    )

    assert result["changed"] == 5
    assert path.read_text(encoding="utf-8") == (
        "head\na\nbefore\nmiddle\nafter\nd\ntail\n"
    )


def test_compact_edit_supports_block_replace_cut_insert_and_paste(tmp_path):
    path = tmp_path / "blocks.py"
    path.write_text(
        "# header\ndef first():\n    return 1\ndef second():\n    return 2\nprint(first())\n",
        encoding="utf-8",
    )
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    tag = _read_hashline_tag(path, runtime)

    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "tag": tag,
            "edits": [
                {
                    "op": "replace_block",
                    "line": 2,
                    "new": "def first():\n    return 10",
                },
                {"op": "cut_block", "line": 4, "register": "function"},
                {"op": "insert_block_after", "line": 2, "new": "# moved below"},
                {"op": "paste_block_after", "line": 2, "register": "function"},
            ],
            **runtime,
        },
    )

    assert result["warnings"] == []
    assert path.read_text(encoding="utf-8") == (
        "# header\ndef first():\n    return 10\n# moved below\n"
        "def second():\n    return 2\nprint(first())\n"
    )


def test_compact_cut_register_persists_for_all_paste_positions(tmp_path):
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    source = tmp_path / "source.txt"
    source.write_text("zero\ncut one\ncut two\n", encoding="utf-8")
    source_tag = _read_hashline_tag(source, runtime)
    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(source),
            "tag": source_tag,
            "edits": [{"op": "cut", "line": 2, "end_line": 3, "register": "selection"}],
            **runtime,
        },
    )

    destination = tmp_path / "destination.txt"
    destination.write_text("one\ntwo\nthree\n", encoding="utf-8")
    destination_tag = _read_hashline_tag(destination, runtime)
    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(destination),
            "tag": destination_tag,
            "edits": [
                {"op": "paste_head", "register": "selection"},
                {"op": "paste_before", "line": 2, "register": "selection"},
                {"op": "paste_after", "line": 2, "register": "selection"},
                {"op": "paste_tail", "register": "selection"},
            ],
            **runtime,
        },
    )

    assert result["changed"] == 4
    assert destination.read_text(encoding="utf-8") == (
        "cut one\ncut two\none\ncut one\ncut two\ntwo\n"
        "cut one\ncut two\nthree\ncut one\ncut two\n"
    )


def test_compact_block_resolution_supports_markdown_and_braces(tmp_path):
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    markdown = tmp_path / "sections.md"
    markdown.write_text(
        "## First\nbody\n### Child\nnested\n## Second\nkeep\n",
        encoding="utf-8",
    )
    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(markdown),
            "tag": _read_hashline_tag(markdown, runtime),
            "edits": [{"op": "replace_block", "line": 1, "new": "## Replacement\nnew"}],
            **runtime,
        },
    )
    assert markdown.read_text(encoding="utf-8") == (
        "## Replacement\nnew\n## Second\nkeep\n"
    )

    javascript = tmp_path / "block.js"
    javascript.write_text(
        "function value() {\n  return 1;\n}\nconsole.log(value());\n",
        encoding="utf-8",
    )
    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(javascript),
            "tag": _read_hashline_tag(javascript, runtime),
            "edits": [{"op": "insert_block_after", "line": 1, "new": "// after"}],
            **runtime,
        },
    )
    assert javascript.read_text(encoding="utf-8") == (
        "function value() {\n  return 1;\n}\n// after\nconsole.log(value());\n"
    )


def test_compact_range_recovers_after_an_earlier_line_shift(tmp_path):
    path = tmp_path / "recovery.txt"
    path.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    original_tag = _read_hashline_tag(path, runtime)
    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "tag": original_tag,
            "edits": [{"op": "insert_after", "line": 1, "new": "inserted"}],
            **runtime,
        },
    )
    result = _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "tag": original_tag,
            "edits": [
                {"op": "replace", "line": 3, "end_line": 4, "new": "THREE\nFOUR"}
            ],
            **runtime,
        },
    )

    assert result["recovered"] is True
    assert path.read_text(encoding="utf-8") == (
        "one\ninserted\ntwo\nTHREE\nFOUR\nfive\n"
    )


def test_compact_block_replace_only_needs_the_displayed_header(tmp_path):
    path = tmp_path / "partial.py"
    path.write_text("def value():\n    return 1\nprint(value())\n", encoding="utf-8")
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(tmp_path / "clipboard.json"),
    }
    content = _run_sandbox_code(
        _HASHLINE_READ_CODE,
        {
            "path": str(path),
            "max_chars": 200_000,
            "start_line": 1,
            "end_line": 1,
            **runtime,
        },
    )
    tag = content.split("#", 1)[1].split("|", 1)[0]

    _run_sandbox_code(
        _HASHLINE_EDIT_CODE,
        {
            "path": str(path),
            "tag": tag,
            "edits": [
                {"op": "replace_block", "line": 1, "new": "def value():\n    return 2"}
            ],
            **runtime,
        },
    )

    assert path.read_text(encoding="utf-8") == (
        "def value():\n    return 2\nprint(value())\n"
    )


def test_compact_edit_rejects_overlaps_before_file_or_register_changes(tmp_path):
    path = tmp_path / "overlap.txt"
    path.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    clipboard_path = tmp_path / "clipboard.json"
    runtime = {
        "snapshot_dir": str(tmp_path / "snapshots"),
        "clipboard_path": str(clipboard_path),
    }
    tag = _read_hashline_tag(path, runtime)

    with pytest.raises(ValueError, match="overlaps"):
        _run_sandbox_code(
            _HASHLINE_EDIT_CODE,
            {
                "path": str(path),
                "tag": tag,
                "edits": [
                    {"op": "replace", "line": 2, "end_line": 3, "new": "changed"},
                    {"op": "cut", "line": 3, "end_line": 4, "register": "saved"},
                ],
                **runtime,
            },
        )

    assert path.read_text(encoding="utf-8") == "one\ntwo\nthree\nfour\n"
    assert not clipboard_path.exists()


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
    properties = schema["parameters"]["properties"]
    assert "tag" in properties
    edits_schema = properties["edits"]
    assert edits_schema["type"] == "array"
    assert edits_schema["items"]["required"] == []
    assert "replace_block" in edits_schema["items"]["properties"]["op"]["enum"]
    assert "paste_block_after" in edits_schema["items"]["properties"]["op"]["enum"]
    assert edits_schema["items"]["additionalProperties"] is False
