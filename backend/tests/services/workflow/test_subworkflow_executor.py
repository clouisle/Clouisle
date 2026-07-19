import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest

from app.models.workflow import Workflow, WorkflowRun
from app.services.workflow.errors import MaxDepthExceededError
from app.services.workflow.executors import subworkflow
from app.services.workflow.executors.subworkflow import (
    MAX_DEPTH,
    SubWorkflowNodeExecutor,
)
from app.services.workflow.orchestrator import WorkflowOrchestrator


@pytest.fixture
def dependencies(monkeypatch):
    workflow_query = MagicMock()
    workflow_query.first = AsyncMock(return_value=SimpleNamespace())
    run_query = MagicMock()
    run_query.first = AsyncMock()
    run_child = AsyncMock(return_value=uuid4())

    monkeypatch.setattr(Workflow, "filter", MagicMock(return_value=workflow_query))
    monkeypatch.setattr(WorkflowRun, "filter", MagicMock(return_value=run_query))
    monkeypatch.setattr(WorkflowOrchestrator, "run", run_child)

    return workflow_query, run_query, run_child


def parent_run(**overrides):
    values = {
        "id": uuid4(),
        "root_run_id": None,
        "depth": 1,
        "triggered_by_id": uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def node(**config):
    return {"data": {"subWorkflowConfig": {"workflowId": str(uuid4()), **config}}}


@pytest.mark.asyncio
async def test_rejects_missing_workflow_and_depth_boundary():
    executor = SubWorkflowNodeExecutor()

    result = await executor.execute({"data": {"config": {}}}, MagicMock(), parent_run())
    assert result.error == "validation_error"

    with pytest.raises(MaxDepthExceededError):
        await executor.execute(node(), MagicMock(), parent_run(depth=MAX_DEPTH))


@pytest.mark.asyncio
async def test_returns_not_found_when_child_workflow_lookup_misses(dependencies):
    workflow_query, run_query, run_child = dependencies
    workflow_query.first.return_value = None
    workflow_id = str(uuid4())

    result = await SubWorkflowNodeExecutor().execute(
        node(workflowId=workflow_id), MagicMock(), parent_run()
    )

    assert result.error == "workflow_not_found"
    Workflow.filter.assert_called_once_with(id=workflow_id)
    run_child.assert_not_awaited()
    run_query.first.assert_not_awaited()


@pytest.mark.asyncio
async def test_maps_inputs_runs_child_and_wraps_outputs(dependencies):
    _, run_query, run_child = dependencies
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    child = SimpleNamespace(
        status="completed", outputs={"answer": "done"}, save=AsyncMock()
    )
    run_query.first.return_value = child
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(return_value="resolved")
    parent = parent_run()
    workflow_id = str(uuid4())

    result = await SubWorkflowNodeExecutor().execute(
        node(
            workflowId=workflow_id,
            timeout=12,
            inputMappings=[
                {"name": "query", "source": "variable", "variableRef": "start.q"},
                {"name": "limit", "source": "constant", "constantValue": 3},
                {"name": "ignored", "source": "unsupported"},
                {"source": "constant", "constantValue": "no name"},
            ],
            outputVariable="child",
        ),
        context,
        parent,
    )

    assert result.outputs == {
        "child": {"answer": "done"},
        "_sub_run_id": str(sub_run_id),
    }
    context.resolve_variable_ref.assert_awaited_once_with("start.q")
    run_child.assert_awaited_once_with(
        workflow_id=UUID(workflow_id),
        inputs={"query": "resolved", "limit": 3},
        user_id=parent.triggered_by_id,
        team_id=None,
        stream=False,
    )
    WorkflowRun.filter.assert_called_once_with(id=sub_run_id)
    assert child.parent_run_id == parent.id
    assert child.root_run_id == parent.id
    assert child.depth == parent.depth + 1
    child.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {"outputVariable": "", "outputMapping": {"local": "remote"}},
            {"local": 7},
        ),
        ({"outputVariable": ""}, {"remote": 7}),
    ],
)
async def test_supports_legacy_output_mapping_and_passthrough(
    dependencies, config, expected
):
    _, run_query, run_child = dependencies
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    run_query.first.return_value = SimpleNamespace(
        status="completed", outputs={"remote": 7}, save=AsyncMock()
    )

    result = await SubWorkflowNodeExecutor().execute(
        node(**config), MagicMock(), parent_run()
    )

    assert result.outputs == {"_sub_run_id": str(sub_run_id), **expected}


