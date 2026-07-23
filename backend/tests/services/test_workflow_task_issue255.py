from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.workflow import RunStatus
from app.tasks.workflow import cancel_workflow_task, run_workflow_task


RUN_ID = "11111111-1111-1111-1111-111111111111"
WORKFLOW_ID = "22222222-2222-2222-2222-222222222222"
USER_ID = "33333333-3333-3333-3333-333333333333"
TEAM_ID = "44444444-4444-4444-4444-444444444444"


def workflow_run_query(run):
    query = MagicMock()
    query.first = AsyncMock(return_value=run)
    return query


def test_run_workflow_task_returns_completed_outputs():
    run = MagicMock(outputs={"answer": 42})
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(return_value=UUID(RUN_ID))

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.tasks.workflow.WorkflowRun.filter",
            return_value=workflow_run_query(run),
        ),
    ):
        result = run_workflow_task.run(
            RUN_ID, WORKFLOW_ID, {"question": "meaning"}, USER_ID, TEAM_ID, True
        )

    assert result == {
        "status": "success",
        "run_id": UUID(RUN_ID),
        "outputs": {"answer": 42},
    }
    orchestrator.run_with_run_id.assert_awaited_once_with(
        run_id=UUID(RUN_ID),
        workflow_id=UUID(WORKFLOW_ID),
        inputs={"question": "meaning"},
        user_id=UUID(USER_ID),
        team_id=UUID(TEAM_ID),
        stream=True,
        is_debug=True,
    )


def test_run_workflow_task_localizes_missing_final_run():
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(return_value=UUID(RUN_ID))

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.tasks.workflow.WorkflowRun.filter",
            return_value=workflow_run_query(None),
        ),
        patch(
            "app.tasks.workflow.get_default_language",
            new=AsyncMock(return_value="zh"),
        ),
        patch("app.tasks.workflow.t", return_value="未找到运行记录") as translate,
    ):
        result = run_workflow_task.run(RUN_ID, WORKFLOW_ID, {}, None)

    assert result == {"status": "error", "message": "未找到运行记录"}
    translate.assert_called_once_with(
        "workflow_run_not_found_after_execution", lang="zh"
    )


def test_run_workflow_task_persists_public_failure():
    run = MagicMock()
    run.save = AsyncMock()
    orchestrator = MagicMock()
    orchestrator.run_with_run_id = AsyncMock(
        side_effect=RuntimeError("provider secret")
    )

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.tasks.workflow.WorkflowRun.filter",
            return_value=workflow_run_query(run),
        ),
        patch(
            "app.tasks.workflow.translate_public_workflow_error",
            return_value="workflow_execution_error",
        ),
    ):
        result = run_workflow_task.run(RUN_ID, WORKFLOW_ID, {}, None)

    assert result == {"status": "error", "message": "workflow_execution_error"}
    assert run.status == RunStatus.FAILED
    assert run.error_message == "workflow_execution_error"
    run.save.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, {"status": "success", "cancelled": True}),
        (RuntimeError("cancel failed"), {"status": "error", "message": "public error"}),
    ],
)
def test_cancel_workflow_task_handles_result_and_error(error, expected):
    orchestrator = MagicMock()
    orchestrator.cancel = AsyncMock(return_value=True, side_effect=error)

    with (
        patch("app.services.workflow.WorkflowOrchestrator", return_value=orchestrator),
        patch(
            "app.tasks.workflow.translate_public_workflow_error",
            return_value="public error",
        ),
    ):
        result = cancel_workflow_task.run(RUN_ID)

    assert result == expected
    orchestrator.cancel.assert_awaited_once_with(RUN_ID)
