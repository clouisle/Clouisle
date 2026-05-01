"""Bash sandbox tool for safe shell command execution."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import SandboxJob, SandboxJobSource, SandboxLimits, SandboxTaskStatus

from .registry import ToolInfo, ToolParameter, tool_registry

logger = logging.getLogger(__name__)

class BashSandboxTool:
    """Bash 沙箱工具封装，支持 shell=True 模式"""

    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        workspace_root: str = "/workspace",
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        self.session_id = session_id
        self.allowed_commands = allowed_commands
        self.workspace_root = workspace_root
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self,
        command: str,
        timeout: float = 30.0,
        cwd: str = "/workspace",
    ) -> dict[str, Any]:
        runtime_workspace_root = await self._runtime_workspace_root()
        logical_cwd = self._normalize_logical_cwd(cwd, runtime_workspace_root)
        runtime_command = self._normalize_install_commands(command)
        runtime_command = self._map_workspace_paths(runtime_command, runtime_workspace_root)
        job = SandboxJob(
            source=SandboxJobSource.BASH,
            command=["bash", "-c", runtime_command],
            shell=True,
            cwd=logical_cwd,
            limits=SandboxLimits(
                timeout_seconds=timeout,
                disk_mb=1024,
            ),
            env={
                "HOME": str(runtime_workspace_root),
                "TMPDIR": f"{runtime_workspace_root}/tmp",
            },
        )

        try:
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=timeout + 5,
            )

            return {
                "success": result.success,
                "stdout": self._restore_workspace_paths(result.stdout, runtime_workspace_root),
                "stderr": self._restore_workspace_paths(result.stderr, runtime_workspace_root),
                "exit_code": result.metadata.exit_code,
                "timed_out": result.status == SandboxTaskStatus.FAILED
                and "timeout" in (result.error or "").lower(),
                "error": self._restore_workspace_paths(result.error, runtime_workspace_root),
            }
        except Exception as e:
            logger.exception("Bash sandbox execution failed: %s", e)
            return {
                "success": False,
                "error": str(e),
            }

    def _normalize_install_commands(self, command: str) -> str:
        return re.sub(
            r"(^|(?:&&|\|\||;|\|)\s*)pip3?(?=\s+install\b)",
            r"\1python3 -m pip",
            command,
        )

    async def _runtime_workspace_root(self) -> Path:
        if not self.session_id:
            return Path(self.workspace_root)
        workspace = await sandbox_gateway.get_session_workspace(
            self.session_id,
            agent_id=self.agent_id,
            team_id=self.team_id,
        )
        if workspace is None:
            return Path(self.workspace_root)
        return workspace.root

    def _map_workspace_paths(self, value: str, runtime_workspace_root: Path) -> str:
        return re.sub(
            r"(?<![A-Za-z0-9._-])/workspace(?=/|\b)",
            str(runtime_workspace_root),
            value,
        )

    def _restore_workspace_paths(
        self,
        value: str | None,
        runtime_workspace_root: Path,
    ) -> str | None:
        if value is None:
            return None
        return value.replace(str(runtime_workspace_root), "/workspace")

    def _normalize_logical_cwd(self, cwd: str, runtime_workspace_root: Path) -> str:
        runtime_root_str = str(runtime_workspace_root)
        if cwd == runtime_root_str:
            return "/workspace"
        if cwd.startswith(f"{runtime_root_str}/"):
            suffix = cwd.removeprefix(f"{runtime_root_str}/")
            return f"/workspace/{suffix}"
        return cwd

def register_bash_tool() -> None:
    bash_tool_info = ToolInfo(
        name="bash",
        description=(
            "Execute a Bash command in the sandbox workspace. Use this for running scripts, "
            "installing packages, inspecting files, and invoking CLI tools. The sandbox workspace "
            "is exposed to you as /workspace; prefer paths under /workspace when calling this tool "
            "and set cwd to /workspace or a subdirectory. The cwd value is mapped to the current "
            "sandbox session directory on disk. When you write Python or Node scripts with the write "
            "tool, those scripts should use relative paths (e.g., 'output/report.docx') or derive "
            "paths from their working directory, not hardcode /workspace/... inside the script code. "
            "To install Python packages, run `python3 -m pip install <package>` or `pip install "
            "<package>`; pip commands are normalized to python3 -m pip. To run Python code, prefer "
            "writing a script with the write tool, then run `python3 /workspace/script.py`. Inline "
            "checks like `python3 -c \"print('ok')\"` are also allowed. For Node packages, use "
            "`npm install <package>` in the workspace, then run scripts with `node /workspace/script.js` "
            "or `npm run <script>`. If a module is missing, install it first instead of repeatedly "
            "retrying the same command."
        ),
        parameters=[
            ToolParameter(
                name="command",
                type="string",
                description=(
                    "Command to execute with bash -c. Examples: `ls -la /workspace`, "
                    "`python3 -m pip install python-docx`, `python3 /workspace/create_docx.py`, "
                    "`npm install mammoth`, `node /workspace/convert.js`. Use /workspace paths "
                    "when referring to files created by read/write tools."
                ),
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="number",
                description="Execution timeout in seconds. Increase this for package installs, builds, or document conversion tasks.",
                required=False,
                default=30,
            ),
            ToolParameter(
                name="cwd",
                type="string",
                description="Working directory for the command. Defaults to /workspace; use /workspace/subdir for files in subdirectories.",
                required=False,
                default="/workspace",
            ),
        ],
    )
    tool_registry.register_sandbox_tool(
        "bash",
        BashSandboxTool,
        tool_info=bash_tool_info,
        aliases=["Bash"],
    )


# 全局 Bash 工具实例（无 session）
bash_tool = BashSandboxTool()


async def execute_bash(
    command: str,
    timeout: float = 30.0,
    session_id: str | None = None,
    allowed_commands: list[str] | None = None,
    agent_id: str | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """便捷函数：执行 Bash 命令"""
    tool = BashSandboxTool(
        session_id=session_id,
        allowed_commands=allowed_commands,
        agent_id=agent_id,
        team_id=team_id,
    )
    return await tool.execute(command=command, timeout=timeout)
