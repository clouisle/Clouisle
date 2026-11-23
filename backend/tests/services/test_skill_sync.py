"""Skill package delivery into a session workspace.

The packages must reach a worker node through the job payload only, so these
tests assert the job shape and the workspace effects rather than any shared
storage lookup.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from unittest.mock import AsyncMock

from app.models.skill import Skill, SkillCategory
from app.schemas.response import BusinessError
from app.services.sandbox.models import (
    SandboxBinding,
    SandboxJobSource,
    SandboxResult,
    SandboxSkillSyncState,
    SandboxTaskStatus,
)
from app.services.sandbox.skill_sync import (
    SYNC_MARKER_FILENAME,
    WORKSPACE_SKILLS_DIR,
    SkillWorkspaceSync,
)


def make_skill(**overrides: Any) -> Skill:
    files = overrides.pop(
        "files",
        [
            {"path": "SKILL.md", "content": b"# Skill\n"},
            {"path": "scripts/run.py", "content": b"print('hi')\n", "mode": 0o755},
        ],
    )
    data: dict[str, Any] = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "echo-skill",
        "display_name": "Echo Skill",
        "description": "Echo a value",
        "category": SkillCategory.CODE,
        "version": "1.0.0",
        "package_hash": "hash-a",
        "skill_spec": {
            "package_files": [
                {
                    "path": item["path"],
                    "content_base64": base64.b64encode(item["content"]).decode("ascii"),
                    "mode": item.get("mode"),
                }
                for item in files
            ]
        },
        "is_enabled": True,
    }
    data.update(overrides)
    return Skill(**data)


def test_skill_root_uses_workspace_skills_directory():
    skill = make_skill()

    assert SkillWorkspaceSync.skill_root(skill) == "/workspace/skills/echo-skill"


def test_skill_root_falls_back_to_id_for_unsafe_names():
    skill = make_skill(name="...---")

    assert SkillWorkspaceSync.skill_root(skill) == (
        f"/workspace/{WORKSPACE_SKILLS_DIR}/{skill.id}"
    )


def test_skill_files_skips_unsafe_and_malformed_entries():
    encoded = base64.b64encode(b"ok").decode("ascii")
    skill = make_skill(
        skill_spec={
            "package_files": [
                "not-a-dict",
                {"path": 1, "content_base64": encoded},
                {"path": "/absolute", "content_base64": encoded},
                {"path": "../escape", "content_base64": encoded},
                {"path": "valid.txt", "content_base64": encoded, "mode": "644"},
            ]
        }
    )

    files = SkillWorkspaceSync.skill_files(skill)

    assert files == [{"path": "valid.txt", "content_base64": encoded, "mode": None}]
    assert SkillWorkspaceSync.skill_files(make_skill(skill_spec={})) == []


def build_job_for(skill: Skill):
    return SkillWorkspaceSync._build_job(
        [(skill, SkillWorkspaceSync.skill_files(skill))]
    )


def test_sync_job_carries_package_through_input_files():
    skill = make_skill()

    job = build_job_for(skill)

    assert job.source is SandboxJobSource.SKILL
    assert job.cwd == "/workspace"
    assert job.command == []
    assert job.code and ".skill-sync" in job.code
    assert [item.target_path for item in job.input_files] == [
        f"/workspace/.skill-sync/{job.job_id}/0",
        f"/workspace/.skill-sync/{job.job_id}/1",
    ]
    assert job.input_files[1].mode == 0o755
    # The staging plan and the sync marker both target the workspace copy.
    assert f"{WORKSPACE_SKILLS_DIR}/echo-skill/scripts/run.py" in job.code
    assert SYNC_MARKER_FILENAME in job.code
    assert job.metadata["skill_sync"][0]["package_hash"] == "hash-a"


def test_sync_job_bootstrap_only_touches_workspace_paths():
    skill = make_skill()

    code = build_job_for(skill).code or ""

    assert "Skill path escapes workspace" in code
    assert "Skill path contains a symlink" in code
    assert "shutil.rmtree(root / staging_root, ignore_errors=True)" in code
    assert "os.replace" in code


def test_chunking_splits_when_payload_bound_is_hit(monkeypatch):
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.settings.SKILL_SYNC_MAX_TOTAL_BYTES", 100
    )
    small = make_skill(
        name="small-skill",
        files=[{"path": "SKILL.md", "content": b"x" * 10}],
    )
    also_small = make_skill(
        name="other-skill",
        files=[{"path": "SKILL.md", "content": b"y" * 10}],
    )

    chunks = SkillWorkspaceSync._chunk_by_payload(
        [
            (small, SkillWorkspaceSync.skill_files(small)),
            (also_small, SkillWorkspaceSync.skill_files(also_small)),
        ]
    )

    # Base64 of 10 bytes is 16 characters, so both fit inside one 100 byte job.
    assert len(chunks) == 1

    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.settings.SKILL_SYNC_MAX_TOTAL_BYTES", 20
    )
    chunks = SkillWorkspaceSync._chunk_by_payload(
        [
            (small, SkillWorkspaceSync.skill_files(small)),
            (also_small, SkillWorkspaceSync.skill_files(also_small)),
        ]
    )
    assert len(chunks) == 2


def test_chunking_rejects_a_package_larger_than_the_payload_bound(monkeypatch):
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.settings.SKILL_SYNC_MAX_TOTAL_BYTES", 5
    )
    skill = make_skill(files=[{"path": "SKILL.md", "content": b"x" * 64}])

    with pytest.raises(BusinessError) as exc:
        SkillWorkspaceSync._chunk_by_payload(
            [(skill, SkillWorkspaceSync.skill_files(skill))]
        )

    assert exc.value.msg_key == "skill_package_sync_too_large"


def binding_for() -> SandboxBinding:
    return SandboxBinding(
        worker_id="worker-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
        workspace_id="session-1",
        generation=2,
    )


@pytest.mark.anyio
async def test_ensure_skills_skips_already_synced_packages(monkeypatch):
    skill = make_skill()
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=binding_for()),
        get_skill_sync=AsyncMock(
            return_value=SandboxSkillSyncState(
                generation=2, skills={str(skill.id): "hash-a"}
            )
        ),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock()
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id="session-1", skills=[skill]
    )

    assert synced == []
    submit.assert_not_awaited()
    store.set_skill_sync.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_skills_resyncs_after_workspace_generation_changes(monkeypatch):
    skill = make_skill()
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=binding_for()),
        get_skill_sync=AsyncMock(
            return_value=SandboxSkillSyncState(
                generation=1, skills={str(skill.id): "hash-a"}
            )
        ),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock(
        return_value=SandboxResult(
            job_id="job-1",
            success=True,
            status=SandboxTaskStatus.COMPLETED,
            binding=binding_for(),
        )
    )
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id="session-1", skills=[skill]
    )

    assert synced == [str(skill.id)]
    submit.assert_awaited_once()
    _, state = store.set_skill_sync.await_args.args
    assert state.generation == 2
    assert state.skills[str(skill.id)] == "hash-a"


@pytest.mark.anyio
async def test_ensure_skills_raises_when_the_worker_rejects_the_job(monkeypatch):
    skill = make_skill()
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=None),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait",
        AsyncMock(
            return_value=SandboxResult(
                job_id="job-1",
                success=False,
                status=SandboxTaskStatus.FAILED,
                error="Sandbox worker unavailable",
            )
        ),
    )

    with pytest.raises(BusinessError) as exc:
        await SkillWorkspaceSync.ensure_skills(session_id="session-1", skills=[skill])

    assert exc.value.msg_key == "skill_package_sync_failed"
    store.set_skill_sync.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_skills_ignores_disabled_skills(monkeypatch):
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=None),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock()
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    assert (
        await SkillWorkspaceSync.ensure_skills(
            session_id="session-1", skills=[make_skill(is_enabled=False)]
        )
        == []
    )
    submit.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_skills_ignores_skills_without_package_files(monkeypatch):
    store = SimpleNamespace(
        get_binding=AsyncMock(return_value=None),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr("app.services.sandbox.skill_sync.sandbox_session_store", store)
    submit = AsyncMock()
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait", submit
    )

    assert (
        await SkillWorkspaceSync.ensure_skills(
            session_id="session-1", skills=[make_skill(skill_spec={})]
        )
        == []
    )
    submit.assert_not_awaited()


@pytest.mark.anyio
async def test_sync_job_materializes_package_inside_worker_workspace(
    tmp_path, monkeypatch
):
    """End-to-end through the worker manager: files land under skills/<name>."""
    from app.services.sandbox.manager import SandboxManager
    from app.services.sandbox.process_launcher import SandboxProcessLauncher
    from app.services.sandbox.worker_registry import WorkerPresence
    from app.services.sandbox.workspace import SandboxWorkspaceManager

    skill = make_skill()
    session_id = uuid4().hex
    team_id = str(uuid4())
    binding = SandboxBinding(
        worker_id="worker-a",
        instance_id="instance-a",
        node_id="node-a",
        storage_id="storage-a",
        workspace_id=session_id,
    )
    worker = WorkerPresence(
        worker_id=binding.worker_id,
        instance_id=binding.instance_id,
        node_id=binding.node_id,
        storage_id=binding.storage_id,
    )
    manager_store = SimpleNamespace(
        get=AsyncMock(
            return_value=SimpleNamespace(
                agent_id=None,
                team_id=team_id,
                user_id=None,
                conversation_id=None,
                disk_usage_bytes=0,
            )
        ),
        touch=AsyncMock(),
        get_active_round=AsyncMock(return_value=None),
        get_workspace_round=AsyncMock(return_value=None),
        mark_workspace_round=AsyncMock(),
    )
    manager_store.get_binding = AsyncMock(return_value=binding)
    monkeypatch.setattr(
        "app.services.sandbox.manager.sandbox_session_store", manager_store
    )
    monkeypatch.setattr(
        "app.services.sandbox.manager.sandbox_worker_registry",
        SimpleNamespace(get=AsyncMock(return_value=worker)),
    )
    workspace_manager = SandboxWorkspaceManager(root=str(tmp_path / "worker"))
    manager = SandboxManager(
        workspace_manager=workspace_manager,
        process_launcher=SandboxProcessLauncher(filesystem_isolation_enabled=False),
        cleanup_workspaces=False,
        result_store=SimpleNamespace(
            get_result=AsyncMock(return_value=None),
            save_result=AsyncMock(side_effect=lambda result: result),
        ),
    )

    async def run_without_proxy(job, workspace, metadata):
        return await manager._run_job_with_proxy(
            job, workspace, metadata, network_proxy=None
        )

    monkeypatch.setattr(manager, "_run_job", run_without_proxy)

    async def run_on_worker(job, *, session_id, team_id, **kwargs):
        result = await manager.execute(
            job.model_copy(update={"binding": binding}),
            session_id=session_id,
            session_team_id=team_id,
        )
        assert result.success, result.error
        return SandboxResult(
            job_id=job.job_id,
            success=result.success,
            status=SandboxTaskStatus.COMPLETED,
            binding=binding,
        )

    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_gateway.submit_and_wait",
        run_on_worker,
    )
    sync_store = SimpleNamespace(
        get_binding=AsyncMock(return_value=binding),
        get_skill_sync=AsyncMock(return_value=None),
        set_skill_sync=AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.sandbox.skill_sync.sandbox_session_store", sync_store
    )

    synced = await SkillWorkspaceSync.ensure_skills(
        session_id=session_id, skills=[skill], team_id=team_id
    )

    assert synced == [str(skill.id)]
    worker_root = workspace_manager.get_session_root(session_id)
    skill_root = worker_root / "skills" / "echo-skill"
    assert (skill_root / "SKILL.md").read_bytes() == b"# Skill\n"
    run_py = skill_root / "scripts" / "run.py"
    assert run_py.read_bytes() == b"print('hi')\n"
    assert run_py.stat().st_mode & 0o777 == 0o755
    marker = json.loads((skill_root / SYNC_MARKER_FILENAME).read_text())
    assert marker == {
        "skill_id": str(skill.id),
        "name": "echo-skill",
        "package_hash": "hash-a",
        "file_count": 2,
    }
    assert list((worker_root / ".skill-sync").iterdir()) == []

    # A second sync replaces the previous copy instead of failing on existing files.
    skill.skill_spec = {
        "package_files": [
            {
                "path": "SKILL.md",
                "content_base64": base64.b64encode(b"# Skill v2\n").decode("ascii"),
            }
        ]
    }
    skill.package_hash = "hash-b"
    await SkillWorkspaceSync.ensure_skills(
        session_id=session_id, skills=[skill], team_id=team_id
    )
    assert (skill_root / "SKILL.md").read_bytes() == b"# Skill v2\n"
    assert not (skill_root / "scripts").exists()
