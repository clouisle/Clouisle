from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.llm.tools.bash import BashSandboxTool
from app.services.sandbox.artifacts import SandboxArtifactStore
from app.services.sandbox.models import (
    SandboxArtifactLimits,
    SandboxArtifactSpec,
    SandboxResult,
    SandboxTaskStatus,
)
from app.services.sandbox.process_launcher import SandboxProcessLauncher
from app.services.sandbox.workspace import SandboxWorkspaceManager


@pytest.mark.asyncio
async def test_cross_host_bash_file_is_collectable(monkeypatch, tmp_path):
    """A caller's physical /private/tmp alias must not become a worker path."""
    from app.llm.tools import bash

    monkeypatch.setattr(settings, "SANDBOX_FILESYSTEM_ISOLATION_ENABLED", True)
    manager = SandboxWorkspaceManager(root=str(tmp_path / "jobs"))
    workspace = manager.prepare("worker-session")
    descriptor = AsyncMock(
        return_value=type(
            "Workspace",
            (),
            {"root": Path("/private/tmp/caller-only/jobs/sessions/worker-session")},
        )()
    )
    monkeypatch.setattr(bash.sandbox_gateway, "get_session_workspace", descriptor)

    async def execute(job, **kwargs):
        # Exercise the command in a real process with the worker's logical mount
        # represented by a temporary directory (Bubblewrap is Linux-only).
        command = [
            value.replace("/workspace", str(workspace.root)) for value in job.command
        ]
        result = await SandboxProcessLauncher(
            filesystem_isolation_enabled=False
        ).launch(command, cwd=str(workspace.root))
        return SandboxResult(
            job_id=job.job_id,
            success=result.exit_code == 0,
            status=SandboxTaskStatus.COMPLETED,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    monkeypatch.setattr(bash.sandbox_gateway, "submit_and_wait", execute)
    result = await BashSandboxTool(session_id="session").execute(
        "printf product-slides > /workspace/introduction.pptx"
    )
    assert result.display_result["success"]
    assert result.display_result["status"] == "completed"
    assert (workspace.root / "introduction.pptx").read_bytes() == b"product-slides"
    store = SandboxArtifactStore(manager)
    uploaded = []

    async def upload(**kwargs):
        uploaded.append(kwargs["content"])
        return {
            "path": "introduction.pptx",
            "url": "/download/introduction.pptx",
            "filename": "introduction.pptx",
        }

    monkeypatch.setattr(store, "_upload_artifact", upload)
    artifacts = await store.collect(
        job_id="collect",
        artifacts=[SandboxArtifactSpec(path="/workspace/introduction.pptx")],
        workspace=workspace,
        artifact_limits=SandboxArtifactLimits(),
    )
    assert uploaded == [b"product-slides"]
    assert artifacts[0].url == "/download/introduction.pptx"
