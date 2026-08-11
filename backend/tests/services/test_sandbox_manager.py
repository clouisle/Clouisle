import base64
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from app.core.config import settings
from app.schemas.response import BusinessError, ResponseCode
from app.services.document_processor import UploadGatewayError

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

    async def update_status(
        self, job_id: str, status: SandboxTaskStatus, *, metadata=None, **updates
    ):
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
                    content_base64=base64.b64encode(b"print('hello sandbox')").decode(
                        "ascii"
                    ),
                ),
            ],
        )

        result = await manager.execute(job)

        assert result.success is True
        assert result.stdout.strip() == "hello sandbox"
        assert result.result == "hello sandbox"

    def test_python_executable_prefers_runtime_python_over_backend_venv(
        self, tmp_path: Path
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        env = {"PATH": "/app/backend/.venv/bin:/usr/local/bin:/usr/bin"}

        from unittest.mock import patch

        with (
            patch(
                "app.services.sandbox.manager.Path",
                side_effect=lambda value: FakePath(
                    value, exists=value == "/usr/local/bin/python3"
                ),
            ),
            patch(
                "app.services.sandbox.manager.shutil.which",
                return_value="/app/backend/.venv/bin/python3",
            ),
        ):
            executable = manager._python_executable(env)

        assert executable == "/usr/local/bin/python3"

    async def test_stages_inline_input_files_and_honors_command_cwd(
        self, tmp_path: Path
    ):
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
            artifacts=[
                SandboxArtifactSpec(path="/workspace/output/missing.txt", optional=True)
            ],
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
        assert python_env_manager.calls == [
            (["requests==2.32.3"], "standard", "https://mirror.example.com/simple")
        ]
        assert len(python_env_manager.workspace_env_calls) == 1

    async def test_injects_workspace_python_env_for_plain_commands(
        self, tmp_path: Path
    ):
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

    def test_workspace_env_repairs_missing_pip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
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
            error=ValueError(
                "Artifact '/workspace/output/big.bin' is 2048 bytes, exceeding per-file limit 1024 bytes"
            )
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

    async def test_execute_rejects_missing_and_wrong_owner_sessions(
        self, tmp_path: Path, monkeypatch
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        get_session = AsyncMock(return_value=None)
        monkeypatch.setattr(
            "app.services.sandbox.manager.sandbox_session_store.get", get_session
        )
        job = SandboxJob(command=["python3"])

        with pytest.raises(ValueError, match="not found or expired"):
            await manager.execute(job, session_id="missing")

        get_session.return_value = SimpleNamespace(agent_id="agent-1", team_id="team-1")
        with pytest.raises(ValueError, match="not found or expired"):
            await manager.execute(
                job, session_id="session-1", session_agent_id="agent-2"
            )
        with pytest.raises(ValueError, match="not found or expired"):
            await manager.execute(job, session_id="session-1", session_team_id="team-2")

    async def test_execute_session_touches_usage_without_cleanup(
        self, tmp_path: Path, monkeypatch
    ):
        launcher = FakeProcessLauncher(stdout="ok")
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            process_launcher=launcher,
            result_store=InMemoryResultStore(),
        )
        store = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(agent_id=None, team_id=None, user_id=None)
            ),
            touch=AsyncMock(),
        )
        cleanup = MagicMock(wraps=workspace_manager.cleanup)
        monkeypatch.setattr("app.services.sandbox.manager.sandbox_session_store", store)
        monkeypatch.setattr(workspace_manager, "cleanup", cleanup)

        result = await manager.execute(
            SandboxJob(command=["python3"]), session_id="session-1"
        )

        assert result.success is True
        store.touch.assert_awaited_once()
        cleanup.assert_not_called()

    async def test_session_artifact_is_registered_without_asset_inputs(
        self, tmp_path: Path, monkeypatch
    ):
        team_id, user_id, artifact_id = uuid4(), uuid4(), uuid4()
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
            process_launcher=FakeProcessLauncher(stdout="ok"),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            artifact_store=artifact_store,
        )
        store = SimpleNamespace(
            get=AsyncMock(
                return_value=SimpleNamespace(
                    agent_id="agent-1",
                    team_id=str(team_id),
                    user_id=str(user_id),
                )
            ),
            touch=AsyncMock(),
        )
        register = AsyncMock(return_value=SimpleNamespace(id=artifact_id))
        monkeypatch.setattr("app.services.sandbox.manager.sandbox_session_store", store)
        monkeypatch.setattr("app.services.asset.asset_service.register", register)

        result = await manager.execute(
            SandboxJob(
                command=["python3"],
                artifacts=[SandboxArtifactSpec(path="/workspace/output/result.txt")],
            ),
            session_id="session-1",
        )

        assert result.artifacts[0].asset_id == artifact_id
        assert register.await_args.kwargs["team_id"] == team_id
        assert register.await_args.kwargs["created_by_id"] == user_id

    async def test_run_job_handles_timeout_and_failed_command(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        metadata = SandboxResult(job_id="job-1").metadata
        launcher = MagicMock()
        launcher.launch = AsyncMock(
            return_value=ProcessLaunchResult(exit_code=1, stderr="boom")
        )
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            process_launcher=launcher,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        failed = await manager._run_job(
            SandboxJob(job_id="job-1", command=["python3"]), workspace, metadata
        )

        assert failed.success is False
        assert failed.error == "boom"

        launcher.launch.return_value = ProcessLaunchResult(exit_code=1, timed_out=True)
        timed_out = await manager._run_job(
            SandboxJob(job_id="job-1", command=["python3"]), workspace, metadata
        )
        assert timed_out.success is False
        assert timed_out.error

    @pytest.mark.anyio
    async def test_stage_input_files_rejects_existing_target(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        target = workspace.root / "input.txt"
        target.write_text("existing", encoding="utf-8")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            command=["python3"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/input.txt",
                    content_base64=base64.b64encode(b"new").decode("ascii"),
                )
            ],
        )

        with pytest.raises(FileExistsError, match="already exists"):
            await manager._stage_input_files(job, workspace)

    @pytest.mark.anyio
    async def test_stage_asset_input_verifies_content_and_cleans_partial(
        self, tmp_path: Path, monkeypatch
    ):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        content = b"asset content"
        asset_id = "c3f74d2b-255d-49bc-8895-89a7f088ea86"
        asset = SimpleNamespace(storage_key="files/input.bin")
        authorize = AsyncMock(return_value=asset)
        read = AsyncMock(return_value=content)
        storage = object()
        monkeypatch.setattr(
            "app.services.asset.asset_service.get_authorized", authorize
        )
        monkeypatch.setattr("app.services.asset.asset_service.read", read)
        monkeypatch.setattr(settings, "UPLOAD_STORAGE_MODE", "local")
        monkeypatch.setattr(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=storage),
        )
        job = SandboxJob(
            command=["python3"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/input/data.bin",
                    asset_id=asset_id,
                    expected_size=len(content),
                    expected_checksum=hashlib.sha256(content).hexdigest(),
                )
            ],
        )

        await manager._stage_input_files(job, workspace)

        assert (workspace.root / "input/data.bin").read_bytes() == content
        assert not (workspace.root / "input/.data.bin.partial").exists()
        authorize.assert_awaited_once_with(
            job.input_files[0].asset_id,
            team_id=None,
            user_id=None,
        )
        read.assert_awaited_once_with(asset, storage=storage)

        mismatch = job.model_copy(
            update={
                "input_files": [
                    job.input_files[0].model_copy(update={"expected_size": 1})
                ]
            }
        )
        (workspace.root / "input/data.bin").unlink()
        with pytest.raises(BusinessError) as exc_info:
            await manager._stage_input_files(mismatch, workspace)
        assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
        assert exc_info.value.msg_key == "sandbox_input_size_mismatch"
        assert not (workspace.root / "input/.data.bin.partial").exists()

    @pytest.mark.anyio
    async def test_stage_asset_input_reads_through_internal_gateway(
        self, tmp_path: Path, monkeypatch
    ):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        content = b"remote asset content"
        checksum = hashlib.sha256(content).hexdigest()
        asset = SimpleNamespace(
            storage_key="files/input.bin", size=len(content), checksum=checksum
        )
        authorize = AsyncMock(return_value=asset)
        monkeypatch.setattr(
            "app.services.asset.asset_service.get_authorized", authorize
        )
        monkeypatch.setattr(settings, "UPLOAD_STORAGE_MODE", "remote")
        monkeypatch.setattr(settings, "API_INTERNAL_BASE_URL", "http://api:8000")
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "gateway-token")
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", "")

        async def aiter_bytes():
            yield b"remote "
            yield b"asset content"

        response = SimpleNamespace(
            status_code=200, raise_for_status=Mock(), aiter_bytes=aiter_bytes
        )

        class StreamContext:
            async def __aenter__(self):
                return response

            async def __aexit__(self, *_args):
                return None

        class Client:
            def __init__(self):
                self.stream = Mock(return_value=StreamContext())

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        client = Client()
        async_client = Mock(return_value=client)
        monkeypatch.setattr(
            "app.services.sandbox.manager.httpx.AsyncClient", async_client
        )
        job = SandboxJob(
            command=["python3"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/input/data.bin",
                    asset_id="c3f74d2b-255d-49bc-8895-89a7f088ea86",
                    expected_size=len(content),
                    expected_checksum=checksum,
                )
            ],
        )

        await manager._stage_input_files(job, workspace)

        assert (workspace.root / "input/data.bin").read_bytes() == content
        async_client.assert_called_once_with(
            base_url="http://api:8000",
            headers={"Authorization": "Bearer gateway-token"},
            timeout=60.0,
        )
        client.stream.assert_called_once_with(
            "GET", "/internal/uploads/read", params={"key": asset.storage_key}
        )
        authorize.assert_awaited_once_with(
            job.input_files[0].asset_id,
            team_id=None,
            user_id=None,
        )

    @pytest.mark.anyio
    async def test_read_asset_gateway_preserves_missing_and_wraps_network_error(
        self, tmp_path: Path, monkeypatch
    ):
        import httpx

        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            result_store=InMemoryResultStore(),
        )
        monkeypatch.setattr(settings, "API_INTERNAL_BASE_URL", "http://api:8000")
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN", "gateway-token")
        monkeypatch.setattr(settings, "INTERNAL_API_TOKEN_FILE", "")

        response = SimpleNamespace(
            status_code=404, raise_for_status=Mock(), aiter_bytes=None
        )

        class StreamContext:
            async def __aenter__(self):
                return response

            async def __aexit__(self, *_args):
                return None

        class Client:
            def stream(self, *_args, **_kwargs):
                return StreamContext()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

        monkeypatch.setattr(
            "app.services.sandbox.manager.httpx.AsyncClient",
            Mock(return_value=Client()),
        )
        with pytest.raises(FileNotFoundError, match="files/missing.bin"):
            await manager._read_asset_from_gateway("files/missing.bin")

        monkeypatch.setattr(
            "app.services.sandbox.manager.httpx.AsyncClient",
            Mock(side_effect=httpx.ConnectError("connection reset")),
        )
        with pytest.raises(UploadGatewayError, match="api gateway"):
            await manager._read_asset_from_gateway("files/missing.bin")

    def test_parse_snippet_result_handles_timeout_and_plain_output(
        self, tmp_path: Path
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        script = tmp_path / "snippet.py"

        timed_out = manager._parse_snippet_result(
            ProcessLaunchResult(exit_code=1, stdout="partial", timed_out=True), script
        )
        plain = manager._parse_snippet_result(
            ProcessLaunchResult(exit_code=0, stdout="value\n"), script
        )

        assert timed_out.success is False
        assert timed_out.error
        assert plain.success is True
        assert plain.result == "value"

    def test_link_node_modules_guards_and_links(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        manager._link_node_modules_into_workspace(workspace, {})
        manager._link_node_modules_into_workspace(
            workspace, {"NODE_PATH": str(tmp_path / "missing")}
        )
        source = tmp_path / "modules"
        source.mkdir()
        manager._link_node_modules_into_workspace(workspace, {"NODE_PATH": str(source)})
        manager._link_node_modules_into_workspace(workspace, {"NODE_PATH": str(source)})

        assert (workspace.root / "node_modules").is_symlink()

    def test_command_and_python_resolution_fallbacks(self, tmp_path: Path, monkeypatch):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        monkeypatch.setattr(
            "app.services.sandbox.manager.shutil.which", lambda *a, **k: None
        )
        monkeypatch.setattr(
            "app.services.sandbox.manager.Path.exists", lambda self: False
        )

        assert manager._resolve_command([], {}) == []
        assert manager._resolve_command(["/bin/python3"], {}) == ["/bin/python3"]
        assert manager._resolve_command(["missing"], {}) == ["missing"]
        assert manager._python_executable({"PATH": "/bin"}) == "python3"

    async def test_metadata_and_snapshot_store_fallbacks(self, tmp_path: Path):
        store = SimpleNamespace(update_status=AsyncMock())
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=store,
        )

        metadata = await manager._load_or_create_metadata("job-1")
        result = SandboxResult(job_id="job-1")
        await manager._save_result_snapshot(result)

        assert metadata.started_at is None
        store.update_status.assert_awaited_once()
        assert await manager.run_once() is None

    async def test_stage_input_file_applies_mode(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        job = SandboxJob(
            command=["python3"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/input/data.bin",
                    content_base64=base64.b64encode(b"asset content").decode(),
                    mode=0o755,
                )
            ],
        )

        await manager._stage_input_files(job, workspace)

        assert (workspace.root / "input/data.bin").stat().st_mode & 0o777 == 0o755

    async def test_stage_input_file_rejects_checksum_mismatch(self, tmp_path: Path):
        workspace_manager = SandboxWorkspaceManager(root=str(tmp_path))
        workspace = workspace_manager.prepare("job-1")
        manager = SandboxManager(
            workspace_manager=workspace_manager,
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        content = b"asset content"
        job = SandboxJob(
            command=["python3"],
            input_files=[
                SandboxInputFileSpec(
                    target_path="/workspace/input/data.bin",
                    content_base64=base64.b64encode(content).decode(),
                    expected_checksum="0" * 64,
                )
            ],
        )

        with pytest.raises(BusinessError) as exc_info:
            await manager._stage_input_files(job, workspace)

        assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
        assert exc_info.value.msg_key == "sandbox_input_checksum_mismatch"

    def test_python_executable_resolves_plain_which(self, tmp_path: Path, monkeypatch):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )
        monkeypatch.setattr(
            "app.services.sandbox.manager.shutil.which",
            lambda *a, **k: "/usr/bin/python3",
        )
        monkeypatch.setattr(
            "app.services.sandbox.manager.Path.exists", lambda self: False
        )

        assert manager._python_executable({"PATH": "/usr/bin"}) == "/usr/bin/python3"

    def test_inject_default_node_runtime_prepends_path(self, tmp_path: Path):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
            node_env_manager=SimpleNamespace(node_binary=lambda: "/usr/bin/node"),
        )
        env = {"PATH": "/usr/local/bin"}

        manager._inject_default_node_runtime(env)
        manager._inject_default_node_runtime(empty_env := {})

        assert env["PATH"] == "/usr/bin:/usr/local/bin"
        assert empty_env["PATH"] == "/usr/bin"
        assert env["SANDBOX_NODE_BINARY"] == "/usr/bin/node"

    def test_artifact_storage_key_requires_marker(self):
        manager = SandboxManager(
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        assert manager._artifact_storage_key("https://example.com/files/x.png") is None
        assert (
            manager._artifact_storage_key("/api/v1/upload/files/images/2026/05/out.png")
            == "images/2026/05/out.png"
        )

    async def test_save_result_snapshot_uses_save_result(self, tmp_path: Path):
        save_result = AsyncMock()
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
            cleanup_workspaces=False,
            result_store=SimpleNamespace(save_result=save_result),
        )

        await manager._save_result_snapshot(SandboxResult(job_id="job-1"))

        save_result.assert_awaited_once()
