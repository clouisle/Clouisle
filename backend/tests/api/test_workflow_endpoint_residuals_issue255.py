from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus, TriggerType, WorkflowStatus
from app.schemas.response import BusinessError


class _Query:
    def __init__(self, rows=(), *, total=None):
        self.rows = list(rows)
        self.total = len(self.rows) if total is None else total
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        return self

    def select_related(self, *args):
        return self

    def prefetch_related(self, *args):
        return self

    def order_by(self, *args):
        return self

    def offset(self, value):
        return self

    def limit(self, value):
        return self

    async def all(self):
        return self.rows

    async def count(self):
        return self.total

    async def first(self):
        return self.rows[0] if self.rows else None

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


class _MembershipQuery:
    async def values_list(self, *args, **kwargs):
        return [uuid4()]


@pytest.mark.anyio
async def test_list_all_workflow_runs_applies_every_residual_filter(monkeypatch):
    workflow_query = _Query([SimpleNamespace(id=uuid4())])
    run_query = _Query()
    user = SimpleNamespace(is_superuser=False)
    workflow_id = uuid4()
    user_id = uuid4()

    monkeypatch.setattr(workflows.Workflow, "all", lambda: workflow_query)
    monkeypatch.setattr(workflows.WorkflowRun, "filter", lambda **kwargs: run_query)
    monkeypatch.setattr(
        workflows.TeamMember, "filter", lambda **kwargs: _MembershipQuery()
    )

    response = await workflows.list_all_workflow_runs(
        team_id=None,
        workflow_id=[workflow_id],
        status=[RunStatus.SUCCESS],
        trigger_type=[TriggerType.MANUAL],
        user_id=[user_id],
        is_debug=False,
        search="needle",
        page=1,
        page_size=20,
        current_user=user,
    )

    assert response["data"]["total"] == 0
    assert workflow_query.filters[-1][1] == {"name__icontains": "needle"}
    assert [call[1] for call in run_query.filters] == [
        {"workflow_id__in": [workflow_id]},
        {"status__in": [RunStatus.SUCCESS]},
        {"trigger_type__in": [TriggerType.MANUAL]},
        {"triggered_by_id__in": [user_id]},
        {"is_debug": False},
    ]


@pytest.mark.anyio
async def test_workflow_run_stats_team_filter_calculates_completed_average(monkeypatch):
    workflow_id = uuid4()
    workflow = SimpleNamespace(id=workflow_id, name="Flow", icon=None)
    workflow_query = _Query([workflow])
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = SimpleNamespace(
        workflow_id=workflow_id,
        status=RunStatus.SUCCESS,
        started_at=started_at,
        finished_at=started_at + timedelta(milliseconds=1500),
    )
    access = AsyncMock()

    monkeypatch.setattr(workflows, "check_team_access", access)
    monkeypatch.setattr(workflows.Workflow, "all", lambda: workflow_query)
    monkeypatch.setattr(workflows.WorkflowRun, "filter", lambda **kwargs: _Query([run]))

    response = await workflows.get_workflow_run_stats(
        team_id=uuid4(), current_user=SimpleNamespace(is_superuser=False)
    )

    access.assert_awaited_once()
    assert workflow_query.filters[-1][1] == {"team_id": access.call_args.args[0]}
    assert response["data"]["avg_duration_ms"] == 1500


@pytest.mark.parametrize(
    "team_id", [uuid4(), None], ids=["specific-team", "memberships"]
)
@pytest.mark.anyio
async def test_list_workflows_applies_non_superuser_visibility_scope(
    monkeypatch, team_id
):
    query = _Query()
    user = SimpleNamespace(is_superuser=False)

    monkeypatch.setattr(workflows.Workflow, "all", lambda: query)
    monkeypatch.setattr(workflows, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        workflows.TeamMember, "filter", lambda **kwargs: _MembershipQuery()
    )

    response = await workflows.list_workflows(
        team_id=team_id,
        status=None,
        trigger_type=None,
        visibility=None,
        keyword=None,
        own_only=False,
        page=1,
        page_size=20,
        current_user=user,
    )

    assert response["data"]["total"] == 0
    assert len(query.filters) == (2 if team_id else 1)


