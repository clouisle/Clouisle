from types import SimpleNamespace
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.api import deps
from app.api.v1.endpoints import workflows
from app.models.workflow import RunStatus, TriggerType, WorkflowStatus
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.workflow import WorkflowRunRequest
from app.tasks.workflow import run_workflow_task
import app.services.workflow.pause_approvers as pause_approvers


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

    def using_db(self, *_args):
        return self

    def select_for_update(self):
        return self


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
        SimpleNamespace(base_url="http://testserver/"),
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


class PauseQuery:
    def __init__(self, *, first=None, updated=0):
        self.first_value = first
        self.updated = updated

    async def first(self):
        return self.first_value

    def order_by(self, *_args):
        return self

    async def update(self, **_kwargs):
        return self.updated

    def using_db(self, *_args):
        return self

    def select_for_update(self):
        return self


@asynccontextmanager
async def _pause_transaction():
    yield object()


@pytest.fixture(autouse=True)
def mock_pause_dependencies(monkeypatch):
    async def resolve(workflow, config):
        raw = config.get("approverIds") if isinstance(config, dict) else None
        if isinstance(raw, list):
            ids = []
            for item in raw:
                try:
                    user_id = UUID(str(item))
                except (TypeError, ValueError):
                    continue
                if user_id not in ids:
                    ids.append(user_id)
            return ids
        owner_id = getattr(workflow, "created_by_id", None)
        return [owner_id] if owner_id else []

    monkeypatch.setattr(workflows, "in_transaction", _pause_transaction)
    monkeypatch.setattr(workflows, "resolve_pause_approver_ids", resolve)


@pytest.mark.parametrize(
    "value",
    ["", "   ", [], {}],
)
def test_pause_submission_rejects_empty_required_values(value):
    config = {
        "inputVariables": [
            {
                "name": "value",
                "type": "text" if isinstance(value, str) else "object",
                "required": True,
            }
        ]
    }

    assert not workflows.pause_submission_is_valid(
        config, "variables", {"value": value}
    )


@pytest.mark.parametrize(
    ("var_type", "valid_value"),
    [
        ("text", "hello"),
        ("paragraph", "multi\nline"),
        ("select", "chosen"),
        ("number", 42),
        ("number", 3.5),
        ("checkbox", True),
        ("checkbox", False),
        ("array", [1, "two", {"three": 3}]),
        ("object", {"a": 1, "b": [2]}),
        ("file", "/api/v1/upload/files/a.pdf"),
        ("image", "/api/v1/upload/files/a.png"),
        ("files", ["/api/v1/upload/files/a.pdf", "/api/v1/upload/files/b.pdf"]),
        ("images", ["/api/v1/upload/files/a.png", "/api/v1/upload/files/b.png"]),
    ],
)
def test_pause_submission_accepts_every_variable_type(var_type, valid_value):
    config = {"inputVariables": [{"name": "value", "type": var_type, "required": True}]}
    assert workflows.pause_submission_is_valid(
        config, "variables", {"value": valid_value}
    )


@pytest.mark.parametrize(
    ("var_type", "invalid_value"),
    [
        ("text", 42),
        ("paragraph", ["list"]),
        ("select", 1),
        ("number", "42"),
        ("number", True),  # bool is an int subclass, but not a valid number
        ("checkbox", "true"),
        ("array", '["a", "b"]'),
        ("array", {"a": 1}),
        ("object", '{"a": 1}'),
        ("object", [1, 2]),
        ("file", ["/api/v1/upload/files/a.pdf"]),
        ("image", {"url": "/api/v1/upload/files/a.png"}),
        ("files", "/api/v1/upload/files/a.pdf"),
        ("images", {"url": "/api/v1/upload/files/a.png"}),
    ],
)
def test_pause_submission_rejects_type_mismatches(var_type, invalid_value):
    config = {
        "inputVariables": [{"name": "value", "type": var_type, "required": False}]
    }
    assert not workflows.pause_submission_is_valid(
        config, "variables", {"value": invalid_value}
    )


