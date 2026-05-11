import os
import shutil
from pathlib import Path

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxJob, SandboxJobSource, SandboxResult
from app.services.sandbox.workspace import SandboxWorkspaceManager

REAL_RUNTIME_TESTS_ENABLED = os.getenv("RUN_SANDBOX_REAL_RUNTIME_TESTS") == "1"
NODE_RUNTIME_AVAILABLE = (
    shutil.which("node") is not None and shutil.which("npm") is not None
)


class InMemoryResultStore:
    def __init__(self):
        self.results: dict[str, SandboxResult] = {}

    async def update_status(self, job_id, status, *, metadata=None, **updates):
        current = self.results.get(job_id, SandboxResult(job_id=job_id))
        current.status = status
        if metadata is not None:
            current.metadata = metadata
        for key, value in updates.items():
            setattr(current, key, value)
        self.results[job_id] = current
        return current


@pytest.mark.anyio
class TestSandboxRuntimeIntegration:
    @pytest.mark.skipif(
        not REAL_RUNTIME_TESTS_ENABLED,
        reason="Set RUN_SANDBOX_REAL_RUNTIME_TESTS=1 to run real sandbox runtime validation",
    )
    async def test_python_runtime_installs_real_package_for_snippet_and_cli(
        self, tmp_path: Path
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        snippet_job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            language="python",
            code="import pygments\nreturn {'version': pygments.__version__}",
            command=["python"],
            python_packages=["Pygments==2.18.0"],
        )
        snippet_result = await manager.execute(snippet_job)

        assert snippet_result.success is True
        assert snippet_result.result == {"version": "2.18.0"}
        assert snippet_result.metadata.cache_hit_python is False

        cli_job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["pygmentize", "-V"],
            python_packages=["Pygments==2.18.0"],
        )
        cli_result = await manager.execute(cli_job)

        assert cli_result.success is True
        assert "Pygments version" in cli_result.stdout
        assert cli_result.metadata.cache_hit_python is True

    @pytest.mark.skipif(
        not REAL_RUNTIME_TESTS_ENABLED or not NODE_RUNTIME_AVAILABLE,
        reason="Set RUN_SANDBOX_REAL_RUNTIME_TESTS=1 and install node/npm to run real sandbox runtime validation",
    )
    async def test_node_runtime_installs_real_package_for_snippet_and_cli(
        self, tmp_path: Path
    ):
        manager = SandboxManager(
            workspace_manager=SandboxWorkspaceManager(root=str(tmp_path / "jobs")),
            cleanup_workspaces=False,
            result_store=InMemoryResultStore(),
        )

        snippet_job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            language="javascript",
            code="const semver = require('semver'); return { ok: semver.satisfies(params.version, params.range) };",
            command=["javascript"],
            js_packages=["semver@7.5.4"],
            metadata={"params": {"version": "1.2.3", "range": ">=1.0.0"}},
        )
        snippet_result = await manager.execute(snippet_job)

        assert snippet_result.success is True
        assert snippet_result.result == {"ok": True}
        assert snippet_result.metadata.cache_hit_node is False

        cli_job = SandboxJob(
            source=SandboxJobSource.DEBUG,
            command=["semver", "1.2.3", "-r", ">=1.0.0"],
            js_packages=["semver@7.5.4"],
        )
        cli_result = await manager.execute(cli_job)

        assert cli_result.success is True
        assert cli_result.stdout.strip() == "1.2.3"
        assert cli_result.metadata.cache_hit_node is True
