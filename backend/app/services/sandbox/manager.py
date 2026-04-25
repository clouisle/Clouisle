"""Long-running sandbox manager."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.i18n import t
from app.llm.tools.sandbox import ExecutionResult as LegacyExecutionResult
from app.services.error_messages import resolve_user_visible_error

from .artifacts import SandboxArtifactStore
from .models import SandboxExecutionMetadata, SandboxJob, SandboxResult, SandboxTaskStatus
from .node_env import NodeEnvironmentManager
from .policies import sandbox_policy_engine
from .process_launcher import SandboxProcessLauncher
from .python_env import PythonEnvironmentManager
from .result_store import sandbox_result_store
from .workspace import SandboxWorkspace, SandboxWorkspaceManager


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

    async def execute(self, job: SandboxJob):
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

        workspace = self.workspace_manager.prepare(job.job_id)
        self._enforce_disk_limit(job, workspace, stage="prepare")
        metadata.mark_prepare_completed(datetime.now(UTC))

        try:
            result = await self._run_job(job, workspace, metadata)
            self._enforce_disk_limit(job, workspace, stage="execution")
            artifacts = await self._collect_artifacts(job, workspace, metadata)
        finally:
            if self.cleanup_workspaces:
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
        await self._save_result_snapshot(final_result)
        return final_result

    async def _run_job(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
    ) -> LegacyExecutionResult:
        env = self._build_command_env(job, workspace, metadata)

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
                timeout_seconds=job.limits.timeout_seconds,
                max_stdout_kb=job.limits.max_stdout_kb,
                max_stderr_kb=job.limits.max_stderr_kb,
            )
            metadata.mark_execute_completed(datetime.now(UTC))
            return self._parse_snippet_result(process_result, script_path)

        if job.command:
            process_result = await self.process_launcher.launch(
                self._resolve_command(job.command, env),
                cwd=str(workspace.root),
                env=env,
                timeout_seconds=job.limits.timeout_seconds,
                max_stdout_kb=job.limits.max_stdout_kb,
                max_stderr_kb=job.limits.max_stderr_kb,
            )
            metadata.mark_execute_completed(datetime.now(UTC))
            success = process_result.exit_code == 0 and not process_result.timed_out
            result_value = process_result.stdout.strip() or None
            error = None
            if process_result.timed_out:
                error = t("request_timeout")
            elif not success:
                error = process_result.stderr.strip() or t(
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

    def _prepare_snippet_execution(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        env: dict[str, str],
    ) -> tuple[Path, list[str]]:
        script_name = "snippet.py" if job.language == "python" else "snippet.js"
        script_path = workspace.root / script_name
        params: dict[str, Any] = (job.metadata.get("params") or {}) if isinstance(job.metadata, dict) else {}

        if job.language == "python":
            wrapper = self._build_python_snippet_wrapper(job.code or "", params)
            script_path.write_text(wrapper, encoding="utf-8")
            return script_path, self._build_python_snippet_command(job, script_path, env)

        wrapper = self._build_javascript_snippet_wrapper(job.code or "", params)
        script_path.write_text(wrapper, encoding="utf-8")
        self._link_node_modules_into_workspace(workspace, env)
        return script_path, self._build_javascript_snippet_command(job, script_path, env)

    def _build_python_snippet_command(
        self,
        job: SandboxJob,
        script_path: Path,
        env: dict[str, str],
    ) -> list[str]:
        command = list(job.command or ["python"])
        executable = command[0]
        if executable in {"python", "python3"}:
            executable = shutil.which("python3") or "python3"
            if env.get("VIRTUAL_ENV"):
                executable = str(Path(env["VIRTUAL_ENV"]) / "bin" / "python")
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
        return f"""
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
""".strip() + "\n"

    def _build_javascript_snippet_wrapper(self, code: str, params: dict[str, Any]) -> str:
        return f"""
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
""".strip() + "\n"

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
                stderr.strip()
                or t("sandbox_process_exit_code", exit_code=process_result.exit_code),
                fallback_key="code_tool_execution_failed",
            ),
            stdout=stdout,
            stderr=stderr,
        )

    def _build_command_env(
        self,
        job: SandboxJob,
        workspace: SandboxWorkspace,
        metadata: SandboxExecutionMetadata,
    ) -> dict[str, str]:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(workspace.root),
            "TMPDIR": str(workspace.tmp_dir),
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
        }
        needs_node_runtime = job.language == "javascript" or bool(job.command and job.command[0] in {"javascript", "node"})
        if job.python_packages or job.js_packages:
            install_started_monotonic = time.perf_counter()
            metadata.mark_install_started(datetime.now(UTC))
            try:
                if job.python_packages:
                    python_env_dir, cache_hit = self.python_env_manager.ensure_environment(
                        packages=job.python_packages,
                        runtime_profile=job.runtime_profile,
                        package_index_url=job.python_package_index_url,
                    )
                    metadata.cache_hit_python = cache_hit
                    if python_env_dir is not None:
                        env.update(self.python_env_manager.build_env_vars(python_env_dir))

                if job.js_packages:
                    node_env_dir, cache_hit = self.node_env_manager.ensure_environment(
                        packages=job.js_packages,
                        runtime_profile=job.runtime_profile,
                        registry_url=job.node_package_registry_url,
                    )
                    metadata.cache_hit_node = cache_hit
                    if node_env_dir is not None:
                        env.update(self.node_env_manager.build_env_vars(node_env_dir))
                elif needs_node_runtime:
                    self._inject_default_node_runtime(env)
            finally:
                metadata.mark_install_completed(datetime.now(UTC))
                metadata.install_ms = max(0, int((time.perf_counter() - install_started_monotonic) * 1000))
                metadata.install_duration_ms = metadata.install_ms
        else:
            if needs_node_runtime:
                self._inject_default_node_runtime(env)
            metadata.install_ms = 0
            metadata.install_duration_ms = 0

        env.update(job.env)
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
        )
        metadata.mark_collect_completed(datetime.now(UTC))
        return artifacts

    async def _load_or_create_metadata(self, job_id: str) -> SandboxExecutionMetadata:
        get_result = getattr(self.result_store, "get_result", None)
        if get_result is None:
            return SandboxExecutionMetadata()
        current = await get_result(job_id)
        return current.metadata if current is not None else SandboxExecutionMetadata()

    async def _save_result_snapshot(self, result: SandboxResult) -> None:
        save_result = getattr(self.result_store, "save_result", None)
        if save_result is not None:
            await save_result(result)
            return

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
