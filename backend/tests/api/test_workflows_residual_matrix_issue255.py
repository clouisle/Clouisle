from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus, TriggerType
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, items=None, *, first=None, total=0):
        self.items = items or []
        self.first_value = first
        self.total = total
        self.filters = []

    def all(self):
        return self

    def filter(self, *args, **kwargs):
        self.filters.append(kwargs)
        return self

    def select_related(self, *_args):
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.first_value

    async def values_list(self, *_args, **_kwargs):
        return self.items

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


class Dump:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


def patch_dump(monkeypatch, schema, values):
    monkeypatch.setattr(
        schema,
        "model_validate",
        Mock(side_effect=[Dump(value) for value in values]),
    )


@pytest.mark.anyio
async def test_global_run_list_applies_access_filters_and_serializes_relations(
    monkeypatch,
):
    team_id, workflow_id, user_id = uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(is_superuser=False)
    workflow = SimpleNamespace(id=workflow_id)
    run_with_relations = SimpleNamespace(
        workflow=SimpleNamespace(name="Flow", icon="spark"),
        triggered_by=SimpleNamespace(username="runner"),
    )
    run_without_relations = SimpleNamespace(workflow=None, triggered_by=None)
    workflow_query = Query([workflow])
    run_query = Query([run_with_relations, run_without_relations], total=2)
    access = AsyncMock()

    monkeypatch.setattr(workflows.Workflow, "all", Mock(return_value=workflow_query))
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=run_query))
    monkeypatch.setattr(workflows, "check_team_access", access)
    patch_dump(
        monkeypatch,
        workflows.WorkflowRunListItem,
        [
            {"id": uuid4(), "error_message": None},
            {"id": uuid4(), "error_message": None},
        ],
    )

    response = await workflows.list_all_workflow_runs(
        team_id=[team_id],
        workflow_id=[workflow_id],
        status=[RunStatus.FAILED],
        trigger_type=[TriggerType.WEBHOOK],
        user_id=[user_id],
        is_debug=False,
        search="flow",
        page=2,
        page_size=5,
        current_user=user,
    )

    access.assert_awaited_once_with(team_id, user)
    assert {"team_id__in": [team_id]} in workflow_query.filters
    assert {"workflow_id__in": [workflow_id]} in run_query.filters
    assert {"status__in": [RunStatus.FAILED]} in run_query.filters
    assert {"trigger_type__in": [TriggerType.WEBHOOK]} in run_query.filters
    assert {"triggered_by_id__in": [user_id]} in run_query.filters
    assert {"is_debug": False} in run_query.filters
    assert response["data"]["items"][0]["workflow_name"] == "Flow"
    assert response["data"]["items"][0]["triggered_by_name"] == "runner"
    assert response["data"]["items"][1]["workflow_name"] is None
    assert response["data"]["page"] == 2


@pytest.mark.anyio
async def test_global_run_list_and_stats_return_empty_for_no_accessible_workflows(
    monkeypatch,
):
    user = SimpleNamespace(is_superuser=False)
    memberships = Query([uuid4()])
    monkeypatch.setattr(workflows.TeamMember, "filter", Mock(return_value=memberships))
    monkeypatch.setattr(workflows.Workflow, "all", Mock(return_value=Query([])))
    run_filter = Mock()
    monkeypatch.setattr(workflows.WorkflowRun, "filter", run_filter)

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

    assert listed["data"] == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert stats["data"] == {
        "total_runs": 0,
        "runs_by_status": {},
        "runs_by_workflow": [],
        "avg_duration_ms": 0,
    }
    assert memberships.filters == []
    run_filter.assert_not_called()


@pytest.mark.anyio
async def test_global_run_stats_aggregates_status_workflow_and_duration(monkeypatch):
    first_id, second_id, unknown_id = uuid4(), uuid4(), uuid4()
    first = SimpleNamespace(id=first_id, name="Primary", icon="one")
    second = SimpleNamespace(id=second_id, name="Secondary", icon=None)
    started = datetime(2026, 1, 1, tzinfo=UTC)
    runs = [
        SimpleNamespace(
            status=RunStatus.SUCCESS,
            workflow_id=first_id,
            started_at=started,
            finished_at=started + timedelta(milliseconds=100),
        ),
        SimpleNamespace(
            status=RunStatus.SUCCESS,
            workflow_id=first_id,
            started_at=started,
            finished_at=started + timedelta(milliseconds=300),
        ),
        SimpleNamespace(
            status=RunStatus.FAILED,
            workflow_id=second_id,
            started_at=None,
            finished_at=None,
        ),
        SimpleNamespace(
            status=RunStatus.FAILED,
            workflow_id=unknown_id,
            started_at=None,
            finished_at=None,
        ),
        SimpleNamespace(
            status=RunStatus.PENDING,
            workflow_id=None,
            started_at=None,
            finished_at=None,
        ),
    ]
    monkeypatch.setattr(
        workflows.Workflow, "all", Mock(return_value=Query([first, second]))
    )
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=Query(runs)))

    response = await workflows.get_workflow_run_stats(
        team_id=None, current_user=SimpleNamespace(is_superuser=True)
    )

    assert response["data"]["total_runs"] == 5
    assert response["data"]["runs_by_status"] == {
        "success": 2,
        "failed": 2,
        "pending": 1,
    }
    assert response["data"]["runs_by_workflow"] == [
        {
            "workflow_id": str(first_id),
            "workflow_name": "Primary",
            "workflow_icon": "one",
            "count": 2,
        },
        {
            "workflow_id": str(second_id),
            "workflow_name": "Secondary",
            "workflow_icon": None,
            "count": 1,
        },
    ]
    assert response["data"]["avg_duration_ms"] == 200


