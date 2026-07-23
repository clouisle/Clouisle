from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1 import workflow_versions
from app.api.v1.workflow_versions import (
    CreateTemplateRequest,
    CreateVersionRequest,
    ForkRequest,
    InstantiateTemplateRequest,
    RateTemplateRequest,
    RollbackRequest,
)
from app.schemas.response import BusinessError
from app.services.workflow.templates import TemplateCategory, TemplateVisibility
from app.services.workflow.versioning import VersionStatus


@pytest.fixture
def user():
    return SimpleNamespace(id=uuid4(), username="tester")


def version(workflow_id, *, status=VersionStatus.DRAFT, version_id="version-1"):
    return SimpleNamespace(
        version_id=version_id,
        version_number=1,
        workflow_id=str(workflow_id),
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        to_dict=lambda: {"version_id": version_id},
    )


@pytest.mark.anyio
async def test_version_access_checks_permission_and_workflow_binding(user):
    workflow_id = uuid4()
    team_id = uuid4()
    workflow = SimpleNamespace(id=workflow_id, team=SimpleNamespace(id=team_id))
    manager = SimpleNamespace(get_version=AsyncMock(return_value=version(workflow_id)))

    with (
        patch.object(
            workflow_versions,
            "check_workflow_access",
            new=AsyncMock(return_value=workflow),
        ) as check_access,
        patch.object(
            workflow_versions.deps, "check_scoped_permission", new=AsyncMock()
        ) as check_permission,
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
    ):
        await workflow_versions.check_version_workflow_access(
            str(workflow_id),
            "version-1",
            user,
            required_permission="workflow:publish",
        )

    check_access.assert_awaited_once_with(workflow_id, user, require_write=True)
    check_permission.assert_awaited_once_with(user, "workflow:publish", "team", team_id)

    manager.get_version.return_value = version(uuid4())
    with (
        patch.object(
            workflow_versions,
            "check_workflow_access",
            new=AsyncMock(return_value=workflow),
        ),
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        pytest.raises(BusinessError) as exc_info,
    ):
        await workflow_versions.check_version_workflow_access(
            str(workflow_id), "version-1", user
        )

    assert exc_info.value.status_code == 404


@pytest.mark.anyio
async def test_create_history_and_get_version_happy_paths(user):
    workflow_id = uuid4()
    item = version(workflow_id)
    manager = SimpleNamespace(
        create_version=AsyncMock(return_value=item),
        get_history=AsyncMock(return_value=[item]),
        get_version=AsyncMock(return_value=item),
    )
    check_access = AsyncMock()
    check_version_access = AsyncMock()

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(workflow_versions, "check_workflow_access", new=check_access),
        patch.object(
            workflow_versions,
            "check_version_workflow_access",
            new=check_version_access,
        ),
    ):
        created = await workflow_versions.create_version(
            CreateVersionRequest(
                workflow_id=str(workflow_id),
                nodes=[{"id": "start"}],
                edges=[],
                config={"timeout": 30},
            ),
            user,
        )
        history = await workflow_versions.get_version_history(
            str(workflow_id), user, limit=5, offset=1, status=VersionStatus.DRAFT
        )
        fetched = await workflow_versions.get_version(
            str(workflow_id), "version-1", user
        )

    assert created.version_id == "version-1"
    assert created.created_at == "2026-01-01T00:00:00+00:00"
    manager.create_version.assert_awaited_once_with(
        workflow_id=workflow_id,
        definition={"nodes": [{"id": "start"}], "edges": [], "timeout": 30},
        user_id=user.id,
        description="",
    )
    assert history.total == 1
    assert fetched == {"version_id": "version-1"}
    check_version_access.assert_awaited_once_with(str(workflow_id), "version-1", user)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "manager_method", "expected_status"),
    [
        (workflow_versions.publish_version, "publish_version", VersionStatus.PUBLISHED),
        (workflow_versions.archive_version, "archive_version", VersionStatus.ARCHIVED),
    ],
)
async def test_publish_and_archive_version_lifecycle(
    user, endpoint, manager_method, expected_status
):
    workflow_id = uuid4()
    manager = SimpleNamespace(
        **{
            manager_method: AsyncMock(
                return_value=version(workflow_id, status=expected_status)
            )
        }
    )

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ) as check_access,
    ):
        result = await endpoint(str(workflow_id), "version-1", user)

    assert result == {"success": True, "status": expected_status.value}
    if manager_method == "publish_version":
        check_access.assert_awaited_once_with(
            str(workflow_id),
            "version-1",
            user,
            required_permission="workflow:publish",
        )
    else:
        check_access.assert_awaited_once_with(
            str(workflow_id), "version-1", user, require_write=True
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "manager_method"),
    [
        (workflow_versions.publish_version, "publish_version"),
        (workflow_versions.archive_version, "archive_version"),
    ],
)
async def test_publish_and_archive_translate_invalid_lifecycle(
    user, endpoint, manager_method
):
    manager = SimpleNamespace(
        **{manager_method: AsyncMock(side_effect=ValueError("invalid transition"))}
    )

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError),
    ):
        await endpoint(str(uuid4()), "version-1", user)