def test_pause_submission_accepts_optional_missing_values_for_every_type():
    config = {
        "inputVariables": [
            {"name": "value", "type": var_type, "required": False}
            for var_type in [
                "text",
                "paragraph",
                "select",
                "number",
                "checkbox",
                "array",
                "object",
                "file",
                "image",
                "files",
                "images",
            ]
        ]
    }
    assert workflows.pause_submission_is_valid(
        config,
        "variables",
        {"number": ""},  # cleared optional number
    )


@pytest.mark.asyncio
async def test_submit_pause_allows_configured_private_workflow_approver(monkeypatch):
    workflow_id, run_id, approver_id, pause_id = (uuid4() for _ in range(4))
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Private flow",
        created_by_id=uuid4(),
        team_id=uuid4(),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "pauseConfig": {
                                "mode": "variables",
                                "approverIds": [str(approver_id)],
                                "inputVariables": [],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="pending",
    )
    denied = BusinessError(
        code=ResponseCode.FORBIDDEN,
        msg_key="workflow_access_denied",
        status_code=403,
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(side_effect=denied),
    )
    monkeypatch.setattr(
        workflows.Workflow, "filter", lambda **_kwargs: Query(first=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "filter",
        lambda **_kwargs: Query(first=run),
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request,
            updated=1 if "status" in kwargs else 0,
        ),
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    monkeypatch.setattr(workflows, "remove_pause_pending_notifications", AsyncMock())
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={}),
        SimpleNamespace(),
        SimpleNamespace(id=approver_id, is_superuser=False),
    )

    assert response["data"]["status"] == "submitted"
    delay.assert_called_once_with(str(run_id))


@pytest.mark.asyncio
async def test_submit_pause_variables_dispatches_resume(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        created_by_id=user_id,
        team_id=uuid4(),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "inputVariables": [
                                    {
                                        "name": "target_price",
                                        "type": "number",
                                        "required": True,
                                    }
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="pending",
    )
    checks = AsyncMock(return_value=workflow)
    audit = AsyncMock()
    delay = Mock()
    remove_notifications = AsyncMock()

    monkeypatch.setattr(workflows, "check_workflow_access", checks)
    monkeypatch.setattr(
        workflows, "remove_pause_pending_notifications", remove_notifications
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request, updated=1 if "status" in kwargs else 0
        ),
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    monkeypatch.setattr(run_workflow_task, "delay", Mock())
    from app.tasks.workflow import resume_workflow_task

    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={"target_price": 42}),
        SimpleNamespace(),
        user,
    )

    assert response["data"] == {
        "pause_request_id": str(pause_id),
        "status": "submitted",
    }
    checks.assert_awaited_once_with(workflow_id, user)
    delay.assert_called_once_with(str(run_id))
    audit.assert_awaited_once()
    remove_notifications.assert_awaited_once_with(pause_request.id)


@pytest.mark.asyncio
async def test_submit_pause_approval_rejects_invalid_decision(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    user = SimpleNamespace(id=user_id)
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {"config": {"mode": "approval"}},
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        description=None,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "maybe"}),
            SimpleNamespace(),
            user,
        )

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    assert exc_info.value.status_code == 400
    assert exc_info.value.msg_key == "workflow_pause_invalid_values"


@pytest.mark.asyncio
async def test_submit_pause_variables_mode_rejects_missing_and_wrong_types(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    user = SimpleNamespace(id=user_id, is_superuser=False)
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "inputVariables": [
                                    {
                                        "name": "target_price",
                                        "type": "number",
                                        "required": True,
                                    },
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="pending",
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(
            return_value=SimpleNamespace(
                id=workflow_id, created_by_id=user_id, team_id=uuid4()
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    # required field missing
    with pytest.raises(BusinessError) as missing:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={}),
            SimpleNamespace(),
            user,
        )
    assert missing.value.msg_key == "workflow_pause_invalid_values"

    # boolean submitted as a number must be rejected (bool is an int subclass)
    with pytest.raises(BusinessError) as boolean_as_number:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"target_price": True}),
            SimpleNamespace(),
            user,
        )
    assert boolean_as_number.value.msg_key == "workflow_pause_invalid_values"