@pytest.mark.anyio
async def test_workflow_trends_uses_thirty_day_period(monkeypatch):
    fixed_now = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)

    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows, "now", lambda: fixed_now)
    monkeypatch.setattr(workflows.WorkflowRun, "filter", lambda **kwargs: _Query())

    response = await workflows.get_workflow_trends(
        workflow_id=uuid4(), period="30d", current_user=SimpleNamespace()
    )

    assert response["data"]["period"] == "30d"
    assert len(response["data"]["data"]) == 30


@pytest.mark.anyio
async def test_update_workflow_changes_description_without_optional_fields(monkeypatch):
    workflow_id = uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=uuid4(),
        name="Flow",
        description="old",
        save=AsyncMock(),
    )
    workflow_in = SimpleNamespace(
        name=None,
        description="new",
        icon=None,
        definition=None,
        variables=None,
        trigger_type=None,
        trigger_config=None,
        visibility=None,
        embed_config=None,
    )
    reloaded = SimpleNamespace()

    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        workflows.Workflow,
        "get",
        lambda **kwargs: _Query([reloaded]),
    )
    monkeypatch.setattr(
        workflows.WorkflowOut,
        "model_validate",
        lambda value: SimpleNamespace(model_dump=lambda: {"id": str(workflow_id)}),
    )

    response = await workflows.update_workflow(
        workflow_id=workflow_id,
        workflow_in=workflow_in,
        request=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert workflow.description == "new"
    workflow.save.assert_awaited_once()
    assert response["data"]["id"] == str(workflow_id)


@pytest.mark.anyio
async def test_webhook_matching_skips_empty_token_before_constant_time_match(
    monkeypatch,
):
    workflow_id = uuid4()
    team_id = uuid4()
    matching = SimpleNamespace(
        id=workflow_id,
        webhook_token="target",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
        team_id=team_id,
    )
    candidates = [SimpleNamespace(webhook_token=None), matching]
    run = SimpleNamespace(id=uuid4())
    user = SimpleNamespace(id=uuid4())
    delay = Mock()

    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **kwargs: _Query(candidates)
    )
    monkeypatch.setattr(workflows.WorkflowRun, "create", AsyncMock(return_value=run))
    monkeypatch.setattr(
        "app.api.deps._authenticate_api_key", AsyncMock(return_value=(user, None))
    )
    monkeypatch.setattr("app.tasks.workflow.run_workflow_task.delay", delay)

    response = await workflows.trigger_workflow_webhook(
        webhook_token="target",
        inputs={"value": 1},
        authorization="Bearer clou_test",
    )

    assert response["data"]["run_id"] == str(run.id)
    delay.assert_called_once()


@pytest.mark.anyio
async def test_list_workflow_runs_applies_status_debug_dates_and_uuid_search(
    monkeypatch,
):
    query = _Query()
    workflow_id = uuid4()
    search_id = uuid4()
    created_after = datetime(2026, 1, 1, tzinfo=timezone.utc)
    created_before = datetime(2026, 2, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowRun, "filter", lambda **kwargs: query)

    response = await workflows.list_workflow_runs(
        workflow_id=workflow_id,
        status=RunStatus.SUCCESS,
        is_debug=False,
        search=f"  {search_id}  ",
        created_after=created_after,
        created_before=created_before,
        page=1,
        page_size=20,
        current_user=SimpleNamespace(),
    )

    assert response["data"]["total"] == 0
    assert [call[1] for call in query.filters] == [
        {"status": RunStatus.SUCCESS},
        {"is_debug": False},
        {"id": search_id},
        {"created_at__gte": created_after},
        {"created_at__lte": created_before},
    ]


@pytest.mark.anyio
async def test_get_workflow_version_raises_for_missing_version(monkeypatch):
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowVersion, "filter", lambda **kwargs: _Query())

    with pytest.raises(BusinessError) as exc_info:
        await workflows.get_workflow_version(
            workflow_id=uuid4(), version=99, current_user=SimpleNamespace()
        )

    assert exc_info.value.msg_key == "workflow_version_not_found"
    assert exc_info.value.status_code == 404