@pytest.mark.asyncio
async def test_requires_trigger_user_before_starting_child(dependencies):
    _, run_query, run_child = dependencies

    result = await SubWorkflowNodeExecutor().execute(
        node(), MagicMock(), parent_run(triggered_by_id=None)
    )

    assert result.error == "validation_error"
    run_child.assert_not_awaited()
    run_query.first.assert_not_awaited()


@pytest.mark.asyncio
async def test_returns_not_found_when_child_run_lookup_misses(dependencies):
    _, run_query, _ = dependencies
    run_query.first.return_value = None

    result = await SubWorkflowNodeExecutor().execute(node(), MagicMock(), parent_run())

    assert result.error == "workflow_run_not_found"


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_error", [True, False])
async def test_handles_failed_child_status(dependencies, monkeypatch, fail_on_error):
    _, run_query, run_child = dependencies
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    run_query.first.return_value = SimpleNamespace(
        status="failed", error_message="private", save=AsyncMock()
    )
    translate = MagicMock(return_value="public_error")
    monkeypatch.setattr(subworkflow, "translate_public_workflow_error", translate)

    result = await SubWorkflowNodeExecutor().execute(
        node(failOnError=fail_on_error), MagicMock(), parent_run()
    )

    translate.assert_called_once_with("private")
    if fail_on_error:
        assert result.error == "public_error"
    else:
        assert result.outputs == {
            "_status": "failed",
            "_error": "public_error",
            "_sub_run_id": str(sub_run_id),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_error", [True, False])
async def test_translates_timeout_boundary(dependencies, monkeypatch, fail_on_error):
    _, _, run_child = dependencies
    timeout = TimeoutError("late")
    run_child.side_effect = timeout
    translate = MagicMock(return_value="timeout_error")
    monkeypatch.setattr(subworkflow, "translate_public_workflow_error", translate)

    result = await SubWorkflowNodeExecutor().execute(
        node(failOnError=fail_on_error), MagicMock(), parent_run()
    )

    translate.assert_called_once_with(timeout)
    if fail_on_error:
        assert result.error == "timeout_error"
    else:
        assert result.outputs == {"_status": "error", "_error": "timeout_error"}


@pytest.mark.asyncio
async def test_propagates_task_cancellation(dependencies):
    _, _, run_child = dependencies
    run_child.side_effect = asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await SubWorkflowNodeExecutor().execute(node(), MagicMock(), parent_run())


@pytest.mark.asyncio
async def test_uses_legacy_config_and_input_shape(dependencies):
    _, run_query, run_child = dependencies
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    run_query.first.return_value = SimpleNamespace(
        status="completed", outputs={}, save=AsyncMock()
    )
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock(side_effect=["first", "second"])
    workflow_id = str(uuid4())
    legacy_node = {
        "data": {
            "config": {
                "workflowId": workflow_id,
                "inputs": [
                    {"name": "a", "source": "other", "value": "start.a"},
                    {"name": "b", "source": "other", "variableRef": "start.b"},
                ],
            }
        }
    }

    await SubWorkflowNodeExecutor().execute(legacy_node, context, parent_run())

    assert context.resolve_variable_ref.await_args_list == [
        call("start.a"),
        call("start.b"),
    ]
    assert run_child.await_args.kwargs["inputs"] == {"a": "first", "b": "second"}
