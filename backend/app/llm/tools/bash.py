"""Bash sandbox tool for safe shell command execution."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import (
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
    SandboxTaskStatus,
)

from .registry import ToolInfo, ToolParameter, tool_registry
from .bash_output import denoise_output

logger = logging.getLogger(__name__)
_FIND_ROOT_SCAN_PATHS = frozenset({"/", "//"})
_FIND_OPTION_ARGS_CONSUMING_VALUE = frozenset(
    {
        "-f",
        "-fprintf",
        "-newer",
        "-newermt",
        "-newerct",
        "-anewer",
        "-cnewer",
        "-path",
        "-ipath",
        "-name",
        "-iname",
        "-lname",
        "-ilname",
        "-regex",
        "-iregex",
        "-context",
        "-xtype",
        "-type",
        "-user",
        "-uid",
        "-group",
        "-gid",
        "-perm",
        "-links",
        "-inum",
        "-size",
        "-exec",
        "-execdir",
        "-ok",
        "-okdir",
    }
)
_FIND_ROOT_SCAN_PATTERN = re.compile(
    r"(?P<head>(?:^|(?:&&|\|\||;|\|)\s*)(?:command\s+)?(?:/usr/bin/)?find\s+)"
    r"(?P<quote>['\"]?)/(?P=quote)(?=\s|$)"
)
_SHELL_TOKEN_RE = re.compile(
    r"""
    (?P<op>\|\||&&|;|\||<|>|\(|\))   # shell operators
  | (?P<dq>"(?:\\.|[^"\\])*")        # double-quoted string
  | (?P<sq>'(?:[^'])*')              # single-quoted string
  | (?P<word>[^\s'"|<>()&;]+)        # bare word
    """,
    re.VERBOSE,
)


class BashRootScanError(ValueError):
    """Raised when a bash command launches a root-level find scan."""


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] in "'\"" and token[-1] == token[0]:
        return token[1:-1]
    return token


def _find_root_scan_tokens(command: str) -> list[str]:
    """Return raw tokens that pass root paths (``/`` or ``//``) to any ``find`` call.

    The scan walks shell-like tokens so it catches multi-path ``find`` forms,
    ``find -- /``, and root scans nested in compound commands. It intentionally
    does not recurse into quoted script bodies such as ``python -c 'find /'``;
    the sandbox filesystem namespace still confines code-launched scans when
    isolation is enabled.
    """
    tokens = list(_SHELL_TOKEN_RE.finditer(command))
    roots: list[str] = []
    index = 0
    while index < len(tokens):
        kind, value = tokens[index].lastgroup, tokens[index].group()
        if kind != "word":
            index += 1
            continue
        if value.rsplit("/", 1)[-1] != "find":
            index += 1
            continue
        position = index + 1
        skip_next_value = False
        while position < len(tokens):
            token_kind, token_value = (
                tokens[position].lastgroup,
                tokens[position].group(),
            )
            if token_kind == "op":
                break
            if skip_next_value:
                skip_next_value = False
                position += 1
                continue
            unquoted = _strip_quotes(token_value)
            if unquoted in {"--", "("}:
                position += 1
                continue
            if unquoted.startswith("-") and unquoted != "-":
                if unquoted in _FIND_OPTION_ARGS_CONSUMING_VALUE:
                    skip_next_value = True
                position += 1
                continue
            if unquoted in _FIND_ROOT_SCAN_PATHS:
                roots.append(token_value)
            position += 1
        index = position if position > index else index + 1
    return roots


def _rewrite_direct_find_root_scans(command: str) -> str:
    """Rewrite direct ``find /`` forms to ``find /workspace``.

    Kept for the common single-root case so agent ``find /`` calls remain a
    no-op scan of the workspace rather than an error. Shell-aware rejection in
    :func:`_reject_find_root_scans` handles forms the regex cannot reach.
    """
    return _FIND_ROOT_SCAN_PATTERN.sub(
        lambda match: (
            f"{match.group('head')}{match.group('quote')}"
            f"/workspace{match.group('quote')}"
        ),
        command,
    )


def _reject_find_root_scans(command: str) -> None:
    """Reject root-level ``find`` scans that survive the direct rewrite.

    Multi-path scans (``find /tmp /``), option-prefixed scans (``find -- /``),
    double-slash forms (``find //``), and root scans nested in compound commands
    are rejected instead of silently rewritten, because a partial rewrite could
    still leave a root path in place.
    """
    root_tokens = _find_root_scan_tokens(command)
    if root_tokens:
        raise BashRootScanError(
            "Root-level find scans are not allowed; scan /workspace instead. "
            f"Rejected root paths: {', '.join(root_tokens)}"
        )


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
        try:
            runtime_command = self._confine_find_root_scans(
                self._normalize_install_commands(command)
            )
        except BashRootScanError as exc:
            return {"success": False, "error": str(exc)}
        runtime_command = self._map_workspace_paths(
            runtime_command, runtime_workspace_root
        )
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

            failed = not result.success
            return {
                "success": result.success,
                "stdout": denoise_output(
                    self._restore_workspace_paths(
                        result.stdout, runtime_workspace_root
                    ),
                    failed=failed,
                ),
                "stderr": denoise_output(
                    self._restore_workspace_paths(
                        result.stderr, runtime_workspace_root
                    ),
                    failed=failed,
                ),
                "exit_code": result.metadata.exit_code,
                "timed_out": result.status == SandboxTaskStatus.FAILED
                and "timeout" in (result.error or "").lower(),
                "error": self._restore_workspace_paths(
                    result.error, runtime_workspace_root
                ),
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

    def _confine_find_root_scans(self, command: str) -> str:
        rewritten = _rewrite_direct_find_root_scans(command)
        _reject_find_root_scans(rewritten)
        return rewritten

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
            "is exposed as a real /workspace filesystem path; use paths under /workspace and "
            "set cwd to /workspace or a subdirectory. Python and Node scripts may use absolute "
            "/workspace paths or paths relative to their working directory. Root-level find scans "
            "are confined to /workspace. "
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
