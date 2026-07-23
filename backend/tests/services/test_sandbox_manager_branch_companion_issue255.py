from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import (
    SandboxExecutionMetadata,
    SandboxResult,
    SandboxTaskStatus,
)


def _manager() -> SandboxManager:
    manager = object.__new__(SandboxManager)
    manager.result_store = MagicMock()
    return manager


def test_issue255_sandbox_command_and_runtime_fallback_branches():
    manager = _manager()

    with (
        patch("app.services.sandbox.manager.shutil.which", return_value=None),
        patch("app.services.sandbox.manager.Path.exists", return_value=False),
    ):
        assert manager._resolve_command([], {}) == []
        assert manager._resolve_command(["missing", "arg"], {}) == ["missing", "arg"]
        assert manager._python_executable({}) == "python3"

    assert manager._resolve_command(["/bin/tool", "arg"], {}) == ["/bin/tool", "arg"]


def test_issue255_sandbox_snippet_timeout_and_plain_result_branches():
    manager = _manager()
    script = Path("snippet.py")

    timed_out = manager._parse_snippet_result(
        SimpleNamespace(stdout="partial", stderr="late", timed_out=True, exit_code=1),
        script,
    )
    successful = manager._parse_snippet_result(
        SimpleNamespace(
            stdout="plain output\n", stderr="", timed_out=False, exit_code=0
        ),
        script,
    )

    assert timed_out.success is False
    assert timed_out.stdout == "partial"
    assert successful.success is True
    assert successful.result == "plain output"
    assert successful.error is None


@pytest.mark.anyio
async def test_issue255_sandbox_result_store_compatibility_branches():
    manager = _manager()
    manager.result_store = SimpleNamespace(update_status=AsyncMock())
    result = SandboxResult(
        job_id="job-255",
        status=SandboxTaskStatus.RUNNING,
        metadata=SandboxExecutionMetadata(),
    )

    metadata = await manager._load_or_create_metadata(result.job_id)
    await manager._save_result_snapshot(result)

    assert isinstance(metadata, SandboxExecutionMetadata)
    manager.result_store.update_status.assert_awaited_once_with(
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


@pytest.mark.anyio
async def test_issue255_sandbox_existing_metadata_is_reused():
    existing = SandboxExecutionMetadata()
    manager = _manager()
    manager.result_store = SimpleNamespace(
        get_result=AsyncMock(return_value=SimpleNamespace(metadata=existing))
    )

    assert await manager._load_or_create_metadata("job-255") is existing
