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
                code=(
                    "from pathlib import Path\n"
                    "path = Path(params['path'])\n"
                    "if not path.is_file():\n"
                    "    raise ValueError(f'not a file: {path}')\n"
                    "return path.read_text(encoding='utf-8', errors='replace')[:params['max_chars']]\n"
                ),
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
                    "from pathlib import Path\n"
                    "content = params['content'].encode('utf-8')\n"
                    "path = Path(params['path'])\n"
                    "path.parent.mkdir(parents=True, exist_ok=True)\n"
                    "path.write_bytes(content)\n"
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
            "Read a UTF-8 text file from the sandbox workspace. Use this to inspect files "
            "created earlier with the write tool or generated by Bash commands. Paths must stay "
            "inside /workspace. For binary files such as .docx, .xlsx, images, or archives, use "
            "bash commands like `ls -l`, `file`, or a Python script to inspect metadata instead "
            "of reading raw binary content."
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
                description="Maximum characters to return for text files. Increase only when you need more of a large file.",
                required=False,
                default=_MAX_READ_CHARS,
            ),
        ],
    )
    write_info = ToolInfo(
        name="write",
        description=(
            "Write UTF-8 text content to a file inside the sandbox workspace. Use this before "
            "running non-trivial Python or Node code: write the script to /workspace/name.py or "
            "/workspace/name.js, then execute it with bash using `python3 /workspace/name.py` "
            "or `node /workspace/name.js`. Parent directories are created automatically. Use "
            "/workspace/... paths when calling this tool, but inside generated Python or Node "
            "scripts, prefer relative output paths such as `output/report.docx` or derive paths "
            "from the current working directory instead of hardcoding `/workspace/...`. For "
            "generated output files, keep them under /workspace, commonly /workspace/output/."
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
                description="Full UTF-8 text content to write. For scripts, include the complete Python or JavaScript source code.",
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
    "SandboxReadTool",
    "SandboxWriteTool",
    "register_sandbox_file_tools",
]
