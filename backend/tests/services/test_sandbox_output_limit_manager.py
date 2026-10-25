from pathlib import Path

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import (
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
    SandboxTaskStatus,
)
from app.services.sandbox.process_launcher import SandboxOutputLimitError
from app.services.sandbox.workspace import SandboxWorkspaceManager
from tests.services.test_sandbox_manager import InMemoryResultStore


class LimitLauncher:
    async def launch(self, command, **kwargs):
        log_dir = Path(kwargs["log_dir"])
        log_path = log_dir / f"{kwargs['log_stem']}.stdout.log"
        log_path.write_text("partial\n", encoding="utf-8")
        raise SandboxOutputLimitError(8, stream="stdout", log_path=str(log_path))


@pytest.mark.anyio
async def test_output_limit_becomes_failed_result_with_partial_log(tmp_path):
    manager = SandboxManager(
        workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
        cleanup_workspaces=False,
        result_store=InMemoryResultStore(),
        process_launcher=LimitLauncher(),
    )
    job = SandboxJob(
        source=SandboxJobSource.BASH,
        command=["bash", "-c", "yes"],
        shell=True,
        limits=SandboxLimits(timeout_seconds=5, disk_mb=16),
    )

    result = await manager.execute(job)

    assert result.status == SandboxTaskStatus.FAILED
    assert result.success is False
    assert "execution log limit" in (result.error or "")
    assert result.stdout_log == f"logs/exec-{job.job_id}.stdout.log"
    assert result.stdout_log_partial is True
    assert result.stderr_log is None
    assert result.stdout_lines is None


def test_relative_log_path_variants(tmp_path):
    workspace = SandboxWorkspaceManager(root=str(tmp_path / "jobs")).prepare("job")
    log_path = workspace.logs_dir / "exec-1.stdout.log"

    assert SandboxManager._relative_log_path(None, workspace) is None
    assert SandboxManager._relative_log_path(str(log_path), None) == "exec-1.stdout.log"
    assert (
        SandboxManager._relative_log_path(str(log_path), workspace)
        == "logs/exec-1.stdout.log"
    )
    outside = tmp_path / "outside.log"
    assert SandboxManager._relative_log_path(str(outside), workspace) == "outside.log"


class StderrLimitLauncher:
    async def launch(self, command, **kwargs):
        log_dir = Path(kwargs["log_dir"])
        log_path = log_dir / f"{kwargs['log_stem']}.stderr.log"
        log_path.write_text("partial\n", encoding="utf-8")
        raise SandboxOutputLimitError(8, stream="stderr", log_path=str(log_path))


class AnonymousLimitLauncher:
    async def launch(self, command, **kwargs):
        raise SandboxOutputLimitError(8)


def _bash_job():
    return SandboxJob(
        source=SandboxJobSource.BASH,
        command=["bash", "-c", "true"],
        shell=True,
        limits=SandboxLimits(timeout_seconds=5, disk_mb=16),
    )


@pytest.mark.anyio
async def test_output_limit_on_stderr_keeps_stderr_log(tmp_path):
    manager = SandboxManager(
        workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
        cleanup_workspaces=False,
        result_store=InMemoryResultStore(),
        process_launcher=StderrLimitLauncher(),
    )

    result = await manager.execute(_bash_job())

    assert result.status == SandboxTaskStatus.FAILED
    assert result.stderr_log == f"logs/exec-{result.job_id}.stderr.log"
    assert result.stderr_log_partial is True
    assert result.stdout_log is None


@pytest.mark.anyio
async def test_output_limit_without_stream_metadata_still_fails(tmp_path):
    manager = SandboxManager(
        workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
        cleanup_workspaces=False,
        result_store=InMemoryResultStore(),
        process_launcher=AnonymousLimitLauncher(),
    )

    result = await manager.execute(_bash_job())

    assert result.status == SandboxTaskStatus.FAILED
    assert "execution log limit" in (result.error or "")
    assert result.stdout_log is None
    assert result.stderr_log is None
