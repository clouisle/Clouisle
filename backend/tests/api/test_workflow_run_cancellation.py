from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.schemas.response import BusinessError, ResponseCode


def _run_lookup(run):
    query = MagicMock()
    query.prefetch_related.return_value.first = AsyncMock(return_value=run)
    return query


@pytest.mark.anyio
async def test_cancel_workflow_run_rejects_missing_run():
    run_id = uuid4()

    with patch.object(workflows.WorkflowRun, "filter", return_value=_run_lookup(None)):
        with pytest.raises(BusinessError) as error:
            await workflows.cancel_workflow_run(
                run_id, SimpleNamespace(), SimpleNamespace()
            )

    assert error.value.code == ResponseCode.NOT_FOUND
    assert error.value.msg_key == "workflow_run_not_found"
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_cancel_workflow_run_rejects_orphaned_run():
    run_id = uuid4()
    run = SimpleNamespace(workflow_id=None)

    with patch.object(workflows.WorkflowRun, "filter", return_value=_run_lookup(run)):
        with pytest.raises(BusinessError) as error:
            await workflows.cancel_workflow_run(
                run_id, SimpleNamespace(), SimpleNamespace()
            )

    assert error.value.code == ResponseCode.NOT_FOUND
    assert error.value.msg_key == "workflow_not_found"
    assert error.value.status_code == 404


@pytest.mark.anyio
async def test_cancel_workflow_run_stops_when_write_access_is_denied():
    run_id = uuid4()
    workflow_id = uuid4()
    user = SimpleNamespace()
    access_error = BusinessError(code=ResponseCode.FORBIDDEN, status_code=403)
    access = AsyncMock(side_effect=access_error)

    with (
        patch.object(
            workflows.WorkflowRun,
            "filter",
            return_value=_run_lookup(SimpleNamespace(workflow_id=workflow_id)),
        ),
        patch.object(workflows, "check_workflow_access", access),
        patch("app.services.workflow.WorkflowOrchestrator") as orchestrator,
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit_log,
    ):
        with pytest.raises(BusinessError) as error:
            await workflows.cancel_workflow_run(run_id, SimpleNamespace(), user)

    assert error.value is access_error
    access.assert_awaited_once_with(workflow_id, user, require_write=True)
    orchestrator.return_value.cancel.assert_not_called()
    audit_log.assert_not_awaited()


@pytest.mark.anyio
async def test_cancel_workflow_run_cancels_and_audits():
    run_id = uuid4()
    workflow_id = uuid4()
    request = SimpleNamespace()
    user = SimpleNamespace()
    access = AsyncMock()
    cancel = AsyncMock(return_value=True)

    with (
        patch.object(
            workflows.WorkflowRun,
            "filter",
            return_value=_run_lookup(SimpleNamespace(workflow_id=workflow_id)),
        ),
        patch.object(workflows, "check_workflow_access", access),
        patch("app.services.workflow.WorkflowOrchestrator") as orchestrator,
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit_log,
    ):
        orchestrator.return_value.cancel = cancel

        response = await workflows.cancel_workflow_run(run_id, request, user)

    assert response["code"] == ResponseCode.SUCCESS
    assert response["data"] == {"cancelled": True}
    access.assert_awaited_once_with(workflow_id, user, require_write=True)
    cancel.assert_awaited_once_with(str(run_id))
    audit_log.assert_awaited_once_with(
        user=user,
        action="cancel_workflow_run",
        resource_type="workflow_run",
        resource_id=run_id,
        resource_name=str(run_id),
        operation="update",
        status="success",
        request=request,
        metadata={"workflow_id": str(workflow_id), "cancelled": True},
    )
