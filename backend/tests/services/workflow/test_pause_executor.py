from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.models.workflow import PauseRequestStatus
from app.services.workflow.executors.pause import PauseNodeExecutor
import app.services.workflow.executors.pause as pause_module


def _query(result):
    query = Mock()
    query.order_by.return_value = query
    query.first = AsyncMock(return_value=result)
    return query


def _node(mode="variables"):
    config = {
        "mode": mode,
        "title": "Pause for external input",
        "inputVariables": [
            {
                "name": "target_price",
                "type": "number",
                "required": True,
                "description": "Approved price",
            }
        ],
    }
    return {"id": "pause-1", "data": {"label": "Pause", "config": config}}


@pytest.mark.asyncio
async def test_pause_executor_creates_pending_request_and_waits(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    request_query = _query(None)
    execution = SimpleNamespace(id=uuid4())
    execution_query = _query(execution)
    create = AsyncMock()
    notify = AsyncMock()

    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=request_query)
    )
    monkeypatch.setattr(pause_module.WorkflowPauseRequest, "create", create)
    monkeypatch.setattr(
        pause_module.NodeExecution, "filter", Mock(return_value=execution_query)
    )
    monkeypatch.setattr(pause_module, "notify_pause_pending", notify)

    result = await PauseNodeExecutor().execute(_node(), SimpleNamespace(), run)

    assert result.waiting is True
    execution_query.order_by.assert_called_once_with("-started_at")
    assert result.outputs == {}
    create.assert_awaited_once_with(
        run_id=run.id,
        node_execution_id=execution.id,
        workflow_id=run.workflow_id,
        node_id="pause-1",
        node_name="Pause",
        mode="variables",
        status=PauseRequestStatus.PENDING,
        description=None,
    )
    notify.assert_awaited_once()
    assert notify.await_args.args[0] is run
    assert notify.await_args.args[1]["mode"] == "variables"


@pytest.mark.asyncio
async def test_pause_executor_reads_frontend_pause_config_for_approval(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    request_query = _query(None)
    execution_query = _query(SimpleNamespace(id=uuid4()))
    create = AsyncMock()
    notify = AsyncMock()
    node = {
        "id": "pause-approval",
        "data": {
            "label": "审批",
            "pauseConfig": {"mode": "approval", "title": "请审批"},
        },
    }

    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=request_query)
    )
    monkeypatch.setattr(pause_module.WorkflowPauseRequest, "create", create)
    monkeypatch.setattr(
        pause_module.NodeExecution, "filter", Mock(return_value=execution_query)
    )
    monkeypatch.setattr(pause_module, "notify_pause_pending", notify)

    result = await PauseNodeExecutor().execute(node, SimpleNamespace(), run)

    assert result.waiting is True
    assert create.await_args.kwargs["mode"] == "approval"
    notify.assert_awaited_once()
    assert notify.await_args.args[1]["mode"] == "approval"


@pytest.mark.asyncio
async def test_pause_executor_emits_submitted_variables(monkeypatch):
    request = SimpleNamespace(
        status=PauseRequestStatus.SUBMITTED,
        values={"target_price": 42},
        submitted_by_id=uuid4(),
    )
    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=_query(request))
    )

    result = await PauseNodeExecutor().execute(
        _node(), SimpleNamespace(), SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    )

    assert result.waiting is False
    assert result.error is None
    assert result.outputs == {"target_price": 42}


@pytest.mark.asyncio
async def test_pause_executor_emits_approval_comment_from_request(monkeypatch):
    submitter_id = uuid4()
    request = SimpleNamespace(
        status=PauseRequestStatus.SUBMITTED,
        values={"decision": "approved"},
        comment="Ready to run",
        submitted_by_id=submitter_id,
    )
    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=_query(request))
    )

    result = await PauseNodeExecutor().execute(
        _node("approval"),
        SimpleNamespace(),
        SimpleNamespace(id=uuid4(), workflow_id=uuid4()),
    )

    assert result.error is None
    assert result.outputs == {
        "decision": "approved",
        "approved": True,
        "comment": "Ready to run",
        "submitted_by": str(submitter_id),
    }


