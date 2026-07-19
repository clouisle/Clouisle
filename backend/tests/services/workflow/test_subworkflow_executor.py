"""Behavioral tests for the sub-workflow node executor."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.workflow.errors import MaxDepthExceededError
from app.services.workflow.executors.subworkflow import (
    MAX_DEPTH,
    SubWorkflowNodeExecutor,
)


@pytest.fixture
def executor():
    return SubWorkflowNodeExecutor()


@pytest.fixture
def context():
    value = MagicMock()
    value.resolve_variable_ref = AsyncMock(return_value="resolved")
    return value


@pytest.fixture
def parent_run():
    value = MagicMock()
    value.id = uuid4()
    value.root_run_id = None
    value.depth = 2
    value.triggered_by_id = uuid4()
    return value


def node(workflow_id, **config):
    return {
        "data": {
            "subWorkflowConfig": {
                "workflowId": str(workflow_id),
                **config,
            }
        }
    }


def query_returning(value):
    query = MagicMock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.asyncio
async def test_execute_rejects_missing_workflow_id(executor, context, parent_run):
    result = await executor.execute({"data": {}}, context, parent_run)

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_execute_enforces_maximum_depth(executor, context, parent_run):
    parent_run.depth = MAX_DEPTH

    with pytest.raises(MaxDepthExceededError) as exc_info:
        await executor.execute(node(uuid4()), context, parent_run)

    assert exc_info.value.current_depth == MAX_DEPTH


@pytest.mark.asyncio
async def test_execute_reports_unknown_workflow(executor, context, parent_run):
    with patch(
        "app.models.workflow.Workflow.filter", return_value=query_returning(None)
    ):
        result = await executor.execute(node(uuid4()), context, parent_run)

    assert result.error == "workflow_not_found"


@pytest.mark.asyncio
async def test_execute_runs_child_and_persists_lineage(executor, context, parent_run):
    workflow_id = uuid4()
    sub_run_id = uuid4()
    sub_run = MagicMock(status="success", outputs={"answer": "done"})
    sub_run.save = AsyncMock()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=str(sub_run_id))

    config = node(
        workflow_id,
        timeout=17,
        inputMappings=[
            {"name": "query", "source": "variable", "variableRef": "start.query"},
            {"name": "limit", "source": "constant", "constantValue": 3},
            {"name": "", "source": "constant", "constantValue": "ignored"},
        ],
        outputVariable="child",
    )
    with (
        patch(
            "app.models.workflow.Workflow.filter",
            return_value=query_returning(MagicMock()),
        ),
        patch(
            "app.models.workflow.WorkflowRun.filter",
            return_value=query_returning(sub_run),
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator",
            return_value=orchestrator,
        ) as orchestrator_class,
    ):
        result = await executor.execute(config, context, parent_run)

    orchestrator_class.assert_called_once_with(timeout=17)
    orchestrator.run.assert_awaited_once_with(
        workflow_id=workflow_id,
        inputs={"query": "resolved", "limit": 3},
        user_id=parent_run.triggered_by_id,
        team_id=None,
        stream=False,
    )
    context.resolve_variable_ref.assert_awaited_once_with("start.query")
    assert result.outputs == {
        "child": {"answer": "done"},
        "_sub_run_id": str(sub_run_id),
    }
    assert sub_run.parent_run_id == parent_run.id
    assert sub_run.root_run_id == parent_run.id
    assert sub_run.depth == 3
    sub_run.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {"outputVariable": "", "outputMapping": {"local": "remote"}},
            {"local": 7, "_sub_run_id": "SUB_RUN_ID"},
        ),
        (
            {"outputVariable": ""},
            {"remote": 7, "_sub_run_id": "SUB_RUN_ID"},
        ),
    ],
)
async def test_execute_supports_legacy_output_modes(
    executor, context, parent_run, config, expected
):
    workflow_id = uuid4()
    sub_run_id = uuid4()
    expected["_sub_run_id"] = str(sub_run_id)
    sub_run = MagicMock(status="success", outputs={"remote": 7})
    sub_run.save = AsyncMock()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=sub_run_id)

    with (
        patch(
            "app.models.workflow.Workflow.filter",
            return_value=query_returning(MagicMock()),
        ),
        patch(
            "app.models.workflow.WorkflowRun.filter",
            return_value=query_returning(sub_run),
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator",
            return_value=orchestrator,
        ),
    ):
        result = await executor.execute(
            node(workflow_id, **config), context, parent_run
        )

    assert result.outputs == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_error", [True, False])
async def test_execute_handles_failed_child_run(
    executor, context, parent_run, fail_on_error
):
    workflow_id = uuid4()
    sub_run_id = uuid4()
    sub_run = MagicMock(status="failed", error_message="private details")
    sub_run.save = AsyncMock()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=sub_run_id)

    with (
        patch(
            "app.models.workflow.Workflow.filter",
            return_value=query_returning(MagicMock()),
        ),
        patch(
            "app.models.workflow.WorkflowRun.filter",
            return_value=query_returning(sub_run),
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator",
            return_value=orchestrator,
        ),
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value="public error",
        ),
    ):
        result = await executor.execute(
            node(workflow_id, failOnError=fail_on_error), context, parent_run
        )

    if fail_on_error:
        assert result.error == "public error"
    else:
        assert result.outputs == {
            "_status": "failed",
            "_error": "public error",
            "_sub_run_id": str(sub_run_id),
        }


@pytest.mark.asyncio
async def test_execute_reports_missing_child_run(executor, context, parent_run):
    workflow_id = uuid4()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(return_value=uuid4())

    with (
        patch(
            "app.models.workflow.Workflow.filter",
            return_value=query_returning(MagicMock()),
        ),
        patch(
            "app.models.workflow.WorkflowRun.filter", return_value=query_returning(None)
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator",
            return_value=orchestrator,
        ),
    ):
        result = await executor.execute(node(workflow_id), context, parent_run)

    assert result.error == "workflow_run_not_found"


@pytest.mark.asyncio
async def test_execute_returns_error_outputs_when_orchestration_raises(
    executor, context, parent_run
):
    workflow_id = uuid4()
    orchestrator = MagicMock()
    orchestrator.run = AsyncMock(side_effect=RuntimeError("private details"))

    with (
        patch(
            "app.models.workflow.Workflow.filter",
            return_value=query_returning(MagicMock()),
        ),
        patch(
            "app.services.workflow.orchestrator.WorkflowOrchestrator",
            return_value=orchestrator,
        ),
        patch(
            "app.services.workflow.executors.subworkflow.translate_public_workflow_error",
            return_value="public error",
        ),
    ):
        result = await executor.execute(
            node(workflow_id, failOnError=False), context, parent_run
        )

    assert result.outputs == {"_status": "error", "_error": "public error"}


@pytest.mark.asyncio
async def test_execute_requires_triggering_user(executor, context, parent_run):
    parent_run.triggered_by_id = None

    with patch(
        "app.models.workflow.Workflow.filter", return_value=query_returning(MagicMock())
    ):
        result = await executor.execute(node(uuid4()), context, parent_run)

    assert result.error == "validation_error"


@pytest.mark.asyncio
async def test_public_configuration_and_output_contract(executor):
    assert await executor.validate_config({}) == ["Sub-workflow ID is required"]
    assert await executor.validate_config({"workflowId": "id"}) == []
    assert executor.get_output_variables({}) == [{"name": "result", "type": "any"}]
    assert executor.get_output_variables({"outputMapping": {"local": "remote"}}) == [
        {"name": "local", "type": "any"}
    ]

    specs = executor.get_output_specs({"outputMapping": {"local": "remote"}})
    assert [(spec.name, spec.type.kind) for spec in specs] == [("local", "any")]
