"""Recovery race outcomes and audit guarantees for sandbox workspaces.

Recovery is driven by remote worker leases, so these tests pin the exact
sequence of lease/token observations that decide whether a placement is
refreshed, abandoned or reset.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.sandbox import recovery
from app.services.sandbox.models import SandboxBinding, SandboxTaskStatus
from app.services.sandbox.worker_registry import WorkerPresence


def _binding(**overrides) -> SandboxBinding:
    values = {
        "worker_id": "worker-a",
        "instance_id": "instance-a",
        "node_id": "node-a",
        "storage_id": "storage-a",
        "workspace_id": "session",
        "status": "RECOVERING",
        "reset_count": 0,
    }
    values.update(overrides)
    return SandboxBinding(**values)


def _presence(**overrides) -> WorkerPresence:
    values = {
        "worker_id": "worker-a",
        "instance_id": "instance-a",
        "node_id": "node-a",
        "storage_id": "storage-a",
    }
    values.update(overrides)
    return WorkerPresence(**values)


class _Clock:
    """Makes the first local-deadline computation look already expired."""

    def __init__(self, first: float, later: float) -> None:
        self._first = first
        self._later = later
        self.calls = 0

    def time(self) -> float:
        self.calls += 1
        return self._first if self.calls == 1 else self._later


@pytest.mark.asyncio
async def test_prepare_worker_loss_does_not_emit_duplicate_failure_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tasks import sandbox as sandbox_tasks

    monkeypatch.setattr(
        sandbox_tasks,
        "prepare_sandbox_workspace_task",
        SimpleNamespace(apply_async=Mock()),
    )
    results = SimpleNamespace(
        create_queued_result=AsyncMock(),
        get_status=AsyncMock(return_value=SandboxTaskStatus.RUNNING),
        get_result=AsyncMock(
            return_value=SimpleNamespace(status=SandboxTaskStatus.COMPLETED)
        ),
        update_status=AsyncMock(
            return_value=SimpleNamespace(
                status=SandboxTaskStatus.FAILED, error_code="SANDBOX_UNAVAILABLE"
            )
        ),
    )
    audit = AsyncMock()
    monkeypatch.setattr(recovery, "sandbox_result_store", results)
    monkeypatch.setattr(
        recovery,
        "sandbox_worker_registry",
        SimpleNamespace(get=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(recovery, "log_sandbox_task_event", audit)

    prepared = await recovery._prepare(
        "session",
        _binding(),
        "token",
        _presence(),
        "replacement-workspace",
        False,
        time.time() + 5,
    )

    assert prepared is False
    results.update_status.assert_awaited_once()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_cancellation_keeps_existing_terminal_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.tasks import sandbox as sandbox_tasks

    monkeypatch.setattr(
        sandbox_tasks,
        "prepare_sandbox_workspace_task",
        SimpleNamespace(apply_async=Mock()),
    )
    results = SimpleNamespace(
        create_queued_result=AsyncMock(),
        get_status=AsyncMock(return_value=SandboxTaskStatus.RUNNING),
        get_result=AsyncMock(
            return_value=SimpleNamespace(status=SandboxTaskStatus.CANCELLED)
        ),
        update_status=AsyncMock(
            return_value=SimpleNamespace(
                status=SandboxTaskStatus.CANCELLED, error_code=None
            )
        ),
    )
    audit = AsyncMock()
    monkeypatch.setattr(recovery, "sandbox_result_store", results)
    monkeypatch.setattr(
        recovery,
        "sandbox_worker_registry",
        SimpleNamespace(get=AsyncMock(return_value=_presence())),
    )
    monkeypatch.setattr(recovery, "log_sandbox_task_event", audit)
    checks = 0

    async def stop() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(recovery.SandboxGuardLost) as error:
        with recovery.sandbox_execution_scope(stop_requested=stop):
            await recovery._prepare(
                "session",
                _binding(),
                "token",
                _presence(),
                "replacement-workspace",
                False,
                time.time() + 5,
            )

    assert error.value.code == "CANCELLED"
    results.update_status.assert_awaited_once()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_owned_returns_none_when_refreshed_placement_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=False),
        commit_recovery=AsyncMock(),
    )
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[_presence(instance_id="instance-new"), None])
    )
    prepare = AsyncMock(return_value=True)
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", prepare)

    recovered = await recovery._recover_owned(
        "session", _binding(), "token", time.time() + 5, first=False
    )

    assert recovered is None
    prepare.assert_awaited_once()
    sessions.commit_recovery.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_owned_reserve_clock_abandons_local_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(first=990.0, later=997.0)
    monkeypatch.setattr(recovery, "time", SimpleNamespace(time=clock.time))
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=True),
        commit_recovery=AsyncMock(),
        mark_resetting=AsyncMock(return_value=None),
    )
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[_presence(), _presence(instance_id="stale")]),
    )
    prepare = AsyncMock(return_value=True)
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", prepare)

    recovered = await recovery._recover_owned(
        "session", _binding(), "token", 1000.0, first=False
    )

    assert recovered is None


@pytest.mark.asyncio
async def test_recover_owned_skips_failed_prepare_and_retries_next_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _binding()
    candidate_a = _presence(worker_id="worker-a")
    candidate_b = _presence(
        worker_id="worker-b", node_id="node-b", storage_id="storage-b"
    )
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=True),
        commit_recovery=AsyncMock(),
        mark_resetting=AsyncMock(return_value=binding),
    )
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[None, None]),
        list_ready=AsyncMock(return_value=[candidate_a, candidate_b]),
    )
    prepare = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", prepare)
    monkeypatch.setattr(recovery.settings, "SANDBOX_RECOVERY_POLL_SECONDS", 0.001)
    checks = 0

    async def stop() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 5

    with pytest.raises(recovery.SandboxGuardLost) as error:
        with recovery.sandbox_execution_scope(stop_requested=stop):
            await recovery._recover_owned(
                "session", binding, "token", time.time() + 5, first=True
            )

    assert error.value.code == "CANCELLED"
    assert [call.args[3].worker_id for call in prepare.await_args_list] == [
        "worker-a",
        "worker-b",
    ]
    sessions.commit_recovery.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_candidate_returns_none_when_recovery_token_was_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _binding()
    candidate = _presence(worker_id="worker-b", node_id="node-b")
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=False),
        commit_recovery=AsyncMock(),
        mark_resetting=AsyncMock(return_value=binding),
    )
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[None, None]),
        list_ready=AsyncMock(return_value=[candidate]),
    )
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", AsyncMock(return_value=True))

    recovered = await recovery._recover_owned(
        "session", binding, "token", time.time() + 5, first=True
    )

    assert recovered is None
    sessions.commit_recovery.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_candidate_returns_none_when_commit_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _binding()
    candidate = _presence(worker_id="worker-b", node_id="node-b")
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=True),
        commit_recovery=AsyncMock(return_value=False),
        mark_resetting=AsyncMock(return_value=binding),
    )
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[None, candidate]),
        list_ready=AsyncMock(return_value=[candidate]),
    )
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", AsyncMock(return_value=True))

    recovered = await recovery._recover_owned(
        "session", binding, "token", time.time() + 5, first=True
    )

    assert recovered is None
    sessions.commit_recovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_restore_failure_at_local_deadline_abandons_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(first=990.0, later=997.0)
    monkeypatch.setattr(recovery, "time", SimpleNamespace(time=clock.time))
    binding = _binding()
    sessions = SimpleNamespace(mark_resetting=AsyncMock(return_value=None))
    registry = SimpleNamespace(
        get=AsyncMock(side_effect=[_presence(), None]),
    )
    prepare = AsyncMock(return_value=False)
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", prepare)

    recovered = await recovery._recover_owned(
        "session", binding, "token", 1000.0, first=False
    )

    assert recovered is None
    prepare.assert_awaited_once()
    sessions.mark_resetting.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_restore_failure_with_replaced_storage_abandons_placement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock(first=990.0, later=997.0)
    monkeypatch.setattr(recovery, "time", SimpleNamespace(time=clock.time))
    binding = _binding()
    sessions = SimpleNamespace(mark_resetting=AsyncMock(return_value=None))
    registry = SimpleNamespace(
        get=AsyncMock(
            side_effect=[
                _presence(),
                _presence(storage_id="storage-b"),
            ]
        ),
    )
    prepare = AsyncMock(return_value=False)
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", prepare)

    recovered = await recovery._recover_owned(
        "session", binding, "token", 1000.0, first=False
    )

    assert recovered is None
    assert prepare.await_count == 1
    sessions.mark_resetting.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_commit_rejected_by_new_placement_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = _presence()
    sessions = SimpleNamespace(
        recovery_matches=AsyncMock(return_value=True),
        commit_recovery=AsyncMock(return_value=False),
    )
    registry = SimpleNamespace(get=AsyncMock(side_effect=[live, live]))
    monkeypatch.setattr(recovery, "sandbox_session_store", sessions)
    monkeypatch.setattr(recovery, "sandbox_worker_registry", registry)
    monkeypatch.setattr(recovery, "_prepare", AsyncMock(return_value=True))

    recovered = await recovery._recover_owned(
        "session", _binding(), "token", time.time() + 5, first=False
    )

    assert recovered is None
    sessions.commit_recovery.assert_awaited_once()
