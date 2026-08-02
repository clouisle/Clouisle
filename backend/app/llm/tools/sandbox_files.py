"""Sandbox file tools for skill-assisted chat."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from app.core.config import settings
from app.llm.tools.builtin.media import ToolExecutionResult
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import (
    SandboxArtifactLimits,
    SandboxArtifactSpec,
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
)

from .registry import ToolInfo, ToolParameter, tool_registry

_MAX_READ_CHARS = 200_000
_MAX_WRITE_CHARS = 1_000_000
_HASHLINE_ALPHABET = "ZPMQVRWSNKTXJBYH"
_HASHLINE_RUNTIME = rf"""
from hashlib import blake2s

_HASHLINE_ALPHABET = "{_HASHLINE_ALPHABET}"

def _compute_line_hash(lines, index):
    previous = lines[index - 1] if index > 0 else ""
    following = lines[index + 1] if index + 1 < len(lines) else ""
    context = "\0".join((previous, lines[index], following))
    digest = blake2s(context.encode("utf-8"), digest_size=1).digest()[0]
    return _HASHLINE_ALPHABET[digest >> 4] + _HASHLINE_ALPHABET[digest & 0x0f]

def _format_hashlines(lines):
    return "\n".join(
        f"{{index + 1}}#{{_compute_line_hash(lines, index)}}| {{line}}"
        for index, line in enumerate(lines)
    )
""".strip()

_HASHLINE_READ_CODE = (
    _HASHLINE_RUNTIME
    + r"""

import fcntl
from pathlib import Path

path = Path(params["path"])
if not path.is_file():
    raise ValueError(f"not a file: {path}")
with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
    fcntl.flock(handle, fcntl.LOCK_SH)
    text = handle.read()
return _format_hashlines(text.splitlines())[:params["max_chars"]]
"""
).strip()

_HASHLINE_EDIT_CODE = (
    _HASHLINE_RUNTIME
    + r"""

import fcntl
import os
import re
from pathlib import Path

path = Path(params["path"])
if not path.is_file():
    raise ValueError(f"not a file: {path}")

with path.open("r+", encoding="utf-8", newline="") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    original = handle.read()
    raw_lines = original.splitlines(keepends=True)
    lines = original.splitlines()
    if len(raw_lines) != len(lines):
        raise ValueError("unable to map file lines safely")

    planned = []
    seen = set()
    stale = []
    for edit in params["edits"]:
        anchor = edit["line"].strip()
        match = re.fullmatch(r"([1-9]\d*)#([ZPMQVRWSNKTXJBYH]{2})", anchor)
        if match is None:
            raise ValueError(f"line must use a LINE#ID reference from read: {anchor}")

        line_number = int(match.group(1))
        index = line_number - 1
        if index >= len(lines):
            raise ValueError(
                f"line reference is out of range: {anchor}; re-read the file"
            )
        if index in seen:
            raise ValueError(f"duplicate line reference: {anchor}")
        seen.add(index)

        expected_hash = match.group(2)
        actual_hash = _compute_line_hash(lines, index)
        if expected_hash != actual_hash:
            stale.append(f"{anchor} (current {line_number}#{actual_hash})")
        planned.append((index, edit["new"]))

    if stale:
        raise ValueError(
            "stale line reference(s): "
            + ", ".join(stale)
            + "; re-read the file before editing"
        )

    default_ending = "\n"
    for raw_line, line in zip(raw_lines, lines):
        ending = raw_line[len(line):]
        if ending:
            default_ending = ending
            break

    changed = 0
    for index, replacement in sorted(planned, key=lambda item: item[0], reverse=True):
        raw_line = raw_lines[index]
        ending = raw_line[len(lines[index]):]
        parts = replacement.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        separator = ending or default_ending
        replacement_lines = [
            part + (ending if part_index == len(parts) - 1 else separator)
            for part_index, part in enumerate(parts)
        ]
        if "".join(replacement_lines) != raw_line:
            changed += 1
        raw_lines[index:index + 1] = replacement_lines

    updated = "".join(raw_lines)
    if updated != original:
        handle.seek(0)
        handle.write(updated)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())