@pytest.mark.anyio
async def test_diff_rollback_and_fork_branches(user):
    workflow_id = uuid4()
    new_workflow_id = uuid4()
    diff = SimpleNamespace(to_dict=lambda: {"nodes_added": ["node-2"]})
    manager = SimpleNamespace(
        diff=AsyncMock(return_value=diff),
        rollback=AsyncMock(return_value=version(workflow_id, version_id="version-2")),
        fork=AsyncMock(return_value=version(new_workflow_id, version_id="fork-1")),
    )

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ) as check_version_access,
        patch.object(
            workflow_versions, "check_workflow_access", new=AsyncMock()
        ) as check_access,
    ):
        diff_response = await workflow_versions.get_version_diff(
            str(workflow_id), user, from_version="version-1", to_version="version-2"
        )
        rollback_response = await workflow_versions.rollback_version(
            str(workflow_id), RollbackRequest(version_id="version-1"), user
        )
        fork_response = await workflow_versions.fork_workflow(
            str(workflow_id),
            ForkRequest(version_id="version-1", new_workflow_id=str(new_workflow_id)),
            user,
        )

    assert diff_response.diff == {"nodes_added": ["node-2"]}
    assert rollback_response.new_version_id == "version-2"
    assert rollback_response.backup_version_id is None
    assert fork_response.new_version_id == "fork-1"
    check_version_access.assert_any_await(
        str(workflow_id), "version-1", user, require_write=True
    )
    check_access.assert_awaited_once_with(new_workflow_id, user, require_write=True)


@pytest.mark.anyio
async def test_missing_diff_and_get_version_raise_not_found(user):
    manager = SimpleNamespace(
        get_version=AsyncMock(return_value=None), diff=AsyncMock(return_value=None)
    )

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError) as get_error,
    ):
        await workflow_versions.get_version(str(uuid4()), "missing", user)
    assert get_error.value.status_code == 404

    with (
        patch.object(workflow_versions, "get_version_manager", return_value=manager),
        patch.object(
            workflow_versions, "check_version_workflow_access", new=AsyncMock()
        ),
        pytest.raises(BusinessError) as diff_error,
    ):
        await workflow_versions.get_version_diff(
            str(uuid4()), user, from_version="a", to_version="b"
        )
    assert diff_error.value.status_code == 404


@pytest.mark.anyio
async def test_template_creation_defaults_and_validation_errors(user):
    template = SimpleNamespace(to_dict=lambda: {"id": "template-1"})
    manager = SimpleNamespace(
        create_template=AsyncMock(return_value=template),
        instantiate=AsyncMock(side_effect=ValueError("missing variable")),
        rate_template=AsyncMock(return_value=False),
    )
    request = CreateTemplateRequest(
        name="Demo",
        description="A demo",
        category=TemplateCategory.CUSTOM,
        visibility=TemplateVisibility.PRIVATE,
        nodes=[],
        edges=[],
        variables=[{"name": "topic"}],
    )

    with patch.object(workflow_versions, "get_template_manager", return_value=manager):
        assert await workflow_versions.create_template(request, user) == {
            "id": "template-1"
        }
        with pytest.raises(BusinessError):
            await workflow_versions.instantiate_template(
                "template-1",
                InstantiateTemplateRequest(
                    template_id="template-1", variables={"topic": "tests"}
                ),
                user,
            )
        with pytest.raises(BusinessError):
            await workflow_versions.rate_template(
                "template-1", RateTemplateRequest(rating=4), user
            )

    variable = manager.create_template.await_args.kwargs["variables"][0]
    assert variable.label == "topic"
    assert variable.required is True


@pytest.mark.anyio
async def test_delete_template_enforces_ownership_and_delete_result(user):
    foreign = SimpleNamespace(author_id=str(uuid4()))
    owned = SimpleNamespace(author_id=str(user.id))
    manager = SimpleNamespace(
        get_template=AsyncMock(return_value=foreign),
        delete_template=AsyncMock(return_value=False),
    )

    with patch.object(workflow_versions, "get_template_manager", return_value=manager):
        with pytest.raises(BusinessError) as forbidden:
            await workflow_versions.delete_template("template-1", user)
        assert forbidden.value.status_code == 403

        manager.get_template.return_value = owned
        with pytest.raises(BusinessError):
            await workflow_versions.delete_template("template-1", user)

        manager.delete_template.return_value = True
        assert await workflow_versions.delete_template("template-1", user) == {
            "success": True
        }