@pytest.mark.asyncio
async def test_get_pending_pause_request_returns_pinned_input_schema(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "title": "Budget review",
                                "inputVariables": [
                                    {
                                        "name": "target_price",
                                        "type": "number",
                                        "required": True,
                                        "defaultValue": 12,
                                        "description": "Approved price",
                                    }
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        description=None,
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(
            return_value=SimpleNamespace(
                id=workflow_id, created_by_id=user_id, team_id=uuid4()
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(pause_approvers.User, "filter", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    assert response["data"]["pause_request"] == {
        "id": str(pause_id),
        "node_id": "pause-1",
        "node_name": "Pause",
        "mode": "variables",
        "title": "Budget review",
        "description": "",
        "workflow_name": "Flow",
        "triggered_by_name": "alice",
        "triggered_at": "2026-01-01T00:00:00Z",
        "input_variables": [
            {
                "name": "target_price",
                "label": "target_price",
                "type": "number",
                "required": True,
                "default": 12,
                "description": "Approved price",
                "options": None,
                "fileConfig": None,
            }
        ],
        "approver_ids": [str(user_id)],
        "approver_names": [],
        "require_all": False,
        "approvals": [],
        "already_submitted": False,
        "can_submit": True,
    }


def _require_all_run(workflow_id, run_id, *approver_ids):
    return SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "requireAllApprovals": True,
                                "approverIds": [str(uid) for uid in approver_ids],
                            }
                        },
                    }
                ]
            }
        },
    )


