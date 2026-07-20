from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.workflow.errors import (
    ExecutionCancelledError,
    ExecutionTimeoutError,
    MaxDepthExceededError,
)
from app.services.workflow.executors.subworkflow import (
    MAX_DEPTH,
    SubWorkflowNodeExecutor,
)


def subworkflow_node(workflow_id: str, **config):
    return {
        "id": "sub_1",
        "data": {
            "subWorkflowConfig": {
                "workflowId": workflow_id,
                "inputMappings": [
                    {
                        "name": "query",
                        "source": "variable",
                        "variableRef": "start.query",
                    },
                    {"name": "limit", "source": "constant", "constantValue": 3},
                ],
                **config,
            }
        },
    }


@pytest.mark.asyncio
async def test_execute_maps_inputs_outputs_and_persists_parent_metadata():
    workflow_id = str(uuid4())
    parent_id = uuid4()
    sub_run_id = uuid4()
    user_id = uuid4()
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value="hello")
    parent_run = SimpleNamespace(
        id=parent_id,
        root_run_id=None,
        depth=1,
        triggered_by_id=user_id,
    )
    sub_run = SimpleNamespace(
        status="success",
        outputs={"answer": "world"},
        parent_run_id=None,
        root_run_id=None,
        depth=0,
        save=AsyncMock(),
    )

    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.workflow.WorkflowRun.filter") as run_filter,
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator.run",
            new=AsyncMock(return_value=str(sub_run_id)),
        ) as run_subworkflow,
    ):
        workflow_filter.return_value.first = AsyncMock(return_value=SimpleNamespace())
        run_filter.return_value.first = AsyncMock(return_value=sub_run)

        result = await SubWorkflowNodeExecutor().execute(
            subworkflow_node(workflow_id, outputVariable="nested", timeout=12),
            context,
            parent_run,
        )

    assert result.outputs == {
        "nested": {"answer": "world"},
        "_sub_run_id": str(sub_run_id),
    }
    run_subworkflow.assert_awaited_once_with(
        workflow_id=UUID(workflow_id),
        inputs={"query": "hello", "limit": 3},
        user_id=user_id,
        team_id=None,
        stream=False,
    )
    assert (sub_run.parent_run_id, sub_run.root_run_id, sub_run.depth) == (
        parent_id,
        parent_id,
        2,
    )
    sub_run.save.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("node", "run", "expected_error"),
    [
        (
            {"data": {"subWorkflowConfig": {}}},
            SimpleNamespace(depth=0),
            "validation_error",
        ),
        (
            subworkflow_node(str(uuid4())),
            SimpleNamespace(depth=0, triggered_by_id=None),
            "validation_error",
        ),
    ],
)
async def test_execute_rejects_invalid_configuration_or_trigger(
    node, run, expected_error
):
    with patch("app.models.workflow.Workflow.filter") as workflow_filter:
        workflow_filter.return_value.first = AsyncMock(return_value=SimpleNamespace())
        result = await SubWorkflowNodeExecutor().execute(
            node,
            MagicMock(resolve_variable_ref=AsyncMock(return_value="hello")),
            run,
        )

    assert result.error == expected_error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workflow_exists", "sub_run_exists", "expected_error"),
    [
        (False, True, "workflow_not_found"),
        (True, False, "workflow_run_not_found"),
    ],
)
async def test_execute_handles_missing_workflow_records(
    workflow_exists, sub_run_exists, expected_error
):
    workflow_id = str(uuid4())
    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.workflow.WorkflowRun.filter") as run_filter,
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator.run",
            new=AsyncMock(return_value=str(uuid4())),
        ),
    ):
        workflow_filter.return_value.first = AsyncMock(
            return_value=SimpleNamespace() if workflow_exists else None
        )
        run_filter.return_value.first = AsyncMock(
            return_value=SimpleNamespace() if sub_run_exists else None
        )
        result = await SubWorkflowNodeExecutor().execute(
            subworkflow_node(workflow_id),
            MagicMock(resolve_variable_ref=AsyncMock(return_value="hello")),
            SimpleNamespace(depth=0, triggered_by_id=uuid4()),
        )

    assert result.error == expected_error


