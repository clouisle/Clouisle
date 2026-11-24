"""Skill delivery resilience: workspace replacement and gateway contract."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.skill import Skill, SkillCategory
from app.schemas.response import BusinessError
from app.services.agent_run_worker import _sync_agent_skill_packages
from app.services.sandbox.models import (
    SandboxBinding,
    SandboxResult,
    SandboxSkillSyncState,
    SandboxTaskStatus,
)
from app.services.sandbox.skill_sync import SkillWorkspaceSync


def make_skill(**overrides: Any) -> Skill:
    data: dict[str, Any] = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "echo-skill",
        "display_name": "Echo Skill",
        "category": SkillCategory.CODE,
        "version": "1.0.0",
        "package_hash": "hash-a",
        "skill_spec": {
            "package_files": [
                {
                    "path": "scripts/run.py",
                    "content_base64": base64.b64encode(b"print('hi')\n").decode(
                        "ascii"
                    ),
                    "mode": 0o755,
                }
            ]
        },
    }
    data.update(overrides)
    return Skill(**data)


def binding_for(generation: int) -> SandboxBinding:
    return SandboxBinding(
        worker_id="worker-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
        workspace_id="session-1",
        generation=generation,
    )


def result_for(generation: int) -> SandboxResult:
    return SandboxResult(
        job_id="job-1",
        success=True,
        status=SandboxTaskStatus.COMPLETED,
        binding=binding_for(generation),
    )


def store_for(generation: int) -> SimpleNamespace:
    return SimpleNamespace(
        get_binding=AsyncMock(return_value=binding_for(generation)),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )


@pytest.mark.anyio
async def test_pending_round_rollback_resyncs_all_cached_packages(monkeypatch):
    first = make_skill()
    second = make_skill(name="second")
    store = store_for(2)
    store.get_active_round = AsyncMock(return_value="new-round")
    store.get_workspace_round = AsyncMock(return_value="interrupted-round")
    store.get_skill_sync = AsyncMock(
        return_value=SandboxSkillSyncState(
            generation=2, skills={str(first.id): "hash-a"}
        )
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock(return_value=result_for(2))
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id="session-1", skills=[first, second]
    )

    assert synced == [str(first.id), str(second.id)]
    submit.assert_awaited_once()
    _, state = store.set_skill_sync.await_args.args
    assert state.skills == {str(first.id): "hash-a", str(second.id): "hash-a"}


@pytest.mark.anyio
async def test_generation_change_mid_push_is_not_recorded_and_retries(monkeypatch):
    """A push that lands in a replaced workspace must not mark the Skill synced."""
    skill = make_skill()
    store = store_for(2)
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock(side_effect=[result_for(3), result_for(2)])
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id="session-1", skills=[skill]
    )

    assert synced == [str(skill.id)]
    assert submit.await_count == 2
    # Only the retry that ran in the surviving generation is recorded.
    store.set_skill_sync.assert_awaited_once()
    _, state = store.set_skill_sync.await_args.args
    assert state == SandboxSkillSyncState(
        generation=2, skills={str(skill.id): "hash-a"}
    )


@pytest.mark.anyio
async def test_generation_that_keeps_changing_fails_instead_of_lying(monkeypatch):
    skill = make_skill()
    store = store_for(2)
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait",
        AsyncMock(side_effect=[result_for(3), result_for(4)]),
    )

    with pytest.raises(BusinessError) as exc:
        await SkillWorkspaceSync.ensure_skills(session_id="session-1", skills=[skill])

    assert exc.value.msg_key == "skill_package_sync_failed"
    store.set_skill_sync.assert_not_awaited()


@pytest.mark.anyio
async def test_first_push_without_a_binding_adopts_the_published_generation(
    monkeypatch,
):
    """A brand-new session has no binding yet; that is not a replacement."""
    skill = make_skill()
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=None),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock(return_value=result_for(0))
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id="session-1", skills=[skill]
    )

    assert synced == [str(skill.id)]
    submit.assert_awaited_once()
    _, state = store.set_skill_sync.await_args.args
    assert state.generation == 0


@pytest.mark.anyio
async def test_ensure_skills_forwards_team_and_agent_identity(monkeypatch):
    """The node re-checks session ownership, so identity must ride the job."""
    skill = make_skill()
    store = store_for(2)
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock(return_value=result_for(2))
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    await SkillWorkspaceSync.ensure_skills(
        session_id="session-1",
        skills=[skill],
        team_id="team-1",
        agent_id="agent-1",
    )

    assert submit.await_args.kwargs["session_id"] == "session-1"
    assert submit.await_args.kwargs["team_id"] == "team-1"
    assert submit.await_args.kwargs["agent_id"] == "agent-1"


@pytest.mark.anyio
async def test_agent_run_sync_pushes_skills_with_team_and_agent(monkeypatch):
    """The pre-round sync is real code, not only an ordering mock."""
    from app.services.skill import SkillService

    skill = make_skill()
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    ensure = AsyncMock(return_value=[str(skill.id)])
    monkeypatch.setattr(
        SkillService,
        "get_agent_skills",
        AsyncMock(return_value=[(skill, {})]),
    )
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.SkillWorkspaceSync.ensure_skills",
        ensure,
    )

    await _sync_agent_skill_packages("session-1", agent)

    ensure.assert_awaited_once_with(
        session_id="session-1",
        skills=[skill],
        team_id=str(agent.team_id),
        agent_id=str(agent.id),
    )


@pytest.mark.anyio
async def test_agent_run_sync_skips_work_when_no_skills_are_attached(monkeypatch):
    from app.services.skill import SkillService

    ensure = AsyncMock()
    monkeypatch.setattr(SkillService, "get_agent_skills", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.SkillWorkspaceSync.ensure_skills", ensure
    )

    await _sync_agent_skill_packages(
        "session-1", SimpleNamespace(id=uuid4(), team_id=None)
    )

    ensure.assert_not_awaited()


@pytest.mark.anyio
async def test_agent_run_sync_stays_best_effort_when_delivery_fails(monkeypatch):
    from app.services.skill import SkillService

    skill = make_skill()
    monkeypatch.setattr(
        SkillService,
        "get_agent_skills",
        AsyncMock(return_value=[(skill, {})]),
    )
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.SkillWorkspaceSync.ensure_skills",
        AsyncMock(side_effect=BusinessError(code=5000, msg_key="x")),
    )

    # Must not raise: the Skill tool call re-syncs and reports the failure.
    await _sync_agent_skill_packages(
        "session-1", SimpleNamespace(id=uuid4(), team_id=uuid4())
    )
