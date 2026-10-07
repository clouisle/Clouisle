import json
import sys
import subprocess
from pathlib import Path

import pytest
from app.core.config import settings

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxJob, SandboxJobSource
from app.services.sandbox.process_launcher import (
    ProcessLaunchResult,
    SandboxProcessLauncher,
)
from app.services.sandbox.workspace import SandboxWorkspaceManager


class FakePythonEnvManager:
    def __init__(self, env_dir: Path):
        self.env_dir = env_dir
        self.calls = []

    async def ensure_environment(
        self, *, packages, runtime_profile, package_index_url=None, **kwargs
    ):
        self.calls.append((packages, runtime_profile, package_index_url))
        return self.env_dir, True

    def build_env_vars(self, env_dir: Path):
        return {
            "VIRTUAL_ENV": str(env_dir),
            "PATH": f"{env_dir / 'bin'}:/usr/bin",
        }

    def build_workspace_env_vars(self, workspace_root: Path, tmp_dir: Path):
        return {"PATH": self.runtime_path()}

    def runtime_path(self):
        return "/usr/local/bin:/usr/bin:/bin"


class InMemoryResultStore:
    async def update_status(self, job_id, status, *, metadata=None, **updates):
        from app.services.sandbox.models import SandboxResult

        result = SandboxResult(job_id=job_id, status=status, metadata=metadata)
        for key, value in updates.items():
            setattr(result, key, value)
        return result


class FakeProcessLauncher:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.calls = []

    async def launch(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return ProcessLaunchResult(exit_code=0, stdout=self.stdout)


@pytest.mark.anyio
class TestSandboxSnippetRuntime:
    async def test_python_snippet_with_packages_uses_env_manager(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        env_dir = tmp_path / "cache" / "py-env"
        bin_dir = env_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        python_env_manager = FakePythonEnvManager(env_dir)
        payload = json.dumps({"success": True, "result": {"value": 42}, "logs": []})
        launcher = FakeProcessLauncher(stdout=f"__RESULT__{payload}__END__")

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            python_env_manager=python_env_manager,
            process_launcher=launcher,
        )
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="python",
            code="return {'value': params['value']}",
            command=["python"],
            python_packages=["requests==2.32.3"],
            metadata={"params": {"value": 42}},
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.result == {"value": 42}
        assert python_env_manager.calls == [(["requests==2.32.3"], "standard", None)]
        assert launcher.calls[0][0][0] == str(env_dir / "bin" / "python")
        assert launcher.calls[0][1]["env"]["VIRTUAL_ENV"] == str(env_dir)

    async def test_python_snippet_appends_script_path_after_custom_argv(
        self, tmp_path: Path
    ):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        env_dir = tmp_path / "cache" / "py-env"
        bin_dir = env_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        python_env_manager = FakePythonEnvManager(env_dir)
        payload = json.dumps({"success": True, "result": {"value": 1}, "logs": []})
        launcher = FakeProcessLauncher(stdout=f"__RESULT__{payload}__END__")

        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            python_env_manager=python_env_manager,
            process_launcher=launcher,
        )
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="python",
            code="return {'value': 1}",
            command=["python", "-X", "utf8"],
            python_packages=["requests==2.32.3"],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert launcher.calls[0][0][:3] == [
            str(env_dir / "bin" / "python"),
            "-X",
            "utf8",
        ]
        assert launcher.calls[0][0][3].endswith("snippet.py")

    async def test_package_install_failure_returns_blocked_host_diagnostic(
        self, tmp_path: Path
    ):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
        python_env_manager = FakePythonEnvManager(tmp_path / "cache" / "py-env")

        async def fail_install(**kwargs):
            raise subprocess.CalledProcessError(
                1,
                ["pip", "install"],
                stderr=(
                    "[sandbox-network] blocked host=evil.example "
                    "port=443 reason=not_allowlisted"
                ),
            )

        python_env_manager.ensure_environment = fail_install
        launcher = FakeProcessLauncher(stdout="must not execute")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            python_env_manager=python_env_manager,
            process_launcher=launcher,
        )
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="python",
            code="return 1",
            command=["python"],
            python_packages=["requests==2.32.3"],
        )

        result = await manager.execute(job)

        assert result.success is False
        assert "blocked host=evil.example" in result.stderr
        assert launcher.calls == []

    async def test_python_snippet_preserves_boolean_parameters(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", False)
        monkeypatch.setattr(
            settings, "SANDBOX_DEFAULT_PYTHON_BINARIES", [sys.executable]
        )

        class LocalProcessLauncher(SandboxProcessLauncher):
            async def launch(self, command, **kwargs):
                kwargs.pop("network_proxy", None)
                return await super().launch(command, **kwargs)

        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            python_env_manager=FakePythonEnvManager(tmp_path / "cache" / "py-env"),
            process_launcher=LocalProcessLauncher(),
        )
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="python",
            code=(
                "return {'flag': params['rules']['success'], "
                "'status_code': params['rules']['status_code']}"
            ),
            metadata={"params": {"rules": {"success": True, "status_code": 200}}},
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.result == {"flag": True, "status_code": 200}
