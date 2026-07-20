from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import workflows
from app.models.workflow import TriggerType, WorkflowStatus, WorkflowVisibility
from app.schemas.response import BusinessError, ResponseCode, error
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
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
    team_id = uuid4()
    creator_id = uuid4()
    values = {
        "id": uuid4(),
        "team_id": team_id,
        "team": SimpleNamespace(id=team_id, name="Operations"),
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
        "run_count": 7,
        "success_count": 5,
        "fail_count": 2,
        "total_tokens": 123,
        "created_by_id": creator_id,
        "created_by": SimpleNamespace(id=creator_id, username="creator"),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def admin():
    return SimpleNamespace(id=uuid4(), username="admin")


@pytest.fixture
def fake_request():
    return MagicMock()


@pytest.fixture
def admin_workflows_client():
    app = FastAPI()
    app.include_router(workflows.router, prefix="/api/v1/admin/workflows")

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(
                code=exc.code,
                msg=exc.msg,
                msg_key=exc.msg_key,
                data=exc.data,
                **exc.kwargs,
            ),
        )

    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    async def fake_current_user():
        return user

    app.dependency_overrides[deps.get_current_active_user] = fake_current_user
    client = TestClient(app)
    try:
        yield client, user
    finally:
        app.dependency_overrides.clear()


def test_admin_workflows_require_admin_app_permission(admin_workflows_client):
    client, user = admin_workflows_client
    user.roles = [_Role("workflow:read")]

    response = client.get("/api/v1/admin/workflows")

    assert response.status_code == 403
    assert response.json()["code"] == ResponseCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_list_workflows_filters_paginates_and_serializes(admin):
    item = _workflow()
    query = _Query([item], count=1)

    with patch.object(workflows.Workflow, "all", return_value=query):
        response = await workflows.list_workflows(
            page=2,
            page_size=5,
            search="approval",
            status=[WorkflowStatus.DRAFT],
            visibility=[WorkflowVisibility.TEAM],
            trigger_type=[TriggerType.MANUAL],
            team_id=[item.team_id],
            creator=["creator"],
            current_user=admin,
        )

    assert response["data"]["total"] == 1
    assert response["data"]["page"] == 2
    serialized = response["data"]["items"][0]
    assert serialized["team_name"] == "Operations"
    assert serialized["created_by_name"] == "creator"
    assert serialized["total_tokens"] == 123
    assert serialized["version"] == 3
    keyword_filters = [call for call in query.calls if call[0] == "filter"]
    assert len(keyword_filters) == 6
    assert ("offset", (5,), {}) in query.calls
    assert ("limit", (5,), {}) in query.calls


@pytest.mark.anyio
async def test_list_workflows_serializes_deleted_creator_and_missing_team(admin):
    item = _workflow(team=None, created_by=None, created_by_id=None)
    query = _Query([item], count=1)

    with patch.object(workflows.Workflow, "all", return_value=query):
        response = await workflows.list_workflows(
            page=1,
            page_size=20,
            search=None,
            status=None,
            visibility=None,
            trigger_type=None,
            team_id=None,
            creator=None,
            current_user=admin,
        )

    serialized = response["data"]["items"][0]
    assert serialized["team_name"] is None
    assert serialized["created_by_id"] is None
    assert serialized["created_by_name"] is None


@pytest.mark.anyio
async def test_filter_options_are_sorted_and_deduplicated(admin):
    teams = [SimpleNamespace(id=uuid4(), name="Alpha")]
    team_query = _Query(teams)
    creator_query = _Query(["zoe", "amy", "zoe", None])

    with (
        patch.object(workflows.Team, "all", return_value=team_query),
        patch.object(workflows.Workflow, "filter", return_value=creator_query),
    ):
        response = await workflows.get_workflow_filter_options(current_user=admin)

    data = response["data"]
    assert [option["value"] for option in data["statuses"]] == [
        "draft",
        "published",
        "archived",
    ]
    assert data["teams"] == [{"value": str(teams[0].id), "label": "Alpha"}]
    assert data["creators"] == [
        {"value": "amy", "label": "amy"},
        {"value": "zoe", "label": "zoe"},
    ]


@pytest.mark.anyio
async def test_get_workflow_prefetches_detail_and_rejects_missing(admin):
    item = _workflow()
    detail_query = _Query(item)

    with patch.object(workflows.Workflow, "filter", return_value=detail_query):
        response = await workflows.get_workflow(item.id, current_user=admin)

    assert response["data"]["id"] == item.id
    assert ("prefetch_related", ("team", "created_by"), {}) in detail_query.calls

    with (
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        pytest.raises(BusinessError) as exc,
    ):
        await workflows.get_workflow(uuid4(), current_user=admin)

    assert exc.value.status_code == 404
    assert exc.value.msg_key == "workflow_not_found"


