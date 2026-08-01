from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, items=(), *, first=None):
        self.items = list(items)
        self.first_value = first
        self.filters = []

    def all(self):
        return self

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def select_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def count(self):
        return len(self.items)

    async def first(self):
        return self.first_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


class AwaitableValue:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def __await__(self):
        async def resolve():
            return self.value

        return resolve().__await__()


class Dump:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


@pytest.mark.anyio
async def test_global_run_queries_cover_superuser_defaults_and_no_completed_runs(
    monkeypatch,
):
    workflow_id = uuid4()
    workflow_query = Query([SimpleNamespace(id=workflow_id, name="Flow", icon=None)])
    run_query = Query(
        [
            SimpleNamespace(
                workflow_id=workflow_id,
                workflow=SimpleNamespace(id=workflow_id, name="Flow", icon=None),
                triggered_by=None,
                status=RunStatus.FAILED,
                started_at=None,
                finished_at=None,
            )
        ]
    )
    monkeypatch.setattr(
        workflows.Workflow, "all", Mock(side_effect=[workflow_query, workflow_query])
    )
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=run_query))
    monkeypatch.setattr(
        workflows.WorkflowRunListItem,
        "model_validate",
        Mock(return_value=Dump({"error_message": None})),
    )

    user = SimpleNamespace(is_superuser=True)
    listed = await workflows.list_all_workflow_runs(
        team_id=None,
        workflow_id=None,
        status=None,
        trigger_type=None,
        user_id=None,
        is_debug=None,
        search=None,
        page=1,
        page_size=20,
        current_user=user,
    )
    stats = await workflows.get_workflow_run_stats(team_id=None, current_user=user)

    assert listed["data"]["total"] == 1
    assert run_query.filters == []
    assert stats["data"]["avg_duration_ms"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize("team_id", [uuid4(), None], ids=["team", "all-teams"])
async def test_list_workflows_superuser_skips_visibility_scopes(monkeypatch, team_id):
    query = Query()
    monkeypatch.setattr(workflows.Workflow, "all", Mock(return_value=query))
    monkeypatch.setattr(workflows, "check_team_access", AsyncMock())

    response = await workflows.list_workflows(
        team_id=team_id,
        current_user=SimpleNamespace(is_superuser=True),
    )

    assert response["data"]["total"] == 0
    assert query.filters == ([{"team_id": team_id}] if team_id else [])


@pytest.mark.anyio
async def test_trends_default_period_has_empty_daily_durations(monkeypatch):
    fixed_now = datetime(2026, 1, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows, "now", Mock(return_value=fixed_now))
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=Query()))

    response = await workflows.get_workflow_trends(
        uuid4(), period="7d", current_user=SimpleNamespace()
    )

    assert len(response["data"]["data"]) == 7
    assert response["data"]["data"][-1]["avgDuration"] == 0


@pytest.mark.anyio
async def test_update_workflow_skips_description_and_updates_icon(monkeypatch):
    workflow_id = uuid4()
    workflow = SimpleNamespace(
        team_id=uuid4(), name="Flow", description="kept", icon=None, save=AsyncMock()
    )
    workflow_in = SimpleNamespace(
        name=None,
        description=None,
        icon="new-icon",
        definition=None,
        variables=None,
        trigger_type=None,
        trigger_config=None,
        visibility=None,
        embed_config=None,
        run_page_config=None,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        workflows.Workflow,
        "get",
        Mock(return_value=AwaitableValue(workflow)),
    )
    monkeypatch.setattr(
        workflows.WorkflowOut,
        "model_validate",
        Mock(return_value=Dump({"id": str(workflow_id)})),
    )

    await workflows.update_workflow(
        workflow_id=workflow_id,
        workflow_in=workflow_in,
        request=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert workflow.description == "kept"
    assert workflow.icon == "new-icon"


@pytest.mark.anyio
async def test_regenerate_webhook_token_mocks_access_and_audit(monkeypatch):
    workflow_id = uuid4()
    workflow = SimpleNamespace(team_id=uuid4(), name="Flow", save=AsyncMock())
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(workflows.secrets, "token_urlsafe", Mock(return_value="token"))
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())

    response = await workflows.regenerate_webhook_token(
        workflow_id, SimpleNamespace(), SimpleNamespace()
    )

    assert response["data"] == {"webhook_token": "token"}
    workflow.save.assert_awaited_once()


@pytest.mark.anyio
async def test_webhook_reraises_api_key_business_error(monkeypatch):
    error = BusinessError(
        code=ResponseCode.UNAUTHORIZED, msg_key="invalid_api_key", status_code=401
    )
    monkeypatch.setattr(
        "app.api.deps._authenticate_api_key", AsyncMock(side_effect=error)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_bad")

    assert exc_info.value is error


@pytest.mark.anyio
async def test_list_workflow_runs_skips_all_optional_filters(monkeypatch):
    query = Query()
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=query))

    response = await workflows.list_workflow_runs(
        uuid4(),
        status=None,
        is_debug=None,
        search=None,
        created_after=None,
        created_before=None,
        page=1,
        page_size=20,
        current_user=SimpleNamespace(),
    )

    assert response["data"]["total"] == 0
    assert query.filters == []


@pytest.mark.anyio
async def test_get_existing_workflow_version(monkeypatch):
    version = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(
        workflows.WorkflowVersion,
        "filter",
        Mock(return_value=Query(first=version)),
    )
    monkeypatch.setattr(
        workflows.WorkflowVersionOut,
        "model_validate",
        Mock(return_value=Dump({"id": str(version.id)})),
    )

    response = await workflows.get_workflow_version(uuid4(), 1, SimpleNamespace())

    assert response["data"] == {"id": str(version.id)}
