from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from app.models.workflow import RunStatus
from app.tasks.workflow import cancel_workflow_task, run_workflow_task

RUN_ID = "11111111-1111-1111-1111-111111111111"
WORKFLOW_ID = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"
TEAM_ID = "44444444-4444-4444-4444-444444444444"


def test_run_workflow_task_returns_outputs_after_success():
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(return_value=UUID(RUN_ID))
    run = SimpleNamespace(outputs={"answer": "done"})

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch("app.tasks.workflow.WorkflowRun") as workflow_run,
    ):
        workflow_run.filter.return_value.first = AsyncMock(return_value=run)
        result = run_workflow_task.run(
            RUN_ID,
            WORKFLOW_ID,
            {"question": "hello"},
            USER_ID,
            TEAM_ID,
            True,
        )

    assert result == {
        "status": "success",
        "run_id": UUID(RUN_ID),
        "outputs": {"answer": "done"},
    }
    orchestrator.run_with_run_id.assert_awaited_once_with(
        run_id=UUID(RUN_ID),
        workflow_id=UUID(WORKFLOW_ID),
        inputs={"question": "hello"},
        user_id=UUID(USER_ID),
        team_id=UUID(TEAM_ID),
        stream=True,
        is_debug=True,
    )


def test_run_workflow_task_reports_missing_final_run():
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(return_value=UUID(RUN_ID))

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch("app.tasks.workflow.WorkflowRun") as workflow_run,
        patch(
            "app.tasks.workflow.get_default_language",
            new=AsyncMock(return_value="en"),
        ),
        patch("app.tasks.workflow.t", return_value="run missing") as translate,
    ):
        workflow_run.filter.return_value.first = AsyncMock(return_value=None)
        result = run_workflow_task.run(RUN_ID, WORKFLOW_ID, {}, None)

    assert result == {"status": "error", "message": "run missing"}
    translate.assert_called_once_with(
        "workflow_run_not_found_after_execution", lang="en"
    )


def test_run_workflow_task_marks_run_failed_on_execution_error():
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(side_effect=RuntimeError("internal"))
    run = SimpleNamespace(status=None, error_message=None, save=AsyncMock())

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch("app.tasks.workflow.WorkflowRun") as workflow_run,
        patch(
            "app.tasks.workflow.translate_public_workflow_error",
            return_value="safe error",
        ),
    ):
        workflow_run.filter.return_value.first = AsyncMock(return_value=run)
        result = run_workflow_task.run(RUN_ID, WORKFLOW_ID, {}, None)

    assert result == {"status": "error", "message": "safe error"}
    assert run.status == RunStatus.FAILED
    assert run.error_message == "safe error"
    run.save.assert_awaited_once_with()


def test_run_workflow_task_creates_an_event_loop_when_none_is_available():
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(return_value=UUID(RUN_ID))
    run = SimpleNamespace(outputs={})
    loop = MagicMock()
    loop.run_until_complete.side_effect = lambda coroutine: (
        coroutine.close() or {"status": "success"}
    )

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch("app.tasks.workflow.WorkflowRun") as workflow_run,
        patch("asyncio.get_event_loop", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        workflow_run.filter.return_value.first = AsyncMock(return_value=run)
        assert run_workflow_task.run(RUN_ID, WORKFLOW_ID, {}, None) == {
            "status": "success"
        }

    set_event_loop.assert_called_once_with(loop)


def test_cancel_workflow_task_creates_an_event_loop_when_none_is_available():
    loop = MagicMock()
    loop.run_until_complete.side_effect = lambda coroutine: (
        coroutine.close() or {"status": "success"}
    )

    with (
        patch("asyncio.get_event_loop", side_effect=RuntimeError),
        patch("asyncio.new_event_loop", return_value=loop),
        patch("asyncio.set_event_loop") as set_event_loop,
    ):
        assert cancel_workflow_task.run(RUN_ID) == {"status": "success"}

    set_event_loop.assert_called_once_with(loop)


def test_cancel_workflow_task_returns_or_translates_result():
    orchestrator = MagicMock()
    orchestrator.cancel = AsyncMock(return_value=True)

    with patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator):
        assert cancel_workflow_task.run(RUN_ID) == {
            "status": "success",
            "cancelled": True,
        }

    orchestrator.cancel = AsyncMock(side_effect=RuntimeError("internal"))
    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.tasks.workflow.translate_public_workflow_error",
            return_value="safe error",
        ),
    ):
        assert cancel_workflow_task.run(RUN_ID) == {
            "status": "error",
            "message": "safe error",
        }
