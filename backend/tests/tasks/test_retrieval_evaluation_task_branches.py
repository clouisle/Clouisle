from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.retrieval_evaluation import EvaluationRunStatus
from app.tasks import retrieval_evaluation as task
from tests.tasks.test_retrieval_evaluation_task import Cases, Query


def objects(*, canceled=False):
    case = SimpleNamespace(
        id=uuid4(),
        query="q",
        chunk_relevance={},
        document_relevance={},
        expected_empty=True,
    )
    dataset = SimpleNamespace(knowledge_base_id=uuid4(), cases=Cases([case]))
    run = SimpleNamespace(
        id=uuid4(),
        dataset=dataset,
        status="pending",
        started_at=None,
        config_snapshot={
            "search_mode": "fulltext",
            "top_k": 10,
            "score_threshold": 0,
            "dense_weight": 1,
            "lexical_weight": 1,
            "rrf_k": 60,
            "rerank_enabled": False,
            "rerank_candidate_k": 20,
            "rerank_fail_open": True,
            "rerank_score_threshold": None,
        },
        save=AsyncMock(),
        refresh_from_db=AsyncMock(),
        summary_metrics=None,
        finished_at=None,
        error_message=None,
    )
    if canceled:

        async def refresh(*, fields):
            run.status = EvaluationRunStatus.CANCELED.value

        run.refresh_from_db.side_effect = refresh
    kb = SimpleNamespace(
        id=dataset.knowledge_base_id,
        name="kb",
        team_id=uuid4(),
        status="active",
        embedding_model_id=None,
        rerank_model_id=None,
        embedding_dimension=None,
    )
    return run, kb


@pytest.mark.anyio
async def test_task_stops_when_canceled_before_case_retrieval():
    run, kb = objects(canceled=True)
    retrieve = AsyncMock()
    with (
        patch.object(task.EvaluationRun, "filter", return_value=Query(run)),
        patch.object(task.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(task, "retrieve", retrieve),
    ):
        result = await task.execute_evaluation_run(run.id)
    assert result["status"] == "canceled"
    retrieve.assert_not_awaited()


@pytest.mark.anyio
async def test_task_records_stable_case_error_then_handles_persistence_failure():
    run, kb = objects()
    update = AsyncMock(side_effect=RuntimeError("secret"))
    with (
        patch.object(task.EvaluationRun, "filter", return_value=Query(run)),
        patch.object(task.KnowledgeBase, "get", AsyncMock(return_value=kb)),
        patch.object(
            task, "retrieve", AsyncMock(side_effect=ValueError("private query"))
        ),
        patch.object(task.EvaluationCaseResult, "update_or_create", update),
    ):
        result = await task.execute_evaluation_run(run.id)
    assert update.await_args.kwargs["defaults"]["error_message"] == "ValueError"
    assert result["status"] == "failed"
    assert run.error_message == "RuntimeError"
    assert run.finished_at is not None


def test_celery_wrapper_runs_async_executor():
    run_id = uuid4()
    execute = MagicMock(return_value="coroutine")
    with (
        patch.object(task, "execute_evaluation_run", execute),
        patch.object(task.asyncio, "run", return_value={"status": "completed"}) as run,
    ):
        result = task.execute_evaluation_run_task(str(run_id))
    execute.assert_called_once_with(run_id)
    run.assert_called_once_with("coroutine")
    assert result["status"] == "completed"
