from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from tortoise.expressions import Q

from app.api import workflow_access
from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus, TriggerType, WorkflowVisibility
from app.schemas.response import BusinessError, ResponseCode


def _flatten(node) -> list[dict]:
    """Collect the leaf filter kwargs of a (possibly nested) Q tree."""
    if not node.children:
        return [dict(node.filters)]
    leaves: list[dict] = []
    for child in node.children:
        leaves.extend(_flatten(child))
    return leaves


class Query:
    def __init__(self, items=None, *, first=None, total=0):
        self.items = items or []
        self.first_value = first
        self.total = total
        self.filters = []

    def all(self):
        return self

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
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
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
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
    monkeypatch.setattr(
        workflow_access.TeamMember, "filter", Mock(return_value=Query([uuid4()]))
    )
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
    assert ((), {"team_id__in": [team_id]}) in workflow_query.filters
    assert ((), {"workflow_id__in": [workflow_id]}) in run_query.filters
    assert ((), {"status__in": [RunStatus.FAILED]}) in run_query.filters
    assert ((), {"trigger_type__in": [TriggerType.WEBHOOK]}) in run_query.filters
    assert ((), {"triggered_by_id__in": [user_id]}) in run_query.filters
    assert ((), {"is_debug": False}) in run_query.filters
    assert response["data"]["items"][0]["workflow_name"] == "Flow"
    assert response["data"]["items"][0]["triggered_by_name"] == "runner"
    assert response["data"]["items"][1]["workflow_name"] is None
    assert response["data"]["page"] == 2


@pytest.mark.anyio
async def test_global_run_list_applies_visibility_scope_to_workflow_queryset(
    monkeypatch,
):
    """Removing the scope filter must fail here: /workflows/runs is the leak.

    The endpoint passes the scope positionally, so a stub that recorded only
    kwargs could not see it. This asserts the visibility ``Q`` actually reaches
    the workflow queryset for a non-superuser.
    """
    user_id, team_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow_query = Query([SimpleNamespace(id=uuid4())])
    monkeypatch.setattr(workflows.Workflow, "all", Mock(return_value=workflow_query))
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query([], total=0))
    )
    monkeypatch.setattr(
        workflow_access.TeamMember, "filter", Mock(return_value=Query([team_id]))
    )

    await workflows.list_all_workflow_runs(
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

    scopes = [args[0] for args, _kwargs in workflow_query.filters if args]
    assert len(scopes) == 1, "the workflow queryset must be visibility-scoped once"
    assert isinstance(scopes[0], Q)
    leaves = _flatten(scopes[0])
    # Team/public workflows only inside the caller's teams; own private
    # workflows remain readable. A foreign member's private row matches none.
    assert {
        "team_id__in": [team_id],
        "visibility__in": [WorkflowVisibility.TEAM, WorkflowVisibility.PUBLIC],
    } in leaves
    assert {
        "created_by_id": user_id,
        "visibility": WorkflowVisibility.PRIVATE,
    } in leaves


@pytest.mark.anyio
async def test_global_run_stats_applies_visibility_scope_to_workflow_queryset(
    monkeypatch,
):
    """``/workflows/runs/stats`` must scope its workflow set the same way."""
    user_id, team_id = uuid4(), uuid4()
    workflow_query = Query([])
    monkeypatch.setattr(workflows.Workflow, "all", Mock(return_value=workflow_query))
    monkeypatch.setattr(
        workflow_access.TeamMember, "filter", Mock(return_value=Query([team_id]))
    )

    await workflows.get_workflow_run_stats(
        team_id=None, current_user=SimpleNamespace(id=user_id, is_superuser=False)
    )

    scopes = [args[0] for args, _kwargs in workflow_query.filters if args]
    assert len(scopes) == 1
    assert isinstance(scopes[0], Q)


@pytest.mark.anyio
async def test_global_run_list_and_stats_return_empty_for_no_accessible_workflows(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    memberships = Query([uuid4()])
    monkeypatch.setattr(
        workflow_access.TeamMember, "filter", Mock(return_value=memberships)
    )
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
    monkeypatch.setattr(
        workflows.Workflow, "all", Mock(return_value=Query([first, second]))
    )
    monkeypatch.setattr(
        workflows.stats_sql,
        "workflow_global_run_stats",
        AsyncMock(
            return_value={
                "runs_by_status": {"success": 2, "failed": 2, "pending": 1},
                "total_runs": 5,
                # ``unknown_id`` is absent from the accessible map and must be
                # dropped from the response rather than rendered nameless.
                "top_workflows": [(first_id, 2), (second_id, 1), (unknown_id, 1)],
                "avg_duration_ms": 200,
            }
        ),
    )

    response = await workflows.get_workflow_run_stats(
        team_id=None, current_user=SimpleNamespace(id=uuid4(), is_superuser=True)
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
    access = AsyncMock()
    overview = AsyncMock(
        side_effect=[
            {
                "total_runs": 0,
                "success_count": 0,
                "failed_count": 0,
                "timeout_count": 0,
                "avg_duration_ms": 0,
                "last_run_at": None,
            },
            {
                "total_runs": 3,
                "success_count": 1,
                "failed_count": 1,
                "timeout_count": 1,
                "avg_duration_ms": 200.0,
                "last_run_at": fixed_now,
            },
        ]
    )
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    monkeypatch.setattr(workflows.stats_sql, "workflow_run_overview", overview)
    monkeypatch.setattr(
        workflows.stats_sql,
        "workflow_trend_buckets",
        AsyncMock(
            return_value={
                datetime(2026, 2, 7): {
                    "runs": 3,
                    "success": 1,
                    "failed": 1,
                    "avg_duration": 200.0,
                }
            }
        ),
    )
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
