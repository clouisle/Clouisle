from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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
def mocked_execution(monkeypatch):
    workflow_query = MagicMock()
    workflow_query.first = AsyncMock(return_value=SimpleNamespace())
    run_query = MagicMock()
    run_query.first = AsyncMock()
    run_child = AsyncMock(return_value=uuid4())

    monkeypatch.setattr(Workflow, "filter", MagicMock(return_value=workflow_query))
    monkeypatch.setattr(WorkflowRun, "filter", MagicMock(return_value=run_query))
    monkeypatch.setattr(WorkflowOrchestrator, "run", run_child)
    return workflow_query, run_query, run_child


def make_node(**config):
    return {"data": {"subWorkflowConfig": {"workflowId": str(uuid4()), **config}}}


def make_parent(**overrides):
    values = {
        "id": uuid4(),
        "root_run_id": None,
        "depth": 1,
        "triggered_by_id": uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_rejects_invalid_setup_and_missing_records(mocked_execution):
    workflow_query, run_query, run_child = mocked_execution
    executor = SubWorkflowNodeExecutor()

    result = await executor.execute(
        {"data": {"config": {}}}, MagicMock(), make_parent()
    )
    assert result.error == "validation_error"

    with pytest.raises(MaxDepthExceededError):
        await executor.execute(make_node(), MagicMock(), make_parent(depth=MAX_DEPTH))

    workflow_query.first.return_value = None
    result = await executor.execute(make_node(), MagicMock(), make_parent())
    assert result.error == "workflow_not_found"

    workflow_query.first.return_value = SimpleNamespace()
    result = await executor.execute(
        make_node(), MagicMock(), make_parent(triggered_by_id=None)
    )
    assert result.error == "validation_error"
    run_child.assert_not_awaited()

    run_child.return_value = uuid4()
    run_query.first.return_value = None
    result = await executor.execute(make_node(), MagicMock(), make_parent())
    assert result.error == "workflow_run_not_found"


@pytest.mark.asyncio
async def test_maps_inputs_runs_child_and_wraps_outputs(mocked_execution):
    _, run_query, run_child = mocked_execution
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    child = SimpleNamespace(
        status="completed", outputs={"answer": "done"}, save=AsyncMock()
    )
    run_query.first.return_value = child
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value="resolved"))
    parent = make_parent(root_run_id=uuid4())
    workflow_id = str(uuid4())

    result = await SubWorkflowNodeExecutor().execute(
        make_node(
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
    run_child.assert_awaited_once_with(
        workflow_id=UUID(workflow_id),
        inputs={"query": "resolved", "limit": 3},
        user_id=parent.triggered_by_id,
        team_id=None,
        stream=False,
    )
    assert (child.parent_run_id, child.root_run_id, child.depth) == (
        parent.id,
        parent.root_run_id,
        parent.depth + 1,
    )
    child.save.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"outputVariable": "", "outputMapping": {"local": "remote"}}, {"local": 7}),
        ({"outputVariable": ""}, {"remote": 7}),
    ],
)
async def test_supports_legacy_output_modes(mocked_execution, config, expected):
    _, run_query, run_child = mocked_execution
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    run_query.first.return_value = SimpleNamespace(
        status="completed", outputs={"remote": 7}, save=AsyncMock()
    )

    result = await SubWorkflowNodeExecutor().execute(
        make_node(**config), MagicMock(), make_parent()
    )

    assert result.outputs == {"_sub_run_id": str(sub_run_id), **expected}


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_error", [True, False])
async def test_handles_failed_child(mocked_execution, monkeypatch, fail_on_error):
    _, run_query, run_child = mocked_execution
    sub_run_id = uuid4()
    run_child.return_value = sub_run_id
    run_query.first.return_value = SimpleNamespace(
        status="failed", error_message="private", save=AsyncMock()
    )
    monkeypatch.setattr(
        subworkflow, "translate_public_workflow_error", MagicMock(return_value="public")
    )

    result = await SubWorkflowNodeExecutor().execute(
        make_node(failOnError=fail_on_error), MagicMock(), make_parent()
    )

    if fail_on_error:
        assert result.error == "public"
    else:
        assert result.outputs == {
            "_status": "failed",
            "_error": "public",
            "_sub_run_id": str(sub_run_id),
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_error", [True, False])
async def test_translates_execution_exception(
    mocked_execution, monkeypatch, fail_on_error
):
    _, _, run_child = mocked_execution
    error = TimeoutError("late")
    run_child.side_effect = error
    translate = MagicMock(return_value="timeout_error")
    monkeypatch.setattr(subworkflow, "translate_public_workflow_error", translate)

    result = await SubWorkflowNodeExecutor().execute(
        make_node(failOnError=fail_on_error), MagicMock(), make_parent()
    )

    translate.assert_called_once_with(error)
    if fail_on_error:
        assert result.error == "timeout_error"
    else:
        assert result.outputs == {"_status": "error", "_error": "timeout_error"}


@pytest.mark.asyncio
async def test_uses_legacy_config_and_mapping_shape(mocked_execution):
    _, run_query, run_child = mocked_execution
    run_query.first.return_value = SimpleNamespace(
        status="completed", outputs=None, save=AsyncMock()
    )
    context = SimpleNamespace(resolve_variable_ref=AsyncMock(return_value="resolved"))
    parent = SimpleNamespace(id=uuid4(), root_run_id=None, triggered_by_id=uuid4())
    workflow_id = str(uuid4())

    result = await SubWorkflowNodeExecutor().execute(
        {
            "data": {
                "config": {
                    "workflowId": workflow_id,
                    "inputs": [
                        {"name": "query", "source": "other", "value": "start.q"},
                        {"name": "empty", "source": "other", "variableRef": ""},
                    ],
                }
            }
        },
        context,
        parent,
    )

    assert result.outputs == {"result": {}, "_sub_run_id": str(run_child.return_value)}
    assert run_child.await_args.kwargs["inputs"] == {"query": "resolved"}


@pytest.mark.asyncio
async def test_validates_config_and_describes_outputs():
    executor = SubWorkflowNodeExecutor()

    assert await executor.validate_config({}) == ["Sub-workflow ID is required"]
    assert await executor.validate_config({"workflowId": "id"}) == []
    assert executor.get_output_variables({}) == [{"name": "result", "type": "any"}]
    assert executor.get_output_variables({"outputMapping": {"local": "remote"}}) == [
        {"name": "local", "type": "any"}
    ]
    assert [spec.name for spec in executor.get_output_specs({})] == ["result"]
    assert [
        spec.name
        for spec in executor.get_output_specs(
            {"outputMapping": {"first": "a", "second": "b"}}
        )
    ] == ["first", "second"]