@pytest.mark.asyncio
async def test_submit_pause_require_all_partial_keeps_pending(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    approver_b = uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=uuid4(), team_id=uuid4()
    )
    run = _require_all_run(workflow_id, run_id, user_id, approver_b)
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        approvals=None,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request, updated=1 if "status" in kwargs else 0
        ),
    )
    remove_for = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notification_for", remove_for)
    remove_all = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notifications", remove_all)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(
            values={"decision": "approved"}, comment="ok"
        ),
        SimpleNamespace(),
        user,
    )

    # One of two approvers decided: the run must stay waiting, the request
    # pending, and only this user's notification is removed.
    assert response["data"]["status"] == "pending"
    remove_for.assert_awaited_once_with(pause_request.id, user_id)
    remove_all.assert_not_awaited()
    delay.assert_not_called()
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_pause_require_all_all_approved_resolves(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    approver_b = uuid4()
    user = SimpleNamespace(id=approver_b, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=uuid4(), team_id=uuid4()
    )
    run = _require_all_run(workflow_id, run_id, user_id, approver_b)
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        approvals=[
            {
                "approver_id": str(user_id),
                "decision": "approved",
                "comment": "looks good",
                "submitted_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request, updated=1 if "status" in kwargs else 0
        ),
    )
    remove_for = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notification_for", remove_for)
    remove_all = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notifications", remove_all)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
        SimpleNamespace(),
        user,
    )

    assert response["data"]["status"] == "submitted"
    remove_for.assert_awaited_once_with(pause_request.id, approver_b)
    remove_all.assert_awaited_once_with(pause_request.id)
    delay.assert_called_once_with(str(run_id))
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_pause_require_all_rejection_short_circuits(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    approver_b = uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=uuid4(), team_id=uuid4()
    )
    run = _require_all_run(workflow_id, run_id, user_id, approver_b)
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        approvals=None,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request, updated=1 if "status" in kwargs else 0
        ),
    )
    remove_for = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notification_for", remove_for)
    remove_all = AsyncMock()
    monkeypatch.setattr(workflows, "remove_pause_pending_notifications", remove_all)
    audit = AsyncMock()
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={"decision": "rejected"}),
        SimpleNamespace(),
        user,
    )

    # Any rejection resolves the request immediately: the run fails on resume.
    assert response["data"]["status"] == "submitted"
    delay.assert_called_once_with(str(run_id))
    remove_all.assert_awaited_once_with(pause_request.id)
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_submit_pause_require_all_duplicate_submission_conflicts(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    approver_b = uuid4()
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id, name="Flow", created_by_id=uuid4(), team_id=uuid4()
    )
    run = _require_all_run(workflow_id, run_id, user_id, approver_b)
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        approvals=[
            {
                "approver_id": str(user_id),
                "decision": "approved",
                "comment": None,
                "submitted_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )
    monkeypatch.setattr(workflows, "remove_pause_pending_notification_for", AsyncMock())
    monkeypatch.setattr(workflows, "remove_pause_pending_notifications", AsyncMock())
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    from app.tasks.workflow import resume_workflow_task

    monkeypatch.setattr(resume_workflow_task, "delay", Mock())

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            user,
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.status_code == 409
    assert exc_info.value.msg_key == "workflow_pause_already_submitted"


@pytest.mark.asyncio
async def test_get_pending_pause_request_require_all_payload(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    approver_b = uuid4()
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "requireAllApprovals": True,
                                "approverIds": [str(user_id), str(approver_b)],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        description=None,
        approvals=[
            {
                "approver_id": str(user_id),
                "decision": "approved",
                "comment": "ok",
                "submitted_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=SimpleNamespace())
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        AsyncMock(
            return_value=[
                SimpleNamespace(id=user_id, username="alice"),
                SimpleNamespace(id=approver_b, username="bob"),
            ]
        ),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )
    pause = response["data"]["pause_request"]
    assert pause["require_all"] is True
    assert pause["already_submitted"] is True
    assert pause["can_submit"] is False
    assert pause["approver_names"] == ["alice", "bob"]
    assert pause["approvals"] == [
        {
            "approver_id": str(user_id),
            "username": "alice",
            "decision": "approved",
            "comment": "ok",
            "submitted_at": "2026-01-01T00:00:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_submit_pause_forbidden_for_non_approver(monkeypatch):
    workflow_id, run_id, user_id, pause_id, approver_id = (uuid4() for _ in range(5))
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        created_by_id=uuid4(),
        team_id=uuid4(),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "approverIds": [str(approver_id)],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="pending",
        description=None,
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            user,
        )

    assert exc_info.value.code == ResponseCode.FORBIDDEN
    assert exc_info.value.status_code == 403
    assert exc_info.value.msg_key == "workflow_pause_not_approver"


@pytest.mark.asyncio
async def test_submit_pause_allows_configured_approver_and_superuser(monkeypatch):
    for superuser in (False, True):
        workflow_id, run_id, user_id, pause_id, approver_id = (
            uuid4() for _ in range(5)
        )
        current_user_id = approver_id if not superuser else user_id
        user = SimpleNamespace(id=current_user_id, is_superuser=superuser)
        workflow = SimpleNamespace(
            id=workflow_id,
            name="Flow",
            created_by_id=uuid4(),
            team_id=uuid4(),
        )
        run = SimpleNamespace(
            id=run_id,
            workflow_id=workflow_id,
            status=RunStatus.WAITING,
            context_snapshot={
                "workflow_definition": {
                    "nodes": [
                        {
                            "id": "pause-1",
                            "data": {
                                "config": {
                                    "mode": "approval",
                                    "approverIds": [str(approver_id)],
                                }
                            },
                        }
                    ]
                }
            },
        )
        pause_request = SimpleNamespace(
            id=pause_id,
            run_id=run_id,
            workflow_id=workflow_id,
            node_id="pause-1",
            node_name="Approval",
            mode="approval",
            status="pending",
        )
        monkeypatch.setattr(
            workflows, "check_workflow_access", AsyncMock(return_value=workflow)
        )
        monkeypatch.setattr(
            workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
        )
        monkeypatch.setattr(
            workflows.WorkflowPauseRequest,
            "filter",
            lambda **kwargs: PauseQuery(
                first=pause_request, updated=1 if "status" in kwargs else 0
            ),
        )
        monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
        from app.tasks.workflow import resume_workflow_task

        delay = Mock()
        monkeypatch.setattr(resume_workflow_task, "delay", delay)

        response = await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            user,
        )

        assert response["data"]["status"] == "submitted"
        delay.assert_called_once_with(str(run_id))


@pytest.mark.asyncio
async def test_get_pending_pause_returns_approver_names_and_can_submit(monkeypatch):
    workflow_id, run_id, user_id, pause_id, approver_id = (uuid4() for _ in range(5))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "title": "Budget approval",
                                "approverIds": [str(approver_id)],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        description=None,
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(id=workflow_id)),
    )
    monkeypatch.setattr(
        pause_approvers.User,
        "filter",
        AsyncMock(return_value=[SimpleNamespace(id=approver_id, username="alice")]),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    # A user outside the approver list must not see the pending request at all.
    assert response["data"]["pause_request"] is None

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=approver_id, is_superuser=False)
    )
    pause = response["data"]["pause_request"]
    assert pause["approver_ids"] == [str(approver_id)]
    assert pause["approver_names"] == ["alice"]
    assert pause["can_submit"] is True
    assert pause["workflow_name"] == "Flow"
    assert pause["triggered_by_name"] == "alice"


@pytest.mark.asyncio
async def test_submit_pause_accepts_checkbox_and_blank_optional_number(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        created_by_id=user_id,
        team_id=uuid4(),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "inputVariables": [
                                    {
                                        "name": "agree",
                                        "type": "checkbox",
                                        "required": True,
                                    },
                                    {
                                        "name": "price",
                                        "type": "number",
                                        "required": False,
                                    },
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="pending",
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **kwargs: PauseQuery(
            first=pause_request, updated=1 if "status" in kwargs else 0
        ),
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    # checkbox bool + cleared optional number ("" treated as absent)
    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={"agree": True, "price": ""}),
        SimpleNamespace(),
        user,
    )

    assert response["data"]["status"] == "submitted"


@pytest.mark.asyncio
async def test_get_pending_pause_passes_options_and_blank_default(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "inputVariables": [
                                    {
                                        "name": "plan",
                                        "type": "select",
                                        "required": False,
                                        "defaultValue": "",
                                        "options": ["basic", "pro"],
                                        "fileConfig": {"maxSize": 10},
                                    }
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        description=None,
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(
            return_value=SimpleNamespace(
                id=workflow_id, created_by_id=user_id, team_id=uuid4()
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(pause_approvers.User, "filter", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    variable = response["data"]["pause_request"]["input_variables"][0]
    assert variable["default"] is None
    assert variable["options"] == ["basic", "pro"]
    assert variable["fileConfig"] == {"maxSize": 10}


@pytest.mark.asyncio
async def test_get_pending_pause_serializes_every_variable_type(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "variables",
                                "inputVariables": [
                                    {"name": name, "type": var_type, "required": True}
                                    for name, var_type in [
                                        ("t", "text"),
                                        ("p", "paragraph"),
                                        ("s", "select"),
                                        ("n", "number"),
                                        ("c", "checkbox"),
                                        ("arr", "array"),
                                        ("obj", "object"),
                                        ("f", "file"),
                                        ("img", "image"),
                                        ("fs", "files"),
                                        ("imgs", "images"),
                                    ]
                                ]
                                + [
                                    {
                                        "name": "upload",
                                        "type": "files",
                                        "required": False,
                                        "defaultValue": "",
                                        "description": "docs",
                                        "options": ["x"],
                                        "fileConfig": {"maxFiles": 3},
                                    }
                                ],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        description=None,
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(
            return_value=SimpleNamespace(
                id=workflow_id, created_by_id=user_id, team_id=uuid4()
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(pause_approvers.User, "filter", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    variables = response["data"]["pause_request"]["input_variables"]
    assert [v["name"] for v in variables] == [
        "t",
        "p",
        "s",
        "n",
        "c",
        "arr",
        "obj",
        "f",
        "img",
        "fs",
        "imgs",
        "upload",
    ]
    assert [v["type"] for v in variables] == [
        "text",
        "paragraph",
        "select",
        "number",
        "checkbox",
        "array",
        "object",
        "file",
        "image",
        "files",
        "images",
        "files",
    ]
    # Every variable keeps its required flag; type metadata round-trips.
    assert all(v["required"] is True for v in variables[:11])
    upload = variables[11]
    assert upload["default"] is None  # blank default -> None
    assert upload["description"] == "docs"
    assert upload["options"] == ["x"]
    assert upload["fileConfig"] == {"maxFiles": 3}


@pytest.mark.asyncio
async def test_submit_pause_rejects_run_not_waiting(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.SUCCESS,
        context_snapshot={},
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="pending",
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(id=workflow_id)),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            SimpleNamespace(id=user_id),
        )

    assert exc_info.value.code == ResponseCode.BAD_REQUEST
    assert exc_info.value.msg_key == "workflow_run_not_waiting"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_pause_rejects_resolved_request(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={},
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status="cancelled",
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(id=workflow_id)),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            SimpleNamespace(id=user_id, is_superuser=False),
        )

    assert exc_info.value.msg_key == "workflow_pause_request_not_pending"
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_pause_resubmits_lost_resume_when_still_waiting(monkeypatch):
    """A SUBMITTED request with a still-WAITING run re-dispatches the resume."""
    workflow_id, run_id, user_id, pause_id, approver_id = (uuid4() for _ in range(5))
    user = SimpleNamespace(id=approver_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        created_by_id=uuid4(),
        team_id=uuid4(),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "approverIds": [str(approver_id)],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="submitted",
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )
    from app.tasks.workflow import resume_workflow_task

    delay = Mock()
    monkeypatch.setattr(resume_workflow_task, "delay", delay)

    response = await workflows.submit_workflow_pause_request(
        workflow_id,
        run_id,
        pause_id,
        workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
        SimpleNamespace(),
        user,
    )

    assert response["data"]["status"] == "submitted"
    delay.assert_called_once_with(str(run_id))


@pytest.mark.asyncio
async def test_submit_pause_lost_resume_still_requires_approver(monkeypatch):
    workflow_id, run_id, user_id, pause_id, approver_id = (uuid4() for _ in range(5))
    user = SimpleNamespace(id=user_id, is_superuser=False)
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        created_by_id=uuid4(),
        team_id=uuid4(),
    )
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        status=RunStatus.WAITING,
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "approverIds": [str(approver_id)],
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        run_id=run_id,
        workflow_id=workflow_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        status="submitted",
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.submit_workflow_pause_request(
            workflow_id,
            run_id,
            pause_id,
            workflows.PauseRequestSubmitRequest(values={"decision": "approved"}),
            SimpleNamespace(),
            user,
        )

    assert exc_info.value.code == ResponseCode.FORBIDDEN
    assert exc_info.value.msg_key == "workflow_pause_not_approver"


@pytest.mark.asyncio
async def test_get_pending_pause_returns_none_when_no_request(monkeypatch):
    workflow_id, run_id, user_id = (uuid4() for _ in range(3))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={},
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(return_value=SimpleNamespace(id=workflow_id)),
    )
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=None),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    assert response["data"]["pause_request"] is None


@pytest.mark.asyncio
async def test_get_pending_pause_prefers_resolved_request_description(monkeypatch):
    workflow_id, run_id, user_id, pause_id = (uuid4() for _ in range(4))
    run = SimpleNamespace(
        id=run_id,
        workflow_id=workflow_id,
        fetch_related=AsyncMock(),
        workflow=SimpleNamespace(name="Flow"),
        triggered_by=SimpleNamespace(username="alice"),
        started_at=None,
        created_at="2026-01-01T00:00:00Z",
        context_snapshot={
            "workflow_definition": {
                "nodes": [
                    {
                        "id": "pause-1",
                        "data": {
                            "config": {
                                "mode": "approval",
                                "title": "Approval",
                                "description": "Raw {{start.price}}",
                            }
                        },
                    }
                ]
            }
        },
    )
    pause_request = SimpleNamespace(
        id=pause_id,
        node_id="pause-1",
        node_name="Approval",
        mode="approval",
        description="Resolved: price is 42",
    )
    monkeypatch.setattr(
        workflows,
        "check_workflow_access",
        AsyncMock(
            return_value=SimpleNamespace(
                id=workflow_id, created_by_id=user_id, team_id=uuid4()
            )
        ),
    )
    monkeypatch.setattr(
        pause_approvers.TeamMember,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(pause_approvers.User, "filter", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", lambda **_kwargs: Query(first=run)
    )
    monkeypatch.setattr(
        workflows.WorkflowPauseRequest,
        "filter",
        lambda **_kwargs: PauseQuery(first=pause_request),
    )

    response = await workflows.get_pending_workflow_pause_request(
        workflow_id, run_id, SimpleNamespace(id=user_id, is_superuser=False)
    )

    assert response["data"]["pause_request"]["description"] == "Resolved: price is 42"