@pytest.mark.anyio
async def test_create_workflow_checks_team_and_duplicate_name(fake_request, admin):
    data = WorkflowCreate(team_id=uuid4(), name="Approval flow")

    with (
        patch.object(workflows.Team, "filter", return_value=_Query(None)),
        pytest.raises(BusinessError) as exc,
    ):
        await workflows.create_workflow(fake_request, data, current_user=admin)
    assert exc.value.msg_key == "team_not_found"

    with (
        patch.object(
            workflows.Team,
            "filter",
            return_value=_Query(SimpleNamespace(id=data.team_id, name="Operations")),
        ),
        patch.object(workflows.Workflow, "filter", return_value=_Query(_workflow())),
        pytest.raises(BusinessError) as exc,
    ):
        await workflows.create_workflow(fake_request, data, current_user=admin)
    assert exc.value.code == ResponseCode.DUPLICATE_NAME


@pytest.mark.anyio
async def test_create_workflow_persists_default_definition_and_audits(
    fake_request, admin
):
    team = SimpleNamespace(id=uuid4(), name="Operations")
    data = WorkflowCreate(
        team_id=team.id,
        name="Approval flow",
        description="Routes approvals",
        visibility="team",
    )
    created = _workflow(team_id=team.id, team=team)
    create_mock = AsyncMock(return_value=created)
    audit_mock = AsyncMock()

    with (
        patch.object(workflows.Team, "filter", return_value=_Query(team)),
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        patch.object(workflows.Workflow, "create", create_mock),
        patch.object(workflows.Workflow, "get", return_value=_Query(created)),
        patch.object(workflows.AuditLogService, "log", audit_mock),
        patch.object(workflows, "t", return_value="Start"),
    ):
        response = await workflows.create_workflow(
            fake_request, data, current_user=admin
        )

    persisted = create_mock.await_args.kwargs
    assert persisted["team"] is team
    assert persisted["created_by"] is admin
    assert persisted["visibility"] == WorkflowVisibility.TEAM
    assert persisted["definition"]["nodes"][0]["data"]["label"] == "Start"
    assert response["data"]["team_id"] == team.id
    assert audit_mock.await_args.kwargs["metadata"]["team_id"] == str(team.id)


@pytest.mark.anyio
async def test_create_workflow_propagates_persistence_error(fake_request, admin):
    team = SimpleNamespace(id=uuid4(), name="Operations")
    data = WorkflowCreate(team_id=team.id, name="Approval flow")

    with (
        patch.object(workflows.Team, "filter", return_value=_Query(team)),
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        patch.object(
            workflows.Workflow,
            "create",
            AsyncMock(side_effect=RuntimeError("database unavailable")),
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await workflows.create_workflow(fake_request, data, current_user=admin)


@pytest.mark.anyio
async def test_update_workflow_rejects_duplicate_name(fake_request, admin):
    item = _workflow()

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.Workflow, "filter", return_value=_Query(_workflow())),
        pytest.raises(BusinessError) as exc,
    ):
        await workflows.update_workflow(
            fake_request,
            item.id,
            WorkflowUpdate(name="Existing name"),
            current_user=admin,
        )

    assert exc.value.code == ResponseCode.DUPLICATE_NAME


@pytest.mark.anyio
async def test_update_workflow_applies_fields_increments_version_and_audits(
    fake_request, admin
):
    item = _workflow()
    refreshed = _workflow(id=item.id, team_id=item.team_id, version=4)
    audit_mock = AsyncMock()
    data = WorkflowUpdate(
        name="Updated",
        description="New description",
        icon="bolt",
        definition={"nodes": [{"id": "start"}], "edges": []},
        variables=[{"name": "query"}],
        trigger_type=TriggerType.WEBHOOK,
        trigger_config={"secret": True},
        visibility="public",
        embed_config={"enabled": True},
    )

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        patch.object(workflows.Workflow, "get", return_value=_Query(refreshed)),
        patch.object(workflows.AuditLogService, "log", audit_mock),
    ):
        response = await workflows.update_workflow(
            fake_request, item.id, data, current_user=admin
        )

    assert item.name == "Updated"
    assert item.version == 4
    assert item.visibility == WorkflowVisibility.PUBLIC
    item.save.assert_awaited_once()
    assert response["data"]["version"] == 4
    assert audit_mock.await_args.kwargs["changes"] == {
        "before": {"version": 3},
        "after": {"version": 4},
    }
    assert audit_mock.await_args.kwargs["metadata"]["fields_updated"] == [
        "name",
        "description",
        "icon",
        "definition",
        "variables",
        "trigger_type",
        "trigger_config",
        "visibility",
        "embed_config",
    ]


