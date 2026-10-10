"""Long-running sandbox manager."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.sandbox_network_policy import (
    SandboxNetworkPolicyError,
    get_sandbox_network_allowlist,
)
from app.schemas.response import BusinessError, ResponseCode
from app.core.i18n import t
from app.llm.tools.sandbox import ExecutionResult as LegacyExecutionResult
from app.services.error_messages import resolve_user_visible_error
from app.services import upload_gateway

from .egress_proxy import SandboxEgressProxy
from .artifacts import SandboxArtifactStore
from .models import (
    SandboxExecutionMetadata,
    SandboxJob,
    SandboxResult,
    SandboxTaskStatus,
)
from .node_env import NodeEnvironmentManager
from .policies import sandbox_policy_engine
from .process_launcher import SandboxProcessLauncher, _session_lock_fd
from .python_env import PythonEnvironmentManager
from .result_store import sandbox_result_store
from .session_store import STANDALONE_ROUND, sandbox_session_store
from .workspace import SandboxWorkspace, SandboxWorkspaceManager
from .recovery import SandboxGuardLost, presence_matches
from .worker_registry import sandbox_worker_registry
from .result_store import TERMINAL_STATUSES

_executing_job: ContextVar[SandboxJob | None] = ContextVar(
    "sandbox_manager_job", default=None
)

BLOCKED_ENV = frozenset(
    {
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "BASH_ENV",
        "ENV",
        "RUBYOPT",
        "PERL5LIB",
        "PYTHONPATH",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "npm_config_proxy",
        "npm_config_https_proxy",
        "npm_config_noproxy",
    }
)

BWRAP_USER_NS_ERROR_MARKER = "No permissions to create new namespace"


def translate_sandbox_error(message: str | None) -> str | None:
    """Map known isolation-binary failures to actionable messages.

    Keeps the raw payload in ``stderr`` while surfacing an actionable,
    localized explanation in ``error``.
    """
    if not message or BWRAP_USER_NS_ERROR_MARKER not in message:
        return message
    return t("sandbox_userns_unavailable")


class SandboxManager:
    def __init__(
        self,
        workspace_manager: SandboxWorkspaceManager | None = None,
        process_launcher: SandboxProcessLauncher | None = None,
        cleanup_workspaces: bool = True,
        result_store: Any | None = None,
        python_env_manager: PythonEnvironmentManager | None = None,
        node_env_manager: NodeEnvironmentManager | None = None,
        artifact_store: SandboxArtifactStore | None = None,
    ):
        self.workspace_manager = workspace_manager or SandboxWorkspaceManager()
        self.process_launcher = process_launcher or SandboxProcessLauncher()
        self.cleanup_workspaces = cleanup_workspaces
        self.result_store = result_store or sandbox_result_store
        self.python_env_manager = python_env_manager or PythonEnvironmentManager(
            self.workspace_manager.cache_root
        )
        self.node_env_manager = node_env_manager or NodeEnvironmentManager(
            self.workspace_manager.cache_root
        )
        self.artifact_store = artifact_store or SandboxArtifactStore(
            self.workspace_manager
        )

    async def execute(
        self,
        job: SandboxJob,
        session_id: str | None = None,
        *,
        session_agent_id: str | None = None,
        session_team_id: str | None = None,
    ):
        session_id = session_id or job.session_id
        if session_id:
            session = await sandbox_session_store.get(session_id)
            if (
                session is None
                or (
                    session_agent_id is not None
                    and session.agent_id != session_agent_id
                )
                or (session_team_id is not None and session.team_id != session_team_id)
            ):
                raise ValueError("Sandbox session not found or expired")
        job = job.model_copy(
            update={
                "session_id": session_id,
                "deadline_at": job.deadline_at
                if job.deadline_at is not None
                else time.time() + job.limits.timeout_seconds + 5,
            }
        )
        token = _executing_job.set(job)

        async def run():
            if session_id:
                if job.binding is None:
                    raise SandboxGuardLost(
                        "Session jobs require a canonical binding", "JOB_OBSOLETE"
                    )
                async with self.workspace_manager.session_lock(
                    job.binding.workspace_id,
                    deadline_at=job.deadline_at,
                    guard=lambda: self._guard(job),
                ) as lock_fd:
                    await self._guard(job)
                    lock_token = _session_lock_fd.set(lock_fd)
                    try:
                        return await self._execute(
                            job,
                            session_id=session_id,
                            session_agent_id=session_agent_id,
                            session_team_id=session_team_id,
                        )
                    finally:
                        _session_lock_fd.reset(lock_token)
            return await self._execute(job)

        task = None
        try:
            await self._guard(job)
            task = asyncio.create_task(run())
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=0.1)
                if not done:
                    await self._guard(job)
            return await task
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, SandboxGuardLost):
                    pass
            _executing_job.reset(token)

    async def _guard(self, job: SandboxJob) -> None:
        if job.deadline_at is not None and time.time() >= job.deadline_at:
            raise SandboxGuardLost("Sandbox job deadline expired", "DEADLINE_EXCEEDED")
        get_status = getattr(self.result_store, "get_status", None)
        if get_status is not None and await get_status(job.job_id) in TERMINAL_STATUSES:
            raise SandboxGuardLost("Sandbox job is already terminal", "CANCELLED")
        if job.session_id:
            binding = await sandbox_session_store.get_binding(job.session_id)
            if job.binding is None or not job.binding.matches(binding):
                raise SandboxGuardLost("Sandbox execution lost its session binding")
            if not presence_matches(
                job.binding, await sandbox_worker_registry.get(job.binding.worker_id)
            ):
                raise SandboxGuardLost("Sandbox execution lost its worker lease")

    async def _execute(
        self,
        job: SandboxJob,
        session_id: str | None = None,
        *,
        session_agent_id: str | None = None,
        session_team_id: str | None = None,
    ):
        sandbox_policy_engine.validate(job)
        metadata = await self._load_or_create_metadata(job.job_id)
        now = datetime.now(UTC)
        metadata.mark_started(now)
        metadata.mark_prepare_started(now)
        await self._save_result_snapshot(
            SandboxResult(
                job_id=job.job_id,
                status=SandboxTaskStatus.PREPARING,
                metadata=metadata,
            )
        )

        asset_team_id: UUID | None = self._optional_uuid(job.metadata.get("team_id"))
        asset_user_id: UUID | None = self._optional_uuid(job.metadata.get("user_id"))
        conversation_id: UUID | None = None
        workflow_run_id = self._optional_uuid(job.metadata.get("workflow_run_id"))
        if session_id:
            session = await sandbox_session_store.get(session_id)
            if session is None:
                raise ValueError("Sandbox session not found or expired")
            if session_agent_id is not None and session.agent_id != session_agent_id:
                raise ValueError("Sandbox session not found or expired")
            if session_team_id is not None and session.team_id != session_team_id:
                raise ValueError("Sandbox session not found or expired")
            asset_team_id = UUID(session.team_id) if session.team_id else None
            asset_user_id = UUID(session.user_id) if session.user_id else None
            conversation_id = self._optional_uuid(
                getattr(session, "conversation_id", None)
            )
            round_id = (
                await sandbox_session_store.get_active_round(session_id)
                or STANDALONE_ROUND
            )
            previous_round = await sandbox_session_store.get_workspace_round(session_id)
            if job.binding is None:
                raise SandboxGuardLost("Session job has no binding", "JOB_OBSOLETE")
            await self._guard(job)
            workspace = self.workspace_manager.restore_session(
                job.binding.workspace_id,
                allow_empty=session.disk_usage_bytes == 0,
                force=previous_round is not None and previous_round != round_id,
            )
            if not await sandbox_session_store.mark_workspace_round(
                session_id, round_id, expected_binding=job.binding
            ):
                raise SandboxGuardLost("Sandbox round binding changed")
            should_cleanup = False
        else:
            workspace = self.workspace_manager.prepare(job.job_id)
            should_cleanup = self.cleanup_workspaces

        await self._stage_input_files(
            job,
            workspace,
            team_id=asset_team_id,
            user_id=asset_user_id,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
        await self._guard(job)
        self._enforce_disk_limit(job, workspace, stage="prepare")
        metadata.mark_prepare_completed(datetime.now(UTC))

        try:
            result = await self._run_job(job, workspace, metadata)
            await self._guard(job)
            self._enforce_disk_limit(job, workspace, stage="execution")
            artifacts = await self._collect_artifacts(
                job,
                workspace,
                metadata,
                team_id=asset_team_id,
                user_id=asset_user_id,
                conversation_id=conversation_id,
                workflow_run_id=workflow_run_id,
            )
        finally:
            if session_id:
                try:
                    await self._guard(job)
                except SandboxGuardLost:
                    pass
                else:
                    await sandbox_session_store.touch(
                        session_id,
                        expected_binding=job.binding,
                        disk_usage_bytes=self.workspace_manager.workspace_size_bytes(
                            workspace
                        ),
                    )
            if should_cleanup:
                self.workspace_manager.cleanup(job.job_id)

        metadata.mark_completed(datetime.now(UTC))
        metadata.exit_code = 0 if result.success else 1
        final_status = (
            SandboxTaskStatus.COMPLETED if result.success else SandboxTaskStatus.FAILED
        )
        final_result = SandboxResult(
            job_id=job.job_id,
            status=final_status,
            success=result.success,
            result=result.result,
            error=result.error,
            stdout=result.stdout,
            stderr=result.stderr,
            artifacts=artifacts,
            metadata=metadata,
        )
        return await self._save_result_snapshot(final_result)

    async def _run_job(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
    ) -> LegacyExecutionResult:
        async with SandboxEgressProxy(
            job_id=job.job_id,
            allowed_hosts=await get_sandbox_network_allowlist(),
        ) as network_proxy:
            return await self._run_job_with_proxy(
                job,
                workspace,
                metadata,
                network_proxy,
            )

    async def _run_job_with_proxy(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
        network_proxy: SandboxEgressProxy,
    ) -> LegacyExecutionResult:
        try:
            env = await self._build_command_env(
                job,
                workspace,
                metadata,
                network_proxy,
            )
        except SandboxNetworkPolicyError as exc:
            return LegacyExecutionResult(
                success=False,
                error=str(exc),
                stderr=str(exc),
            )
        except subprocess.CalledProcessError as exc:
            return LegacyExecutionResult(
                success=False,
                error=t("tool_execution_failed"),
                stdout=exc.output or "",
                stderr=exc.stderr or "",
            )

        metadata.mark_execute_started(datetime.now(UTC))
        await self._save_result_snapshot(
            SandboxResult(
                job_id=job.job_id,
                status=SandboxTaskStatus.RUNNING,
                metadata=metadata,
            )
        )

        if job.code and job.language:
            script_path, command = self._prepare_snippet_execution(job, workspace, env)
            process_result = await self.process_launcher.launch(
                command,
                cwd=str(workspace.root),
                env=env,
                timeout_seconds=min(
                    job.limits.timeout_seconds,
                    max(0.001, job.deadline_at - time.time()),
                )
                if job.deadline_at is not None
                else job.limits.timeout_seconds,
                max_stdout_kb=job.limits.max_stdout_kb,
                max_stderr_kb=job.limits.max_stderr_kb,
                workspace_root=str(workspace.root),
                cache_root=str(self.workspace_manager.cache_root),
                network_proxy=network_proxy,
            )
            metadata.mark_execute_completed(datetime.now(UTC))
            return self._parse_snippet_result(process_result, script_path)

        if job.command:
            cwd = self.workspace_manager.resolve_workspace_path(workspace, job.cwd)
            process_result = await self.process_launcher.launch(
                self._resolve_command(job.command, env),
                cwd=str(cwd),
                env=env,
                timeout_seconds=min(
                    job.limits.timeout_seconds,
                    max(0.001, job.deadline_at - time.time()),
                )
                if job.deadline_at is not None
                else job.limits.timeout_seconds,
                max_stdout_kb=job.limits.max_stdout_kb,
                max_stderr_kb=job.limits.max_stderr_kb,
                workspace_root=str(workspace.root),
                cache_root=str(self.workspace_manager.cache_root),
                network_proxy=network_proxy,
            )
            metadata.mark_execute_completed(datetime.now(UTC))
            success = process_result.exit_code == 0 and not process_result.timed_out
            result_value = process_result.stdout.strip() or None
            error = None
            if process_result.timed_out:
                error = t("request_timeout")
            elif not success:
                error = translate_sandbox_error(process_result.stderr.strip()) or t(
                    "sandbox_process_exit_code",
                    exit_code=process_result.exit_code,
                )
            return LegacyExecutionResult(
                success=success,
                result=result_value,
                error=error,
                stdout=process_result.stdout,
                stderr=process_result.stderr,
            )

        metadata.mark_execute_completed(datetime.now(UTC))
        return LegacyExecutionResult(
            success=False,
            error=t("sandbox_missing_executable_payload"),
        )

    async def _stage_input_files(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        *,
        team_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
    ) -> None:
        for input_file in job.input_files:
            active = _executing_job.get()
            if active is not None:
                await self._guard(active)
            target = self.workspace_manager.resolve_workspace_path(
                workspace, input_file.target_path
            )
            if target.exists():
                raise FileExistsError(
                    f"Sandbox input target already exists: {input_file.target_path}"
                )
            if input_file.asset_id is not None:
                from app.services.asset import asset_service

                if input_file.asset_ref is not None:
                    from app.models.asset import AssetScopeType
                    from app.models.user import User
                    from app.services.asset_access import resolve_authorized_asset_ref

                    scope_type = AssetScopeType(input_file.scope_type)
                    expected_scope_id = (
                        conversation_id
                        if scope_type == AssetScopeType.CONVERSATION
                        else workflow_run_id
                    )
                    if (
                        expected_scope_id is None
                        or input_file.scope_id != expected_scope_id
                    ):
                        raise BusinessError(
                            code=ResponseCode.PERMISSION_DENIED,
                            msg_key="access_denied",
                            status_code=403,
                        )
                    user = (
                        await User.filter(id=user_id)
                        .prefetch_related("roles__permissions")
                        .first()
                        if user_id is not None
                        else None
                    )
                    asset = await resolve_authorized_asset_ref(
                        input_file.asset_ref,
                        scope_type=scope_type,
                        scope_id=input_file.scope_id,
                        user=user,
                        expected_team_id=team_id,
                    )
                    if asset.id != input_file.asset_id:
                        raise BusinessError(
                            code=ResponseCode.PERMISSION_DENIED,
                            msg_key="access_denied",
                            status_code=403,
                        )
                else:
                    if conversation_id is not None or workflow_run_id is not None:
                        raise BusinessError(
                            code=ResponseCode.PERMISSION_DENIED,
                            msg_key="access_denied",
                            status_code=403,
                        )
                    asset = await asset_service.get_authorized(
                        input_file.asset_id,
                        team_id=team_id,
                        user_id=user_id,
                    )

                if settings.UPLOAD_STORAGE_MODE == "remote":
                    content = await upload_gateway.read(asset.storage_key)
                    if (
                        len(content) != asset.size
                        or hashlib.sha256(content).hexdigest() != asset.checksum
                    ):
                        raise BusinessError(
                            code=ResponseCode.VALIDATION_ERROR,
                            msg_key="sandbox_input_checksum_mismatch",
                        )
                else:
                    from app.api.v1.endpoints.upload import UPLOAD_ROOT
                    from app.services.upload_storage import get_upload_storage_backend

                    storage = await get_upload_storage_backend(UPLOAD_ROOT)
                    content = await asset_service.read(asset, storage=storage)
            else:
                assert input_file.content_base64 is not None
                content = base64.b64decode(input_file.content_base64, validate=True)

            if (
                input_file.expected_size is not None
                and len(content) != input_file.expected_size
            ):
                raise BusinessError(
                    code=ResponseCode.VALIDATION_ERROR,
                    msg_key="sandbox_input_size_mismatch",
                )
            checksum = hashlib.sha256(content).hexdigest()
            if (
                input_file.expected_checksum is not None
                and checksum != input_file.expected_checksum
            ):
                raise BusinessError(
                    code=ResponseCode.VALIDATION_ERROR,
                    msg_key="sandbox_input_checksum_mismatch",
                )

            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f".{target.name}.partial")
            try:
                partial.write_bytes(content)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
            if input_file.mode is not None:
                target.chmod(input_file.mode)

    def _prepare_snippet_execution(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        env: dict[str, str],
    ) -> tuple[Path, list[str]]:
        script_name = "snippet.py" if job.language == "python" else "snippet.js"
        script_path = workspace.root / script_name
        params: dict[str, Any] = (
            (job.metadata.get("params") or {}) if isinstance(job.metadata, dict) else {}
        )

        if job.language == "python":
            wrapper = self._build_python_snippet_wrapper(job.code or "", params)
            script_path.write_text(wrapper, encoding="utf-8")
            return script_path, self._build_python_snippet_command(
                job, script_path, env
            )

        wrapper = self._build_javascript_snippet_wrapper(job.code or "", params)
        script_path.write_text(wrapper, encoding="utf-8")
        self._link_node_modules_into_workspace(workspace, env)
        return script_path, self._build_javascript_snippet_command(
            job, script_path, env
        )

    def _build_python_snippet_command(
        self,
        job: SandboxJob,
        script_path: Path,
        env: dict[str, str],
    ) -> list[str]:
        command = list(job.command or ["python"])
        executable = command[0]
        if executable in {"python", "python3"}:
            executable = self._python_executable(env)
        return self._resolve_command([executable, *command[1:], str(script_path)], env)

    def _build_javascript_snippet_command(
        self,
        job: SandboxJob,
        script_path: Path,
        env: dict[str, str],
    ) -> list[str]:
        command = list(job.command or ["javascript"])
        executable = command[0]
        if executable in {"javascript", "node"}:
            executable = env.get("SANDBOX_NODE_BINARY") or "node"
        return self._resolve_command([executable, *command[1:], str(script_path)], env)

    def _build_python_snippet_wrapper(self, code: str, params: dict[str, Any]) -> str:
        indented_code = "\n".join(f"    {line}" for line in code.split("\n"))
        return (
            f"""
