from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1 import workflow_versions
from app.api.v1.workflow_versions import (
    CreateVersionRequest,
    ForkRequest,
    RollbackRequest,
)
from app.schemas.response import BusinessError
from app.services.workflow.versioning import VersionStatus


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4(), username="tester")


def make_version(workflow_id, *, version_id="version-1", status=VersionStatus.DRAFT):
    return SimpleNamespace(
        version_id=version_id,
        version_number=1,
        workflow_id=str(workflow_id),
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        to_dict=lambda: {"version_id": version_id},
    )


@pytest.mark.anyio
async def test_version_access_rejects_missing_and_foreign_versions(user):
    workflow_id = uuid4()
    workflow = SimpleNamespace(id=workflow_id, team=SimpleNamespace(id=uuid4()))
    manager = SimpleNamespace(get_version=AsyncMock(return_value=None))

    with (
        patch.object(
            workflow_versions,
            "check_workflow_access",
            new=AsyncMock(return_value=workflow),
        ),
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        pytest.raises(BusinessError) as missing,
    ):
        await workflow_versions.check_version_workflow_access(
            str(workflow_id), "missing", user
        )
    assert missing.value.status_code == 404

    manager.get_version.return_value = make_version(uuid4())
    with (
        patch.object(
            workflow_versions,
            "check_workflow_access",
            new=AsyncMock(return_value=workflow),
        ),
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        pytest.raises(BusinessError) as foreign,
    ):
        await workflow_versions.check_version_workflow_access(
            str(workflow_id), "version-1", user
        )
    assert foreign.value.status_code == 404


@pytest.mark.anyio
async def test_version_create_list_and_get_branches(user):
    workflow_id = uuid4()
    item = make_version(workflow_id)
    manager = SimpleNamespace(
        create_version=AsyncMock(return_value=item),
        get_history=AsyncMock(return_value=[item]),
        get_version=AsyncMock(return_value=item),
    )

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_workflow_access", new=AsyncMock()
        ) as check_workflow,
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ) as check_version,
    ):
        created = await workflow_versions.create_version(
            CreateVersionRequest(
                workflow_id=str(workflow_id),
                nodes=[{"id": "start"}],
                edges=[],
                config={"timeout": 30},
                description=None,
            ),
            user,
        )
        history = await workflow_versions.get_version_history(
            str(workflow_id), user, 5, 1, VersionStatus.DRAFT
        )
        fetched = await workflow_versions.get_version(
            str(workflow_id), "version-1", user
        )

    assert created.version_id == "version-1"
    assert history.total == 1
    assert fetched == {"version_id": "version-1"}
    check_workflow.assert_any_await(workflow_id, user, require_write=True)
    check_workflow.assert_any_await(workflow_id, user)
    check_version.assert_awaited_once_with(str(workflow_id), "version-1", user)
    manager.create_version.assert_awaited_once_with(
        workflow_id=workflow_id,
        definition={"nodes": [{"id": "start"}], "edges": [], "timeout": 30},
        user_id=user.id,
        description="",
    )

    manager.get_version.return_value = None
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError) as error,
    ):
        await workflow_versions.get_version(str(workflow_id), "missing", user)
    assert error.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "method", "status", "access_kwargs"),
    [
        (
            workflow_versions.publish_version,
            "publish_version",
            VersionStatus.PUBLISHED,
            {"required_permission": "workflow:publish"},
        ),
        (
            workflow_versions.archive_version,
            "archive_version",
            VersionStatus.ARCHIVED,
            {"require_write": True},
        ),
    ],
)
async def test_publish_and_archive_success_missing_and_value_error(
    user, endpoint, method, status, access_kwargs
):
    workflow_id = str(uuid4())
    operation = AsyncMock(return_value=make_version(workflow_id, status=status))
    manager = SimpleNamespace(**{method: operation})
    check_access = AsyncMock()

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=check_access
        ),
    ):
        assert await endpoint(workflow_id, "version-1", user) == {
            "success": True,
            "status": status.value,
        }
    check_access.assert_awaited_once_with(
        workflow_id, "version-1", user, **access_kwargs
    )

    operation.return_value = None
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError) as missing,
    ):
        await endpoint(workflow_id, "version-1", user)
    assert missing.value.status_code == 404

    operation.side_effect = ValueError("version_not_found")
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError),
    ):
        await endpoint(workflow_id, "version-1", user)


@pytest.mark.anyio
async def test_diff_success_missing_and_value_error(user):
    workflow_id = str(uuid4())
    diff = SimpleNamespace(to_dict=lambda: {"nodes_added": ["node-2"]})
    manager = SimpleNamespace(diff=AsyncMock(return_value=diff))
    check_access = AsyncMock()

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=check_access
        ),
    ):
        result = await workflow_versions.get_version_diff(
            workflow_id, user, from_version="version-1", to_version="version-2"
        )
    assert result.diff == {"nodes_added": ["node-2"]}
    assert check_access.await_count == 2

    manager.diff.return_value = None
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError) as missing,
    ):
        await workflow_versions.get_version_diff(
            workflow_id, user, from_version="version-1", to_version="version-2"
        )
    assert missing.value.status_code == 404

    manager.diff.side_effect = ValueError("version_not_found")
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError),
    ):
        await workflow_versions.get_version_diff(
            workflow_id, user, from_version="version-1", to_version="version-2"
        )


@pytest.mark.anyio
async def test_rollback_and_fork_success_and_value_errors(user):
    workflow_id = uuid4()
    new_workflow_id = uuid4()
    manager = SimpleNamespace(
        rollback=AsyncMock(
            return_value=make_version(workflow_id, version_id="version-2")
        ),
        fork=AsyncMock(return_value=make_version(new_workflow_id, version_id="fork-1")),
    )
    check_version = AsyncMock()
    check_workflow = AsyncMock()

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=check_version
        ),
        patch.object(workflow_versions, "check_workflow_access", new=check_workflow),
    ):
        rollback = await workflow_versions.rollback_version(
            str(workflow_id),
            RollbackRequest(version_id="version-1", create_backup=False),
            user,
        )
        fork = await workflow_versions.fork_workflow(
            str(workflow_id),
            ForkRequest(version_id="version-1", new_workflow_id=str(new_workflow_id)),
            user,
        )
    assert rollback.new_version_id == "version-2"
    assert rollback.backup_version_id is None
    assert fork.new_version_id == "fork-1"
    check_version.assert_any_await(
        str(workflow_id), "version-1", user, require_write=True
    )
    check_workflow.assert_awaited_once_with(new_workflow_id, user, require_write=True)

    manager.rollback.side_effect = ValueError("workflow_not_found")
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError),
    ):
        await workflow_versions.rollback_version(
            str(workflow_id), RollbackRequest(version_id="version-1"), user
        )

    manager.fork.side_effect = ValueError("version_not_found")
    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        patch.object(workflow_versions, "check_workflow_access", new=AsyncMock()),
        pytest.raises(BusinessError),
    ):
        await workflow_versions.fork_workflow(
            str(workflow_id),
            ForkRequest(version_id="version-1", new_workflow_id=str(new_workflow_id)),
            user,
        )