@pytest.mark.anyio
async def test_update_workflow_does_not_audit_failed_save(fake_request, admin):
    item = _workflow(save=AsyncMock(side_effect=RuntimeError("write failed")))
    audit_mock = AsyncMock()

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.AuditLogService, "log", audit_mock),
        pytest.raises(RuntimeError, match="write failed"),
    ):
        await workflows.update_workflow(
            fake_request,
            item.id,
            WorkflowUpdate(description="Changed"),
            current_user=admin,
        )

    audit_mock.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "initial", "expected", "message"),
    [
        (
            workflows.publish_workflow,
            WorkflowStatus.DRAFT,
            WorkflowStatus.PUBLISHED,
            "workflow_published",
        ),
        (
            workflows.unpublish_workflow,
            WorkflowStatus.PUBLISHED,
            WorkflowStatus.DRAFT,
            "workflow_unpublished",
        ),
    ],
)
async def test_publish_transitions_status_and_audits(
    fake_request, admin, function, initial, expected, message
):
    item = _workflow(status=initial)
    audit_mock = AsyncMock()

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(
            workflows.WorkflowVersion, "filter", return_value=_Query(object())
        ),
        patch.object(workflows.AuditLogService, "log", audit_mock),
    ):
        response = await function(fake_request, item.id, current_user=admin)

    assert item.status == expected
    item.save.assert_awaited_once()
    assert response["msg"]
    assert audit_mock.await_args.kwargs["changes"] == {
        "before": {"status": initial.value},
        "after": {"status": expected.value},
    }


@pytest.mark.anyio
async def test_publish_snapshots_new_version(fake_request, admin):
    item = _workflow()
    create_version = AsyncMock()

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.WorkflowVersion, "filter", return_value=_Query(None)),
        patch.object(workflows.WorkflowVersion, "create", create_version),
        patch.object(workflows.AuditLogService, "log", AsyncMock()),
        patch.object(workflows, "t", return_value="Published snapshot"),
    ):
        await workflows.publish_workflow(fake_request, item.id, current_user=admin)

    assert create_version.await_args.kwargs == {
        "workflow_id": item.id,
        "version": 3,
        "definition": item.definition,
        "variables": item.variables,
        "trigger_type": item.trigger_type,
        "trigger_config": item.trigger_config,
        "description": "Published snapshot",
        "created_by": admin,
    }


@pytest.mark.anyio
async def test_duplicate_workflow_copies_content_as_private_draft(fake_request, admin):
    source = _workflow(status=WorkflowStatus.PUBLISHED)
    duplicate = _workflow(
        team_id=source.team_id,
        status=WorkflowStatus.DRAFT,
        visibility=WorkflowVisibility.PRIVATE,
    )
    create_mock = AsyncMock(return_value=duplicate)

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=source)),
        patch.object(workflows.Workflow, "create", create_mock),
        patch.object(workflows.Workflow, "get", return_value=_Query(duplicate)),
        patch.object(workflows.AuditLogService, "log", AsyncMock()),
        patch.object(workflows, "t", return_value="Approval flow copy"),
    ):
        response = await workflows.duplicate_workflow(
            fake_request, source.id, current_user=admin
        )

    persisted = create_mock.await_args.kwargs
    assert persisted["name"] == "Approval flow copy"
    assert persisted["team_id"] == source.team_id
    assert persisted["definition"] is source.definition
    assert persisted["status"] == WorkflowStatus.DRAFT
    assert persisted["visibility"] == WorkflowVisibility.PRIVATE
    assert response["data"]["id"] == duplicate.id


@pytest.mark.anyio
async def test_delete_workflow_audits_then_deletes(fake_request, admin):
    item = _workflow()
    audit_mock = AsyncMock()

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.AuditLogService, "log", audit_mock),
    ):
        response = await workflows.delete_workflow(
            fake_request, item.id, current_user=admin
        )

    audit_mock.assert_awaited_once()
    item.delete.assert_awaited_once()
    assert response["data"] == {"id": str(item.id)}


@pytest.mark.anyio
async def test_delete_workflow_propagates_delete_error(fake_request, admin):
    item = _workflow(delete=AsyncMock(side_effect=RuntimeError("delete failed")))

    with (
        patch.object(workflows, "_get_workflow", AsyncMock(return_value=item)),
        patch.object(workflows.AuditLogService, "log", AsyncMock()),
        pytest.raises(RuntimeError, match="delete failed"),
    ):
        await workflows.delete_workflow(fake_request, item.id, current_user=admin)