@pytest.mark.asyncio
async def test_execute_enforces_maximum_nesting_depth_before_external_calls():
    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        pytest.raises(MaxDepthExceededError),
    ):
        await SubWorkflowNodeExecutor().execute(
            subworkflow_node(str(uuid4())),
            MagicMock(),
            SimpleNamespace(depth=MAX_DEPTH),
        )

    workflow_filter.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_error"),
    [
        (ExecutionTimeoutError(5), "request_timeout"),
        (ExecutionCancelledError(), "workflow_run_cancelled"),
        (RuntimeError("provider secret"), "workflow_execution_error"),
    ],
)
async def test_execute_translates_orchestrator_failures(failure, expected_error):
    workflow_id = str(uuid4())
    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator.run",
            new=AsyncMock(side_effect=failure),
        ),
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value=expected_error,
        ),
    ):
        workflow_filter.return_value.first = AsyncMock(return_value=SimpleNamespace())
        result = await SubWorkflowNodeExecutor().execute(
            subworkflow_node(workflow_id),
            MagicMock(resolve_variable_ref=AsyncMock(return_value="hello")),
            SimpleNamespace(depth=0, triggered_by_id=uuid4()),
        )

    assert result.error == expected_error


@pytest.mark.asyncio
async def test_execute_returns_failed_sub_run_details_when_failure_is_allowed():
    workflow_id = str(uuid4())
    sub_run_id = uuid4()
    sub_run = SimpleNamespace(
        status="failed",
        error_message="provider secret",
        outputs=None,
        parent_run_id=None,
        root_run_id=None,
        depth=0,
        save=AsyncMock(),
    )

    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.workflow.WorkflowRun.filter") as run_filter,
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator.run",
            new=AsyncMock(return_value=str(sub_run_id)),
        ),
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value="workflow_execution_error",
        ),
    ):
        workflow_filter.return_value.first = AsyncMock(return_value=SimpleNamespace())
        run_filter.return_value.first = AsyncMock(return_value=sub_run)
        result = await SubWorkflowNodeExecutor().execute(
            subworkflow_node(workflow_id, failOnError=False),
            MagicMock(resolve_variable_ref=AsyncMock(return_value="hello")),
            SimpleNamespace(
                id=uuid4(), root_run_id=uuid4(), depth=0, triggered_by_id=uuid4()
            ),
        )

    assert result.outputs == {
        "_status": "failed",
        "_error": "workflow_execution_error",
        "_sub_run_id": str(sub_run_id),
    }
    sub_run.save.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected_outputs"),
    [
        (
            {"outputVariable": "", "outputMapping": {"local": "answer"}},
            {"local": "world"},
        ),
        ({"outputVariable": ""}, {"answer": "world"}),
    ],
)
async def test_execute_supports_legacy_and_passthrough_outputs(
    config, expected_outputs
):
    workflow_id = str(uuid4())
    sub_run_id = uuid4()
    sub_run = SimpleNamespace(
        status="success",
        outputs={"answer": "world"},
        parent_run_id=None,
        root_run_id=None,
        depth=0,
        save=AsyncMock(),
    )
    with (
        patch("app.models.workflow.Workflow.filter") as workflow_filter,
        patch("app.models.workflow.WorkflowRun.filter") as run_filter,
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator.run",
            new=AsyncMock(return_value=str(sub_run_id)),
        ),
    ):
        workflow_filter.return_value.first = AsyncMock(return_value=SimpleNamespace())
        run_filter.return_value.first = AsyncMock(return_value=sub_run)
        result = await SubWorkflowNodeExecutor().execute(
            subworkflow_node(workflow_id, **config),
            MagicMock(resolve_variable_ref=AsyncMock(return_value="hello")),
            SimpleNamespace(
                id=uuid4(), root_run_id=None, depth=0, triggered_by_id=uuid4()
            ),
        )

    assert result.outputs == {"_sub_run_id": str(sub_run_id), **expected_outputs}
