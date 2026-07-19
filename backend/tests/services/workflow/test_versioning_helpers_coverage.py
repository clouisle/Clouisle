"""Focused coverage for workflow graph and versioning helpers."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.workflow.errors import CyclicDependencyError, WorkflowValidationError
from app.services.workflow.plan import ExecutionPlan
from app.services.workflow.versioning import (
    VersionStatus,
    WorkflowVersionManager,
)


def test_execution_plan_ignores_malformed_and_canvas_graph_entries():
    plan = ExecutionPlan.from_workflow(
        {
            "nodes": [
                {"id": "start", "data": {"type": "user_input"}},
                {"id": "comment", "data": {"type": "comment"}},
                {"id": "answer", "type": "answer"},
                {"type": "llm"},
            ],
            "edges": [
                {"source": "start", "target": "answer"},
                {"source": "start"},
                {"source": "comment", "target": "answer"},
                {"source": "missing", "target": "answer"},
            ],
        }
    )

    assert plan.get_execution_order() == ["start", "answer"]
    assert plan.get_downstream_nodes("start") == ["answer"]
    assert plan.validate() == []


@pytest.mark.parametrize(
    ("workflow", "error"),
    [
        (
            {"nodes": [{"id": "answer", "type": "answer"}], "edges": []},
            WorkflowValidationError,
        ),
        (
            {
                "nodes": [
                    {"id": "start", "type": "user_input"},
                    {"id": "loop", "type": "llm"},
                ],
                "edges": [
                    {"source": "start", "target": "loop"},
                    {"source": "loop", "target": "start"},
                ],
            },
            CyclicDependencyError,
        ),
    ],
)
def test_execution_plan_rejects_malformed_graphs(workflow, error):
    with pytest.raises(error):
        ExecutionPlan.from_workflow(workflow)


def test_version_diff_normalizes_graph_changes():
    manager = WorkflowVersionManager()

    diff = manager._compute_diff(
        {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "position": {"x": 0},
                    "data": {"label": "Start"},
                },
                {"id": "removed", "type": "llm", "data": {"label": "Old"}},
            ],
            "edges": [{"source": "start", "target": "removed"}],
            "viewport": {"zoom": 1},
        },
        {
            "nodes": [
                {
                    "id": "start",
                    "type": "user_input",
                    "position": {"x": 1},
                    "data": {"label": "Input"},
                },
                {"id": "added", "type": "answer", "data": {"label": "Done"}},
            ],
            "edges": [{"source": "start", "target": "added", "sourceHandle": "output"}],
            "viewport": {"zoom": 2},
        },
        "v1",
        "v2",
    )

    assert diff.nodes_added == [{"id": "added", "type": "answer", "label": "Done"}]
    assert diff.nodes_removed == [{"id": "removed", "type": "llm", "label": "Old"}]
    assert {change["field"] for change in diff.nodes_modified[0]["changes"]} == {
        "position",
        "data.label",
    }
    assert diff.edges_added == [
        {"source": "start", "target": "added", "sourceHandle": "output"}
    ]
    assert diff.edges_removed == [
        {"source": "start", "target": "removed", "sourceHandle": None}
    ]
    assert diff.config_changes == {"viewport": {"from": {"zoom": 1}, "to": {"zoom": 2}}}


@pytest.mark.asyncio
async def test_draft_publish_boundary_updates_persistence_once():
    manager = WorkflowVersionManager()
    manager._versions = {}
    manager._update_workflow = AsyncMock()
    workflow_id = uuid4()
    user_id = uuid4()

    draft = await manager.create_version(workflow_id, {"nodes": []}, user_id)

    assert draft.status is VersionStatus.DRAFT
    assert draft.published_at is None
    manager._update_workflow.assert_not_awaited()

    published = await manager.publish_version(draft.version_id, user_id)

    assert published is draft
    assert published.status is VersionStatus.PUBLISHED
    assert published.published_at is not None
    manager._update_workflow.assert_awaited_once_with(
        workflow_id, {"nodes": []}, draft.version_id
    )

    assert await manager.publish_version(draft.version_id, user_id) is draft
    manager._update_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_version_manager_rejects_missing_version_without_persistence():
    manager = WorkflowVersionManager()
    manager._versions = {}
    manager._update_workflow = AsyncMock()

    with pytest.raises(ValueError, match="version_not_found"):
        await manager.publish_version("missing", uuid4())

    manager._update_workflow.assert_not_awaited()
