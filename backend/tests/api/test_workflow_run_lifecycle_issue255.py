from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.schemas.response import BusinessError, ResponseCode


class RunQuery:
    def __init__(self, run):
        self.run = run

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run", "msg_key"),
    [
        (None, "workflow_run_not_found"),
        (SimpleNamespace(workflow_id=None), "workflow_not_found"),
    ],
)
async def test_stream_rejects_missing_run_or_workflow(monkeypatch, run, msg_key):
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.stream_workflow_run(uuid4())

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == msg_key
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_requires_user_for_user_triggered_run(monkeypatch):
    run = SimpleNamespace(workflow_id=uuid4(), triggered_by_id=uuid4())
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.stream_workflow_run(uuid4(), current_user=None)

    assert exc_info.value.code == ResponseCode.UNAUTHORIZED
    assert exc_info.value.msg_key == "unauthorized"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("triggered_by_id", [uuid4(), None])
async def test_stream_checks_private_access_and_allows_public_webhook_runs(
    monkeypatch, triggered_by_id
):
    run_id = uuid4()
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(
        workflow_id=workflow_id,
        triggered_by_id=triggered_by_id,
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )
    access = AsyncMock()
    monkeypatch.setattr(workflows, "check_workflow_access", access)

    from app.services.workflow import stream as stream_module

    stream_to_sse = Mock()

    async def fake_stream_to_sse(received_run_id, from_sequence):
        stream_to_sse(received_run_id, from_sequence)
        yield "data: complete\n\n"

    monkeypatch.setattr(stream_module, "stream_to_sse", fake_stream_to_sse)

    response = await workflows.stream_workflow_run(
        run_id, from_sequence=7, current_user=user
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == ["data: complete\n\n"]
    stream_to_sse.assert_called_once_with(str(run_id), 7)
    if triggered_by_id is None:
        access.assert_not_awaited()
    else:
        access.assert_awaited_once_with(workflow_id, user)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run", "msg_key"),
    [
        (None, "workflow_run_not_found"),
        (SimpleNamespace(workflow_id=None), "workflow_not_found"),
    ],
)
async def test_cancel_rejects_missing_run_or_workflow(monkeypatch, run, msg_key):
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.cancel_workflow_run(
            uuid4(), SimpleNamespace(), SimpleNamespace(id=uuid4())
        )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == msg_key


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [True, False])
async def test_cancel_checks_write_access_and_reports_orchestrator_result(
    monkeypatch, cancelled
):
    run_id = uuid4()
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(workflow_id=workflow_id)
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )
    access = AsyncMock()
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)

    import app.services.workflow as workflow_service

    cancel = AsyncMock(return_value=cancelled)
    monkeypatch.setattr(
        workflow_service,
        "WorkflowOrchestrator",
        lambda: SimpleNamespace(cancel=cancel),
    )

    response = await workflows.cancel_workflow_run(run_id, SimpleNamespace(), user)

    assert response["data"] == {"cancelled": cancelled}
    access.assert_awaited_once_with(workflow_id, user, require_write=True)
    cancel.assert_awaited_once_with(str(run_id))
    assert audit.await_args.kwargs["metadata"] == {
        "workflow_id": str(workflow_id),
        "cancelled": cancelled,
    }


@pytest.mark.asyncio
async def test_delete_run_checks_write_access_deletes_and_audits(monkeypatch):
    run_id = uuid4()
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    delete = AsyncMock()
    run = SimpleNamespace(workflow_id=workflow_id, delete=delete)
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: RunQuery(run)
    )
    access = AsyncMock()
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)

    response = await workflows.delete_workflow_run(run_id, SimpleNamespace(), user)

    assert response["data"] == {"id": str(run_id)}
    access.assert_awaited_once_with(workflow_id, user, require_write=True)
    delete.assert_awaited_once_with()
    assert audit.await_args.kwargs["metadata"] == {"workflow_id": str(workflow_id)}
