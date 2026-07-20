"""Behavior coverage for sandbox integration scaffolds."""

from unittest.mock import AsyncMock

import pytest

from app.services.sandbox.cleanup import cleanup_sandbox_resources
from app.services.sandbox.metrics import record_sandbox_metric
from app.services.sandbox.models import SandboxJob, SandboxJobSource, SandboxSkillSpec
from app.services.sandbox.scheduler import SandboxScheduler
from app.services.sandbox.skills import compile_skill_to_job
from app.services.sandbox.worker import run_sandbox_worker


def test_compile_skill_preserves_execution_configuration():
    skill = SandboxSkillSpec(
        name="document-parser",
        version="1.2.3",
        python_packages=["pypdf"],
        env={"MODE": "safe"},
        metadata={"owner": "team-1"},
    )

    job = compile_skill_to_job(skill, ["python", "parse.py"])

    assert job.source is SandboxJobSource.SKILL
    assert job.command == ["python", "parse.py"]
    assert job.python_packages == ["pypdf"]
    assert job.env == {"MODE": "safe"}
    assert job.metadata == {
        "skill_name": "document-parser",
        "skill_version": "1.2.3",
        "owner": "team-1",
    }


def test_scheduler_accepts_a_valid_job():
    job = SandboxJob(source=SandboxJobSource.TOOL, command=["python", "main.py"])

    assert SandboxScheduler().can_schedule(job) is True


def test_metric_and_cleanup_scaffolds_are_noops():
    assert record_sandbox_metric("jobs.completed", 2) is None


@pytest.mark.asyncio
async def test_cleanup_scaffold_completes():
    assert await cleanup_sandbox_resources() is None


@pytest.mark.asyncio
async def test_worker_runs_one_manager_iteration(monkeypatch):
    run_once = AsyncMock()
    monkeypatch.setattr(
        "app.services.sandbox.worker.SandboxManager.run_once", run_once
    )

    await run_sandbox_worker()

    run_once.assert_awaited_once_with()
