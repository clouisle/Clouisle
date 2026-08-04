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
    def __init__(self, *, first=None, items=None):
        self.first_value = first
        self.items = items or []

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def all(self):
        return self.items


@pytest.mark.parametrize(
    ("message", "expected"),
    [(None, None), ("unknown internal detail", "safe error")],
)
def test_public_error_sanitizers_hide_internal_details(monkeypatch, message, expected):
    monkeypatch.setattr(workflows, "t", lambda _key: "safe error")
    monkeypatch.setattr(workflows, "get_public_workflow_error_key", lambda _msg: None)
    monkeypatch.setattr(workflows, "is_safe_user_visible_error", lambda _msg: False)
    assert (
        workflows.sanitize_workflow_run_payload({"error_message": message})[
            "error_message"
        ]
        == expected
    )
    assert (
        workflows.sanitize_node_execution_payload({"error_message": message})[
            "error_message"
        ]
        == expected
    )


def test_public_error_sanitizers_translate_known_errors(monkeypatch):
    monkeypatch.setattr(
        workflows, "get_public_workflow_error_key", lambda _msg: "known"
    )
    monkeypatch.setattr(
        workflows, "translate_public_workflow_error", lambda _msg: "translated"
    )

    assert workflows.sanitize_public_workflow_error("known detail") == "translated"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "msg_key"),
    [(None, "api_key_required"), ("not-an-api-key", "invalid_api_key_format")],
)
async def test_webhook_rejects_missing_or_malformed_api_keys(authorization, msg_key):
    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, authorization)

    assert exc_info.value.msg_key == msg_key
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_webhook_wraps_unexpected_authentication_failures(monkeypatch):
    monkeypatch.setattr(
        deps, "_authenticate_api_key", AsyncMock(side_effect=RuntimeError("down"))
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_key")

    assert exc_info.value.msg_key == "api_key_authentication_failed"
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow", "msg_key"),
    [
        (None, "invalid_webhook_token"),
        (
            SimpleNamespace(
                webhook_token="token",
                status=WorkflowStatus.DRAFT,
                trigger_type=TriggerType.WEBHOOK,
            ),
            "workflow_not_published",
        ),
        (
            SimpleNamespace(
                webhook_token="token",
                status=WorkflowStatus.PUBLISHED,
                trigger_type=TriggerType.MANUAL,
            ),
            "webhook_trigger_disabled",
        ),
    ],
)
async def test_webhook_rejects_invalid_workflow_states(monkeypatch, workflow, msg_key):
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        deps, "_authenticate_api_key", AsyncMock(return_value=(user, None))
    )
    candidates = [] if workflow is None else [workflow]
    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **_kwargs: Query(items=candidates)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_key")

    assert exc_info.value.msg_key == msg_key
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_webhook_enforces_api_key_workflow_restrictions(monkeypatch):
    workflow = SimpleNamespace(
        id=uuid4(),
        webhook_token="token",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
    )
    api_key = SimpleNamespace(
        workflows=SimpleNamespace(
            all=AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
        )
    )
    monkeypatch.setattr(
        deps,
        "_authenticate_api_key",
        AsyncMock(return_value=(SimpleNamespace(id=uuid4()), api_key)),
    )
    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **_kwargs: Query(items=[workflow])
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_key")

    assert exc_info.value.msg_key == "api_key_no_workflow_access"


@pytest.mark.asyncio
async def test_webhook_creates_run_and_dispatches_normalized_inputs(monkeypatch):
    workflow_id, team_id, user_id, run_id = (uuid4() for _ in range(4))
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=team_id,
        webhook_token="token",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
    )
    monkeypatch.setattr(
        deps,
        "_authenticate_api_key",
        AsyncMock(return_value=(SimpleNamespace(id=user_id), None)),
    )
    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **_kwargs: Query(items=[workflow])
    )
    create = AsyncMock(return_value=SimpleNamespace(id=run_id))
    monkeypatch.setattr(workflows.WorkflowRun, "create", create)
    delay = Mock()
    monkeypatch.setattr(run_workflow_task, "delay", delay)

    response = await workflows.trigger_workflow_webhook(
        "token", {"inputs": {"query": "hello"}}, "Bearer clou_key"
    )

    assert response["data"]["run_id"] == str(run_id)
    assert create.await_args.kwargs["inputs"] == {"query": "hello"}
    delay.assert_called_once_with(
        run_id=str(run_id),
        workflow_id=str(workflow_id),
        inputs={"query": "hello"},
        user_id=str(user_id),
        team_id=str(team_id),
    )


@pytest.mark.asyncio
async def test_webhook_wraps_run_creation_failure(monkeypatch):
    workflow = SimpleNamespace(
        id=uuid4(),
        team_id=None,
        webhook_token="token",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
    )
    monkeypatch.setattr(
        deps,
        "_authenticate_api_key",
        AsyncMock(return_value=(SimpleNamespace(id=uuid4()), None)),
    )
    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **_kwargs: Query(items=[workflow])
    )
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "create",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_key")

    assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
    assert exc_info.value.msg_key == "workflow_execution_error"


@pytest.mark.asyncio
async def test_run_rejects_draft_workflow(monkeypatch):
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(status=WorkflowStatus.DRAFT)),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.run_workflow(
            uuid4(),
            WorkflowRunRequest(inputs={}),
            SimpleNamespace(),
            SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.msg_key == "workflow_not_published"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint_name", "is_debug", "message_key"),
    [
        ("run_workflow", False, "workflow_run_started"),
        ("debug_workflow", True, "workflow_debug_started"),
    ],
)
async def test_run_endpoints_create_dispatch_and_audit(
    monkeypatch, endpoint_name, is_debug, message_key
):
    workflow_id, team_id, user_id, run_id = (uuid4() for _ in range(4))
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=team_id,
        name="Flow",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.MANUAL,
    )
    access = AsyncMock(return_value=workflow)
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    create = AsyncMock(return_value=SimpleNamespace(id=run_id))
    monkeypatch.setattr(workflows.WorkflowRun, "create", create)
    delay = Mock()
    monkeypatch.setattr(run_workflow_task, "delay", delay)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)

    response = await getattr(workflows, endpoint_name)(
        workflow_id,
        WorkflowRunRequest(inputs={"query": "hello"}),
        SimpleNamespace(),
        SimpleNamespace(id=user_id),
    )

    assert response["data"]["run_id"] == str(run_id)
    assert response["msg"]
    assert create.await_args.kwargs["is_debug"] is is_debug
    assert create.await_args.kwargs["status"] == RunStatus.PENDING
    assert delay.call_args.kwargs["team_id"] == str(team_id)
    assert delay.call_args.kwargs.get("is_debug", False) is is_debug
    assert audit.await_args.kwargs["metadata"]["is_debug"] is is_debug
    access.assert_awaited_once_with(
        workflow_id, SimpleNamespace(id=user_id), require_write=True
    ) if is_debug else access.assert_awaited_once_with(
        workflow_id, SimpleNamespace(id=user_id)
    )
    assert message_key in {"workflow_run_started", "workflow_debug_started"}