return {
    "edits": len(planned),
    "changed": changed,
    "bytes": len(updated.encode("utf-8")),
}
"""
).strip()


def _normalize_workspace_path(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    posix_path = PurePosixPath(raw)
    if posix_path.is_absolute() and not raw.startswith("/workspace"):
        raise ValueError("path must stay inside /workspace")
    relative = raw.removeprefix("/workspace/") if raw != "/workspace" else ""
    relative_path = PurePosixPath(relative)
    if ".." in relative_path.parts:
        raise ValueError("path must stay inside /workspace")
    if raw == "/workspace":
        return "/workspace"
    if raw.startswith("/workspace/"):
        return PurePosixPath("/workspace", relative_path).as_posix()
    return PurePosixPath("/workspace", posix_path).as_posix()


def _runtime_workspace_path(path: str) -> str:
    if path == "/workspace":
        return "."
    return path.removeprefix("/workspace/")


class SandboxReadTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self, path: str, max_chars: int = _MAX_READ_CHARS
    ) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            limit = max(1, min(int(max_chars), _MAX_READ_CHARS))
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=_HASHLINE_READ_CODE,
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "max_chars": limit,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            return {
                "success": result.success,
                "path": safe_path,
                "content": result.result if result.success else None,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class SandboxArtifactTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self,
        paths: list[Any],
        max_size_mb: float | None = None,
        max_total_size_mb: float | None = None,
    ) -> ToolExecutionResult:
        if not self.session_id:
            return self._result(success=False, error="Sandbox session is required")
        try:
            artifact_specs = self._build_artifact_specs(paths)
            if not artifact_specs:
                return self._result(
                    success=False, error="At least one artifact path is required"
                )
            artifact_limits = SandboxArtifactLimits(
                max_size_mb=float(
                    max_size_mb
                    if max_size_mb is not None
                    else settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB
                ),
                max_total_size_mb=float(
                    max_total_size_mb
                    if max_total_size_mb is not None
                    else settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB
                ),
            )
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code="return {'collected': True}",
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                artifacts=artifact_specs,
                artifact_limits=artifact_limits,
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            files = [
                {
                    "path": artifact.path,
                    "filename": artifact.filename,
                    "url": artifact.url,
                    "size": artifact.size,
                    "content_type": artifact.content_type,
                }
                for artifact in getattr(result, "artifacts", [])
            ]
            return self._result(success=result.success, files=files, error=result.error)
        except Exception as exc:
            return self._result(success=False, error=str(exc))

    def _build_artifact_specs(self, paths: list[Any]) -> list[SandboxArtifactSpec]:
        if not isinstance(paths, list):
            raise ValueError("paths must be a list")

        specs: list[SandboxArtifactSpec] = []
        for item in paths:
            optional = False
            description = None
            if isinstance(item, str):
                raw_path = item
            elif isinstance(item, dict):
                item_path = item.get("path")
                raw_path = item_path if isinstance(item_path, str) else ""
                optional = bool(item.get("optional", False))
                item_description = item.get("description")
                description = (
                    str(item_description) if item_description is not None else None
                )
            else:
                raise ValueError("artifact path item must be a string or object")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError("artifact path is required")
            specs.append(
                SandboxArtifactSpec(
                    path=_normalize_workspace_path(raw_path),
                    optional=optional,
                    description=description,
                )
            )
        return specs

    def _result(
        self,
        *,
        success: bool,
        files: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> ToolExecutionResult:
        files = files or []
        markdown_links = [f"[{file['filename']}]({file['url']})" for file in files]
        display_result = {
            "success": success,
            "result": f"Generated {len(markdown_links)} downloadable link(s) for the assistant response.",
            "count": len(markdown_links),
            "error": error,
        }
        llm_result = {
            "success": success,
            "result": "Use these Markdown links in your final answer."
            if success
            else None,
            "markdown_links": markdown_links,
            "files": files,
            "error": error,
        }
        return ToolExecutionResult(
            display_result=display_result,
            llm_result=json.dumps(llm_result, ensure_ascii=False),
        )


class SandboxEditTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(self, path: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            if not isinstance(edits, list) or not edits:
                raise ValueError("edits must be a non-empty list")

            normalized_edits: list[dict[str, str]] = []
            total_chars = 0
            for edit in edits:
                if not isinstance(edit, dict):
                    raise ValueError("each edit must be an object")
                line = edit.get("line")
                replacement = edit.get("new")
                if not isinstance(line, str) or not line.strip():
                    raise ValueError("each edit requires a LINE#ID line reference")
                if not isinstance(replacement, str):
                    raise ValueError("each edit requires string new content")
                total_chars += len(replacement)
                normalized_edits.append({"line": line, "new": replacement})

            if total_chars > _MAX_WRITE_CHARS:
                return {"success": False, "error": "edit content is too large"}

            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=_HASHLINE_EDIT_CODE,
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "edits": normalized_edits,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            details = result.result if isinstance(result.result, dict) else {}
            return {
                "success": result.success,
                "path": safe_path,
                "edits": details.get("edits", 0) if result.success else 0,
                "changed": details.get("changed", 0) if result.success else 0,
                "bytes": details.get("bytes", 0) if result.success else 0,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class SandboxWriteTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(self, path: str, content: str) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            text = str(content or "")
            if len(text) > _MAX_WRITE_CHARS:
                return {"success": False, "error": "content is too large"}
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=(
                    "import fcntl\n"
                    "import os\n"
                    "from pathlib import Path\n"
                    "content = params['content'].encode('utf-8')\n"
                    "path = Path(params['path'])\n"
                    "path.parent.mkdir(parents=True, exist_ok=True)\n"
                    "path.touch(exist_ok=True)\n"
                    "with path.open('r+b') as handle:\n"
                    "    fcntl.flock(handle, fcntl.LOCK_EX)\n"
                    "    handle.seek(0)\n"
                    "    handle.write(content)\n"
                    "    handle.truncate()\n"
                    "    handle.flush()\n"
                    "    os.fsync(handle.fileno())\n"
                    "return {'bytes': len(content)}\n"
                ),
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "content": text,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            bytes_written = (
                result.result.get("bytes", 0) if isinstance(result.result, dict) else 0
            )
            return {
                "success": result.success,
                "path": safe_path,
                "bytes": bytes_written if result.success else 0,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


def register_sandbox_file_tools() -> None:
    read_info = ToolInfo(
        name="read",
        description=(
            "Read a UTF-8 text file from the sandbox workspace. Each returned line is prefixed "
            "with a hashline anchor in the form LINE#ID| content. Copy the LINE#ID value into "
            "the edit tool for safe localized changes. Paths must stay inside /workspace. For "
            "binary files such as .docx, .xlsx, images, or archives, inspect metadata with bash "
            "instead of reading raw binary content."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="File path to read. Use /workspace/file.txt or a relative path like file.txt; paths outside /workspace are rejected.",
                required=True,
            ),
            ToolParameter(
                name="max_chars",
                type="integer",
                description="Maximum characters of hashline-formatted text to return. Increase only when you need more of a large file.",
                required=False,
                default=_MAX_READ_CHARS,
            ),
        ],
    )
    edit_info = ToolInfo(
        name="edit",
        description=(
            "Apply localized, hash-verified edits to an existing UTF-8 text file. Call read "
            "first, then copy each LINE#ID anchor exactly into edits. Every anchor is checked "
            "against the current file before any change is written; stale anchors reject the "
            "entire request and require a fresh read. Use write for new files or full rewrites."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="Existing text file to edit. Use a /workspace path or a relative path; paths outside /workspace are rejected.",
                required=True,
            ),
            ToolParameter(
                name="edits",
                type="array",
                description="Localized replacements. Each item uses a LINE#ID anchor from read and the replacement line content.",
                required=True,
                items={
                    "type": "object",
                    "properties": {
                        "line": {
                            "type": "string",
                            "description": "Exact LINE#ID anchor from read, for example 22#XJ.",
                        },
                        "new": {
                            "type": "string",
                            "description": "Replacement content without the hashline prefix. Newlines replace the anchored line with multiple lines.",
                        },
                    },
                    "required": ["line", "new"],
                    "additionalProperties": False,
                },
            ),
        ],
    )
    write_info = ToolInfo(
        name="write",
        description=(
            "Create a new UTF-8 text file or replace a file's complete content inside the "
            "sandbox workspace. For localized changes to an existing file, use read followed "
            "by edit instead of rewriting the whole file. Use write before running non-trivial "
            "Python or Node code, then execute the script with bash. Parent directories are "
            "created automatically. Inside generated scripts, prefer output paths relative to "
            "the working directory rather than hardcoding /workspace."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="File path to write. Use /workspace/script.py, /workspace/output/result.txt, or a relative path; paths outside /workspace are rejected.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Complete UTF-8 text content to write. Use edit instead when only a localized section needs to change.",
                required=True,
            ),
        ],
    )
    artifact_info = ToolInfo(
        name="artifact",
        description=(
            "Collect existing files or directories from /workspace and return Markdown download "
            "links for the assistant's final answer. Use this after generating and verifying final "
            "user-facing files with bash commands such as `ls`, `find`, or `file`. This tool does "
            "not render download cards directly; after calling it, include the returned Markdown "
            "links in the final response body. Relative paths are interpreted from /workspace."
        ),
        parameters=[
            ToolParameter(
                name="paths",
                type="array",
                description=(
                    "Files or directories to collect for download. Prefer objects like "
                    '[{"path":"/workspace/output/report.docx","description":"Generated report"}]. '
                    'String paths like ["output/report.docx"] are also accepted.'
                ),
                required=True,
                items={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "optional": {"type": "boolean"},
                        "description": {"type": "string"},
                    },
                    "required": ["path"],
                },
            ),
            ToolParameter(
                name="max_size_mb",
                type="number",
                description="Maximum allowed size for each collected artifact in MB. Defaults to 10.",
                required=False,
                default=settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB,
            ),
            ToolParameter(
                name="max_total_size_mb",
                type="number",
                description="Maximum allowed total upload size across all collected artifacts in MB. Defaults to 10.",
                required=False,
                default=settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB,
            ),
        ],
    )
    tool_registry.register_sandbox_tool(
        "read",
        SandboxReadTool,
        tool_info=read_info,
        aliases=["Read"],
    )
    tool_registry.register_sandbox_tool(
        "edit",
        SandboxEditTool,
        tool_info=edit_info,
        aliases=["Edit"],
    )
    tool_registry.register_sandbox_tool(
        "write",
        SandboxWriteTool,
        tool_info=write_info,
        aliases=["Write"],
    )
    tool_registry.register_sandbox_tool(
        "artifact",
        SandboxArtifactTool,
        tool_info=artifact_info,
        aliases=["Artifact"],
    )


__all__ = [
    "SandboxArtifactTool",
    "SandboxEditTool",
    "SandboxReadTool",
    "SandboxWriteTool",
    "register_sandbox_file_tools",
]
