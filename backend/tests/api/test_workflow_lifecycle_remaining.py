from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import TriggerType, WorkflowStatus, WorkflowVisibility
from app.schemas.response import BusinessError
from app.schemas.workflow import WorkflowUpdate


class _Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    def values_list(self, *args, **kwargs):
        self.calls.append(("values_list", args, kwargs))
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def _workflow(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "Approval flow",
        "description": "Routes approvals",
        "icon": None,
        "definition": {"nodes": [], "edges": []},
        "variables": [],
        "status": WorkflowStatus.DRAFT,
        "visibility": WorkflowVisibility.TEAM,
        "version": 3,
        "trigger_type": TriggerType.MANUAL,
        "trigger_config": {},
        "webhook_token": None,
        "embed_config": {},
        "run_count": 0,
        "success_count": 0,
        "fail_count": 0,
        "created_by_id": uuid4(),
        "created_by": SimpleNamespace(username="creator"),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_list_workflows_applies_team_and_optional_filters():
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    item = _workflow(team_id=team_id)
    query = _Query([item], count=1)
    access = AsyncMock()

    with (
        patch.object(workflows.Workflow, "all", return_value=query),
        patch.object(workflows, "check_team_access", access),
    ):
        response = await workflows.list_workflows(
            team_id=team_id,
            status=WorkflowStatus.DRAFT,
            trigger_type=TriggerType.MANUAL,
            visibility="team",
            keyword="approval",
            own_only=True,
            page=2,
            page_size=5,
            current_user=user,
        )

    access.assert_awaited_once_with(team_id, user)
    assert len([call for call in query.calls if call[0] == "filter"]) == 7
    assert ("offset", (5,), {}) in query.calls
    assert response["data"]["items"][0]["created_by_name"] == "creator"
    assert response["data"]["total"] == 1


@pytest.mark.anyio
async def test_list_workflows_limits_non_superuser_to_memberships():
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    workflow_query = _Query([], count=0)
    membership_query = _Query([uuid4()])

    with (
        patch.object(workflows.Workflow, "all", return_value=workflow_query),
        patch.object(workflows.TeamMember, "filter", return_value=membership_query),
    ):
        response = await workflows.list_workflows(current_user=user)

    assert membership_query.calls == [("values_list", ("team_id",), {"flat": True})]
    assert len([call for call in workflow_query.calls if call[0] == "filter"]) == 1
    assert response["data"]["items"] == []


@pytest.mark.anyio
async def test_get_workflow_returns_accessible_workflow_and_propagates_denial():
    user = SimpleNamespace(id=uuid4())
    item = _workflow()
    access = AsyncMock(return_value=item)

    with patch.object(workflows, "check_workflow_access", access):
        response = await workflows.get_workflow(item.id, user)

    assert response["data"]["id"] == item.id
    access.assert_awaited_once_with(item.id, user)

    denial = BusinessError(msg_key="operation_not_permitted", status_code=403)
    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(side_effect=denial)
        ),
        pytest.raises(BusinessError) as error,
    ):
        await workflows.get_workflow(uuid4(), user)

    assert error.value.status_code == 403


@pytest.mark.anyio
async def test_partial_update_skips_duplicate_lookup_and_definition_version_bump():
    user = SimpleNamespace(id=uuid4())
    item = _workflow()
    reloaded = _workflow(id=item.id, team_id=item.team_id)
    workflow_filter = MagicMock()

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=item)
        ),
        patch.object(workflows.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(workflows.Workflow, "filter", workflow_filter),
        patch.object(workflows.Workflow, "get", return_value=_Query(reloaded)),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit,
    ):
        response = await workflows.update_workflow(
            workflow_id=item.id,
            workflow_in=WorkflowUpdate(description="Only this changed"),
            request=MagicMock(),
            current_user=user,
        )

    workflow_filter.assert_not_called()
    assert item.description == "Only this changed"
    assert item.version == 3
    item.save.assert_awaited_once()
    audit.assert_awaited_once()
    assert response["data"]["id"] == item.id


@pytest.mark.anyio
async def test_unpublish_transitions_and_audits():
    user = SimpleNamespace(id=uuid4())
    item = _workflow(status=WorkflowStatus.PUBLISHED)

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=item)
        ) as access,
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit,
    ):
        response = await workflows.unpublish_workflow(item.id, MagicMock(), user)

    access.assert_awaited_once_with(item.id, user, require_write=True)
    assert item.status == WorkflowStatus.DRAFT
    item.save.assert_awaited_once()
    audit.assert_awaited_once()
    assert response["data"]["status"] == WorkflowStatus.DRAFT


@pytest.mark.anyio
async def test_duplicate_creates_private_draft_and_checks_scope():
    user = SimpleNamespace(id=uuid4())
    source = _workflow(status=WorkflowStatus.PUBLISHED)
    duplicate = _workflow(
        team_id=source.team_id,
        status=WorkflowStatus.DRAFT,
        visibility=WorkflowVisibility.PRIVATE,
    )
    create = AsyncMock(return_value=duplicate)

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=source)
        ),
        patch.object(
            workflows.deps, "check_scoped_permission", new=AsyncMock()
        ) as scoped,
        patch.object(workflows.Workflow, "create", new=create),
        patch.object(workflows.Workflow, "get", return_value=_Query(duplicate)),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()),
        patch.object(workflows, "t", return_value="Approval flow copy"),
    ):
        response = await workflows.duplicate_workflow(source.id, MagicMock(), user)

    scoped.assert_awaited_once_with(user, "workflow:create", "team", source.team_id)
    assert create.await_args.kwargs["status"] == WorkflowStatus.DRAFT
    assert create.await_args.kwargs["visibility"] == WorkflowVisibility.PRIVATE
    assert response["data"]["id"] == duplicate.id


@pytest.mark.anyio
async def test_delete_workflow_deletes_then_audits():
    user = SimpleNamespace(id=uuid4())
    item = _workflow()

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=item)
        ) as access,
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit,
    ):
        response = await workflows.delete_workflow(item.id, MagicMock(), user)

    access.assert_awaited_once_with(item.id, user, require_write=True)
    item.delete.assert_awaited_once()
    audit.assert_awaited_once()
    assert response["data"] == {"id": str(item.id)}
