from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import WorkflowStatus, TriggerType
from app.schemas.response import BusinessError, ResponseCode
from app.services.workflow.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkStatus,
    LatencyHistogram,
    WorkflowBenchmark,
    compare_benchmarks,
    get_benchmark,
)
from app.services.workflow.errors import ExecutionCancelledError, ExecutionTimeoutError
from app.services.workflow.orchestrator import WorkflowOrchestrator


@pytest.mark.asyncio
async def test_webhook_rejects_restricted_api_key_without_workflow_access():
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    api_key = SimpleNamespace(workflows=SimpleNamespace(all=AsyncMock(return_value=[])))
    workflow = SimpleNamespace(
        id=workflow_id,
        webhook_token="token",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.WEBHOOK,
        team_id=None,
    )

    query = MagicMock()
    query.prefetch_related.return_value.all = AsyncMock(return_value=[workflow])

    run = SimpleNamespace(id=uuid4())
    task = SimpleNamespace(delay=MagicMock())

    with (
        patch(
            "app.api.deps._authenticate_api_key",
            AsyncMock(return_value=(user, api_key)),
        ),
        patch.object(workflows.Workflow, "filter", return_value=query),
        patch.object(workflows.WorkflowRun, "create", AsyncMock(return_value=run)),
        patch.dict(
            "sys.modules",
            {"app.tasks.workflow": SimpleNamespace(run_workflow_task=task)},
        ),
    ):
        response = await workflows.trigger_workflow_webhook(
            webhook_token="token",
            inputs={"query": "hi"},
            authorization="Bearer clou_ok",
        )

    assert response["data"]["status"] == "pending"
    api_key.workflows.all.assert_awaited_once()

    other_workflow = SimpleNamespace(id=uuid4())
    api_key.workflows.all = AsyncMock(return_value=[other_workflow])

    with (
        patch(
            "app.api.deps._authenticate_api_key",
            AsyncMock(return_value=(user, api_key)),
        ),
        patch.object(workflows.Workflow, "filter", return_value=query),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await workflows.trigger_workflow_webhook(
                webhook_token="token",
                inputs={"query": "hi"},
                authorization="Bearer clou_ok",
            )

    assert exc_info.value.code == ResponseCode.FORBIDDEN
    assert exc_info.value.msg_key == "api_key_no_workflow_access"


@pytest.mark.asyncio
async def test_run_and_debug_wrap_db_or_task_errors():
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    run_request = SimpleNamespace(inputs={"query": "hi"})
    workflow = SimpleNamespace(
        id=workflow_id,
        name="Flow",
        status=WorkflowStatus.PUBLISHED,
        trigger_type=TriggerType.MANUAL,
        team_id=None,
    )

    with (
        patch.object(
            workflows, "check_workflow_access", AsyncMock(return_value=workflow)
        ),
        patch.object(
            workflows.WorkflowRun,
            "create",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await workflows.run_workflow(workflow_id, run_request, request, user)

    assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
    assert exc_info.value.msg_key == "workflow_execution_error"

    with (
        patch.object(
            workflows, "check_workflow_access", AsyncMock(return_value=workflow)
        ),
        patch.object(
            workflows.WorkflowRun,
            "create",
            AsyncMock(side_effect=RuntimeError("db down")),
        ),
    ):
        with pytest.raises(BusinessError) as exc_info:
            await workflows.debug_workflow(workflow_id, run_request, request, user)

    assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
    assert exc_info.value.msg_key == "workflow_execution_error"


@pytest.mark.asyncio
async def test_stream_and_cancel_reject_runs_without_workflow_id():
    run_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    run = SimpleNamespace(workflow_id=None)
    query = MagicMock()
    query.prefetch_related.return_value.first = AsyncMock(return_value=run)

    with patch.object(workflows.WorkflowRun, "filter", return_value=query):
        with pytest.raises(BusinessError) as exc_info:
            await workflows.stream_workflow_run(run_id, current_user=user)

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "workflow_not_found"

    with patch.object(workflows.WorkflowRun, "filter", return_value=query):
        with pytest.raises(BusinessError) as exc_info:
            await workflows.cancel_workflow_run(run_id, request, user)

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "workflow_not_found"


@pytest.mark.asyncio
async def test_orchestrator_branches_cover_timeout_cancel_missing_node_and_labels():
    orchestrator = WorkflowOrchestrator(
        timeout=1, enable_retry=False, enable_cache=False
    )
    run = SimpleNamespace(id=uuid4())

    timeout_plan = SimpleNamespace(stages=[SimpleNamespace(node_ids=[])])
    context = SimpleNamespace(get_status=AsyncMock(return_value="running"))
    with patch("app.services.workflow.orchestrator.time.time", return_value=10):
        with pytest.raises(ExecutionTimeoutError):
            await orchestrator._execute(timeout_plan, context, run, None, start_time=0)

    cancelled_plan = SimpleNamespace(stages=[SimpleNamespace(node_ids=[])])
    context = SimpleNamespace(get_status=AsyncMock(return_value="cancelled"))
    with patch("app.services.workflow.orchestrator.time.time", return_value=0):
        with pytest.raises(ExecutionCancelledError):
            await orchestrator._execute(
                cancelled_plan, context, run, None, start_time=0
            )

    missing_plan = SimpleNamespace(get_node=MagicMock(return_value=None))
    with pytest.raises(Exception):
        await orchestrator._execute_node("missing", missing_plan, context, run, None)

    condition_node = SimpleNamespace(
        node_type="condition",
        node_data={"data": {}},
        upstream=set(),
        handle_map={"true": ["missing_downstream"], "false": ["taken"]},
    )
    unknown_plan = SimpleNamespace(
        stages=[SimpleNamespace(node_ids=["cond"])],
        get_node=MagicMock(
            side_effect=lambda node_id: condition_node if node_id == "cond" else None
        ),
        get_all_downstream=MagicMock(return_value=[]),
    )
    stream = SimpleNamespace(publish_node_skip=AsyncMock())
    orchestrator._execute_node = AsyncMock(
        return_value=SimpleNamespace(outputs={}, next_handles=["false"])
    )

    with (
        patch("app.services.workflow.orchestrator.time.time", return_value=0),
        patch(
            "app.services.workflow.orchestrator.get_node_type_label",
            AsyncMock(return_value=None),
        ),
    ):
        await orchestrator._execute(
            unknown_plan,
            SimpleNamespace(get_status=AsyncMock(return_value="running")),
            run,
            stream,
            start_time=0,
        )

    stream.publish_node_skip.assert_awaited_once_with(
        node_id="missing_downstream",
        reason="branch_not_taken",
        node_type=None,
        node_label="missing_downstream",
    )


@pytest.mark.asyncio
async def test_benchmark_residual_branches_and_helpers():
    benchmark = WorkflowBenchmark()
    config = BenchmarkConfig(concurrent_users=1, requests_per_user=1, warmup_requests=0)

    async def bad_executor(_inputs):
        raise RuntimeError("boom")

    result = await benchmark.run("bad", bad_executor, lambda: {}, config)
    assert result.status == BenchmarkStatus.COMPLETED
    assert result.failed_requests == 1
    assert result.errors == {"boom": 1}

    timeout = await benchmark._execute_request(
        "req", lambda _inputs: AsyncMock()(), {}, timeout=0
    )
    assert timeout.success is False
    assert timeout.error == "timeout"

    empty = BenchmarkResult(
        benchmark_id="empty",
        status=BenchmarkStatus.RUNNING,
        config=config,
        start_time=datetime.now(timezone.utc),
    )
    benchmark._calculate_stats(empty)
    assert empty.total_requests == 0
    assert await benchmark.cancel("missing") is False
    assert benchmark.get_status("missing") is None

    histogram = LatencyHistogram(buckets=[1, 10])
    assert histogram.get_percentile(0.95) == 0
    histogram.observe(50)
    assert histogram.get_distribution()[">10ms"] == 1
    assert histogram.get_percentile(0.95) == 10

    fake_result = BenchmarkResult(
        benchmark_id="quick",
        status=BenchmarkStatus.COMPLETED,
        config=config,
        start_time=datetime.now(timezone.utc),
        total_requests=0,
        successful_requests=0,
        mean_latency=2,
        p95_latency=3,
        requests_per_second=4,
    )
    fake_benchmark = SimpleNamespace(run=AsyncMock(return_value=fake_result))
    with patch(
        "app.services.workflow.benchmark.WorkflowBenchmark", return_value=fake_benchmark
    ):
        results = await compare_benchmarks({"one": bad_executor}, lambda: {}, config)
    assert results == {"one": fake_result}

    with patch("app.services.workflow.benchmark._benchmark", None):
        assert get_benchmark() is get_benchmark()
