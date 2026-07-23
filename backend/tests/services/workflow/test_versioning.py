"""Behavioral tests for workflow version management."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow.versioning import (
    VersionStatus,
    WorkflowVersionManager,
)


@pytest.fixture
def manager():
    manager = WorkflowVersionManager()
    manager._versions = {}
    return manager


@pytest.mark.asyncio
async def test_create_version_builds_history_and_publishes_when_requested(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    definition = {"nodes": [], "edges": []}
    manager._update_workflow = AsyncMock()

    first = await manager.create_version(workflow_id, definition, user_id)
    second = await manager.create_version(
        workflow_id,
        definition,
        user_id,
        name="release",
        auto_publish=True,
    )

    assert (first.version_number, first.name, first.parent_version_id) == (
        1,
        "v1.0",
        None,
    )
    assert (second.version_number, second.name, second.parent_version_id) == (
        2,
        "release",
        first.version_id,
    )
    assert second.status is VersionStatus.PUBLISHED
    assert second.published_at is not None
    manager._update_workflow.assert_awaited_once_with(
        workflow_id, definition, second.version_id
    )


@pytest.mark.asyncio
async def test_history_filters_orders_and_paginates(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    first = await manager.create_version(workflow_id, {}, user_id)
    second = await manager.create_version(workflow_id, {}, user_id)
    third = await manager.create_version(workflow_id, {}, user_id)
    second.status = VersionStatus.PUBLISHED
    third.status = VersionStatus.PUBLISHED

    assert await manager.get_history(workflow_id, limit=1, offset=1) == [second]
    assert await manager.get_history(workflow_id, status=VersionStatus.PUBLISHED) == [
        third,
        second,
    ]
    assert await manager.get_history(uuid4()) == []
    assert await manager.get_version(first.version_id) is first
    assert await manager.get_version("missing") is None


@pytest.mark.asyncio
async def test_latest_version_honors_published_only(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    manager._update_workflow = AsyncMock()
    published = await manager.create_version(
        workflow_id, {}, user_id, auto_publish=True
    )
    draft = await manager.create_version(workflow_id, {}, user_id)

    assert await manager.get_latest_version(workflow_id) is draft
    assert (
        await manager.get_latest_version(workflow_id, published_only=True) is published
    )
    assert await manager.get_latest_version(uuid4()) is None


@pytest.mark.asyncio
async def test_publish_is_idempotent_and_missing_version_errors(manager):
    workflow_id = uuid4()
    version = await manager.create_version(workflow_id, {"nodes": []}, uuid4())
    manager._update_workflow = AsyncMock()

    assert await manager.publish_version(version.version_id, uuid4()) is version
    first_published_at = version.published_at
    assert await manager.publish_version(version.version_id, uuid4()) is version

    assert version.status is VersionStatus.PUBLISHED
    assert version.published_at is first_published_at
    manager._update_workflow.assert_awaited_once_with(
        workflow_id, version.definition, version.version_id
    )
    with pytest.raises(ValueError, match="version_not_found"):
        await manager.publish_version("missing", uuid4())


@pytest.mark.asyncio
async def test_archive_updates_status_and_rejects_missing_version(manager):
    version = await manager.create_version(uuid4(), {}, uuid4())

    assert await manager.archive_version(version.version_id) is version
    assert version.status is VersionStatus.ARCHIVED
    with pytest.raises(ValueError, match="version_not_found"):
        await manager.archive_version("missing")


@pytest.mark.asyncio
async def test_rollback_archives_latest_and_publishes_copy(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    target = await manager.create_version(
        workflow_id, {"nodes": [{"id": "target"}]}, user_id, name="target"
    )
    latest = await manager.create_version(workflow_id, {"nodes": []}, user_id)
    manager._update_workflow = AsyncMock()

    rolled_back = await manager.rollback(workflow_id, target.version_id, user_id)

    assert latest.status is VersionStatus.ARCHIVED
    assert latest.metadata["archived_reason"] == "rollback_backup"
    assert rolled_back.definition == target.definition
    assert rolled_back.status is VersionStatus.PUBLISHED
    assert rolled_back.metadata["rollback_from"] == target.version_id
    manager._update_workflow.assert_awaited_once()


@pytest.mark.asyncio
async def test_rollback_rejects_version_from_another_workflow(manager):
    version = await manager.create_version(uuid4(), {}, uuid4())

    with pytest.raises(ValueError, match="workflow_not_found"):
        await manager.rollback(uuid4(), version.version_id, uuid4())


@pytest.mark.asyncio
async def test_diff_reports_node_edge_and_config_changes(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    before = await manager.create_version(
        workflow_id,
        {
            "nodes": [
                {
                    "id": "changed",
                    "type": "llm",
                    "position": {"x": 0},
                    "data": {"label": "Old", "model": "a"},
                },
                {"id": "removed", "type": "answer", "data": {}},
            ],
            "edges": [{"source": "changed", "target": "removed"}],
            "viewport": {"x": 0},
        },
        user_id,
    )
    after = await manager.create_version(
        workflow_id,
        {
            "nodes": [
                {
                    "id": "changed",
                    "type": "llm",
                    "position": {"x": 1},
                    "data": {"label": "New", "model": "a"},
                },
                {"id": "added", "type": "answer", "data": {"label": "Done"}},
            ],
            "edges": [{"source": "changed", "target": "added"}],
            "viewport": {"x": 1},
        },
        user_id,
    )

    diff = await manager.diff(before.version_id, after.version_id)

    assert diff.has_changes is True
    assert diff.nodes_added == [{"id": "added", "type": "answer", "label": "Done"}]
    assert diff.nodes_removed == [{"id": "removed", "type": "answer", "label": ""}]
    assert diff.nodes_modified == [
        {
            "id": "changed",
            "type": "llm",
            "changes": [
                {"field": "position", "type": "moved"},
                {"field": "data.label", "from": "Old", "to": "New"},
            ],
        }
    ]
    assert diff.edges_added == [
        {"source": "changed", "target": "added", "sourceHandle": None}
    ]
    assert diff.edges_removed == [
        {"source": "changed", "target": "removed", "sourceHandle": None}
    ]
    assert diff.config_changes == {"viewport": {"from": {"x": 0}, "to": {"x": 1}}}


@pytest.mark.asyncio
async def test_diff_handles_identical_empty_definitions_and_missing_versions(manager):
    version = await manager.create_version(uuid4(), {}, uuid4())

    diff = await manager.diff(version.version_id, version.version_id)

    assert diff.has_changes is False
    assert diff.change_summary == "No changes"
    with pytest.raises(ValueError, match="version_not_found"):
        await manager.diff(version.version_id, "missing")


@pytest.mark.asyncio
async def test_diff_with_current_uses_mocked_workflow_persistence(manager):
    workflow_id = uuid4()
    version = await manager.create_version(
        workflow_id, {"nodes": [], "edges": []}, uuid4()
    )
    workflow = MagicMock(definition={"nodes": [{"id": "new"}], "edges": []})

    with patch("app.services.workflow.versioning.Workflow") as workflow_model:
        workflow_model.filter.return_value.first = AsyncMock(return_value=workflow)
        diff = await manager.diff_with_current(workflow_id, version.version_id)

    assert diff.to_version == "current"
    assert diff.nodes_added == [{"id": "new", "type": None, "label": ""}]

    with patch("app.services.workflow.versioning.Workflow") as workflow_model:
        workflow_model.filter.return_value.first = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="workflow_not_found"):
            await manager.diff_with_current(workflow_id, version.version_id)


@pytest.mark.asyncio
async def test_fork_uses_latest_published_version_and_records_origin(manager):
    source_id = uuid4()
    target_id = uuid4()
    user_id = uuid4()
    manager._update_workflow = AsyncMock()
    published = await manager.create_version(
        source_id, {"nodes": [{"id": "source"}]}, user_id, auto_publish=True
    )
    await manager.create_version(source_id, {"nodes": []}, user_id)

    forked = await manager.fork(source_id, None, target_id, user_id)

    assert forked.definition == published.definition
    assert forked.status is VersionStatus.DRAFT
    assert forked.metadata["forked_from"] == {
        "workflow_id": str(source_id),
        "version_id": published.version_id,
    }
    with pytest.raises(ValueError, match="version_not_found"):
        await manager.fork(uuid4(), None, uuid4(), user_id)


@pytest.mark.asyncio
async def test_stats_cover_empty_and_mixed_history(manager):
    workflow_id = uuid4()
    user_id = uuid4()
    empty = await manager.get_stats(workflow_id)
    assert empty["total_versions"] == 0
    assert empty["first_version_date"] is None
    assert empty["latest_version_date"] is None

    draft = await manager.create_version(workflow_id, {}, user_id)
    published = await manager.create_version(workflow_id, {}, user_id)
    published.status = VersionStatus.PUBLISHED
    archived = await manager.create_version(workflow_id, {}, user_id)
    archived.status = VersionStatus.ARCHIVED

    stats = await manager.get_stats(workflow_id)
    assert stats["total_versions"] == 3
    assert stats["draft_versions"] == 1
    assert stats["published_versions"] == 1
    assert stats["archived_versions"] == 1
    assert stats["first_version_date"] == draft.created_at
    assert stats["latest_version_date"] == archived.created_at
