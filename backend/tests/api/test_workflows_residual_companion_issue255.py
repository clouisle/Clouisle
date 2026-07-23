from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api import deps
from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus, TriggerType, WorkflowStatus
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.workflow import WorkflowRunRequest
from app.tasks.workflow import run_workflow_task


class Query:
    def __init__(self, items=None, *, first=None, total=0):
        self.items = items or []
        self.first_value = first
        self.total = total
        self.filters = []

    def all(self):
        return self

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.total

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


@pytest.mark.asyncio
async def test_list_runs_bad_search_forces_empty_filter_and_sanitizes_errors(
    monkeypatch,
):
    query = Query([SimpleNamespace(error_message="raw internal detail")], total=1)
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=query))
    monkeypatch.setattr(
        workflows.WorkflowRunListItem,
        "model_validate",
        Mock(return_value=Dump({"id": str(uuid4()), "error_message": "raw"})),
    )
    monkeypatch.setattr(workflows, "get_public_workflow_error_key", lambda _msg: None)
    monkeypatch.setattr(workflows, "t", lambda _key: "safe")

    response = await workflows.list_workflow_runs(
        uuid4(),
        status=RunStatus.FAILED,
        is_debug=True,
        search="not-a-uuid",
        page=1,
        page_size=10,
        current_user=SimpleNamespace(),
    )

    assert {"id__isnull": True} in query.filters
    assert {"status": RunStatus.FAILED} in query.filters
    assert {"is_debug": True} in query.filters
    assert response["data"]["items"][0]["error_message"] == "safe"


@pytest.mark.asyncio
async def test_stream_run_allows_webhook_triggered_run_without_user(monkeypatch):
    run_id = uuid4()
    run = SimpleNamespace(workflow_id=uuid4(), triggered_by_id=None)
    access = AsyncMock()
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )
    monkeypatch.setattr(workflows, "check_workflow_access", access)

    response = await workflows.stream_workflow_run(
        run_id, from_sequence=7, current_user=None
    )

    access.assert_not_awaited()
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.asyncio
async def test_stream_run_rejects_user_triggered_run_without_user(monkeypatch):
    run = SimpleNamespace(workflow_id=uuid4(), triggered_by_id=uuid4())
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.stream_workflow_run(uuid4(), current_user=None)

    assert exc_info.value.code == ResponseCode.UNAUTHORIZED
    assert exc_info.value.status_code == 401
    assert exc_info.value.msg_key == "unauthorized"


@pytest.mark.asyncio
async def test_cancel_run_reports_not_cancellable(monkeypatch):
    import app.services.workflow as workflow_services

    run_id, workflow_id = uuid4(), uuid4()
    run = SimpleNamespace(workflow_id=workflow_id)
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    orchestrator = SimpleNamespace(cancel=AsyncMock(return_value=False))
    monkeypatch.setattr(
        workflow_services, "WorkflowOrchestrator", Mock(return_value=orchestrator)
    )

    response = await workflows.cancel_workflow_run(
        run_id, SimpleNamespace(), SimpleNamespace()
    )

    assert response["data"] == {"cancelled": False}
    assert response["msg"]
    orchestrator.cancel.assert_awaited_once_with(str(run_id))


@pytest.mark.asyncio
async def test_run_and_debug_wrap_run_creation_failures(monkeypatch):
    workflow = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        name="Flow",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.MANUAL,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "create",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    delay = Mock()
    monkeypatch.setattr(run_workflow_task, "delay", delay)

    for endpoint in (workflows.run_workflow, workflows.debug_workflow):
        with pytest.raises(BusinessError) as exc_info:
            await endpoint(
                workflow.id,
                WorkflowRunRequest(inputs={}),
                SimpleNamespace(),
                SimpleNamespace(id=uuid4()),
            )
        assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
        assert exc_info.value.msg_key == "workflow_execution_error"

    delay.assert_not_called()


@pytest.mark.asyncio
async def test_webhook_success_with_unrestricted_api_key_and_plain_header(monkeypatch):
    workflow_id, user_id, run_id = uuid4(), uuid4(), uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=None,
        webhook_token="token",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
    )
    api_key = SimpleNamespace(workflows=SimpleNamespace(all=AsyncMock(return_value=[])))
    monkeypatch.setattr(
        deps,
        "_authenticate_api_key",
        AsyncMock(return_value=(SimpleNamespace(id=user_id), api_key)),
    )
    monkeypatch.setattr(
        workflows.Workflow, "filter", Mock(return_value=Query([workflow]))
    )
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "create",
        AsyncMock(return_value=SimpleNamespace(id=run_id)),
    )
    delay = Mock()
    monkeypatch.setattr(run_workflow_task, "delay", delay)

    response = await workflows.trigger_workflow_webhook(
        "token", {"query": "raw"}, "clou_plain"
    )

    assert response["data"]["run_id"] == str(run_id)
    delay.assert_called_once_with(
        run_id=str(run_id),
        workflow_id=str(workflow_id),
        inputs={"query": "raw"},
        user_id=str(user_id),
        team_id=None,
    )


@pytest.mark.asyncio
async def test_restore_version_success_defaults_trigger_config_and_description(
    monkeypatch,
):
    workflow_id = uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=uuid4(),
        name="Flow",
        version=3,
        definition={"old": True},
        variables=[{"name": "old"}],
        trigger_type=TriggerType.MANUAL,
        trigger_config={"old": True},
        save=AsyncMock(),
    )
    version = SimpleNamespace(
        definition={"restored": True},
        variables=[{"name": "new"}],
        trigger_type=TriggerType.WEBHOOK,
        trigger_config=None,
    )
    creates = AsyncMock(
        side_effect=[SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(
        workflows.WorkflowVersion, "filter", Mock(return_value=Query(first=version))
    )
    monkeypatch.setattr(workflows.WorkflowVersion, "create", creates)
    monkeypatch.setattr(
        workflows.Workflow,
        "get",
        Mock(return_value=AwaitableValue(SimpleNamespace(id=workflow_id, name="Flow"))),
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(
        workflows, "t", lambda key, **kwargs: f"{key}:{kwargs.get('version', '')}"
    )
    monkeypatch.setattr(
        workflows.WorkflowOut,
        "model_validate",
        Mock(return_value=Dump({"id": str(workflow_id)})),
    )

    response = await workflows.restore_workflow_version(
        workflow_id,
        2,
        SimpleNamespace(description=None),
        SimpleNamespace(),
        SimpleNamespace(id=uuid4()),
    )

    assert workflow.trigger_config == {}
    assert workflow.version == 4
    assert response["data"] == {"id": str(workflow_id)}
    assert (
        creates.await_args_list[1].kwargs["description"]
        == "workflow_restored_from_version:2"
    )
