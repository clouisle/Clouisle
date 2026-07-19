from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow.tasks import (
    cancel_workflow_task,
    check_scheduled_workflows,
    cleanup_old_runs,
    cleanup_workflow_task,
    execute_node_task,
    execute_stage_task,
    execute_workflow_task,
)


def test_execute_workflow_success_converts_ids_and_preserves_inputs():
    workflow_id, user_id, team_id = uuid4(), uuid4(), uuid4()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value="run-1")

    with patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator):
        result = execute_workflow_task.run(
            str(workflow_id), {"query": "hello"}, str(user_id), str(team_id)
        )

    assert result == {"run_id": "run-1", "status": "completed"}
    orchestrator.run.assert_awaited_once_with(
        workflow_id=workflow_id,
        inputs={"query": "hello"},
        user_id=user_id,
        team_id=team_id,
        stream=True,
    )


def test_execute_workflow_returns_public_error_and_requested_run_id():
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(side_effect=RuntimeError("private"))

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.services.workflow.tasks.translate_public_workflow_error",
            return_value="safe error",
        ),
    ):
        result = execute_workflow_task.run(
            str(uuid4()), {}, str(uuid4()), run_id="run-1"
        )

    assert result == {"run_id": "run-1", "status": "failed", "error": "safe error"}


@pytest.mark.parametrize(
    ("status", "run", "execution_result", "expected"),
    [
        ("cancelled", None, None, {"node_id": "node-1", "status": "cancelled"}),
        (
            "running",
            None,
            None,
            {"node_id": "node-1", "status": "error", "error": "missing run"},
        ),
        (
            "running",
            SimpleNamespace(id="run-1"),
            SimpleNamespace(
                success=True,
                outputs={"answer": 42},
                error=None,
                next_handles=["next"],
            ),
            {
                "node_id": "node-1",
                "status": "success",
                "outputs": {"answer": 42},
                "error": None,
                "next_handles": ["next"],
            },
        ),
        (
            "running",
            SimpleNamespace(id="run-1"),
            SimpleNamespace(
                success=False,
                outputs={},
                error="bad input",
                next_handles=[],
            ),
            {
                "node_id": "node-1",
                "status": "error",
                "outputs": {},
                "error": "bad input",
                "next_handles": [],
            },
        ),
    ],
)
def test_execute_node_branches(status, run, execution_result, expected):
    context = MagicMock()
    context.get_status = AsyncMock(return_value=status)
    context.set_node_outputs = AsyncMock()
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=execution_result)
    run_query = MagicMock()
    run_query.first = AsyncMock(return_value=run)

    with (
        patch(
            "app.services.workflow.ExecutionContext.load",
            AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.NodeExecutorRegistry.get", return_value=executor),
        patch("app.models.workflow.WorkflowRun.filter", return_value=run_query),
        patch("app.services.workflow.tasks.t", return_value="missing run"),
    ):
        result = execute_node_task.run("run-1", "node-1", "code", {"code": "1"})

    assert result == expected
    if execution_result and execution_result.success:
        context.set_node_outputs.assert_awaited_once_with("node-1", {"answer": 42})
    else:
        context.set_node_outputs.assert_not_awaited()


def test_execute_node_retries_unexpected_errors():
    error = RuntimeError("redis unavailable")
    retry_error = RuntimeError("retry requested")

    with (
        patch(
            "app.services.workflow.ExecutionContext.load", AsyncMock(side_effect=error)
        ),
        patch.object(execute_node_task, "retry", side_effect=retry_error) as retry,
        pytest.raises(RuntimeError, match="retry requested"),
    ):
        execute_node_task.run("run-1", "node-1", "code", {})

    retry.assert_called_once_with(exc=error)


def test_execute_stage_builds_parallel_signatures_and_returns_results():
    signatures = [object(), object()]
    async_result = MagicMock()
    async_result.get.return_value = [{"status": "success"}, {"status": "error"}]
    job = MagicMock()
    job.apply_async.return_value = async_result

    with (
        patch.object(execute_node_task, "s", side_effect=signatures) as signature,
        patch("app.services.workflow.tasks.group", return_value=job) as task_group,
    ):
        result = execute_stage_task.run(
            "run-1",
            2,
            ["known", "missing"],
            {"known": {"data": {"type": "llm"}}},
        )

    assert result == {
        "stage_index": 2,
        "results": [{"status": "success"}, {"status": "error"}],
    }
    assert signature.call_args_list[0].args == (
        "run-1",
        "known",
        "llm",
        {"data": {"type": "llm"}},
    )
    assert signature.call_args_list[1].args == ("run-1", "missing", "unknown", {})
    task_group.assert_called_once_with(signatures)
    async_result.get.assert_called_once_with(timeout=300)


def test_cancel_and_cleanup_delegate_to_workflow_services():
    orchestrator = MagicMock()
    orchestrator.cancel = AsyncMock(return_value=True)
    context = MagicMock()
    context.set_ttl = AsyncMock()

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.services.workflow.ExecutionContext.load",
            AsyncMock(return_value=context),
        ),
    ):
        assert cancel_workflow_task.run("run-1") == {
            "run_id": "run-1",
            "cancelled": True,
        }
        assert cleanup_workflow_task.run("run-1", 15) == {
            "run_id": "run-1",
            "cleaned": True,
        }

    orchestrator.cancel.assert_awaited_once_with("run-1")
    context.set_ttl.assert_awaited_once_with(15)


def test_check_scheduled_workflows_skips_invalid_and_triggers_current_cron():
    workflows = [
        SimpleNamespace(id="no-cron", trigger_config={}, name="No cron"),
        SimpleNamespace(id="invalid", trigger_config={"cron": "bad"}, name="Invalid"),
        SimpleNamespace(id="stale", trigger_config={"cron": "stale"}, name="Stale"),
        SimpleNamespace(
            id=uuid4(),
            trigger_config={"cron": "current"},
            name="Current",
            created_by_id=uuid4(),
            team_id=uuid4(),
        ),
    ]
    query = MagicMock()
    query.all = AsyncMock(return_value=workflows)

    def cron(expr, now):
        if expr == "bad":
            raise ValueError("invalid cron")
        age = 61 if expr == "stale" else 30
        return SimpleNamespace(get_prev=lambda _: now - timedelta(seconds=age))

    with (
        patch("app.models.workflow.Workflow.filter", return_value=query),
        patch.dict("sys.modules", {"croniter": SimpleNamespace(croniter=cron)}),
        patch.object(execute_workflow_task, "delay") as delay,
    ):
        result = check_scheduled_workflows.run()

    assert result == {"triggered": 1}
    current = workflows[-1]
    delay.assert_called_once_with(
        workflow_id=str(current.id),
        inputs={},
        user_id=str(current.created_by_id),
        team_id=str(current.team_id),
    )


def test_cleanup_old_runs_uses_requested_retention_window():
    query = MagicMock()
    query.delete = AsyncMock(return_value=7)

    with patch(
        "app.models.workflow.WorkflowRun.filter", return_value=query
    ) as filter_runs:
        before = datetime.utcnow()
        result = cleanup_old_runs.run(10)
        after = datetime.utcnow()

    assert result == {"deleted": 7}
    cutoff = filter_runs.call_args.kwargs["created_at__lt"]
    assert before - timedelta(days=10) <= cutoff <= after - timedelta(days=10)
