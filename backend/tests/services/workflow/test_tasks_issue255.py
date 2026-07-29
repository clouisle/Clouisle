from datetime import UTC, datetime, timedelta
import sys
from types import ModuleType, SimpleNamespace
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


def test_execute_workflow_returns_completed_run():
    workflow_id = uuid4()
    user_id = uuid4()
    team_id = uuid4()
    result_run_id = str(uuid4())
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=result_run_id)

    with patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator):
        result = execute_workflow_task.run(
            str(workflow_id), {"query": "hello"}, str(user_id), str(team_id)
        )

    assert result == {"run_id": result_run_id, "status": "completed"}
    orchestrator.run.assert_awaited_once_with(
        workflow_id=workflow_id,
        inputs={"query": "hello"},
        user_id=user_id,
        team_id=team_id,
        stream=True,
    )


def test_execute_workflow_translates_failure():
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(side_effect=ValueError("private details"))

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.services.workflow.tasks.translate_public_workflow_error",
            return_value="safe error",
        ) as translate,
    ):
        result = execute_workflow_task.run(
            str(uuid4()), {}, str(uuid4()), run_id="existing-run"
        )

    assert result == {
        "run_id": "existing-run",
        "status": "failed",
        "error": "safe error",
    }
    translate.assert_called_once()


def test_execute_node_stops_when_run_is_cancelled():
    context = MagicMock()
    context.get_status = AsyncMock(return_value="cancelled")

    with patch(
        "app.services.workflow.ExecutionContext.load",
        new=AsyncMock(return_value=context),
    ):
        result = execute_node_task.run("run-1", "node-1", "llm", {})

    assert result == {"node_id": "node-1", "status": "cancelled"}


@pytest.mark.parametrize("success", [True, False])
def test_execute_node_returns_executor_result_and_only_stores_success(success):
    context = MagicMock()
    context.get_status = AsyncMock(return_value="running")
    context.set_node_outputs = AsyncMock()
    run = object()
    execution_result = SimpleNamespace(
        success=success,
        outputs={"answer": "ok"},
        error=None if success else "failed",
        next_handles=["next"],
    )
    executor = MagicMock()
    executor.execute = AsyncMock(return_value=execution_result)
    query = MagicMock()
    query.first = AsyncMock(return_value=run)

    with (
        patch(
            "app.services.workflow.ExecutionContext.load",
            new=AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.NodeExecutorRegistry.get", return_value=executor),
        patch("app.models.workflow.WorkflowRun.filter", return_value=query),
    ):
        result = execute_node_task.run("run-1", "node-1", "llm", {"prompt": "hello"})

    assert result == {
        "node_id": "node-1",
        "status": "success" if success else "error",
        "outputs": {"answer": "ok"},
        "error": None if success else "failed",
        "next_handles": ["next"],
    }
    executor.execute.assert_awaited_once_with(
        node={"id": "node-1", "data": {"prompt": "hello"}},
        context=context,
        run=run,
    )
    if success:
        context.set_node_outputs.assert_awaited_once_with("node-1", {"answer": "ok"})
    else:
        context.set_node_outputs.assert_not_awaited()


def test_execute_node_reports_missing_run():
    context = MagicMock()
    context.get_status = AsyncMock(return_value="running")
    query = MagicMock()
    query.first = AsyncMock(return_value=None)

    with (
        patch(
            "app.services.workflow.ExecutionContext.load",
            new=AsyncMock(return_value=context),
        ),
        patch("app.services.workflow.NodeExecutorRegistry.get"),
        patch("app.models.workflow.WorkflowRun.filter", return_value=query),
        patch("app.services.workflow.tasks.t", return_value="run not found"),
    ):
        result = execute_node_task.run("missing", "node-1", "llm", {})

    assert result == {
        "node_id": "node-1",
        "status": "error",
        "error": "run not found",
    }


def test_execute_stage_fans_out_nodes_and_collects_results():
    signatures = [object(), object()]
    async_result = MagicMock()
    async_result.get.return_value = [{"status": "success"}, {"status": "error"}]
    job = MagicMock()
    job.apply_async.return_value = async_result

    with (
        patch(
            "app.services.workflow.tasks.execute_node_task.s",
            side_effect=signatures,
        ) as signature,
        patch("app.services.workflow.tasks.group", return_value=job) as task_group,
    ):
        result = execute_stage_task.run(
            "run-1",
            2,
            ["first", "second"],
            {"first": {"data": {"type": "llm"}}},
        )

    assert result == {
        "stage_index": 2,
        "results": [{"status": "success"}, {"status": "error"}],
    }
    assert signature.call_args_list[0].args == (
        "run-1",
        "first",
        "llm",
        {"data": {"type": "llm"}},
    )
    assert signature.call_args_list[1].args == ("run-1", "second", "unknown", {})
    task_group.assert_called_once_with(signatures)
    async_result.get.assert_called_once_with(timeout=300)


def test_cancel_and_cleanup_delegate_to_workflow_services():
    orchestrator = MagicMock()
    orchestrator.cancel = AsyncMock(return_value=True)
    context = MagicMock()
    context.set_ttl = AsyncMock()

    with patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator):
        assert cancel_workflow_task.run("run-1") == {
            "run_id": "run-1",
            "cancelled": True,
        }

    with patch(
        "app.services.workflow.ExecutionContext.load",
        new=AsyncMock(return_value=context),
    ):
        assert cleanup_workflow_task.run("run-1", 90) == {
            "run_id": "run-1",
            "cleaned": True,
        }

    orchestrator.cancel.assert_awaited_once_with("run-1")
    context.set_ttl.assert_awaited_once_with(90)


def test_check_scheduled_workflows_skips_invalid_and_triggers_current_cron():
    due = SimpleNamespace(
        id=uuid4(),
        name="due",
        trigger_config={"cron": "* * * * *"},
        created_by_id=uuid4(),
        team_id=uuid4(),
    )
    missing = SimpleNamespace(id=uuid4(), trigger_config={})
    invalid = SimpleNamespace(
        id=uuid4(), name="invalid", trigger_config={"cron": "invalid"}
    )
    query = MagicMock()
    query.all = AsyncMock(return_value=[missing, invalid, due])
    croniter_module = ModuleType("croniter")

    def croniter(expression, now):
        if expression == "invalid":
            raise ValueError("invalid cron")
        return SimpleNamespace(get_prev=lambda _: now - timedelta(seconds=30))

    croniter_module.croniter = croniter

    with (
        patch.dict(sys.modules, {"croniter": croniter_module}),
        patch("app.models.workflow.Workflow.filter", return_value=query),
        patch("app.services.workflow.tasks.execute_workflow_task.delay") as delay,
    ):
        result = check_scheduled_workflows.run()

    assert result == {"triggered": 1}
    delay.assert_called_once_with(
        workflow_id=str(due.id),
        inputs={},
        user_id=str(due.created_by_id),
        team_id=str(due.team_id),
    )


def test_cleanup_old_runs_deletes_before_cutoff():
    query = MagicMock()
    query.delete = AsyncMock(return_value=4)

    with patch("app.models.workflow.WorkflowRun.filter", return_value=query) as filter_:
        result = cleanup_old_runs.run(days=7)

    assert result == {"deleted": 4}
    cutoff = filter_.call_args.kwargs["created_at__lt"]
    assert datetime.now(UTC) - timedelta(days=7, seconds=1) < cutoff
    assert cutoff < datetime.now(UTC) - timedelta(days=7) + timedelta(seconds=1)