import json
import sys
from io import StringIO

params = json.loads({json.dumps(params)!r})
_logs = []
_original_stdout = sys.stdout
sys.stdout = StringIO()

def __execute__():
{indented_code}

try:
    result = __execute__()
    _captured = sys.stdout.getvalue()
    sys.stdout = _original_stdout
    if _captured:
        _logs.extend(_captured.strip().split('\\n'))
    output = {{"success": True, "result": result, "logs": _logs}}
    print('__RESULT__' + json.dumps(output, default=str) + '__END__')
except Exception as e:
    sys.stdout = _original_stdout
    output = {{"success": False, "error": str(e), "logs": _logs}}
    print('__RESULT__' + json.dumps(output, default=str) + '__END__')
""".strip()
            + "\n"
        )

    def _build_javascript_snippet_wrapper(
        self, code: str, params: dict[str, Any]
    ) -> str:
        return (
            f"""
const params = {json.dumps(params)};
const logs = [];
const originalLog = console.log;
console.log = (...args) => {{
  logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
}};

async function __execute__() {{
{code}
}}

(async () => {{
  try {{
    const result = await __execute__();
    console.log = originalLog;
    process.stdout.write('__RESULT__' + JSON.stringify({{ success: true, result, logs }}) + '__END__');
  }} catch (e) {{
    console.log = originalLog;
    process.stdout.write('__RESULT__' + JSON.stringify({{ success: false, error: e.message || String(e), logs }}) + '__END__');
  }}
}})();
""".strip()
            + "\n"
        )

    def _link_node_modules_into_workspace(
        self,
        workspace: SandboxWorkspace,
        env: dict[str, str],
    ) -> None:
        node_path = env.get("NODE_PATH")
        if not node_path:
            return

        source = Path(node_path)
        if not source.exists():
            return

        target = workspace.root / "node_modules"
        if target.exists() or target.is_symlink():
            return
        target.symlink_to(source, target_is_directory=True)

    def _python_executable(self, env: dict[str, str]) -> str:
        if env.get("VIRTUAL_ENV"):
            return str(Path(env["VIRTUAL_ENV"]) / "bin" / "python")

        for candidate in settings.SANDBOX_DEFAULT_PYTHON_BINARIES:
            if Path(candidate).exists():
                return candidate

        resolved = shutil.which("python3", path=env.get("PATH"))
        if resolved and "/.venv/" not in resolved and "/backend/.venv/" not in resolved:
            return resolved
        return "python3"

    def _resolve_command(
        self,
        command: list[str],
        env: dict[str, str],
    ) -> list[str]:
        if not command:
            return command

        executable = command[0]
        if os.path.isabs(executable):
            return command

        resolved = shutil.which(executable, path=env.get("PATH"))
        if not resolved:
            return command
        return [resolved, *command[1:]]

    def _parse_snippet_result(
        self,
        process_result,
        script_path: Path,
    ) -> LegacyExecutionResult:
        del script_path
        stdout = process_result.stdout
        stderr = process_result.stderr
        if "__RESULT__" in stdout and "__END__" in stdout:
            start = stdout.index("__RESULT__") + len("__RESULT__")
            end = stdout.index("__END__")
            payload = json.loads(stdout[start:end])
            logs = payload.get("logs", [])
            return LegacyExecutionResult(
                success=bool(payload.get("success", False)),
                result=payload.get("result"),
                error=None
                if payload.get("success", False)
                else resolve_user_visible_error(
                    payload.get("error"),
                    fallback_key="code_tool_execution_failed",
                ),
                stdout="\n".join(logs) if logs else "",
                stderr=stderr,
            )

        if process_result.timed_out:
            return LegacyExecutionResult(
                success=False,
                error=t("request_timeout"),
                stdout=stdout,
                stderr=stderr,
            )

        return LegacyExecutionResult(
            success=process_result.exit_code == 0,
            result=stdout.strip() or None,
            error=None
            if process_result.exit_code == 0
            else resolve_user_visible_error(
                translate_sandbox_error(stderr.strip())
                or t(
                    "sandbox_process_exit_code",
                    exit_code=process_result.exit_code,
                ),
                fallback_key="code_tool_execution_failed",
            ),
            stdout=stdout,
            stderr=stderr,
        )

    async def _build_command_env(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
        network_proxy: SandboxEgressProxy,
    ) -> dict[str, str]:
        env = {
            "HOME": str(workspace.root),
            "TMPDIR": str(workspace.tmp_dir),
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        }
        env.update(
            self.python_env_manager.build_workspace_env_vars(
                workspace.root,
                workspace.tmp_dir,
            )
        )

        for key in BLOCKED_ENV:
            env.pop(key, None)

        needs_node_runtime = job.language == "javascript" or bool(
            job.command and job.command[0] in {"javascript", "node"}
        )
        if job.python_packages or job.js_packages:
            install_started_monotonic = time.perf_counter()
            metadata.mark_install_started(datetime.now(UTC))
            try:
                if job.python_packages:
                    (
                        python_env_dir,
                        cache_hit,
                    ) = await self.python_env_manager.ensure_environment(
                        packages=job.python_packages,
                        runtime_profile=job.runtime_profile,
                        process_launcher=self.process_launcher,
                        network_proxy=network_proxy,
                        package_index_url=job.python_package_index_url,
                    )
                    metadata.cache_hit_python = cache_hit
                    if python_env_dir is not None:
                        env.update(
                            self.python_env_manager.build_env_vars(python_env_dir)
                        )

                if job.js_packages:
                    (
                        node_env_dir,
                        cache_hit,
                    ) = await self.node_env_manager.ensure_environment(
                        packages=job.js_packages,
                        runtime_profile=job.runtime_profile,
                        process_launcher=self.process_launcher,
                        network_proxy=network_proxy,
                        registry_url=job.node_package_registry_url,
                    )
                    metadata.cache_hit_node = cache_hit
                    if node_env_dir is not None:
                        env.update(self.node_env_manager.build_env_vars(node_env_dir))
                elif needs_node_runtime:
                    self._inject_default_node_runtime(env)
            finally:
                metadata.mark_install_completed(datetime.now(UTC))
                metadata.install_ms = max(
                    0, int((time.perf_counter() - install_started_monotonic) * 1000)
                )
                metadata.install_duration_ms = metadata.install_ms
        else:
            if needs_node_runtime:
                self._inject_default_node_runtime(env)
            metadata.install_ms = 0
            metadata.install_duration_ms = 0

        env.update(
            {key: value for key, value in job.env.items() if key not in BLOCKED_ENV}
        )
        return env

    def _inject_default_node_runtime(self, env: dict[str, str]) -> None:
        node_binary = self.node_env_manager.node_binary()
        node_bin_dir = str(Path(node_binary).parent)
        current_path = env.get("PATH", "")
        env["SANDBOX_NODE_BINARY"] = node_binary
        if current_path:
            env["PATH"] = f"{node_bin_dir}{os.pathsep}{current_path}"
        else:
            env["PATH"] = node_bin_dir

    async def _collect_artifacts(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
        *,
        team_id: UUID | None = None,
        user_id: UUID | None = None,
        conversation_id: UUID | None = None,
        workflow_run_id: UUID | None = None,
    ):
        if not job.artifacts:
            metadata.collect_ms = 0
            return []

        metadata.mark_collect_started(datetime.now(UTC))
        await self._save_result_snapshot(
            SandboxResult(
                job_id=job.job_id,
                status=SandboxTaskStatus.COLLECTING,
                metadata=metadata,
            )
        )
        artifacts = await self.artifact_store.collect(
            job_id=job.job_id,
            artifacts=job.artifacts,
            workspace=workspace,
            artifact_limits=job.artifact_limits,
        )
        active = _executing_job.get()
        if active is not None:
            await self._guard(active)
        await self._register_artifact_assets(
            artifacts,
            job=job,
            team_id=team_id,
            user_id=user_id,
            conversation_id=conversation_id,
            workflow_run_id=workflow_run_id,
        )
        metadata.mark_collect_completed(datetime.now(UTC))
        return artifacts

    async def _register_artifact_assets(
        self,
        artifacts: list[Any],
        *,
        job: SandboxJob,
        team_id: UUID | None,
        user_id: UUID | None,
        conversation_id: UUID | None,
        workflow_run_id: UUID | None,
    ) -> None:
        from app.models.asset import AssetScopeType, AssetSource
        from app.services.asset import asset_service

        scope: tuple[AssetScopeType, UUID] | None = None
        if workflow_run_id is not None:
            scope = (AssetScopeType.WORKFLOW_RUN, workflow_run_id)
        elif conversation_id is not None:
            scope = (AssetScopeType.CONVERSATION, conversation_id)
        if scope is None:
            return
        for artifact in artifacts:
            active = _executing_job.get()
            if active is not None:
                await self._guard(active)
            storage_key = self._artifact_storage_key(artifact.url)
            if storage_key is None or not artifact.checksum:
                continue
            asset = await asset_service.register(
                storage_key=storage_key,
                original_filename=artifact.filename,
                content_type=artifact.content_type or "application/octet-stream",
                size=artifact.size,
                checksum=artifact.checksum,
                source=AssetSource.SANDBOX_ARTIFACT,
                team_id=team_id,
                created_by_id=user_id,
                provenance={
                    "job_id": job.job_id,
                    "workspace_path": artifact.path,
                },
            )
            if active is not None:
                await self._guard(active)
            binding = await asset_service.get_or_create_ref(
                scope_type=scope[0],
                scope_id=scope[1],
                asset=asset,
            )
            if active is not None:
                await self._guard(active)
            artifact.asset_id = asset.id
            artifact.asset_ref = binding.ref

    @staticmethod
    def _optional_uuid(value: Any) -> UUID | None:
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _artifact_storage_key(url: str | None) -> str | None:
        marker = "/api/v1/upload/files/"
        if not url or marker not in url:
            return None
        return url.split(marker, 1)[1]

    async def _load_or_create_metadata(self, job_id: str) -> SandboxExecutionMetadata:
        get_result = getattr(self.result_store, "get_result", None)
        if get_result is None:
            return SandboxExecutionMetadata()
        current = await get_result(job_id)
        return current.metadata if current is not None else SandboxExecutionMetadata()

    async def _save_result_snapshot(self, result: SandboxResult) -> SandboxResult:
        job = _executing_job.get()
        if job is not None:
            await self._guard(job)
            result.session_id = job.session_id
            result.binding = job.binding
            result.deadline_at = job.deadline_at
        save_result = getattr(self.result_store, "save_result", None)
        if save_result is not None:
            return await save_result(result) or result
        return (
            await self.result_store.update_status(
                result.job_id,
                result.status,
                metadata=result.metadata,
                success=result.success,
                result=result.result,
                error=result.error,
                stdout=result.stdout,
                stderr=result.stderr,
                artifacts=result.artifacts,
            )
            or result
        )

    def _enforce_disk_limit(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        *,
        stage: str,
    ) -> None:
        if job.limits.disk_mb <= 0:
            usage_bytes = self.workspace_manager.workspace_size_bytes(workspace)
        elif not self._should_measure_workspace_usage(job):
            return
        else:
            usage_bytes = self.workspace_manager.workspace_size_bytes(workspace)
        limit_bytes = job.limits.disk_mb * 1024 * 1024
        if usage_bytes > limit_bytes:
            raise RuntimeError(
                t(
                    "sandbox_disk_limit_exceeded",
                    stage=stage,
                    usage_bytes=usage_bytes,
                    limit_bytes=limit_bytes,
                )
            )

    def _should_measure_workspace_usage(self, job: SandboxJob) -> bool:
        return job.limits.disk_mb > 0 or bool(job.artifacts)

    async def run_once(self) -> None:
        return None