@pytest.mark.asyncio
async def test_pause_executor_rejects_approval_submission(monkeypatch):
    submitter_id = uuid4()
    request = SimpleNamespace(
        status=PauseRequestStatus.SUBMITTED,
        values={"decision": "rejected"},
        comment="Amount too high",
        submitted_by_id=submitter_id,
    )
    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=_query(request))
    )

    result = await PauseNodeExecutor().execute(
        _node("approval"),
        SimpleNamespace(),
        SimpleNamespace(id=uuid4(), workflow_id=uuid4()),
    )

    assert result.waiting is False
    assert result.error == "workflow_approval_rejected"
    assert result.outputs == {
        "decision": "rejected",
        "comment": "Amount too high",
        "approved": False,
        "submitted_by": str(submitter_id),
    }


def test_pause_executor_declares_mode_specific_outputs():
    executor = PauseNodeExecutor()

    assert executor.get_output_variables(_node()["data"]["config"]) == [
        {
            "name": "target_price",
            "type": "number",
            "description": "Approved price",
        }
    ]
    assert [
        item["name"]
        for item in executor.get_output_variables(_node("approval")["data"]["config"])
    ] == [
        "decision",
        "approved",
        "comment",
        "submitted_by",
    ]


@pytest.mark.asyncio
async def test_pause_executor_resolves_description_before_persisting(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    request_query = _query(None)
    execution_query = _query(SimpleNamespace(id=uuid4()))
    create = AsyncMock()
    notify = AsyncMock()
    node = {
        "id": "pause-1",
        "data": {
            "pauseConfig": {
                "mode": "approval",
                "title": "审批",
                "description": "请审核报价 {{start.price}}",
            }
        },
    }
    context = SimpleNamespace(resolve_template=AsyncMock(return_value="请审核报价 42"))

    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=request_query)
    )
    monkeypatch.setattr(pause_module.WorkflowPauseRequest, "create", create)
    monkeypatch.setattr(
        pause_module.NodeExecution, "filter", Mock(return_value=execution_query)
    )
    monkeypatch.setattr(pause_module, "notify_pause_pending", notify)

    result = await PauseNodeExecutor().execute(node, context, run)

    assert result.waiting is True
    create.assert_awaited_once()
    assert create.await_args.kwargs["description"] == "请审核报价 42"
    notify.assert_awaited_once()
    assert notify.await_args.kwargs["description"] == "请审核报价 42"


@pytest.mark.asyncio
async def test_pause_executor_stores_empty_resolution_as_is(monkeypatch):
    run = SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    request_query = _query(None)
    execution_query = _query(SimpleNamespace(id=uuid4()))
    create = AsyncMock()
    notify = AsyncMock()
    node = {
        "id": "pause-1",
        "data": {
            "pauseConfig": {
                "mode": "approval",
                "description": "{{start.price}}",
            }
        },
    }
    # 引用值不可用 → 解析结果为空串：按解析结果存储，不泄漏 {{var}} 原文
    context = SimpleNamespace(resolve_template=AsyncMock(return_value=""))

    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=request_query)
    )
    monkeypatch.setattr(pause_module.WorkflowPauseRequest, "create", create)
    monkeypatch.setattr(
        pause_module.NodeExecution, "filter", Mock(return_value=execution_query)
    )
    monkeypatch.setattr(pause_module, "notify_pause_pending", notify)

    result = await PauseNodeExecutor().execute(node, context, run)

    assert result.waiting is True
    assert create.await_args.kwargs["description"] == ""
    assert notify.await_args.kwargs["description"] == ""


@pytest.mark.asyncio
async def test_pause_executor_falls_back_to_raw_description_on_resolve_failure(
    monkeypatch,
):
    run = SimpleNamespace(id=uuid4(), workflow_id=uuid4())
    request_query = _query(None)
    execution_query = _query(SimpleNamespace(id=uuid4()))
    create = AsyncMock()
    notify = AsyncMock()
    node = {
        "id": "pause-1",
        "data": {
            "pauseConfig": {
                "mode": "approval",
                "description": "请审核 {{start.price}}",
            }
        },
    }
    context = SimpleNamespace(
        resolve_template=AsyncMock(side_effect=RuntimeError("variable missing"))
    )

    monkeypatch.setattr(
        pause_module.WorkflowPauseRequest, "filter", Mock(return_value=request_query)
    )
    monkeypatch.setattr(pause_module.WorkflowPauseRequest, "create", create)
    monkeypatch.setattr(
        pause_module.NodeExecution, "filter", Mock(return_value=execution_query)
    )
    monkeypatch.setattr(pause_module, "notify_pause_pending", notify)

    result = await PauseNodeExecutor().execute(node, context, run)

    assert result.waiting is True
    assert create.await_args.kwargs["description"] == "请审核 {{start.price}}"
    assert notify.await_args.kwargs["description"] == "请审核 {{start.price}}"
