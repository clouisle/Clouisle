"""A nested run must respect the child workflow's access policy."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.models.user import Team, TeamMember, User
from app.models.workflow import Workflow, WorkflowStatus, WorkflowVisibility
from app.services.workflow.executors.subworkflow import SubWorkflowNodeExecutor


@asynccontextmanager
async def _database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        yield
    finally:
        await Tortoise.close_connections()


async def _fixture_workflow(policy, *, owner_role: str = "member"):
    owner = await User.create(
        id=uuid4(),
        username=f"nested_{uuid4().hex[:6]}",
        email=f"nested_{uuid4().hex[:6]}@policy.test",
        hashed_password="x",
    )
    team = await Team.create(id=uuid4(), name=f"nested_{uuid4().hex[:8]}")
    await TeamMember.create(
        id=uuid4(), team_id=team.id, user_id=owner.id, role=owner_role
    )
    workflow = await Workflow.create(
        id=uuid4(),
        team_id=team.id,
        created_by_id=owner.id,
        name=f"child_{uuid4().hex[:6]}",
        visibility=WorkflowVisibility.TEAM,
        status=WorkflowStatus.PUBLISHED,
        definition={"nodes": [], "edges": [], "viewport": {}},
        access_policy=policy,
    )
    return owner, workflow


def _node(workflow_id) -> dict:
    return {"data": {"subWorkflowConfig": {"workflowId": str(workflow_id)}}}


@pytest.mark.asyncio
async def test_child_policy_denial_stops_the_node():
    async with _database():
        owner, workflow = await _fixture_workflow(
            {"operations": {"run": {"decision": "deny"}}}
        )
        parent = SimpleNamespace(
            id=uuid4(),
            depth=0,
            triggered_by_id=owner.id,
            api_key_id=None,
            workflow_id=uuid4(),
            context_snapshot={},
            root_run_id=None,
        )

        result = await SubWorkflowNodeExecutor().execute(
            _node(workflow.id), MagicMock(), parent
        )

        assert result.error == "workflow_access_denied"


@pytest.mark.asyncio
async def test_child_policy_admits_the_matching_role():
    async with _database():
        owner, workflow = await _fixture_workflow(
            {
                "operations": {
                    "run": {
                        "decision": "allow",
                        "gates": [{"kind": "team_role", "roles": ["owner"]}],
                    }
                }
            },
            owner_role="owner",
        )
        parent = SimpleNamespace(
            id=uuid4(),
            depth=0,
            triggered_by_id=owner.id,
            api_key_id=None,
            workflow_id=uuid4(),
            context_snapshot={},
            root_run_id=None,
        )
        run_child = AsyncMock(return_value=uuid4())
        monkey = pytest.MonkeyPatch()
        try:
            from app.services.workflow.orchestrator import WorkflowOrchestrator
            from app.models.workflow import WorkflowRun as WorkflowRunModel

            monkey.setattr(WorkflowOrchestrator, "run", run_child)
            monkey.setattr(
                WorkflowRunModel, "filter", MagicMock(return_value=_Missing())
            )
            await SubWorkflowNodeExecutor().execute(
                _node(workflow.id), MagicMock(), parent
            )
        finally:
            monkey.undo()

        # Past the policy: the executor proceeded to run the child workflow.
        run_child.assert_awaited()


class _Missing:
    """Stand-in for a query that finds no existing child run."""

    async def first(self):
        return None
