"""Session state error boundaries in the sandbox manager.

Execution must re-check the session after queueing: a session that expired or
changed owner between submit and workspace preparation is rejected before any
workspace or process work happens.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.sandbox import manager as manager_module
from app.services.sandbox.manager import SandboxManager
from app.services.sandbox.models import SandboxJob, SandboxResult
from app.services.sandbox.workspace import SandboxWorkspaceManager


class _ResultStore:
    """Minimal result store holding snapshots in memory."""

    def __init__(self) -> None:
        self.results: dict[str, SandboxResult] = {}

    async def update_status(self, job_id, status, *, metadata=None, **updates):
        result = self.results.get(job_id) or SandboxResult(job_id=job_id)
        result.status = status
        if metadata is not None:
            result.metadata = metadata
        for key, value in updates.items():
            setattr(result, key, value)
        self.results[job_id] = result
        return result


def _manager(tmp_path: Path) -> SandboxManager:
    return SandboxManager(
        workspace_manager=SandboxWorkspaceManager(root=str(tmp_path)),
        cleanup_workspaces=False,
        result_store=_ResultStore(),
    )


@pytest.mark.asyncio
async def test_execute_revalidates_session_that_expired_during_preparation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    manager = _manager(tmp_path)
    store = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(manager_module, "sandbox_session_store", store)
    job = SandboxJob(command=["python3"])

    with pytest.raises(ValueError, match="not found or expired"):
        await manager._execute(job, session_id="session-1")

    store.get.return_value = SimpleNamespace(
        agent_id="agent-1", team_id="team-1", user_id=None
    )
    with pytest.raises(ValueError, match="not found or expired"):
        await manager._execute(job, session_id="session-1", session_agent_id="agent-2")
    with pytest.raises(ValueError, match="not found or expired"):
        await manager._execute(job, session_id="session-1", session_team_id="team-2")
