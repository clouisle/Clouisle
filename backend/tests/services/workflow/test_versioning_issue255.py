"""Issue #255 branch coverage for workflow versioning."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow import versioning
from app.services.workflow.versioning import (
    VersionDiff,
    VersionStatus,
    WorkflowVersion,
    WorkflowVersionManager,
)


def make_version(workflow_id=None, **overrides):
    values = {
        "version_id": str(uuid4()),
        "workflow_id": str(workflow_id or uuid4()),
        "version_number": 1,
        "name": "v1.0",
        "description": "test",
        "definition": {"nodes": [], "edges": []},
        "status": VersionStatus.DRAFT,
        "created_by": str(uuid4()),
        "created_at": datetime(2026, 1, 2, 3, 4, 5),
        "content_hash": "supplied-hash",
    }
    values.update(overrides)
    return WorkflowVersion(**values)


@pytest.fixture
def manager():
    WorkflowVersionManager._versions = {}
    return WorkflowVersionManager()


def test_version_models_serialize_all_change_types():
    published_at = datetime(2026, 2, 3, 4, 5, 6)
    workflow_version = make_version(
        status=VersionStatus.PUBLISHED,
        published_at=published_at,
        metadata={"source": "test"},
    )

    serialized = workflow_version.to_dict()

    assert serialized["published_at"] == published_at.isoformat()
    assert serialized["content_hash"] == "supplied-hash"
    assert serialized["metadata"] == {"source": "test"}

    diff = VersionDiff(
        from_version="one",
        to_version="two",
        nodes_added=[{"id": "added"}],
        nodes_removed=[{"id": "removed"}],
        nodes_modified=[{"id": "changed"}],
        edges_added=[{"source": "a", "target": "b"}],
        edges_removed=[{"source": "b", "target": "c"}],
        config_changes={"timeout": {"from": 1, "to": 2}},
    )

    assert diff.get_change_summary() == (
        "+1 nodes, -1 nodes, ~1 nodes modified, +1 edges, -1 edges, 1 config changes"
    )
    assert diff.to_dict()["has_changes"] is True

    with patch.object(versioning, "t", return_value="none") as translate:
        assert VersionDiff("one", "two").get_change_summary("zh") == "none"
        translate.assert_called_once_with("no_changes", lang="zh")


@pytest.mark.asyncio
async def test_rollback_rejects_missing_and_wrong_workflow(manager):
    workflow_id = uuid4()

    with pytest.raises(ValueError, match="version_not_found"):
        await manager.rollback(workflow_id, "missing", uuid4())

    other = make_version()
    manager._versions[other.workflow_id] = [other]
    with pytest.raises(ValueError, match="workflow_not_found"):
        await manager.rollback(workflow_id, other.version_id, uuid4())


@pytest.mark.asyncio
async def test_rollback_archives_latest_and_can_skip_backup(manager):
    workflow_id = uuid4()
    target = make_version(workflow_id)
    current = make_version(workflow_id, version_number=2, name="v2.0")
    manager._versions[str(workflow_id)] = [target, current]
    manager._update_workflow = AsyncMock()

    rolled_back = await manager.rollback(workflow_id, target.version_id, uuid4())

    assert current.status is VersionStatus.ARCHIVED
    assert current.metadata["archived_reason"] == "rollback_backup"
    assert rolled_back.metadata["rollback_from"] == target.version_id
    assert rolled_back.status is VersionStatus.PUBLISHED

    second = await manager.rollback(
        workflow_id, target.version_id, uuid4(), create_backup=False
    )
    assert second.metadata["rollback_from"] == target.version_id


@pytest.mark.asyncio
async def test_diff_and_diff_with_current_missing_version(manager):
    workflow_id = uuid4()
    old = make_version(workflow_id)
    new = make_version(workflow_id, version_number=2)
    old.definition = {
        "nodes": [
            {"id": "removed", "type": "input", "data": {"label": "Old"}},
            {
                "id": "changed",
                "type": "llm",
                "position": {"x": 0},
                "data": {"label": "Before", "removed": True},
            },
            {"id": "same", "type": "output", "data": {}},
        ],
        "edges": [
            {"source": "removed", "target": "changed"},
            {"source": "changed", "sourceHandle": "out", "target": "same"},
        ],
        "timeout": 1,
        "stable": True,
    }
    new.definition = {
        "nodes": [
            {"id": "added", "type": "tool", "data": {"label": "New"}},
            {
                "id": "changed",
                "type": "llm",
                "position": {"x": 1},
                "data": {"label": "After", "added": True},
            },
            {"id": "same", "type": "output", "data": {}},
        ],
        "edges": [
            {"source": "added", "target": "changed"},
            {"source": "changed", "sourceHandle": "out", "target": "same"},
        ],
        "timeout": 2,
        "stable": True,
    }
    manager._versions[str(workflow_id)] = [old, new]

    diff = await manager.diff(old.version_id, new.version_id)

    assert [node["id"] for node in diff.nodes_added] == ["added"]
    assert [node["id"] for node in diff.nodes_removed] == ["removed"]
    assert [node["id"] for node in diff.nodes_modified] == ["changed"]
    assert len(diff.nodes_modified[0]["changes"]) == 4
    assert len(diff.edges_added) == len(diff.edges_removed) == 1
    assert diff.config_changes == {"timeout": {"from": 1, "to": 2}}

    workflow = MagicMock(definition=new.definition)
    query = MagicMock()
    query.first = AsyncMock(return_value=workflow)
    with patch.object(versioning.Workflow, "filter", return_value=query):
        with pytest.raises(ValueError, match="version_not_found"):
            await manager.diff_with_current(workflow_id, "missing")


class AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_update_workflow_handles_present_and_missing_records(manager):
    workflow_id = uuid4()
    workflow = MagicMock()
    workflow.save = AsyncMock()
    query = MagicMock()
    query.first = AsyncMock(side_effect=[workflow, None])

    with (
        patch.object(versioning, "in_transaction", return_value=AsyncContext()),
        patch.object(versioning.Workflow, "filter", return_value=query),
    ):
        await manager._update_workflow(workflow_id, {"nodes": []}, "version-1")
        await manager._update_workflow(workflow_id, {}, "version-2")

    assert workflow.definition == {"nodes": []}
    assert workflow.current_version_id == "version-1"
    workflow.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_fork_supports_explicit_and_latest_version(manager):
    workflow_id = uuid4()
    target_workflow_id = uuid4()
    source = make_version(workflow_id, status=VersionStatus.PUBLISHED)
    manager._versions[str(workflow_id)] = [source]

    explicit = await manager.fork(
        workflow_id, source.version_id, target_workflow_id, uuid4()
    )
    latest = await manager.fork(workflow_id, None, uuid4(), uuid4())

    assert explicit.metadata["forked_from"]["version_id"] == source.version_id
    assert latest.definition == source.definition


@pytest.mark.asyncio
async def test_fork_rejects_missing_source(manager):
    with pytest.raises(ValueError, match="version_not_found"):
        await manager.fork(uuid4(), None, uuid4(), uuid4())


def test_get_version_manager_creates_once():
    with patch.object(versioning, "_version_manager", None):
        first = versioning.get_version_manager()
        assert versioning.get_version_manager() is first
