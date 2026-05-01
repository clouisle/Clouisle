import base64
import json
import subprocess
from pathlib import Path

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import (
    SandboxArtifact,
    SandboxArtifactLimits,
    SandboxArtifactSpec,
    SandboxInputFileSpec,
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.process_launcher import ProcessLaunchResult
from app.services.sandbox.python_env import PythonEnvironmentManager
from app.services.sandbox.workspace import SandboxWorkspaceManager


class InMemoryResultStore:
    def __init__(self):
        self.results: dict[str, SandboxResult] = {}

    async def update_status(self, job_id: str, status: SandboxTaskStatus, *, metadata=None, **updates):
        current = self.results.get(job_id, SandboxResult(job_id=job_id))
        current.status = status
        if metadata is not None:
            current.metadata = metadata
        for key, value in updates.items():
            setattr(current, key, value)
        self.results[job_id] = current
        return current


class FakeProcessLauncher:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.calls = []

    async def launch(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return ProcessLaunchResult(exit_code=0, stdout=self.stdout)


class FakePythonEnvManager:
    def __init__(self):
        self.calls = []
        self.workspace_env_calls = []

    def ensure_environment(self, *, packages, runtime_profile, package_index_url=None):
        self.calls.append((packages, runtime_profile, package_index_url))
        return None, False

    def build_env_vars(self, env_dir):
        return {}

    def build_workspace_env_vars(self, workspace_root, tmp_dir):
        self.workspace_env_calls.append((workspace_root, tmp_dir))
        return {
            "VIRTUAL_ENV": str(workspace_root / ".venv"),
            "PYTHONNOUSERSITE": "1",
            "PATH": "/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin",
            "PIP_CACHE_DIR": str(tmp_dir / "pip-cache"),
        }

    def runtime_path(self):
        return "/usr/local/bin:/usr/bin:/bin"


class FakeArtifactStore:
    def __init__(self, artifacts=None, error=None):
        self.artifacts = artifacts or []
        self.error = error
        self.calls = []

    async def collect(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.artifacts


class WorkspacePythonEnvironmentProbe:
    def __init__(self, python_binary: str):
        self._python_binary = python_binary

    def python_binary(self) -> str:
        return self._python_binary


class FakePath:
    def __init__(self, value: str, exists: bool = True):
        self.value = value
        self._exists = exists

    def exists(self):
        return self._exists

    def __str__(self):
        return self.value


@pytest.mark.anyio
class TestSandboxManager:
    async def test_executes_legacy_python_snippet(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="python",
            code="return {'value': params['value'] * 2}",
            command=["python"],
            metadata={"params": {"value": 21}},
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.result == {"value": 42}
        assert result.status == "completed"
        assert result.metadata.queue_wait_ms is not None
        assert result.metadata.prepare_ms is not None
        assert result.metadata.execute_ms is not None
        assert result.metadata.collect_ms == 0
        assert result.metadata.total_ms == result.metadata.duration_ms

    async def test_executes_legacy_javascript_snippet(self, tmp_path: Path):
        payload = json.dumps({"success": True, "result": {"value": 42}, "logs": []})
        launcher = FakeProcessLauncher(stdout=f"__RESULT__{payload}__END__")
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            process_launcher=launcher,
        )
        manager.node_env_manager._node_exec_path_cache = "/opt/runtime/node"
        job = SandboxJob(
            source=SandboxJobSource.LEGACY_SNIPPET,
            language="javascript",
            code="return { value: params.value * 3 };",
            command=["javascript"],
            metadata={"params": {"value": 14}},
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.result == {"value": 42}
        assert launcher.calls[0][0][0] == "/opt/runtime/node"

    async def test_executes_raw_command_in_workspace(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('hello sandbox')").decode("ascii"),
                ),
            ],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.stdout.strip() == "hello sandbox"
        assert result.result == "hello sandbox"

    def test_python_executable_prefers_runtime_python_over_backend_venv(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        env = {"PATH": "/app/backend/.venv/bin:/usr/local/bin:/usr/bin"}

        from unittest.mock import patch

        with patch(
            "app.services.sandbox.manager.Path",
            side_effect=lambda value: FakePath(value, exists=value == "/usr/local/bin/python3"),
        ), patch(
            "app.services.sandbox.manager.shutil.which",
            return_value="/app/backend/.venv/bin/python3",
        ):
            executable = manager._python_executable(env)

        assert executable == "/usr/local/bin/python3"

    async def test_stages_inline_input_files_and_honors_command_cwd(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.SKILL,
            command=["python3", "run.py"],
            cwd="/workspace/skill",
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/skill/run.py",
                    content_base64=base64.b64encode(
                        b"from pathlib import Path; print(Path.cwd().name)"
                    ).decode("ascii"),
                ),
            ],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.stdout.strip() == "skill"

    async def test_collects_required_artifact(self, tmp_path: Path):
        artifact_store = FakeArtifactStore(
            artifacts=[
                SandboxArtifact(
                    path="/workspace/output/result.txt",
                    file_type="file",
                    size=2,
                    checksum="abc",
                    content_type="text/plain",
                    storage_path="/tmp/uploads/result.txt",
                    url="/api/v1/upload/files/sandbox-artifacts/2026/05/result.txt",
                    filename="result.txt",
                )
            ]
        )
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            artifact_store=artifact_store,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(
                        b"from pathlib import Path; Path('output/result.txt').parent.mkdir(parents=True, exist_ok=True); Path('output/result.txt').write_text('ok')"
                    ).decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/result.txt")],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.metadata.collect_ms is not None
        assert len(result.artifacts) == 1
        assert result.artifacts[0].path == "/workspace/output/result.txt"
        assert result.artifacts[0].file_type == "file"
        assert result.artifacts[0].size == 2
        assert result.artifacts[0].checksum
        assert result.artifacts[0].content_type == "text/plain"
        assert result.artifacts[0].storage_path
        assert result.artifacts[0].url.startswith("/api/v1/upload/files/")
        assert result.artifacts[0].filename

    async def test_collects_directory_artifact(self, tmp_path: Path):
        artifact_store = FakeArtifactStore(
            artifacts=[
                SandboxArtifact(
                    path="/workspace/output/reports",
                    file_type="directory",
                    size=3,
                    checksum="abc",
                    content_type="application/zip",
                    storage_path="/tmp/uploads/reports.zip",
                    url="/api/v1/upload/files/sandbox-artifacts/2026/05/reports.zip",
                    filename="reports.zip",
                )
            ]
        )
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            artifact_store=artifact_store,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(
                        b"from pathlib import Path; Path('output/reports').mkdir(parents=True, exist_ok=True); Path('output/reports/a.txt').write_text('A'); Path('output/reports/b.txt').write_text('BC')"
                    ).decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/reports")],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert len(result.artifacts) == 1
        assert result.artifacts[0].file_type == "directory"
        assert result.artifacts[0].size == 3
        assert result.artifacts[0].content_type == "application/zip"
        assert result.artifacts[0].url.startswith("/api/v1/upload/files/")
        assert result.artifacts[0].filename.endswith(".zip")

    async def test_skips_optional_missing_artifact(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('done')").decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/missing.txt", optional=True)],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.artifacts == []

    async def test_fails_when_required_artifact_missing(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('done')").decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/missing.txt")],
        )

        with pytest.raises(FileNotFoundError):
            await manager.execute(job)

    async def test_fails_when_disk_limit_is_exceeded(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(
                        b"from pathlib import Path; Path('output/blob.bin').write_bytes(b'x' * 2048)"
                    ).decode("ascii"),
                ),
            ],
            limits=SandboxLimits(disk_mb=128).model_copy(update={"disk_mb": 0}),
        )

        with pytest.raises(RuntimeError, match="disk limit exceeded"):
            await manager.execute(job)

    async def test_builds_python_env_for_package_install(self, tmp_path: Path):
        launcher = FakeProcessLauncher(stdout="ok")
        python_env_manager = FakePythonEnvManager()
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            process_launcher=launcher,
            python_env_manager=python_env_manager,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('ok')").decode("ascii"),
                ),
            ],
            python_packages=["requests==2.32.3"],
            python_package_index_url=" https://mirror.example.com/simple/ ",
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.metadata.install_ms is not None
        assert result.metadata.install_duration_ms == result.metadata.install_ms
        assert python_env_manager.calls == [(["requests==2.32.3"], "standard", "https://mirror.example.com/simple")]
        assert len(python_env_manager.workspace_env_calls) == 1

    async def test_injects_workspace_python_env_for_plain_commands(self, tmp_path: Path):
        launcher = FakeProcessLauncher(stdout="ok")
        python_env_manager = FakePythonEnvManager()
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            process_launcher=launcher,
            python_env_manager=python_env_manager,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('ok')").decode("ascii"),
                ),
            ],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert len(launcher.calls) == 1
        env = launcher.calls[0][1]["env"]
        assert env["VIRTUAL_ENV"].endswith("/.venv")
        assert env["PYTHONNOUSERSITE"] == "1"
        assert env["PIP_CACHE_DIR"].endswith("/tmp/pip-cache")
        assert env["PATH"].startswith("/workspace/.venv/bin:")
        assert len(python_env_manager.workspace_env_calls) == 1

    def test_workspace_env_repairs_missing_pip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        manager = PythonEnvironmentManager(cache_root=tmp_path / "cache")
        monkeypatch.setattr(manager, "python_binary", lambda: "/usr/local/bin/python3")
        env_dir = tmp_path / "workspace" / ".venv"
        bin_dir = env_dir / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "python").write_text("", encoding="utf-8")

        calls: list[list[str]] = []

        def fake_run(command, check, stdout, stderr):
            calls.append(command)
            if command[:3] == [str(bin_dir / "python"), "-m", "ensurepip"]:
                (bin_dir / "pip").write_text("", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(subprocess, "run", fake_run)

        result = manager.ensure_workspace_environment(tmp_path / "workspace")

        assert result == env_dir
        assert calls == [[str(bin_dir / "python"), "-m", "ensurepip", "--upgrade"]]
        assert (bin_dir / "pip").exists()

    async def test_passes_artifact_limits_to_artifact_store(self, tmp_path: Path):
        artifact_store = FakeArtifactStore(
            artifacts=[
                SandboxArtifact(
                    path="/workspace/output/result.txt",
                    file_type="file",
                    size=2,
                    checksum="abc",
                    content_type="text/plain",
                    storage_path="/tmp/uploads/result.txt",
                    url="/api/v1/upload/files/sandbox-artifacts/2026/05/result.txt",
                    filename="result.txt",
                )
            ]
        )
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            artifact_store=artifact_store,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(
                        b"from pathlib import Path; Path('output/result.txt').parent.mkdir(parents=True, exist_ok=True); Path('output/result.txt').write_text('ok')"
                    ).decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/result.txt")],
            artifact_limits=SandboxArtifactLimits(max_size_mb=2, max_total_size_mb=3),
        )

        result = await manager.execute(job)

        assert result.success is True
        assert artifact_store.calls[0]["artifact_limits"].max_size_mb == 2
        assert artifact_store.calls[0]["artifact_limits"].max_total_size_mb == 3

    async def test_returns_safe_artifact_collection_error(self, tmp_path: Path):
        artifact_store = FakeArtifactStore(
            error=ValueError("Artifact '/workspace/output/big.bin' is 2048 bytes, exceeding per-file limit 1024 bytes")
        )
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            artifact_store=artifact_store,
        )
        job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["python3", "run.py"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/run.py",
                    content_base64=base64.b64encode(b"print('done')").decode("ascii"),
                ),
            ],
            artifacts=[SandboxArtifactSpec(path="/workspace/output/big.bin")],
        )

        with pytest.raises(ValueError, match="per-file limit"):
            await manager.execute(job)