@pytest.mark.anyio
async def test_workflow_stats_and_trends_cover_empty_and_timed_runs(monkeypatch):
    workflow_id = uuid4()
    fixed_now = datetime(2026, 2, 7, 12, tzinfo=UTC)
    runs = [
        SimpleNamespace(
            status=RunStatus.SUCCESS,
            created_at=fixed_now - timedelta(hours=2),
            total_duration_ms=100,
        ),
        SimpleNamespace(
            status=RunStatus.FAILED,
            created_at=fixed_now - timedelta(hours=1),
            total_duration_ms=300,
        ),
        SimpleNamespace(
            status=RunStatus.TIMEOUT,
            created_at=fixed_now,
            total_duration_ms=None,
        ),
    ]
    access = AsyncMock()
    run_filter = Mock(side_effect=[Query([]), Query(runs), Query(runs)])
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    monkeypatch.setattr(workflows.WorkflowRun, "filter", run_filter)
    monkeypatch.setattr(workflows, "now", Mock(return_value=fixed_now))

    empty = await workflows.get_workflow_stats(workflow_id, SimpleNamespace())
    stats = await workflows.get_workflow_stats(workflow_id, SimpleNamespace())
    trends = await workflows.get_workflow_trends(workflow_id, "30d", SimpleNamespace())

    assert empty["data"]["last_run_at"] is None
    assert stats["data"] == {
        "total_runs": 3,
        "success_count": 1,
        "failed_count": 1,
        "timeout_count": 1,
        "avg_duration_ms": 200.0,
        "last_run_at": fixed_now.isoformat(),
    }
    assert trends["data"]["period"] == "30d"
    assert len(trends["data"]["data"]) == 30
    assert trends["data"]["data"][-1] == {
        "date": "02/07",
        "runs": 3,
        "success": 1,
        "failed": 1,
        "avgDuration": 200.0,
    }
    assert access.await_count == 3


@pytest.mark.anyio
@pytest.mark.parametrize("run", [None, SimpleNamespace(workflow_id=None)])
async def test_delete_run_rejects_missing_and_orphaned_records(monkeypatch, run):
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "filter",
        Mock(return_value=Query(first=run)),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.delete_workflow_run(
            uuid4(), SimpleNamespace(), SimpleNamespace()
        )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.status_code == 404
    assert exc_info.value.msg_key == (
        "workflow_run_not_found" if run is None else "workflow_not_found"
    )


@pytest.mark.anyio
async def test_version_list_detail_create_and_missing_restore(monkeypatch):
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=uuid4(),
        name="Flow",
        version=4,
        definition={"nodes": []},
        variables=[],
        trigger_type=TriggerType.MANUAL,
        trigger_config={},
    )
    version = SimpleNamespace(id=uuid4())
    version_query = Query([version], total=1)
    access = AsyncMock(return_value=workflow)
    scope = AsyncMock()
    create = AsyncMock(return_value=version)
    audit = AsyncMock()

    monkeypatch.setattr(workflows, "check_workflow_access", access)
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", scope)
    monkeypatch.setattr(
        workflows.WorkflowVersion,
        "filter",
        Mock(side_effect=[version_query, Query(first=None), Query(first=None)]),
    )
    monkeypatch.setattr(workflows.WorkflowVersion, "create", create)
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    patch_dump(monkeypatch, workflows.WorkflowVersionListItem, [{"version": 4}])
    patch_dump(monkeypatch, workflows.WorkflowVersionOut, [{"version": 4}])

    listed = await workflows.list_workflow_versions(workflow_id, current_user=user)
    with pytest.raises(BusinessError) as detail_error:
        await workflows.get_workflow_version(workflow_id, 99, user)
    created = await workflows.create_workflow_version(
        workflow_id,
        SimpleNamespace(description="checkpoint"),
        SimpleNamespace(),
        user,
    )
    with pytest.raises(BusinessError) as restore_error:
        await workflows.restore_workflow_version(
            workflow_id,
            99,
            SimpleNamespace(description=None),
            SimpleNamespace(),
            user,
        )

    assert listed["data"] == {
        "items": [{"version": 4}],
        "total": 1,
        "page": 1,
        "page_size": 20,
    }
    assert detail_error.value.msg_key == "workflow_version_not_found"
    assert restore_error.value.msg_key == "workflow_version_not_found"
    assert created["data"] == {"version": 4}
    assert create.await_args.kwargs["description"] == "checkpoint"
    scope.assert_any_await(user, "workflow:update", "team", workflow.team_id)
    assert audit.await_args.kwargs["action"] == "create_workflow_version"
